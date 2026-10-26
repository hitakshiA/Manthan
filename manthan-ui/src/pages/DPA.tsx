/**
 * Data Processing Addendum. Plain-English summary + subprocessor table.
 * For procurement reviews and GDPR / DPDPA compliance.
 */

import { MarketingShell, Section, DefList } from "@/components/marketing/MarketingShell";

const SUBPROCESSORS: {
  name: string;
  purpose: string;
  region: string;
  data: string;
}[] = [
  {
    name: "Amazon Web Services",
    purpose: "Compute, storage, KMS",
    region: "us-east-1 / eu-west-1 / ap-south-1",
    data: "All workspace data at rest and in transit",
  },
  {
    name: "Anthropic",
    purpose: "LLM inference (Claude family)",
    region: "us-east-1 (zero-retention mode)",
    data: "Case content sent to the agent for reasoning",
  },
  {
    name: "OpenAI",
    purpose: "LLM inference (fallback)",
    region: "us-east-1 (zero-retention mode)",
    data: "Case content sent to the agent for reasoning",
  },
  {
    name: "Vercel",
    purpose: "Marketing site hosting",
    region: "Global edge CDN",
    data: "No workspace data. Public marketing assets only.",
  },
  {
    name: "Stripe",
    purpose: "Subscription billing for Manthan invoices",
    region: "us-east-1",
    data: "Manthan customer billing metadata. Not your end-customer data.",
  },
  {
    name: "Postmark",
    purpose: "Transactional email (sign-in, weekly digest)",
    region: "us-east-1",
    data: "Recipient email + message content (no workspace records)",
  },
];

export default function DPA() {
  return (
    <MarketingShell
      eyebrow="Data Processing Addendum"
      title={
        <>
          How we handle your data. <em className="font-serif italic font-normal">In writing.</em>
        </>
      }
      intro="This is the document procurement teams ask for. Summary first, formal clauses after."
      lastUpdated="2026-05-25"
    >
      <Section heading="Roles">
        <DefList
          items={[
            { term: "Controller", def: "You. You decide what personal data to send into Manthan and why." },
            { term: "Processor", def: "Manthan. We process the data on your instructions, only to provide the service." },
            { term: "Subprocessors", def: "The vendors listed below. Each is bound by a DPA at least as protective as this one." },
          ]}
        />
      </Section>

      <Section heading="Scope">
        <p>
          This addendum applies to all personal data that Manthan processes on
          your behalf in connection with the service, including data ingested
          from systems you connect (Stripe, Salesforce, Zendesk, Notion, Slack,
          Gmail, and similar).
        </p>
      </Section>

      <Section heading="Subprocessors">
        <p className="mb-4">
          Current as of the "Last updated" date at the top. Material changes
          (additions or replacements) are notified to admins by email at least
          30 days before taking effect.
        </p>
        <div
          className="rounded-lg overflow-hidden border"
          style={{
            background: "oklch(0.08 0.005 75)",
            borderColor: "rgba(255,255,255,0.08)",
          }}
        >
          <table className="w-full" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.10)" }}>
                {["Subprocessor", "Purpose", "Region", "Data accessed"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left font-mono uppercase"
                    style={{
                      fontSize: 10.5,
                      color: "oklch(0.55 0.006 75)",
                      letterSpacing: "0.14em",
                      fontWeight: 600,
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SUBPROCESSORS.map((s, i) => (
                <tr
                  key={s.name}
                  style={{
                    borderBottom:
                      i === SUBPROCESSORS.length - 1
                        ? "none"
                        : "1px solid rgba(255,255,255,0.06)",
                  }}
                >
                  <td
                    className="px-4 py-3"
                    style={{
                      fontSize: 14,
                      color: "oklch(0.96 0.004 75)",
                      fontWeight: 600,
                    }}
                  >
                    {s.name}
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ fontSize: 13.5, color: "oklch(0.80 0.006 75)" }}
                  >
                    {s.purpose}
                  </td>
                  <td
                    className="px-4 py-3 font-mono"
                    style={{ fontSize: 12.5, color: "oklch(0.70 0.006 75)" }}
                  >
                    {s.region}
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ fontSize: 13, color: "oklch(0.70 0.006 75)" }}
                  >
                    {s.data}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section heading="Security measures">
        <ul className="list-disc pl-5 space-y-2">
          <li>AES-256 encryption at rest; TLS 1.3 in transit.</li>
          <li>Secrets managed in AWS KMS with 90-day rotation.</li>
          <li>Single sign-on (SAML / OIDC) available on the Enterprise plan.</li>
          <li>Role-based access controls on every workspace resource.</li>
          <li>Every action logged with timestamp + approver. Logs stream to your SIEM if configured.</li>
          <li>Annual third-party penetration test; SOC 2 Type II audit in progress.</li>
        </ul>
      </Section>

      <Section heading="Data residency">
        <p>
          Default region is <strong>us-east-1</strong>. Enterprise customers can
          select <strong>eu-west-1</strong> or <strong>ap-south-1</strong> at no
          extra cost. Once a workspace is assigned a region, data does not move
          across regions without your written instruction.
        </p>
      </Section>

      <Section heading="International transfers">
        <p>
          Where personal data of EU / UK / Swiss data subjects flows outside
          their jurisdiction, transfers are governed by the European
          Commission's Standard Contractual Clauses (Module Two, 2021) and the
          UK IDTA where applicable. The signed clauses are available on
          request.
        </p>
      </Section>

      <Section heading="Sub-processor objection">
        <p>
          You may object to the addition of a new subprocessor for legitimate
          reasons within 30 days of notice. If we cannot accommodate the
          objection, you may terminate the affected services without penalty
          and receive a pro-rata refund.
        </p>
      </Section>

      <Section heading="Data subject requests">
        <p>
          We will assist you in responding to data subject access, correction,
          or deletion requests within 10 business days of your written
          instruction. There is no fee for reasonable assistance.
        </p>
      </Section>

      <Section heading="Breach notification">
        <p>
          If we become aware of a personal data breach affecting your data, we
          will notify you within 72 hours, with the information required by
          GDPR Article 33(3).
        </p>
      </Section>

      <Section heading="Audit rights">
        <p>
          On 30 days' written notice, once per twelve-month period, you may
          conduct or commission an audit of our processing activities relevant
          to your workspace. We may, at our option, satisfy this by providing a
          SOC 2 Type II report once available.
        </p>
      </Section>

      <Section heading="Termination">
        <p>
          On termination of the underlying service agreement, we will return or
          delete all personal data within 90 days, unless retention is required
          by applicable law (e.g., tax / accounting records).
        </p>
      </Section>

      <Section heading="Signed version">
        <p>
          A counter-signed DPA is available for enterprise procurement reviews.
          Email{" "}
          <a
            href="mailto:akash@miny-labs.com"
            style={{ color: "oklch(0.62 0.15 150)", textDecoration: "underline" }}
          >
            akash@miny-labs.com
          </a>{" "}
          and we'll route a copy with your order form.
        </p>
      </Section>
    </MarketingShell>
  );
}
