import { Component, type ReactNode } from "react";
import type { Visual } from "@/types/render-spec";
import { KPICard } from "@/components/render/shared/KPICard";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, AreaChart, Area,
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

/** Extract chart data from the visual — handles all agent formats */
function extractData(visual: Visual): { data: Array<Record<string, unknown>>; xKey: string; yKey: string } {
  const enc = visual.encoding ?? {};
  const raw = visual as Record<string, unknown>;

  // Format 1: encoding.data is an array of objects with encoding.x and encoding.y as field names
  if (Array.isArray(enc.data) && enc.x && enc.y) {
    return { data: enc.data as Array<Record<string, unknown>>, xKey: enc.x as string, yKey: enc.y as string };
  }

  // Format 2: x and y are parallel arrays (raw agent format)
  const xArr = (enc.x ?? raw.x) as unknown;
  const yArr = (enc.y ?? raw.y) as unknown;
  if (Array.isArray(xArr) && Array.isArray(yArr)) {
    const xLabel = String(enc.x_label ?? raw.x_label ?? "x");
    const yLabel = String(enc.y_label ?? raw.y_label ?? "y");
    const data = xArr.map((x: unknown, i: number) => ({
      [xLabel]: x,
      [yLabel]: yArr[i],
    }));
    return { data, xKey: xLabel, yKey: yLabel };
  }

  // Format 3: encoding.data with auto-detected keys
  if (Array.isArray(enc.data) && enc.data.length > 0) {
    const keys = Object.keys(enc.data[0] as Record<string, unknown>);
    return { data: enc.data as Array<Record<string, unknown>>, xKey: keys[0] ?? "x", yKey: keys[1] ?? "y" };
  }

  return { data: [], xKey: "x", yKey: "y" };
}

export function ChartRenderer({ visual }: { visual: Visual }) {
  // KPI renders as a card
  if (visual.type === "kpi") {
    const enc = visual.encoding ?? {};
    const raw = visual as Record<string, unknown>;
    const d = (enc.data ?? raw.data ?? enc) as Record<string, unknown>;
    return (
      <KPICard kpi={{ value: String(d.value ?? ""), label: String(d.label ?? visual.title), sentiment: "neutral" }} />
    );
  }

  const { data, xKey, yKey } = extractData(visual);

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
                <Line type="monotone" dataKey={yKey} stroke="#6E56CF" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
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
              /* Default: bar chart */
              <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey={xKey} tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" angle={data.length > 6 ? -35 : 0} textAnchor={data.length > 6 ? "end" : "middle"} height={data.length > 6 ? 80 : 30} />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--color-text-faint)" />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)", fontSize: 12 }} />
                <Bar dataKey={yKey} fill="#6E56CF" radius={[4, 4, 0, 0]} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
        {visual.caption && <p className="text-xs text-text-tertiary mt-1">{String(visual.caption)}</p>}
      </div>
    </ChartErrorBoundary>
  );
}
