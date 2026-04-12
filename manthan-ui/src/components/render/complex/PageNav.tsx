import type { ReportPage } from "@/types/render-spec";
import { cn } from "@/lib/utils";
import { FileText, BarChart3, BookOpen } from "lucide-react";

interface Props {
  pages: ReportPage[];
  activePage: string;
  onNavigate: (pageId: string) => void;
  showExecSummary?: boolean;
  showAppendix?: boolean;
}

export function PageNav({ pages, activePage, onNavigate, showExecSummary = true, showAppendix = true }: Props) {
  return (
    <nav className="w-48 shrink-0 border-r border-border py-3 space-y-0.5 overflow-y-auto">
      {showExecSummary && (
        <button
          onClick={() => onNavigate("__exec_summary")}
          className={cn(
            "w-full text-left px-3 py-2 text-xs font-medium rounded-r-md transition-colors flex items-center gap-2",
            activePage === "__exec_summary"
              ? "bg-accent-soft text-accent border-l-2 border-accent"
              : "text-text-secondary hover:bg-surface-2",
          )}
        >
          <BarChart3 size={13} />
          Executive Summary
        </button>
      )}

      {pages.map((page) => (
        <button
          key={page.id}
          onClick={() => onNavigate(page.id)}
          className={cn(
            "w-full text-left px-3 py-2 text-xs rounded-r-md transition-colors flex items-center gap-2",
            activePage === page.id
              ? "bg-accent-soft text-accent font-medium border-l-2 border-accent"
              : "text-text-secondary hover:bg-surface-2",
          )}
        >
          <FileText size={13} />
          <span className="truncate">{page.title}</span>
        </button>
      ))}

      {showAppendix && (
        <button
          onClick={() => onNavigate("__appendix")}
          className={cn(
            "w-full text-left px-3 py-2 text-xs rounded-r-md transition-colors flex items-center gap-2",
            activePage === "__appendix"
              ? "bg-accent-soft text-accent font-medium border-l-2 border-accent"
              : "text-text-secondary hover:bg-surface-2",
          )}
        >
          <BookOpen size={13} />
          Appendix
        </button>
      )}
    </nav>
  );
}
