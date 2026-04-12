import type { ReportPage as ReportPageType } from "@/types/render-spec";
import { BlockRenderer } from "./BlockRenderer";

export function ReportPage({ page }: { page: ReportPageType }) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-text-primary text-balance">{page.title}</h2>
        {page.purpose && (
          <p className="text-sm text-text-secondary mt-1 leading-relaxed">{page.purpose}</p>
        )}
      </div>
      <div className="space-y-4">
        {page.blocks.map((block, i) => (
          <BlockRenderer key={i} block={block} />
        ))}
      </div>
      {page.cross_references.length > 0 && (
        <div className="pt-3 border-t border-border">
          <p className="text-xs text-text-tertiary">
            See also:{" "}
            {page.cross_references.map((ref, i) => (
              <span key={i}>
                {i > 0 && ", "}
                <span className="text-accent">{ref.to_page}</span>
                <span className="text-text-tertiary"> ({ref.reason})</span>
              </span>
            ))}
          </p>
        </div>
      )}
    </div>
  );
}
