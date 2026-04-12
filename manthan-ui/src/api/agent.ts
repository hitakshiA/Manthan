import type { AgentEvent } from "@/types/events";
import { BASE_URL } from "./client";

export type EventHandler = (event: AgentEvent) => void;

/** Connect to POST /agent/query SSE stream and dispatch events */
export async function queryStream(
  sessionId: string,
  datasetId: string,
  message: string,
  onEvent: EventHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/agent/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      dataset_id: datasetId,
      message,
    }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Agent query failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop()!;

    for (const chunk of chunks) {
      const line = chunk.trim();
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6)) as AgentEvent;
          onEvent(event);
        } catch {
          // Skip malformed events
        }
      }
    }
  }
}
