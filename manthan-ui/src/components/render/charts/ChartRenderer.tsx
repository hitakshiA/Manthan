import { Component, type ReactNode } from "react";
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

/** Error boundary specifically for charts — never crashes the whole page */
class ChartErrorBoundary extends Component<
  { children: ReactNode; title: string },
  { hasError: boolean; error: string }
> {
  constructor(props: { children: ReactNode; title: string }) {
    super(props);
    this.state = { hasError: false, error: "" };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }
  componentDidCatch(error: Error) {
    console.error("[ChartRenderer] Chart failed to render:", this.props.title, error.message);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="w-full h-40 flex items-center justify-center rounded-xl bg-surface-sunken border border-border text-sm text-text-faint">
          Chart could not render: {this.state.error.slice(0, 100)}
        </div>
      );
    }
    return this.props.children;
  }
}

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

  let option;
  try {
    option = toEChartsOption(visual);
  } catch (e) {
    console.error("[ChartRenderer] toEChartsOption failed:", e, "visual:", JSON.stringify(visual).slice(0, 500));
    return (
      <div className="w-full h-40 flex items-center justify-center rounded-xl bg-surface-sunken border border-border text-sm text-text-faint">
        Chart configuration error
      </div>
    );
  }

  return (
    <ChartErrorBoundary title={String(visual.title ?? "")}>
      <div className="w-full">
        {visual.title && (
          <h4 className="text-sm font-medium text-text-primary mb-2">{String(visual.title)}</h4>
        )}
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          style={{ height: 320, width: "100%" }}
          notMerge
          lazyUpdate
        />
        {visual.caption && (
          <p className="text-xs text-text-tertiary mt-1">{String(visual.caption)}</p>
        )}
      </div>
    </ChartErrorBoundary>
  );
}
