/**
 * useInboxStream - subscribe to the cross-cases SSE stream.
 *
 * Replaces the old "GET /api/cases every 10 seconds" pattern. The server
 * pushes a fresh `cases` event whenever any case in the org changes
 * (debounced ~1s on the server side so investigation bursts collapse).
 *
 * Falls back to a 15s poll if the EventSource fails to connect - we
 * never want the Inbox to stop updating because of a transient SSE issue.
 */

import { useEffect, useRef, useState } from "react";
import { useUser } from "@clerk/react";

import { getApiUserEmail, listCases, type ApiCase, type ApiCaseList } from "@/lib/api";

const API_URL =
  (import.meta.env.VITE_MANTHAN_API_URL as string | undefined) ??
  "http://127.0.0.1:8765";

const DEV_ORG =
  (import.meta.env.VITE_MANTHAN_DEV_ORG as string | undefined) || "acme";

export interface UseInboxStreamState {
  cases: ApiCase[] | null;
  total: number;
  isLive: boolean;
  error: string | null;
  /** Wall-clock ms timestamp of the most recent payload. */
  lastUpdatedAt: number | null;
}

export function useInboxStream(limit = 60): UseInboxStreamState {
  const [cases, setCases] = useState<ApiCase[] | null>(null);
  const [total, setTotal] = useState(0);
  const [isLive, setIsLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const sourceRef = useRef<EventSource | null>(null);
  const pollRef = useRef<number | null>(null);

  // Wait for Clerk to resolve before connecting - without this, the
  // first SSE connect fires before ClerkIdentitySync has set the
  // dev_email header, so the backend has no email to route on and
  // (post-acme-wipe) has no fallback org → 404. Once Clerk loads
  // and surfaces the user, we re-run this effect with the identity
  // in place.
  const { isLoaded: clerkLoaded, user } = useUser();
  const clerkEmail = user?.primaryEmailAddress?.emailAddress ?? null;

  useEffect(() => {
    let cancelled = false;
    if (!clerkLoaded) return;

    const startPollFallback = () => {
      if (pollRef.current !== null) return;
      const tick = async () => {
        try {
          const r = await listCases({ limit });
          if (cancelled) return;
          setCases(r.cases);
          setTotal(r.total);
          setLastUpdatedAt(Date.now());
          setError(null);
        } catch (err) {
          if (cancelled) return;
          setError((err as Error).message);
        }
      };
      tick();
      pollRef.current = window.setInterval(tick, 15_000);
    };

    const stopPollFallback = () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    const userEmail = getApiUserEmail();
    const url =
      `${API_URL}/api/inbox/stream?limit=${limit}` +
      `&dev_org=${encodeURIComponent(DEV_ORG)}` +
      (userEmail ? `&dev_email=${encodeURIComponent(userEmail)}` : "");

    let es: EventSource;
    try {
      es = new EventSource(url);
    } catch {
      // Browser blocked EventSource entirely; fall back to polling.
      startPollFallback();
      return () => {
        cancelled = true;
        stopPollFallback();
      };
    }
    sourceRef.current = es;

    es.addEventListener("open", () => {
      if (cancelled) return;
      setIsLive(true);
      setError(null);
      // We have SSE; cancel any in-flight fallback polling.
      stopPollFallback();
    });

    es.addEventListener("cases", (e) => {
      if (cancelled) return;
      try {
        const payload = JSON.parse((e as MessageEvent).data) as ApiCaseList;
        setCases(payload.cases);
        setTotal(payload.total);
        setLastUpdatedAt(Date.now());
      } catch (err) {
        console.warn("manthan: failed to parse inbox SSE payload", err);
      }
    });

    es.addEventListener("ping", () => {
      /* heartbeat - no-op */
    });

    es.addEventListener("error", () => {
      if (cancelled) return;
      setIsLive(false);
      setError("stream disconnected");
      // Browser auto-reconnects EventSource; meanwhile keep data fresh
      // by enabling the slow poll fallback. It cancels itself on `open`.
      startPollFallback();
    });

    return () => {
      cancelled = true;
      es.close();
      sourceRef.current = null;
      stopPollFallback();
    };
  }, [limit, clerkLoaded, clerkEmail]);

  return { cases, total, isLive, error, lastUpdatedAt };
}
