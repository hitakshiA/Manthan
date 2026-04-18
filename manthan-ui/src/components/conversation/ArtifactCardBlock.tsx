import { Code2, Maximize2 } from "lucide-react";
import type { ArtifactCardBlock as ArtifactCardType } from "@/types/conversation";
import { useUIStore } from "@/stores/ui-store";

export function ArtifactCardBlock({ block }: { block: ArtifactCardType }) {
  const ext = block.filename.split(".").pop()?.toUpperCase() ?? "";
  const setArtifactOpen = useUIStore((s) => s.setArtifactOpen);
  const setArtifactFullscreen = useUIStore((s) => s.setArtifactFullscreen);

  return (
    <button
      onClick={() => setArtifactOpen(true)}
      className="w-full flex items-center gap-3 p-3 rounded-xl border border-border bg-surface-raised hover:border-border-strong hover:bg-surface-1 transition-all font-body group text-left"
    >
      <div className="w-9 h-9 rounded-lg bg-accent-soft flex items-center justify-center shrink-0">
        <Code2 size={16} className="text-accent" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-text-primary truncate">{block.title}</p>
        <p className="text-[11px] text-text-faint">
          {block.filename} {ext && <span className="text-text-tertiary">{"\u00B7"} Interactive dashboard {"\u00B7"} {ext}</span>}
        </p>
      </div>
      <span
        role="button"
        tabIndex={0}
        onClick={(e) => { e.stopPropagation(); setArtifactFullscreen(true); }}
        onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); setArtifactFullscreen(true); } }}
        className="opacity-0 group-hover:opacity-100 p-1.5 rounded-md text-text-faint hover:text-text-primary hover:bg-surface-sunken transition-all cursor-pointer"
        title="Open fullscreen"
      >
        <Maximize2 size={13} />
      </span>
    </button>
  );
}
