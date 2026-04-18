import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Database, ArrowRight } from "lucide-react";
import { listDatasets } from "@/api/datasets";
import { useDatasetStore } from "@/stores/dataset-store";
import { useSessionStore } from "@/stores/session-store";
import type { DatasetSummary } from "@/types/api";
import { cn } from "@/lib/utils";

/**
 * One-click gallery of the existing datasets in the workspace, rendered
 * on FirstOpen when the user has nothing to type-to. Duplicates (same
 * dataset name) are collapsed onto the most recent — the user sees one
 * tile per entity, and clicking it opens the dataset profile.
 */

type Seed = {
  name: string;
  description: string;
  match: RegExp;
};

// Descriptions overlay the raw dataset names so the gallery reads like
// a product catalog, not a database index.
const SEEDS: Seed[] = [
  {
    name: "Orders",
    description: "Food-delivery order transactions with fees, tips, and delivery outcomes.",
    match: /orders?$/i,
  },
  {
    name: "Startup Funding",
    description: "Deal-level funding rounds: amount, sector, lead investor, year.",
    match: /startup[_ ]funding/i,
  },
  {
    name: "Payments",
    description: "Payment transactions — methods, refunds, statuses.",
    match: /^payments?$/i,
  },
  {
    name: "Users",
    description: "Customer directory — corporate affiliations, loyalty tiers.",
    match: /^users?$/i,
  },
  {
    name: "Dishes",
    description: "Restaurant menu items with ratings, categories, availability.",
    match: /^dishes$/i,
  },
  {
    name: "Delivery History",
    description: "Delivery events across personnel, routes, and timing.",
    match: /delivery[_ ]history/i,
  },
];

function describe(ds: DatasetSummary): string {
  const seed = SEEDS.find((s) => s.match.test(ds.name));
  if (seed) return seed.description;
  return `${ds.row_count.toLocaleString()} rows × ${ds.column_count} fields`;
}

export function SampleGallery({ onOpenPicker }: { onOpenPicker?: () => void }) {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);
  const { datasets: stored, fetchDatasets } = useDatasetStore();

  useEffect(() => {
    (async () => {
      if (stored.length === 0) await fetchDatasets();
      try {
        const list = await listDatasets();
        // Dedupe by name — most recently updated wins.
        const byName = new Map<string, DatasetSummary>();
        for (const d of list) {
          const existing = byName.get(d.name);
          if (!existing || new Date(d.created_at) > new Date(existing.created_at)) {
            byName.set(d.name, d);
          }
        }
        setDatasets([...byName.values()].slice(0, 8));
      } catch {}
    })();
  }, [fetchDatasets, stored.length]);

  if (datasets.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.3 }}
      className="w-full max-w-4xl mx-auto"
    >
      <div className="flex items-center justify-between mb-3 px-1">
        <h3 className="text-[11px] text-white/60 uppercase tracking-wider font-body">
          Open a recent dataset
        </h3>
        {onOpenPicker && (
          <button
            onClick={onOpenPicker}
            className="text-[11px] text-white/70 hover:text-white transition-colors font-body"
          >
            Or add new →
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {datasets.map((ds) => (
          <button
            key={ds.dataset_id}
            onClick={() => setActiveDataset(ds.dataset_id)}
            className={cn(
              "group text-left p-4 rounded-xl border border-white/10 bg-black/20 hover:bg-black/30 backdrop-blur-md",
              "transition-all font-body",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Database size={13} className="text-white/60 shrink-0" />
                  <p className="text-sm text-white font-medium truncate">
                    {ds.name}
                  </p>
                </div>
                <p className="text-[11px] text-white/60 mt-1 line-clamp-2">
                  {describe(ds)}
                </p>
                <p className="text-[10px] text-white/40 mt-2 font-mono">
                  {ds.row_count.toLocaleString()} rows
                </p>
              </div>
              <ArrowRight
                size={13}
                className="text-white/40 shrink-0 mt-1 group-hover:text-white group-hover:translate-x-0.5 transition-all"
              />
            </div>
          </button>
        ))}
      </div>
    </motion.div>
  );
}
