import type { Visual } from "@/types/render-spec";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type EChartsOption = Record<string, any>;

/** Map a render_spec Visual's encoding to an ECharts option object */
export function toEChartsOption(visual: Visual): EChartsOption {
  const enc = visual.encoding;
  const data = (enc.data ?? []) as Array<Record<string, unknown>>;
  const xField = (enc.x as string) ?? "";
  const yField = (enc.y as string) ?? "";
  const type = visual.type;

  const xValues = data.map((d) => d[xField] as string);
  const yValues = data.map((d) => d[yField] as number);

  const base: EChartsOption = {
    animation: true,
    animationDuration: 600,
    animationEasing: "cubicOut",
    grid: { left: 48, right: 24, top: 40, bottom: 48, containLabel: true },
    tooltip: { trigger: "axis", backgroundColor: "oklch(98% 0.006 65)", borderColor: "oklch(90% 0.005 65)" },
  };

  switch (type) {
    case "bar":
      return {
        ...base,
        xAxis: { type: "category", data: xValues, axisLabel: { rotate: xValues.length > 8 ? 35 : 0, fontSize: 11 } },
        yAxis: { type: "value", axisLabel: { fontSize: 11 } },
        series: [{ type: "bar", data: yValues, itemStyle: { color: "oklch(55% 0.18 265)", borderRadius: [3, 3, 0, 0] } }],
      };

    case "line":
    case "area":
      return {
        ...base,
        xAxis: { type: "category", data: xValues, boundaryGap: false, axisLabel: { fontSize: 11 } },
        yAxis: { type: "value", axisLabel: { fontSize: 11 } },
        series: [{
          type: "line",
          data: yValues,
          smooth: true,
          areaStyle: type === "area" ? { opacity: 0.15 } : undefined,
          itemStyle: { color: "oklch(55% 0.18 265)" },
          lineStyle: { width: 2 },
        }],
      };

    case "scatter":
    case "bubble":
      return {
        ...base,
        tooltip: { trigger: "item" },
        xAxis: { type: "value", name: xField, axisLabel: { fontSize: 11 } },
        yAxis: { type: "value", name: yField, axisLabel: { fontSize: 11 } },
        series: [{
          type: "scatter",
          data: data.map((d) => [d[xField], d[yField]]),
          itemStyle: { color: "oklch(55% 0.18 265)", opacity: 0.7 },
        }],
      };

    case "pie":
      return {
        ...base,
        tooltip: { trigger: "item" },
        series: [{
          type: "pie",
          radius: ["35%", "65%"],
          data: data.map((d) => ({ name: d[xField] as string, value: d[yField] as number })),
          label: { fontSize: 11 },
          emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: "rgba(0,0,0,0.1)" } },
        }],
      };

    case "heatmap":
      return {
        ...base,
        tooltip: { trigger: "item" },
        xAxis: { type: "category", data: [...new Set(data.map((d) => d[xField] as string))], axisLabel: { fontSize: 10, rotate: 35 } },
        yAxis: { type: "category", data: [...new Set(data.map((d) => d[yField] as string))], axisLabel: { fontSize: 10 } },
        visualMap: { min: 0, max: Math.max(...data.map((d) => d.value as number ?? 0)), calculable: true, orient: "horizontal", left: "center", bottom: 0, inRange: { color: ["oklch(95% 0.02 265)", "oklch(55% 0.18 265)"] } },
        series: [{
          type: "heatmap",
          data: data.map((d) => [d[xField], d[yField], d.value]),
          label: { show: data.length < 50, fontSize: 10 },
        }],
      };

    case "histogram":
      return {
        ...base,
        xAxis: { type: "category", data: xValues, axisLabel: { fontSize: 11 } },
        yAxis: { type: "value", axisLabel: { fontSize: 11 } },
        series: [{ type: "bar", data: yValues, itemStyle: { color: "oklch(55% 0.18 265)", borderRadius: [2, 2, 0, 0] }, barWidth: "90%" }],
      };

    case "funnel":
      return {
        ...base,
        tooltip: { trigger: "item" },
        series: [{
          type: "funnel",
          left: "10%",
          width: "80%",
          data: data.map((d) => ({ name: d[xField] as string, value: d[yField] as number })),
          label: { fontSize: 11 },
        }],
      };

    default:
      // Fallback: bar chart
      return {
        ...base,
        xAxis: { type: "category", data: xValues, axisLabel: { fontSize: 11 } },
        yAxis: { type: "value", axisLabel: { fontSize: 11 } },
        series: [{ type: "bar", data: yValues, itemStyle: { color: "oklch(55% 0.18 265)" } }],
      };
  }
}
