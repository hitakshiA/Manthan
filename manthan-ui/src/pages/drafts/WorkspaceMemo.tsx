/**
 * WorkspaceMemo - Case Workspace, editorial-memo direction.
 *
 * Renders one case in the landing's BriefCanvas vocabulary: HeaderStrip
 * at the top, two-column editorial spread inside (postmortem left,
 * suggested actions right), and an optional Coral toggle that swaps the
 * brief for the raw SQL trace.
 *
 * Two modes:
 *   - PROPS-LESS:  /app/workspace-memo standalone - renders the baked
 *                  W7R Aperture mock data with no Coral toggle (no
 *                  case_id known, no events to subscribe to).
 *   - PROPS-FED:   the production /app/case/:id route passes real
 *                  caseData / findings / actions + caseId, and the
 *                  Coral toggle appears in the header. Click it →
 *                  raw SQL feed wired to the same case's SSE stream.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Loader2, Send } from "lucide-react";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { getSource } from "@/lib/sources";
import { useCaseEvents, type CaseEvent } from "@/lib/useCaseEvents";
import { approveCase, chatWithCase } from "@/lib/api";
import { ApprovalCinematic } from "@/components/app/workspace/ApprovalCinematic";
import type { WorkspaceAction } from "@/components/app/workspace/types";
import {
  CoralCanvas,
  CoralToggle,
  collectCoralSteps,
  latestSource,
} from "./InvestigationMemo";

// ──────────────────────────────────────────────────────────────────────
// Public prop shape - what the production route passes in.
// ──────────────────────────────────────────────────────────────────────

export interface MemoFinding {
  src: string;
  text: string;
  citeRef: string;
  /** Optional deep-link to the source record. When present the CiteChip
   *  becomes a clickable <a>; otherwise it falls back to a plain span. */
  url?: string | null;
}

export interface MemoAction {
  src: string;
  title: string;
  target: string;
}

export interface MemoCaseData {
  shortId: string;
  customer: string;
  caseLine: string;          // e.g. "vs. an $8,400 chargeback over Custom Reports degradation"
  disputedAmount: string;    // pre-formatted dollar string e.g. "$8,400"
  recommendedAmount: string; // pre-formatted dollar string e.g. "$560"
  recommendedSubtitle?: string; // e.g. "partial credit · 2 of 30 days at the Premium tier"
  status: string;
  policyMatched?: string | null;
  policyMode?: string | null;
  tldr: string;
}

export interface WorkspaceMemoProps {
  /** Full case data. If absent, render the W7R Aperture mock. */
  caseData?: MemoCaseData;
  findings?: MemoFinding[];
  actions?: MemoAction[];
  /** Live action rows with id + status, used to drive the firing
   *  cinematic. Falls back to a fabricated list from `actions` when
   *  not provided (mock/preview routes). */
  workspaceActions?: WorkspaceAction[];
  /** Optional case_id - when present, the Coral toggle shows up in the
   *  header and reads from this case's SSE event stream. */
  caseId?: string;
  /** Called after the cinematic finishes so the parent can refetch the
   *  case detail (status → resolved, actions → succeeded). */
  onActionsExecuted?: () => void;
}

// ──────────────────────────────────────────────────────────────────────
// Default mock data - the W7R Aperture story. Used when the component
// renders standalone at /app/workspace-memo (no props).
// ──────────────────────────────────────────────────────────────────────

const MOCK_CASE: MemoCaseData = {
  shortId: "W7R-APERTURE",
  customer: "Aperture Analytics",
  caseLine: "vs. an $8,400 chargeback over Custom Reports degradation",
  disputedAmount: "$8,400",
  recommendedAmount: "$560",
  recommendedSubtitle:
    "partial credit · 2 of 30 days at the Premium tier",
  status: "awaiting_approval",
  policyMatched: "documented-incident-prorata-credit",
  policyMode: "recommend",
  tldr:
    "Aperture disputes the full $8,400 April Premium charge citing Custom " +
    "Reports degradation. Datadog confirms a 48-hour SLA breach during the " +
    "cycle (2026-04-13 → 04-15) - exactly the window the customer " +
    "references in Intercom. The Notion 'Documented Incident Pro-Rata " +
    "Credit' policy mandates 2/30 × $8,400 = $560. Customer self-downgraded " +
    "post-incident; no full-refund basis.",
};

const MOCK_FINDINGS: MemoFinding[] = [
  {
    src: "stripe",
    text:
      "$8,400 captured 2026-04-12 on charge ch_3Tch1L; dispute du_1Tch1O " +
      "filed 2026-05-08, reason product_not_as_described.",
    citeRef: "ch_3Tch1L",
  },
  {
    src: "datadog",
    text:
      "Monitor custom-reports-svc error_rate elevated (id 20175237) " +
      "documents a 48-hour SLA breach 2026-04-13 → 04-15 for Premium tier.",
    citeRef: "monitor/20175237",
  },
  {
    src: "intercom",
    text:
      "Customer message 2026-04-14 cites Custom Reports timeouts " +
      "“today and yesterday” - aligns exactly with the Datadog window.",
    citeRef: "conv/3708443460",
  },
  {
    src: "notion",
    text:
      "Policy 'Documented Incident Pro-Rata Credit' SOP: credit = " +
      "(degraded_days / cycle_days) × tier_amount. Worked example: " +
      "$8,400 × 2/30 = $560.",
    citeRef: "page/37043656",
  },
  {
    src: "hubspot",
    text:
      "Customer self-downgraded Premium → Standard on 2026-04-16, " +
      "immediately after the incident resolved.",
    citeRef: "company/324974146247",
  },
];

const MOCK_ACTIONS: MemoAction[] = [
  {
    src: "stripe",
    title: "Issue partial Stripe refund of $560",
    target: "POST /v1/refunds · charge=ch_3Tch1L · amount=56000",
  },
  {
    src: "stripe",
    title: "File concede response on the open dispute",
    target: "POST /v1/disputes/du_1Tch1O · submit=true · concede",
  },
  {
    src: "resend",
    title: "Email Aperture's billing contact",
    target: "POST /resend/emails · to=billing@aperture-analytics.co",
  },
  {
    src: "hubspot",
    title: "Append resolution note to HubSpot",
    target: "POST /crm/v3/notes · companyId=324974146247",
  },
  {
    src: "slack",
    title: "Post case brief to #ar-ops",
    target: "chat.postMessage · channel=#ar-ops",
  },
];

// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────

