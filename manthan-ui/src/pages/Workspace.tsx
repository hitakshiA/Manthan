/**
 * Workspace page - the unified case workspace, replacing the older
 * Dashboard + CaseDetail split. Matches the marketing showcase exactly.
 *
 * Data flow:
 *   - listCases() → cases sidebar (the inbox)
 *   - getCase(id) → case detail (TL;DR, evidence, actions, policy)
 *   - URL is /app or /app/case/:id; sidebar selection drives navigation
 *
 * Adapter functions convert raw API shapes to the WorkspaceCaseRow /
 * WorkspaceCaseDetail view models the workspace components expect.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  actionBody,
  actionExternalUrl,
  actionTarget,
  actionTitle,
  caseTypeLabel,
  formatAge,
  getCase,
  humanizeTrigger,
  listCaseActions,
  listCases,
  type ApiActionRow,
  type ApiCase,
  type CaseStatus,
} from "@/lib/api";
import { useCaseEvents } from "@/lib/useCaseEvents";
import { CaseWorkspace } from "@/components/app/workspace/CaseWorkspace";
import type {
  Tone,
  WorkspaceAction,
  WorkspaceCaseDetail,
  WorkspaceCaseRow,
} from "@/components/app/workspace/types";
import WorkspaceMemo, {
  citationUrl,
  type MemoAction,
  type MemoCaseData,
  type MemoFinding,
} from "./drafts/WorkspaceMemo";
import InvestigationMemo from "./drafts/InvestigationMemo";

// ──────────────────────────────────────────────────────────────────────
// Adapters
// ──────────────────────────────────────────────────────────────────────

function toneFromStatus(s: CaseStatus): Tone {
  if (s === "investigating") return "investigating";
  if (s === "awaiting_approval") return "awaiting";
  if (s === "acting") return "executing";
  if (s === "resolved") return "resolved";
  // errored, escalated - display as drafted (no other better mapping)
  return "drafted";
}

function caseRowFromApi(c: ApiCase, meEmail: string): WorkspaceCaseRow {
  // short_id is like "CASE-4821"; use the trailing digits as the num.
  const num = c.short_id.replace(/^CASE-/i, "") || c.short_id;
  return {
    num,
    customer: c.customer_ref ?? "-",
    type: caseTypeLabel(c.case_type),
    amount: (c.amount_minor ?? 0) / 100,
    status: toneFromStatus(c.status),
    ago: formatAge(c.created_at),
    drafts: 0, // backend doesn't expose drafted-action count yet; fill in v0.2
    owner: meEmail, // placeholder - backend doesn't expose assigned member email yet
    watching: true,
    caseId: c.id,
    triggerSurface: c.trigger_surface,
  };
}

function detailFromApi(c: ApiCase): WorkspaceCaseDetail {
  const num = c.short_id.replace(/^CASE-/i, "") || c.short_id;
  const amountLabel = c.amount_minor != null
    ? `$${(c.amount_minor / 100).toLocaleString("en-US", { maximumFractionDigits: 0 })}`
    : "the disputed amount";

  // Build a 1-paragraph TL;DR from the findings (or fallback prose).
  const findingText = (c.findings ?? []).map((f) => f.text).join(" ");
  const tldr =
    findingText.length > 0
      ? findingText
      : `Investigating ${c.customer_ref ?? "the customer"}. The agent is currently gathering evidence across connected sources.`;

  // Map findings → evidence rows. Old behaviour kept the first citation
  // per finding. The new Brief postmortem wants EVERY citation as its
  // own clickable chip, so we now flatten: one evidence row per citation.
  // Findings without any citation fall back to a single sniffed row so
  // they still render under "Postmortem in detail".
  const evidence: WorkspaceCaseDetail["evidence"] = [];
  const findings: WorkspaceCaseDetail["findings"] = [];

  (c.findings ?? []).forEach((f) => {
    const citationIndices: number[] = [];
    const cites = (f.citations ?? []).filter((x) => x);

    if (cites.length === 0) {
      // No structured citation - sniff a source from the finding text so
      // the chip isn't a dead "Finding N" placeholder.
      const sniffed = sniffSourceFromText(f.text);
      const idx = evidence.length;
      evidence.push({
        n: idx + 1,
        src: sniffed ?? "brief",
        record: sniffed ? `${sniffed} record` : `Finding ${f.seq}`,
        finding: f.text,
        url: null,
        table: null,
        ref: null,
        field: null,
      });
      citationIndices.push(idx);
    } else {
      cites.forEach((cite) => {
        const idx = evidence.length;
        evidence.push({
          n: idx + 1,
          src: cite.source,
          record: `${cite.ref}${cite.field ? ` · ${cite.field}` : ""}`,
          finding: f.text,
          url: cite.url ?? null,
          table: cite.table ?? null,
          ref: cite.ref ?? null,
          field: cite.field ?? null,
        });
        citationIndices.push(idx);
      });
    }

    findings.push({
      seq: f.seq,
      text: f.text,
      confidence: f.confidence ?? null,
      citationIndices,
    });
  });

  // Drafted actions get filled in from the real `actions` table by the
  // caller via `withActions()` below. Default empty so the function is
  // pure when no actions have been fetched yet.
  const actions: WorkspaceCaseDetail["actions"] = [];

  // Account snapshot from raw API shape - humanize all field values.
  const account: [string, React.ReactNode][] = [
    ["Customer", c.customer_ref ?? "-"],
    ["Status", humanizeStatus(c.status)],
    ["Trigger", humanizeTrigger(c.trigger_surface)],
    ["Amount", c.amount_minor != null ? amountLabel : "-"],
    ["Opened", formatAge(c.created_at) + " ago"],
  ];

  return {
    num,
    headlineVerb: c.case_type === "chargeback"
      ? <>vs. a {amountLabel} chargeback</>
      : c.case_type === "refund_request"
        ? <>requesting a {amountLabel} refund</>
        : c.case_type === "sla_credit"
          ? <>seeking an SLA credit</>
          : c.case_type === "failed_renewal"
            ? <>· renewal payment failed</>
            : <>· {caseTypeLabel(c.case_type).toLowerCase()}</>,
    routedNote:
      c.status === "awaiting_approval"
        ? "Routed to your queue"
        : c.status === "investigating"
          ? "Currently investigating"
          : "Under review",
    // Policy label: prefer the actual matched rule name; fall back to a
    // generic label until rules are wired into every case.
    policyFile: c.policy_match?.rule_name
      ? `${c.policy_match.rule_name} · ${c.policy_match.mode}`
      : "policy.yaml",
    tldr,
    // The brief's "real" TLDR (written by the agent in the brief_drafted
    // event). Falls back to undefined; the BriefPostmortem component
    // hides the lede if there isn't one yet.
    briefTldr: c.brief?.tldr ?? null,
    findings,
    caseId: c.id,
    account,
    evidence,
    actions,
    // Decision rationale block: surface the agent's actual rationale text
    // from the brief, then layer the policy match mode on top.
    policyReasoning: renderPolicyReasoning(c),
  };
}

function renderPolicyReasoning(c: ApiCase): React.ReactNode {
  const rationale = c.brief?.decision_rationale?.trim();
  const match = c.policy_match;
  const conf =
    c.brief?.decision_confidence ?? c.decision_confidence ?? null;
  return (
    <>
      {rationale ? (
        <span>{rationale}</span>
      ) : (
        <span>
          Held for your nod per policy. The agent gathered all relevant evidence
          and drafted resolution actions.
        </span>
      )}
      {(match || conf !== null) && (
        <span className="block mt-1 text-[11px] opacity-70">
          {match && (
            <>
              Policy <code>{match.rule_name}</code> matched ({match.mode}).{" "}
            </>
          )}
          {conf !== null && (
            <>
              Confidence: <code>{(conf * 100).toFixed(0)}%</code>.
            </>
          )}
        </span>
      )}
    </>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Merge real action rows into the synthesized detail's actions[] slot.
    Called after the detail has been built so the right column shows
    actual Stripe charge IDs, refund refs, email subjects, etc. */
