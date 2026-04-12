import type { KPICard as KPICardType } from "@/types/render-spec";
import { KPICard } from "./KPICard";

export function KPIRow({ cards }: { cards: KPICardType[] }) {
  return (
    <div className="grid gap-3" style={{
      gridTemplateColumns: `repeat(${Math.min(cards.length, 4)}, minmax(0, 1fr))`,
    }}>
      {cards.map((kpi, i) => (
        <KPICard key={i} kpi={kpi} />
      ))}
    </div>
  );
}