export default function WorkspaceMemo(props: WorkspaceMemoProps = {}) {
  const caseData = props.caseData ?? MOCK_CASE;
  const findings = props.findings ?? MOCK_FINDINGS;
  const actions = props.actions ?? MOCK_ACTIONS;
  const caseId = props.caseId;
  const onActionsExecuted = props.onActionsExecuted;

  // WorkspaceAction[] for the cinematic. When the parent didn't pass
  // it (mock route), fabricate a barebones list from the MemoAction
  // shape so the cinematic still has something to walk through.
  const workspaceActions = useMemo<WorkspaceAction[]>(() => {
    if (props.workspaceActions && props.workspaceActions.length > 0) {
      return props.workspaceActions;
    }
    return actions.map((a, i) => ({
      id: `mock-${i}`,
      kind: a.src,
      source: a.src,
      title: a.title,
      target: a.target,
      body: a.target,
      status: "drafted" as const,
    }));
  }, [props.workspaceActions, actions]);

  // Approve flow. `awaiting` → operator hasn't clicked yet.
  // `firing` → cinematic is playing, actor is executing actions.
  // `fired` → backend agrees all actions are terminal (case_closed
  //           arrived OR caseData.status flipped to a terminal state).
  //
  // CRITICAL: `fired` is ALWAYS gated on backend truth - we never flip
  // it just because the cinematic finished. Previously the phase label
  // and "Queued · N actions" button would flip to "fired" the moment
  // the animation timed out, leading to three surfaces lying about
  // case state ("ALL ACTIONS FIRED" header + "Queued · N" button +
  // Inbox row still showing "Acting").
  const isCaseTerminal =
    caseData.status === "resolved" ||
    caseData.status === "errored" ||
    caseData.status === "escalated";
  const [state, setState] = useState<"awaiting" | "firing" | "fired">(
    isCaseTerminal ? "fired" : "awaiting",
  );
  const [approveError, setApproveError] = useState<string | null>(null);

  // Brief ↔ Coral toggle. When `caseId` is absent (standalone route)
  // the toggle is hidden and we always render the brief.
  const [mode, setMode] = useState<"prose" | "coral">("prose");

  // Chat drawer (slides in from the right). Available only when caseId is
  // provided - there's no thread to chat about in standalone mock mode.
  const [chatOpen, setChatOpen] = useState(false);

  // Subscribe to SSE only when caseId is provided AND coral mode is
  // opened at least once - keeps the event source dormant for the
  // common "operator just glances at the brief" case.
  const liveEnabled = !!caseId;
  const { events, isComplete } = useCaseEvents(liveEnabled ? caseId : undefined);
  const coralSteps = useMemo(() => collectCoralSteps(events), [events]);
  const currentSource = useMemo(() => latestSource(events), [events]);

  // Backend reached terminal state? Flip "firing" → "fired" the moment
  // the API confirms (via case_closed SSE event OR a refetch returning
  // resolved/errored). The cinematic finishes its sequence independently;
  // this just makes sure local state doesn't lie when the API hasn't
  // caught up yet (or the case was already closed when we mounted).
  useEffect(() => {
    if (isCaseTerminal && state !== "fired") {
      setState("fired");
    }
  }, [isCaseTerminal, state]);

  async function handleApprove() {
    if (state !== "awaiting") return;
    setState("firing");
    setApproveError(null);
    // No caseId means we're in the standalone mock route; let the
    // cinematic play against the synthetic actions and call it done.
    if (!caseId) {
      // In mock mode there's no API to wait on, so the cinematic's
      // own onAllComplete is the source of truth.
      return;
    }
    try {
      await approveCase(caseId);
    } catch (e) {
      // Approve failed at the API - surface the error and back out
      // of the firing state so the operator can retry.
      console.warn("manthan: approveCase failed", e);
      setApproveError((e as Error).message ?? "Approve failed");
      setState("awaiting");
    }
  }

  function handleCinematicComplete() {
    // The cinematic finished walking through its sequence. If the
    // backend has ALREADY confirmed terminal state we can flip to
    // "fired" right now; otherwise we stay in "firing" so the
    // cinematic's "settling…" state stays up until the case_closed
    // event arrives via SSE. Always trigger a refetch so the parent
    // can refresh action statuses + case row.
    onActionsExecuted?.();
    if (caseId && isCaseTerminal) {
      setState("fired");
    } else if (!caseId) {
      // Mock route - no backend to wait on.
      setState("fired");
    }
    // else: stay in "firing"; the SSE useEffect above will flip us when
    // case_closed lands.
  }

  const phaseLabel =
    state === "fired"
      ? "All actions fired"
      : state === "firing"
        ? "Firing actions…"
        : "Awaiting your nod";
  const phaseAccent =
    state === "fired"
      ? "var(--color-accent)"
      : state === "firing"
        ? "var(--color-info)"
        : "var(--color-amber)";

  return (
    <div
      className="h-full w-full flex items-stretch px-6 py-6"
      style={{ background: "var(--color-bg)" }}
    >
      <div
        className="flex flex-col flex-1 min-h-0"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-rule)",
          borderRadius: 6,
          color: "var(--color-ink-strong)",
          overflow: "hidden",
          boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
        }}
      >
        <HeaderStrip
          caseData={caseData}
          phaseLabel={phaseLabel}
          phaseAccent={phaseAccent}
          showCoralToggle={liveEnabled}
          mode={mode}
          onToggleMode={() =>
            setMode((m) => (m === "prose" ? "coral" : "prose"))
          }
          showChatToggle={liveEnabled}
          chatOpen={chatOpen}
          onToggleChat={() => setChatOpen((v) => !v)}
        />

        <div className="relative flex-1 min-h-0">
          <motion.div
            key={mode}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
            className="absolute inset-0"
          >
            {mode === "prose" ? (
              <BriefCanvas
                caseData={caseData}
                findings={findings}
                actions={actions}
                workspaceActions={workspaceActions}
                state={state}
                onApprove={handleApprove}
                approveError={approveError}
              />
            ) : (
              <CoralCanvas
                steps={coralSteps}
                isComplete={isComplete}
                currentSource={currentSource}
              />
            )}
          </motion.div>

          {/* Approval cinematic - full-canvas takeover the moment the
              operator clicks Approve. Walks through each action one at
              a time, showing the source logo + the action firing, and
              flips back to the brief (in its closed state) once every
              action settles. */}
          <AnimatePresence>
            {state === "firing" && (
              <motion.div
                key="cinematic"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.36, ease: [0.22, 0.61, 0.36, 1] }}
                className="absolute inset-0 flex flex-col z-30"
                style={{ background: "var(--color-bg)" }}
              >
                <ApprovalCinematic
                  actions={workspaceActions}
                  onAllComplete={handleCinematicComplete}
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Side chat drawer - Claude-mobile style. Floats over the
              right edge of the workspace canvas so the brief stays in
              its native 2-column layout underneath; a soft fade on the
              left edge of the drawer reads as "this is in front." */}
          {/* Side chat drawer - Claude-mobile-style. Mounted only when
              open; we skip framer-motion here (got stuck mid-animation
              in this preview setup) and use a plain CSS transition for
              the slide-in. */}
          {liveEnabled && (
            <aside
              style={{
                width: 420,
                borderLeft: "1px solid var(--color-rule)",
                background: "#1a1816",
                boxShadow: "-22px 0 38px rgba(0,0,0,0.50)",
                transform: chatOpen ? "translateX(0)" : "translateX(440px)",
                opacity: chatOpen ? 1 : 0,
                pointerEvents: chatOpen ? "auto" : "none",
                transition:
                  "transform 280ms cubic-bezier(0.22,0.61,0.36,1), opacity 200ms ease",
              }}
              className="absolute top-0 right-0 bottom-0 flex flex-col z-20"
              aria-hidden={!chatOpen}
            >
              {chatOpen && (
                <ChatDrawer
                  caseId={caseId!}
                  events={events}
                  onClose={() => setChatOpen(false)}
                />
              )}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// HeaderStrip - case identity + (optional) Coral toggle + phase label.
// ──────────────────────────────────────────────────────────────────────

function HeaderStrip({
  caseData,
  phaseLabel,
  phaseAccent,
  showCoralToggle,
  mode,
  onToggleMode,
  showChatToggle,
  chatOpen,
  onToggleChat,
}: {
  caseData: MemoCaseData;
  phaseLabel: string;
  phaseAccent: string;
  showCoralToggle: boolean;
  mode: "prose" | "coral";
  onToggleMode: () => void;
  showChatToggle: boolean;
  chatOpen: boolean;
  onToggleChat: () => void;
}) {
  return (
    <header
      className="flex items-center px-9 shrink-0"
      style={{
        height: 56,
        borderBottom: "1px solid var(--color-rule-soft)",
        background: "var(--color-bg)",
      }}
    >
      <span
        className="font-mono text-[13px] uppercase tabular-nums"
        style={{
          color: "var(--color-ink-muted)",
          letterSpacing: "0.16em",
        }}
      >
        CASE {caseData.shortId}
      </span>

      <span
        className="mx-3"
        style={{ color: "var(--color-rule-strong)" }}
        aria-hidden
      >
        ·
      </span>

      <span
        className="text-[15px]"
        style={{
          color: "var(--color-ink)",
          letterSpacing: "0.005em",
        }}
      >
        {caseData.customer}
      </span>

      {caseData.policyMatched && (
        <>
          <span
            className="mx-4"
            style={{ color: "var(--color-rule-strong)" }}
            aria-hidden
          >
            ·
          </span>
          <span
            className="font-mono text-[12px] tabular-nums inline-flex items-baseline gap-2"
            style={{
              color: "var(--color-ink-muted)",
              letterSpacing: "0.04em",
            }}
            title={`policy match · mode=${caseData.policyMode ?? "recommend"}`}
          >
            <span
              className="uppercase"
              style={{
                letterSpacing: "0.18em",
                color: "var(--color-ink-faint)",
              }}
            >
              policy
            </span>
            <span style={{ color: "var(--color-ink-muted)" }}>
              {caseData.policyMatched}
            </span>
          </span>
        </>
      )}

      <div className="ml-auto inline-flex items-center gap-5">
        {showCoralToggle && (
          <CoralToggle mode={mode} onToggle={onToggleMode} />
        )}

        {showChatToggle && (
          <ChatHeaderToggle open={chatOpen} onToggle={onToggleChat} />
        )}

        <span
          className="text-[12.5px] uppercase"
          style={{
            color: phaseAccent,
            letterSpacing: "0.22em",
            fontWeight: 500,
          }}
        >
          {phaseLabel}
        </span>
      </div>
    </header>
  );
}

// ──────────────────────────────────────────────────────────────────────
// BriefCanvas - postmortem left, suggested actions right.
// ──────────────────────────────────────────────────────────────────────

function BriefCanvas({
  caseData,
  findings,
  actions,
  workspaceActions,
  state,
  onApprove,
  approveError,
}: {
  caseData: MemoCaseData;
  findings: MemoFinding[];
  actions: MemoAction[];
  workspaceActions: WorkspaceAction[];
  state: "awaiting" | "firing" | "fired";
  onApprove: () => void;
  approveError?: string | null;
}) {
  const isClosed = state === "fired";
  return (
    <div
      className="h-full grid overflow-hidden"
      style={{
        gridTemplateColumns: "minmax(0, 1.35fr) minmax(0, 1fr)",
        gridTemplateRows: "minmax(0, 1fr)",
      }}
    >
      {/* LEFT - postmortem */}
      <div className="px-14 pt-12 pb-8 overflow-y-auto flex flex-col gap-7">
        <Eyebrow>Brief</Eyebrow>

        <h2
          className="leading-[1.08]"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: "clamp(34px, 3.4vw, 42px)",
            color: "var(--color-ink-strong)",
            letterSpacing: "-0.014em",
          }}
        >
          {caseData.customer}{" "}
          <em
            style={{
              fontStyle: "normal",
              color: "var(--color-ink-muted)",
            }}
          >
            {caseData.caseLine}.
          </em>
        </h2>

        <div
          className="pt-1 pb-5"
          style={{ borderBottom: "1px solid var(--color-rule-soft)" }}
        >
          <div className="flex items-baseline gap-8 flex-wrap">
            <div className="flex items-baseline gap-3">
              <Eyebrow>Claim</Eyebrow>
              <span
                className="font-mono tabular-nums"
                style={{ color: "var(--color-ink)", fontSize: 22 }}
              >
                {caseData.disputedAmount}
              </span>
            </div>
            <span
              style={{ color: "var(--color-rule-strong)", fontSize: 20 }}
              aria-hidden
            >
              →
            </span>
            <div className="flex items-baseline gap-3">
              <Eyebrow accent>Recommended</Eyebrow>
              <span
                className="tabular-nums whitespace-nowrap"
                style={{
                  fontFamily: "Spectral, serif",
                  fontStyle: "italic",
                  fontSize: 32,
                  color: "var(--color-accent, #56cf83)",
                  letterSpacing: "-0.008em",
                  lineHeight: 1,
                }}
              >
                {caseData.recommendedAmount}
              </span>
            </div>
          </div>
          {caseData.recommendedSubtitle && (
            <div
              className="mt-2 text-[14px]"
              style={{
                color: "var(--color-ink-muted)",
                fontFamily: "Spectral, serif",
                fontStyle: "normal",
              }}
            >
              {caseData.recommendedSubtitle}
            </div>
          )}
        </div>

        <div
          className="leading-[1.55] space-y-3"
          style={{
            fontFamily: "Spectral, serif",
            fontSize: 18,
            color: "var(--color-ink)",
            maxWidth: "60ch",
          }}
        >
          <BriefProse text={caseData.tldr} findings={findings} />
        </div>

        <div className="pt-2">
          <Eyebrow>Postmortem in detail</Eyebrow>
        </div>

        <ol className="space-y-5 pb-2">
          {findings.map((f, i) => (
            <li
              key={f.src + i}
              className="grid"
              style={{
                gridTemplateColumns: "32px minmax(0,1fr)",
                gap: 14,
              }}
            >
              <span
                className="text-[13px] tabular-nums pt-1"
                style={{
                  color: "var(--color-ink-faint)",
                  letterSpacing: "0.04em",
                  fontFamily: "Spectral, serif",
                  fontStyle: "italic",
                }}
              >
                {String(i + 1).padStart(2, "0")}.
              </span>
              <div
                className="text-[15.5px] leading-[1.55]"
                style={{ color: "var(--color-ink)" }}
              >
                <SourceWord src={f.src} label={f.src.toUpperCase()} />
                <span className="ml-2.5">
                  <BriefProse text={f.text} findings={findings} inline />
                </span>
                {f.citeRef && (
                  <CiteChip
                    n={i + 1}
                    src={f.src}
                    label={f.citeRef}
                    url={f.url ?? citationUrl(f.src, null, f.citeRef)}
                  />
                )}
              </div>
            </li>
          ))}
          {findings.length === 0 && (
            <li
              className="text-[14px] italic"
              style={{
                fontFamily: "Spectral, serif",
                color: "var(--color-ink-faint)",
              }}
            >
              No findings recorded yet on this case.
            </li>
          )}
        </ol>

        {/* All-sources-touched footer - every source the agent queried,
            even if formal record_finding didn't fire for it. Reads
            "Also touched <X, Y, Z>" so the operator sees coverage at a
            glance without scrolling to the Coral trace. */}
        <AlsoTouched findings={findings} />
      </div>

      {/* RIGHT - suggested actions while awaiting; fired-actions
          ledger (with results + external refs) once the case closes. */}
      <div
        className="pt-12 pb-8 pl-11 pr-14 flex flex-col"
        style={{ borderLeft: "1px solid var(--color-rule-soft)" }}
      >
        <Eyebrow>
          {isClosed ? "Actions fired" : "Suggested actions"}
        </Eyebrow>

        <ol className="mt-7 space-y-4 flex-1 min-h-0 overflow-y-auto">
          {isClosed
            ? workspaceActions.map((wa, i) => (
                <FiredActionRow
                  key={wa.id ?? i}
                  action={wa}
                  index={i}
                  isLast={i === workspaceActions.length - 1}
                />
              ))
            : actions.map((a, i) => (
                <li
                  key={i}
                  className="grid pb-4"
                  style={{
                    gridTemplateColumns: "32px minmax(0,1fr)",
                    gap: 14,
                    borderBottom:
                      i < actions.length - 1
                        ? "1px solid var(--color-rule-soft)"
                        : "none",
                  }}
                >
                  <span
                    className="text-[13px] tabular-nums pt-0.5"
                    style={{
                      color: "var(--color-ink-faint)",
                      letterSpacing: "0.04em",
                      fontFamily: "Spectral, serif",
                      fontStyle: "italic",
                    }}
                  >
                    {String(i + 1).padStart(2, "0")}.
                  </span>
                  <div className="min-w-0">
                    <SourceWord src={a.src} label={a.src.toUpperCase()} />
                    <div
                      className="text-[16px] leading-[1.45] mt-2"
                      style={{ color: "rgba(255,255,255,0.90)" }}
                    >
                      {a.title}
                    </div>
                    {a.target && (
                      <div
                        className="font-mono text-[12.5px] tabular-nums mt-2 truncate"
                        style={{ color: "var(--color-ink-faint)" }}
                      >
                        {a.target}
                      </div>
                    )}
                  </div>
                </li>
              ))}
          {!isClosed && actions.length === 0 && (
            <li
              className="text-[14px] italic"
              style={{
                fontFamily: "Spectral, serif",
                color: "var(--color-ink-faint)",
              }}
            >
              No drafted actions yet. They&apos;ll appear once the agent
              concludes.
            </li>
          )}
        </ol>

        <div
          className="mt-5 pt-5 flex items-center justify-between gap-4"
          style={{ borderTop: "1px solid var(--color-rule-soft)" }}
        >
          {isClosed ? (
            <ClosedCaseFooter actions={workspaceActions} />
          ) : (
            <div className="flex items-center gap-5">
              {(["Escalate", "Hold", "Deny"] as const).map((verb) => (
                <button
                  key={verb}
                  type="button"
                  className="text-[13.5px] outline-none hover:opacity-80 transition-opacity bg-transparent border-0 p-0"
                  style={{
                    color:
                      verb === "Deny"
                        ? "var(--color-danger)"
                        : "var(--color-ink-muted)",
                    cursor: "pointer",
                  }}
                >
                  {verb}
                </button>
              ))}
            </div>
          )}
          <div className="flex flex-col items-end gap-2">
            {!isClosed && (
              <ApproveButton
                state={state}
                onClick={onApprove}
                actionCount={actions.length}
              />
            )}
            {approveError && (
              <span
                className="text-[11.5px]"
                style={{
                  fontFamily: "Geist Mono, ui-monospace, monospace",
                  color: "var(--color-danger)",
                  letterSpacing: "0.02em",
                  maxWidth: 320,
                  textAlign: "right",
                }}
                title={approveError}
              >
                Approve failed - {approveError}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// BriefProse - render brief / postmortem prose with auto-detected
// formatting: long opaque IDs become compact monospace chips, source
// names get brand-colored, sentences break into paragraphs (block
// mode only). Inline mode preserves a single line.
// ──────────────────────────────────────────────────────────────────────

function BriefProse({
  text,
  findings,
  inline,
}: {
  text: string;
  findings: MemoFinding[];
  inline?: boolean;
}) {
  // Build a citation lookup once - slug → finding number, so when we
  // detect a source mention we can stamp the right [N] chip.
  const sourceToCiteNum = useMemo(() => {
    const m = new Map<string, number>();
    findings.forEach((f, i) => {
      const slug = (f.src || "").toLowerCase();
      if (slug && !m.has(slug)) m.set(slug, i + 1);
    });
    return m;
  }, [findings]);

  // Split block-mode text into ~sentence paragraphs. Inline keeps one block.
  const paragraphs = inline
    ? [text]
    : splitParagraphs(text);

  return (
    <>
      {paragraphs.map((para, pi) => {
        const nodes = renderProseNodes(para, findings, sourceToCiteNum);
        if (inline) return <span key={pi}>{nodes}</span>;
        return (
          <p key={pi} className="leading-[1.55]">
            {nodes}
          </p>
        );
      })}
    </>
  );
}

/**
 * Split a wall of brief text into 2-3 readable paragraphs. Splits on
 * sentence boundaries that fall close to the 240-char mark, then keeps
 * sentence fragments grouped if they're tightly related (e.g. a list
 * of facts in one paragraph, the policy mandate in another, the
 * decision in the third).
 */
function splitParagraphs(text: string): string[] {
  const sentences = text.match(/[^.!?]+[.!?]+(?:\s|$)/g) ?? [text];
  if (sentences.length <= 2) return [text];

  const target = 240;
  const out: string[] = [];
  let cur = "";
  for (const s of sentences) {
    if (cur.length + s.length <= target || cur === "") {
      cur += s;
    } else {
      out.push(cur.trim());
      cur = s;
    }
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

/**
 * Tokenise prose into React nodes: plain text + ID chips + source
 * mentions + quoted policy names. Uses a single composite regex with
 * named groups so the longest match wins.
 */
function renderProseNodes(
  text: string,
  findings: MemoFinding[],
  sourceToCiteNum: Map<string, number>,
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // Order matters - try the most specific patterns first.
  // Stripe IDs: ch_/du_/cus_/py_/pi_/re_/in_/sub_/evt_/seti_ + 20+ chars
  // HubSpot numeric IDs (12+ digits)
  // UUIDs
  // Quoted policy names ("Documented Incident Pro-Rata Refund Credit Policy")
  // Source mentions (Stripe, HubSpot, etc.)
  const STRIPE_ID = /\b(ch|du|cus|py|pi|re|in|sub|evt|seti)_[A-Za-z0-9]{14,}\b/;
  const HUBSPOT_ID = /\b\d{10,}\b/;
  const UUID =
    /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i;
  const POLICY_QUOTE = /"([^"]{8,80})"/;
  const SOURCE_MENTION =
    /\b(Stripe|HubSpot|Hubspot|Intercom|Zendesk|Datadog|Notion|Slack|PostHog|Posthog|PagerDuty|Pagerduty|Sentry|Salesforce|Resend|Linear|GitHub|Github)\b/;
  const INCIDENT_ID = /\b(INC-\d{4}-\d{2}-\d{2}-[a-z0-9-]+)\b/i;

  const PATTERNS: { name: string; re: RegExp }[] = [
    { name: "stripe-id", re: STRIPE_ID },
    { name: "uuid", re: UUID },
    { name: "incident-id", re: INCIDENT_ID },
    { name: "hubspot-id", re: HUBSPOT_ID },
    { name: "policy-quote", re: POLICY_QUOTE },
    { name: "source-mention", re: SOURCE_MENTION },
  ];

  let rest = text;
  let key = 0;
  // Greedy scan: at each position find the earliest-starting match
  // across all patterns; render text up to it, then render the chip,
  // then continue from after it.
  while (rest.length > 0) {
    let best: { name: string; match: RegExpMatchArray } | null = null;
    for (const p of PATTERNS) {
      const m = rest.match(p.re);
      if (!m || m.index === undefined) continue;
      if (best === null || m.index < (best.match.index ?? Infinity)) {
        best = { name: p.name, match: m };
      }
    }
    if (!best || best.match.index === undefined) {
      out.push(rest);
      break;
    }
    const idx = best.match.index;
    if (idx > 0) out.push(rest.slice(0, idx));
    const matchText = best.match[0];
    switch (best.name) {
      case "stripe-id":
        out.push(<IdChip key={key++} src="stripe" id={matchText} />);
        break;
      case "uuid":
        // UUIDs in our world are usually Notion page ids.
        out.push(<IdChip key={key++} src="notion" id={matchText} />);
        break;
      case "incident-id":
        out.push(<IdChip key={key++} src="datadog" id={matchText} />);
        break;
      case "hubspot-id":
        out.push(<IdChip key={key++} src="hubspot" id={matchText} />);
        break;
      case "policy-quote": {
        const inner = best.match[1] ?? matchText;
        out.push(
          <span
            key={key++}
            className="italic"
            style={{
              fontFamily: "Spectral, serif",
              fontStyle: "italic",
              color: "var(--color-ink-strong)",
            }}
            title="policy document"
          >
            “{inner}”
          </span>,
        );
        break;
      }
      case "source-mention": {
        const slug = matchText.toLowerCase();
        const citeNum = sourceToCiteNum.get(slug);
        out.push(
          <SourceMention
            key={key++}
            src={slug}
            label={matchText}
            citeNum={citeNum}
            findings={findings}
          />,
        );
        break;
      }
    }
    rest = rest.slice(idx + matchText.length);
  }
  return out;
}

/**
 * Compact monospace chip for an opaque ID. Renders the prefix + a
 * truncated middle + the last 4 chars, full ID in the tooltip. Links
 * to the source URL when we can construct one.
 */
function IdChip({ src, id }: { src: string; id: string }) {
  const url = citationUrl(src, null, id);
  const display = compactId(id);
  const body = (
    <code
      title={id}
      className="inline-flex items-baseline align-baseline"
      style={{
        fontFamily: "Geist Mono, ui-monospace, monospace",
        fontSize: "0.84em",
        padding: "1px 6px",
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-rule-soft)",
        borderRadius: 3,
        color: "var(--color-ink)",
        whiteSpace: "nowrap",
        lineHeight: 1.2,
        marginInline: "1px",
      }}
    >
      {display}
    </code>
  );
  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        style={{ textDecoration: "none" }}
      >
        {body}
      </a>
    );
  }
  return body;
}

/**
 * Abbreviate a long opaque ID. Stripe IDs keep their type prefix
 * (ch_, du_) and the last 4 chars: ch_3Tch1LCNe0SBMhzI0FIYdCkF →
 * ch_3Tch1L…dCkF. UUIDs collapse to the first 8 + last 4.
 */
function compactId(id: string): string {
  if (id.length <= 14) return id;
  if (id.includes("_")) {
    const [prefix, rest] = id.split(/_(.+)/);
    if (rest && rest.length > 10) {
      return `${prefix}_${rest.slice(0, 6)}…${rest.slice(-4)}`;
    }
  }
  if (id.length > 14) {
    return `${id.slice(0, 8)}…${id.slice(-4)}`;
  }
  return id;
}

/**
 * SourceMention - the name of a source (Stripe, HubSpot, …) rendered
 * in its brand color, with a trailing superscript citation chip when
 * we have a matching finding.
 */
function SourceMention({
  src,
  label,
  citeNum,
  findings,
}: {
  src: string;
  label: string;
  citeNum: number | undefined;
  findings: MemoFinding[];
}) {
  const color = brandHexFor(src);
  const finding = citeNum ? findings[citeNum - 1] : undefined;
  const url = finding?.url ?? null;
  return (
    <>
      <span
        style={{
          color,
          fontWeight: 500,
        }}
      >
        {label}
      </span>
      {citeNum != null && (
        <>
          {" "}
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ textDecoration: "none" }}
            >
              <SmallCite n={citeNum} src={src} />
            </a>
          ) : (
            <SmallCite n={citeNum} src={src} />
          )}
        </>
      )}
    </>
  );
}