function withActions(
  detail: WorkspaceCaseDetail,
  rows: ApiActionRow[],
): WorkspaceCaseDetail {
  if (!rows.length) return detail;
  return {
    ...detail,
    actions: rows.map((r) => ({
      id: r.id,
      kind: r.kind,
      source: sourceFromActionKind(r.kind),
      title: actionTitle(r),
      target: actionTarget(r),
      body: actionBody(r),
      status: r.status,
      externalRef: r.external_ref,
      errorMessage: r.error_message,
      externalUrl: actionExternalUrl(r),
      payload: r.payload,
    })),
  };
}

function humanizeStatus(s: string): string {
  return {
    investigating: "Investigating",
    awaiting_approval: "Awaiting your nod",
    acting: "Executing",
    resolved: "Resolved",
    errored: "Errored",
    escalated: "Escalated",
  }[s] ?? s.replace(/_/g, " ");
}

// humanizeTrigger now lives in @/lib/api so other pages (Approvals,
// Audit, future surface-filtered views) can reuse it.

const SOURCE_KEYWORDS: { token: string; source: string }[] = [
  { token: "stripe", source: "stripe" },
  { token: "salesforce", source: "salesforce" },
  { token: "hubspot", source: "hubspot" },
  { token: "intercom", source: "intercom" },
  { token: "zendesk", source: "zendesk" },
  { token: "notion", source: "notion" },
  { token: "slack", source: "slack" },
  { token: "posthog", source: "posthog" },
  { token: "sentry", source: "sentry" },
  { token: "datadog", source: "datadog" },
  { token: "pagerduty", source: "pagerduty" },
];

