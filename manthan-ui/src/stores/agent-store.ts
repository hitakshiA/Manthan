import { create } from "zustand";
import type { AgentEvent, WaitingForUserEvent, PlanCreatedEvent } from "@/types/events";
import type { RenderSpec } from "@/types/render-spec";
import type { ConversationBlock, ArtifactState, ThinkingStep, NumericClaim } from "@/types/conversation";
import { TOOL_BADGES, TOOL_LABELS } from "@/types/conversation";
import { normalizeSpec } from "@/lib/normalize-spec";
import { inferWorkFromTool } from "@/lib/work-inference";

// Force bundler to keep normalizeSpec (prevent tree-shaking)
if (typeof normalizeSpec !== "function") throw new Error("normalizeSpec missing");

export type AgentPhase =
  | "idle"
  | "discovering"
  | "preparing"
  | "thinking"
  | "executing"
  | "waiting_for_user"
  | "waiting_for_plan"
  | "done"
  | "error";

interface AgentState {
  phase: AgentPhase;
  events: AgentEvent[];

  // Conversation stream (new)
  blocks: ConversationBlock[];
  artifact: ArtifactState | null;

  // Existing
  currentTurn: number;
  totalToolCalls: number;
  activeTools: Set<string>;
  elapsedSeconds: number;
  pendingQuestion: WaitingForUserEvent | null;
  pendingPlan: PlanCreatedEvent | null;
  renderSpec: RenderSpec | null;
  agentText: string;
  error: string | null;
  model: string | null;
  /** Live thinking text — updates as agent reasons */
  thinkingText: string;
  /** Progression messages the UI cycles through while a slow tool is
   *  running. The first ladder entry is shown after ~3s, the rest every
   *  ~4s. Reset to [] whenever a new tool fires or a new narrative
   *  arrives. */
  thinkingLadder: string[];
  /** Timestamp (performance.now ms) when the current thinkingText was
   *  set. The ConversationStream uses this to time ladder swaps. */
  thinkingStartedAt: number;
  /** Version counter for the module-level thinking buffer. Every time
   *  a step is pushed or removed, this increments so React re-renders
   *  the live thinking card. Read `getLiveThinking()` for the steps. */
  liveThinkingVersion: number;
  /** `Date.now()` when the live buffer's first step was pushed — used
   *  to show "Working for 12s" etc. in the live card. Zeroed on reset
   *  and after flush. */
  liveThinkingStartedAt: number;
  /** Lineage-carrying numeric claims keyed by metric_ref (or fabricated
   *  id for bare-SQL claims). The conversation component looks up
   *  formatted values here to underline them with a click-to-audit
   *  affordance. */
  numericClaims: NumericClaim[];
  /** Drawer state — the claim currently being inspected, or null. */
  inspectedClaim: NumericClaim | null;
  /** Non-null while a server-side repair pass is in flight for the
   *  current artifact. Cleared by the next ``artifact_created`` /
   *  ``artifact_updated`` event. UI shows a "Polishing dashboard…"
   *  banner in the artifact panel while set. */
  repairingArtifact: { artifact_id: string; reason: string } | null;

  pushEvent: (event: AgentEvent) => void;
  addUserMessage: (text: string) => void;
  setInspectedClaim: (claim: NumericClaim | null) => void;
  /** Drop blocks from ``startIndex`` onward. Used by retry: we
   *  remove the failed turn (the last user_message plus every
   *  block the agent produced in response) so the retry reads as
   *  a replacement, not an accumulation. */
  truncateBlocksFrom: (startIndex: number) => void;
  reset: () => void;
}

/** Snapshot of the module-level thinking buffer — components call this
 *  after subscribing to `liveThinkingVersion` so they always see the
 *  freshest steps. Returns a copy so callers can't mutate the buffer. */
export function getLiveThinking(): ThinkingStep[] {
  return [...thinkingBuffer];
}

// Thinking buffer — groups consecutive tool events into a ThinkingGroup
let thinkingBuffer: ThinkingStep[] = [];
let thinkingStart = 0;
/**
 * Last reasoning narration the agent emitted before (yet-to-arrive) tool
 * call. Attached as `display_label` to the next tool_call step so the
 * UI shows exec-speak ("Pulled Q3 orders by region") instead of the
 * static tool name ("Running SQL query"). Cleared after attach.
 */
