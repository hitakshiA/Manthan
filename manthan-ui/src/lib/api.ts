/**
 * Manthan API client.
 *
 * Talks to the backend at MANTHAN_API_URL (Vite env var) with the dev-org
 * header X-Manthan-Dev-Org until Clerk JWT verification is wired.
 */

// `??` (not `||`) so an explicit empty string survives — in prod we set
// VITE_MANTHAN_API_URL="" so fetches go to relative /api/* (same origin),
// and Caddy reverse-proxies to the local API. With `||`, "" was falsy
// and we fell back to localhost:8765 from the browser → CORS hellscape.
const API_URL =
  (import.meta.env.VITE_MANTHAN_API_URL as string | undefined) ??
  "http://127.0.0.1:8765";

const DEV_ORG_SLUG =
  (import.meta.env.VITE_MANTHAN_DEV_ORG as string | undefined) || "acme";

// ──────────────────────────────────────────────────────────────────────
// Wire types - mirror what the Python API returns
// ──────────────────────────────────────────────────────────────────────

export type CaseStatus =
  | "investigating"
  | "awaiting_approval"
  | "acting"
  | "resolved"
  | "errored"
  | "escalated";

export type TriggerSurface =
  | "stripe_webhook"
  | "inbound_email"
  | "slack_mention"
  | "cron"
  | "web_new"
  | "api";

export type CaseType =
  | "chargeback"
  | "refund_request"
  | "sla_credit"
  | "failed_renewal"
  | "invoice_dispute"
  | "other";

export type DecisionAction =
  | "refund"
  | "fight"
  | "partial_credit"
  | "escalate"
  | "accept";

export interface ApiCitation {
  source: string;
  table: string;
  ref: string;
  field?: string;
  /** Deep-link URL to the source record (e.g. dashboard.stripe.com/.../{id}).
      Null when the source isn't deep-linkable or env config is missing. */
  url?: string | null;
}

export interface ApiFinding {
  id: string;
  seq: number;
  text: string;
  confidence: number | null;
  citations: ApiCitation[];
  created_at: string;
}

export interface ApiCase {
  id: string;
  org_id: string;
  short_id: string;
  status: CaseStatus;
  trigger_surface: TriggerSurface;
  case_type: CaseType | null;
  customer_ref: string | null;
  amount_minor: number | null;
  currency: string;
  decision_action: DecisionAction | null;
  decision_amount_minor: number | null;
  decision_confidence: number | null;
  assigned_member_id: string | null;
  created_at: string;
  resolved_at: string | null;
  findings?: ApiFinding[];
  brief?: ApiBriefSummary | null;
  policy_match?: ApiPolicyMatchSummary | null;
  /** One-line Gemini-Flash-written summary for the inbox cards.
   *  Populated by `listCases`, null on detail fetches. */
  card_summary?: string | null;
}

export interface ApiBriefSummary {
  tldr: string | null;
  decision_rationale: string | null;
  decision_action: string | null;
  decision_amount_minor: number | null;
  decision_confidence: number | null;
  hitl_question: string | null;
  generated_at: string | null;
}

export interface ApiPolicyMatchSummary {
  rule_name: string;
  mode: "auto" | "suggest" | "escalate" | string;
  matched_at: string;
}

export interface ApiCaseList {
  cases: ApiCase[];
  total: number;
}

// ──────────────────────────────────────────────────────────────────────
// Low-level fetch wrapper
// ──────────────────────────────────────────────────────────────────────

// Module-level user-email cache. ClerkIdentitySync writes here whenever
// the Clerk session changes; every API call threads it as
// X-Manthan-Dev-Email so the backend's dev tenant resolver can map to
// the right member row (and upsert if absent). Null when no Clerk user
// is signed in - backend falls back to oldest-admin in that case.
let API_USER_EMAIL: string | null = null;

export function setApiUserEmail(email: string | null | undefined): void {
  API_USER_EMAIL = email ?? null;
}

