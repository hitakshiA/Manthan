/**
 * Terms of Service. Plain English. Replace with counsel-approved version
 * before public GA.
 */

import { MarketingShell, Section } from "@/components/marketing/MarketingShell";

export default function Terms() {
  return (
    <MarketingShell
      eyebrow="Terms of Service"
      title={
        <>
          The rules. <em className="font-serif italic font-normal">Short version.</em>
        </>
      }
      intro="If you use Manthan, you agree to these terms. We tried to keep them human."
      lastUpdated="2026-05-25"
    >
      <Section heading="Acceptance">
        <p>
          By creating a Manthan account, accessing the dashboard, or invoking
          the API, you agree to these Terms and to our{" "}
          <a
            href="/privacy"
            style={{ color: "oklch(0.62 0.15 150)", textDecoration: "underline" }}
          >
            Privacy Policy
          </a>
          . If you're agreeing on behalf of a company, you represent that you have
          the authority to bind it.
        </p>
      </Section>

      <Section heading="What Manthan does">
        <p>
          Manthan provides software that investigates billing-operations cases
          (chargebacks, failed payments, refund requests, dunning escalations)
          across the systems you connect, drafts responses and actions, and fires
          those actions under approval gates that you control. We do not provide
          legal, financial, tax, or accounting advice. Final responsibility for
          every action rests with you.
        </p>
      </Section>

      <Section heading="Your account">
        <p>
          You're responsible for keeping credentials secure and for activity that
          happens under your workspace. Tell us within 24 hours if you suspect
          unauthorized access.
        </p>
      </Section>

      <Section heading="Outcome pricing & billing">
        <p>
          Our default model is outcome-based: the first 50 closed cases each
          month are free, then $3 per closed case for 51 to 500, then $2 per
          closed case from 501 to 5,000. "Closed" means one of: chargeback
          resolved, failed payment recovered, refund decided, invoice dispute
          settled, or renewal saved. False positives are not billed.
        </p>
        <p>
          Invoices are issued monthly in arrears via Stripe. Past-due balances
          over 30 days may result in workspace suspension after a 7-day written
          notice. Enterprise contracts are billed annually under a separate
          order form.
        </p>
      </Section>

      <Section heading="Acceptable use">
        <p>
          Don't use Manthan to break the law, evade legitimate chargebacks,
          process payments for prohibited industries, or attempt to extract our
          model weights. We reserve the right to suspend workspaces for clear
          violations after one written warning.
        </p>
      </Section>

      <Section heading="Your data, your IP">
        <p>
          You retain all rights to the data you connect and to anything Manthan
          generates from it on your behalf. We get a narrow, time-limited
          license to process the data only to run the service. See the{" "}
          <a
            href="/privacy"
            style={{ color: "oklch(0.62 0.15 150)", textDecoration: "underline" }}
          >
            Privacy Policy
          </a>{" "}
          for the operational detail.
        </p>
      </Section>

      <Section heading="Service availability">
        <p>
          We target 99.9% monthly uptime for the API and dashboard. Scheduled
          maintenance is announced at least 48 hours in advance. Status lives at
          status.manthan.dev (coming soon to a public mirror near you).
        </p>
      </Section>

      <Section heading="Termination">
        <p>
          You can cancel at any time from Settings, with no penalty. We can
          terminate accounts for non-payment or violations of acceptable use
          after written notice. On termination you get a 90-day window to export
          your data; after that, primary storage is purged.
        </p>
      </Section>

      <Section heading="Liability">
        <p>
          Manthan is provided "as is" without warranties of any kind beyond what
          the law requires. To the maximum extent permitted, our total
          liability is capped at the fees paid to us in the 12 months before the
          claim arose.
        </p>
      </Section>

      <Section heading="Changes">
        <p>
          We may update these Terms. Material changes are emailed to admins at
          least 30 days before taking effect. Continued use after that date
          means acceptance.
        </p>
      </Section>

      <Section heading="Governing law">
        <p>
          These Terms are governed by the laws of the State of Delaware, USA,
          without regard to conflict-of-laws principles. Disputes go to courts
          located in New Castle County, Delaware.
        </p>
      </Section>

      <Section heading="Contact">
        <p>
          Legal questions:{" "}
          <a
            href="mailto:akash@miny-labs.com"
            style={{ color: "oklch(0.62 0.15 150)", textDecoration: "underline" }}
          >
            akash@miny-labs.com
          </a>
          .
        </p>
      </Section>
    </MarketingShell>
  );
}
