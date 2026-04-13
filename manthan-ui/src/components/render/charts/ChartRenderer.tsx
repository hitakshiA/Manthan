import { Component, type ReactNode } from "react";
import type { Visual } from "@/types/render-spec";
import { KPICard } from "@/components/render/shared/KPICard";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter,
} from "recharts";

// Warm indigo palette for charts
const COLORS = ["#6E56CF", "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6"];

/** Error boundary — a bad chart never crashes the page */
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
  render() {
    if (this.state.hasError) {
      return (
        <div className="w-full h-40 flex items-center justify-center rounded-xl bg-surface-sunken border border-border text-sm text-text-faint">
          Chart unavailable
        </div>
      );
    }
    return this.props.children;
  }
}

/** Extract chart data from the visual — handles ALL agent formats */
function extractData(visual: Visual): { data: Array<Record<string, unknown>>; xKey: string; yKey: string; yKeys?: string[] } {
  const enc = visual.encoding ?? {};
  const raw = visual as Record<string, unknown>;
  const rawData = (raw.data ?? enc.data) as Record<string, unknown> | Array<Record<string, unknown>> | undefined;

  // Format A: data.categories + data.series[{name, values}] (GLM 5.1 bar/grouped_bar)
  // or data.x + data.series[{name, values}] (GLM 5.1 line)
  if (rawData && typeof rawData === "object" && !Array.isArray(rawData)) {
    const categories = (rawData.categories ?? rawData.x) as unknown[];
    const series = rawData.series as Array<{ name: string; values: unknown[] }>;
    if (Array.isArray(categories) && Array.isArray(series) && series.length > 0) {
      const data = categories.map((cat, i) => {
        const row: Record<string, unknown> = { category: cat };
        for (const s of series) {
          row[s.name] = s.values?.[i];
        }
        return row;
      });
      return { data, xKey: "category", yKey: series[0].name, yKeys: series.map((s) => s.name) };
    }
  }

  // Format B: encoding.data array + encoding.x/y field names (normalized)
  if (Array.isArray(enc.data) && enc.x && enc.y && typeof enc.x === "string" && typeof enc.y === "string") {
    return { data: enc.data as Array<Record<string, unknown>>, xKey: enc.x, yKey: enc.y };
  }

  // Format C: x and y as parallel arrays (gpt-oss raw format)
  const xArr = (enc.x ?? raw.x) as unknown;
  const yArr = (enc.y ?? raw.y) as unknown;
  if (Array.isArray(xArr) && Array.isArray(yArr)) {
    const xLabel = String(enc.x_label ?? raw.x_label ?? "x");
    const yLabel = String(enc.y_label ?? raw.y_label ?? "y");
    const data = xArr.map((x: unknown, i: number) => ({ [xLabel]: x, [yLabel]: yArr[i] }));
    return { data, xKey: xLabel, yKey: yLabel };
  }

  // Format D: data as array of objects, auto-detect keys
  if (Array.isArray(rawData) && rawData.length > 0) {
    const keys = Object.keys(rawData[0] as Record<string, unknown>);
    return { data: rawData as Array<Record<string, unknown>>, xKey: keys[0] ?? "x", yKey: keys[1] ?? "y" };
  }

  return { data: [], xKey: "x", yKey: "y" };
}

export function ChartRenderer({ visual }: { visual: Visual }) {
  // KPI renders as a card — handle multiple formats
  const raw = visual as Record<string, unknown>;
  if (visual.type === "kpi" || (raw.value !== undefined && raw.label !== undefined)) {
    const enc = visual.encoding ?? {};
    const d = (enc.data ?? raw.data ?? raw) as Record<string, unknown>;
    return (
      <KPICard kpi={{ value: String(d.value ?? raw.value ?? ""), label: String(d.label ?? raw.label ?? visual.title ?? ""), sentiment: "neutral" }} />
    );
  }

  const { data, xKey, yKey, yKeys } = extractData(visual);
  const allYKeys = yKeys ?? [yKey];

  if (data.length === 0) {
    return (
      <div className="w-full h-40 flex items-center justify-center rounded-xl bg-surface-sunken border border-border text-sm text-text-faint">
        No chart data available
      </div>
    );
  }

  const chartType = (visual.type ?? (visual as Record<string, unknown>).chart_type ?? "bar") as string;
  const title = String(visual.title ?? "");

  return (
    <ChartErrorBoundary title={title}>
      <div className="w-full">
        {title && <h4 className="text-sm font-medium text-text-primary mb-3">{title}</h4>}
        <div className="w-full h-72">
          <ResponsiveContainer width="100%" height="100%">
            {chartType === "line" || chartType === "area" ? (
              <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)", fontSize: 12 }} />
                {allYKeys.map((k, i) => (
                  <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name={k} />
                ))}
              </LineChart>
            ) : chartType === "scatter" ? (
              <ScatterChart margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" />
                <YAxis dataKey={yKey} tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)", fontSize: 12 }} />
                <Scatter data={data} fill="#6E56CF" />
              </ScatterChart>
            ) : chartType === "pie" ? (
              <PieChart>
                <Pie data={data} dataKey={yKey} nameKey={xKey} cx="50%" cy="50%" innerRadius={40} outerRadius={100} paddingAngle={2} label={{ fontSize: 11 }}>
                  {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)", fontSize: 12 }} />
              </PieChart>
            ) : (
              /* Default: bar chart (supports grouped bars via multiple yKeys) */
              <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" angle={data.length > 6 ? -35 : 0} textAnchor={data.length > 6 ? "end" : "middle"} height={data.length > 6 ? 80 : 30} />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)", fontSize: 12 }} />
                {allYKeys.map((k, i) => (
                  <Bar key={k} dataKey={k} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} name={k} />
                ))}
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
        {visual.caption && <p className="text-xs text-text-tertiary mt-1">{String(visual.caption)}</p>}
      </div>
    </ChartErrorBoundary>
  );
}
