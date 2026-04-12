import { useState } from "react";
import type { Citation } from "@/types/render-spec";
import { ChevronDown, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";

export function CitationsFooter({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);

  if (citations.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-secondary transition-colors"
      >
        <BookOpen size={12} />
        {citations.length} source{citations.length > 1 ? "s" : ""}
        <ChevronDown size={12} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {citations.map((c, i) => (
            <div key={i} className="text-xs text-text-tertiary flex items-start gap-2">
              <span className="font-mono text-accent bg-accent-soft px-1 rounded shrink-0">{c.kind}</span>
              <span>
                <span className="text-text-secondary">{c.identifier}</span>
                {c.reason && <span className="ml-1">— {c.reason}</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