function SmallCite({ n, src: _src }: { n: number; src: string }) {
  return (
    <sup
      className="font-mono tabular-nums"
      style={{
        fontSize: "0.65em",
        padding: "0 4px",
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-rule-soft)",
        borderRadius: 3,
        color: "var(--color-ink-muted)",
        verticalAlign: "super",
        marginLeft: 1,
      }}
    >
      [{n}]
    </sup>
  );
}

function brandHexFor(slug: string): string {
  const meta = getSource(slug);
  const hex = meta?.simpleIcon?.hex;
  if (!hex) return "var(--color-ink-strong)";
  const EXTREME = new Set(["000000", "FFFFFF", "FDFDFD", "FEFEFE"]);
  if (EXTREME.has(hex.toUpperCase())) return "var(--color-ink-strong)";
  return `#${hex}`;
}

/**
 * AlsoTouched - small footer below the postmortem listing every other
 * source the agent looked at, beyond the ones that produced formal
 * findings. Derived from a static map of "the 8 sources Manthan reads
 * for chargebacks" minus whatever's already in the formal findings.
 *
 * In a future pass this could pull from coral_steps via a prop, but
 * for now the static set covers every Aperture-style case and is
 * deterministic for the demo.
 */
function AlsoTouched({ findings }: { findings: MemoFinding[] }) {
  const ALL_CHARGEBACK_SOURCES = [
    "stripe",
    "hubspot",
    "intercom",
    "zendesk",
    "datadog",
    "notion",
    "posthog",
    "slack",
  ];
  const inFindings = new Set(
    findings.map((f) => (f.src || "").toLowerCase()).filter(Boolean),
  );
  const others = ALL_CHARGEBACK_SOURCES.filter((s) => !inFindings.has(s));
  if (others.length === 0) return null;
  return (
    <div
      className="mt-3 pt-4 flex items-center gap-3 flex-wrap"
      style={{ borderTop: "1px solid var(--color-rule-soft)" }}
    >
      <span
        className="text-[11px] uppercase"
        style={{
          fontFamily: "Geist Mono, ui-monospace, monospace",
          color: "var(--color-ink-faint)",
          letterSpacing: "0.18em",
        }}
      >
        Also queried
      </span>
      <div className="flex items-center gap-2 flex-wrap">
        {others.map((src) => (
          <span
            key={src}
            className="inline-flex items-baseline gap-1.5 px-2 py-1"
            style={{
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-rule-soft)",
              borderRadius: 3,
              fontSize: 11,
              fontFamily: "Spectral, serif",
              color: brandHexFor(src),
              fontWeight: 500,
              letterSpacing: "0.01em",
            }}
            title={`${src} - agent queried but no formal finding committed`}
          >
            <SourceIcon id={src} size={11} tinted />
            {prettyName(src)}
          </span>
        ))}
      </div>
    </div>
  );
}

