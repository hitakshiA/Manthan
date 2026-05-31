-- Auth signups - dedup table for the Clerk user.created webhook.
--
-- When Clerk fires `user.created`, we send a Manthan-branded MVP
-- welcome email via Resend. This table is the idempotency guard so a
-- redelivered webhook doesn't double-send.
--
-- We DO NOT use this as the source of truth for "who's logged in" -
-- that's still Clerk. This is just (a) dedup, (b) audit trail for
-- "who got the welcome email and when".

CREATE TABLE IF NOT EXISTS auth_signups (
    clerk_user_id   TEXT PRIMARY KEY,           -- Clerk's id; opaque
    email           TEXT NOT NULL,              -- primary email at signup
    first_name      TEXT,                       -- optional, for email greeting
    last_name       TEXT,
    welcome_sent_at TIMESTAMPTZ,                -- null until the email lands
    welcome_email_id TEXT,                      -- Resend message id
    source          TEXT NOT NULL DEFAULT 'clerk',  -- room for future paths
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_signups_email ON auth_signups(lower(email));
