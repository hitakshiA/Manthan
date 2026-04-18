import { BASE_URL } from "./client";
import type { NumericClaim } from "@/types/conversation";

/**
 * Streaming client for the audit drawer.
 *
 * The backend at `POST /audit/describe-claim` streams an audit-grade
 * description token-by-token via SSE so the drawer can render words
 * as they're produced instead of popping in a full paragraph after a
 * multi-second wait. The stream emits three frame shapes:
 *
 *   { token: "..." }                        — partial content
 *   { done: true, description, cache_key }  — final snapshot
 *   { error: "..." }                        — upstream failure
 *
 * On error we fail silent (the drawer already renders a regex-built
 * fallback description, so the worst case is the user sees the
 * cheaper summary instead of the audit sentence).
 */

export interface ClaimDescribeBody {
  dataset_id: string;
  value: number;
  formatted: string;
  label?: string | null;
  entity?: string | null;
  metric_ref?: string | null;
  filters_applied: string[];
  dimensions: string[];
  grain?: string | null;
  sql?: string | null;
  row_count_scanned?: number | null;
  current_description?: string | null;
}

export interface StreamCallbacks {
  onToken: (chunk: string) => void;
  onDone: (finalDescription: string, cacheKey: string) => void;
  onError?: (message: string) => void;
  /** Backend detected that the model leaked its drafting process
   *  but was able to rescue a clean paragraph. The client should
   *  discard everything it's rendered so far — the replacement
   *  text will stream in as normal tokens right after. */
  onReset?: () => void;
}

export function claimToBody(
  datasetId: string,
  claim: NumericClaim,
): ClaimDescribeBody {
  return {
    dataset_id: datasetId,
    value: claim.value,
    formatted: claim.formatted,
    label: claim.label,
    entity: claim.entity,
    metric_ref: claim.metric_ref,
    filters_applied: claim.filters_applied ?? [],
    dimensions: claim.dimensions ?? [],
    grain: claim.grain,
    sql: claim.sql,
    row_count_scanned: claim.row_count_scanned,
    current_description: claim.description,
  };
}

export async function streamClaimDescription(
  body: ClaimDescribeBody,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/audit/describe-claim`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    const msg = `describe-claim failed: ${res.status}`;
    callbacks.onError?.(msg);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      // SSE frames are double-newline delimited. Split, keep the
      // trailing partial for the next read.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6);
        try {
          const event = JSON.parse(payload);
          if (typeof event.token === "string") {
            callbacks.onToken(event.token);
          } else if (event.reset) {
            callbacks.onReset?.();
          } else if (event.done) {
            callbacks.onDone(
              typeof event.description === "string" ? event.description : "",
              typeof event.cache_key === "string" ? event.cache_key : "",
            );
          } else if (event.error) {
            callbacks.onError?.(String(event.error));
          }
        } catch {
          // Skip malformed frame; drawer falls back to regex summary.
        }
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      callbacks.onError?.((err as Error).message);
    }
  }
}
