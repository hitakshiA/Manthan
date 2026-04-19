import { useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAgentStore } from "@/stores/agent-store";
import { useSmoothText } from "@/lib/smooth-text";
import type { NumericClaim } from "@/types/conversation";

/**
 * Pre-process: wrap every known numeric-claim rendering with a
 * markdown link using the ``claim:`` scheme. The custom ``a`` renderer
 * below converts those into click-to-audit buttons.
 *
 * Matching is fuzzy on purpose — each claim carries a list of
 * ``formatted_variants`` (``$706K``, ``$0.7M``, ``706,532``), so the
 * underline survives when the agent's prose format drifts from the
 * tool output's format.
 *
 * Longest-first (by variant length) so ``$13.1B`` wins over ``$13``
 * when both could match.
 *
 * The ``[value]()`` empty-href convention from the agent stays
 * clickable even when no claim backs it — we route it to a
 * synthetic "free-form" drawer so the exec can still see *some*
 * provenance (the run id, the SQL context, the dataset name). A
 * missing claim should produce a weaker drawer, never a silent unwrap.
 */
const FREEFORM_CLAIM_SCHEME = "claim:free";

function injectClaimLinks(text: string, claims: NumericClaim[]): string {
  if (!text) return text;
  // Map every variant to the first claim index that declared it.
  const byVariant = new Map<string, number>();
  claims.forEach((c, i) => {
    const variants = c.formatted_variants?.length ? c.formatted_variants : [c.formatted];
    for (const v of variants) {
      if (v && !byVariant.has(v)) byVariant.set(v, i);
    }
  });
  let out = text;

  // Rewrite `[text]()` first. If the bracketed text matches a known
  // variant, route it to that specific claim. Otherwise leave the
  // empty-href link as a FREEFORM marker — we'll render it as a
  // softer underline that opens a generic provenance drawer.
  out = out.replace(/\[([^\]]+)\]\(\)/g, (_, inner) => {
    const trimmed = String(inner).trim();
    const idx = byVariant.get(trimmed);
    if (idx != null) return `[${inner}](claim:${idx})`;
    // Preserve the click affordance; the link renderer will show a
    // generic audit drawer because the URL lacks a numeric index.
    return `[${inner}](${FREEFORM_CLAIM_SCHEME})`;
  });

  if (!claims.length) return out;

  // Walk the string in alternating spans — text regions where we
  // safely wrap bare variants, and already-linked regions
  // (``[text](href)``) which we pass through untouched. This is the
  // only way to avoid inserting a link-inside-a-link when a new
  // variant happens to be a substring of a prior wrap's text.
  const entries = [...byVariant.entries()].sort(
    (a, b) => b[0].length - a[0].length,
  );
  const LINK_RE = /\[[^\]]+\]\([^)]*\)/g;
  const pieces: string[] = [];
  let cursor = 0;
  for (const m of out.matchAll(LINK_RE)) {
    const start = m.index ?? 0;
    if (start > cursor) {
      pieces.push(wrapBare(out.slice(cursor, start), entries));
    }
    pieces.push(m[0]); // preserve existing link verbatim
    cursor = start + m[0].length;
  }
  if (cursor < out.length) {
    pieces.push(wrapBare(out.slice(cursor), entries));
  }
  return pieces.join("");
}

function wrapBare(text: string, entries: [string, number][]): string {
  let out = text;
  for (const [variant, idx] of entries) {
    if (!variant.trim()) continue;
    const escaped = variant.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // Require a non-word boundary on both sides so ``$13.1M`` inside a
    // longer token doesn't accidentally match. Leading ``$`` isn't a
    // word char, so a naïve ``\b`` wouldn't work; we hand-roll it.
    const re = new RegExp(
      `(?<![\\w])${escaped}(?![\\w])`,
      "g",
    );
    out = out.replace(re, `[${variant}](claim:${idx})`);
  }
  return out;
}

/**
 * Narrative block — renders the agent's commentary between thinking groups.
 * Explicit component styles (not relying on @tailwindcss/typography).
 */
