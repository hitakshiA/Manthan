/**
 * HeroShowcase - Manthan landing demo.
 *
 * Aesthetic: Operations Memo (see .impeccable.md).
 *   - Three scenes, each with a DISTINCT layout grammar (not a templated
 *     sub-tab strip). Case workspace = long-form memo with sidebar list.
 *     Approval ledger = sortable table with row-expand inspector + bulk bar.
 *     Policy document = YAML editor with marginalia commentary.
 *   - Rules separate sections, not card borders.
 *   - Geist Sans body, Instrument Serif italic for accent words,
 *     Geist Mono for IDs / amounts / timestamps.
 *   - Numbered footnotes [1] [2] [3] cite evidence.
 *   - One desaturated emerald accent. No glow. No glassmorphism.
 *     No sparkles icon. No card-on-card.
 */

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Check,
  Filter,
  Pencil,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import { SourceIcon } from "@/components/ui/SourceIcon";

/* ═══════════════════════════════════════════════════════════════════════
   SAMPLE DATA - 8 distinct cases covering Manthan's full range:
     · 4821 TechCorp        - first-dispute chargeback, healthy account
     · 4815 StartupY        - SLA refund (service downtime)
     · 4810 AcmeInc         - enterprise invoice dispute, still investigating
     · 4805 Loop & Co       - auto-executed refund (under threshold)
     · 4798 ZenSaaS Studios - failed annual renewal (card expired)
     · 4793 PlanetGrid      - trial-end refund, fraud-pattern risk
     · 4781 Midcorp Systems - high-value card-expiry urgency
     · 4774 Pulse Healthcare - fraud-signal chargeback, suspected stolen card
   ═══════════════════════════════════════════════════════════════════════ */

type Tone = "awaiting" | "drafted" | "investigating" | "executing" | "resolved";
type CaseFilter = "all" | "mine" | "watching";
type Owner = "you" | "lina" | "raj" | "system";

interface CaseRow {
  num: string;
  customer: string;
  customerInitial: string;
  customerBg: [string, string]; // tailwind colors for avatar gradient
  type: string;
  amount: number;
  status: Tone;
  ago: string;
  drafts: number;
  risk?: "low" | "med" | "high";
  owner: Owner;
  watching: boolean;
}

const CASES: CaseRow[] = [
  { num: "4821", customer: "TechCorp Industries",  customerInitial: "T", customerBg: ["from-blue-500",   "to-blue-700"],     type: "Chargeback",      amount: 1200, status: "awaiting",      ago: "2m",  drafts: 3, risk: "low",  owner: "you",    watching: true  },
  { num: "4815", customer: "StartupY",             customerInitial: "S", customerBg: ["from-violet-500", "to-violet-700"],   type: "SLA refund",      amount:  840, status: "drafted",       ago: "11m", drafts: 3, risk: "low",  owner: "you",    watching: true  },
  { num: "4810", customer: "AcmeInc",              customerInitial: "A", customerBg: ["from-amber-500",  "to-amber-700"],    type: "Invoice dispute", amount: 3400, status: "investigating", ago: "24m", drafts: 0, risk: "med",  owner: "lina",   watching: true  },
  { num: "4805", customer: "Loop & Co",            customerInitial: "L", customerBg: ["from-emerald-500","to-emerald-700"],  type: "Refund request",  amount:  199, status: "executing",     ago: "38m", drafts: 3, risk: "low",  owner: "system", watching: false },
  { num: "4798", customer: "ZenSaaS Studios",      customerInitial: "Z", customerBg: ["from-cyan-500",   "to-cyan-700"],     type: "Failed renewal",  amount: 1890, status: "drafted",       ago: "1h",  drafts: 3, risk: "low",  owner: "raj",    watching: false },
  { num: "4793", customer: "PlanetGrid",           customerInitial: "P", customerBg: ["from-rose-500",   "to-rose-700"],     type: "Trial refund",    amount:   67, status: "awaiting",      ago: "1h",  drafts: 2, risk: "high", owner: "you",    watching: false },
  { num: "4781", customer: "Midcorp Systems",      customerInitial: "M", customerBg: ["from-orange-500", "to-orange-700"],   type: "Card expired",    amount: 4200, status: "investigating", ago: "2h",  drafts: 2, risk: "high", owner: "lina",   watching: true  },
  { num: "4774", customer: "Pulse Healthcare",     customerInitial: "P", customerBg: ["from-teal-500",   "to-teal-700"],     type: "Chargeback",      amount:  890, status: "awaiting",      ago: "3h",  drafts: 2, risk: "med",  owner: "you",    watching: false },
];

const ACTIVE_CASE_NUM = "4821";

/* ─── Full case details (each one tells a different story) ─────────────── */

interface CaseDetail {
  headlineVerb: React.ReactNode; // italic part after customer name
  routedNote: string;
  policyFile: string;
  tldr: React.ReactNode;
  account: [string, React.ReactNode][];
  evidence: { n: number; src: string; record: string; finding: string }[];
  actions: { title: string; target: string; body: string }[];
  policyReasoning: React.ReactNode;
  footnotes: [number, string, string][];
}

