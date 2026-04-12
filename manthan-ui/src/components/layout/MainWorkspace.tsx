import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { RenderRouter } from "@/components/render/RenderRouter";
import { NarrativeBlock } from "@/components/render/shared/NarrativeBlock";
import { Database, ArrowUpRight, Clock, Wrench, RotateCcw } from "lucide-react";
import type { RenderSpec } from "@/types/render-spec";

function EmptyState() {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);

  if (!activeDatasetId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 px-8">
        <div className="w-12 h-12 rounded-xl bg-surface-2 flex items-center justify-center">
          <Database size={22} className="text-text-tertiary" />
        </div>
        <div className="text-center max-w-sm">
          <h2 className="text-lg font-semibold text-text-primary">
            Select a dataset
          </h2>
          <p className="text-sm text-text-secondary mt-1.5 leading-relaxed">
            Upload a CSV, Parquet, or Excel file from the sidebar, then ask any question about your data.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-8">
      <div className="text-center max-w-md">
        <h2 className="text-lg font-semibold text-text-primary">
          What would you like to know?
        </h2>
        <p className="text-sm text-text-secondary mt-1.5 leading-relaxed">
          Ask a question and the analyst team will investigate — running SQL, building charts, and writing insights.
        </p>
      </div>
      <div className="flex flex-wrap gap-2 justify-center">
        {[
          "What percentage of people earn over $50k?",
          "Compare income across education levels",
          "Full income inequality analysis with recommendations",
        ].map((q) => (
          <button
            key={q}
            className="flex items-center gap-1.5 text-xs text-text-secondary bg-surface-1 hover:bg-surface-2 border border-border px-3 py-2 rounded-lg transition-colors"
          >
            {q}
            <ArrowUpRight size={12} className="text-text-tertiary" />
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
    <div className="px-6 py-5 space-y-5">
      {/* Stats bar */}
      <div className="flex items-center gap-4 text-xs text-text-tertiary">
        <span className="flex items-center gap-1">
          <Clock size={12} />
          {elapsed.toFixed(1)}s
        </span>
        <span className="flex items-center gap-1">
          <Wrench size={12} />
          {toolCalls} tool calls
        </span>
        <button
          onClick={reset}
          className="flex items-center gap-1 ml-auto text-text-tertiary hover:text-accent transition-colors"
        >
          <RotateCcw size={12} />
          New query
        </button>
      </div>

      {/* Render spec output */}
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
    <main className="flex-1 flex flex-col min-w-0 bg-surface-0">
      <QueryInput />
      <div className="flex-1 overflow-y-auto">
        {!hasContent && <EmptyState />}
        {hasContent && !isDone && <ActivityFeed />}
        {hasContent && isDone && (
          <>
            <details className="px-6 pt-4">
              <summary className="text-xs text-text-tertiary cursor-pointer hover:text-text-secondary transition-colors">
                Show agent activity ({events.length} events)
              </summary>
              <ActivityFeed />
            </details>
            <ResultView />
          </>
        )}
      </div>
    </main>
  );
}
