// Demo v3 - guided Slack-Thread wizard.
//
// Mirrors lib/demo-v2.ts but for the Slack-mention flow:
// join the ManthanDemo workspace -> @-mention the bot in
// #all-manthandemo -> watch the case auto-resolve. Identity is bridged
// by users.lookupByEmail: when the operator's logged-in Manthan email
// matches a Slack user in the workspace, the inbound mention routes
// into their personal Manthan org (slack_bot.open_case_from_slack
// does the matching on the backend).

import { call } from "@/lib/api";

// ──────────────────────────────────────────────────────────────────────
// Step model
// ──────────────────────────────────────────────────────────────────────

export type StepId =
  | "intro"
  | "join-workspace"        // open the invite link, join ManthanDemo
  | "verify-join"           // poll check-slack-member until found
  | "send-mention"          // copy canonical mention text + send in #all-manthandemo
  | "case-opened"           // nav to case workspace, watch agent
  | "case-resolved"         // outro
  | "done";

export const STEP_ORDER: StepId[] = [
  "intro",
  "join-workspace",
  "verify-join",
  "send-mention",
  "case-opened",
  "case-resolved",
  "done",
];

// Once they've sent the mention the case is real and server-side; the
// wizard going away doesn't undo it, just abandons the guided overlay.
export const CANCELLABLE_STEPS: ReadonlySet<StepId> = new Set([
  "intro",
  "join-workspace",
  "verify-join",
  "send-mention",
]);

export const NAV_LOCKED_STEPS: ReadonlySet<StepId> = new Set([
  "case-opened",
]);

// ──────────────────────────────────────────────────────────────────────
// Persisted state - distinct key from demo-v2 so they don't collide
// ──────────────────────────────────────────────────────────────────────

const STORAGE_KEY = "manthan_demo_v3_state";
const STALE_AFTER_MS = 30 * 60 * 1000;

export interface DemoV3State {
  step: StepId;
  startedAt: number;
  loggedInEmail: string | null;
  caseId: string | null;
  shortId: string | null;
  waitingStartedAt: number | null;
  slackDisplayName: string | null;
}

const FRESH: DemoV3State = {
  step: "intro",
  startedAt: 0,
  loggedInEmail: null,
  caseId: null,
  shortId: null,
  waitingStartedAt: null,
  slackDisplayName: null,
};

export function loadState(): DemoV3State | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DemoV3State>;
    if (
      !parsed.step ||
      !parsed.startedAt ||
      Date.now() - parsed.startedAt > STALE_AFTER_MS
    ) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return { ...FRESH, ...parsed } as DemoV3State;
  } catch {
    return null;
  }
}

export function saveState(state: DemoV3State): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* noop */
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

export function freshState(loggedInEmail: string): DemoV3State {
  return { ...FRESH, step: "intro", startedAt: Date.now(), loggedInEmail };
}

// ──────────────────────────────────────────────────────────────────────
// API client
// ──────────────────────────────────────────────────────────────────────

export interface DemoV3Template {
  invite_url: string;
  workspace_name: string;
  channel: string;
  bot_handle: string;
  mention_text: string;
  inbound_help: string;
}

export interface CheckSlackMemberResp {
  member: boolean;
  slack_user_id: string | null;
  slack_display_name: string | null;
}

export interface CheckSlackInboundResp {
  matched: boolean;
  case_id: string | null;
  short_id: string | null;
  status: string | null;
  opened_at: string | null;
}

export async function fetchTemplate(): Promise<DemoV3Template> {
  return call<DemoV3Template>("/api/demo-v3/template");
}

export async function checkSlackMember(
  email: string,
): Promise<CheckSlackMemberResp> {
  const q = new URLSearchParams({ email }).toString();
  return call(`/api/demo-v3/check-slack-member?${q}`);
}

export async function checkSlackInbound(
  email: string,
  sinceMs: number,
): Promise<CheckSlackInboundResp> {
  const q = new URLSearchParams({
    slack_email: email,
    since_ms: String(sinceMs),
  }).toString();
  return call(`/api/demo-v3/check-slack-inbound?${q}`);
}

export const POLL_TIMEOUT_MS = 5 * 60 * 1000;
export const POLL_INTERVAL_MS = 3_000;
// Faster poll during verify-join since users.lookupByEmail is cheap
// and we want immediate progression as soon as they accept the invite.
export const VERIFY_POLL_INTERVAL_MS = 2_500;
