import type { Visual } from "@/types/render-spec";
import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart, LineChart, ScatterChart, PieChart, HeatmapChart, FunnelChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { toEChartsOption } from "@/lib/encoding-mapper";
import { KPICard } from "@/components/render/shared/KPICard";

echarts.use([
  BarChart, LineChart, ScatterChart, PieChart, HeatmapChart, FunnelChart,
  GridComponent, TooltipComponent, LegendComponent, VisualMapComponent,
  CanvasRenderer,
]);

interface Props {
  visual: Visual;
}

export function ChartRenderer({ visual }: Props) {
  // KPI type renders as a card, not a chart
  if (visual.type === "kpi") {
    const enc = visual.encoding ?? {};
    const raw = visual as Record<string, unknown>;
    const data = (enc.data ?? raw.data ?? enc) as Record<string, unknown>;
    return (
      <KPICard
        kpi={{
          value: String(data.value ?? ""),
          label: String(data.label ?? visual.title),
          sentiment: "neutral",
        }}
      />
    );
  }

  const option = toEChartsOption(visual);

  return (
    <div className="w-full">
      {visual.title && (
        <h4 className="text-sm font-medium text-text-primary mb-2">{visual.title}</h4>
      )}
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height: 320, width: "100%" }}
        notMerge
        lazyUpdate
      />
      {visual.caption && (
        <p className="text-xs text-text-tertiary mt-1">{visual.caption}</p>
      )}
    </div>
  );
}