let pendingDisplayLabel: string | null = null;

// Tolerant patterns — the canonical marker is ---NEXT---, but models drift
// wildly: ``**NEXT---**``, ``**---NEXT---**``, natural-language headers,
// bolded or not. Accept anything that smells like the chip boundary so the
// three-follow-up UX doesn't fall over every time the model rewords.
const NEXT_HEADER_PATTERNS: RegExp[] = [
  // ---NEXT---, **---NEXT---**, NEXT---, **NEXT---**, and all the
  // variants in between. Optional leading dashes, optional bold
  // wrapping, optional trailing dashes, optional colon.
  /^\s*\**\s*-{0,3}\s*NEXT\s*-{0,3}\s*\**\s*:?\s*$/im,
  /^#+\s*(what to look at next|next steps|follow[- ]?ups?|follow[- ]?up questions?|suggested follow[- ]?ups?)\s*[:.]?\s*$/im,
  /^(what to look at next|next steps|follow[- ]?ups?|follow[- ]?up questions?)\s*[:.]?\s*$/im,
  /^\*\*\s*(what to look at next|next steps|follow[- ]?ups?)\s*\*\*\s*[:.]?\s*$/im,
];

function findMarkerIndex(text: string): { index: number; length: number } | null {
  for (const pattern of NEXT_HEADER_PATTERNS) {
    const match = pattern.exec(text);
    if (match && match.index != null) {
      return { index: match.index, length: match[0].length };
    }
  }
  return null;
}

/** Split a run-on follow-up line like ``A? B? C?`` into three chips.
 *  The model sometimes puts all three questions on a single line; our
 *  newline-only splitter would produce one giant 120-char chip
 *  otherwise. Heuristic: break on ``?`` followed by a space and a
 *  capital letter (sentence boundary). */
function splitQuestionRun(line: string): string[] {
  const parts: string[] = [];
  let buf = "";
  for (let i = 0; i < line.length; i++) {
    buf += line[i];
    if (line[i] === "?") {
      const next = line.slice(i + 1);
      if (next.match(/^\s+[A-Z]/) || next.trim().length === 0) {
        parts.push(buf.trim());
        buf = "";
      }
    }
  }
  if (buf.trim()) parts.push(buf.trim());
  return parts.filter((p) => p.length > 0);
}

function extractFollowups(text: string): string[] | null {
  const hit = findMarkerIndex(text);
  if (!hit) return null;
  const after = text.slice(hit.index + hit.length);
  // First split on newlines. For each resulting line, if it still
  // contains multiple question marks, break on sentence boundaries.
  const rawLines = after
    .split("\n")
    .map((l) => l.replace(/^[-•*\d.)\s]+/, "").trim())
    .filter((l) => l.length > 0 && !/^done$/i.test(l));
  const chips: string[] = [];
  for (const line of rawLines) {
    const qCount = (line.match(/\?/g) || []).length;
    if (qCount >= 2) {
      chips.push(...splitQuestionRun(line));
    } else {
      chips.push(line);
    }
    if (chips.length >= 3) break;
  }
  const trimmed = chips
    .map((c) => c.replace(/^\**|\**$/g, "").trim())
    .filter((c) => c.length > 0 && c.length < 200)
    .slice(0, 3);
  return trimmed.length > 0 ? trimmed : null;
}

function splitPreamble(text: string): { preamble: string; hitIndex: number } {
  const hit = findMarkerIndex(text);
  if (!hit) return { preamble: text, hitIndex: -1 };
  return { preamble: text.slice(0, hit.index).trim(), hitIndex: hit.index };
}

function firstSentence(text: string, maxChars = 80): string {
  const trimmed = text.trim();
  const dot = trimmed.search(/[.!?](\s|$)/);
  const candidate = dot > 0 ? trimmed.slice(0, dot) : trimmed;
  return candidate.length > maxChars ? candidate.slice(0, maxChars - 1) + "…" : candidate;
}

