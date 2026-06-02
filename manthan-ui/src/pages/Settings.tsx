/**
 * Settings - the workspace control panel, editorial-memo direction.
 *
 * Only renders information that's actually real:
 *   - Workspace · team       → /api/me
 *
 * Everything else (billing, compliance certifications, policy
 * thresholds, notification channels) is honestly labelled "Demo mode" -
 * it's part of the production surface but isn't exposed in this build,
 * so we list it explicitly rather than render opaque settings rows
 * the operator can't actually change.
 *
 * Same typography ramp as the other editorial-memo pages: Spectral
 * italic title, Geist Mono uppercase labels, hairlines for separators.
 */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { getMe, type MeResponse } from "@/lib/api";

// ──────────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────────

export default function Settings() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [meError, setMeError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch((e: Error) => setMeError(e.message));
  }, []);

  return (
    <div
      className="h-full w-full overflow-y-auto"
      style={{ background: "var(--color-bg)" }}
    >
      <div className="mx-auto px-4 sm:px-6 py-6 sm:py-9" style={{ maxWidth: 1100 }}>
        <PageHeader />

        {meError && (
          <p
            className="mt-8 text-[14px] italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-danger)",
            }}
          >
            Couldn’t load /api/me: {meError}
          </p>
        )}

        <div className="mt-10 flex flex-col gap-9">
          <WorkspaceCard me={me} />
          <TeamCard me={me} />
          <DemoCard />
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// PageHeader - eyebrow + Spectral italic + DEMO MODE badge.
// ──────────────────────────────────────────────────────────────────────

function PageHeader() {
  return (
    <header className="flex flex-col gap-5">
      <div className="flex items-baseline gap-4 flex-wrap">
        <Eyebrow>Settings</Eyebrow>
        <DemoBadge />
      </div>
      <h1
        className="leading-[1.05]"
        style={{
          fontFamily: "Spectral, serif",
          fontSize: "clamp(34px, 3.4vw, 42px)",
          color: "var(--color-ink-strong)",
          letterSpacing: "-0.014em",
          fontStyle: "italic",
        }}
      >
        The workspace.
      </h1>
      <p
        className="leading-[1.55]"
        style={{
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
          fontSize: 15,
          color: "var(--color-ink-muted)",
          maxWidth: "62ch",
          letterSpacing: "-0.003em",
        }}
      >
        Identity and team. Billing, compliance, and notification
        channels are wired in production - this build runs them in
        demo mode.
      </p>
    </header>
  );
}

