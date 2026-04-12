import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { RenderRouter } from "@/components/render/RenderRouter";
import { NarrativeBlock } from "@/components/render/shared/NarrativeBlock";
import { Clock, Wrench, RotateCcw, BarChart3, TrendingUp, FileText, Sparkles } from "lucide-react";
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
      pushEvent({ type: "error", message: e instanceof Error ? e.message : "Failed", recoverable: false });
    }
  }, [activeDatasetId, sessionId, addQuery, pushEvent, reset]);

  const suggestions = activeDs ? [
    { icon: BarChart3, label: "Overview", text: `What are the key metrics in ${activeDs.name}?` },
    { icon: TrendingUp, label: "Compare", text: "Compare the top categories by volume" },
    { icon: FileText, label: "Report", text: "Full analytical report with recommendations" },
  ] : [];

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      {/* Hero */}
      <div className="text-center mb-8 stagger-item" style={{ "--i": 0 } as React.CSSProperties}>
        <div className="inline-flex items-center gap-2 mb-4">
          <Sparkles size={28} className="text-accent" strokeWidth={1.5} />
        </div>
        <h1 className="text-3xl font-bold text-text-primary tracking-tight">
          {activeDs ? (
            <>{activeDs.name}</>
          ) : (
            <>Manthan</>
          )}
        </h1>
        <p className="text-base text-text-secondary mt-2">
          {activeDs
            ? `${activeDs.row_count.toLocaleString()} rows · ${activeDs.column_count} columns`
            : "Your autonomous data analyst"
          }
        </p>
      </div>

      {/* Centered input — the hero element */}
      <div className="w-full max-w-2xl mb-6 stagger-item" style={{ "--i": 1 } as React.CSSProperties}>
        <QueryInput variant="hero" />
      </div>

      {/* Suggestion chips */}
      {activeDs && (
        <div className="flex gap-2 stagger-item" style={{ "--i": 2 } as React.CSSProperties}>
          {suggestions.map(({ icon: Icon, label, text }) => (
            <button
              key={label}
              onClick={() => runSuggestion(text)}
              className="flex items-center gap-2 text-[13px] text-text-secondary hover:text-text-primary bg-surface-raised hover:bg-surface-1 border border-border hover:border-border-strong px-4 py-2.5 rounded-xl shadow-xs hover:shadow-sm transition-all duration-200"
            >
              <Icon size={14} className="text-text-tertiary" />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ActiveWorkspace() {
  const events = useAgentStore((s) => s.events);
  const phase = useAgentStore((s) => s.phase);
  const renderSpec = useAgentStore((s) => s.renderSpec);
  const agentText = useAgentStore((s) => s.agentText);
  const elapsed = useAgentStore((s) => s.elapsedSeconds);
  const toolCalls = useAgentStore((s) => s.totalToolCalls);
  const reset = useAgentStore((s) => s.reset);
  const isDone = phase === "done";

  return (
    <>
      <div className="flex-1 overflow-y-auto">
        {!isDone && <ActivityFeed />}
        {isDone && (
          <div className="animate-fade-up">
            {/* Result header */}
            <div className="px-8 pt-6 pb-4 flex items-center gap-4">
              <div className="flex items-center gap-3 text-[11px] text-text-tertiary">
                <span className="flex items-center gap-1.5 bg-surface-sunken px-2 py-1 rounded-md">
                  <Clock size={11} />
                  {elapsed.toFixed(1)}s
                </span>
                <span className="flex items-center gap-1.5 bg-surface-sunken px-2 py-1 rounded-md">
                  <Wrench size={11} />
                  {toolCalls} tools
                </span>
              </div>
              <div className="flex-1" />
              <details className="text-[11px]">
                <summary className="text-text-faint cursor-pointer hover:text-text-secondary transition-colors select-none">
                  {events.length} agent events
                </summary>
                <div className="absolute right-8 mt-1 w-96 max-h-80 overflow-y-auto bg-surface-raised border border-border rounded-xl shadow-lg p-3 z-50">
                  <ActivityFeed />
                </div>
              </details>
              <button
                onClick={reset}
                aria-label="New query"
                className="flex items-center gap-1.5 text-[11px] text-text-faint hover:text-accent bg-surface-sunken hover:bg-accent-soft px-2.5 py-1 rounded-md transition-all"
              >
                <RotateCcw size={11} />
                New
              </button>
            </div>

            {/* Render spec output */}
            <div className="px-8 pb-8">
              {renderSpec ? (
                <RenderRouter spec={renderSpec as RenderSpec} />
              ) : agentText ? (
                <div className="bg-surface-raised border border-border rounded-xl shadow-sm p-6">
                  <NarrativeBlock text={agentText} />
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>

      {/* Bottom input — compact when active */}
      <div className="px-6 py-3 border-t border-border bg-surface-1">
        <QueryInput variant="compact" />
      </div>
    </>
  );
}

export function MainWorkspace() {
  const events = useAgentStore((s) => s.events);
  const hasContent = events.length > 0;

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-surface-0 relative" role="main">
      {hasContent ? <ActiveWorkspace /> : <WelcomeState />}
    </main>
  );
}
