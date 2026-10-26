/**
 * useInvestigationNarrative - polls /api/cases/:id/narrative every 6s
 * while a case is investigating, returning a 2-paragraph live story
 * of what the agent has done + 3-5 interim findings derived from
 * tool_results. Stops polling once `isComplete` flips true.
 *
 * Why polling: the SSE event stream gives us individual events; the
 * narrative is a synthesized view across the whole recent window, so
 * regenerating it on every event would burn LLM cost for no benefit.
 * 6s feels live, matches the typical interval between tool_call bursts.
 */

import { useEffect, useRef, useState } from "react";

import {
  getInvestigationNarrative,
  type InvestigationNarrative,
} from "@/lib/api";

const POLL_MS = 6_000;

export function useInvestigationNarrative(
  caseId: string | undefined,
  opts: { enabled: boolean } = { enabled: true },
): {
  narrative: string | null;
  findings: string[];
  eventsProcessed: number;
  loading: boolean;
  error: string | null;
} {
  const [data, setData] = useState<InvestigationNarrative | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!caseId || !opts.enabled) {
      // Clean up any prior timer when disabled.
      if (timerRef.current != null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    let cancelled = false;

    const fetchOnce = async () => {
      setLoading(true);
      try {
        const r = await getInvestigationNarrative(caseId);
        if (!cancelled) {
          setData(r);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    // Fire immediately + on interval.
    fetchOnce();
    timerRef.current = window.setInterval(fetchOnce, POLL_MS);

    return () => {
      cancelled = true;
      if (timerRef.current != null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [caseId, opts.enabled]);

  return {
    narrative: data?.narrative ?? null,
    findings: data?.findings ?? [],
    eventsProcessed: data?.events_processed ?? 0,
    loading,
    error,
  };
}