function DemoBadge() {
  return (
    <span
      className="inline-flex items-center gap-2 px-2.5 py-[3px]"
      style={{
        background: "var(--color-amber-soft)",
        border: "1px solid rgba(255,182,77,0.45)",
        borderRadius: 3,
        color: "var(--color-amber)",
        fontFamily: "Geist Mono, ui-monospace, monospace",
        fontSize: 10.5,
        letterSpacing: "0.20em",
        textTransform: "uppercase",
        fontWeight: 500,
      }}
    >
      <span
        aria-hidden
        className="inline-block"
        style={{
          width: 5,
          height: 5,
          borderRadius: 999,
          background: "var(--color-amber)",
        }}
      />
      Demo mode
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Editorial card shell - HeaderStrip + body. Mirrors the WorkspaceMemo /
// SourceProfileCard / RuleMemo pattern so all the inner pages use the
// same vocabulary.
// ──────────────────────────────────────────────────────────────────────

function Card({
  eyebrow,
  trailing,
  children,
}: {
  eyebrow: string;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <article
      style={{
        background: "var(--color-bg)",
        border: "1px solid var(--color-rule)",
        borderRadius: 6,
        color: "var(--color-ink-strong)",
        overflow: "hidden",
        boxShadow: "0 16px 40px rgba(0,0,0,0.30)",
      }}
    >
      <header
        className="flex items-center px-5 sm:px-7 lg:px-9 gap-4"
        style={{
          minHeight: 52,
          paddingTop: 14,
          paddingBottom: 14,
          borderBottom: "1px solid var(--color-rule-soft)",
        }}
      >
        <span
          className="font-mono text-[12.5px] uppercase tabular-nums"
          style={{
            color: "var(--color-ink-muted)",
            letterSpacing: "0.18em",
          }}
        >
          {eyebrow}
        </span>
        {trailing && <span className="ml-auto">{trailing}</span>}
      </header>
      <div className="px-5 sm:px-7 lg:px-9 py-6 lg:py-7">{children}</div>
    </article>
  );
}

function Row({
  label,
  value,
  hint,
  mono,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  mono?: boolean;
}) {
  return (
    <div
      className="grid items-baseline gap-2 sm:gap-6 py-3 grid-cols-1 sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)]"
      style={{
        borderBottom: "1px solid var(--color-rule-soft)",
      }}
    >
      <div>
        <div
          className="text-[12.5px] uppercase"
          style={{
            color: "var(--color-ink-muted)",
            letterSpacing: "0.18em",
            fontFamily: "Geist Mono, ui-monospace, monospace",
          }}
        >
          {label}
        </div>
        {hint && (
          <div
            className="text-[12.5px] mt-1.5 italic"
            style={{
              fontFamily: "Spectral, serif",
              color: "var(--color-ink-faint)",
              letterSpacing: "-0.002em",
              maxWidth: "42ch",
              lineHeight: 1.45,
            }}
          >
            {hint}
          </div>
        )}
      </div>
      <div
        className={
          mono
            ? "text-[13.5px] tabular-nums break-all"
            : "text-[15px] tabular-nums"
        }
        style={
          mono
            ? {
                color: "var(--color-ink-strong)",
                fontFamily: "Geist Mono, ui-monospace, monospace",
                letterSpacing: "0.01em",
              }
            : {
                color: "var(--color-ink-strong)",
                fontFamily: "Spectral, serif",
              }
        }
      >
        {value}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Cards - real data only.
// ──────────────────────────────────────────────────────────────────────

function WorkspaceCard({ me }: { me: MeResponse | null }) {
  const placeholder = me === null;
  return (
    <Card eyebrow="Workspace">
      <Row
        label="Name"
        value={placeholder ? "…" : me.org.name}
      />
      <Row
        label="Slug"
        value={placeholder ? "…" : me.org.slug}
        hint={placeholder ? undefined : `manthan.quest/${me.org.slug}`}
        mono
      />
      <Row
        label="Plan"
        value={placeholder ? "…" : me.org.plan.replace(/_/g, " ")}
      />
      <Row
        label="Members"
        value={
          placeholder
            ? "…"
            : `${me.org.member_count} ${me.org.member_count === 1 ? "member" : "members"}`
        }
      />
      <Row
        label="Workspace id"
        value={placeholder ? "…" : me.org.id}
        mono
      />
      {!placeholder && me.org.created_at && (
        <Row
          label="Created"
          value={new Date(me.org.created_at).toLocaleDateString(undefined, {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        />
      )}
    </Card>
  );
}

function TeamCard({ me }: { me: MeResponse | null }) {
  const placeholder = me === null;
  return (
    <Card
      eyebrow="Team"
      trailing={
        !placeholder ? (
          <span
            className="text-[11.5px] uppercase tabular-nums"
            style={{
              fontFamily: "Geist Mono, ui-monospace, monospace",
              color: "var(--color-ink-faint)",
              letterSpacing: "0.18em",
            }}
          >
            {me.org.member_count} {me.org.member_count === 1 ? "seat" : "seats"}
          </span>
        ) : null
      }
    >
      <Row
        label="Your name"
        value={placeholder ? "…" : me.member.display_name}
      />
      <Row
        label="Email"
        value={placeholder ? "…" : me.member.email}
        mono
      />
      <Row
        label="Role"
        value={placeholder ? "…" : me.member.role}
        hint={
          placeholder
            ? undefined
            : me.member.role === "admin"
              ? "Full workspace control - invite teammates, change policies, switch models."
              : "Member access - read cases, draft replies, request approvals."
        }
      />
      <Row
        label="Member id"
        value={placeholder ? "…" : me.member.id}
        mono
      />
    </Card>
  );
}

function DemoCard() {
  return (
    <Card
      eyebrow="Demo surfaces"
      trailing={<DemoBadge />}
    >
      <p
        className="text-[14px] leading-[1.62] max-w-[60ch]"
        style={{
          fontFamily: "Spectral, serif",
          color: "var(--color-ink)",
        }}
      >
        Billing, compliance, and notification channels are part of the
        production surface and aren’t exposed in this build. Listed here
        so contributors know what’s missing rather than hidden behind
        opaque settings rows.
      </p>
      <ul
        className="mt-5 flex flex-col"
        style={{ borderTop: "1px solid var(--color-rule-soft)" }}
      >
        {DEMO_ENTRIES.map((entry) => (
          <li
            key={entry.label}
            className="grid items-baseline gap-2 sm:gap-6 py-3 grid-cols-1 sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)]"
            style={{
              borderBottom: "1px solid var(--color-rule-soft)",
            }}
          >
            <span
              className="text-[12.5px] uppercase"
              style={{
                color: "var(--color-ink-muted)",
                letterSpacing: "0.18em",
                fontFamily: "Geist Mono, ui-monospace, monospace",
              }}
            >
              {entry.label}
            </span>
            <span
              className="text-[14px] italic"
              style={{
                fontFamily: "Spectral, serif",
                color: "var(--color-ink)",
                letterSpacing: "-0.002em",
                lineHeight: 1.5,
              }}
            >
              {entry.detail}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const DEMO_ENTRIES: { label: string; detail: string }[] = [
  {
    label: "Billing",
    detail:
      "Per-resolution metering, monthly cap, and card-on-file land in production. No charges fire in this build.",
  },
  {
    label: "Compliance",
    detail:
      "SOC 2 and EU AI Act certifications attach in production. The badges aren’t shown here on purpose.",
  },
  {
    label: "Notifications",
    detail:
      "Slack and email routing wire in once you’ve completed the source-connect flow in production.",
  },
  {
    label: "Self-host",
    detail:
      "Manthan ships a self-host bundle. Switching from hosted to self-host is a contract-level change, not a setting.",
  },
];

// ──────────────────────────────────────────────────────────────────────
// Eyebrow primitive - mirrors the other editorial-memo pages.
// ──────────────────────────────────────────────────────────────────────

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span
      className="text-[12.5px] uppercase"
      style={{
        color: "var(--color-ink-muted)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}
