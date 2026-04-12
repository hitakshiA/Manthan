import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { RenderRouter } from "@/components/render/RenderRouter";
import { NarrativeBlock } from "@/components/render/shared/NarrativeBlock";
import { Clock, Wrench, RotateCcw, BarChart3, TrendingUp, FileText } from "lucide-react";
import { queryStream } from "@/api/agent";
import type { RenderSpec } from "@/types/render-spec";
import { useCallback } from "react";

function WelcomeState() {
  const activeDatasetId = useSessionStore((s) => s.activeDatasetId);
  const sessionId = useSessionStore((s) => s.sessionId);
  const addQuery = useSessionStore((s) => s.addQuery);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const reset = useAgentStore((s) => s.reset);
  const datasets = useDatasetStore((s) => s.datasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);

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

  const suggestions = activeDs ? [
    { icon: BarChart3, text: `What are the key metrics in ${activeDs.name}?` },
    { icon: TrendingUp, text: `Compare the top categories by volume` },
    { icon: FileText, text: `Full analytical report with recommendations` },
  ] : [];

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-8 pb-16">
      {/* Hero greeting */}
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">
          {activeDs ? (
            <>Explore <span className="text-accent">{activeDs.name}</span></>
          ) : (
            "Manthan"
          )}
        </h1>
        <p className="text-sm text-text-secondary mt-2 max-w-sm mx-auto leading-relaxed">
          {activeDs
            ? `${activeDs.row_count.toLocaleString()} rows · ${activeDs.column_count} columns — ask anything`
            : "Select a dataset from the sidebar to start analyzing"
          }
        </p>
      </div>

      {/* Suggestion chips */}
      {activeDs && (
        <div className="grid gap-2 w-full max-w-lg">
          {suggestions.map(({ icon: Icon, text }) => (
            <button
              key={text}
              onClick={() => runSuggestion(text)}
              className="flex items-center gap-3 text-left text-[13px] text-text-secondary hover:text-text-primary bg-surface-1 hover:bg-surface-2 border border-border hover:border-border-strong px-4 py-3 rounded-lg transition-all duration-150 group"
            >
              <Icon size={16} className="text-text-tertiary group-hover:text-accent shrink-0 transition-colors" />
              <span>{text}</span>
            </button>
          ))}
        </div>
      )}
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
        {!hasContent && <WelcomeState />}
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
