-- Policy engine - autonomous-execution gate.
--
-- After a brief drops, the policy engine evaluates rules in priority
-- order. If a rule matches AND its mode is 'auto', the case skips the
-- awaiting_approval step: actions are auto-approved and fired by the
-- actor worker. If the rule's mode is 'recommend', we still mark a
-- match (for the UI to surface) but require human approval.
--
-- Rules use a simple JSON DSL evaluated in services/policy.py:
--   {"all": [ {field: {op: value}}, ... ]}    - AND
--   {"any": [ ... ]}                          - OR
--   field paths: case.case_type, case.amount_minor, case.trigger_surface,
--                case.decision_action, customer.has_prior_disputes, etc.

CREATE TABLE IF NOT EXISTS policy_rules (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    description   TEXT,
    conditions    JSONB NOT NULL DEFAULT '{}'::jsonb,
    decision      JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {mode: auto|recommend|hitl, action: refund|fight|..., reply_to_customer: bool}
    priority      INT NOT NULL DEFAULT 100,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by    UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_rules_org_priority
    ON policy_rules (org_id, priority ASC)
    WHERE enabled = TRUE;

CREATE TABLE IF NOT EXISTS policy_matches (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    case_id      UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    rule_id      UUID NOT NULL REFERENCES policy_rules(id) ON DELETE CASCADE,
    mode         TEXT NOT NULL,            -- 'auto' | 'recommend' | 'hitl'
    matched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    snapshot     JSONB                     -- the case fields the rule matched against
);

CREATE INDEX IF NOT EXISTS idx_policy_matches_case ON policy_matches (case_id);
CREATE INDEX IF NOT EXISTS idx_policy_matches_rule_recent ON policy_matches (rule_id, matched_at DESC);