function sniffSourceFromText(t: string): string | null {
  const lower = (t || "").toLowerCase();
  for (const { token, source } of SOURCE_KEYWORDS) {
    if (lower.includes(token)) return source;
  }
  return null;
}

// ──────────────────────────────────────────────────────────────────────
// Memo adapters - convert the existing ApiCase / ApiActionRow shapes
// into the MemoCaseData / MemoFinding / MemoAction props the new
// editorial-memo views accept. Used only on the post-investigation
// stages (awaiting_approval, resolved, etc).
// ──────────────────────────────────────────────────────────────────────

function memoCaseFromApi(c: ApiCase): MemoCaseData {
  const disputedMinor = c.amount_minor ?? 0;
  const recommendedMinor = c.decision_amount_minor;
  const verb = caseTypeLabel(c.case_type).toLowerCase();
  // Spectral italic case-line. Matches the landing's "vs. an $8,400
  // chargeback over Custom Reports degradation" shape.
  let caseLine = `· ${verb}`;
  if (c.case_type === "chargeback") {
    caseLine = `vs. ${formatMoney(disputedMinor)} chargeback`;
  } else if (c.case_type === "refund_request") {
    caseLine = `requesting ${formatMoney(disputedMinor)} refund`;
  } else if (c.case_type === "sla_credit") {
    caseLine = `seeking an SLA credit`;
  } else if (c.case_type === "failed_renewal") {
    caseLine = `- renewal payment failed`;
  }

  // Recommended-amount Spectral subtitle ("partial credit · 2 of 30…")
  // is only meaningful when the agent's draft amount is a partial.
  let recommendedSubtitle: string | undefined = undefined;
  if (
    recommendedMinor != null &&
    disputedMinor > 0 &&
    recommendedMinor > 0 &&
    recommendedMinor < disputedMinor
  ) {
    const pct = Math.round((recommendedMinor / disputedMinor) * 100);
    recommendedSubtitle = `partial credit · ${pct}% of the disputed amount`;
  } else if (recommendedMinor === 0) {
    recommendedSubtitle = "fight - concede nothing";
  } else if (
    recommendedMinor != null &&
    recommendedMinor >= disputedMinor
  ) {
    recommendedSubtitle = "full refund";
  }

  const tldr =
    c.brief?.tldr?.trim() ||
    (c.findings ?? []).map((f) => f.text).join(" ").trim() ||
    `Investigating ${c.customer_ref ?? "the customer"}. The agent is gathering evidence across connected sources.`;

  return {
    shortId: c.short_id,
    customer: c.customer_ref ?? "-",
    caseLine,
    disputedAmount: formatMoney(disputedMinor),
    recommendedAmount:
      recommendedMinor != null ? formatMoney(recommendedMinor) : "-",
    recommendedSubtitle,
    status: c.status,
    policyMatched: c.policy_match?.rule_name ?? null,
    policyMode: c.policy_match?.mode ?? null,
    tldr,
  };
}

