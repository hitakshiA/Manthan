// Demo v2 - guided autonomous-email wizard.
//
// Centralised state + API client + step config for the wizard. The
// component (components/demo-v2/DemoV2Wizard.tsx) renders content
// off this; this module stays UI-agnostic.
//
// State lives in localStorage so closing the tab mid-flow leaves a
// resumable session for ~30 minutes. After that the saved state is
// considered stale and we start fresh.

import { call } from "@/lib/api";

// ──────────────────────────────────────────────────────────────────────
// Step model
// ──────────────────────────────────────────────────────────────────────

// The wizard walks the user through real product UI - each step
// spotlights an actual element and waits for the user to interact.
// We DON'T do things for them - they click "New rule", they fill in
// the name, they pick the mode, they hit save. The wizard just coaches.
export type StepId =
  | "intro"                  // center modal, "Welcome, here's what we'll do"
  | "goto-policies"          // spotlight the Policies sidebar link
  | "click-new-rule"         // spotlight the "New rule" button
  | "name-rule"              // spotlight the Name input
  | "set-conditions"         // spotlight the When-conditions block
  | "select-auto-mode"       // spotlight the auto-execute mode button
  | "save-rule"              // spotlight the Create rule button
  | "goto-inbox"             // spotlight the Inbox sidebar link
  | "send-email"             // center modal, 3 copy buttons + mailto
  | "waiting-for-email"      // center modal, 5-min countdown poll
  | "case-opened"            // dim, "watch the agent" floating tip
  | "case-resolved"          // center modal, outro
  | "done";

export const STEP_ORDER: StepId[] = [
  "intro",
  "goto-policies",
  "click-new-rule",
  "name-rule",
  "set-conditions",
  "select-auto-mode",
  "save-rule",
  "goto-inbox",
  "send-email",
  "waiting-for-email",
  "case-opened",
  "case-resolved",
  "done",
];

// Steps where the user can bail out. From `waiting-for-email` onward
// they've sent a real email and the case will land in their inbox
// regardless; cancelling the wizard doesn't undo that.
export const CANCELLABLE_STEPS: ReadonlySet<StepId> = new Set([
  "intro",
  "goto-policies",
  "click-new-rule",
  "name-rule",
  "set-conditions",
  "select-auto-mode",
  "save-rule",
  "goto-inbox",
  "send-email",
]);

// During these steps the sidebar nav + browser-back should be guarded
// so the user actually watches the auto-execute happen instead of
// drifting away mid-investigation.
export const NAV_LOCKED_STEPS: ReadonlySet<StepId> = new Set([
  "waiting-for-email",
  "case-opened",
]);

// ──────────────────────────────────────────────────────────────────────
// Persisted state
// ──────────────────────────────────────────────────────────────────────

const STORAGE_KEY = "manthan_demo_v2_state";
const STALE_AFTER_MS = 30 * 60 * 1000; // 30 minutes

export interface DemoV2State {
  step: StepId;
  startedAt: number;          // ms epoch
  senderEmail: string | null; // user's logged-in email (target for verification)
  caseId: string | null;      // assigned once check-inbound succeeds
  shortId: string | null;
  waitingStartedAt: number | null; // when the poll began (drives countdown)
}

const FRESH: DemoV2State = {
  step: "intro",
  startedAt: 0,
  senderEmail: null,
  caseId: null,
  shortId: null,
  waitingStartedAt: null,
};

export function loadState(): DemoV2State | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DemoV2State>;
    if (
      !parsed.step ||
      !parsed.startedAt ||
      Date.now() - parsed.startedAt > STALE_AFTER_MS
    ) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return { ...FRESH, ...parsed } as DemoV2State;
  } catch {
    return null;
  }
}

export function saveState(state: DemoV2State): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* localStorage full or disabled - silently degrade */
  }
}

export function clearState(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* noop */
  }
}

export function freshState(senderEmail: string): DemoV2State {
  return {
    ...FRESH,
    step: "intro",
    startedAt: Date.now(),
    senderEmail,
  };
}

// ──────────────────────────────────────────────────────────────────────
// API client - thin wrappers around /api/demo-v2/*
// ──────────────────────────────────────────────────────────────────────

export interface DemoV2Template {
  to: string;
  subject: string;
  body: string;
  policy_name: string;
  policy_description: string;
  inbound_help: string;
}

export interface PolicyReadyResp {
  ready: boolean;
  rule_id: string | null;
  rule_name: string | null;
}

export interface CheckInboundResp {
  matched: boolean;
  case_id: string | null;
  short_id: string | null;
  status: string | null;
  opened_at: string | null;
}

export async function fetchTemplate(): Promise<DemoV2Template> {
  return call<DemoV2Template>("/api/demo-v2/template");
}

export async function resetPolicies(): Promise<{ policies_deleted: number }> {
  return call("/api/demo-v2/reset", { method: "POST" });
}

export async function seedPolicy(): Promise<PolicyReadyResp> {
  return call("/api/demo-v2/seed-policy", { method: "POST" });
}

export async function checkPolicyReady(): Promise<PolicyReadyResp> {
  return call("/api/demo-v2/policy-ready");
}

export async function checkInbound(
  sender: string,
  sinceMs: number,
): Promise<CheckInboundResp> {
  const q = new URLSearchParams({
    sender,
    since_ms: String(sinceMs),
  }).toString();
  return call(`/api/demo-v2/check-inbound?${q}`);
}

// ──────────────────────────────────────────────────────────────────────
// Constants the UI uses
// ──────────────────────────────────────────────────────────────────────

// Hard timeout on the inbound poll. Past this, we surface a "didn't
// arrive" affordance and stop polling so the page doesn't zombie.
export const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
export const POLL_INTERVAL_MS = 3_000; // 3s between check-inbound hits
