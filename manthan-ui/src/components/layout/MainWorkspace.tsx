import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { RenderRouter } from "@/components/render/RenderRouter";
import { NarrativeBlock } from "@/components/render/shared/NarrativeBlock";
import { Database, ArrowUpRight, Clock, Wrench, RotateCcw } from "lucide-react";
import { queryStream } from "@/api/agent";
import type { RenderSpec } from "@/types/render-spec";
import { useCallback } from "react";

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
      <div className="flex-1 flex flex-col items-center justify-center gap-5 px-8">
        <div className="w-10 h-10 rounded-lg bg-surface-2 flex items-center justify-center">
          <Database size={20} className="text-text-tertiary" />
        </div>
        <div className="text-center max-w-xs">
          <h2 className="text-base font-semibold text-text-primary">
            Upload a dataset to begin
          </h2>
          <p className="text-sm text-text-secondary mt-1.5 leading-relaxed">
            Drop a CSV, Parquet, or Excel file in the sidebar.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-8">
      <div className="text-center max-w-sm">
        <h2 className="text-base font-semibold text-text-primary">
          What would you like to know?
        </h2>
        <p className="text-sm text-text-secondary mt-1.5 leading-relaxed">
          The analyst team will run SQL, build charts, and write insights.
        </p>
      </div>
      <div className="flex flex-wrap gap-2 justify-center max-w-lg">
        {[
          "What percentage earn over $50k?",
          "Compare income across education levels",
          "Full income inequality report",
        ].map((q) => (
          <button
            key={q}
            onClick={() => runSuggestion(q)}
            className="flex items-center gap-1.5 text-xs text-text-secondary bg-surface-1 hover:bg-surface-2 hover:text-text-primary border border-border px-3 py-2 rounded-lg transition-all duration-150"
          >
            {q}
            <ArrowUpRight size={11} className="text-text-tertiary" />
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
      <div className="flex items-center gap-4 text-xs text-text-tertiary">
        <span className="flex items-center gap-1">
          <Clock size={12} />
          {elapsed.toFixed(1)}s
        </span>
        <span className="flex items-center gap-1">
          <Wrench size={12} />
          {toolCalls} tools
        </span>
        <button
          onClick={reset}
          aria-label="Start new query"
          className="flex items-center gap-1 ml-auto text-text-tertiary hover:text-accent transition-colors"
        >
          <RotateCcw size={12} />
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
      <QueryInput />
      <div className="flex-1 overflow-y-auto">
        {!hasContent && <EmptyState />}
        {hasContent && !isDone && <ActivityFeed />}
        {hasContent && isDone && (
          <>
            <details className="px-6 pt-4">
              <summary className="text-xs text-text-tertiary cursor-pointer hover:text-text-secondary transition-colors select-none">
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
    </main>
  );
}
