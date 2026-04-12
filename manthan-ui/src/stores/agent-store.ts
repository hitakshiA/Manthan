import { create } from "zustand";
import type { AgentEvent, WaitingForUserEvent, PlanCreatedEvent } from "@/types/events";
import type { RenderSpec } from "@/types/render-spec";
import { normalizeSpec } from "@/lib/normalize-spec";

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

  pushEvent: (event: AgentEvent) => void;
  reset: () => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  phase: "idle",
  events: [],
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

  pushEvent: (event) =>
    set((state) => {
      const events = [...state.events, event];
      const patch: Partial<AgentState> = { events };

      switch (event.type) {
        case "session_start":
          patch.phase = "discovering";
          patch.model = event.model;
          break;
        case "discovering_tables":
          patch.phase = "discovering";
          break;
        case "tables_found":
        case "loading_schema":
        case "checking_memory":
        case "memory_found":
          patch.phase = "preparing";
          break;
        case "thinking":
          patch.phase = "thinking";
          break;
        case "deciding":
          break;
        case "tool_start":
          patch.phase = "executing";
          patch.activeTools = new Set(state.activeTools).add(
            `${event.tool}_${event.turn}`,
          );
          break;
        case "tool_complete":
          patch.totalToolCalls = state.totalToolCalls + 1;
          break;
        case "tool_error":
          break;
        case "turn_complete":
          patch.currentTurn = event.turn;
          patch.activeTools = new Set();
          break;
        case "waiting_for_user":
          patch.phase = "waiting_for_user";
          patch.pendingQuestion = event;
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
        case "done":
          patch.phase = "done";
          patch.elapsedSeconds = event.elapsed_seconds;
          patch.agentText = event.summary;
          if (event.render_spec) {
            try {
              patch.renderSpec = normalizeSpec(event.render_spec);
            } catch {
              // If normalizer fails, don't set renderSpec — show text instead
              patch.renderSpec = null;
            }
          }
          break;
        case "error":
          if (!event.recoverable) {
            patch.phase = "error";
            patch.error = event.message;
          }
          break;
      }

      return patch;
    }),

  reset: () =>
    set({
      phase: "idle",
      events: [],
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
    }),
}));
