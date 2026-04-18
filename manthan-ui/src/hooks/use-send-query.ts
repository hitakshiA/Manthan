import { useCallback } from "react";
import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useUIStore } from "@/stores/ui-store";
import { queryStream } from "@/api/agent";

/**
 * Re-submit the most recent user_message as a replacement for a
 * failed turn.
 *
 * Semantics:
 *   1. Find the last user_message block — that's the question that
 *      started the failed turn.
 *   2. Remove that block and everything after it so the transcript
 *      doesn't carry a dead broken-artifact / half-answer.
 *   3. Re-add the user_message with the original text plus a short
 *      retry-context suffix so the agent sees WHY the prior attempt
 *      failed (runtime error, timeout, etc.) and can pick a
 *      different approach. Transparency > clever: we show the
 *      retry context in the UI too, so the exec knows what we're
 *      re-asking.
 *   4. Stream the new turn over the same transport as a fresh
 *      send.
 *
 * Returns ``retry: null`` when there's no prior user message to
 * retry so callers can hide the button.
 */
export function useRetryLastQuery(): {
  retry: ((failureReason?: string) => void) | null;
  busy: boolean;
  /** The text of the last user_message, for display in a "Your
   *  question was: ..." banner. Null when there's nothing to retry. */
  lastQuestion: string | null;
} {
  const phase = useAgentStore((s) => s.phase);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const addUserMessage = useAgentStore((s) => s.addUserMessage);
  const truncateBlocksFrom = useAgentStore((s) => s.truncateBlocksFrom);
  const blocks = useAgentStore((s) => s.blocks);
  const { sessionId, activeDatasetId, addQuery } = useSessionStore();
  const setArtifactOpen = useUIStore((s) => s.setArtifactOpen);
  const setExpandedVisual = useUIStore((s) => s.setExpandedVisual);

  const busy = phase !== "idle" && phase !== "done" && phase !== "error";

  // Last user_message index — anchor for the failed turn.
  let lastUserIdx = -1;
  let lastUserText: string | null = null;
  for (let i = blocks.length - 1; i >= 0; i--) {
    const b = blocks[i];
    if (b.type === "user_message") {
      lastUserIdx = i;
      lastUserText = b.text;
      break;
    }
  }

  const retry = useCallback(
    async (failureReason?: string) => {
      if (
        lastUserText == null ||
        lastUserIdx < 0 ||
        !activeDatasetId ||
        busy
      )
        return;

      // Build the retry message. Keep the original question verbatim
      // so it's still recognizable in the transcript; append a short
      // failure-context line so the agent knows what to avoid. We
      // also cap the error string so a huge stack trace doesn't
      // dominate the prompt.
      const reasonLine = failureReason
        ? `\n\n(Retry — the previous attempt failed with: ${failureReason.slice(0, 400)}. Please take a different approach.)`
        : "\n\n(Retry — the previous attempt did not complete. Please try again, ideally a simpler approach.)";
      const retryText = `${lastUserText}${reasonLine}`;

      // Drop the failed turn before replaying. After this the user
      // sees only the conversation up to (but not including) the
      // failed question.
      truncateBlocksFrom(lastUserIdx);
      setArtifactOpen(false);
      setExpandedVisual(null);

      addQuery(retryText, activeDatasetId);
      addUserMessage(retryText);
      try {
        await queryStream(sessionId, activeDatasetId, retryText, pushEvent);
      } catch (e) {
        pushEvent({
          type: "error",
          message: e instanceof Error ? e.message : "Connection failed",
          recoverable: false,
        });
      }
    },
    [
      lastUserText,
      lastUserIdx,
      activeDatasetId,
      busy,
      sessionId,
      pushEvent,
      addQuery,
      addUserMessage,
      truncateBlocksFrom,
      setArtifactOpen,
      setExpandedVisual,
    ],
  );

  return {
    retry: lastUserText != null ? retry : null,
    busy,
    lastQuestion: lastUserText,
  };
}
