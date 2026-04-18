import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";

export function StatusBar() {
  const phase = useAgentStore((s) => s.phase);
  const model = useAgentStore((s) => s.model);
  const activeId = useSessionStore((s) => s.activeDatasetId);
  const datasets = useDatasetStore((s) => s.datasets);

  const activeDs = datasets.find((d) => d.dataset_id === activeId);
  const isActive = phase !== "idle" && phase !== "done" && phase !== "error";

  return (
    <footer className="h-6 flex items-center gap-3 px-4 text-[10px] text-text-faint select-none shrink-0">
      <span className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-success animate-pulse" : "bg-text-faint"}`} />
        {isActive ? "Analyzing" : activeDs ? `Analyzing ${activeDs.name}` : "Ready"}
      </span>
      <span className="ml-auto font-medium">{model ?? "manthan"}</span>
    </footer>
  );
}
