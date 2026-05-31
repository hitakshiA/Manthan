-- Manthan v1 backend schema.
-- Multi-tenant Postgres. Every row scoped by org_id.
-- Events table is the single source of truth (12-Factor Agents pattern).
-- Derived projections (cases, actions) catch up via background workers.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ──────────────────────────────────────────────────────────────────────
-- Tenancy root
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE orgs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    plan          TEXT NOT NULL DEFAULT 'design_partner',  -- design_partner | growth | enterprise
    coral_socket  TEXT,                                    -- path to per-org Coral stdio socket
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE members (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    name            TEXT,
    role            TEXT NOT NULL DEFAULT 'approver',  -- admin | approver | viewer
    approval_limit_minor BIGINT NOT NULL DEFAULT 50000,  -- $500 default
    clerk_user_id   TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, email)
);

CREATE INDEX idx_members_clerk ON members(clerk_user_id);

-- ──────────────────────────────────────────────────────────────────────
-- Event log - single source of truth
-- Every case is a thread. Events accumulate. State is derived.
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE events (
    id          BIGSERIAL PRIMARY KEY,
    org_id      UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    thread_id   UUID NOT NULL,
    seq         INT NOT NULL,
    type        TEXT NOT NULL,
    -- case_opened | tool_call | tool_result | finding_recorded | reflexion |
    -- brief_drafted | hitl_paused | hitl_resumed | action_enqueued |
    -- action_executed | action_verified | drift_detected | case_closed | error
    actor       TEXT NOT NULL,  -- system | agent | human:member:<uuid> | source:stripe | ...
    data        JSONB NOT NULL DEFAULT '{}',
    signed_at   TIMESTAMPTZ,                          -- HMAC signature timestamp
    signature   TEXT,                                  -- hex HMAC over (org_id, thread_id, seq, type, data)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, thread_id, seq)
);

CREATE INDEX idx_events_thread     ON events(org_id, thread_id, seq);
CREATE INDEX idx_events_type       ON events(org_id, type, created_at DESC);
CREATE INDEX idx_events_created    ON events(org_id, created_at DESC);

-- Notify channel - workers LISTEN to react to new triggers.
CREATE OR REPLACE FUNCTION notify_event() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(
        'manthan_event',
        json_build_object(
            'org_id', NEW.org_id,
            'thread_id', NEW.thread_id,
            'type', NEW.type,
            'event_id', NEW.id
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER events_notify AFTER INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION notify_event();

-- ──────────────────────────────────────────────────────────────────────
-- Case workspace projection
-- Derived from events; updated by worker on case_opened / case_closed / etc.
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE cases (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id              UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    thread_id           UUID UNIQUE NOT NULL,
    short_id            TEXT NOT NULL,        -- "CASE-4821" - display id
    status              TEXT NOT NULL DEFAULT 'investigating',
    -- investigating | awaiting_approval | acting | resolved | errored | escalated
    trigger_surface     TEXT NOT NULL,
    -- stripe_webhook | inbound_email | slack_mention | cron | web_new | api
    trigger_payload     JSONB NOT NULL DEFAULT '{}',
    customer_ref        TEXT,                  -- e.g. "Summit Payments" or external id
    case_type           TEXT,                  -- chargeback | refund_request | sla_credit | failed_renewal | invoice_dispute
    amount_minor        BIGINT,
    currency            TEXT DEFAULT 'usd',
    decision_action     TEXT,                  -- refund | fight | partial_credit | escalate
    decision_amount_minor BIGINT,
    decision_confidence NUMERIC(3,2),
    assigned_member_id  UUID REFERENCES members(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    UNIQUE (org_id, short_id)
);

CREATE INDEX idx_cases_org_status  ON cases(org_id, status, created_at DESC);
CREATE INDEX idx_cases_assignee    ON cases(assigned_member_id) WHERE assigned_member_id IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────
-- Findings cache (denormalized from events for fast UI queries)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE findings (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id       UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    case_id      UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    seq          INT NOT NULL,
    text         TEXT NOT NULL,
    confidence   NUMERIC(3,2),
    citations    JSONB NOT NULL DEFAULT '[]',
    -- e.g. [{"source":"stripe","table":"disputes","ref":"du_xxx","field":"reason"}]
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (case_id, seq)
);

CREATE INDEX idx_findings_case ON findings(case_id, seq);

-- ──────────────────────────────────────────────────────────────────────
-- Actions queue (Action Executor drains this)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE actions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id              UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    case_id             UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    seq                 INT NOT NULL,         -- ordering within a case
    type                TEXT NOT NULL,
    -- stripe.refund | stripe.dispute_response | resend.send_email |
    -- linear.create_issue | hubspot.create_note | notion.append_block | slack.post
    payload             JSONB NOT NULL,
    idempotency_key     TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'drafted',
    -- drafted | awaiting_approval | approved | executing | succeeded | failed | drift
    external_ref        TEXT,                  -- e.g. "re_xxx" from Stripe
    verified_at         TIMESTAMPTZ,
    approved_by         UUID REFERENCES members(id),
    approved_at         TIMESTAMPTZ,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, idempotency_key)
);

CREATE INDEX idx_actions_pending   ON actions(org_id, status) WHERE status IN ('approved','executing');
CREATE INDEX idx_actions_case      ON actions(case_id, seq);

-- ──────────────────────────────────────────────────────────────────────
-- Source connections (per-org credentials, encrypted at rest)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE sources (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id              UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    kind                TEXT NOT NULL,
    -- stripe | salesforce | hubspot | intercom | zendesk | notion |
    -- slack | pagerduty | sentry | posthog | datadog | resend
    label               TEXT,
    config_encrypted    BYTEA NOT NULL,        -- encrypted JSON (kms-managed key)
    status              TEXT NOT NULL DEFAULT 'connected',  -- connected | degraded | broken
    last_health_check   TIMESTAMPTZ,
    last_token_refresh  TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, kind, label)
);

