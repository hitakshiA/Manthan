import type { PipelineEvent } from "@/types/pipeline";
import { BASE_URL } from "./client";

/** Connect to GET /datasets/{id}/progress SSE stream */
export async function connectPipelineProgress(
  datasetId: string,
  onEvent: (event: PipelineEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/datasets/${datasetId}/progress`, {
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Pipeline progress stream failed: ${res.status}`);
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
          const event = JSON.parse(line.slice(6)) as PipelineEvent;
          onEvent(event);
        } catch {
          // Skip malformed events
        }
      }
    }
  }
}
