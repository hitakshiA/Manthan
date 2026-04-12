import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { RenderRouter } from "@/components/render/RenderRouter";
import { NarrativeBlock } from "@/components/render/shared/NarrativeBlock";
import { Clock, Wrench, RotateCcw } from "lucide-react";
import { queryStream } from "@/api/agent";
import type { RenderSpec } from "@/types/render-spec";
import { useCallback } from "react";

const SUGGESTIONS = [
  "What percentage earn over $50k?",
  "Compare income by education level",
  "Full income inequality report",
];

function EmptyState() {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const sessionId = useSessionStore((s) => s.sessionId);
  const addQuery = useSessionStore((s) => s.addQuery);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const reset = useAgentStore((s) => s.reset);

  const runSuggestion = useCallback(async (q: string) => {
    if (!activeDatasetId) return;
    reset();
    addQuery(q, activeDatasetId);
    try {
      await queryStream(sessionId, activeDatasetId, q, pushEvent);
    } catch (e) {
      pushEvent({
        type: "error",
        message: e instanceof Error ? e.message : "Failed",
        recoverable: false,
      });
    }
  }, [activeDatasetId, sessionId, addQuery, pushEvent, reset]);

  if (!activeDatasetId) {
    return (
      <div className="flex-1 flex items-center justify-center px-8">
        <p className="text-sm text-text-tertiary">
          Select a dataset from the sidebar to begin
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-8 gap-5">
      <div className="text-center">
        <p className="text-sm text-text-secondary">
          What would you like to know?
        </p>
      </div>
      <div className="flex flex-col gap-1.5 w-full max-w-md">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => runSuggestion(q)}
            className="w-full text-left text-[13px] text-text-secondary hover:text-text-primary bg-surface-1 hover:bg-surface-2 border border-border px-3 py-2 rounded-md transition-all duration-150"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function ResultView() {
  const renderSpec = useAgentStore((s) => s.renderSpec);
  const agentText = useAgentStore((s) => s.agentText);
  const elapsed = useAgentStore((s) => s.elapsedSeconds);
  const toolCalls = useAgentStore((s) => s.totalToolCalls);
  const reset = useAgentStore((s) => s.reset);

  return (
    <div className="px-6 py-5 space-y-5 animate-fade-up">
      <div className="flex items-center gap-3 text-[11px] text-text-tertiary">
        <span className="flex items-center gap-1">
          <Clock size={11} />
          {elapsed.toFixed(1)}s
        </span>
        <span className="flex items-center gap-1">
          <Wrench size={11} />
          {toolCalls} tools
        </span>
        <button
          onClick={reset}
          aria-label="Start new query"
          className="flex items-center gap-1 ml-auto text-text-tertiary hover:text-accent transition-colors"
        >
          <RotateCcw size={11} />
          New query
        </button>
      </div>

      {renderSpec ? (
        <RenderRouter spec={renderSpec as RenderSpec} />
      ) : agentText ? (
        <NarrativeBlock text={agentText} />
      ) : null}
    </div>
  );
}

export function MainWorkspace() {
  const phase = useAgentStore((s) => s.phase);
  const events = useAgentStore((s) => s.events);
  const hasContent = events.length > 0;
  const isDone = phase === "done";

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-surface-0" role="main">
      <div className="flex-1 overflow-y-auto">
        {!hasContent && <EmptyState />}
        {hasContent && !isDone && <ActivityFeed />}
        {hasContent && isDone && (
          <>
            <details className="px-6 pt-3">
              <summary className="text-[11px] text-text-tertiary cursor-pointer hover:text-text-secondary transition-colors select-none">
                Agent activity ({events.length} events)
              </summary>
              <div className="mt-2">
                <ActivityFeed />
              </div>
            </details>
            <ResultView />
          </>
        )}
      </div>
      <QueryInput />
    </main>
  );
}