CREATE INDEX idx_sources_org ON sources(org_id, kind);

-- ──────────────────────────────────────────────────────────────────────
-- Policy (per-org versioned)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE policies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    version         INT NOT NULL,
    yaml_body       TEXT NOT NULL,
    shadow_mode     BOOLEAN NOT NULL DEFAULT false,
    activated_at    TIMESTAMPTZ,
    created_by      UUID REFERENCES members(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, version)
);

CREATE INDEX idx_policies_active ON policies(org_id) WHERE activated_at IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────
-- Memory tiers (episodic = events table; semantic + procedural here)
-- ──────────────────────────────────────────────────────────────────────

-- Semantic memory uses pgvector. Lazy-loaded; only enabled when needed.
-- CREATE EXTENSION IF NOT EXISTS vector;
-- CREATE TABLE memory_semantic (
--     id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     org_id        UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
--     kind          TEXT NOT NULL,  -- case | finding | source_row
--     ref           TEXT NOT NULL,
--     text          TEXT NOT NULL,
--     embedding     vector(1536),
--     created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
-- CREATE INDEX idx_memory_semantic_org ON memory_semantic(org_id, kind);

-- Procedural memory - YAML skills the agent loads at runtime.
CREATE TABLE memory_procedural (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    skill_name      TEXT NOT NULL,
    yaml_body       TEXT NOT NULL,
    -- description + when_to_use + steps
    learned_from_case_ids UUID[] NOT NULL DEFAULT '{}',
    confidence_score NUMERIC(3,2) NOT NULL DEFAULT 0.5,
    activated        BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, skill_name)
);

CREATE INDEX idx_procedural_org ON memory_procedural(org_id) WHERE activated = true;

-- ──────────────────────────────────────────────────────────────────────
-- HITL pending approvals (resumable interrupts)
-- ──────────────────────────────────────────────────────────────────────

CREATE TABLE hitl_pending (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id              UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    case_id             UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    thread_id           UUID NOT NULL,
    checkpoint_data     JSONB NOT NULL,        -- serialized agent state
    decision_required   TEXT NOT NULL,          -- approve_actions | edit_brief | re_investigate
    assigned_to         UUID REFERENCES members(id),
    backup_assignee     UUID REFERENCES members(id),
    approval_token      TEXT UNIQUE NOT NULL,   -- for magic-link email approval
    deadline            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    resolution          TEXT                    -- approved | rejected | edited | timed_out
);

CREATE INDEX idx_hitl_assignee ON hitl_pending(assigned_to) WHERE resolved_at IS NULL;
CREATE INDEX idx_hitl_org_open ON hitl_pending(org_id, created_at DESC) WHERE resolved_at IS NULL;