export function NarrativeBlock({ text }: { text: string }) {
  const claims = useAgentStore((s) => s.numericClaims);
  const setInspected = useAgentStore((s) => s.setInspectedClaim);
  // Stable per-block key so the smoothing engine treats each
  // NarrativeBlock as its own stream. Using a ref here instead of an
  // id prop means callers don't have to thread keys through.
  const streamKeyRef = useRef<string>(
    `narr-${Math.random().toString(36).slice(2)}`,
  );
  // Smooth reveal — takes whatever `text` currently is (a full
  // paragraph when the backend emits narrative as one event, or a
  // growing partial if we later switch to token streaming) and
  // returns the prefix that should be visible this frame.
  const { visibleText, isAnimating } = useSmoothText(text, {
    streamKey: streamKeyRef.current,
    // The block is marked streaming until the text stabilises; when
    // the parent re-renders with the same text, the engine naturally
    // flushes and isAnimating goes false.
    isStreaming: true,
  });
  // Swap to the full text once smoothing is done so copy-paste and
  // claim-link injection see the stable final prose, not the ticking
  // prefix. While animating we render the partial — that's the whole
  // point of the smoother.
  const displayText = isAnimating ? visibleText : text;
  const processed = injectClaimLinks(displayText, claims);
  return (
    <div className="text-[15px] text-text-primary font-body leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // Default urlTransform strips unknown schemes — including our
        // ``claim:N`` scheme — replacing them with an empty string and
        // leaving numeric claims rendered as broken external links.
        // Override to pass everything through unchanged; sanitization
        // happens at the source (the agent's output is already trusted).
        urlTransform={(url) => url}
        components={{
          // Paragraph: body text, NOT bold
          p: ({ children }) => (
            <p className="my-2 first:mt-0 last:mb-0 text-text-primary">{children}</p>
          ),
          // Headings: use display font, visually distinct
          h1: ({ children }) => (
            <h1 className="font-display text-2xl text-text-primary mt-6 mb-3 tracking-tight">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="font-display text-xl text-text-primary mt-5 mb-2 tracking-tight">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[15px] font-semibold text-text-primary mt-4 mb-1.5">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-sm font-semibold text-text-primary mt-3 mb-1">{children}</h4>
          ),
          // Emphasis
          strong: ({ children }) => <strong className="font-semibold text-text-primary">{children}</strong>,
          em: ({ children }) => <em className="italic text-text-secondary">{children}</em>,
          // Lists
          ul: ({ children }) => <ul className="my-2 space-y-1 list-disc pl-5 marker:text-text-faint">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 space-y-1 list-decimal pl-5 marker:text-text-faint">{children}</ol>,
          li: ({ children }) => <li className="text-text-primary leading-relaxed pl-1">{children}</li>,
          // Inline code
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <code className="block bg-surface-sunken rounded-lg p-3 font-mono text-[12px] text-text-secondary overflow-x-auto my-2">
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-accent-soft text-accent px-1.5 py-0.5 rounded text-[13px] font-mono">
                {children}
              </code>
            );
          },
          // Tables — Claude-style clean bordered
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead>{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr className="border-b border-border last:border-b-0">{children}</tr>,
          th: ({ children }) => (
            <th className="text-left font-semibold text-text-secondary text-xs uppercase tracking-wide py-2 pr-4 border-b border-border">
              {children}
            </th>
          ),
          td: ({ children }) => <td className="py-2 pr-4 text-text-primary align-top">{children}</td>,
          // Blockquote
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-accent pl-4 my-3 text-text-secondary italic">
              {children}
            </blockquote>
          ),
          // Horizontal rule
          hr: () => <hr className="my-5 border-border" />,
          // Links — also handles our ``claim:<index>`` (resolved
          // claim) and ``claim:free`` (freeform, no backing claim)
          // schemes that the pre-processor injects around numeric
          // values. The freeform path still shows the audit
          // affordance but routes to a generic drawer built from the
          // last visible claim in the session so the exec sees *some*
          // provenance (never an unannotated bare number).
          a: ({ children, href }) => {
            if (href === "claim:free") {
              // Synthesize a drawer payload even when there are no
              // real claims — the agent sometimes cites values
              // without calling a data tool, and a silent no-op
              // click breaks trust harder than an honest
              // "unverified" drawer does.
              const latest = claims[claims.length - 1];
              const text = String(
                (Array.isArray(children) ? children.join("") : children) ?? "",
              );
              // Two cases:
              //   (a) claims exist but none matched — "Cited number"
              //       drawer, conservative provenance from latest.
              //   (b) no claims at all — "Unverified" drawer,
              //       explicit about the missing audit trail.
              const freeformClaim: NumericClaim = latest
                ? {
                    ...latest,
                    label: "Cited number",
                    description: null,
                    formatted: text || latest.formatted,
                    metric_ref: null,
                    filters_applied: [],
                    dimensions: [],
                    sql: null,
                  }
                : {
                    value: Number.NaN,
                    formatted: text,
                    formatted_variants: [text],
                    label: "Unverified number",
                    description: null,
                    entity: null,
                    metric_ref: null,
                    filters_applied: [],
                    dimensions: [],
                    grain: null,
                    sql: null,
                    row_count_scanned: null,
                    run_id: null,
                  };
              return (
                <button
                  onClick={() => setInspected(freeformClaim)}
                  className="font-semibold text-text-primary border-b-2 border-border-strong hover:border-accent hover:bg-accent-soft/30 transition-colors cursor-help"
                  title="How was this calculated?"
                >
                  {children}
                </button>
              );
            }
            if (href?.startsWith("claim:")) {
              const idx = Number(href.slice("claim:".length));
              const claim = claims[idx];
              if (!claim) return <>{children}</>;
              return (
                <button
                  onClick={() => setInspected(claim)}
                  className="font-semibold text-text-primary border-b-2 border-accent/40 hover:border-accent hover:bg-accent-soft/40 transition-colors cursor-help"
                  title={`How was ${claim.label} calculated?`}
                >
                  {children}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                {children}
              </a>
            );
          },
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}
