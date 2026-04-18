import { useEffect, useState } from "react";
import { claimToBody, streamClaimDescription } from "@/api/audit";
import { useSessionStore } from "@/stores/session-store";
import type { NumericClaim } from "@/types/conversation";

/**
 * Audit-grade, streaming description of a clicked numeric claim.
 *
 * The claim event already carries a regex-built ``description`` —
 * enough for the 80% case. When the drawer opens we fire a
 * streaming LLM call that reads the full governed-metric contract
 * from the semantic layer and composes a real audit sentence. Tokens
 * arrive over SSE and we append them to state so the drawer renders
 * words as they're produced.
 *
 *   * Returns ``{description, loading, streaming}``. Callers render
 *     the cached/regex description while loading is true and swap /
 *     overlay as tokens stream in.
 *   * Cache is module-level (not zustand) because it's pure derived
 *     state — the only UI subscriber is this hook.
 *   * Errors fail silent: the drawer keeps the regex fallback.
 */

interface CacheEntry {
  description: string;
}

const cache = new Map<string, CacheEntry>();

function claimKey(datasetId: string | null, claim: NumericClaim): string {
  return [
    datasetId ?? "",
    claim.formatted,
    claim.value,
    claim.metric_ref ?? "",
    (claim.sql ?? "").slice(0, 200),
  ].join("|");
}

interface HookState {
  description: string | null;
  loading: boolean;
  streaming: boolean;
  /** True once the upstream call has ended *without* producing a
   *  description (network error, empty content, aborted). The
   *  drawer uses this to fall back silently to the regex summary
   *  — otherwise it would stay stuck in the "tracing…" state. */
  errored: boolean;
}

export function useClaimDescription(claim: NumericClaim | null): HookState {
  const datasetId = useSessionStore((s) => s.activeDatasetId);
  const [state, setState] = useState<HookState>({
    description: null,
    loading: false,
    streaming: false,
    errored: false,
  });

  useEffect(() => {
    if (!claim || !datasetId) {
      setState({
        description: null,
        loading: false,
        streaming: false,
        errored: false,
      });
      return;
    }
    // No point describing a number with no audit trail — the drawer
    // renders an explicit "Unverified" banner instead.
    if (claim.label === "Unverified number") {
      setState({
        description: null,
        loading: false,
        streaming: false,
        errored: false,
      });
      return;
    }
    // Also skip the call for freeform synthesized claims with no
    // provenance (everything stripped by NarrativeBlock). They
    // hide the audit-trail section upstream, so an LLM call here
    // would just burn tokens for a hidden component.
    const hasProvenance =
      claim.entity ||
      claim.metric_ref ||
      (claim.sql && claim.sql.trim()) ||
      claim.filters_applied.length > 0 ||
      (claim.dimensions && claim.dimensions.length > 0) ||
      claim.row_count_scanned != null;
    if (!hasProvenance) {
      setState({
        description: null,
        loading: false,
        streaming: false,
        errored: false,
      });
      return;
    }
    const key = claimKey(datasetId, claim);
    const cached = cache.get(key);
    if (cached) {
      setState({
        description: cached.description,
        loading: false,
        streaming: false,
        errored: false,
      });
      return;
    }

    const ctrl = new AbortController();
    let acc = "";
    // Kick off synchronously so the drawer re-renders in the
    // "tracing…" state *this tick*, not after the first setState.
    setState({
      description: null,
      loading: true,
      streaming: false,
      errored: false,
    });

    streamClaimDescription(
      claimToBody(datasetId, claim),
      {
        onToken: (chunk) => {
          acc += chunk;
          setState({
            description: acc,
            loading: true,
            streaming: true,
            errored: false,
          });
        },
        onReset: () => {
          // Backend detected the stream was leaking the model's
          // drafting and found a clean paragraph to replace it.
          // Drop what we rendered so the drawer re-starts the
          // reveal from the clean version.
          acc = "";
          setState({
            description: null,
            loading: true,
            streaming: true,
            errored: false,
          });
        },
        onDone: (finalDescription) => {
          const final = (finalDescription || acc).trim();
          if (final) cache.set(key, { description: final });
          setState({
            description: final || null,
            loading: false,
            streaming: false,
            errored: !final,
          });
        },
        onError: () => {
          // Fail silent at the drawer level — CLEAR whatever partial
          // content we streamed so a draft-leak abort doesn't leave
          // planning text visible. The drawer sees errored=true and
          // drops to the regex summary.
          setState({
            description: null,
            loading: false,
            streaming: false,
            errored: true,
          });
        },
      },
      ctrl.signal,
    );

    return () => {
      ctrl.abort();
    };
  }, [
    claim?.value,
    claim?.formatted,
    claim?.sql,
    claim?.metric_ref,
    datasetId,
    claim,
  ]);

  return state;
}
