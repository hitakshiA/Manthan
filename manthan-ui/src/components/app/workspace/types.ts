/**
 * Shared types for the Manthan case workspace.
 *
 * These mirror the data shapes used in HeroShowcase (the marketing
 * showcase) so the live product can use the SAME components.
 *
 * Adapter functions in lib/api.ts convert the raw ApiCase / ApiFinding
 * shapes to the workspace view-models below.
 */

import type { ReactNode } from "react";

export type Tone = "awaiting" | "drafted" | "investigating" | "executing" | "resolved";
export type CaseFilter = "all" | "mine" | "watching";
export type Owner = "you" | string;
export type CaseStatus = "awaiting" | "approving" | "approved" | "held";

export interface WorkspaceCaseRow {
  num: string;                 // "4821" - display short id
  customer: string;
  type: string;                // "Chargeback"
  amount: number;              // dollars (not minor)
  status: Tone;
  ago: string;                 // "2m"
  drafts: number;
  risk?: "low" | "med" | "high";
  owner: Owner;                // "you" if assigned to current member, else email
  watching: boolean;
  caseId: string;              // uuid for routing
  /** Raw API trigger_surface - drives surface-specific affordances
      like the "Original email" button. Optional so older callers
      that built rows by hand still compile. */
  triggerSurface?: string;
}

export interface WorkspaceEvidence {
  n: number;
  src: string;                 // "salesforce" | "stripe" | ...
  record: string;              // e.g. "ch_xxx · $1,200"
  finding: string;             // 1-line summary
  /** Deep-link URL to the source record. If present, the record chip
      becomes clickable and opens the source UI in a new tab. */
  url?: string | null;
  /** Source table (stripe.charges → "charges"). Needed by the clicky
      citation popup to fetch a "why this matters" reasoning. */
  table?: string | null;
  /** Exact ref id passed through to the reasoning lookup. */
  ref?: string | null;
  /** Optional specific aspect within the record (e.g. "amount"). */
  field?: string | null;
}

/** A single recorded finding - text + the citations that back it. The
    Brief postmortem renders these as numbered paragraphs with inline
    citation chips. */
export interface WorkspaceFinding {
  seq: number;
  text: string;
  confidence: number | null;
  /** Indices into the `evidence` array - every citation chip resolves
      to one evidence row so clicking opens the same modal in both places. */
  citationIndices: number[];
}

/** Status of a drafted/in-flight action, mirroring the API's ActionRow.status. */
export type ActionStatus =
  | "drafted"
  | "awaiting_approval"
  | "approved"
  | "executing"
  | "succeeded"
  | "failed"
  | "drift";

export interface WorkspaceAction {
  /** Action UUID (when this card is backed by a real DB row).
      Falsy when it's a synthesized placeholder for an empty/investigating case. */
  id?: string;
  /** Raw kind from the API (`stripe_refund`, `customer_email`, etc.).
      Used by the ApprovalCinematic to resolve the source icon. */
  kind?: string;
  /** Source id (`stripe` | `notion` | ...) - derived from `kind`. */
  source?: string;
  title: string;               // "Refund $1,200 via Stripe"
  target: string;              // "POST /v1/refunds · ch_xxx"
  body: string;                // the drafted text or a 1-line summary
  /** Status from the actions table - drives the pill + 'fired' check. */
  status?: ActionStatus;
  /** External reference once executed: re_xxx (Stripe), Resend msg id, Notion page id, etc. */
  externalRef?: string | null;
  /** If status=failed, the error message. */
  errorMessage?: string | null;
  /** Deep-link to the source where this action landed (e.g. Stripe Dashboard for a refund). */
  externalUrl?: string | null;
  /** The raw payload JSON - used by the edit affordance + power-user view. */
  payload?: Record<string, unknown>;
}

export interface WorkspaceCaseDetail {
  num: string;
  headlineVerb: ReactNode;     // italic after customer name
  routedNote: string;          // "Routed to your queue"
  policyFile: string;          // "refunds.yaml@main"
  tldr: ReactNode;
  account: [string, ReactNode][];
  evidence: WorkspaceEvidence[];
  /** Findings broken out as separate items so the Brief postmortem can
      render each as its own paragraph with inline citation chips. */
  findings: WorkspaceFinding[];
  /** The brief.tldr field straight from the API (when present). Reads
      like a memo lede. The old `tldr` field above is the concatenated
      finding text used as a fallback when no brief exists yet. */
  briefTldr?: string | null;
  /** Caller wires this through so child components (Brief, citation
      modal) can hit the citation reasoning endpoint. */
  caseId: string;
  actions: WorkspaceAction[];
  policyReasoning: ReactNode;
}
