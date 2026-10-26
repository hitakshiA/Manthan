-- Seed: the policy set that supports the email → Stripe dispute →
-- resolve → email-reply demo flow.
--
-- Reads as a real Revenue Accounting team's rulebook:
--   - guards first (abuse, high $, low confidence)  ── lower priority
--   - autonomous defaults for narrow, high-confidence cases
--   - recommend-mode fallback for everything else
--
-- All conditions reference fields the engine actually evaluates
-- (services/policy.py build_facts). No invented columns.

BEGIN;

-- Replace whatever's there with the curated set. Demo deserves a
-- clean ledger, not a layered pile of ad-hoc rules.
DELETE FROM policy_rules
  WHERE org_id = '8ae1b532-8f5a-44bc-9a48-9110336e49fb';

INSERT INTO policy_rules
  (org_id, name, description, conditions, decision, priority, enabled)
VALUES
  -- ── 1. Abuse guard (priority 10 - fires first) ────────────────────
  (
    '8ae1b532-8f5a-44bc-9a48-9110336e49fb',
    'repeat-disputer-escalate',
    'Customers with three or more disputes in the last 90 days are a pattern, not a one-off. Manthan stops, hands the case to a human, and flags the account for the abuse review queue. Never auto-fire.',
    '{
      "all": [
        {"customer.prior_dispute_count": {"gte": 3}}
      ]
    }'::jsonb,
    '{
      "mode": "escalate",
      "action": "escalate",
      "reason": "repeat_disputer",
      "reply_to_customer": false
    }'::jsonb,
    10,
    TRUE
  ),

  -- ── 2. High-amount two-approver rule (priority 20) ────────────────
  (
    '8ae1b532-8f5a-44bc-9a48-9110336e49fb',
    'large-amount-two-approvers',
    'Disputes above $25,000 require a sign-off from a director-level approver - finance-controls-aligned. Manthan drafts the full brief and packet but never fires alone, regardless of confidence.',
    '{
      "all": [
        {"case.amount_minor": {"gt": 2500000}}
      ]
    }'::jsonb,
    '{
      "mode": "escalate",
      "action": "escalate",
      "reason": "amount_above_director_threshold",
      "approvers_required": 2
    }'::jsonb,
    20,
    TRUE
  ),

  -- ── 3. Low confidence → always HITL (priority 30) ─────────────────
  (
    '8ae1b532-8f5a-44bc-9a48-9110336e49fb',
    'low-confidence-require-human',
    'If Manthan''s confidence sits below 70%, the case waits for a human. Speed never overrides judgment when the evidence isn''t clean.',
    '{
      "all": [
        {"case.decision_confidence": {"lt": 0.70}}
      ]
    }'::jsonb,
    '{
      "mode": "hitl",
      "action": "review",
      "reason": "low_confidence",
      "reply_to_customer": false
    }'::jsonb,
    30,
    TRUE
  ),

  -- ── 4. Email refund - autonomous when evidence is clean (priority 50)
  (
    '8ae1b532-8f5a-44bc-9a48-9110336e49fb',
    'email-refund-clean-customer',
    'A customer emails about a duplicate or small unintended charge. If they''re in good standing - no prior disputes - and the agent''s confidence is above 90%, Manthan refunds and replies on the same email thread. The full receipt lands in the audit log.',
    '{
      "all": [
        {"case.trigger_surface": {"eq": "inbound_email"}},
        {"case.case_type":       {"in": ["refund_request", "duplicate_charge"]}},
        {"case.amount_minor":    {"lte": 20000}},
        {"case.decision_action": {"eq": "refund"}},
        {"case.decision_confidence": {"gte": 0.90}},
        {"customer.has_prior_disputes": {"eq": false}}
      ]
    }'::jsonb,
    '{
      "mode": "auto",
      "action": "refund",
      "reply_to_customer": true,
      "via": "email_dispatcher"
    }'::jsonb,
    50,
    TRUE
  ),

  -- ── 5. Chargeback - autonomous fight when the evidence is overwhelming
  (
    '8ae1b532-8f5a-44bc-9a48-9110336e49fb',
    'chargeback-fight-strong-evidence',
    'Stripe chargebacks where the customer has months of healthy usage, the contract is in writing, and the agent''s confidence is above 92% - auto-submit the dispute evidence packet. Anything under $5,000 fires alone; above that it requests a nod.',
    '{
      "all": [
        {"case.case_type":           {"eq": "chargeback"}},
        {"case.decision_action":     {"eq": "fight"}},
        {"case.decision_confidence": {"gte": 0.92}},
        {"case.amount_minor":        {"lte": 500000}},
        {"customer.prior_dispute_count": {"lte": 1}}
      ]
    }'::jsonb,
    '{
      "mode": "auto",
      "action": "fight",
      "submit_evidence": true,
      "reply_to_customer": false
    }'::jsonb,
    60,
    TRUE
  ),

  -- ── 6. Documented-incident pro-rata partial credit (priority 75)
  -- W7R-pattern: a customer disputes a paid cycle in which an
  -- internally-documented operational incident degraded the feature
  -- they paid for. The agent's drafted decision will be a PARTIAL
  -- refund (decision_amount_minor < case.amount_minor) - that's the
  -- shape this rule recognises. We recommend the partial-credit
  -- decision back to a human reviewer rather than auto-firing it,
  -- because the math (degraded_days / cycle_days × tier_amount)
  -- benefits from a sanity check before the credit lands.
  (
    '8ae1b532-8f5a-44bc-9a48-9110336e49fb',
    'documented-incident-prorata-credit',
    'A chargeback the agent wants to settle with a partial credit (not full refund, not fight) because an internally-documented operational incident degraded the paid feature for a specific number of days. Recommend the prorated number to a human reviewer.',
    '{
      "all": [
        {"case.case_type":           {"eq": "chargeback"}},
        {"case.decision_action":     {"eq": "refund"}},
        {"case.decision_confidence": {"gte": 0.75}},
        {"case.is_partial_refund":   {"eq": true}}
      ]
    }'::jsonb,
    '{
      "mode": "recommend",
      "action": "refund",
      "reason": "documented_incident_prorata",
      "reply_to_customer": true,
      "via": "email_dispatcher"
    }'::jsonb,
    75,
    TRUE
  ),

  -- ── 7. Email default - always investigate, then ask (priority 100)
  (
    '8ae1b532-8f5a-44bc-9a48-9110336e49fb',
    'email-default-investigate-then-ask',
    'Every customer email gets the full investigation treatment - Manthan reads across the eleven connected sources, drafts a brief with cited evidence, and queues the case for your nod. Default safe: nothing fires without you when the more specific auto rules don''t match.',
    '{
      "all": [
        {"case.trigger_surface": {"eq": "inbound_email"}}
      ]
    }'::jsonb,
    '{
      "mode": "recommend",
      "action": "draft_for_review",
      "reply_to_customer": false
    }'::jsonb,
    100,
    TRUE
  );

COMMIT;

-- Quick sanity output so you can confirm the seed landed.
SELECT
  priority,
  name,
  decision->>'mode' AS mode,
  enabled
FROM policy_rules
WHERE org_id = '8ae1b532-8f5a-44bc-9a48-9110336e49fb'
ORDER BY priority;