const CASE_DETAILS: Record<string, CaseDetail> = {
  /* ─── 4821 TechCorp - first-dispute chargeback, healthy account ───── */
  "4821": {
    headlineVerb: <>vs. a <span className="nums">$1,200</span> chargeback</>,
    routedNote: "Routed to your queue",
    policyFile: "refunds.yaml@main",
    tldr: (
      <>
        TechCorp filed a <Money>$1,200</Money> chargeback on Stripe charge{" "}
        <Code>ch_3MqXfL</Code> on 12 May, citing reason 4853 (product not
        received). Account is healthy<Ref n={1} />; this is the customer&apos;s
        first dispute in 14 months<Ref n={2} />; the last support conversation
        was 14 days ago about an unrelated onboarding question<Ref n={3} />.{" "}
        <Italic>Refund, apologise, follow up.</Italic> Held for your nod
        because the amount exceeds the <Money>$500</Money> auto-refund
        threshold<Ref n={4} />.
      </>
    ),
    account: [
      ["Customer",    <Strong>TechCorp Industries Inc.</Strong>],
      ["Plan",        <>Growth Annual · <Money>$24,000</Money>/yr</>],
      ["ARR",         <Strong>$240,000</Strong>],
      ["Account age", <>14 months · <Muted>since 4 Mar 2025</Muted></>],
      ["NPS",         <>9 <Muted>(last survey Mar 2026)</Muted></>],
      ["CSM",         <>Lina Martinez</>],
      ["Renewal",     <>4 Sep 2026 · <Amber>113 days</Amber></>],
    ],
    evidence: [
      { n: 1, src: "salesforce", record: "Account · TechCorp Industries", finding: "Health = good · NPS 9 · plan: Growth Annual" },
      { n: 2, src: "stripe",     record: "cus_8mFqZ · dispute history",   finding: "0 prior disputes in last 14 months · 47 successful charges" },
      { n: 3, src: "zendesk",    record: "Ticket #8412 (closed 14d ago)", finding: "Onboarding query · resolved · customer satisfied" },
      { n: 4, src: "notion",     record: "refunds.yaml · main branch",     finding: "refund.threshold = $500 · refund.auto_approve = false" },
    ],
    actions: [
      {
        title:  "Refund $1,200 via Stripe",
        target: "POST /v1/refunds · ch_3MqXfL",
        body:   'reason: "requested_by_customer" · metadata: { case: "4821", approver: "{{user}}" }',
      },
      {
        title:  "Apology + retention email",
        target: "Gmail · billing@techcorp.io · cc: lina@acme.com",
        body:   '"Hi TechCorp team, I\'m writing about the $1,200 charge from 12 May. We\'ve refunded it in full and added a $200 credit toward your renewal. Lina from our team will follow up later this week to make sure everything\'s in order."',
      },
      {
        title:  "CSM follow-up ticket",
        target: "Linear · BIL-128 · assignee: Lina Martinez · due in 7d",
        body:   "Confirm refund landed; offer 15-min call to walk through the dispute trigger and prevent recurrence.",
      },
    ],
    policyReasoning: (
      <>
        Amount <Money>$1,200</Money> &gt; <Code>refund.threshold</Code> →
        escalate per <Code>refund.auto_approve_under = false</Code>. Customer
        health <Code>good</Code> → add retention follow-up per{" "}
        <Code>refund.health_good_action = csm_followup</Code>.
      </>
    ),
    footnotes: [
      [1, "Salesforce · TechCorp Industries", "Health = good · NPS 9 · last sync 4m ago"],
      [2, "Stripe · cus_8mFqZ",                "0 prior disputes in last 14mo (47 successful charges)"],
      [3, "Zendesk · #8412",                   "Onboarding query · closed 14d ago · CSAT 5/5"],
      [4, "policy.yaml · refunds.yaml@main",    "refund.threshold = $500 · auto_approve = false"],
    ],
  },

  /* ─── 4815 StartupY - SLA refund (downtime) ───────────────────────── */
  "4815": {
    headlineVerb: <>owed an <Italic>SLA credit</Italic></>,
    routedNote: "Drafted · awaiting your nod",
    policyFile: "sla.yaml@main",
    tldr: (
      <>
        StartupY&apos;s production workspace was offline for{" "}
        <Strong>2h 14m</Strong> during EU business hours on 11 May
        <Ref n={1} />. Their contract guarantees{" "}
        <Strong>10% of MRR credit per hour</Strong> of downtime past the first
        hour<Ref n={2} />. They asked, so I&apos;ve drafted the credit, an
        apology to their CTO, and a Slack note to their CSM<Ref n={3} />.{" "}
        <Italic>Standard SLA. Clean approve.</Italic>
      </>
    ),
    account: [
      ["Customer",    <Strong>StartupY OÜ</Strong>],
      ["Plan",        <>Scale Annual · <Money>$84,000</Money>/yr</>],
      ["ARR",         <Strong>$84,000</Strong>],
      ["Account age", <>8 months · <Muted>since 18 Sep 2025</Muted></>],
      ["NPS",         <>8 <Muted>(Apr 2026)</Muted></>],
      ["CSM",         <>Raj Patel</>],
      ["SLA tier",    <Code>contract.sla.tier_2</Code>],
    ],
    evidence: [
      { n: 1, src: "datadog",    record: "Incident INC-2287 · 11 May",          finding: "EU-west region · 2h 14m hard outage · 100% impact" },
      { n: 2, src: "notion",     record: "contract.startupy.pdf · §8.3",         finding: "10% of MRR per downtime hour after first 60 minutes" },
      { n: 3, src: "salesforce", record: "Account · StartupY",                   finding: "Healthy · CSM Raj Patel · last QBR 23 Apr" },
    ],
    actions: [
      {
        title:  "SLA credit $840 via Stripe",
        target: "POST /v1/customer_credit_balance · cus_4ZsQp",
        body:   'amount: 84000 · currency: "usd" · description: "SLA credit · INC-2287 (2h 14m downtime, 11 May)"',
      },
      {
        title:  "Apology + RCA to CTO",
        target: "Gmail · marko@startupy.io",
        body:   '"Marko, we owe you an explanation on yesterday\'s 2h 14m outage. The RCA is attached. Per §8.3 of your contract we\'ve credited $840 against your next invoice. I\'ll keep an eye on the post-incident metrics. Happy to jump on a call this week."',
      },
      {
        title:  "CSM Slack ping",
        target: "Slack · @raj.patel · #cs-startupy",
        body:   "StartupY took the brunt of INC-2287. Credit drafted, RCA going to Marko. Anything else you want me to add?",
      },
    ],
    policyReasoning: (
      <>
        Downtime <Strong>2h 14m</Strong> &gt;{" "}
        <Code>sla.threshold = 60m</Code> → fire{" "}
        <Code>sla.credit_per_hour = 10%_mrr</Code>. Credit{" "}
        <Money>$700</Money> + <Money>$140</Money> (partial hour) ={" "}
        <Money>$840</Money>.
      </>
    ),
    footnotes: [
      [1, "Datadog · INC-2287",         "EU-west region · 2h 14m · 100% impact · 11 May 09:14–11:28 UTC"],
      [2, "Notion · contract §8.3",     "10% of MRR per hour after first 60m · tier 2 SLA"],
      [3, "Salesforce · StartupY",      "CSM = Raj Patel · last QBR 23 Apr · health = good"],
    ],
  },

  /* ─── 4810 AcmeInc - enterprise invoice dispute, investigating ────── */
  "4810": {
    headlineVerb: <>disputing <Italic>$3,400 of overages</Italic></>,
    routedNote: "Investigating · no actions drafted yet",
    policyFile: "invoice-disputes.yaml@main",
    tldr: (
      <>
        AcmeInc&apos;s AP team is contesting{" "}
        <Strong>$3,400 of API overage</Strong> on their March invoice
        <Ref n={1} />. I&apos;m pulling the source-of-truth event count from
        PostHog and reconciling against the Stripe metered usage we billed
        from<Ref n={2} />. Current read:{" "}
        <Italic>usage records match within 2%</Italic>. The overage is real,
        but their AP needs a packet they can sign off on
        <Ref n={3} />. Drafting evidence package next; no action fires until
        reconciliation is clean.
      </>
    ),
    account: [
      ["Customer",    <Strong>AcmeInc</Strong>],
      ["Plan",        <>Enterprise · <Money>$312,000</Money>/yr base + metered</>],
      ["ARR",         <Strong>$312,000</Strong>],
      ["Account age", <>22 months · <Muted>since 7 Jul 2024</Muted></>],
      ["NPS",         <>7 <Muted>(Feb 2026)</Muted></>],
      ["CSM",         <>Lina Martinez</>],
      ["AP contact",  <>fatima.r@acme-inc.com</>],
    ],
    evidence: [
      { n: 1, src: "stripe",     record: "Invoice in_1NkXfL · March 2026",     finding: "Base $26,000 + metered overage $3,400 (line: api_calls_above_quota)" },
      { n: 2, src: "posthog",    record: "Events ·  acme_prod · March",        finding: "47.2M API calls (Stripe billed 47.6M) · delta 0.8% within rounding" },
      { n: 3, src: "salesforce", record: "Account · AcmeInc · NPS 7",           finding: "Enterprise · last QBR 18 Mar · CSM Lina Martinez" },
    ],
    actions: [
      {
        title:  "Compile reconciliation packet",
        target: "Notion · /acmeinc/march-overage-recon",
        body:   "Side-by-side: PostHog event count vs Stripe metered events. Per-day breakdown. Quota table. Contract metering schedule (§4.2). Recommendation: confirm the charge, offer to sit on a 30-min call.",
      },
      {
        title:  "Hold the dunning",
        target: "Stripe · in_1NkXfL · pause auto-collect for 14 days",
        body:   "Don't escalate this to a hard collection until Fatima has the packet. Their AP is reasonable; rushing this will burn goodwill.",
      },
    ],
    policyReasoning: (
      <>
        Customer ARR <Strong>$312K</Strong> &gt;{" "}
        <Code>dispute.high_value_threshold = $100K</Code> → require evidence
        packet before any countering. <Code>auto_action = false</Code>.
      </>
    ),
    footnotes: [
      [1, "Stripe · in_1NkXfL",          "March invoice · base + $3,400 metered overage"],
      [2, "PostHog · acme_prod",         "47.2M events (vs 47.6M billed) · 0.8% delta within rounding"],
      [3, "Salesforce · AcmeInc",        "Enterprise · NPS 7 · CSM Lina Martinez"],
    ],
  },

  /* ─── 4805 Loop & Co - auto-executed (no human needed) ────────────── */
  "4805": {
    headlineVerb: <><Italic>auto-refunded.</Italic></>,
    routedNote: "Resolved by Manthan · no approval needed",
    policyFile: "refunds.yaml@main",
    tldr: (
      <>
        Loop &amp; Co accidentally signed up for{" "}
        <Strong>Team tier ($199/mo)</Strong> when they intended Starter
        ($29)<Ref n={1} />. They contacted us within 72 hours
        <Ref n={2} />. Amount is{" "}
        <Strong>under your $500 auto-refund threshold</Strong>, account is
        healthy, and the policy gate cleared on the first pass
        <Ref n={3} />.{" "}
        <Italic>I refunded, fixed their plan, and emailed them.</Italic>{" "}
        No human action needed. Flagging it here for your audit log.
      </>
    ),
    account: [
      ["Customer",     <Strong>Loop &amp; Co</Strong>],
      ["Plan",         <>Starter Monthly · <Money>$348</Money>/yr (corrected)</>],
      ["ARR",          <Strong>$348</Strong>],
      ["Account age",  <>9 days · <Muted>since 16 May 2026</Muted></>],
      ["NPS",          <>- <Muted>(no survey yet)</Muted></>],
      ["CSM",          <Muted>none assigned (SMB tier)</Muted>],
      ["Approval",     <Strong style={{ color: "var(--color-accent)" }}>auto · policy:refunds.auto_under_500</Strong>],
    ],
    evidence: [
      { n: 1, src: "stripe",     record: "sub_3PqLm · plan switch",              finding: "Switched from Team ($199) → Starter ($29) · 22 May 14:02 UTC" },
      { n: 2, src: "zendesk",    record: "Ticket #9821 · opened 22 May",         finding: "Customer self-reported error · politely asked for refund" },
      { n: 3, src: "notion",     record: "refunds.yaml · refund.auto_under_500", finding: "TRUE · account healthy · age < 90d but amount < $100" },
    ],
    actions: [
      {
        title:  "✓ Refunded $199 (executed)",
        target: "Stripe · ch_2NrMv · 22 May 14:08 UTC",
        body:   'reason: "duplicate_or_wrong_tier" · approver: "manthan-auto"',
      },
      {
        title:  "✓ Plan corrected to Starter (executed)",
        target: "Stripe · sub_3PqLm · effective 22 May",
        body:   "Downgrade applied immediately. Next invoice: $29 on 16 Jun.",
      },
      {
        title:  "✓ Confirmation email sent",
        target: "Gmail · founders@loopandco.com",
        body:   '"Refund processed, plan switched to Starter. Sorry for the friction. First month\'s on us. Welcome to Manthan."',
      },
    ],
    policyReasoning: (
      <>
        Amount <Money>$199</Money> &lt;{" "}
        <Code>refund.auto_approve_under = $500</Code>{" "}
        AND <Code>customer_intent_clear = true</Code> →{" "}
        <Strong style={{ color: "var(--color-accent)" }}>auto-approve</Strong>.
        Human approval not required.
      </>
    ),
    footnotes: [
      [1, "Stripe · sub_3PqLm",     "Plan switch from Team to Starter on 22 May"],
      [2, "Zendesk · #9821",        "Self-reported wrong-tier signup · 22 May 13:51 UTC"],
      [3, "Notion · refunds.yaml",  "auto_approve_under = $500 cleared on first pass"],
    ],
  },

  /* ─── 4798 ZenSaaS Studios - failed annual renewal (dunning) ──────── */
  "4798": {
    headlineVerb: <>missed their <Italic>annual renewal</Italic></>,
    routedNote: "Drafted · awaiting your nod",
    policyFile: "dunning.yaml@main",
    tldr: (
      <>
        ZenSaaS&apos; <Money>$1,890</Money> annual renewal failed on 12 May
        ; card on file expired 8 May<Ref n={1} />. They&apos;re a healthy
        14-month customer with zero disputes<Ref n={2} />. I&apos;ve drafted
        three things: a card-update request to billing@, a Slack DM to their
        CSM about the renewal-at-risk, and a 3-day grace period before any
        service degradation<Ref n={3} />.{" "}
        <Italic>Recover quietly, then close the loop.</Italic>
      </>
    ),
    account: [
      ["Customer",     <Strong>ZenSaaS Studios LLC</Strong>],
      ["Plan",         <>Pro Annual · <Money>$22,680</Money>/yr</>],
      ["ARR",          <Strong>$22,680</Strong>],
      ["Account age",  <>14 months · <Muted>since 15 Mar 2025</Muted></>],
      ["NPS",          <>9 <Muted>(Jan 2026)</Muted></>],
      ["CSM",          <>Raj Patel</>],
      ["Last invoice", <>$1,890 · <Amber>failed 12 May</Amber></>],
    ],
    evidence: [
      { n: 1, src: "stripe",     record: "Invoice in_2KpXw · 12 May",     finding: "Card declined · exp_used_card · card last4 4242 expired 8 May" },
      { n: 2, src: "salesforce", record: "Account · ZenSaaS Studios",      finding: "Healthy · NPS 9 · CSM Raj Patel · 0 disputes ever" },
      { n: 3, src: "notion",     record: "dunning.yaml · annual_at_risk",  finding: "grace_period = 72h · channels = [email, slack_csm]" },
    ],
    actions: [
      {
        title:  "Card update email + payment link",
        target: "Gmail · billing@zensaas.studio",
        body:   '"Hi ZenSaaS, your annual renewal payment didn\'t go through on 12 May. The card on file (•••• 4242) appears to have expired on 8 May. You can update it in 30 seconds here: https://billing.acme.com/u/zs-3kQ. Service continues normally for 72 hours."',
      },
      {
        title:  "Slack DM to CSM",
        target: "Slack · @raj.patel · DM",
        body:   "Heads up: ZenSaaS' $1,890 renewal failed (card expired). I've sent them the update flow + 72h grace. Let me know if you want me to escalate or if you'd rather reach out yourself first.",
      },
      {
        title:  "Grace period schedule",
        target: "Stripe · sub_4MzNw · pause degradation 72h",
        body:   "Don't touch service tier until 15 May 12:00 UTC. If still unpaid by then, re-evaluate per dunning policy.",
      },
    ],
    policyReasoning: (
      <>
        Annual renewal failed AND account health{" "}
        <Code>good</Code> AND ARR &gt;{" "}
        <Code>dunning.csm_threshold = $20K</Code> → enter retention path:
        notify customer + CSM, hold service degradation for{" "}
        <Code>grace_period = 72h</Code>.
      </>
    ),
    footnotes: [
      [1, "Stripe · in_2KpXw",       "Card declined · exp_used_card · 4242 expired 8 May"],
      [2, "Salesforce · ZenSaaS",    "Healthy · NPS 9 · 0 disputes ever"],
      [3, "Notion · dunning.yaml",   "annual_at_risk → email + slack_csm + 72h grace"],
    ],
  },

  /* ─── 4793 PlanetGrid - trial-end refund, fraud-risk gate ─────────── */
  "4793": {
    headlineVerb: <>flagged as <Italic>trial-end risk</Italic></>,
    routedNote: "High-risk · held for manual review",
    policyFile: "refunds.yaml@main · anti-abuse",
    tldr: (
      <>
        PlanetGrid asked for a <Money>$67</Money> refund four days after
        their trial converted, claiming they{" "}
        <Italic>&quot;didn&apos;t realise the trial ended.&quot;</Italic>{" "}
        Account is <Strong>4 days old</Strong><Ref n={1} /> and matches the
        trial-abuse pattern we flagged in February<Ref n={2} />. The amount
        is small, but the gate is{" "}
        <Code>customer_age_days &gt; 90</Code>: they fail it
        <Ref n={3} />.{" "}
        <Italic>Recommend deny with 50% credit + retention call.</Italic>{" "}
        Held for your call.
      </>
    ),
    account: [
      ["Customer",      <Strong>PlanetGrid (solo)</Strong>],
      ["Plan",          <>Starter Monthly · <Money>$804</Money>/yr</>],
      ["ARR",           <Strong>$804</Strong>],
      ["Account age",   <Amber>4 days</Amber>],
      ["Email domain",  <>@gmail.com · <Amber>non-business</Amber></>],
      ["Sign-up IP",    <Code>91.* · proxied</Code>],
      ["Risk score",    <Strong style={{ color: "var(--color-amber)" }}>7.4 / 10 · trial-abuse pattern</Strong>],
    ],
    evidence: [
      { n: 1, src: "stripe",     record: "cus_5RnFp · subscription_created",    finding: "Account created 21 May · trial converted 26 May" },
      { n: 2, src: "notion",     record: "fraud-signals/trial-abuse.md",         finding: "Pattern: signup → trial use → refund < 7d after charge. 12 flagged accounts in 2026 Q1." },
      { n: 3, src: "notion",     record: "refunds.yaml · anti_abuse rule",      finding: "customer_age_days > 90 OR risk_score < 5 required for auto-approve" },
    ],
    actions: [
      {
        title:  "Decline with 50% goodwill credit",
        target: "Gmail + Stripe · ch_4PrXn · partial_refund",
        body:   '"Thanks for reaching out. To keep things fair we don\'t refund usage past the trial conversion, but I\'ve credited 50% ($33.50) toward your next month. Happy to jump on a call if you\'d like to talk through what would work better for you."',
      },
      {
        title:  "Retention call invite",
        target: "Calendar · 15-min slots / next 5 days",
        body:   "Optional. If they accept, log to Salesforce as a save-attempt and assign to whoever picks it up.",
      },
    ],
    policyReasoning: (
      <>
        Account age <Strong>4 days</Strong> &lt;{" "}
        <Code>refunds.auto_approve.customer_age_days = 90</Code>{" "}
        AND <Code>risk_score = 7.4</Code> &gt;{" "}
        <Code>anti_abuse.score_threshold = 5</Code> →{" "}
        <Strong style={{ color: "var(--color-amber)" }}>manual review</Strong>{" "}
        required. Auto-deny path would also be defensible.
      </>
    ),
    footnotes: [
      [1, "Stripe · cus_5RnFp",          "Account 4d old · trial converted 26 May"],
      [2, "Notion · trial-abuse.md",     "Pattern match: 12 prior flagged in 2026 Q1"],
      [3, "Notion · refunds.yaml",       "Anti-abuse gate: age>90d OR risk<5 required"],
    ],
  },

  /* ─── 4781 Midcorp Systems - high-value renewal failure ───────────── */
  "4781": {
    headlineVerb: <><Italic>$4,200 renewal</Italic> at risk</>,
    routedNote: "Investigating · multi-channel recovery in flight",
    policyFile: "dunning.yaml · high_value",
    tldr: (
      <>
        Midcorp Systems&apos; <Money>$4,200</Money> annual renewal failed
        this morning: primary card expired<Ref n={1} />. They&apos;re a
        top-5% account (<Strong>$420K</Strong>{" "}
        ARR, 31 months in)<Ref n={2} />. Their AP director is reachable on
        Slack; I messaged her at 09:14, awaiting reply<Ref n={3} />. In
        parallel I&apos;m firing a Stripe card-update SMS to her direct line,
        and the CSM is on standby for a call if the silent recovery
        doesn&apos;t work<Ref n={4} />.{" "}
        <Italic>Don&apos;t let this one drop.</Italic>
      </>
    ),
    account: [
      ["Customer",     <Strong>Midcorp Systems plc.</Strong>],
      ["Plan",         <>Enterprise Annual · <Money>$420,000</Money>/yr</>],
      ["ARR",          <Strong>$420,000</Strong>],
      ["Account age",  <>31 months · <Muted>since 12 Oct 2023</Muted></>],
      ["NPS",          <>9 <Muted>(Apr 2026)</Muted></>],
      ["CSM",          <>Lina Martinez</>],
      ["AP contact",   <>priya.s@midcorp.systems · <Code>slack: @priya.s</Code></>],
    ],
    evidence: [
      { n: 1, src: "stripe",     record: "Invoice in_3RsXv · 25 May",          finding: "Card declined · exp_used_card · card last4 1109 expired 19 May" },
      { n: 2, src: "salesforce", record: "Account · Midcorp Systems",          finding: "Top 5% by ARR · NPS 9 · last QBR 4 Apr · health = excellent" },
      { n: 3, src: "slack",      record: "DM @priya.s · sent 09:14 UTC",       finding: "Read receipts on · no reply yet (35m elapsed)" },
      { n: 4, src: "notion",     record: "dunning.yaml · high_value",          finding: "ARR > $200K → all channels · CSM standby · no service degradation" },
    ],
    actions: [
      {
        title:  "Stripe card-update SMS to AP",
        target: "Stripe · sub_5XvYr · SMS to AP direct line",
        body:   "Magic-link card update. Lives for 24h. Doesn't bypass approval; Priya just clicks and updates.",
      },
      {
        title:  "CSM call · standby",
        target: "Calendar · Lina · available from 14:00 UTC",
        body:   "If Priya hasn't replied to Slack by 13:00, Lina dials her. Don't let this stretch past today.",
      },
    ],
    policyReasoning: (
      <>
        ARR <Strong>$420K</Strong> &gt;{" "}
        <Code>dunning.high_value_threshold = $200K</Code> AND renewal failed
        → fire <Code>dunning.high_value.all_channels = true</Code>.{" "}
        <Code>service_degradation = false</Code> for 7 days.
      </>
    ),
    footnotes: [
      [1, "Stripe · in_3RsXv",     "Card declined · 1109 expired 19 May · 25 May 08:01 UTC"],
      [2, "Salesforce · Midcorp",  "Top 5% by ARR · NPS 9 · health = excellent"],
      [3, "Slack · @priya.s",      "DM sent 09:14 · seen · awaiting reply"],
      [4, "Notion · dunning.yaml", "high_value path: all channels, CSM standby"],
    ],
  },

  /* ─── 4774 Pulse Healthcare - fraud signal chargeback ────────────── */
  "4774": {
    headlineVerb: <>flagged for <Italic>possible card fraud</Italic></>,
    routedNote: "Awaiting your read · do not auto-accept",
    policyFile: "chargebacks.yaml · fraud_signal",
    tldr: (
      <>
        Pulse Healthcare&apos;s bank filed an <Money>$890</Money> chargeback
        citing &quot;unrecognised charge&quot;<Ref n={1} />. The customer
        themselves is healthy: 11 months in, zero support tickets, NPS 8
        <Ref n={2} />. That pattern reads more like a{" "}
        <Italic>compromised card</Italic> than a dissatisfied customer
        <Ref n={3} />.{" "}
        <Italic>Recommend: don&apos;t accept the chargeback yet. Slack the
        customer first to confirm, escalate to fraud team if they didn&apos;t
        recognise it.</Italic>
      </>
    ),
    account: [
      ["Customer",       <Strong>Pulse Healthcare Group</Strong>],
      ["Plan",           <>Pro Monthly · <Money>$10,800</Money>/yr</>],
      ["ARR",            <Strong>$10,800</Strong>],
      ["Account age",    <>11 months · <Muted>since 8 Jun 2025</Muted></>],
      ["NPS",            <>8 <Muted>(Mar 2026)</Muted></>],
      ["Support tickets",<>0 in last 11 months</>],
      ["Risk signal",    <Strong style={{ color: "var(--color-amber)" }}>compromised_card · 6.2 / 10</Strong>],
    ],
    evidence: [
      { n: 1, src: "stripe",     record: "Dispute dp_8KqXz · 21 May",        finding: "Reason: 4863 (unrecognised) · evidence due in 7d" },
      { n: 2, src: "salesforce", record: "Account · Pulse Healthcare",        finding: "Healthy · NPS 8 · CSM Raj Patel · no escalations ever" },
      { n: 3, src: "zendesk",    record: "Tickets · cus_pulse",                finding: "0 tickets in 11 months · no contact about billing ever" },
    ],
    actions: [
      {
        title:  "Slack customer admin: confirm or deny",
        target: "Slack · @james.k (Pulse admin) · DM",
        body:   '"Hi James, your bank filed a chargeback on a $890 charge from 19 May. Before we respond either way I wanted to check with you directly: was this charge unfamiliar to you / your team?"',
      },
      {
        title:  "Hold the dispute response",
        target: "Stripe · dp_8KqXz · hold 72h",
        body:   "Don't submit evidence yet. If James confirms the charge is legitimate, accept-and-counter. If he didn't recognise it, that's a fraud case. Escalate.",
      },
    ],
    policyReasoning: (
      <>
        Customer health <Code>good</Code> + 0 support tickets + chargeback
        reason <Code>4863</Code> →{" "}
        <Code>chargebacks.fraud_signal.likely = true</Code>. Per policy:{" "}
        <Strong style={{ color: "var(--color-amber)" }}>confirm with customer first</Strong>,
        do not auto-respond.
      </>
    ),
    footnotes: [
      [1, "Stripe · dp_8KqXz",     "Reason 4863 (unrecognised) · evidence due in 7d"],
      [2, "Salesforce · Pulse",     "Healthy · NPS 8 · zero escalations ever"],
      [3, "Zendesk · cus_pulse",    "0 tickets in 11 months"],
    ],
  },
};