export function getApiUserEmail(): string | null {
  return API_USER_EMAIL;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Manthan-Dev-Org": DEV_ORG_SLUG,
    ...((init?.headers as Record<string, string>) || {}),
  };
  if (API_USER_EMAIL) {
    headers["X-Manthan-Dev-Email"] = API_USER_EMAIL;
  }
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    let detail: string;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      detail = await res.text();
    }
    throw new Error(`API ${res.status} on ${path}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ──────────────────────────────────────────────────────────────────────
// Endpoints
// ──────────────────────────────────────────────────────────────────────

export interface ListCasesOptions {
  scope?: "all" | "mine" | "watching";
  status?: CaseStatus;
  limit?: number;
  offset?: number;
}

export async function listCases(opts: ListCasesOptions = {}): Promise<ApiCaseList> {
  const params = new URLSearchParams();
  if (opts.scope) params.set("scope", opts.scope);
  if (opts.status) params.set("status", opts.status);
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.offset) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return call<ApiCaseList>(`/api/cases${qs ? `?${qs}` : ""}`);
}

export async function getCase(caseId: string): Promise<ApiCase> {
  return call<ApiCase>(`/api/cases/${caseId}`);
}

export interface CreateCasePayload {
  trigger_text: string;
  case_type?: CaseType;
  customer_ref?: string;
  amount_minor?: number;
  currency?: string;
  metadata?: Record<string, unknown>;
}

export async function createCase(payload: CreateCasePayload): Promise<ApiCase> {
  return call<ApiCase>("/api/cases", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ──────────────────────────────────────────────────────────────────────
// Actions: approve / hold / chat / list
// ──────────────────────────────────────────────────────────────────────

export interface ApiActionRow {
  id: string;
  seq: number;
  kind: string;
  status:
    | "drafted"
    | "awaiting_approval"
    | "approved"
    | "executing"
    | "succeeded"
    | "failed"
    | "drift";
  payload: Record<string, unknown>;
  external_ref: string | null;
  error_message: string | null;
  approved_by: string | null;
}

export async function listCaseActions(caseId: string): Promise<ApiActionRow[]> {
  return call<ApiActionRow[]>(`/api/cases/${caseId}/actions`);
}

export async function approveCase(
  caseId: string,
  actionIds?: string[],
): Promise<{ approved: { id: string; kind: string; status: string }[] }> {
  return call(`/api/cases/${caseId}/approve`, {
    method: "POST",
    body: JSON.stringify({ action_ids: actionIds ?? null }),
  });
}

export async function denyCase(caseId: string, reason: string): Promise<void> {
  await call<void>(`/api/cases/${caseId}/deny`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function escalateCase(
  caseId: string,
  reason?: string,
  to?: string,
): Promise<void> {
  await call<void>(`/api/cases/${caseId}/escalate`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null, to: to ?? null }),
  });
}

export async function holdCase(caseId: string): Promise<void> {
  await fetch(`${API_URL}/api/cases/${caseId}/hold`, {
    method: "POST",
    headers: { "X-Manthan-Dev-Org": DEV_ORG_SLUG },
  });
}

export async function chatWithCase(
  caseId: string,
  message: string,
  intent: "question" | "edit_request" | "re_investigate" | "general" = "general",
): Promise<{ queued: boolean }> {
  return call(`/api/cases/${caseId}/chat`, {
    method: "POST",
    body: JSON.stringify({ message, intent }),
  });
}

// ──────────────────────────────────────────────────────────────────────
// Live investigation narrative - one paragraph + interim findings,
// synthesized server-side by feeding the last 25 events to a fast LLM.
// Polled every 6s while a case is investigating.
// ──────────────────────────────────────────────────────────────────────

export interface InvestigationNarrative {
  narrative: string;
  findings: string[];
  events_processed: number;
  max_seq: number;
  cached: boolean;
}

export async function getInvestigationNarrative(
  caseId: string,
): Promise<InvestigationNarrative> {
  return call(`/api/cases/${caseId}/narrative`);
}

// ──────────────────────────────────────────────────────────────────────
// Clicky citation reasoning - the "why this matters" popup.
//
// Each click on a citation chip in the Brief asks the backend for a
// 2-3 sentence explanation. The backend caches in `citation_reasonings`
// so repeated clicks don't pay the LLM cost.
// ──────────────────────────────────────────────────────────────────────

export interface CitationReasoning {
  source: string;
  table: string;
  ref: string;
  field: string | null;
  url: string | null;
  reasoning: string;
  model: string | null;
  generated_at: string;
  cached: boolean;
}

export async function fetchCitationReasoning(
  caseId: string,
  body: { source: string; table: string; ref: string; field?: string | null },
): Promise<CitationReasoning> {
  return call(`/api/cases/${caseId}/citations/reasoning`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listCitationReasonings(
  caseId: string,
): Promise<{ reasonings: CitationReasoning[] }> {
  return call(`/api/cases/${caseId}/citations`);
}

// ──────────────────────────────────────────────────────────────────────
// Inbound email - for the "Original email" panel in the workspace.
// 404s when the case wasn't opened via email; callers should treat that
// as "no panel to show" rather than an error.
// ──────────────────────────────────────────────────────────────────────

export interface TriggerEmail {
  from_addr: string;
  from_name: string;
  subject: string;
  received_at: string;
  message_id: string;
  text: string;
  html: string;
}

export async function fetchTriggerEmail(caseId: string): Promise<TriggerEmail | null> {
  try {
    return await call<TriggerEmail>(`/api/cases/${caseId}/trigger_email`);
  } catch (e) {
    // 404 means the case wasn't email-triggered.
    if ((e as Error).message.includes("404")) return null;
    throw e;
  }
}

// ──────────────────────────────────────────────────────────────────────
// Org-scoped metrics for AppShell sidebar + TopBar
// ──────────────────────────────────────────────────────────────────────

export interface DashboardMetrics {
  inbox_count: number;
  active_count: number;
  done_count: number;
  escalated_count: number;
  errored_count: number;
  awaiting_count: number;
  sources_count: number;
  recovered_this_month_minor: number;
}

export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  return call<DashboardMetrics>("/api/metrics/dashboard");
}

// ──────────────────────────────────────────────────────────────────────
// Policy
// ──────────────────────────────────────────────────────────────────────

export interface ApiPolicyRule {
  id: string;
  name: string;
  description: string | null;
  conditions: Record<string, unknown>;
  decision: Record<string, unknown>;
  priority: number;
  enabled: boolean;
  match_count_90d: number;
}

export interface ApiPolicyMatch {
  id: string;
  case_short_id: string;
  case_id: string;
  rule_name: string;
  mode: "auto" | "recommend" | "hitl";
  matched_at: string;
  decision_action: string | null;
}

export async function listPolicyRules(): Promise<ApiPolicyRule[]> {
  return call<ApiPolicyRule[]>("/api/policy/rules");
}

export async function listPolicyMatches(limit = 50): Promise<ApiPolicyMatch[]> {
  return call<ApiPolicyMatch[]>(`/api/policy/matches?limit=${limit}`);
}

export async function togglePolicyRule(ruleId: string, enabled: boolean): Promise<ApiPolicyRule> {
  return call<ApiPolicyRule>(`/api/policy/rules/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export interface CreatePolicyRulePayload {
  name: string;
  description?: string;
  conditions: Record<string, unknown>;
  decision: Record<string, unknown>;
  priority?: number;
  enabled?: boolean;
}

export async function createPolicyRule(
  payload: CreatePolicyRulePayload,
): Promise<ApiPolicyRule> {
  return call<ApiPolicyRule>(`/api/policy/rules`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}


// ──────────────────────────────────────────────────────────────────────
// Memory (per-customer episodic recall)
// ──────────────────────────────────────────────────────────────────────

export interface CustomerMemoryRow {
  customer_ref: string;
  total_cases: number;
  resolved: number;
  awaiting: number;
  investigating: number;
  escalated: number;
  refunds: number;
  fights: number;
  refunded_total_minor: number;
  last_seen: string | null;
}

export async function listMemoryCustomers(): Promise<{ customers: CustomerMemoryRow[] }> {
  return call(`/api/memory/customers`);
}

export interface CustomerCaseRow {
  id: string;
  short_id: string;
  status: string;
  case_type: string | null;
  trigger_surface: string;
  decision_action: string | null;
  decision_amount_minor: number | null;
  amount_minor: number | null;
  currency: string;
  created_at: string;
  resolved_at: string | null;
}

export async function getCustomerCases(
  customerRef: string,
): Promise<{ customer_ref: string; cases: CustomerCaseRow[] }> {
  return call(`/api/memory/customers/${encodeURIComponent(customerRef)}/cases`);
}


// ──────────────────────────────────────────────────────────────────────
// Metrics timeseries
// ──────────────────────────────────────────────────────────────────────

export interface MetricsDay {
  day: string;
  opened: number;
  resolved: number;
  refunds: number;
  fights: number;
  escalates: number;
  recovered_minor: number;
}

export async function getMetricsTimeseries(days = 30): Promise<{ days: MetricsDay[] }> {
  return call(`/api/metrics/timeseries?days=${days}`);
}


// ──────────────────────────────────────────────────────────────────────
// Cross-case agent chat
// ──────────────────────────────────────────────────────────────────────

export interface AgentChatResponse {
  reply: string;
  cases_seen: number;
}

export async function sendAgentChat(message: string): Promise<AgentChatResponse> {
  return call(`/api/chat`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

// ──────────────────────────────────────────────────────────────────────
// Audit
// ──────────────────────────────────────────────────────────────────────

export interface ApiAuditEvent {
  id: number;
  seq: number;
  type: string;
  actor: string;
  data: Record<string, unknown>;
  summary: string | null;
  created_at: string;
  case_id: string;
  case_short_id: string;
  customer_ref: string | null;
  amount_minor: number | null;
}

export async function listAuditRecent(limit = 200): Promise<ApiAuditEvent[]> {
  return call<ApiAuditEvent[]>(`/api/audit/recent?limit=${limit}`);
}

// ──────────────────────────────────────────────────────────────────────
// View-shape helpers - map API rows to the Dashboard's local types
// ──────────────────────────────────────────────────────────────────────

const CASE_TYPE_LABEL: Record<CaseType, string> = {
  chargeback: "Chargeback",
  refund_request: "Refund request",
  sla_credit: "SLA credit",
  failed_renewal: "Failed renewal",
  invoice_dispute: "Invoice dispute",
  other: "Case",
};

const TRIGGER_TO_SOURCE: Record<TriggerSurface, string> = {
  stripe_webhook: "stripe",
  inbound_email: "gmail",
  slack_mention: "slack",
  cron: "manthan",
  web_new: "manthan",
  api: "manthan",
};

export function formatAmount(minor: number | null | undefined, currency = "usd"): string {
  if (minor === null || minor === undefined) return "";
  const value = minor / 100;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatAge(createdAt: string): string {
  const ms = Date.now() - new Date(createdAt).getTime();
  const mins = Math.max(0, Math.floor(ms / 60_000));
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

export function caseTypeLabel(t: CaseType | null): string {
  return CASE_TYPE_LABEL[t ?? "other"];
}

export function triggerToSource(t: TriggerSurface): string {
  return TRIGGER_TO_SOURCE[t];
}

export function humanizeTrigger(s: string): string {
  return (
    {
      stripe_webhook: "Stripe webhook",
      inbound_email: "Email to support@",
      manual_slack: "Slack mention",
      slack_mention: "Slack mention",
      cron: "Scheduled scan",
      cron_proactive: "Scheduled scan",
      web_new: "Manual (web)",
      manual_web: "Manual (web)",
      api: "API call",
      intercom_ticket: "Intercom ticket",
    }[s] ?? s.replace(/_/g, " ")
  );
}


// ──────────────────────────────────────────────────────────────────────
// Action rendering - translate an ApiActionRow into a human card
// ──────────────────────────────────────────────────────────────────────

/** Map an action kind + payload into a 1-line title for the UI card. */
export function actionTitle(row: ApiActionRow): string {
  const p = row.payload || {};
  switch (row.kind) {
    case "stripe_refund": {
      const minor = (p.amount_minor as number | undefined) ?? null;
      const charge = (p.charge as string | undefined) ?? "";
      const amt = minor != null ? `$${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}` : "";
      return `Refund ${amt}${charge ? ` on ${shortRef(charge)}` : ""} via Stripe`.replace(/\s+/g, " ").trim();
    }
    case "stripe_dispute_response": {
      const dispute = (p.dispute as string | undefined) ?? "";
      return `Submit dispute evidence${dispute ? ` to ${shortRef(dispute)}` : ""} via Stripe`;
    }
    case "customer_email": {
      const subj = (p.subject as string | undefined) ?? "";
      return subj ? `Email customer - ${subj}` : "Email customer";
    }
    case "notion_decision_log": {
      const title = (p.title as string | undefined) ?? "";
      return title ? `Notion log - ${title.slice(0, 80)}` : "Append Notion decision log";
    }
    case "slack_brief": {
      const channel = (p.channel as string | undefined) ?? "";
      return channel ? `Slack post - #${channel}` : "Post brief to Slack";
    }
    case "linear_issue": {
      const t = (p.title as string | undefined) ?? "";
      return t ? `Linear ticket - ${t.slice(0, 80)}` : "Create Linear ticket";
    }
    case "hubspot_note": {
      return "Append HubSpot CRM note";
    }
    default:
      return row.kind.replace(/_/g, " ");
  }
}

/** Map a kind + payload into the second-line "target" (API/source endpoint, ref ids). */
export function actionTarget(row: ApiActionRow): string {
  const p = row.payload || {};
  switch (row.kind) {
    case "stripe_refund": {
      const charge = (p.charge as string | undefined) ?? "-";
      return `POST /v1/refunds · ${charge}`;
    }
    case "stripe_dispute_response": {
      const dispute = (p.dispute as string | undefined) ?? "-";
      const submit = (p.submit as boolean | undefined) ?? false;
      return `POST /v1/disputes/${dispute}${submit ? " (submit=true)" : " (submit=false · draft)"}`;
    }
    case "customer_email": {
      const to = (p.to as string | undefined) ?? "-";
      return `POST resend/emails · to=${to}`;
    }
    case "notion_decision_log": {
      const parent = (p.parent_page_id as string | undefined) ?? "";
      return parent ? `notion.children.append · ${shortRef(parent)}` : "notion.children.append";
    }
    case "slack_brief": {
      const ch = (p.channel as string | undefined) ?? "-";
      return `chat.postMessage · #${ch}`;
    }
    case "linear_issue":
      return "linear.issueCreate";
    case "hubspot_note":
      return "hubspot.engagements.create";
    default:
      return row.kind;
  }
}

/** Map a kind + payload into a 1-2 sentence "body" describing what the action does. */
export function actionBody(row: ApiActionRow): string {
  const p = row.payload || {};
  switch (row.kind) {
    case "stripe_refund": {
      const reason = (p.reason as string | undefined) ?? "requested_by_customer";
      const meta = (p.metadata as Record<string, unknown> | undefined) ?? {};
      const sid = meta && typeof meta === "object" ? (meta as Record<string, string>).manthan_case_short_id : undefined;
      return `Refund reason: ${reason}${sid ? ` · case ${sid}` : ""}.`;
    }
    case "stripe_dispute_response": {
      const evidence = p.evidence as Record<string, unknown> | undefined;
      const text = evidence?.uncategorized_text as string | undefined;
      return text ? text.slice(0, 220) : "Submit evidence packet to Stripe based on the brief.";
    }
    case "customer_email": {
      const body = (p.body_text as string | undefined) ?? "";
      return body.slice(0, 280);
    }
    case "notion_decision_log": {
      const body = (p.body as string | undefined) ?? "";
      return body.slice(0, 280);
    }
    case "slack_brief": {
      return (p.text as string | undefined) ?? "Brief post";
    }
    default:
      try {
        return JSON.stringify(p).slice(0, 280);
      } catch {
        return "";
      }
  }
}

/** Build a deep-link URL to the source where the executed action landed. */
export function actionExternalUrl(row: ApiActionRow): string | null {
  if (!row.external_ref) return null;
  const ref = row.external_ref;
  switch (row.kind) {
    case "stripe_refund":
      return `https://dashboard.stripe.com/test/refunds/${ref}`;
    case "stripe_dispute_response":
      return `https://dashboard.stripe.com/test/disputes/${ref}`;
    case "customer_email":
      return `https://resend.com/emails/${ref}`;
    case "notion_decision_log":
      // Notion page id → url with hyphens stripped
      return `https://www.notion.so/${ref.replace(/-/g, "")}`;
    case "slack_brief":
      return null; // ts isn't enough to deep-link without channel id
    case "linear_issue":
      return `https://linear.app/issue/${ref}`;
    default:
      return null;
  }
}

function shortRef(ref: string): string {
  if (ref.length <= 16) return ref;
  return `${ref.slice(0, 6)}…${ref.slice(-4)}`;
}


// ──────────────────────────────────────────────────────────────────────
// Demo triggers - dev-only endpoint that synthesizes case_opened events
// against the pre-seeded scenarios. Useful for in-UI "fire scenario"
// buttons during the recording.
// ──────────────────────────────────────────────────────────────────────

export interface DemoScenario {
  id: string;
  label: string;
  surface: string;
}

export interface DemoTriggerResponse {
  case_id: string;
  short_id: string;
  scenario: string;
}

export async function listDemoScenarios(): Promise<{ scenarios: DemoScenario[] }> {
  return call(`/api/demo/scenarios`);
}

/**
 * Fire a demo scenario. Optionally plumbs the operator's own login
 * email as `demo_email_to`, which (a) routes the customer_email action
 * to that exact inbox with no [demo →] subject prefix, and (b) forces
 * the case to require manual approval - policy auto-approval is
 * skipped so the operator gets to approve the brief before the email
 * actually fires.
 */
export async function triggerDemoScenario(
  id: string,
  opts?: { demoEmailTo?: string | null },
): Promise<DemoTriggerResponse> {
  const body =
    opts?.demoEmailTo
      ? JSON.stringify({ demo_email_to: opts.demoEmailTo })
      : JSON.stringify({});
  return call(`/api/demo/trigger/${encodeURIComponent(id)}`, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
}

export async function resetDemoState(): Promise<void> {
  await call<void>(`/api/demo/reset`, { method: "POST" });
}


// ──────────────────────────────────────────────────────────────────────
// Sources
// ──────────────────────────────────────────────────────────────────────

export interface ApiSource {
  id: string;
  name: string;
  category: string;
  description: string;
  capabilities: ("read" | "write" | "trigger")[];
  oauth: boolean;
  status: "connected" | "available" | "needs_attention";
  last_query_at: string | null;
  queries_total: number;
}

export interface SourcesResponse {
  sources: ApiSource[];
  totals: { configured: number; available: number; total: number };
}

export async function listSources(): Promise<SourcesResponse> {
  return call(`/api/sources`);
}

export interface SourceCoralDetail {
  id: string;
  name: string;
  category: string;
  description: string;
  status: "connected" | "available" | "needs_attention";
  env_vars: { name: string; present: boolean; value_preview: string | null }[];
  tables: string[];
  coral: {
    binary: string;
    transport: string;
    tools: string[];
  };
}

export async function getSourceCoralDetail(
  id: string,
): Promise<SourceCoralDetail> {
  return call(`/api/sources/${encodeURIComponent(id)}/coral`);
}


// ──────────────────────────────────────────────────────────────────────
// Identity (current org + member)
// ──────────────────────────────────────────────────────────────────────

export interface MeResponse {
  org: {
    id: string;
    slug: string;
    name: string;
    plan: string;
    created_at: string | null;
    member_count: number;
  };
  member: {
    id: string;
    email: string;
    role: string;
    initials: string;
    display_name: string;
  };
}

export async function getMe(): Promise<MeResponse> {
  return call(`/api/me`);
}