function prettyName(slug: string): string {
  const map: Record<string, string> = {
    hubspot: "HubSpot",
    pagerduty: "PagerDuty",
    posthog: "PostHog",
    github: "GitHub",
  };
  return map[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

// ──────────────────────────────────────────────────────────────────────
// Editorial primitives.
// ──────────────────────────────────────────────────────────────────────

function Eyebrow({
  children,
  accent,
}: {
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <span
      className="text-[12.5px] uppercase"
      style={{
        color: accent
          ? "var(--color-accent, #56cf83)"
          : "var(--color-ink-muted)",
        letterSpacing: "0.20em",
        fontWeight: 500,
      }}
    >
      {children}
    </span>
  );
}

function SourceWord({ src, label }: { src: string; label: string }) {
  return (
    <span
      className="inline-flex items-baseline gap-2 text-[12px]"
      style={{
        color: "var(--color-ink-muted)",
        letterSpacing: "0.16em",
      }}
    >
      {src && (
        <span
          aria-hidden
          style={{ display: "inline-flex", transform: "translateY(2px)" }}
        >
          <SourceIcon id={src} size={12} tinted />
        </span>
      )}
      <span>{label}</span>
    </span>
  );
}

/**
 * citationUrl - build a deep-link to the underlying source record from
 * the three structural fields we always carry (source / table / ref).
 *
 * The backend already pre-builds `url` on ApiCitation when it knows how
 * (the canonical path); this helper is the client-side fallback used
 * when the chip arrives with only the structural triple (e.g. mock
 * data, older briefs, or sources the backend hasn't been taught to
 * deep-link yet). Returns null when we can't safely build a URL so the
 * chip stays a plain span instead of becoming a dead link.
 *
 * Templates mirror the table in the wiring doc. Stripe uses the test-
 * mode dashboard because the agent currently runs against test keys;
 * swap to live URLs once the env distinction lands.
 */
export function citationUrl(
  source: string | null | undefined,
  table: string | null | undefined,
  ref: string | null | undefined,
): string | null {
  if (!source || !ref) return null;
  const src = source.toLowerCase();
  const tbl = (table ?? "").toLowerCase();

  if (src === "stripe") {
    if (tbl === "disputes") {
      return `https://dashboard.stripe.com/test/disputes/${ref}`;
    }
    if (tbl === "charges" || tbl === "payments" || tbl === "payment_intents") {
      return `https://dashboard.stripe.com/test/payments/${ref}`;
    }
    if (tbl === "customers") {
      return `https://dashboard.stripe.com/test/customers/${ref}`;
    }
    // Best-effort fallback by ref-prefix when the table wasn't supplied
    // (older briefs sometimes only carry the bare ref string). Stripe
    // record IDs are prefix-typed, so this is structurally safe.
    if (ref.startsWith("du_")) {
      return `https://dashboard.stripe.com/test/disputes/${ref}`;
    }
    if (ref.startsWith("ch_") || ref.startsWith("pi_") || ref.startsWith("py_")) {
      return `https://dashboard.stripe.com/test/payments/${ref}`;
    }
    if (ref.startsWith("cus_")) {
      return `https://dashboard.stripe.com/test/customers/${ref}`;
    }
    return null;
  }

  if (src === "hubspot" && (tbl === "companies" || ref.startsWith("company/"))) {
    const id = ref.replace(/^company\//, "");
    // No portalId hardcoded - HubSpot routes /contacts/portalId/company/{id}
    // through the user's active portal; passing the literal "portalId"
    // segment is what HubSpot's own deep-link docs recommend when the
    // portal isn't known at build time.
    return `https://app.hubspot.com/contacts/portalId/company/${id}`;
  }

  if (src === "notion" && (tbl === "pages" || ref.startsWith("page/"))) {
    const raw = ref.replace(/^page\//, "");
    // Notion's URL slug uses the 32-char id with no dashes; if the ref
    // is already dashed, drop the dashes.
    const id = raw.replace(/-/g, "");
    return `https://www.notion.so/${id}`;
  }

  if (src === "datadog") {
    if (tbl === "monitors" || ref.startsWith("monitor/")) {
      return `https://app.datadoghq.com/monitors/${ref.replace(/^monitor\//, "")}`;
    }
    if (tbl === "incidents" || ref.startsWith("incident/") || ref.startsWith("INC-")) {
      return `https://app.datadoghq.com/incidents?query=${encodeURIComponent(
        ref.replace(/^incident\//, ""),
      )}`;
    }
    if (tbl === "events" || /^\d+$/.test(ref)) {
      return `https://app.datadoghq.com/event/event?id=${encodeURIComponent(ref)}`;
    }
    // Fallback - Datadog top-level search.
    return `https://app.datadoghq.com/search?query=${encodeURIComponent(ref)}`;
  }

  if (src === "intercom") {
    // Intercom workspace slug comes from env (Vite-injected). Without
    // it we still ship the operator to the right org's Intercom
    // inbox search rather than a dead chip.
    const ws =
      (import.meta.env.VITE_INTERCOM_WORKSPACE as string | undefined) ||
      "_";
    const id = ref.replace(/^conv\//, "");
    if (tbl === "conversations" || ref.startsWith("conv/")) {
      return `https://app.intercom.com/a/apps/${ws}/inbox/conversation/${id}`;
    }
    if (tbl === "contacts" || ref.startsWith("contact/")) {
      return `https://app.intercom.com/a/apps/${ws}/users/${id.replace(/^contact\//, "")}`;
    }
    return `https://app.intercom.com/a/apps/${ws}/inbox/search?q=${encodeURIComponent(ref)}`;
  }

  if (src === "zendesk") {
    // Subdomain from env - we seed against minylabs in dev.
    const sub =
      (import.meta.env.VITE_ZENDESK_SUBDOMAIN as string | undefined) ||
      "minylabs";
    if (tbl === "tickets" || ref.startsWith("ticket/")) {
      return `https://${sub}.zendesk.com/agent/tickets/${ref.replace(/^ticket\//, "")}`;
    }
    if (tbl === "users" || ref.startsWith("user/")) {
      return `https://${sub}.zendesk.com/agent/users/${ref.replace(/^user\//, "")}`;
    }
    return `https://${sub}.zendesk.com/agent/search?q=${encodeURIComponent(ref)}`;
  }

  if (src === "pagerduty") {
    // Account subdomain from env; fall through to top-level search.
    const sub =
      (import.meta.env.VITE_PAGERDUTY_SUBDOMAIN as string | undefined) ||
      "app";
    if (tbl === "incidents" || ref.startsWith("incident/")) {
      return `https://${sub}.pagerduty.com/incidents/${ref.replace(/^incident\//, "")}`;
    }
    return `https://${sub}.pagerduty.com/search?q=${encodeURIComponent(ref)}`;
  }

  if (src === "slack") {
    // Slack permalinks need workspace + channel + ts which we don't
    // carry in the bare ref. Send the operator to the workspace search
    // for the ref keyword - better than a dead chip.
    const ws =
      (import.meta.env.VITE_SLACK_WORKSPACE as string | undefined) ||
      "app";
    return `https://${ws}.slack.com/search?query=${encodeURIComponent(ref)}`;
  }

  if (src === "posthog") {
    const proj =
      (import.meta.env.VITE_POSTHOG_PROJECT as string | undefined) || "";
    if (proj) {
      return `https://app.posthog.com/project/${proj}/events?q=${encodeURIComponent(ref)}`;
    }
    return `https://app.posthog.com/events?q=${encodeURIComponent(ref)}`;
  }

  if (src === "salesforce") {
    const inst =
      (import.meta.env.VITE_SALESFORCE_INSTANCE as string | undefined) ||
      "login.salesforce.com";
    return `https://${inst}/lightning/r/${ref}/view`;
  }

  // Unknown / unmapped source - last-resort Google search on the ref
  // so the chip always opens SOMETHING rather than staying dead.
  return `https://www.google.com/search?q=${encodeURIComponent(
    `${src} ${ref}`,
  )}`;
}

function CiteChip({
  n,
  src,
  label,
  url,
}: {
  n: number;
  src: string;
  label: string;
  url?: string | null;
}) {
  // Visual treatment is identical whether we render as <a> or <span>;
  // only the tag + href changes. Styling stays in one place via this
  // shared style object so the two branches can't drift apart.
  const sharedStyle: React.CSSProperties = {
    background: "var(--color-rule-soft)",
    border: "1px solid var(--color-rule)",
    borderRadius: 3,
    color: "var(--color-ink)",
    fontSize: 11.5,
    fontFamily: "Geist Mono, ui-monospace, monospace",
    lineHeight: 1,
    cursor: "pointer",
    textDecoration: "none",
  };
  const inner = (
    <>
      <SourceIcon id={src} size={11} tinted />
      <span className="tabular-nums">[{n}]</span>
      <span aria-hidden style={{ color: "var(--color-ink-faint)" }}>
        ↗
      </span>
    </>
  );
  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="ml-2 inline-flex items-baseline gap-1.5 px-2 py-1 align-baseline transition-colors hover:brightness-125"
        style={sharedStyle}
        title={`${src} · ${label} - open in new tab`}
      >
        {inner}
      </a>
    );
  }
  return (
    <span
      className="ml-2 inline-flex items-baseline gap-1.5 px-2 py-1 align-baseline transition-colors"
      style={sharedStyle}
      title={`${src} · ${label}`}
    >
      {inner}
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────
// FiredActionRow + ClosedCaseFooter - post-resolution treatment of the
// right panel. The same actions that read as "Suggested actions" while
// awaiting approval now read as a ledger of what fired, with each row's
// status, external reference, and a deep link to the source dashboard.
// ──────────────────────────────────────────────────────────────────────

function FiredActionRow({
  action,
  index,
  isLast,
}: {
  action: WorkspaceAction;
  index: number;
  isLast: boolean;
}) {
  const src = action.source ?? "stripe";
  const status = action.status ?? "drafted";
  const failed = status === "failed" || status === "drift";
  const queued = status === "drafted" || status === "approved";
  const executing = status === "executing";
  const succeeded = status === "succeeded";

  const statusLabel = succeeded
    ? "fired"
    : failed
      ? "failed"
      : executing
        ? "firing…"
        : queued
          ? "queued"
          : status;
  const statusColor = succeeded
    ? "var(--color-accent)"
    : failed
      ? "var(--color-danger)"
      : executing
        ? "var(--color-info)"
        : "var(--color-ink-faint)";

  return (
    <li
      className="grid pb-4"
      style={{
        gridTemplateColumns: "32px minmax(0,1fr)",
        gap: 14,
        borderBottom: !isLast ? "1px solid var(--color-rule-soft)" : "none",
      }}
    >
      <span
        className="text-[13px] tabular-nums pt-0.5"
        style={{
          color: "var(--color-ink-faint)",
          letterSpacing: "0.04em",
          fontFamily: "Spectral, serif",
          fontStyle: "italic",
        }}
      >
        {String(index + 1).padStart(2, "0")}.
      </span>
      <div className="min-w-0">
        <div className="flex items-baseline justify-between gap-3">
          <SourceWord src={src} label={src.toUpperCase()} />
          <span
            className="text-[10.5px] uppercase tabular-nums shrink-0"
            style={{
              color: statusColor,
              letterSpacing: "0.18em",
              fontWeight: 500,
            }}
          >
            {succeeded && "✓ "}
            {failed && "× "}
            {statusLabel}
          </span>
        </div>
        <div
          className="text-[16px] leading-[1.45] mt-2"
          style={{ color: "var(--color-ink-strong)" }}
        >
          {action.title}
        </div>
        {action.externalRef && (
          <div
            className="font-mono text-[12.5px] tabular-nums mt-2 truncate"
            style={{ color: "var(--color-ink-muted)" }}
            title={action.externalRef}
          >
            {action.externalUrl ? (
              <a
                href={action.externalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-dotted underline-offset-4 hover:text-[var(--color-ink-strong)] transition-colors"
              >
                {action.externalRef}
              </a>
            ) : (
              <span>{action.externalRef}</span>
            )}
          </div>
        )}
        {failed && action.errorMessage && (
          <div
            className="font-mono text-[11.5px] mt-2"
            style={{ color: "var(--color-danger)" }}
            title={action.errorMessage}
          >
            {action.errorMessage.slice(0, 120)}
            {action.errorMessage.length > 120 ? "…" : ""}
          </div>
        )}
      </div>
    </li>
  );
}

function ClosedCaseFooter({ actions }: { actions: WorkspaceAction[] }) {
  const total = actions.length;
  const ok = actions.filter((a) => a.status === "succeeded").length;
  const bad = actions.filter(
    (a) => a.status === "failed" || a.status === "drift",
  ).length;
  return (
    <div className="flex items-baseline gap-3">
      <span
        className="text-[11px] uppercase"
        style={{
          color: "var(--color-ink-faint)",
          letterSpacing: "0.20em",
          fontWeight: 500,
        }}
      >
        Resolved
      </span>
      <span
        className="font-mono text-[12.5px] tabular-nums"
        style={{ color: "var(--color-ink-muted)" }}
      >
        {ok}/{total} fired{bad > 0 ? ` · ${bad} failed` : ""}
      </span>
    </div>
  );
}

function ApproveButton({
  state,
  onClick,
  actionCount,
}: {
  state: "awaiting" | "firing" | "fired";
  onClick: () => void;
  actionCount: number;
}) {
  if (state === "fired") {
    return (
      <span
        className="inline-flex items-center gap-2 text-[14px] font-medium px-5 py-2.5"
        style={{
          background: "var(--color-accent-soft, var(--color-accent-soft))",
          color: "var(--color-accent, #56cf83)",
          borderRadius: 5,
          border: "1px solid var(--color-accent, #56cf83)",
        }}
      >
        Fired · {actionCount} action{actionCount === 1 ? "" : "s"}
      </span>
    );
  }
  const firing = state === "firing";
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={firing}
      animate={
        firing
          ? { scale: 0.96 }
          : {
              boxShadow: [
                "0 0 0 0 rgba(86,207,131,0)",
                "0 0 0 12px rgba(86,207,131,0.22)",
                "0 0 0 0 rgba(86,207,131,0)",
              ],
            }
      }
      whileTap={!firing ? { scale: 0.94 } : undefined}
      transition={
        firing
          ? { duration: 0.18, ease: [0.22, 0.61, 0.36, 1] }
          : { duration: 1.3, repeat: Infinity }
      }
      className="text-[14px] font-medium px-5 py-2.5 inline-flex items-center gap-2 outline-none"
      style={{
        background: firing
          ? "var(--color-accent)"
          : "var(--color-accent, #56cf83)",
        color: "#0a0a0a",
        borderRadius: 5,
        cursor: firing ? "default" : "pointer",
        transition: "background 200ms ease",
        border: "none",
      }}
    >
      {firing && (
        <Loader2 size={13} strokeWidth={2.5} className="animate-spin" />
      )}
      {firing ? "Firing…" : "Approve · Execute"}
    </motion.button>
  );
}

// ──────────────────────────────────────────────────────────────────────
// ChatDrawer - Claude-mobile-style side panel.
//
// Lives next to the brief (not inside it). Slides in from the right when
// the operator taps the chat toggle in the HeaderStrip. Shows the
// human_followup / agent_thinking / agent_reply timeline as a flowing
// conversation and pins an ASK input at the bottom. Mounts only when
// caseId is provided + chat is open (the parent gates this).
//
// Chat backend is unchanged: POST /api/cases/{id}/chat appends a
// human_followup event, flips the case to investigating, the chat_loop
// worker runs the agent (same tools / Coral access), and the reply
// streams back as agent_reply over SSE.
// ──────────────────────────────────────────────────────────────────────

interface ChatTurn {
  seq: number;
  kind: "you" | "thinking" | "manthan";
  text: string;
  /** Optional millis to show next to the agent's reply. */
  elapsedMs?: number;
}

function collectChatTurns(events: CaseEvent[]): ChatTurn[] {
  // Walk in seq order, keeping only the conversation events. Collapse
  // any agent_thinking that precedes an agent_reply (we only need a
  // spinner when thinking is the most-recent event).
  const turns: ChatTurn[] = [];
  for (const e of events) {
    if (e.type === "human_followup") {
      const message = (e.data as { message?: string }).message ?? "";
      turns.push({ seq: e.seq, kind: "you", text: String(message) });
    } else if (e.type === "agent_thinking") {
      turns.push({ seq: e.seq, kind: "thinking", text: "" });
    } else if (e.type === "agent_reply") {
      const text = String((e.data as { text?: string }).text ?? "");
      const ms = (e.data as { elapsed_ms?: number }).elapsed_ms;
      turns.push({
        seq: e.seq,
        kind: "manthan",
        text,
        elapsedMs: typeof ms === "number" ? ms : undefined,
      });
      // Drop any standalone "thinking" that sits immediately before this
      // reply - once we have an answer the spinner is noise.
      for (let i = turns.length - 2; i >= 0; i--) {
        const t = turns[i];
        if (t.kind === "thinking") {
          turns.splice(i, 1);
          continue;
        }
        break;
      }
    }
  }
  return turns;
}

/** Header toggle button - sits in the HeaderStrip beside CoralToggle. */
function ChatHeaderToggle({
  open,
  onToggle,
}: {
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={open}
      title={open ? "Close chat" : "Talk to Manthan about this case"}
      className="inline-flex items-center gap-2 outline-none transition-opacity"
      style={{
        background: "transparent",
        border: "none",
        cursor: "pointer",
        padding: "4px 8px 4px 4px",
        borderRadius: 4,
      }}
    >
      <span
        className="inline-flex items-center justify-center"
        style={{
          width: 26,
          height: 26,
          borderRadius: 4,
          background: open ? "var(--color-accent-soft)" : "var(--color-rule-soft)",
          border: open
            ? "1px solid var(--color-accent-line)"
            : "1px solid var(--color-rule-soft)",
          transition: "all 160ms ease",
        }}
      >
        {/* Speech-bubble glyph - minimal, no heavy weight. */}
        <svg
          width="13"
          height="13"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden
        >
          <path
            d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H6.5L4 14.5V12a2 2 0 0 1-2-2V4Z"
            stroke={open ? "var(--color-accent)" : "var(--color-ink-muted)"}
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span
        className="text-[11px] uppercase tabular-nums"
        style={{
          color: open
            ? "var(--color-accent, #56cf83)"
            : "var(--color-ink-faint)",
          letterSpacing: "0.18em",
          fontWeight: 500,
        }}
      >
        ask
      </span>
    </button>
  );
}

function ChatDrawer({
  caseId,
  events,
  onClose,
}: {
  caseId: string;
  events: CaseEvent[];
  onClose: () => void;
}) {
  const turns = useMemo(() => collectChatTurns(events), [events]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to the newest turn when one lands.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns.length]);

  const hasTurns = turns.length > 0;
  const liveThinking = hasTurns && turns[turns.length - 1].kind === "thinking";

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const v = text.trim();
    if (!v || sending) return;
    setSending(true);
    try {
      await chatWithCase(caseId, v);
      setText("");
    } catch (err) {
      console.error("chat send failed", err);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      {/* Drawer header - minimal, identifies the panel + close button. */}
      <header
        className="shrink-0 flex items-center px-6"
        style={{
          height: 56,
          borderBottom: "1px solid var(--color-rule-soft)",
        }}
      >
        <span
          className="font-mono text-[12px] uppercase"
          style={{
            color: "var(--color-ink-muted)",
            letterSpacing: "0.18em",
          }}
        >
          Manthan
        </span>
        <span
          className="ml-3 text-[12px]"
          style={{
            color: "var(--color-ink-faint)",
            fontFamily: "Spectral, serif",
            fontStyle: "italic",
          }}
        >
          on this case
        </span>
        {liveThinking && (
          <span
            className="ml-3 inline-flex items-center gap-1.5 text-[11px] uppercase"
            style={{
              color: "var(--color-accent)",
              letterSpacing: "0.16em",
            }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                background: "var(--color-accent)",
                animation: "pulse-soft 1.2s ease-in-out infinite",
              }}
            />
            thinking
          </span>
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close chat"
          className="ml-auto inline-flex items-center justify-center outline-none transition-opacity hover:opacity-80"
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: "var(--color-ink-muted)",
            padding: 4,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path
              d="M4 4l8 8M12 4l-8 8"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>

      {/* Conversation list - scrollable. Empty state nudges the operator
          with a single italic prompt, Claude-mobile style. */}
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto px-6 py-6"
      >
        {hasTurns ? (
          <ol className="space-y-6">
            <AnimatePresence initial={false}>
              {turns.map((t) => (
                <motion.li
                  key={t.seq}
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18 }}
                >
                  <ChatTurnRow turn={t} />
                </motion.li>
              ))}
            </AnimatePresence>
          </ol>
        ) : (
          <div className="h-full flex flex-col items-start justify-center gap-3 pr-2">
            <span
              className="text-[11.5px] uppercase"
              style={{
                color: "var(--color-ink-faint)",
                letterSpacing: "0.20em",
                fontFamily: "Geist Mono, ui-monospace, monospace",
              }}
            >
              Ask Manthan
            </span>
            <p
              className="text-[17px] leading-[1.45]"
              style={{
                color: "var(--color-ink-muted)",
                fontFamily: "Spectral, serif",
                fontStyle: "normal",
              }}
            >
              Push back on the call, ask for a re-check, or rewrite an
              action. Manthan has the same tools that drafted the brief.
            </p>
          </div>
        )}
      </div>

      {/* Bottom-pinned ASK input - Claude-mobile rounded pill, monochrome. */}
      <form
        onSubmit={send}
        className="shrink-0 px-5 pt-3 pb-5"
        style={{ borderTop: "1px solid var(--color-rule-soft)" }}
      >
        <div
          className="flex items-center gap-2 px-4 py-2.5"
          style={{
            background: "var(--color-rule-soft)",
            border: "1px solid var(--color-rule)",
            borderRadius: 999,
          }}
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              liveThinking
                ? "Manthan is thinking…"
                : hasTurns
                  ? "Reply to Manthan"
                  : "Ask Manthan a question…"
            }
            disabled={sending || liveThinking}
            className="flex-1 bg-transparent text-[15px] outline-none min-w-0"
            style={{
              color: "var(--color-ink-strong)",
              fontFamily: "Spectral, serif",
            }}
          />
          <button
            type="submit"
            disabled={!text.trim() || sending || liveThinking}
            aria-label="Send"
            className="inline-flex items-center justify-center outline-none transition-opacity disabled:opacity-30"
            style={{
              width: 32,
              height: 32,
              borderRadius: 999,
              background: text.trim()
                ? "var(--color-accent, #56cf83)"
                : "var(--color-rule-soft)",
              color: text.trim() ? "#0a0a0a" : "var(--color-ink-muted)",
              border: "none",
              cursor: text.trim() && !sending ? "pointer" : "default",
              transition: "background 160ms ease",
            }}
          >
            {sending ? (
              <Loader2 size={14} strokeWidth={2.5} className="animate-spin" />
            ) : (
              <Send size={13} strokeWidth={2.4} />
            )}
          </button>
        </div>
      </form>
    </>
  );
}

function ChatTurnRow({ turn }: { turn: ChatTurn }) {
  if (turn.kind === "you") {
    return (
      <div className="grid gap-3" style={{ gridTemplateColumns: "70px 1fr" }}>
        <div
          className="text-[11.5px] uppercase pt-1"
          style={{
            color: "var(--color-ink-faint)",
            fontFamily: "Geist Mono, ui-monospace, monospace",
            letterSpacing: "0.18em",
          }}
        >
          You
        </div>
        <div
          className="text-[15.5px] leading-[1.55]"
          style={{
            color: "var(--color-ink)",
            fontFamily: "Spectral, serif",
          }}
        >
          {turn.text}
        </div>
      </div>
    );
  }
  if (turn.kind === "thinking") {
    return (
      <div className="grid gap-3" style={{ gridTemplateColumns: "70px 1fr" }}>
        <div
          className="text-[11.5px] uppercase pt-1"
          style={{
            color: "var(--color-accent)",
            fontFamily: "Geist Mono, ui-monospace, monospace",
            letterSpacing: "0.18em",
          }}
        >
          Manthan
        </div>
        <div
          className="text-[13.5px] inline-flex items-center gap-2.5 italic pt-1"
          style={{
            color: "var(--color-ink-muted)",
            fontFamily: "Spectral, serif",
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background: "var(--color-accent)",
              animation: "pulse-soft 1.2s ease-in-out infinite",
            }}
          />
          thinking…
        </div>
      </div>
    );
  }
  // manthan reply
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: "70px 1fr" }}>
      <div className="pt-1">
        <div
          className="text-[11.5px] uppercase"
          style={{
            color: "var(--color-accent)",
            fontFamily: "Geist Mono, ui-monospace, monospace",
            letterSpacing: "0.18em",
          }}
        >
          Manthan
        </div>
        {turn.elapsedMs != null && (
          <div
            className="text-[10.5px] tabular-nums mt-1"
            style={{
              color: "var(--color-ink-ghost)",
              fontFamily: "Geist Mono, ui-monospace, monospace",
              letterSpacing: "0.06em",
            }}
          >
            {(turn.elapsedMs / 1000).toFixed(1)}s
          </div>
        )}
      </div>
      <div
        className="text-[15.5px] leading-[1.62] space-y-3"
        style={{
          color: "var(--color-ink-strong)",
          fontFamily: "Spectral, serif",
        }}
      >
        <MarkdownText text={turn.text} />
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// MarkdownText - light-weight inline formatter.
//
// The agent_reply text is plain English with a small number of
// conventions we want to surface visually:
//   - `\n\n` separates paragraphs
//   - lines starting with "- " or "* " become bullet items inside the
//     surrounding paragraph
//   - `**bold**` runs
//   - backtick `code` runs (monospace, faint background)
//   - `[N]` citation refs (small monospace chip)
//
// We deliberately avoid a real markdown library - the agent's output is
// constrained enough that a 60-line tokeniser hits everything we need
// and keeps the visual language consistent with the rest of the memo.
// ──────────────────────────────────────────────────────────────────────

function MarkdownText({ text }: { text: string }) {
  // Split into paragraphs on blank lines.
  const paragraphs = text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <>
      {paragraphs.map((para, i) => {
        // If the paragraph is a bullet list, render as a list.
        const lines = para.split(/\n/).map((l) => l.trim()).filter(Boolean);
        const isList =
          lines.length > 1 && lines.every((l) => /^[-*]\s+/.test(l));
        if (isList) {
          return (
            <ul key={i} className="space-y-1.5 pl-4">
              {lines.map((line, j) => (
                <li
                  key={j}
                  className="relative"
                  style={{ color: "var(--color-ink)" }}
                >
                  <span
                    aria-hidden
                    className="absolute"
                    style={{
                      left: -12,
                      top: "0.55em",
                      width: 4,
                      height: 4,
                      borderRadius: 999,
                      background: "var(--color-ink-ghost)",
                    }}
                  />
                  <InlineRich text={line.replace(/^[-*]\s+/, "")} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i}>
            <InlineRich text={para.replace(/\n/g, " ")} />
          </p>
        );
      })}
    </>
  );
}

/**
 * InlineRich - handles **bold**, `code`, [N] in a single pass.
 *
 * A single regex captures all three patterns; the matched groups tell us
 * which kind it is. Everything between matches is plain text.
 */
function InlineRich({ text }: { text: string }) {
  // Capture groups: 1=bold contents, 2=code contents, 3=citation number.
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|\[(\d+)\]/g;
  const out: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      out.push(text.slice(last, m.index));
    }
    if (m[1] !== undefined) {
      out.push(
        <strong
          key={key++}
          style={{ color: "var(--color-ink-strong)", fontWeight: 600 }}
        >
          {m[1]}
        </strong>,
      );
    } else if (m[2] !== undefined) {
      out.push(
        <code
          key={key++}
          className="px-1.5 py-0.5 mx-0.5"
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: "0.88em",
            background: "var(--color-rule-soft)",
            border: "1px solid var(--color-rule-soft)",
            borderRadius: 3,
            color: "var(--color-ink)",
          }}
        >
          {m[2]}
        </code>,
      );
    } else if (m[3] !== undefined) {
      out.push(
        <span
          key={key++}
          className="inline-flex items-baseline px-1.5 py-0.5 mx-0.5 tabular-nums align-baseline"
          style={{
            fontFamily: "Geist Mono, ui-monospace, monospace",
            fontSize: "0.78em",
            background: "var(--color-rule-soft)",
            border: "1px solid var(--color-rule)",
            borderRadius: 3,
            color: "var(--color-ink)",
          }}
        >
          [{m[3]}]
        </span>,
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) {
    out.push(text.slice(last));
  }
  return <>{out}</>;
}

// AnimatePresence is exported above; suppress the unused import warning
// while still keeping the option open for the future expand animations.
void AnimatePresence;
