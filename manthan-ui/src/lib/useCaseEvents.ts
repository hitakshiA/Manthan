/**
 * useCaseEvents - subscribe to the live event stream for a case.
 *
 * Uses Server-Sent Events. Re-connects on disconnect. Replays past events
 * on initial subscribe (the server emits them first), then live-tails.
 */

import { useEffect, useRef, useState } from "react";
import { useUser } from "@clerk/react";

import { getApiUserEmail } from "@/lib/api";

const API_URL =
  (import.meta.env.VITE_MANTHAN_API_URL as string | undefined) ??
  "http://127.0.0.1:8765";

const DEV_ORG =
  (import.meta.env.VITE_MANTHAN_DEV_ORG as string | undefined) || "acme";

export interface CaseEvent {
  seq: number;
  type: string;        // case_opened | tool_call | tool_result | finding_recorded | brief_drafted | case_closed | error | reflexion | agent_thought | investigation_started | hitl_pause
  actor: string;
  data: Record<string, unknown>;
  /** Pretty one-line summary written by worker.prettifier (Gemini Flash Lite).
      Null while pending; the UI falls back to its own rendering when null. */
  summary: string | null;
  created_at: string;
}

export interface UseCaseEventsState {
  events: CaseEvent[];
  isLive: boolean;
  isComplete: boolean;
  error: string | null;
}

export function useCaseEvents(caseId: string | undefined): UseCaseEventsState {
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const [isLive, setIsLive] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  // Wait for Clerk to resolve before connecting (see useInboxStream
  // for the same pattern). The SSE URL bakes in the user's email at
  // connect time; firing before Clerk loads means the request has no
  // identity and the backend can't route it to the right org.
  const { isLoaded: clerkLoaded, user } = useUser();
  const clerkEmail = user?.primaryEmailAddress?.emailAddress ?? null;

  useEffect(() => {
    if (!caseId) return;
    if (!clerkLoaded) return;

    setEvents([]);
    setIsLive(false);
    setIsComplete(false);
    setError(null);

    const userEmail = getApiUserEmail();
    const url =
      `${API_URL}/api/cases/${caseId}/stream?dev_org=${encodeURIComponent(DEV_ORG)}` +
      (userEmail ? `&dev_email=${encodeURIComponent(userEmail)}` : "");
    const es = new EventSource(url);
    sourceRef.current = es;

    es.addEventListener("open", () => setIsLive(true));

    es.addEventListener("case_event", (e) => {
      try {
        const payload = JSON.parse((e as MessageEvent).data) as CaseEvent;
        setEvents((prev) => {
          if (prev.some((p) => p.seq === payload.seq)) return prev;
          const next = [...prev, payload];
          next.sort((a, b) => a.seq - b.seq);
          return next;
        });
      } catch (err) {
        console.warn("manthan: failed to parse SSE event", err);
      }
    });

    es.addEventListener("complete", () => {
      setIsComplete(true);
      setIsLive(false);
      es.close();
    });

    es.addEventListener("ping", () => {
      /* heartbeat, no-op */
    });

    es.addEventListener("error", () => {
      setError("stream disconnected");
      setIsLive(false);
    });

    return () => {
      es.close();
      sourceRef.current = null;
    };
  }, [caseId, clerkLoaded, clerkEmail]);

  return { events, isLive, isComplete, error };
}
