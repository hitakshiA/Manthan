/**
 * Help - quick reference + links to docs / support / community.
 *
 * Editorial form: print directory. No icon boxes for each link, no FAQ
 * cards-in-cards. Just a short directory of links and a typeset FAQ.
 */

import {
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";

const DIRECTORY = [
  { label: "Docs", value: "manthan.quest/docs", href: "https://manthan.quest/docs" },
  { label: "Support", value: "support@manthan.quest", href: "mailto:support@manthan.quest" },
  { label: "Community Slack", value: "manthan.quest/slack", href: "https://manthan.quest/slack" },
  { label: "Status page", value: "status.manthan.quest", href: "https://status.manthan.quest" },
];

const SHORTCUTS = [
  ["Open inbox", "G then I"],
  ["Open approvals", "G then A"],
  ["Open audit log", "G then U"],
  ["Approve case", "⌘ Enter"],
  ["Hold case", "⌘ ."],
  ["Focus chat", "/"],
];

const FAQ = [
  {
    q: "When does policy auto-resolve vs. wait for me?",
    a: "Each policy rule has a mode. AUTO fires the actions without a human (status flips straight to acting). SUGGEST surfaces the brief but waits for your nod. ESCALATE pings the on-call person and never fires automatically.",
  },
  {
    q: "Can I edit a drafted action before approving?",
    a: "Yes - pencil icon next to any drafted action card in the workspace. The actor honours your edits. Original LLM draft is preserved in the audit log.",
  },
  {
    q: "What's the difference between Active and Inbox?",
    a: "Inbox shows everything in flight (investigating + awaiting_approval + acting). Active is the same view, kept for explicitness. Done shows closed cases. Escalated shows cases that hit a hard error or were handed back by policy.",
  },
  {
    q: "How do I add a new source?",
    a: "Today: drop the credential env vars on the deployment and restart the API. v1.5 will land an OAuth flow on the Sources page.",
  },
];

export default function Help() {
  return (
    <PageBody width="narrow">
      <PageHeader
        eyebrow="Help"
        title="How to use Manthan"
        meta="Quick reference, FAQs, and where to reach a human."
      />

      <Section eyebrow="Directory">
        <dl
          className="divide-y border-t border-b"
          style={{ borderColor: "var(--color-rule-soft)" }}
        >
          {DIRECTORY.map((row) => (
            <a
              key={row.label}
              href={row.href}
              target="_blank"
              rel="noopener noreferrer"
              className="grid grid-cols-[1fr_auto] items-baseline gap-4 py-3 hover:bg-[var(--color-surface)] transition-colors"
              style={{ borderColor: "var(--color-rule-soft)" }}
            >
              <dt
                className="text-[13px]"
                style={{ color: "var(--color-ink-strong)" }}
              >
                {row.label}
              </dt>
              <dd
                className="text-[12.5px] tabular-nums"
                style={{ color: "var(--color-ink-muted)" }}
              >
                {row.value} ↗
              </dd>
            </a>
          ))}
        </dl>
      </Section>

      <Section
        eyebrow="Keyboard shortcuts"
        trailing="v1.1"
      >
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-2">
          {SHORTCUTS.map(([label, value]) => (
            <div
              key={label}
              className="flex items-baseline justify-between text-[12.5px]"
            >
              <dt style={{ color: "var(--color-ink-muted)" }}>{label}</dt>
              <dd
                className="font-mono text-[11px] tabular-nums"
                style={{ color: "var(--color-ink-faint)" }}
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>
        <p
          className="mt-3 text-[11px] italic font-display"
          style={{ color: "var(--color-ink-ghost)" }}
        >
          Listed here so you know what's planned. Shortcuts wire in v1.1.
        </p>
      </Section>

      <Section eyebrow="Frequently asked">
        <div className="space-y-5">
          {FAQ.map((item) => (
            <div key={item.q}>
              <div
                className="text-[13.5px]"
                style={{ color: "var(--color-ink-strong)" }}
              >
                {item.q}
              </div>
              <p
                className="mt-1 text-[12.5px] leading-relaxed max-w-prose"
                style={{ color: "var(--color-ink-muted)" }}
              >
                {item.a}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section eyebrow="Reach the team">
        <p
          className="text-[13px] leading-relaxed max-w-prose"
          style={{ color: "var(--color-ink-muted)" }}
        >
          For anything urgent - billing emergencies, prod incidents, demo-day
          support - email{" "}
          <a
            href="mailto:hello@manthan.quest"
            className="underline"
            style={{ color: "var(--color-ink-strong)" }}
          >
            hello@manthan.quest
          </a>
          . We respond within an hour. Real emails, not autoresponders.
        </p>
      </Section>
    </PageBody>
  );
}
