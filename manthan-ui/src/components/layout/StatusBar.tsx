import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { formatNumber } from "@/lib/utils";
import { Circle } from "lucide-react";

export function StatusBar() {
  const phase = useAgentStore((s) => s.phase);
  const elapsed = useAgentStore((s) => s.elapsedSeconds);
  const turn = useAgentStore((s) => s.currentTurn);
  const toolCalls = useAgentStore((s) => s.totalToolCalls);
  const model = useAgentStore((s) => s.model);
  const activeId = useSessionStore((s) => s.activeDatasetId);
  const datasets = useDatasetStore((s) => s.datasets);

  const activeDs = datasets.find((d) => d.dataset_id === activeId);
  const isActive = phase !== "idle" && phase !== "done" && phase !== "error";

  return (
    <footer className="h-7 flex items-center gap-4 px-4 border-t border-border bg-surface-1 text-xs text-text-tertiary select-none shrink-0">
      <span className="flex items-center gap-1.5">
        <Circle
          size={7}
          fill={isActive ? "var(--color-success)" : "var(--color-text-tertiary)"}
          strokeWidth={0}
        />
        {isActive ? "Working" : "Ready"}
      </span>

      {activeDs && (
        <span>
          {activeDs.name} · {formatNumber(activeDs.row_count)} rows
        </span>
      )}

      {phase !== "idle" && (
        <>
          {turn > 0 && <span>Turn {turn}</span>}
          {toolCalls > 0 && <span>{toolCalls} tool calls</span>}
          {elapsed > 0 && <span>{elapsed.toFixed(1)}s</span>}
        </>
      )}

      <span className="ml-auto">{model ?? "manthan"}</span>
    </footer>
  );
}
