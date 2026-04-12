import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { QueryInput } from "@/components/workspace/QueryInput";
import { ActivityFeed } from "@/components/workspace/ActivityFeed";
import { Database, ArrowUpRight } from "lucide-react";

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

export function MainWorkspace() {
  const phase = useAgentStore((s) => s.phase);
  const events = useAgentStore((s) => s.events);
  const hasContent = events.length > 0 || phase !== "idle";

  return (
    <main className="flex-1 flex flex-col min-w-0 bg-surface-0">
      <QueryInput />
      <div className="flex-1 overflow-y-auto">
        {hasContent ? <ActivityFeed /> : <EmptyState />}
      </div>
    </main>
  );
}