/* ─── Small typographic helpers for case content ──────────────────────── */

// Money values - Geist with tabular-nums + medium weight + strong color.
// We do NOT use mono here - terminal vibes ruin the editorial feel.
function Money({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        color: "var(--color-ink-strong)",
        fontVariantNumeric: "tabular-nums",
        fontWeight: 600,
      }}
    >
      {children}
    </span>
  );
}
// Code - used ONLY for actual identifiers / file paths / config keys
// (e.g. ch_3MqXfL, refunds.yaml, refund.threshold). Stays mono.
function Code({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="font-mono"
      style={{ color: "var(--color-ink-strong)", fontSize: "0.94em" }}
    >
      {children}
    </span>
  );
}
function Strong({ children, className, style }: { children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <span
      className={className}
      style={{
        color: "var(--color-ink-strong)",
        fontWeight: 600,
        fontVariantNumeric: "tabular-nums",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
function Muted({ children }: { children: React.ReactNode }) {
  return <span style={{ color: "var(--color-ink-faint)" }}>{children}</span>;
}
function Italic({ children }: { children: React.ReactNode }) {
  return (
    <em className="display-italic" style={{ color: "var(--color-ink-strong)" }}>
      {children}
    </em>
  );
}
function Amber({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        color: "var(--color-amber)",
        fontVariantNumeric: "tabular-nums",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   ROOT
   ═══════════════════════════════════════════════════════════════════════ */

type SceneId = "case" | "ledger" | "policy";

const SCENES: { id: SceneId; n: string; label: string; sub: string }[] = [
  { id: "case",   n: "01", label: "Case workspace",   sub: "Investigate a single escalation." },
  { id: "ledger", n: "02", label: "Approval ledger",  sub: "Clear the queue." },
  { id: "policy", n: "03", label: "Policy Guardrail", sub: "Govern what Manthan can do without you." },
];

export function HeroShowcase({ blendBody = false }: { blendBody?: boolean }) {
  const [scene, setScene] = useState<SceneId>("case");

  return (
    <div className="w-full font-sans">
      {/* Window - fixed height, NO scroll.
          When `blendBody` is on (hero context), the scene body uses a
          semi-transparent dark surface + heavy backdrop-filter so the video
          behind shows through as a softly-blurred frosted glass texture.
          The chrome stays fully opaque so controls read crisply. */}
      <div
        className="rounded-md overflow-hidden border relative"
        style={{
          background: "transparent",
          borderColor: blendBody ? "rgba(255,255,255,0.10)" : "var(--color-rule)",
          boxShadow: blendBody
            ? "0 30px 80px -30px rgb(0 0 0 / 0.65), inset 0 1px 0 rgba(255,255,255,0.05)"
            : "0 30px 80px -30px rgb(0 0 0 / 0.55)",
          height: 620,
        }}
      >
        {/* Chrome - always opaque, never blended. */}
        <div style={{ background: "var(--color-surface)" }}>
          <WindowChrome scene={scene} />
        </div>

        {/* Scene body - frosted-glass when blendBody is on, opaque otherwise.
            Low-alpha bg + moderate blur so the video texture clearly reads
            through the panel without washing out the dashboard contents. */}
        <div
          className="relative"
          style={{
            height: "calc(100% - 36px)",
            background: blendBody ? "rgba(8, 8, 10, 0.36)" : "var(--color-surface)",
            backdropFilter: blendBody
              ? "blur(14px) saturate(1.5) brightness(0.85)"
              : "none",
            WebkitBackdropFilter: blendBody
              ? "blur(14px) saturate(1.5) brightness(0.85)"
              : "none",
          }}
        >
          <AnimatePresence initial={false}>
            <motion.div
              key={scene}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16, ease: [0.25, 1, 0.5, 1] }}
              className="absolute inset-0 overflow-hidden"
            >
              {scene === "case"   && <CaseWorkspace />}
              {scene === "ledger" && <ApprovalLedger />}
              {scene === "policy" && <PolicyDocument />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* Scene tabs - placed BELOW the window */}
      <SceneTabs scene={scene} setScene={setScene} />
    </div>
  );
}

/* ─── Top scene nav (table-of-contents style) ─────────────────────────── */

function SceneTabs({
  scene,
  setScene,
}: {
  scene: SceneId;
  setScene: (s: SceneId) => void;
}) {
  return (
    <div className="mt-6 flex justify-center gap-2 flex-wrap">
      {SCENES.map((s) => {
        const active = s.id === scene;
        return (
          <button
            key={s.id}
            onClick={() => setScene(s.id)}
            className="rounded-full px-4 py-2 inline-flex items-baseline gap-2 transition-colors"
            style={
              active
                ? {
                    background: "oklch(0.98 0.003 75)",
                    color: "oklch(0.135 0.006 75)",
                    border: "1px solid transparent",
                    boxShadow: "0 6px 20px rgba(0,0,0,0.35)",
                  }
                : {
                    background: "rgba(8, 8, 8, 0.62)",
                    color: "oklch(0.86 0.005 75)",
                    border: "1px solid rgba(255, 255, 255, 0.18)",
                    backdropFilter: "blur(20px) saturate(1.4)",
                    WebkitBackdropFilter: "blur(20px) saturate(1.4)",
                    boxShadow:
                      "inset 0 1px 0 rgba(255,255,255,0.06), 0 4px 14px rgba(0,0,0,0.3)",
                  }
            }
          >
            <span
              className="text-[11px] tabular-nums"
              style={{
                fontWeight: 600,
                letterSpacing: "0.04em",
                color: active ? "oklch(0.45 0.005 75)" : "oklch(0.58 0.005 75)",
              }}
            >
              {s.n}
            </span>
            <span className="text-[14px] font-medium">{s.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ─── Window chrome ───────────────────────────────────────────────────── */

function WindowChrome({ scene }: { scene: SceneId }) {
  const title =
    scene === "case"
      ? `acme.manthan.dev / inbox / case 4821`
      : scene === "ledger"
        ? `acme.manthan.dev / inbox`
        : `acme.manthan.dev / policy / refunds.yaml`;

  return (
    <div
      className="flex items-center justify-between px-4 h-9 border-b"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: "oklch(0.65 0.18 25)" }} />
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: "oklch(0.78 0.13 75)" }} />
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--color-accent)" }} />
      </div>
      <div
        className="font-mono text-[11px] tracking-wide"
        style={{ color: "var(--color-ink-faint)" }}
      >
        {title}
      </div>
      <div
        className="font-mono text-[10px] inline-flex items-center gap-1.5"
        style={{ color: "var(--color-ink-faint)" }}
      >
        <span className="h-1 w-1 rounded-full animate-pulse-dot" style={{ background: "var(--color-accent)" }} />
        live
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   SCENE 1 - CASE WORKSPACE (long-form memo + sidebar)
   ═══════════════════════════════════════════════════════════════════════ */

type CaseStatus = "awaiting" | "approving" | "approved" | "held";

function CaseWorkspace() {
  const [activeCaseNum, setActiveCaseNum] = useState(ACTIVE_CASE_NUM);
  const [status, setStatus] = useState<CaseStatus>("awaiting");
  const [approvedSteps, setApprovedSteps] = useState(0);
  const [editingAction, setEditingAction] = useState<number | null>(null);

  useEffect(() => {
    if (status !== "approving") return;
    if (approvedSteps < 3) {
      const t = setTimeout(() => setApprovedSteps((s) => s + 1), 480);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStatus("approved"), 600);
    return () => clearTimeout(t);
  }, [status, approvedSteps]);

  const reset = () => {
    setStatus("awaiting");
    setApprovedSteps(0);
    setEditingAction(null);
  };

  // Whenever the user changes the active case in the sidebar, reset the
  // approval state (would be different per case in production).
  useEffect(() => reset(), [activeCaseNum]);

  return (
    <div
      className="h-full flex flex-col"
      style={{ background: "var(--color-bg)" }}
    >
      <div
        className="flex-1 min-h-0"
        style={{
          display: "grid",
          gridTemplateColumns: "220px minmax(0, 1fr) 260px",
        }}
      >
        <CaseSidebar
          activeCaseNum={activeCaseNum}
          setActiveCaseNum={setActiveCaseNum}
        />

        <main className="flex flex-col min-w-0 min-h-0" style={{ background: "var(--color-bg)" }}>
          <CaseHeader status={status} caseNum={activeCaseNum} />
          <div className="flex-1 min-h-0 px-7 py-5 space-y-4 overflow-hidden flex flex-col">
            <CaseTLDR caseNum={activeCaseNum} />
            <Rule />
            <div className="flex-1 min-h-0 overflow-hidden">
              <CaseActions
                caseNum={activeCaseNum}
                status={status}
                approvedSteps={approvedSteps}
                editingAction={editingAction}
                setEditingAction={setEditingAction}
              />
            </div>
          </div>
        </main>

        <CaseRightRail caseNum={activeCaseNum} />
      </div>

      <CaseActionBar
        caseNum={activeCaseNum}
        status={status}
        setStatus={setStatus}
        reset={reset}
      />
    </div>
  );
}

/* Right rail - Account + Evidence + Policy reasoning, compact */
function CaseRightRail({ caseNum }: { caseNum: string }) {
  const d = CASE_DETAILS[caseNum] ?? CASE_DETAILS[ACTIVE_CASE_NUM];

  // Take the 5 most important account rows for compactness
  const accountTop = d.account.slice(0, 5);

  return (
    <aside
      className="border-l flex flex-col min-h-0 overflow-hidden"
      style={{
        borderColor: "var(--color-rule-soft)",
        background: "var(--color-bg)",
      }}
    >
      <div className="px-5 pt-5 pb-4 space-y-4 flex-1 min-h-0 overflow-auto">
        {/* Account snapshot */}
        <div>
          <Eyebrow>Account</Eyebrow>
          <dl className="mt-2 space-y-1 text-[12px]">
            {accountTop.map(([k, v], i) => (
              <div key={`${k}-${i}`} className="flex items-baseline justify-between gap-3">
                <dt style={{ color: "var(--color-ink-faint)" }} className="shrink-0">{k}</dt>
                <dd
                  className="text-right truncate"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <Rule />

        {/* Evidence - compact list */}
        <div>
          <div className="flex items-baseline justify-between">
            <Eyebrow>Evidence</Eyebrow>
            <span className="text-[10px]" style={{ color: "var(--color-ink-ghost)" }}>
              {d.evidence.length} cited
            </span>
          </div>
          <ul className="mt-2 space-y-2">
            {d.evidence.map((r) => (
              <li
                key={r.n}
                className="flex items-start gap-2 text-[11.5px] leading-snug"
              >
                <span
                  style={{ color: "var(--color-accent)", fontWeight: 600 }}
                  className="tabular-nums shrink-0"
                >
                  [{r.n}]
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <SourceIcon id={r.src} size={10} tinted />
                    <span style={{ color: "var(--color-ink)" }}>
                      {r.src[0].toUpperCase() + r.src.slice(1)}
                    </span>
                    <span style={{ color: "var(--color-ink-faint)" }}>·</span>
                    <Code>{r.record.split(" · ")[0]}</Code>
                  </div>
                  <div
                    className="mt-0.5 text-[11px] truncate"
                    style={{ color: "var(--color-ink-faint)" }}
                    title={r.finding}
                  >
                    {r.finding}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <Rule />

        {/* Policy reasoning - compact block */}
        <div>
          <Eyebrow>Policy</Eyebrow>
          <p
            className="mt-2 text-[11.5px] leading-relaxed"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {d.policyReasoning}
          </p>
        </div>
      </div>
    </aside>
  );
}

/* sidebar - compact text list, no avatars, no cards */
function CaseSidebar({
  activeCaseNum,
  setActiveCaseNum,
}: {
  activeCaseNum: string;
  setActiveCaseNum: (n: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<CaseFilter>("all");

  const filtered = useMemo(() => {
    let rows = CASES;
    if (filter === "mine") rows = rows.filter((c) => c.owner === "you");
    if (filter === "watching") rows = rows.filter((c) => c.watching);
    if (query) {
      const q = query.toLowerCase();
      rows = rows.filter(
        (c) => c.customer.toLowerCase().includes(q) || c.num.includes(q),
      );
    }
    return rows;
  }, [filter, query]);

  return (
    <aside
      className="border-r flex flex-col min-w-0 min-h-0 overflow-hidden"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <div className="px-3 pt-3.5 pb-2 space-y-2">
        <div
          className="flex items-center gap-2 px-2 py-1.5 border"
          style={{
            borderColor: "var(--color-rule-soft)",
            background: "var(--color-surface)",
          }}
        >
          <Search className="h-3 w-3" style={{ color: "var(--color-ink-faint)" }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find case…"
            className="bg-transparent text-[11.5px] flex-1 outline-none min-w-0"
            style={{ color: "var(--color-ink)" }}
          />
          <span className="font-mono text-[10px]" style={{ color: "var(--color-ink-ghost)" }}>⌘K</span>
        </div>
        <div className="flex items-center gap-1.5">
          {([
            ["all",      "All"],
            ["mine",     "Mine"],
            ["watching", "Watching"],
          ] as const).map(([id, label]) => {
            const active = filter === id;
            const count =
              id === "all"
                ? CASES.length
                : id === "mine"
                  ? CASES.filter((c) => c.owner === "you").length
                  : CASES.filter((c) => c.watching).length;
            return (
              <button
                key={id}
                onClick={() => setFilter(id)}
                className="text-[10.5px] px-1.5 py-0.5 inline-flex items-center gap-1"
                style={{
                  color: active ? "var(--color-ink)" : "var(--color-ink-faint)",
                  borderBottom: active ? "1px solid var(--color-accent)" : "1px solid transparent",
                }}
              >
                {label}
                <span className="font-mono nums text-[9.5px]" style={{ color: active ? "var(--color-accent)" : "var(--color-ink-ghost)" }}>
                  {count}
                </span>
              </button>
            );
          })}
          <span className="ml-auto font-mono text-[10px]" style={{ color: "var(--color-ink-faint)" }}>
            {filtered.length}
          </span>
        </div>
      </div>

      <div className="rule-soft mx-3" style={{ height: 1, background: "var(--color-rule-soft)" }} />

      <div className="flex-1 overflow-auto py-1">
        {filtered.map((c) => {
          const active = c.num === activeCaseNum;
          return (
            <button
              key={c.num}
              onClick={() => setActiveCaseNum(c.num)}
              className="w-full text-left px-3 py-2 block transition-colors"
              style={{
                background: active ? "var(--color-surface)" : "transparent",
                borderLeft: active ? "2px solid var(--color-accent)" : "2px solid transparent",
              }}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span
                  className="font-mono text-[10.5px] tabular-nums"
                  style={{ color: active ? "var(--color-accent)" : "var(--color-ink-faint)" }}
                >
                  {c.num}
                </span>
                <span
                  className="font-mono text-[10px]"
                  style={{ color: "var(--color-ink-ghost)" }}
                >
                  {c.ago}
                </span>
              </div>
              <div
                className="text-[12px] font-medium truncate mt-0.5"
                style={{ color: active ? "var(--color-ink-strong)" : "var(--color-ink-muted)" }}
              >
                {c.customer}
              </div>
              <div className="flex items-center justify-between gap-2 mt-0.5">
                <span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                  {c.type}
                </span>
                <span className="font-mono text-[10.5px] tabular-nums" style={{ color: "var(--color-ink-muted)" }}>
                  ${c.amount.toLocaleString()}
                </span>
              </div>
              <div className="mt-1">
                <StatusDot tone={c.status} subtle />
              </div>
            </button>
          );
        })}
      </div>

      <div
        className="px-3 py-2 border-t font-mono text-[10px] flex items-center justify-between"
        style={{ borderColor: "var(--color-rule-soft)", color: "var(--color-ink-faint)" }}
      >
        <span>{CASES.length} cases</span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1 w-1 rounded-full animate-pulse-dot" style={{ background: "var(--color-accent)" }} />
          syncing
        </span>
      </div>
    </aside>
  );
}

/* case header - compact, single row */
function CaseHeader({ status, caseNum }: { status: CaseStatus; caseNum: string }) {
  const c = CASES.find((x) => x.num === caseNum) ?? CASES[0];
  const d = CASE_DETAILS[caseNum] ?? CASE_DETAILS[ACTIVE_CASE_NUM];
  return (
    <header
      className="px-7 pt-4 pb-3 border-b"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div
            className="text-[10.5px] uppercase"
            style={{
              color: "var(--color-ink-faint)",
              letterSpacing: "0.11em",
              fontWeight: 600,
            }}
          >
            Case № <span style={{ color: "var(--color-ink-strong)" }}>{c.num}</span> · {c.type}
          </div>
          <h2
            className="mt-1 text-[22px] tracking-[-0.02em]"
            style={{ color: "var(--color-ink-strong)" }}
          >
            {c.customer}{" "}
            <em className="display-italic" style={{ color: "var(--color-ink-muted)" }}>
              {d.headlineVerb}
            </em>
          </h2>
          <div
            className="mt-1 text-[11.5px] flex items-center gap-2 flex-wrap"
            style={{ color: "var(--color-ink-faint)" }}
          >
            <span>Drafted {c.ago} ago</span>
            <span style={{ color: "var(--color-rule-strong)" }}>·</span>
            <span>{d.routedNote}</span>
            <span style={{ color: "var(--color-rule-strong)" }}>·</span>
            <Code>{d.policyFile}</Code>
          </div>
        </div>
        <StatusBadge status={status} />
      </div>
    </header>
  );
}

/* TL;DR memo - paragraph from CASE_DETAILS */
function CaseTLDR({ caseNum }: { caseNum: string }) {
  const d = CASE_DETAILS[caseNum] ?? CASE_DETAILS[ACTIVE_CASE_NUM];
  return (
    <section className="space-y-2 shrink-0">
      <Eyebrow>TL;DR</Eyebrow>
      <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--color-ink)" }}>
        {d.tldr}
      </p>
    </section>
  );
}

/* Drafted actions - pulled from CASE_DETAILS */
function CaseActions({
  caseNum,
  status,
  approvedSteps,
  editingAction,
  setEditingAction,
}: {
  caseNum: string;
  status: CaseStatus;
  approvedSteps: number;
  editingAction: number | null;
  setEditingAction: (n: number | null) => void;
}) {
  const d = CASE_DETAILS[caseNum] ?? CASE_DETAILS[ACTIVE_CASE_NUM];
  const actions = d.actions;
  const c = CASES.find((x) => x.num === caseNum) ?? CASES[0];
  const allDone = c.status === "executing" || c.status === "resolved";

  return (
    <section className="h-full flex flex-col min-h-0">
      <div className="flex items-baseline justify-between shrink-0">
        <Eyebrow>Drafted actions</Eyebrow>
        <span className="text-[10.5px]" style={{ color: "var(--color-ink-ghost)", letterSpacing: "0.04em" }}>
          {actions.length} action{actions.length === 1 ? "" : "s"} · {allDone ? "executed" : "awaiting approval"}
        </span>
      </div>

      <ol className="mt-3 space-y-2.5 flex-1 min-h-0 overflow-auto pr-1">
        {actions.map((a, i) => {
          const done =
            allDone ||
            status === "approved" ||
            (status === "approving" && i < approvedSteps);
          const isEditing = editingAction === i;
          return (
            <li key={a.title}>
              <div
                className="items-start py-0.5"
                style={{
                  display: "grid",
                  gridTemplateColumns: "24px minmax(0,1fr) 24px",
                  gap: 10,
                }}
              >
                <span
                  className="tabular-nums text-[11px]"
                  style={{
                    color: done ? "var(--color-accent)" : "var(--color-ink-faint)",
                    paddingTop: 2,
                    fontWeight: 500,
                  }}
                >
                  {done ? "✓" : String(i + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className="text-[12.5px]"
                      style={{ color: "var(--color-ink-strong)", fontWeight: 500 }}
                    >
                      {a.title}
                    </span>
                    {done && (
                      <motion.span
                        initial={{ scale: 0.7, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ duration: 0.2 }}
                        className="inline-flex items-center gap-0.5 text-[10px] uppercase tracking-wider"
                        style={{ color: "var(--color-accent)", fontWeight: 600, letterSpacing: "0.08em" }}
                      >
                        fired
                      </motion.span>
                    )}
                  </div>
                  <div className="mt-0.5">
                    <Code>
                      <span style={{ color: "var(--color-ink-faint)", fontSize: "11px" }}>
                        {a.target}
                      </span>
                    </Code>
                  </div>

                  {isEditing ? (
                    <textarea
                      defaultValue={a.body}
                      className="mt-1.5 w-full text-[11.5px] leading-relaxed p-2 outline-none resize-none"
                      style={{
                        background: "var(--color-surface)",
                        color: "var(--color-ink)",
                        border: "1px solid var(--color-accent-line)",
                        minHeight: 60,
                      }}
                      onBlur={() => setEditingAction(null)}
                      autoFocus
                    />
                  ) : (
                    <p
                      className="mt-1 text-[11.5px] leading-snug line-clamp-2"
                      style={{ color: "var(--color-ink-muted)" }}
                    >
                      {a.body}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setEditingAction(isEditing ? null : i)}
                  className="self-start p-1 transition-colors"
                  style={{ color: isEditing ? "var(--color-accent)" : "var(--color-ink-ghost)" }}
                  disabled={status !== "awaiting"}
                  title="Edit draft"
                >
                  {isEditing ? <X className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                </button>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/* Footer action bar - minimal, no glassmorphism */
function CaseActionBar({
  caseNum,
  status,
  setStatus,
  reset,
}: {
  caseNum: string;
  status: CaseStatus;
  setStatus: (s: CaseStatus) => void;
  reset: () => void;
}) {
  const c = CASES.find((x) => x.num === caseNum) ?? CASES[0];
  const d = CASE_DETAILS[caseNum] ?? CASE_DETAILS[ACTIVE_CASE_NUM];

  // Auto-executed cases (Loop & Co) - show resolved-by-Manthan footer
  if (c.status === "executing") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
      >
        <div className="text-[12.5px] flex items-center gap-3">
          <span style={{ color: "var(--color-accent)" }} className="font-medium inline-flex items-center gap-1.5">
            <Check className="h-3.5 w-3.5" strokeWidth={3} />
            Resolved by Manthan
          </span>
          <span style={{ color: "var(--color-ink-faint)" }}>·</span>
          <span style={{ color: "var(--color-ink-muted)" }}>
            <Strong>${c.amount.toLocaleString()}</Strong>{" "}
            refunded · plan corrected · confirmation sent · under your{" "}
            <Code>refund.auto_under_500</Code> rule
          </span>
        </div>
        <span
          className="text-[11px]"
          style={{ color: "var(--color-ink-faint)", letterSpacing: "0.04em" }}
        >
          no approval needed
        </span>
      </footer>
    );
  }

  // Investigating cases (AcmeInc, Midcorp) - no action button, show investigation status
  if (c.status === "investigating") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
      >
        <div className="text-[12.5px] flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full animate-pulse-dot" style={{ background: "var(--color-info)" }} />
          <span style={{ color: "var(--color-ink-muted)" }}>
            Still investigating · {d.actions.length} action{d.actions.length === 1 ? "" : "s"} drafted but not fired · awaiting reconciliation
          </span>
        </div>
        <span className="font-mono text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
          will route when ready
        </span>
      </footer>
    );
  }

  if (status === "approved") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
      >
        <div className="text-[12.5px] flex items-center gap-3">
          <span style={{ color: "var(--color-accent)" }} className="font-medium inline-flex items-center gap-1.5">
            <Check className="h-3.5 w-3.5" strokeWidth={3} />
            Resolved in 2m 14s
          </span>
          <span style={{ color: "var(--color-ink-faint)" }}>·</span>
          <span style={{ color: "var(--color-ink-muted)" }}>
            <span style={{ color: "var(--color-ink-strong)" }}>${c.amount.toLocaleString()}</span>{" "}
            actioned · brief posted to{" "}
            <span className="font-mono">#billing-ops</span>
          </span>
        </div>
        <button
          onClick={reset}
          className="text-[11.5px] inline-flex items-center gap-1.5 transition-colors"
          style={{ color: "var(--color-ink-muted)" }}
        >
          <RotateCcw className="h-3 w-3" />
          Replay
        </button>
      </footer>
    );
  }
  if (status === "held") {
    return (
      <footer
        className="px-7 py-3.5 border-t flex items-center justify-between"
        style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
      >
        <div className="text-[12.5px]" style={{ color: "var(--color-amber)" }}>
          Held by you · awaiting your edit
        </div>
        <button
          onClick={reset}
          className="text-[11.5px]"
          style={{ color: "var(--color-ink-muted)" }}
        >
          Resume
        </button>
      </footer>
    );
  }
  // Awaiting / Drafted - show approve action
  const actionVerb = c.status === "drafted" ? "drafted, awaiting approval" : "ready to fire";
  return (
    <footer
      className="px-7 py-3.5 border-t flex items-center justify-between gap-3"
      style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
    >
      <div className="text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
        <span style={{ color: "var(--color-ink-strong)" }}>{d.actions.length} action{d.actions.length === 1 ? "" : "s"}</span> {actionVerb}
      </div>
      <div className="flex items-center gap-2">
        <button
          disabled={status === "approving"}
          onClick={() => setStatus("approving")}
          className="text-[12.5px] font-semibold px-4 py-1.5 disabled:opacity-70"
          style={{
            background: "var(--color-accent)",
            color: "var(--color-accent-ink)",
          }}
        >
          {status === "approving" ? "Approving…" : "Approve all"}
        </button>
        <button
          onClick={() => setStatus("held")}
          className="text-[12.5px] font-medium px-3 py-1.5 border"
          style={{
            borderColor: "var(--color-rule-strong)",
            color: "var(--color-ink-muted)",
          }}
        >
          Hold
        </button>
      </div>
    </footer>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   SCENE 2 - APPROVAL LEDGER (ledger table, no card grid, no sub-tabs)
   ═══════════════════════════════════════════════════════════════════════ */

type SortKey = "ago" | "amount" | "customer";

function ApprovalLedger() {
  const [statusFilter, setStatusFilter] = useState<"all" | Tone>("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "ago",
    dir: "asc",
  });
  const [selected, setSelected] = useState<Set<string>>(
    new Set(["4821", "4815", "4810"]),
  );
  const [expanded, setExpanded] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "approving" | "done">("idle");
  const [approvedIds, setApprovedIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    let rows = [...CASES];
    if (statusFilter !== "all") rows = rows.filter((r) => r.status === statusFilter);
    if (query) {
      const q = query.toLowerCase();
      rows = rows.filter(
        (r) => r.customer.toLowerCase().includes(q) || r.num.includes(q),
      );
    }
    rows.sort((a, b) => {
      const mul = sort.dir === "asc" ? 1 : -1;
      if (sort.key === "amount") return (a.amount - b.amount) * mul;
      if (sort.key === "customer") return a.customer.localeCompare(b.customer) * mul;
      // ago - newer (smaller) first when asc
      return a.ago.localeCompare(b.ago) * mul;
    });
    return rows;
  }, [statusFilter, sort, query]);

  const selectedRows = filtered.filter((r) => selected.has(r.num));
  const total = selectedRows.reduce((s, r) => s + r.amount, 0);
  const sumActions = selectedRows.reduce((s, r) => s + r.drafts, 0);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));

  const toggle = (n: string) => {
    if (phase !== "idle") return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  };

  const approveAll = () => {
    if (selectedRows.length === 0 || phase !== "idle") return;
    setPhase("approving");
    selectedRows.forEach((r, i) =>
      setTimeout(() => {
        setApprovedIds((prev) => new Set(prev).add(r.num));
      }, 380 * (i + 1)),
    );
    setTimeout(() => setPhase("done"), 380 * selectedRows.length + 500);
  };

  const reset = () => {
    setPhase("idle");
    setApprovedIds(new Set());
    setSelected(new Set(["4821", "4815", "4810"]));
  };

  return (
    <div
      className="h-full"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) 240px",
        background: "var(--color-bg)",
      }}
    >
      <div className="flex flex-col min-h-0 overflow-hidden">
        <LedgerFilterBar
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          query={query}
          setQuery={setQuery}
          count={filtered.length}
        />
        <div className="rule-soft" style={{ height: 1, background: "var(--color-rule-soft)" }} />
        <LedgerTable
          rows={filtered}
          sort={sort}
          toggleSort={toggleSort}
          selected={selected}
          toggle={toggle}
          expanded={expanded}
          setExpanded={setExpanded}
          phase={phase}
          approvedIds={approvedIds}
        />
        <LedgerBulkBar
          selectedCount={selectedRows.length}
          total={total}
          actions={sumActions}
          phase={phase}
          approveAll={approveAll}
          reset={reset}
        />
      </div>
      <LedgerStats selectedCount={selectedRows.length} total={total} />
    </div>
  );
}

function LedgerFilterBar({
  statusFilter,
  setStatusFilter,
  query,
  setQuery,
  count,
}: {
  statusFilter: "all" | Tone;
  setStatusFilter: (t: "all" | Tone) => void;
  query: string;
  setQuery: (q: string) => void;
  count: number;
}) {
  const filters: { id: "all" | Tone; label: string }[] = [
    { id: "all",           label: "All" },
    { id: "awaiting",      label: "Awaiting" },
    { id: "drafted",       label: "Drafted" },
    { id: "investigating", label: "Investigating" },
    { id: "executing",     label: "Executing" },
  ];
  return (
    <div className="px-5 py-3 flex items-center gap-4 flex-wrap">
      <div className="flex items-baseline gap-4">
        {filters.map((f) => {
          const active = statusFilter === f.id;
          return (
            <button
              key={f.id}
              onClick={() => setStatusFilter(f.id)}
              className="text-[12px] font-medium pb-0.5"
              style={{
                color: active ? "var(--color-ink-strong)" : "var(--color-ink-muted)",
                borderBottom: active ? "1px solid var(--color-accent)" : "1px solid transparent",
              }}
            >
              {f.label}
              {f.id === "all" && (
                <span className="ml-1 font-mono text-[10px]" style={{ color: "var(--color-ink-faint)" }}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className="ml-auto flex items-center gap-3">
        <div
          className="flex items-center gap-1.5 px-2 py-1 border"
          style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
        >
          <Search className="h-3 w-3" style={{ color: "var(--color-ink-faint)" }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find customer or case…"
            className="bg-transparent text-[11.5px] outline-none w-[200px]"
            style={{ color: "var(--color-ink)" }}
          />
        </div>
        <button
          className="flex items-center gap-1.5 px-2 py-1 text-[11.5px] border"
          style={{ borderColor: "var(--color-rule-soft)", color: "var(--color-ink-muted)" }}
        >
          <Filter className="h-3 w-3" />
          More filters
        </button>
      </div>
    </div>
  );
}

function LedgerTable({
  rows,
  sort,
  toggleSort,
  selected,
  toggle,
  expanded,
  setExpanded,
  phase,
  approvedIds,
}: {
  rows: CaseRow[];
  sort: { key: SortKey; dir: "asc" | "desc" };
  toggleSort: (key: SortKey) => void;
  selected: Set<string>;
  toggle: (n: string) => void;
  expanded: string | null;
  setExpanded: (n: string | null) => void;
  phase: "idle" | "approving" | "done";
  approvedIds: Set<string>;
}) {
  return (
    <div className="flex-1 overflow-auto">
      <div
        className="px-5 py-2 text-[10.5px] uppercase"
        style={{
          display: "grid",
          gridTemplateColumns: "36px 64px minmax(0,1fr) 140px 100px 120px 60px",
          gap: 12,
          color: "var(--color-ink-faint)",
          letterSpacing: "0.11em",
          fontWeight: 600,
        }}
      >
        <span />
        <button
          className="text-left inline-flex items-center gap-1 hover:text-ink"
          onClick={() => toggleSort("ago")}
        >
          № <SortIndicator active={sort.key === "ago"} dir={sort.dir} />
        </button>
        <button
          className="text-left inline-flex items-center gap-1 hover:text-ink"
          onClick={() => toggleSort("customer")}
        >
          Customer <SortIndicator active={sort.key === "customer"} dir={sort.dir} />
        </button>
        <span>Type</span>
        <button
          className="text-right inline-flex items-center gap-1 hover:text-ink justify-end"
          onClick={() => toggleSort("amount")}
        >
          Amount <SortIndicator active={sort.key === "amount"} dir={sort.dir} />
        </button>
        <span>Status</span>
        <span className="text-right">Ago</span>
      </div>
      <div className="rule-soft" style={{ height: 1, background: "var(--color-rule-soft)" }} />

      <div>
        {rows.map((r, i) => {
          const isSelected = selected.has(r.num);
          const isApproved = approvedIds.has(r.num);
          const isExpanded = expanded === r.num;
          return (
            <div
              key={r.num}
              style={{
                borderBottom: i < rows.length - 1 ? "1px solid var(--color-rule-soft)" : "none",
                background: isExpanded ? "var(--color-surface)" : "transparent",
              }}
            >
              <div
                className="px-5 py-2.5 items-center hover:bg-[color:var(--color-surface)] transition-colors cursor-pointer"
                style={{
                  display: "grid",
                  gridTemplateColumns: "36px 64px minmax(0,1fr) 140px 100px 120px 60px",
                  gap: 12,
                }}
                onClick={() => setExpanded(isExpanded ? null : r.num)}
              >
                <div onClick={(e) => { e.stopPropagation(); toggle(r.num); }}>
                  <Checkbox checked={isSelected} disabled={phase !== "idle"} />
                </div>
                <span className="font-mono text-[12px] tabular-nums" style={{ color: "var(--color-ink-muted)" }}>
                  {r.num}
                </span>
                <span className="text-[12.5px] font-medium truncate" style={{ color: "var(--color-ink-strong)" }}>
                  {r.customer}
                </span>
                <span className="text-[12px] truncate" style={{ color: "var(--color-ink-muted)" }}>
                  {r.type}
                </span>
                <span className="text-right font-mono text-[12px] tabular-nums" style={{ color: "var(--color-ink-strong)" }}>
                  ${r.amount.toLocaleString()}
                </span>
                <span>
                  {isApproved ? (
                    <motion.span
                      initial={{ scale: 0.7, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ duration: 0.2 }}
                      className="text-[10px] uppercase inline-flex items-center gap-1"
                      style={{ color: "var(--color-accent)", letterSpacing: "0.09em", fontWeight: 600 }}
                    >
                      <Check className="h-3 w-3" strokeWidth={3} />
                      approved
                    </motion.span>
                  ) : phase === "approving" && isSelected ? (
                    <span
                      className="text-[10px] uppercase inline-flex items-center gap-1.5"
                      style={{ color: "var(--color-ink-muted)", letterSpacing: "0.09em", fontWeight: 600 }}
                    >
                      <span className="h-1.5 w-1.5 rounded-full animate-pulse-dot" style={{ background: "var(--color-accent)" }} />
                      firing
                    </span>
                  ) : (
                    <StatusDot tone={r.status} />
                  )}
                </span>
                <span className="text-right font-mono text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                  {r.ago}
                </span>
              </div>
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.22, ease: [0.25, 1, 0.5, 1] }}
                    className="overflow-hidden"
                  >
                    <RowExpand row={r} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RowExpand({ row }: { row: CaseRow }) {
  return (
    <div
      className="px-5 pl-[calc(20px+36px+8px)] pb-4"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr) minmax(0,1fr)",
        gap: 24,
      }}
    >
      <div>
        <div className="eyebrow mb-1">Manthan’s read</div>
        <p className="text-[12px] leading-relaxed" style={{ color: "var(--color-ink-muted)" }}>
          {row.customer} · {row.type.toLowerCase()} of{" "}
          <span className="font-mono" style={{ color: "var(--color-ink-strong)" }}>
            ${row.amount.toLocaleString()}
          </span>
          . {row.drafts} action{row.drafts === 1 ? "" : "s"} drafted, cited, and waiting on your approval.
        </p>
      </div>
      <div>
        <div className="eyebrow mb-1">Sources</div>
        <div className="flex items-center gap-2.5">
          {["stripe", "salesforce", "zendesk", "notion"].slice(0, 3 + (row.drafts > 1 ? 1 : 0)).map((s) => (
            <span key={s} className="inline-flex items-center gap-1 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
              <SourceIcon id={s} size={11} tinted />
              {s[0].toUpperCase() + s.slice(1)}
            </span>
          ))}
        </div>
      </div>
      <div>
        <div className="eyebrow mb-1">Policy</div>
        <div className="text-[11.5px] font-mono leading-relaxed" style={{ color: "var(--color-ink-muted)" }}>
          {row.amount > 500 ? (
            <>refund.threshold = $500<br />→ awaiting approval</>
          ) : (
            <>under refund.threshold<br />→ auto-approve eligible</>
          )}
        </div>
      </div>
    </div>
  );
}

function LedgerBulkBar({
  selectedCount,
  total,
  actions,
  phase,
  approveAll,
  reset,
}: {
  selectedCount: number;
  total: number;
  actions: number;
  phase: "idle" | "approving" | "done";
  approveAll: () => void;
  reset: () => void;
}) {
  if (selectedCount === 0 && phase === "idle") {
    return (
      <div
        className="px-5 py-3 border-t flex items-center justify-between text-[11.5px]"
        style={{ borderColor: "var(--color-rule-soft)", color: "var(--color-ink-faint)" }}
      >
        <span>Select rows to bulk-approve</span>
        <span className="font-mono" style={{ color: "var(--color-ink-ghost)" }}>↵ to expand · ⌘A select all</span>
      </div>
    );
  }
  if (phase === "done") {
    return (
      <div
        className="px-5 py-3.5 border-t flex items-center justify-between"
        style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
      >
        <div className="text-[12.5px]">
          <span className="font-medium inline-flex items-center gap-1.5" style={{ color: "var(--color-accent)" }}>
            <Check className="h-3.5 w-3.5" strokeWidth={3} />
            Approved
          </span>
          <span style={{ color: "var(--color-ink-faint)" }}> · </span>
          <span style={{ color: "var(--color-ink-muted)" }}>
            {selectedCount} cases · {actions} actions fired across Stripe, Gmail, Linear · brief posted to{" "}
            <span className="font-mono">#billing-ops</span>
          </span>
        </div>
        <button
          onClick={reset}
          className="text-[11.5px] inline-flex items-center gap-1.5"
          style={{ color: "var(--color-ink-muted)" }}
        >
          <RotateCcw className="h-3 w-3" />
          Undo / replay
        </button>
      </div>
    );
  }
  return (
    <div
      className="px-5 py-3 border-t flex items-center justify-between gap-4"
      style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
    >
      <div className="text-[12px]">
        <span style={{ color: "var(--color-ink-strong)" }}>
          {selectedCount}
        </span>{" "}
        <span style={{ color: "var(--color-ink-muted)" }}>selected</span>{" "}
        <span style={{ color: "var(--color-ink-faint)" }}>·</span>{" "}
        <span style={{ color: "var(--color-ink-strong)" }}>
          ${total.toLocaleString()}
        </span>{" "}
        <span style={{ color: "var(--color-ink-muted)" }}>exposure</span>{" "}
        <span style={{ color: "var(--color-ink-faint)" }}>·</span>{" "}
        <span style={{ color: "var(--color-ink-muted)" }}>
          fires <span style={{ color: "var(--color-ink-strong)" }}>{actions}</span> actions
        </span>
      </div>
      <button
        onClick={approveAll}
        disabled={phase === "approving"}
        className="text-[12.5px] font-semibold px-4 py-1.5 disabled:opacity-70"
        style={{ background: "var(--color-accent)", color: "var(--color-accent-ink)" }}
      >
        {phase === "approving" ? "Approving…" : "Approve all"}
      </button>
    </div>
  );
}

function LedgerStats({ selectedCount, total }: { selectedCount: number; total: number }) {
  return (
    <aside
      className="border-l p-5 space-y-5"
      style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-bg)" }}
    >
      <div>
        <div className="eyebrow">Selection</div>
        <div
          className="mt-2 font-mono text-[28px] tracking-tight nums"
          style={{ color: "var(--color-ink-strong)" }}
        >
          ${total.toLocaleString()}
        </div>
        <div className="text-[11.5px] mt-0.5" style={{ color: "var(--color-ink-muted)" }}>
          across {selectedCount} {selectedCount === 1 ? "case" : "cases"}
        </div>
      </div>

      <div>
        <div className="eyebrow">Today’s ledger</div>
        <dl
          className="mt-2 text-[12px]"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1fr) auto",
            rowGap: 4,
          }}
        >
          {[
            ["Inbox",      "12"],
            ["Resolved",   "47"],
            ["Recovered",  "$12,320"],
            ["MTTR",       "42s"],
            ["Auto-share", "63%"],
          ].map(([k, v]) => (
            <div key={k} className="contents">
              <dt style={{ color: "var(--color-ink-muted)" }}>{k}</dt>
              <dd className="font-mono nums text-right" style={{ color: "var(--color-ink-strong)" }}>{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div>
        <div className="eyebrow">Daily caps</div>
        <div className="mt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          <div className="flex items-center justify-between">
            <span>Refund exposure</span>
            <span style={{ color: "var(--color-ink-strong)" }}>
              $5,440 / $10,000
            </span>
          </div>
          <div className="mt-1.5 h-1" style={{ background: "var(--color-rule-soft)" }}>
            <div
              className="h-full"
              style={{ width: "54%", background: "var(--color-accent)" }}
            />
          </div>
        </div>
      </div>

      <div className="pt-2 border-t" style={{ borderColor: "var(--color-rule-soft)" }}>
        <div className="text-[10.5px] font-mono" style={{ color: "var(--color-ink-ghost)" }}>
          Updated 14s ago · auto-refresh on
        </div>
      </div>
    </aside>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   SCENE 3 - POLICY (visual rule builder, NOT YAML)
   Toggles, sliders, checkboxes - never code editing.
   ═══════════════════════════════════════════════════════════════════════ */

type PolicyFile = "refunds" | "chargebacks" | "dunning" | "renewals";

type RuleControl =
  | { kind: "toggle"; on: boolean }
  | { kind: "slider"; value: number; min: number; max: number; step: number; prefix?: string; suffix?: string }
  | { kind: "checkbox"; on: boolean };

interface Rule {
  id: string;
  label: string;
  hint?: string;
  control: RuleControl;
}

interface PolicySection {
  id: string;
  title: string;
  rules: Rule[];
}

interface PolicyFileData {
  displayName: string;
  description: string;
  sections: PolicySection[];
  impact: { value: string; label: string }[];
  samples: { num: string; customer: string; amount: string }[];
}

const POLICY_FILES: { id: PolicyFile; name: string }[] = [
  { id: "refunds",     name: "Refunds"     },
  { id: "chargebacks", name: "Chargebacks" },
  { id: "dunning",     name: "Dunning"     },
  { id: "renewals",    name: "Renewals"    },
];

const POLICY_INITIAL: Record<PolicyFile, PolicyFileData> = {
  refunds: {
    displayName: "Refund policy",
    description: "How Manthan handles refund requests across your stack.",
    sections: [
      {
        id: "auto-approve",
        title: "Auto-approve refunds",
        rules: [
          { id: "enabled",     label: "Enable auto-approve",                  control: { kind: "toggle",   on: true } },
          { id: "max-amount",  label: "Maximum amount",                       hint: "Refunds at or under this amount auto-approve.", control: { kind: "slider",   value: 100, min: 25, max: 500, step: 25, prefix: "$" } },
          { id: "age",         label: "Customer must be 90+ days old",         control: { kind: "checkbox", on: true } },
          { id: "no-disputes", label: "Customer must have no prior disputes",  control: { kind: "checkbox", on: true } },
        ],
      },
      {
        id: "health-routing",
        title: "Health-based routing",
        rules: [
          { id: "healthy-csm",   label: "Healthy customers · trigger CSM follow-up",   control: { kind: "checkbox", on: true  } },
          { id: "at-risk-exec",  label: "At-risk customers · escalate to exec sponsor", control: { kind: "checkbox", on: false } },
        ],
      },
    ],
    impact: [
      { value: "14 / 47",  label: "Would auto-approve (last 30d)" },
      { value: "4h → 30s", label: "MTTR for this band" },
    ],
    samples: [
      { num: "C-4793", customer: "Loop & Co",  amount: "$67" },
      { num: "C-4781", customer: "ZenSaaS",    amount: "$89" },
      { num: "C-4774", customer: "PlanetGrid", amount: "$42" },
    ],
  },
  chargebacks: {
    displayName: "Chargeback policy",
    description: "How Manthan responds when a bank files a dispute.",
    sections: [
      {
        id: "response",
        title: "Response handling",
        rules: [
          { id: "always-escalate", label: "Always escalate to your team",            control: { kind: "toggle",   on: true  } },
          { id: "auto-accept",     label: "Auto-accept the dispute",                  control: { kind: "toggle",   on: false } },
          { id: "confirm-first",   label: "Confirm with customer before responding",  control: { kind: "checkbox", on: true  } },
        ],
      },
      {
        id: "fraud",
        title: "Fraud signal",
        rules: [
          { id: "no-tickets",   label: "Route accounts with 0 support tickets to fraud", hint: "Likely a compromised card, not a dissatisfied customer.", control: { kind: "checkbox", on: true } },
          { id: "evidence-win", label: "Evidence response window",                       control: { kind: "slider",   value: 7, min: 1, max: 14, step: 1, suffix: " days" } },
        ],
      },
    ],
    impact: [
      { value: "8 / 23", label: "Routed to fraud (last 90d)" },
      { value: "+11%",   label: "Net recovery vs. accept" },
    ],
    samples: [
      { num: "C-4774", customer: "Pulse Healthcare", amount: "$890"   },
      { num: "C-4721", customer: "Northwind Labs",   amount: "$1,400" },
      { num: "C-4698", customer: "Globex Studio",    amount: "$320"   },
    ],
  },
  dunning: {
    displayName: "Dunning policy",
    description: "How Manthan recovers failed payments and renewals.",
    sections: [
      {
        id: "recovery",
        title: "Failed payment recovery",
        rules: [
          { id: "card-update", label: "Send card-update email",         control: { kind: "toggle",   on: true } },
          { id: "slack-csm",   label: "Slack the CSM if ARR over $20K",  control: { kind: "checkbox", on: true } },
          { id: "grace",       label: "Default grace period",            hint: "How long before service is degraded.", control: { kind: "slider", value: 72, min: 24, max: 168, step: 24, suffix: "h" } },
        ],
      },
      {
        id: "high-value",
        title: "High-value accounts",
        rules: [
          { id: "arr-threshold",  label: "ARR threshold",            control: { kind: "slider",   value: 200, min: 50, max: 500, step: 25, prefix: "$", suffix: "K" } },
          { id: "all-channels",   label: "Use all channels",         hint: "Email + Slack + SMS card-update.", control: { kind: "toggle", on: true } },
          { id: "no-degradation", label: "No service degradation",   control: { kind: "checkbox", on: true } },
        ],
      },
    ],
    impact: [
      { value: "$48K", label: "Recovered (last 90d)" },
      { value: "96h",  label: "Extended grace for top accounts" },
    ],
    samples: [
      { num: "C-4798", customer: "ZenSaaS Studios", amount: "$1,890" },
      { num: "C-4781", customer: "Midcorp Systems", amount: "$4,200" },
      { num: "C-4732", customer: "Hexcore Inc.",    amount: "$2,140" },
    ],
  },
  renewals: {
    displayName: "Renewal policy",
    description: "How Manthan flags and intervenes on upcoming renewals.",
    sections: [
      {
        id: "nudges",
        title: "Renewal nudges",
        rules: [
          { id: "t60", label: "T-60 first nudge",   control: { kind: "checkbox", on: true } },
          { id: "t30", label: "T-30 second nudge",  control: { kind: "checkbox", on: true } },
          { id: "t7",  label: "T-7 final nudge",    control: { kind: "checkbox", on: true } },
        ],
      },
      {
        id: "retention",
        title: "Retention plays",
        rules: [
          { id: "auto-fire", label: "Auto-fire retention play when health = poor", control: { kind: "toggle",   on: true } },
          { id: "credit",    label: "Offer credit when usage is trending down",     control: { kind: "checkbox", on: true } },
          { id: "exec",      label: "Loop in exec sponsor for high-value accounts", control: { kind: "checkbox", on: true } },
        ],
      },
    ],
    impact: [
      { value: "+6.2%", label: "Renewal rate lift" },
      { value: "$184K", label: "ARR saved (est. 90d)" },
    ],
    samples: [
      { num: "C-4665", customer: "Quantix Co.",     amount: "$84K"  },
      { num: "C-4632", customer: "Bluefin Studios", amount: "$22K"  },
      { num: "C-4601", customer: "Lumen & Sons",    amount: "$120K" },
    ],
  },
};

/**
 * Derive live impact stats from the current rule state of a policy file.
 * Numbers are heuristic - they react to slider + toggle + checkbox changes
 * in a plausible direction so the user can see their edits matter.
 */
function computeImpact(
  fileId: PolicyFile,
  sections: PolicySection[],
): { value: string; label: string }[] {
  // Flatten rules into a lookup
  const rules = new Map<string, RuleControl>();
  sections.forEach((s) => s.rules.forEach((r) => rules.set(r.id, r.control)));

  const tog = (id: string): boolean => {
    const r = rules.get(id);
    return r && (r.kind === "toggle" || r.kind === "checkbox") ? r.on : false;
  };
  const slider = (id: string, dflt: number): number => {
    const r = rules.get(id);
    return r && r.kind === "slider" ? r.value : dflt;
  };

  switch (fileId) {
    case "refunds": {
      if (!tog("enabled")) {
        return [
          { value: "0 / 47", label: "Auto-approves disabled" },
          { value: "-",      label: "MTTR for this band" },
        ];
      }
      const max = slider("max-amount", 100);
      const ageOn = tog("age");
      const noDisputesOn = tog("no-disputes");
      // $100 max + both ON → 14
      let count = Math.round(max / 7);
      if (!ageOn) count += 3;
      if (!noDisputesOn) count += 2;
      count = Math.max(0, Math.min(count, 47));
      const mttr = count > 0 ? "4h → 30s" : "-";
      return [
        { value: `${count} / 47`, label: "Would auto-approve (last 30d)" },
        { value: mttr,             label: "MTTR for this band" },
      ];
    }
    case "chargebacks": {
      const autoAccept = tog("auto-accept");
      const noTickets = tog("no-tickets");
      const confirmFirst = tog("confirm-first");
      const winDays = slider("evidence-win", 7);
      // If auto-accept on, we just eat losses - fraud routing = 0
      const routed = autoAccept ? 0 : noTickets ? 8 : 4;
      // Net recovery: confirm-first + fraud routing wins back; auto-accept loses
      let recovery = autoAccept ? -8 : 0;
      if (confirmFirst) recovery += 6;
      if (noTickets) recovery += 5;
      if (winDays < 4) recovery -= 2; // tight window = lost evidence
      return [
        { value: `${routed} / 23`,                           label: "Routed to fraud (last 90d)" },
        { value: (recovery >= 0 ? "+" : "") + recovery + "%", label: "Net recovery vs. accept-all" },
      ];
    }
    case "dunning": {
      const cardUpdate = tog("card-update");
      const slackCsm = tog("slack-csm");
      const grace = slider("grace", 72);
      const allChannels = tog("all-channels");
      const arrThreshold = slider("arr-threshold", 200);
      // Recovered scales with channels enabled
      let recovered = 0;
      if (cardUpdate) recovered += 28;
      if (slackCsm) recovered += 12;
      if (allChannels) recovered += 8;
      // Tighter ARR threshold = more high-value accounts get all-channels
      recovered = Math.round(recovered * (1 + (300 - arrThreshold) / 1000));
      return [
        { value: `$${recovered}K`, label: "Recovered (last 90d)" },
        { value: `${grace}h`,       label: "Default grace period" },
      ];
    }
    case "renewals": {
      const nudges =
        (tog("t60") ? 1 : 0) + (tog("t30") ? 1 : 0) + (tog("t7") ? 1 : 0);
      const autoFire = tog("auto-fire");
      const credit = tog("credit");
      const exec = tog("exec");
      const lift = nudges * 1.5 + (autoFire ? 1.7 : 0) + (credit ? 0.6 : 0) + (exec ? 0.4 : 0);
      const arrSaved = Math.round(lift * 30); // crude scale to $K
      return [
        { value: `+${lift.toFixed(1)}%`, label: "Renewal rate lift" },
        { value: `$${arrSaved}K`,         label: "ARR saved (est. 90d)" },
      ];
    }
  }
}

function PolicyDocument() {
  const [activeFile, setActiveFile] = useState<PolicyFile>("refunds");
  const [policy, setPolicy] = useState(POLICY_INITIAL);
  const [savedByFile, setSavedByFile] = useState<Record<PolicyFile, boolean>>({
    refunds: true, chargebacks: true, dunning: true, renewals: true,
  });
  const [phase, setPhase] = useState<"idle" | "saving">("idle");
  const [showToast, setShowToast] = useState(false);

  const file = policy[activeFile];

  // Live impact recomputes whenever any rule changes
  const liveImpact = useMemo(
    () => computeImpact(activeFile, file.sections),
    [activeFile, file.sections],
  );

  const updateRule = (sectionId: string, ruleId: string, next: RuleControl) => {
    setPolicy((prev) => ({
      ...prev,
      [activeFile]: {
        ...prev[activeFile],
        sections: prev[activeFile].sections.map((s) =>
          s.id !== sectionId
            ? s
            : { ...s, rules: s.rules.map((r) => (r.id === ruleId ? { ...r, control: next } : r)) },
        ),
      },
    }));
    setSavedByFile((prev) => ({ ...prev, [activeFile]: false }));
  };

  const save = () => {
    if (savedByFile[activeFile]) return;
    setPhase("saving");
    setTimeout(() => {
      setPhase("idle");
      setSavedByFile((prev) => ({ ...prev, [activeFile]: true }));
      setShowToast(true);
      setTimeout(() => setShowToast(false), 2800);
    }, 500);
  };

  const reset = () => {
    setPolicy(POLICY_INITIAL);
    setSavedByFile({ refunds: true, chargebacks: true, dunning: true, renewals: true });
  };

  const isSaved = savedByFile[activeFile];

  return (
    <div
      className="h-full"
      style={{
        display: "grid",
        gridTemplateColumns: "180px minmax(0, 1fr) 260px",
        background: "var(--color-bg)",
      }}
    >
      {/* File tree */}
      <aside
        className="border-r p-3 space-y-1 min-h-0 overflow-hidden"
        style={{ borderColor: "var(--color-rule-soft)" }}
      >
        <div className="eyebrow mb-2 px-1.5">Policies</div>
        {POLICY_FILES.map((f) => {
          const active = f.id === activeFile;
          const dirty = !savedByFile[f.id];
          return (
            <button
              key={f.id}
              onClick={() => setActiveFile(f.id)}
              className="w-full text-left px-2 py-1.5 flex items-baseline justify-between gap-2"
              style={{
                background: active ? "var(--color-surface)" : "transparent",
                borderLeft: active ? "2px solid var(--color-accent)" : "2px solid transparent",
              }}
            >
              <span
                className="text-[12px]"
                style={{
                  color: active ? "var(--color-ink-strong)" : "var(--color-ink-muted)",
                  fontWeight: active ? 500 : 400,
                }}
              >
                {f.name}
              </span>
              {dirty && (
                <span
                  className="h-1.5 w-1.5 rounded-full shrink-0"
                  style={{ background: "var(--color-accent)" }}
                  title="unsaved"
                />
              )}
            </button>
          );
        })}
        <div className="rule-soft my-3" style={{ height: 1, background: "var(--color-rule-soft)" }} />
        <div className="eyebrow mb-2 px-1.5">Version</div>
        <div className="px-2 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
          <div>v0.1 · 23 May</div>
          <div className="text-[10px] mt-0.5" style={{ color: "var(--color-ink-faint)" }}>
            Edited by you · 4m ago
          </div>
        </div>
      </aside>

      {/* Rule builder */}
      <section className="flex flex-col min-w-0 min-h-0 overflow-hidden">
        <div
          className="px-6 pt-5 pb-4 border-b"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          <div className="flex items-baseline justify-between">
            <h2
              className="text-[18px] font-medium tracking-[-0.01em]"
              style={{ color: "var(--color-ink-strong)" }}
            >
              {file.displayName}
            </h2>
            <span
              className="text-[10px] uppercase"
              style={{
                color: isSaved ? "var(--color-ink-faint)" : "var(--color-accent)",
                letterSpacing: "0.10em",
                fontWeight: 600,
              }}
            >
              {phase === "saving" ? "saving…" : isSaved ? "synced" : "unsaved changes"}
            </span>
          </div>
          <p
            className="mt-1 text-[12px]"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {file.description}
          </p>
        </div>

        <div className="flex-1 min-h-0 overflow-auto px-6 py-5 space-y-6">
          {file.sections.map((section) => (
            <RuleSection
              key={section.id}
              section={section}
              onChange={(ruleId, next) => updateRule(section.id, ruleId, next)}
            />
          ))}
        </div>

        <div
          className="px-6 py-3 border-t flex items-center justify-between gap-3"
          style={{ borderColor: "var(--color-rule-soft)", background: "var(--color-surface)" }}
        >
          <div className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
            Previewed against the last 30 days of cases.
          </div>
          <div className="flex items-center gap-2">
            {!isSaved && (
              <button
                onClick={reset}
                className="text-[11.5px] font-medium px-3 py-1.5"
                style={{ color: "var(--color-ink-muted)" }}
              >
                Cancel
              </button>
            )}
            <button
              disabled={isSaved || phase === "saving"}
              onClick={save}
              className="text-[12px] font-semibold px-4 py-1.5 disabled:opacity-50 inline-flex items-center gap-1.5"
              style={{
                background: isSaved ? "var(--color-surface-2)" : "var(--color-accent)",
                color: isSaved ? "var(--color-ink-muted)" : "var(--color-accent-ink)",
              }}
            >
              {isSaved ? (
                <>
                  <Check className="h-3.5 w-3.5" strokeWidth={3} />
                  Saved
                </>
              ) : phase === "saving" ? (
                "Saving…"
              ) : (
                "Save changes"
              )}
            </button>
          </div>
        </div>
      </section>

      {/* Impact rail */}
      <aside
        className="border-l p-5 space-y-5 min-h-0 overflow-auto"
        style={{ borderColor: "var(--color-rule-soft)" }}
      >
        <div>
          <div className="eyebrow flex items-center gap-1.5">
            Live impact
            <span
              className="h-1 w-1 rounded-full animate-pulse-dot"
              style={{ background: "var(--color-accent)" }}
            />
          </div>
          <div className="mt-3 space-y-3">
            {liveImpact.map((m) => (
              <motion.div
                key={m.label}
                layout
                initial={false}
              >
                <motion.div
                  key={m.value}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22, ease: [0.25, 1, 0.5, 1] }}
                  className="text-[20px] tabular-nums"
                  style={{ color: "var(--color-accent)", fontWeight: 500 }}
                >
                  {m.value}
                </motion.div>
                <div className="text-[10.5px] mt-0.5" style={{ color: "var(--color-ink-faint)" }}>
                  {m.label}
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        <div className="rule-soft" style={{ height: 1, background: "var(--color-rule-soft)" }} />

        <div>
          <div className="eyebrow">Sample affected cases</div>
          <ul className="mt-2 space-y-1.5 text-[11.5px]">
            {file.samples.map((s) => (
              <li
                key={s.num}
                className="items-baseline"
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(0,1fr) auto",
                  gap: 8,
                }}
              >
                <span style={{ color: "var(--color-ink-muted)" }} className="truncate">
                  {s.customer}
                </span>
                <span className="tabular-nums" style={{ color: "var(--color-ink-strong)" }}>
                  {s.amount}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <AnimatePresence>
          {showToast && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.2 }}
              className="text-[11.5px] px-3 py-2 border inline-flex items-center gap-2"
              style={{
                background: "var(--color-accent-tint)",
                borderColor: "var(--color-accent-line)",
                color: "var(--color-accent)",
              }}
            >
              <Check className="h-3.5 w-3.5" strokeWidth={3} />
              Policy saved
            </motion.div>
          )}
        </AnimatePresence>
      </aside>
    </div>
  );
}

function RuleSection({
  section,
  onChange,
}: {
  section: PolicySection;
  onChange: (ruleId: string, next: RuleControl) => void;
}) {
  return (
    <div>
      <div
        className="text-[11px] uppercase mb-3"
        style={{ color: "var(--color-ink-muted)", letterSpacing: "0.10em", fontWeight: 600 }}
      >
        {section.title}
      </div>
      <div className="space-y-2">
        {section.rules.map((rule) => (
          <RuleRow key={rule.id} rule={rule} onChange={(next) => onChange(rule.id, next)} />
        ))}
      </div>
    </div>
  );
}

function RuleRow({
  rule,
  onChange,
}: {
  rule: Rule;
  onChange: (next: RuleControl) => void;
}) {
  return (
    <div
      className="rounded-lg px-3.5 py-3 border flex items-start justify-between gap-4"
      style={{
        background: "var(--color-surface)",
        borderColor: "var(--color-rule-soft)",
      }}
    >
      <div className="min-w-0 flex-1">
        <div className="text-[12.5px]" style={{ color: "var(--color-ink-strong)" }}>
          {rule.label}
        </div>
        {rule.hint && (
          <div className="text-[10.5px] mt-0.5" style={{ color: "var(--color-ink-faint)" }}>
            {rule.hint}
          </div>
        )}
        {rule.control.kind === "slider" && (
          <div className="mt-2.5 flex items-center gap-3">
            <input
              type="range"
              min={rule.control.min}
              max={rule.control.max}
              step={rule.control.step}
              value={rule.control.value}
              onChange={(e) =>
                onChange({
                  ...(rule.control as Extract<RuleControl, { kind: "slider" }>),
                  value: parseInt(e.target.value),
                })
              }
              className="range-themed flex-1"
              style={{
                ["--fill" as string]: `${
                  ((rule.control.value - rule.control.min) /
                    (rule.control.max - rule.control.min)) *
                  100
                }%`,
              }}
            />
            <span
              className="text-[11.5px] tabular-nums min-w-[56px] text-right"
              style={{ color: "var(--color-ink-strong)", fontWeight: 500 }}
            >
              {rule.control.prefix ?? ""}
              {rule.control.value}
              {rule.control.suffix ?? ""}
            </span>
          </div>
        )}
      </div>

      <div className="shrink-0 pt-0.5">
        {rule.control.kind === "toggle" && (
          <Toggle on={rule.control.on} onChange={(v) => onChange({ kind: "toggle", on: v })} />
        )}
        {rule.control.kind === "checkbox" && (
          <CheckboxBig on={rule.control.on} onChange={(v) => onChange({ kind: "checkbox", on: v })} />
        )}
      </div>
    </div>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className="relative h-5 w-9 rounded-full transition-colors"
      style={{ background: on ? "var(--color-accent)" : "var(--color-rule)" }}
      aria-pressed={on}
    >
      <span
        className="absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all"
        style={{ left: on ? "calc(100% - 18px)" : "2px" }}
      />
    </button>
  );
}

function CheckboxBig({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className="h-5 w-5 rounded inline-flex items-center justify-center transition-all"
      style={{
        background: on ? "var(--color-accent)" : "transparent",
        border: `1.5px solid ${on ? "var(--color-accent)" : "var(--color-rule-strong)"}`,
      }}
      aria-pressed={on}
    >
      {on && <Check className="h-3 w-3" style={{ color: "var(--color-accent-ink)" }} strokeWidth={3} />}
    </button>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   SHARED PRIMITIVES
   ═══════════════════════════════════════════════════════════════════════ */

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}

function Rule() {
  return <div className="rule" style={{ height: 1, background: "var(--color-rule-soft)" }} />;
}

function Ref({ n }: { n: number }) {
  return (
    <sup
      className="ref"
      style={{ color: "var(--color-accent)" }}
    >
      [{n}]
    </sup>
  );
}

function Checkbox({ checked, disabled }: { checked: boolean; disabled?: boolean }) {
  return (
    <div
      className="h-4 w-4 inline-flex items-center justify-center"
      style={{
        background: checked ? "var(--color-accent)" : "transparent",
        border: `1px solid ${checked ? "var(--color-accent)" : "var(--color-rule-strong)"}`,
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {checked && <Check className="h-2.5 w-2.5" style={{ color: "var(--color-accent-ink)" }} strokeWidth={3} />}
    </div>
  );
}

function SortIndicator({ active, dir }: { active: boolean; dir: "asc" | "desc" }) {
  if (!active) return <span className="opacity-0">↑</span>;
  return (
    <span className="font-mono text-[10px]" style={{ color: "var(--color-accent)" }}>
      {dir === "asc" ? "↑" : "↓"}
    </span>
  );
}

/* status display ─────────────────────────────────────────────────────── */

function StatusBadge({ status }: { status: CaseStatus }) {
  if (status === "approved") {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
        style={{ color: "var(--color-accent)", letterSpacing: "0.09em", fontWeight: 600 }}
      >
        <Check className="h-3 w-3" strokeWidth={3} />
        Resolved
      </div>
    );
  }
  if (status === "approving") {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
        style={{ color: "var(--color-accent)", letterSpacing: "0.09em", fontWeight: 600 }}
      >
        <span className="h-1.5 w-1.5 rounded-full animate-pulse-dot" style={{ background: "var(--color-accent)" }} />
        Approving
      </div>
    );
  }
  if (status === "held") {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
        style={{ color: "var(--color-ink-muted)", letterSpacing: "0.09em", fontWeight: 600 }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--color-ink-muted)" }} />
        On hold
      </div>
    );
  }
  return (
    <div
      className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] uppercase"
      style={{ color: "var(--color-amber)", letterSpacing: "0.09em", fontWeight: 600 }}
    >
      <span className="h-1.5 w-1.5 rounded-full animate-pulse-dot" style={{ background: "var(--color-amber)" }} />
      Awaiting nod
    </div>
  );
}

function StatusDot({ tone, subtle }: { tone: Tone; subtle?: boolean }) {
  const palette: Record<
    Tone,
    { color: string; label: string; pulse?: boolean }
  > = {
    awaiting:      { color: "var(--color-amber)",   label: "awaiting",  pulse: true },
    drafted:       { color: "var(--color-info)",    label: "drafted" },
    investigating: { color: "var(--color-info)",    label: "investigating" },
    executing:     { color: "var(--color-accent)",  label: "executing", pulse: true },
    resolved:      { color: "var(--color-accent)",  label: "resolved" },
  };
  const p = palette[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 ${subtle ? "text-[10px]" : "text-[10.5px]"} uppercase`}
      style={{
        color: subtle ? "var(--color-ink-faint)" : p.color,
        letterSpacing: "0.09em",
        fontWeight: 600,
      }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${p.pulse ? "animate-pulse-dot" : ""}`}
        style={{ background: p.color }}
      />
      {p.label}
    </span>
  );
}

