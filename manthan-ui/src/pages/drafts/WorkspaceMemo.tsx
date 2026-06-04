/**
 * WorkspaceMemo - Case Workspace, editorial-memo direction.
 *
 * Renders one case in the landing's BriefCanvas vocabulary: HeaderStrip
 * at the top, two-column editorial spread inside (postmortem left,
 * suggested actions right), and a Coral toggle that swaps the brief
 * for the raw SQL trace wired to the case's SSE stream.
 *
 * Mounted by Workspace.tsx at /app/case/:id once the case has reached
 * an awaiting-approval / resolved / escalated state - every prop is
 * required and comes from the API; the component never falls back to
 * fabricated data.
 */

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { SourceIcon } from "@/components/ui/SourceIcon";
import { getSource } from "@/lib/sources";
import { useCaseEvents, type CaseEvent } from "@/lib/useCaseEvents";
import { approveCase, denyCase, escalateCase, holdCase } from "@/lib/api";
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
  /** Backwards-compat alias for demoMode === 'v2'. */
  isDemoV2?: boolean;
  /** Which guided demo grafted seeded data onto this case:
   *    'v2' - email demo, Maya Patel scenario
   *    'v3' - Slack demo, Vermillion Studios scenario
   *    null - real case, no banner shown */
  demoMode?: "v2" | "v3" | null;
  /** The operator's own email - shown in the banner so the user can
   *  see at a glance that the case + reply are routed to them, even
   *  though the investigation references the seeded customer. */
  loggedInEmail?: string;
}

export interface WorkspaceMemoProps {
  /** Full case data shaped from the API row. */
  caseData: MemoCaseData;
  findings: MemoFinding[];
  actions: MemoAction[];
  /** Live action rows with id + status; drives the firing cinematic. */
  workspaceActions: WorkspaceAction[];
  /** Case_id - identifies the SSE stream the Coral toggle subscribes to. */
  caseId: string;
  /** Called after the cinematic finishes so the parent can refetch the
   *  case detail (status → resolved, actions → succeeded). */
  onActionsExecuted?: () => void;
}

// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────