function memoFindingsFromApi(c: ApiCase): MemoFinding[] {
  return (c.findings ?? []).map((f) => {
    // Prefer the first structured citation. Fall back to sniffing the
    // source from the finding text so the byline isn't empty.
    const firstCite = (f.citations ?? []).find((cc) => cc?.source);
    const src = firstCite?.source ?? sniffSourceFromText(f.text) ?? "brief";
    const citeRef =
      firstCite?.ref ?? firstCite?.url ?? `finding/${f.seq}`;
    // Prefer the backend-built URL when present; fall back to the client
    // helper which knows the same templates. Falling through leaves
    // `url` null and the CiteChip renders as an inert span.
    const url =
      firstCite?.url ??
      citationUrl(firstCite?.source, firstCite?.table, firstCite?.ref);
    return { src, text: f.text, citeRef, url };
  });
}

function memoActionsFromApi(rows: ApiActionRow[]): MemoAction[] {
  return rows.map((r) => ({
    src: sourceFromActionKind(r.kind),
    title: actionTitle(r),
    target: actionTarget(r),
  }));
}

/** Build the full WorkspaceAction shape (with id/status/externalRef)
 *  the ApprovalCinematic needs to drive its per-action progression. */
function workspaceActionsFromApi(rows: ApiActionRow[]): WorkspaceAction[] {
  return rows.map((r) => ({
    id: r.id,
    kind: r.kind,
    source: sourceFromActionKind(r.kind),
    title: actionTitle(r),
    target: actionTarget(r),
    body: actionBody(r),
    status: r.status as WorkspaceAction["status"],
    externalRef: r.external_ref,
    errorMessage: r.error_message,
    externalUrl: actionExternalUrl(r),
    payload: r.payload,
  }));
}

