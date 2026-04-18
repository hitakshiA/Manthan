/**
 * Derive the four exec-voice suggestion chips from a dataset's schema.
 *
 * The analyst persona adapts to the domain — a startup-funding dataset
 * shouldn't ask about "best customers" and a patient-records dataset
 * shouldn't ask about "revenue growth". We pick a primary metric, a
 * primary entity (from identifier columns), and whether there's a
 * time dimension, then template the four questions from those inputs.
 */

import type { SchemaSummary } from "@/types/api";
import type { ComponentType } from "react";
import { TrendingUp, AlertTriangle, Users, Shield } from "lucide-react";

export interface ExecChip {
  icon: ComponentType<{ size?: number; className?: string }>;
  label: string;
  text: string;
}

function humanize(raw: string): string {
  return raw
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim()
    .toLowerCase();
}

function stripIdSuffix(name: string): string {
  return name
    .replace(/[_\s-]id$/i, "")
    .replace(/[_\s-]sku$/i, "")
    .replace(/[_\s-]key$/i, "")
    .replace(/[_\s-]number$/i, "")
    .trim();
}

function pluralize(word: string): string {
  if (!word) return word;
  if (/(s|x|z|ch|sh)$/i.test(word)) return word;
  if (/[^aeiou]y$/i.test(word)) return word.slice(0, -1) + "ies";
  return word + "s";
}