/** Push a step into the live buffer and mark that a version bump is
 *  needed so the UI re-renders. Callers must also set
 *  ``patch.liveThinkingVersion`` — we return the next number so they
 *  can do ``patch.liveThinkingVersion = pushStep(state, step)``. */
function pushStep(state: AgentState, step: ThinkingStep): number {
  if (thinkingBuffer.length === 0) thinkingStart = Date.now();
  thinkingBuffer.push(step);
  return state.liveThinkingVersion + 1;
}

function flushThinking(blocks: ConversationBlock[]): ConversationBlock[] {
  if (thinkingBuffer.length === 0) return blocks;

  // Skip thinking group if the only tool calls are emit_visual (the visual renders directly)
  const toolCalls = thinkingBuffer.filter((s) => s.kind === "tool_call");
  const onlyVisuals = toolCalls.length > 0 && toolCalls.every((s) => s.tool === "emit_visual");
  if (onlyVisuals) {
    thinkingBuffer = [];
    return blocks;
  }

  // Auto-generate summary — prefer exec-speak display_label over static tool labels
  const tools = toolCalls
    .filter((s) => s.tool !== "emit_visual") // exclude emit_visual from summary
    .map((s) => s.display_label ?? TOOL_LABELS[s.tool ?? ""] ?? s.tool ?? "working");
  let summary: string;
  if (tools.length > 0) {
    summary = tools.length === 1 ? tools[0] : `${tools[0]} and ${tools.length - 1} more`;
  } else {
    const firstReasoning = thinkingBuffer.find((s) => s.kind === "reasoning");
    summary = firstReasoning?.text.slice(0, 60) ?? "Thinking...";
  }

  const group: ConversationBlock = {
    type: "thinking_group",
    summary,
    steps: [...thinkingBuffer],
    duration_ms: Date.now() - thinkingStart,
  };

  thinkingBuffer = [];
  return [...blocks, group];
}