export default function WorkspaceMemo(props: WorkspaceMemoProps) {
  const {
    caseData,
    findings,
    actions,
    workspaceActions,
    caseId,
    onActionsExecuted,
  } = props;

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
  // True after the cinematic has walked every action through its
  // MIN_DWELL_MS. Used by the terminal-state useEffect below to allow
  // the "firing" → "fired" flip ONCE the cinematic has done its job,
  // not the moment SSE delivers case_closed (which can land sub-second
  // when the actor is fast - faster than the first ProgressDot animates).
  const [cinematicDone, setCinematicDone] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [verdictPending, setVerdictPending] = useState<
    null | "deny" | "hold" | "escalate"
  >(null);
  const [verdictError, setVerdictError] = useState<string | null>(null);

  const navigate = useNavigate();

  // Brief ↔ Coral toggle.
  const [mode, setMode] = useState<"prose" | "coral">("prose");

  const { events, isComplete } = useCaseEvents(caseId);
  const coralSteps = useMemo(() => collectCoralSteps(events), [events]);
  const currentSource = useMemo(() => latestSource(events), [events]);

  // Backend reached terminal state? Flip to "fired" the moment the API
  // confirms (via case_closed SSE event OR a refetch returning
  // resolved/errored). Critical detail: we ONLY do this when state is
  // "awaiting", never while state is "firing" - the cinematic must be
  // allowed to walk every action with its MIN_DWELL_MS dwell time. The
  // previous version unmounted the cinematic the instant case_closed
  // arrived, so when the actor finished fast (Stripe + Resend + Slack
  // all returned in <1s) the operator saw the first action card animate
  // in and then the workspace just flipped to the Closed Brief - they
  // never got to see the other actions land. handleCinematicComplete
  // below takes care of flipping "firing" → "fired" once the cinematic
  // has actually walked through every step.
  useEffect(() => {
    if (!isCaseTerminal) return;
    // Two valid moments to flip to "fired":
    //   1. We mounted with the case already terminal (state="awaiting"
    //      means the operator never clicked Approve - they navigated
    //      to an already-closed case).
    //   2. The cinematic has finished its walk AND the backend has
    //      confirmed terminal. cinematicDone is set by
    //      handleCinematicComplete.
    if (state === "awaiting" || (state === "firing" && cinematicDone)) {
      setState("fired");
    }
  }, [isCaseTerminal, state, cinematicDone]);

  async function handleApprove() {
    if (state !== "awaiting") return;
    setState("firing");
    setApproveError(null);
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
    // The cinematic finished walking through its sequence. Mark
    // cinematicDone so the terminal-state useEffect can flip us to
    // "fired" once the backend confirms (or right now if it already
    // has). Always trigger a refetch so the parent refreshes action
    // statuses + case row.
    setCinematicDone(true);
    onActionsExecuted?.();
    if (isCaseTerminal) {
      setState("fired");
    }
    // else: stay in "firing"; the terminal-state useEffect will flip
    // us once isCaseTerminal becomes true, because cinematicDone is
    // now set.
  }

  // Escalate / Hold / Deny - the three operator overrides on the brief.
  // Each one calls its own API, refetches the case, then bounces the
  // operator back to the inbox so the row visibly leaves "Active".
  async function handleVerdict(verdict: "deny" | "hold" | "escalate") {
    if (verdictPending) return;
    setVerdictPending(verdict);
    setVerdictError(null);
    try {
      if (verdict === "deny") {
        await denyCase(caseId, "Denied by operator from the brief");
      } else if (verdict === "hold") {
        await holdCase(caseId);
      } else {
        await escalateCase(caseId);
      }
      onActionsExecuted?.();
      navigate("/app");
    } catch (e) {
      console.warn(`manthan: ${verdict} failed`, e);
      setVerdictError((e as Error).message ?? `${verdict} failed`);
      setVerdictPending(null);
    }
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
      // Outer wrapper: card with border on desktop, full-bleed on
      // mobile so the page can grow naturally and AppShell scrolls.
      // The `min-h-full` keeps the card from collapsing when content
      // is short (e.g. an empty closed-case view).
      className="lg:h-full w-full flex items-stretch px-2 sm:px-4 lg:px-6 py-3 sm:py-4 lg:py-6 min-h-full"
      style={{ background: "var(--color-bg)" }}
    >
      <div
        className="flex flex-col flex-1 lg:min-h-0"
        style={{
          background: "var(--color-bg)",
          border: "1px solid var(--color-rule)",
          borderRadius: 6,
          color: "var(--color-ink-strong)",
          // overflow: hidden on lg only; mobile lets content grow.
          overflow: undefined,
          boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
        }}
      >
        <HeaderStrip
          caseData={caseData}
          phaseLabel={phaseLabel}
          phaseAccent={phaseAccent}
          showCoralToggle
          mode={mode}
          onToggleMode={() =>
            setMode((m) => (m === "prose" ? "coral" : "prose"))
          }
        />

        <div className="relative flex-1 lg:min-h-0">
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
                onVerdict={handleVerdict}
                verdictPending={verdictPending}
                verdictError={verdictError}
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
}: {
  caseData: MemoCaseData;
  phaseLabel: string;
  phaseAccent: string;
  showCoralToggle: boolean;
  mode: "prose" | "coral";
  onToggleMode: () => void;
}) {
  return (
    <header
      className="flex items-center px-4 sm:px-6 lg:px-9 shrink-0 gap-2 overflow-x-auto"
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
  onVerdict,
  verdictPending,
  verdictError,
}: {
  caseData: MemoCaseData;
  findings: MemoFinding[];
  actions: MemoAction[];
  workspaceActions: WorkspaceAction[];
  state: "awaiting" | "firing" | "fired";
  onApprove: () => void;
  approveError?: string | null;
  onVerdict: (verdict: "deny" | "hold" | "escalate") => void;
  verdictPending: null | "deny" | "hold" | "escalate";
  verdictError: string | null;
}) {
  const isClosed = state === "fired";
  return (
    // Below `lg` (1024px) we stack the postmortem on top and the
    // actions panel underneath - the fixed 2-column grid was crushing
    // both columns into unreadable narrow strips on phones. lg+ keeps
    // the original side-by-side layout where each column owns its own
    // scroll within a viewport-fixed grid; mobile lets the whole page
    // scroll naturally inside AppShell's main overflow-y-auto.
    //
    // Height management diff:
    //   - lg+: `h-full overflow-hidden` + per-column `overflow-y-auto`
    //   - mobile: no height lock, no overflow rules - the page just
    //     grows tall and the AppShell main column scrolls
    // The earlier version applied the lg rules unconditionally which
    // crushed the postmortem column to ~0px tall on phones, hiding
    // the entire brief.
    <div
      className="
        lg:h-full
        grid lg:overflow-hidden
        grid-cols-1 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]
        lg:grid-rows-[minmax(0,1fr)]
      "
    >
      {/* LEFT - postmortem.
            Padding: aggressive on desktop, tight on mobile so prose
            doesn't have a 56px gutter eating half the viewport.
            `overflow-y-auto` only kicks in at lg+ where the column
            has a bounded height; on mobile the column grows to fit. */}
      <div className="px-5 sm:px-8 lg:px-14 pt-6 lg:pt-12 pb-6 lg:pb-8 lg:overflow-y-auto flex flex-col gap-7">
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

        {(caseData.demoMode || caseData.isDemoV2) && (
          <DemoBanner
            mode={caseData.demoMode ?? (caseData.isDemoV2 ? "v2" : null)}
            loggedInEmail={caseData.loggedInEmail}
          />
        )}

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
          ledger (with results + external refs) once the case closes.
          On mobile this stacks UNDER the brief - so it gets a top
          border instead of a left border, and slimmer paddings. */}
      <div
        className="
          pt-8 lg:pt-12 pb-6 lg:pb-8
          px-5 sm:px-8 lg:pl-11 lg:pr-14
          flex flex-col
          border-t lg:border-t-0 lg:border-l
        "
        style={{ borderColor: "var(--color-rule-soft)" }}
      >
        <Eyebrow>
          {isClosed ? "Actions fired" : "Suggested actions"}
        </Eyebrow>

        <ol className="mt-7 space-y-4 flex-1 lg:min-h-0 lg:overflow-y-auto">
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
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-5">
                {(["Escalate", "Hold", "Deny"] as const).map((verb) => {
                  const key = verb.toLowerCase() as "deny" | "hold" | "escalate";
                  const pending = verdictPending === key;
                  const disabled = verdictPending !== null;
                  return (
                    <button
                      key={verb}
                      type="button"
                      onClick={() => onVerdict(key)}
                      disabled={disabled}
                      className="text-[13.5px] outline-none hover:opacity-80 transition-opacity bg-transparent border-0 p-0 inline-flex items-center gap-1.5"
                      style={{
                        color:
                          verb === "Deny"
                            ? "var(--color-danger)"
                            : "var(--color-ink-muted)",
                        cursor: disabled ? "default" : "pointer",
                        opacity: disabled && !pending ? 0.4 : 1,
                      }}
                    >
                      {pending && (
                        <Loader2 size={11} strokeWidth={2.2} className="animate-spin" />
                      )}
                      {verb}
                    </button>
                  );
                })}
              </div>
              {verdictError && (
                <span
                  className="text-[11px]"
                  style={{
                    fontFamily: "Geist Mono, ui-monospace, monospace",
                    color: "var(--color-danger)",
                    letterSpacing: "0.02em",
                    maxWidth: 320,
                  }}
                  title={verdictError}
                >
                  {verdictError}
                </span>
              )}
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

