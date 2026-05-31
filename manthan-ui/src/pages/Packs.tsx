/**
 * Packs - domain packs that bundle triggers + sources + policy + actions
 * for a specific revenue workflow.
 *
 * Editorial form: a typeset table of contents. Each row in the pack is a
 * single hairline line. No card-per-row, no icon boxes.
 */

import {
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import { SourceIcon } from "@/components/ui/SourceIcon";

interface PackPageProps {
  pack: "billing" | "renewals";
}

export default function Packs({ pack }: PackPageProps) {
  if (pack === "billing") return <BillingPack />;
  return <RenewalsPack />;
}

// The flagship loop this pack runs end-to-end. Numbered as a six-beat
// playbook - what a Director would walk a partner through.
const BILLING_FLOW = [
  {
    n: "01",
    name: "Inbound - customer emails support@",
    detail:
      "Resend webhook delivers the parsed message. Manthan opens a case keyed to the sender's address, writes a Manthan-branded acknowledgement, and tells the customer when they'll hear back.",
  },
  {
    n: "02",
    name: "Investigation - eleven sources, one pass",
    detail:
      "Manthan reads the Stripe charge + dispute, the original contract in Notion, daily active usage in PostHog, the support ticket history in Intercom, and the NPS history in HubSpot. Every claim ends with a clickable citation.",
  },
  {
    n: "03",
    name: "Policy ledger evaluates the draft",
    detail:
      "Six rules run in priority order. Abuse and high-amount guards fire first, then the autonomous-fire rules, then the always-investigate fallback. The match lands on the case + the audit log.",
  },
  {
    n: "04",
    name: "Decision - auto, recommend, hitl, or escalate",
    detail:
      "If the rule matched 'auto', Manthan fires the actions itself. Otherwise the case sits in your inbox, awaiting one click. Below $25,000 a single approver; above, two - the rule decides.",
  },
  {
    n: "05",
    name: "Action - Stripe + Resend + Notion in sequence",
    detail:
      "Refund or dispute-evidence submission to Stripe, decision-log append in Notion, customer reply via Resend (Manthan-branded HTML, never policy-leaky). Each fire records its external ref.",
  },
  {
    n: "06",
    name: "Close - case resolved, receipts attached",
    detail:
      "Case flips to resolved with timestamps + external refs on every action. The customer's reply to your email routes back to the same case automatically.",
  },
];

// Triggers - ordered so the email path the demo shows is at the top.
const BILLING_TRIGGERS = [
  {
    label: "Inbound email to support@",
    sub: "The flagship surface. Resend webhook → case opened with the customer's email as the key.",
    primary: true,
  },
  {
    label: "Stripe webhook",
    sub: "charge.dispute.created, charge.refund.updated, radar.early_fraud_warning.created",
  },
  {
    label: "Slack @manthan mention",
    sub: "Triage in #cs-escalations. Manthan posts the brief in-thread and asks for the nod.",
  },
  {
    label: "Manual case open",
    sub: "Web UI '+ New case' or POST /api/cases with a trigger_text.",
  },
];

// Source byline list - order chosen so the eye lands on the four that
// drive most of the dispute decisions.
const BILLING_SOURCES = [
  "stripe",
  "notion",
  "intercom",
  "hubspot",
  "posthog",
  "salesforce",
  "zendesk",
  "slack",
  "sentry",
  "datadog",
  "pagerduty",
  "resend",
];

// The six policy rules currently seeded against this workspace. Names
// match the rows on /app/policy exactly.
const BILLING_POLICY = [
  {
    name: "repeat-disputer-escalate",
    mode: "escalate",
    detail:
      "Three or more disputes in 90 days = pattern, not one-off. Always hits a human.",
  },
  {
    name: "large-amount-two-approvers",
    mode: "escalate",
    detail:
      "Above $25,000 requires a director-level sign-off. Brief is drafted; firing is gated.",
  },
  {
    name: "low-confidence-require-human",
    mode: "hitl",
    detail:
      "Anything below 70% confidence pauses for a human. Speed never beats judgement on thin evidence.",
  },
  {
    name: "email-refund-clean-customer",
    mode: "auto",
    detail:
      "Email-triggered refund under $200, customer in good standing, confidence ≥ 90% - Manthan refunds and replies alone.",
  },
  {
    name: "chargeback-fight-strong-evidence",
    mode: "auto",
    detail:
      "Stripe chargeback under $5K, contract in writing, confidence ≥ 92% - Manthan submits the evidence packet on its own.",
  },
  {
    name: "email-default-investigate-then-ask",
    mode: "recommend",
    detail:
      "Every email gets the full investigation. If no auto rule matches, the case sits in your inbox waiting on one click.",
  },
];

const MODE_TONE: Record<string, string> = {
  auto: "var(--color-accent)",
  recommend: "var(--color-amber)",
  hitl: "var(--color-info)",
  escalate: "var(--color-danger)",
};

function BillingPack() {
  return (
    <PageBody width="narrow">
      <PageHeader
        eyebrow="Domain pack"
        title="Billing Ops"
        meta={
          <>
            The default pack this workspace runs - built around the
            <em
              className="font-display italic mx-1"
              style={{ color: "var(--color-ink-strong)" }}
            >
              email → Stripe dispute → resolve → email
            </em>
            loop. Source code lives in your git repo under{" "}
            <code
              className="font-mono text-[12px]"
              style={{ color: "var(--color-ink-strong)" }}
            >
              packs/billing.yaml
            </code>
            . Fork it, edit it, push it back.
          </>
        }
      />

      <Section
        eyebrow="The loop"
        trailing="six beats"
      >
        <ol
          className="divide-y border-t border-b"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          {BILLING_FLOW.map((step) => (
            <li
              key={step.n}
              className="py-3.5 grid"
              style={{
                gridTemplateColumns: "36px minmax(0, 1fr)",
                gap: 14,
                borderColor: "var(--color-rule-soft)",
              }}
            >
              <span
                className="font-mono text-[11px] tabular-nums pt-0.5"
                style={{
                  color: "var(--color-ink-faint)",
                  letterSpacing: "0.04em",
                }}
              >
                {step.n}
              </span>
              <div>
                <div
                  className="text-[13.5px]"
                  style={{ color: "var(--color-ink-strong)" }}
                >
                  {step.name}
                </div>
                <div
                  className="text-[12px] mt-1 leading-relaxed max-w-[64ch]"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  {step.detail}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section eyebrow="Triggers" trailing={`${BILLING_TRIGGERS.length}`}>
        <ul
          className="divide-y border-t border-b"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          {BILLING_TRIGGERS.map((t) => (
            <li
              key={t.label}
              className="py-3"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <div
                className="flex items-baseline gap-3 flex-wrap text-[13px]"
                style={{ color: "var(--color-ink-strong)" }}
              >
                {t.label}
                {t.primary && (
                  <span
                    className="text-[10px] uppercase tracking-[0.14em]"
                    style={{ color: "var(--color-accent)" }}
                  >
                    Demo path
                  </span>
                )}
              </div>
              <div
                className="text-[11.5px] mt-1 leading-relaxed max-w-[64ch]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                {t.sub}
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section eyebrow="Policy rules" trailing={`${BILLING_POLICY.length}`}>
        <ul
          className="divide-y border-t border-b"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          {BILLING_POLICY.map((p) => (
            <li
              key={p.name}
              className="py-3"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <div className="flex items-baseline gap-3 flex-wrap">
                <code
                  className="font-mono text-[12px]"
                  style={{ color: "var(--color-ink-strong)" }}
                >
                  {p.name}
                </code>
                <span
                  className="text-[10px] uppercase tracking-[0.14em]"
                  style={{ color: MODE_TONE[p.mode] ?? "var(--color-ink-faint)" }}
                >
                  {p.mode}
                </span>
              </div>
              <div
                className="text-[12px] mt-1 leading-relaxed max-w-[64ch]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                {p.detail}
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section eyebrow="Sources queried" trailing={`${BILLING_SOURCES.length}`}>
        <div className="flex flex-wrap gap-x-5 gap-y-2.5">
          {BILLING_SOURCES.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1.5 text-[12px]"
              style={{ color: "var(--color-ink-muted)" }}
            >
              <SourceIcon id={id} size={13} tinted />
              {id}
            </span>
          ))}
        </div>
      </Section>
    </PageBody>
  );
}

function RenewalsPack() {
  return (
    <PageBody width="narrow">
      <PageHeader
        eyebrow="Domain pack · Q3 2026"
        title="Renewals"
        meta="Renewal risk detection + save plays across your customer book. Roadmap teaser - not active in this workspace yet."
      />

      <Section eyebrow="What it will do">
        <p
          className="text-[13px] leading-relaxed max-w-prose"
          style={{ color: "var(--color-ink-muted)" }}
        >
          Reads usage telemetry (PostHog), CSM notes (Salesforce / HubSpot), and
          CS conversation sentiment (Intercom / Zendesk) to surface at-risk
          renewals 60-90 days out. Drafts save plays - discount, exec call,
          usage-recovery program - and lets the CSM approve from the queue.
        </p>
      </Section>

      <Section eyebrow="Want to design-partner this?">
        <p
          className="text-[13px] leading-relaxed max-w-prose"
          style={{ color: "var(--color-ink-muted)" }}
        >
          Email{" "}
          <a
            href="mailto:hello@manthan.quest"
            className="underline"
            style={{ color: "var(--color-ink-strong)" }}
          >
            hello@manthan.quest
          </a>{" "}
          with a description of your renewals workflow. We&apos;ll get back within
          a day.
        </p>
      </Section>
    </PageBody>
  );
}

function Lines({ rows }: { rows: { name: string; detail: string }[] }) {
  return (
    <ul
      className="divide-y border-t border-b"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      {rows.map((r) => (
        <li
          key={r.name}
          className="py-3"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          <div
            className="text-[13.5px]"
            style={{ color: "var(--color-ink-strong)" }}
          >
            {r.name}
          </div>
          <div
            className="text-[12px] mt-0.5 leading-relaxed"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {r.detail}
          </div>
        </li>
      ))}
    </ul>
  );
}