export const useAgentStore = create<AgentState>((set) => ({
  phase: "idle",
  events: [],
  blocks: [],
  artifact: null,
  currentTurn: 0,
  totalToolCalls: 0,
  activeTools: new Set(),
  elapsedSeconds: 0,
  pendingQuestion: null,
  pendingPlan: null,
  renderSpec: null,
  agentText: "",
  error: null,
  model: null,
  thinkingText: "",
  thinkingLadder: [],
  thinkingStartedAt: 0,
  liveThinkingVersion: 0,
  liveThinkingStartedAt: 0,
  numericClaims: [],
  inspectedClaim: null,
  repairingArtifact: null,

  setInspectedClaim: (claim) => set({ inspectedClaim: claim }),

  addUserMessage: (text) =>
    set((state) => ({
      blocks: [
        ...state.blocks,
        { type: "user_message" as const, text, timestamp: Date.now() },
      ],
      // Scope numeric-claim audit to the current turn. Without this,
      // a coincidental ``$211B`` variant from a prior unrelated
      // question matches first and opens a drawer showing the WRONG
      // SQL (e.g. a surplus/deficit query) under a revenue number.
      // Audit must only reference claims produced by the current
      // answer — conversation memory lives in the agent, not here.
      numericClaims: [],
      inspectedClaim: null,
    })),

  truncateBlocksFrom: (startIndex) =>
    set((state) => ({
      blocks: state.blocks.slice(0, Math.max(0, startIndex)),
      // Drop claims emitted during the failed turn — they're tied to
      // blocks that no longer exist, so keeping them would let a
      // future narrative in this session accidentally wrap a variant
      // from the discarded turn. Audit scope should mirror
      // ``addUserMessage``.
      numericClaims: [],
      inspectedClaim: null,
      repairingArtifact: null,
    })),

  pushEvent: (event) =>
    set((state) => {
      const events = [...state.events, event];
      const patch: Partial<AgentState> = { events };
      let blocks = state.blocks;
      const bufferLenBefore = thinkingBuffer.length;

      switch (event.type) {
        // ── Discovery / preparation (buffer as thinking steps) ──
        case "session_start":
          patch.phase = "discovering";
          patch.model = event.model;
          patch.thinkingText = "Starting analysis...";
          thinkingBuffer = [];
          thinkingStart = Date.now();
          pendingDisplayLabel = null;
          break;

        case "discovering_tables":
          patch.phase = "discovering";
          patch.thinkingText = "Scanning available tables...";
          thinkingBuffer.push({ kind: "reasoning", text: "Scanning available tables..." });
          break;

        case "tables_found":
          patch.phase = "preparing";
          patch.thinkingText = `Found ${event.total} table${event.total !== 1 ? "s" : ""}`;
          thinkingBuffer.push({
            kind: "reasoning",
            text: `Found ${event.total} table${event.total !== 1 ? "s" : ""}`,
          });
          break;

        case "loading_schema":
        case "checking_memory":
          patch.phase = "preparing";
          patch.thinkingText = event.type === "loading_schema" ? "Loading schema..." : "Checking memory...";
          thinkingBuffer.push({
            kind: "reasoning",
            text: event.type === "loading_schema" ? "Loading schema..." : "Checking memory...",
          });
          break;

        case "memory_found":
          patch.phase = "preparing";
          if (event.prior_analyses > 0) {
            thinkingBuffer.push({
              kind: "reasoning",
              text: `Recalled ${event.prior_analyses} prior analysis findings`,
            });
          }
          break;

        // ── Thinking ──
        case "thinking": {
          patch.phase = "thinking";
          patch.thinkingText = event.text.slice(0, 120);
          patch.thinkingLadder = [];
          patch.thinkingStartedAt = performance.now();
          // Stash the first sentence as the display_label for the next
          // tool_start — this is how the agent's exec-speak narration
          // ("Let me pull Q3 orders") becomes the step label instead of
          // the static "Running SQL query".
          pendingDisplayLabel = firstSentence(event.text);
          // Keep the existing behavior: flush buffer, add narrative block
          blocks = flushThinking(blocks);
          blocks = [...blocks, { type: "narrative", text: event.text }];
          patch.blocks = blocks;
          break;
        }

        // ── Tool execution (buffer into thinking group) ──
        case "tool_start": {
          patch.phase = "executing";
          // Infer what the tool is actually doing from its args preview
          // (SARIMAX vs KMeans vs ttest_ind, or ranking vs time-series
          // SQL). Prefer the agent's own exec-speak narration
          // (pendingDisplayLabel) when available, else fall back to the
          // inferred playbook label, else the generic tool name.
          const inferred = inferWorkFromTool(event.tool, event.args_preview);
          patch.thinkingText = pendingDisplayLabel ?? inferred.label;
          patch.thinkingLadder = inferred.ladder;
          patch.thinkingStartedAt = performance.now();
          patch.activeTools = new Set(state.activeTools).add(`${event.tool}_${event.turn}`);
          if (thinkingBuffer.length === 0) thinkingStart = Date.now();
          const step: import("@/types/conversation").ThinkingStep = {
            kind: "tool_call",
            tool: event.tool,
            text: event.args_preview,
            badge: TOOL_BADGES[event.tool],
          };
          // Capture code for SQL and Python tools
          if (event.tool === "run_sql" || event.tool === "run_python") {
            step.code = event.args_preview;
          }
          // Attach exec-speak label from the preceding reasoning narration
          if (pendingDisplayLabel) {
            step.display_label = pendingDisplayLabel;
            pendingDisplayLabel = null;
          }
          thinkingBuffer.push(step);
          break;
        }

        case "tool_complete":
          patch.totalToolCalls = state.totalToolCalls + 1;
          thinkingBuffer.push({
            kind: "tool_result",
            tool: event.tool,
            text: event.preview.slice(0, 100),
            elapsed_ms: event.elapsed_ms,
            success: true,
            output: event.preview,
          });
          break;

        case "tool_error":
          thinkingBuffer.push({
            kind: "tool_result",
            tool: event.tool,
            text: event.error.slice(0, 100),
            success: false,
          });
          break;

        case "turn_complete":
          patch.currentTurn = event.turn;
          patch.activeTools = new Set();
          break;

        // ── SQL result: tucked into the current thinking group ──
        // Raw data pulls, schema dumps, and intermediate table lists are
        // analyst plumbing — the exec should see the narrative, not the
        // SQL output. We still surface the payload inside the expanded
        // thinking group so an analyst-curious user can drill in.
        case "sql_result":
          thinkingBuffer.push({
            kind: "tool_result",
            tool: "run_sql",
            text: `${event.row_count} row${event.row_count !== 1 ? "s" : ""}`,
            elapsed_ms: event.elapsed_ms,
            success: true,
            table: {
              columns: event.columns,
              rows: event.rows as unknown[][],
              row_count: event.row_count,
              truncated: event.truncated,
              query: event.query,
              elapsed_ms: event.elapsed_ms,
            },
          });
          break;

        // ── Narrative (agent's out-loud commentary) ──
        case "narrative": {
          patch.phase = "thinking";
          patch.thinkingText = event.text.slice(0, 120);
          patch.thinkingLadder = [];
          patch.thinkingStartedAt = performance.now();
          // Capture first sentence for the next tool_call's display_label
          // (same pattern as "thinking" — narrative is just longer).
          pendingDisplayLabel = firstSentence(event.text);
          blocks = flushThinking(blocks);
          const chips = extractFollowups(event.text);
          if (chips) {
            // Narrative contains a follow-up block. Render any prose
            // before the marker as narrative, then follow with chips.
            const { preamble } = splitPreamble(event.text);
            if (preamble) {
              blocks = [...blocks, { type: "narrative", text: preamble }];
            }
            blocks = [...blocks, { type: "followup_chips", chips }];
          } else {
            blocks = [...blocks, { type: "narrative", text: event.text }];
          }
          patch.blocks = blocks;
          break;
        }

        // ── Inline visual ──
        case "inline_visual": {
          blocks = flushThinking(blocks);
          blocks = [
            ...blocks,
            {
              type: "inline_visual",
              visual_id: event.visual_id,
              visual_type: event.visual_type,
              html: event.html,
              height: event.height,
            },
          ];
          patch.blocks = blocks;
          break;
        }

        // ── Artifact ──
        case "artifact_created": {
          blocks = flushThinking(blocks);
          const art: ArtifactState = {
            id: event.artifact_id,
            title: event.title,
            code: event.code,
            filename: event.filename,
            versions: [{ code: event.code, timestamp: Date.now() }],
          };
          patch.artifact = art;
          blocks = [
            ...blocks,
            {
              type: "artifact_card",
              artifact_id: event.artifact_id,
              title: event.title,
              filename: event.filename,
            },
          ];
          patch.blocks = blocks;
          // Fresh artifact lands after repair — drop the polishing banner.
          patch.repairingArtifact = null;
          break;
        }

        case "artifact_updated": {
          if (state.artifact) {
            patch.artifact = {
              ...state.artifact,
              code: event.code,
              title: event.title,
              versions: [
                ...state.artifact.versions,
                { code: event.code, timestamp: Date.now() },
              ],
            };
          }
          // Any fresh artifact content supersedes an in-flight repair.
          patch.repairingArtifact = null;
          break;
        }

        case "repairing_artifact": {
          // Server caught a JS parse error and is running a
          // single-shot LLM repair pass. The artifact panel shows a
          // "Polishing dashboard…" banner until the next artifact
          // event clears the flag.
          patch.repairingArtifact = {
            artifact_id: event.artifact_id,
            reason: event.reason,
          };
          break;
        }

        case "numeric_claim": {
          // Phase 3 audit surface. Each numeric claim is a full lineage
          // record tied to the metric definition + SQL that produced it.
          // The ConversationStream renders the formatted value with a
          // click-to-audit underline that opens the CalculationDrawer.
          const variants = event.formatted_variants && event.formatted_variants.length
            ? event.formatted_variants
            : [event.formatted];
          const claim: NumericClaim = {
            value: event.value,
            formatted: event.formatted,
            formatted_variants: variants,
            label: event.label,
            description: event.description ?? null,
            entity: event.entity,
            metric_ref: event.metric_ref,
            filters_applied: event.filters_applied || [],
            dimensions: event.dimensions || [],
            grain: event.grain,
            sql: event.sql,
            row_count_scanned: event.row_count_scanned,
            run_id: event.run_id,
          };
          patch.numericClaims = [...state.numericClaims, claim];
          break;
        }

        // ── HITL ──
        case "waiting_for_user":
          patch.phase = "waiting_for_user";
          patch.pendingQuestion = event;
          blocks = flushThinking(blocks);
          blocks = [
            ...blocks,
            {
              type: "ask_user",
              question_id: event.question_id,
              prompt: event.prompt,
              options: event.options,
              interpretation: event.interpretation,
              why: event.why,
              ambiguity_type: event.ambiguity_type,
            },
          ];
          patch.blocks = blocks;
          break;

        case "user_answered":
          patch.phase = "thinking";
          patch.pendingQuestion = null;
          break;

        case "plan_created":
          patch.phase = "waiting_for_plan";
          patch.pendingPlan = event;
          break;

        case "plan_pending":
          patch.phase = "waiting_for_plan";
          break;

        case "plan_approved":
          patch.phase = "executing";
          patch.pendingPlan = null;
          break;

        case "deciding":
          break;

        case "progress":
          break;

        case "subagent_spawned":
          thinkingBuffer.push({
            kind: "reasoning",
            text: `Spawned agent: ${event.task}`,
          });
          break;

        case "subagent_complete":
          thinkingBuffer.push({
            kind: "reasoning",
            text: `Agent finished: ${event.result?.slice(0, 80) ?? "done"}`,
          });
          break;

        // ── Done ──
        case "done":
          patch.phase = "done";
          patch.elapsedSeconds = event.elapsed_seconds;
          patch.agentText = event.summary;
          patch.thinkingText = "";
          patch.thinkingLadder = [];
          patch.thinkingStartedAt = 0;

          blocks = flushThinking(blocks);
          blocks = [
            ...blocks,
            {
              type: "done",
              summary: event.summary,
              turns: event.turns,
              tool_calls: event.tool_calls,
              elapsed_seconds: event.elapsed_seconds,
            },
          ];
          patch.blocks = blocks;

          // Legacy: if render_spec exists and no artifact was created
          if (event.render_spec && !state.artifact) {
            try {
              patch.renderSpec = normalizeSpec(event.render_spec);
            } catch {
              patch.renderSpec = null;
            }
          }
          break;

        case "error":
          if (!event.recoverable) {
            patch.phase = "error";
            patch.error = event.message;
            blocks = flushThinking(blocks);
            blocks = [
              ...blocks,
              { type: "error", message: event.message, recoverable: false },
            ];
            patch.blocks = blocks;
          }
          break;
      }

      // Bump the live-thinking version on any buffer change so the UI
      // streams steps in as they arrive. We also track the start time
      // the first time the buffer goes from empty → non-empty so the
      // live card can show "Working for 12s".
      const bufferLenAfter = thinkingBuffer.length;
      if (bufferLenAfter !== bufferLenBefore) {
        patch.liveThinkingVersion = state.liveThinkingVersion + 1;
        if (bufferLenBefore === 0 && bufferLenAfter > 0) {
          patch.liveThinkingStartedAt = Date.now();
        } else if (bufferLenAfter === 0) {
          patch.liveThinkingStartedAt = 0;
        }
      }

      return patch;
    }),

  reset: () => {
    thinkingBuffer = [];
    pendingDisplayLabel = null;
    set({
      phase: "idle",
      events: [],
      blocks: [],
      artifact: null,
      currentTurn: 0,
      totalToolCalls: 0,
      activeTools: new Set(),
      elapsedSeconds: 0,
      pendingQuestion: null,
      pendingPlan: null,
      renderSpec: null,
      agentText: "",
      error: null,
      model: null,
      thinkingText: "",
      thinkingLadder: [],
      thinkingStartedAt: 0,
      liveThinkingVersion: 0,
      liveThinkingStartedAt: 0,
      numericClaims: [],
      inspectedClaim: null,
      repairingArtifact: null,
    });
  },
}));