// ──────────────────────────────────────────────────────────────────────
// DemoBanner - shown above the brief when the case landed via either
// guided demo (v2 = email + Maya Patel, v3 = Slack + Vermillion). The
// copy adapts by mode so the user knows why the case prose references
// a seeded customer instead of their own account.
// ──────────────────────────────────────────────────────────────────────

function DemoBanner({
  mode,
  loggedInEmail,
}: {
  mode: "v2" | "v3" | null;
  loggedInEmail?: string;
}) {
  if (!mode) return null;
  const isV3 = mode === "v3";
  const seededCustomer = isV3 ? "Vermillion Studios" : "Maya Patel Design";
  const seededEmail = isV3 ? null : "hitakshi220@gmail.com";
  const triggerWord = isV3 ? "Slack mention" : "demo email";
  const triggerOrigin = isV3
    ? "the ManthanDemo workspace"
    : "your own inbox";
  const replyDestination = isV3
    ? "the Slack thread where you posted the mention"
    : "your own inbox instead of Maya's";
  return (
    <div
      style={{
        background: "rgba(22,208,94,0.06)",
        border: "1px solid rgba(22,208,94,0.30)",
        borderLeft: "3px solid rgba(22,208,94,0.85)",
        borderRadius: 4,
        padding: "10px 14px",
        marginBottom: 18,
        fontSize: 12.5,
        lineHeight: 1.55,
        color: "var(--color-ink-muted)",
        fontFamily: "Geist, ui-sans-serif, sans-serif",
        maxWidth: "60ch",
      }}
    >
      <div
        style={{
          fontSize: 9.5,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "rgba(22,208,94,0.95)",
          fontWeight: 600,
          marginBottom: 4,
        }}
      >
        Demo · why this case mentions {seededCustomer}
      </div>
      Manthan needs real billing records to investigate against. Your{" "}
      {triggerWord}
      {loggedInEmail ? (
        <>
          {" "}from <strong style={{ color: "var(--color-ink-strong)" }}>
            {loggedInEmail}
          </strong>
        </>
      ) : null}
      {" "}— sent from {triggerOrigin} — was matched to a seeded customer in
      the test environment: "{seededCustomer}"
      {seededEmail ? <> / <code>{seededEmail}</code></> : null} — so the
      agent could pull actual Stripe + Notion + HubSpot records to
      reason against. The decision, the policy match, and the resulting
      actions all genuinely fire; the reply just lands in{" "}
      {replyDestination}.
    </div>
  );
}

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
 * when the chip arrives with only the structural triple (older briefs
 * or sources the backend hasn't been taught to deep-link yet). Returns
 * null when we can't safely build a URL so the chip stays a plain span
 * instead of becoming a dead link.
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

  // Placeholder refs ("finding/3", "evidence/12") are agent-internal
  // accumulator pointers - they don't map to anything in the upstream
  // source. Don't pretend they do; the chip stays a plain span.
  if (/^(finding|evidence)\//i.test(ref)) return null;

  // Shape predicates - used both by the typed-table branches and the
  // bare-ref fallback below so a finding can carry just the id.
  const looksLikeNotionUuid = /^[0-9a-f]{32}$|^[0-9a-f-]{36}$/i.test(ref);
  const looksLikeStripeId = /^(du|ch|cus|pi|py|in|re|sub|prod|evt)_/.test(ref);
  const looksLikeAllDigits = /^\d+$/.test(ref);

  if (src === "stripe") {
    if (tbl === "disputes" || ref.startsWith("du_")) {
      return `https://dashboard.stripe.com/test/disputes/${ref}`;
    }
    if (
      tbl === "charges" ||
      tbl === "payments" ||
      tbl === "payment_intents" ||
      ref.startsWith("ch_") ||
      ref.startsWith("pi_") ||
      ref.startsWith("py_")
    ) {
      return `https://dashboard.stripe.com/test/payments/${ref}`;
    }
    if (tbl === "customers" || ref.startsWith("cus_")) {
      return `https://dashboard.stripe.com/test/customers/${ref}`;
    }
    if (ref.startsWith("in_")) return `https://dashboard.stripe.com/test/invoices/${ref}`;
    if (ref.startsWith("re_")) return `https://dashboard.stripe.com/test/refunds/${ref}`;
    if (ref.startsWith("sub_"))
      return `https://dashboard.stripe.com/test/subscriptions/${ref}`;
    // Bare ref without prefix - search Stripe directly.
    if (looksLikeStripeId) {
      return `https://dashboard.stripe.com/test/search?query=${encodeURIComponent(ref)}`;
    }
    return null;
  }

  if (src === "hubspot") {
    if (tbl === "companies" || ref.startsWith("company/")) {
      const id = ref.replace(/^company\//, "");
      return `https://app.hubspot.com/contacts/portalId/company/${id}`;
    }
    if (tbl === "contacts" || ref.startsWith("contact/")) {
      const id = ref.replace(/^contact\//, "");
      return `https://app.hubspot.com/contacts/portalId/contact/${id}`;
    }
    // Bare ~10-digit HubSpot id - assume company (the most common
    // citation kind on a chargeback brief).
    if (looksLikeAllDigits && ref.length >= 6) {
      return `https://app.hubspot.com/contacts/portalId/company/${ref}`;
    }
    return null;
  }

  if (src === "notion") {
    if (tbl === "pages" || ref.startsWith("page/") || looksLikeNotionUuid) {
      const raw = ref.replace(/^page\//, "");
      // Notion's URL slug uses the 32-char id with no dashes.
      const id = raw.replace(/-/g, "");
      return `https://www.notion.so/${id}`;
    }
    return null;
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
    if (tbl === "events" || looksLikeAllDigits) {
      return `https://app.datadoghq.com/event/event?id=${encodeURIComponent(ref)}`;
    }
    return null;
  }

  if (src === "intercom") {
    const ws =
      (import.meta.env.VITE_INTERCOM_WORKSPACE as string | undefined) || "_";
    if (tbl === "conversations" || ref.startsWith("conv/")) {
      const id = ref.replace(/^conv\//, "");
      return `https://app.intercom.com/a/apps/${ws}/inbox/conversation/${id}`;
    }
    if (tbl === "contacts" || ref.startsWith("contact/")) {
      const id = ref.replace(/^contact\//, "");
      return `https://app.intercom.com/a/apps/${ws}/users/${id}`;
    }
    // Bare hex contact-id shape (24 chars) - treat as a contact.
    if (/^[0-9a-f]{24}$/i.test(ref)) {
      return `https://app.intercom.com/a/apps/${ws}/users/${ref}`;
    }
    return null;
  }

  if (src === "zendesk") {
    const sub =
      (import.meta.env.VITE_ZENDESK_SUBDOMAIN as string | undefined) ||
      "minylabs";
    if (tbl === "tickets" || ref.startsWith("ticket/")) {
      return `https://${sub}.zendesk.com/agent/tickets/${ref.replace(/^ticket\//, "")}`;
    }
    if (tbl === "users" || ref.startsWith("user/")) {
      return `https://${sub}.zendesk.com/agent/users/${ref.replace(/^user\//, "")}`;
    }
    // Bare short-number → assume ticket id.
    if (looksLikeAllDigits && ref.length <= 8) {
      return `https://${sub}.zendesk.com/agent/tickets/${ref}`;
    }
    return null;
  }

  if (src === "pagerduty") {
    const sub =
      (import.meta.env.VITE_PAGERDUTY_SUBDOMAIN as string | undefined) || "app";
    if (tbl === "incidents" || ref.startsWith("incident/")) {
      return `https://${sub}.pagerduty.com/incidents/${ref.replace(/^incident\//, "")}`;
    }
    return null;
  }

  if (src === "slack") {
    // Slack permalinks need workspace + channel + ts; without them we
    // leave the chip non-clickable rather than land in a generic
    // search page that doesn't help.
    return null;
  }

  if (src === "posthog") {
    const proj =
      (import.meta.env.VITE_POSTHOG_PROJECT as string | undefined) || "";
    if (!proj) return null;
    if (tbl === "events" || tbl === "event") {
      return `https://us.posthog.com/project/${proj}/events/${encodeURIComponent(ref)}`;
    }
    if (tbl === "persons" || tbl === "person") {
      return `https://us.posthog.com/project/${proj}/persons/${encodeURIComponent(ref)}`;
    }
    return null;
  }

  if (src === "salesforce") {
    const inst =
      (import.meta.env.VITE_SALESFORCE_INSTANCE as string | undefined) ||
      null;
    if (!inst) return null;
    return `https://${inst}/lightning/r/${ref}/view`;
  }

  // Unknown source - leave the chip dead rather than sending the
  // operator to a Google search that has nothing to do with the brief.
  return null;
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

