/**
 * Privacy Policy. Drafted plainly, not lawyered.
 * Replace with counsel-approved version before public GA.
 */

import { MarketingShell, Section, DefList } from "@/components/marketing/MarketingShell";

export default function Privacy() {
  return (
    <MarketingShell
      eyebrow="Privacy Policy"
      title={
        <>
          What we collect, what we don't,{" "}
          <em className="font-serif italic font-normal">and why.</em>
        </>
      }
      intro="Plain English. Short. Updated when anything changes."
      lastUpdated="2026-05-25"
    >
      <Section heading="Who we are">
        <p>
          Manthan ("we," "us") is operated by Manthan Inc., a Delaware C-corp
          building hosted operations software for billing and revenue teams. This
          policy applies to manthan-ui.vercel.app, the Manthan dashboard, and
          every Manthan API.
        </p>
      </Section>

      <Section heading="What we collect">
        <DefList
          items={[
            {
              term: "Account",
              def: "Your work email, name, company, role. Created when you sign up.",
            },
            {
              term: "Workspace data",
              def: "Records you connect via OAuth from Stripe, Salesforce, Zendesk, Notion, Slack, Gmail, and similar systems. We process this data to investigate cases, draft replies, and fire actions you approve.",
            },
            {
              term: "Operational telemetry",
              def: "Page views, button clicks, latency, error traces. Used to keep the product fast and crash-free. No third-party advertising trackers.",
            },
            {
              term: "Approval & audit history",
              def: "Every decision made by you or by Manthan, with timestamp and approver. Kept for compliance and to improve the policy graph.",
            },
          ]}
        />
      </Section>

      <Section heading="What we never do">
        <ul className="list-disc pl-5 space-y-2">
          <li>Sell your data, ever. No exceptions.</li>
          <li>Train shared base models on your workspace data.</li>
          <li>Read or relay messages from your connected sources without an explicit case trigger.</li>
          <li>Share your data with other Manthan customers.</li>
        </ul>
      </Section>

      <Section heading="Where data lives">
        <p>
          Production data is hosted on AWS in <strong>us-east-1</strong> by default.
          Enterprise customers can request <strong>eu-west-1</strong> or{" "}
          <strong>ap-south-1</strong> residency. Encryption at rest (AES-256) and
          in transit (TLS 1.3). Secrets sit in AWS KMS. We rotate access keys on a
          90-day schedule.
        </p>
      </Section>

      <Section heading="Subprocessors">
        <p>
          We share necessary data with a short list of vetted subprocessors so the
          product can function:
        </p>
        <DefList
          items={[
            { term: "AWS", def: "Compute, storage, KMS. us-east-1 / eu-west-1 / ap-south-1." },
            { term: "Vercel", def: "Static asset hosting for the marketing site only. No customer workspace data." },
            { term: "Anthropic / OpenAI", def: "LLM inference. Zero-retention API mode. Customer data is not used to train base models." },
            { term: "Postmark", def: "Transactional email (sign-in links, weekly digests)." },
            { term: "Stripe", def: "Subscription and payment processing for Manthan invoices." },
          ]}
        />
        <p>
          The current list lives at{" "}
          <a
            href="/dpa"
            style={{ color: "oklch(0.62 0.15 150)", textDecoration: "underline" }}
          >
            /dpa
          </a>{" "}
          and is updated whenever it changes.
        </p>
      </Section>

      <Section heading="Your rights">
        <p>
          Under GDPR, CCPA, and DPDPA you can access, correct, export, or delete
          your data at any time. Send the request to{" "}
          <a
            href="mailto:hitakshi@miny-labs.com"
            style={{ color: "oklch(0.62 0.15 150)", textDecoration: "underline" }}
          >
            hitakshi@miny-labs.com
          </a>{" "}
          and we'll complete it within 30 days. No fees.
        </p>
      </Section>

      <Section heading="Retention">
        <p>
          Workspace data is retained while your account is active and for 90 days
          after deletion (for billing reconciliation and audit replay). After 90
          days it is purged from primary stores and from backups within the next
          monthly snapshot rotation.
        </p>
      </Section>

      <Section heading="Updates to this policy">
        <p>
          Material changes are emailed to all admins 30 days before they take
          effect. The "Last updated" date at the top reflects the most recent
          revision.
        </p>
      </Section>

      <Section heading="Contact">
        <p>
          Privacy questions:{" "}
          <a
            href="mailto:hitakshi@miny-labs.com"
            style={{ color: "oklch(0.62 0.15 150)", textDecoration: "underline" }}
          >
            hitakshi@miny-labs.com
          </a>
          .
        </p>
      </Section>
    </MarketingShell>
  );
}