function formatMoney(minor: number): string {
  return `$${(minor / 100).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/** Map an API action.kind to the source id whose logo we should show
 *  during the ApprovalCinematic. Falls back to "stripe" because most
 *  actions land there; the cinematic still renders fine without an icon. */
function sourceFromActionKind(kind: string): string {
  if (!kind) return "stripe";
  const k = kind.toLowerCase();
  if (k.startsWith("stripe_")) return "stripe";
  if (k.startsWith("notion_")) return "notion";
  if (k.startsWith("slack_")) return "slack";
  if (k.startsWith("linear_")) return "linear";
  if (k.startsWith("hubspot_")) return "hubspot";
  if (k.startsWith("zendesk_")) return "zendesk";
  if (k.startsWith("intercom_")) return "intercom";
  if (k.startsWith("salesforce_")) return "salesforce";
  if (k === "customer_email" || k.startsWith("email_")) return "resend";
  return "stripe";
}

// ──────────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────────

export default function Workspace() {
  const params = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const [cases, setCases] = useState<WorkspaceCaseRow[] | null>(null);
  const [detailByNum, setDetailByNum] = useState<Record<string, WorkspaceCaseDetail>>({});
  // Raw API state kept alongside the formatted detail so the memo
  // views (InvestigationMemo / WorkspaceMemo) can render from the same
  // fetch round-trip. Keyed by case id (UUID) to dodge short_id
  // collisions.
  const [rawCaseById, setRawCaseById] = useState<Record<string, ApiCase>>({});
  const [rawActionsById, setRawActionsById] = useState<
    Record<string, ApiActionRow[]>
  >({});
  const [error, setError] = useState<string | null>(null);
  const meEmail = "you@miny-labs.com"; // TODO: from Clerk session

  // 1. Load the inbox.
  useEffect(() => {
    let cancelled = false;
    listCases({ limit: 50 })
      .then((r) => {
        if (cancelled) return;
        const rows = r.cases.map((c) => caseRowFromApi(c, meEmail));
        setCases(rows);

        // If no case in URL, route to the first one.
        if (!params.id && rows.length > 0) {
          navigate(`/app/case/${r.cases[0].id}`, { replace: true });
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [meEmail, navigate, params.id]);

  // 2. Load the active case detail when the URL changes OR when the agent
  //    crosses milestones (brief drafted, action executed, etc).
  const refetchDetail = useCallback(async () => {
    if (!params.id || !cases) return;
    const row = cases.find((c) => c.caseId === params.id);
    if (!row) return;
    try {
      // Pull case + actions in parallel so the right column always reflects
      // the live actions table (not a synthesized placeholder).
      const [c, actionsList] = await Promise.all([
        getCase(params.id),
        listCaseActions(params.id).catch(() => [] as ApiActionRow[]),
      ]);
      setDetailByNum((prev) => ({
        ...prev,
        [row.num]: withActions(detailFromApi(c), actionsList),
      }));
      setRawCaseById((prev) => ({ ...prev, [c.id]: c }));
      setRawActionsById((prev) => ({ ...prev, [c.id]: actionsList }));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [params.id, cases]);

  useEffect(() => {
    if (!params.id || !cases) return;
    const row = cases.find((c) => c.caseId === params.id);
    if (!row) return;
    if (detailByNum[row.num]) return; // first-load cache
    refetchDetail();
  }, [params.id, cases, detailByNum, refetchDetail]);

  // Live-event subscription drives auto-refresh on key milestones.
  const { events, isLive, isComplete } = useCaseEvents(params.id);
  useEffect(() => {
    if (!events.length) return;
    const last = events[events.length - 1];
    if (
      ["brief_drafted", "case_closed", "action_executed", "action_failed", "human_approved"]
        .includes(last.type)
    ) {
      refetchDetail();
      // Also refresh the inbox so status + decision propagate.
      listCases({ limit: 50 })
        .then((r) => setCases(r.cases.map((c) => caseRowFromApi(c, meEmail))))
        .catch(() => {});
    }
  }, [events, refetchDetail, meEmail]);

  const activeCaseNum = useMemo(() => {
    if (!cases) return "";
    if (params.id) {
      const row = cases.find((c) => c.caseId === params.id);
      if (row) return row.num;
    }
    return cases[0]?.num ?? "";
  }, [cases, params.id]);

  const handleActiveCaseChange = (num: string) => {
    const row = cases?.find((c) => c.num === num);
    if (row) navigate(`/app/case/${row.caseId}`);
  };

  if (error) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-bg)", color: "var(--color-danger)" }}
      >
        <div className="text-[12.5px] max-w-md">
          API error: {error}
          <div
            className="mt-2 text-[11px]"
            style={{ color: "var(--color-ink-faint)" }}
          >
            Backend expected at <code>{import.meta.env.VITE_MANTHAN_API_URL ?? "http://127.0.0.1:8765"}</code>. Confirm the API is running.
          </div>
        </div>
      </div>
    );
  }

  if (!cases) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-bg)", color: "var(--color-ink-faint)" }}
      >
        <div className="text-[12.5px]">Loading workspace…</div>
      </div>
    );
  }

  // Editorial-memo direction: render InvestigationMemo while the agent
  // is in flight, WorkspaceMemo for the brief / resolved phases. The
  // legacy CaseWorkspace stays as a fallback for the (rare) "case row
  // exists but we haven't fetched the detail yet" race so the operator
  // never sees a blank screen.
  const rawCase = params.id ? rawCaseById[params.id] : undefined;
  const rawActions = params.id ? rawActionsById[params.id] : undefined;

  if (params.id && rawCase) {
    const status = rawCase.status;
    return (
      <div className="h-[calc(100vh-3.5rem)]">
        {status === "investigating" ? (
          // InvestigationMemo reads :id from useParams and subscribes
          // to its own SSE stream - we don't need to thread anything
          // through; the existing useCaseEvents above + the one inside
          // the memo share the same caseId and Manthan's server-side
          // dedupes the subscription.
          <InvestigationMemo />
        ) : (
          <WorkspaceMemo
            caseId={params.id}
            caseData={memoCaseFromApi(rawCase)}
            findings={memoFindingsFromApi(rawCase)}
            actions={memoActionsFromApi(rawActions ?? [])}
            workspaceActions={workspaceActionsFromApi(rawActions ?? [])}
            onActionsExecuted={refetchDetail}
          />
        )}
      </div>
    );
  }

  // Fallback: legacy three-column workspace while we wait for the first
  // detail fetch to land (or if status is unrecognised). Keeps the UI
  // responsive instead of showing a blank screen.
  return (
    <div className="h-[calc(100vh-3.5rem)]">
      <CaseWorkspace
        cases={cases}
        detailByNum={detailByNum}
        activeCaseNum={activeCaseNum}
        onActiveCaseChange={handleActiveCaseChange}
        meOwner={meEmail}
        activeCaseId={params.id}
        streamedEvents={events}
        isLive={isLive && !isComplete}
        isComplete={isComplete}
      />
    </div>
  );
}
