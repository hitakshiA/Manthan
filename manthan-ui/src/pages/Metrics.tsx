/**
 * Metrics - daily timeseries of case flow + recovered $$.
 *
 * Editorial form: KPIs are tabular numerals on a single hairline row
 * (no card-per-KPI grid). Sparklines are quiet - 1px stroke, no fill.
 * Bar charts use the surface tone, not rainbow legends.
 */

import { useEffect, useMemo, useState } from "react";

import {
  ErrorRow,
  LoadingRow,
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import { getMetricsTimeseries, type MetricsDay } from "@/lib/api";

const KPI_LABELS: { key: keyof MetricsDay | "recovered_dollars"; label: string; format: (n: number) => string }[] = [
  { key: "opened", label: "Opened", format: (n) => n.toLocaleString() },
  { key: "resolved", label: "Resolved", format: (n) => n.toLocaleString() },
  { key: "refunds", label: "Refunds", format: (n) => n.toLocaleString() },
  {
    key: "recovered_dollars",
    label: "Recovered",
    format: (n) => `$${Math.round(n / 100).toLocaleString()}`,
  },
];

export default function Metrics() {
  const [days, setDays] = useState<MetricsDay[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMetricsTimeseries(30)
      .then((r) => setDays(r.days))
      .catch((e: Error) => setError(e.message));
  }, []);

  const totals = useMemo(() => {
    if (!days) return null;
    const sum = (arr: number[]) => arr.reduce((a, b) => a + b, 0);
    return {
      opened: sum(days.map((d) => d.opened)),
      resolved: sum(days.map((d) => d.resolved)),
      refunds: sum(days.map((d) => d.refunds)),
      recovered_dollars: sum(days.map((d) => d.recovered_minor)),
    } as Record<string, number>;
  }, [days]);

  return (
    <PageBody>
      <PageHeader
        eyebrow="Metrics · last 30 days"
        title="How Manthan is doing"
        meta="Case flow + recovery dollars across this workspace."
      />

      {error && <ErrorRow>{error}</ErrorRow>}
      {days === null && !error && <LoadingRow />}

      {days && totals && (
        <>
          <Section eyebrow="At a glance">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-5">
              {KPI_LABELS.map((k) => (
                <KPI
                  key={k.label}
                  label={k.label}
                  value={k.format(totals[k.key as string] ?? 0)}
                  sparkData={days.map((d) =>
                    k.key === "recovered_dollars"
                      ? (d.recovered_minor as number) / 100
                      : ((d[k.key as keyof MetricsDay] as number) ?? 0),
                  )}
                />
              ))}
            </div>
          </Section>

          <Section
            eyebrow="Case flow"
            trailing={
              <span className="tabular-nums">
                <Dot color="var(--color-ink-strong)" /> opened &nbsp;&nbsp;
                <Dot color="var(--color-accent)" /> resolved
              </span>
            }
          >
            <StackedBarChart
              data={days}
              series={[
                { key: "opened", color: "var(--color-ink-strong)" },
                { key: "resolved", color: "var(--color-accent)" },
              ]}
            />
          </Section>

          <Section
            eyebrow="Decision breakdown"
            trailing={
              <span className="tabular-nums">
                <Dot color="var(--color-accent)" /> refund &nbsp;&nbsp;
                <Dot color="var(--color-amber)" /> fight &nbsp;&nbsp;
                <Dot color="var(--color-danger)" /> escalate
              </span>
            }
          >
            <StackedBarChart
              data={days}
              series={[
                { key: "refunds", color: "var(--color-accent)" },
                { key: "fights", color: "var(--color-amber)" },
                { key: "escalates", color: "var(--color-danger)" },
              ]}
            />
          </Section>
        </>
      )}
    </PageBody>
  );
}

// ──────────────────────────────────────────────────────────────────────
// KPI - label + tabular numeral + 1px sparkline.
// ──────────────────────────────────────────────────────────────────────

function KPI({
  label,
  value,
  sparkData,
}: {
  label: string;
  value: string;
  sparkData: number[];
}) {
  return (
    <div>
      <div
        className="eyebrow"
        style={{ color: "var(--color-ink-faint)" }}
      >
        {label}
      </div>
      <div
        className="font-display tabular-nums text-[28px] leading-[1.1] mt-1"
        style={{ color: "var(--color-ink-strong)" }}
      >
        {value}
      </div>
      <Sparkline data={sparkData} />
    </div>
  );
}

function Sparkline({ data }: { data: number[] }) {
  if (data.length === 0) return null;
  const w = 120;
  const h = 22;
  const max = Math.max(1, ...data);
  const pts = data
    .map((v, i) => {
      const x = (i / Math.max(1, data.length - 1)) * w;
      const y = h - (v / max) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      width="100%"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="block mt-1.5"
      style={{ height: 22 }}
    >
      <polyline
        points={pts}
        fill="none"
        stroke="var(--color-ink-muted)"
        strokeOpacity="0.55"
        strokeWidth="1"
      />
    </svg>
  );
}

// ──────────────────────────────────────────────────────────────────────
// StackedBarChart - pure CSS, hover tooltip via title attr.
// ──────────────────────────────────────────────────────────────────────

function StackedBarChart({
  data,
  series,
}: {
  data: MetricsDay[];
  series: { key: keyof MetricsDay; color: string }[];
}) {
  const max = Math.max(
    1,
    ...data.map((d) =>
      series.reduce((acc, s) => acc + (Number(d[s.key]) || 0), 0),
    ),
  );
  return (
    <div
      className="flex items-end gap-[3px] h-28 border-t border-b py-[1px]"
      style={{ borderColor: "var(--color-rule-soft)" }}
    >
      {data.map((d, i) => {
        const total = series.reduce(
          (acc, s) => acc + (Number(d[s.key]) || 0),
          0,
        );
        const heightPct = (total / max) * 100;
        const tooltip = `${d.day}  ·  ${series.map((s) => `${String(s.key)}: ${d[s.key]}`).join("  ·  ")}`;
        return (
          <div
            key={i}
            className="flex-1 flex flex-col justify-end min-w-0"
            title={tooltip}
          >
            <div
              className="flex flex-col-reverse"
              style={{ height: `${heightPct}%`, minHeight: total > 0 ? 1 : 0 }}
            >
              {series.map((s) => {
                const v = Number(d[s.key]) || 0;
                if (v === 0) return null;
                return (
                  <div
                    key={String(s.key)}
                    style={{
                      background: s.color,
                      height: `${(v / Math.max(1, total)) * 100}%`,
                    }}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Dot({ color }: { color: string }) {
  return (
    <span
      className="inline-block h-[5px] w-[5px] rounded-full align-middle mr-1.5"
      style={{ background: color }}
    />
  );
}