function derivePrimaryMetric(schema: SchemaSummary | null): string {
  // Governed metrics first — if the entity declares them, that IS the
  // primary metric, no domain guessing. Exec's mental model is the
  // contract; we just echo it back.
  const governed = schema?.entity?.metrics ?? [];
  if (governed.length > 0) {
    const primary = governed[0];
    return (primary.label || primary.slug).toLowerCase();
  }

  const metrics = schema?.columns.filter((c) => c.role === "metric") ?? [];
  if (metrics.length === 0) return "performance";

  // Tiered priority — look for aggregate money / volume words FIRST, before
  // line-item words like "price" or generic "amount". A food-delivery
  // dataset with "unit_price" plus "subtotal" should land on "revenue",
  // not "pricing". The exec thinks in aggregate outcomes.
  //
  // The money context only fires when there's actual money vocabulary in
  // the schema — otherwise a flights dataset with "flights_total" would
  // get labeled "revenue" which is nonsense.
  const colText = (schema?.columns ?? [])
    .map((c) => `${c.name} ${c.description ?? ""}`)
    .join(" ")
    .toLowerCase();
  const hasMoneyContext =
    /revenue|sales|funding|subtotal|gross|net|spend|cost|price|payment|invoice|charge|fee|usd|eur|gbp|money|\$/.test(
      colText,
    );
  const hasCompanyContext = /company|startup|firm|investor|portfolio/.test(colText);
  const moneyContext = hasCompanyContext ? "funding" : "revenue";

  type Tier = { pattern: RegExp; label: string | null; requiresMoney?: boolean };
  const tiers: Tier[] = [
    { pattern: /revenue/i, label: "revenue" },
    { pattern: /sales/i, label: "sales" },
    { pattern: /funding|capital|raised/i, label: "funding" },
    { pattern: /subtotal|gross|net/i, label: moneyContext, requiresMoney: true },
    { pattern: /spend/i, label: "spend" },
    { pattern: /cost/i, label: "costs" },
    // Flight / logistics / ops vocabulary — evaluated BEFORE the generic
    // (amount/total/value) fallback so a flights dataset lands on the
    // right word instead of "revenue".
    { pattern: /flight/i, label: "flights" },
    { pattern: /deliver/i, label: "deliveries" },
    { pattern: /shipment|parcel/i, label: "shipments" },
    { pattern: /delay|late|cancel/i, label: "delays" },
    { pattern: /trip|ride/i, label: "trips" },
    { pattern: /\border(s|_)?\b|^orders$/i, label: "order volume" },
    { pattern: /transactions?/i, label: "transaction volume" },
    { pattern: /quantity|units|inventory/i, label: "volume" },
    { pattern: /\bcount\b|^count|^num_|^n_/i, label: "volume" },
    { pattern: /payment/i, label: "payments" },
    { pattern: /tip/i, label: "tips" },
    { pattern: /fee/i, label: "fees" },
    { pattern: /price/i, label: "pricing" },
    { pattern: /rating|score|nps|satisfaction/i, label: "ratings" },
    { pattern: /duration/i, label: "timing" },
    // "amount" / "total" / "value" are ambiguous — only trust them as
    // money when the surrounding schema has actual money vocabulary.
    { pattern: /(amount|total|value)/i, label: null },
  ];

  for (const { pattern, label, requiresMoney } of tiers) {
    if (requiresMoney && !hasMoneyContext) continue;
    const match = metrics.find((c) => pattern.test(c.name));
    if (match) {
      if (label !== null) return label;
      // Ambiguous "total/amount/value" — fall through to money context
      // only if we actually have money vocabulary.
      if (hasMoneyContext) return moneyContext;
      // Otherwise, humanize the matched column for a safer word.
      return humanize(match.label || match.name) || "performance";
    }
  }

  // Fallback — humanize the first metric's label (not raw name, not
  // currency words) so the question actually reads like the data.
  const cleaned = humanize(
    stripIdSuffix(metrics[0].label || metrics[0].name),
  )
    .replace(/\b(usd|eur|gbp|inr|jpy|cad|aud)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned || "performance";
}

function deriveEntity(schema: SchemaSummary | null, datasetName: string): string {
  const identifiers = schema?.columns.filter((c) => c.role === "identifier") ?? [];
  if (identifiers.length > 0) {
    // customer_id → customers, order_id → orders, company_sku → companies
    const base = humanize(stripIdSuffix(identifiers[0].name));
    if (base) return pluralize(base);
  }
  // Fall back to the dataset name if it reads like a noun phrase
  const fromName = humanize(datasetName).split(" ").pop() ?? "";
  if (fromName && fromName.length > 2) return pluralize(fromName);
  return "performers";
}

function hasTemporal(schema: SchemaSummary | null): boolean {
  return (schema?.columns.some((c) => c.role === "temporal") ?? false);
}

export function deriveExecChips(
  schema: SchemaSummary | null,
  datasetName: string,
): ExecChip[] {
  const metric = derivePrimaryMetric(schema);
  const entity = deriveEntity(schema, datasetName);
  const temporal = hasTemporal(schema);
  const dsLabel = datasetName || "this dataset";

  // Question 1 — growth / distribution of the headline metric
  const growthChip: ExecChip = temporal
    ? {
        icon: TrendingUp,
        label: `Where's ${metric} growth?`,
        text: `Where is ${metric} growth coming from in ${dsLabel}? Break it down by the dimensions that matter most and tell me what's driving it.`,
      }
    : {
        icon: TrendingUp,
        label: `Where's ${metric} strongest?`,
        text: `Where is ${metric} strongest in ${dsLabel}? Break it down by the dimensions that matter most and tell me what's driving the concentration.`,
      };

  // Question 2 — what's dragging the headline metric
  const dragChip: ExecChip = {
    icon: AlertTriangle,
    label: `What's dragging ${metric}?`,
    text: `What's dragging ${metric} down in ${dsLabel}? Find the biggest concentrations of underperformance and recommend what I should do about it.`,
  };

  // Question 3 — segment / compare. For transactional entities (orders,
  // transactions, events, sessions, payments) "Top orders" reads oddly;
  // ask about the drivers instead. For noun-like entities (customers,
  // companies, products, properties) keep the "Top X" framing.
  const isTransactional = /^(orders?|transactions?|events?|sessions?|payments?|visits?|clicks?|trips?|rides?)$/i.test(entity);
  const segmentChip: ExecChip = isTransactional
    ? {
        icon: Users,
        label: `Who drives most ${entity}?`,
        text: `Who or what drives most of the ${entity} in ${dsLabel}? Segment the drivers by the dimensions that matter and tell me what distinguishes the top contributors from everyone else.`,
      }
    : {
        icon: Users,
        label: `Top ${entity}?`,
        text: `Who/what are the top-performing ${entity} in ${dsLabel}, and why? Segment them meaningfully and tell me what makes the leaders different from the rest.`,
      };

  // Question 4 — risks / anomalies / worries
  const riskChip: ExecChip = {
    icon: Shield,
    label: "What should I worry about?",
    text: `What should I worry about in ${dsLabel}? Surface the anomalies, outliers, concentrations of risk, and data-quality issues I should know about before making decisions.`,
  };

  return [growthChip, dragChip, segmentChip, riskChip];
}
