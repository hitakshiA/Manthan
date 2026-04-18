import {
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { AlertTriangle, Copy, Check, Expand } from "lucide-react";
import type { InlineVisualBlock as InlineVisualType } from "@/types/conversation";
import { useUIStore } from "@/stores/ui-store";

/**
 * Inline chart/widget rendered in a sandboxed iframe.
 *
 * Why this is defensive — inline visuals were crashing the tab before
 * we hardened them. Lag-before-crash was the clue: symptoms of memory
 * pressure from too many iframes, unbounded HTML, and Chart.js loaded
 * from CDN per-instance. Guards now in place:
 *   1. HTML size cap — >300KB renders a fallback panel instead of
 *      shoving a giant srcDoc into the DOM.
 *   2. Lazy mount via IntersectionObserver — the iframe only mounts
 *      when scrolled near, keeping the initial stream light.
 *   3. Auto-height via postMessage from inside the iframe (with a
 *      1200px cap + internal scroll) — no more clipped charts, no
 *      runaway heights.
 *   4. Error boundary — a broken visual can't unwind the stream.
 *   5. Expand-to-side-panel — the user can pop any visual into the
 *      right column (same ergonomics as artifacts).
 */

const MAX_HTML_BYTES = 300_000;
const MAX_AUTO_HEIGHT = 1200;
const MIN_HEIGHT = 160;

const WRAPPER_HEAD = `<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{background:transparent}
body{font-family:'Inter',sans-serif;color:#262625;line-height:1.55;
  -webkit-font-smoothing:antialiased;padding:16px 20px;overflow:visible}
.serif{font-family:'Instrument Serif',serif}
.card{background:#fff;border:1px solid #e8e8e7;border-radius:10px;padding:16px 20px}
.kpi-value{font-family:'Instrument Serif',serif;font-size:28px;color:#262625;line-height:1}
.kpi-label{font-size:11px;font-weight:600;color:#919190;text-transform:uppercase;letter-spacing:0.5px}
.kpi-delta{font-size:12px;font-weight:600}
.positive{color:#3b8263}.negative{color:#c92f31}.neutral{color:#919190}
.tag{font-size:11px;font-weight:600;padding:3px 10px;border-radius:999px;display:inline-block}
.tag-accent{background:#eae3fc;color:#6e56cf}
.tag-success{background:#e7f6f0;color:#3b8263}
.tag-warning{background:#fcf5e0;color:#bd9e14}
.tag-error{background:#feeced;color:#c92f31}
.flex{display:flex}.gap-3{gap:12px}.gap-4{gap:16px}
.grid{display:grid;gap:12px}
.grid-2{grid-template-columns:1fr 1fr}
.grid-3{grid-template-columns:1fr 1fr 1fr}
.grid-4{grid-template-columns:1fr 1fr 1fr 1fr}
.text-sm{font-size:13px}.text-xs{font-size:11px}
.text-muted{color:#919190}.text-faint{color:#b6b6b5}
.font-semibold{font-weight:600}.font-bold{font-weight:700}
.mb-2{margin-bottom:8px}.mb-3{margin-bottom:12px}.mt-2{margin-top:8px}
.callout{border-radius:10px;padding:14px 18px;font-size:13px;line-height:1.5}
.callout-insight{background:#eae3fc;color:#5d42b0}
.callout-warning{background:#fcf5e0;color:#8a7200}
.callout-tip{background:#e7f6f0;color:#2d6b4f}
.callout-error{background:#feeced;color:#a12324}
.callout-title{font-weight:700;margin-bottom:4px}
canvas{max-width:100%!important;height:auto!important}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #f0f0ef}
th{color:#919190;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.4px}
</style>
</head><body>`;

function wrapperTail(visualId: string): string {
  // Report the document height back to the parent via postMessage so
  // the iframe auto-sizes to its content. We deliberately do NOT
  // intercept window.onerror: the iframe is sandboxed (no allow-
  // same-origin), which forces browsers to report every inner throw
  // as the opaque "Script error." — including harmless ones from
  // Chart.js animation callbacks. Reporting those up would replace
  // the iframe with a red error card even though the chart renders
  // fine. The sandbox is our safety net; we trust it.
  return `
<script>
(function(){
  var ID = ${JSON.stringify(visualId)};
  try {
    if (typeof Chart !== 'undefined') {
      Chart.defaults.font.family = "'Inter',sans-serif";
      Chart.defaults.font.size = 12;
      Chart.defaults.color = '#919190';
      Chart.defaults.plugins.legend.labels.usePointStyle = true;
      Chart.defaults.plugins.legend.labels.padding = 14;
      Chart.defaults.elements.line.tension = 0.3;
      Chart.defaults.elements.line.borderWidth = 2;
      Chart.defaults.elements.point.radius = 3;
      Chart.defaults.elements.bar.borderRadius = 4;
      Chart.defaults.animation = { duration: 250 };
    }
  } catch (_) { /* don't let theme tweaks break the viz */ }

  function reportHeight() {
    try {
      var h = Math.max(
        document.body ? document.body.scrollHeight : 0,
        document.documentElement ? document.documentElement.scrollHeight : 0
      );
      parent.postMessage({ source: 'manthan-viz', id: ID, type: 'height', height: h }, '*');
    } catch (_) {}
  }

  window.addEventListener('load', reportHeight);
  // Chart.js renders async; re-report a few times.
  setTimeout(reportHeight, 120);
  setTimeout(reportHeight, 400);
  setTimeout(reportHeight, 1200);
  try { new ResizeObserver(reportHeight).observe(document.body); } catch (_) {}
})();
</script>
</body></html>`;
}

// ── React error boundary so one bad visual can't tank the stream ──
class VisualErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn("[InlineVisual] render boundary caught:", error, info);
  }
  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

function HtmlTooLargeFallback({ bytes }: { bytes: number }) {
  return (
    <div className="flex items-start gap-2 p-3 rounded-md border border-warning/20 bg-warning-soft/40 text-xs text-warning font-body">
      <AlertTriangle size={14} className="mt-0.5 shrink-0" />
      <span>
        This inline view is too heavy to render safely ({Math.round(bytes / 1024)}&nbsp;KB). Ask the agent
        to simplify or open it as a full artifact instead.
      </span>
    </div>
  );
}

interface Props {
  block: InlineVisualType;
}

function InlineVisualBlockInner({ block }: Props) {
  const setExpandedVisual = useUIStore((s) => s.setExpandedVisual);

  const htmlBytes = useMemo(() => new Blob([block.html]).size, [block.html]);
  const tooLarge = htmlBytes > MAX_HTML_BYTES;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);
  const [height, setHeight] = useState<number>(
    Math.min(Math.max(block.height ?? MIN_HEIGHT, MIN_HEIGHT), MAX_AUTO_HEIGHT),
  );
  const [copied, setCopied] = useState(false);

  const srcDoc = useMemo(() => {
    if (tooLarge) return "";
    return WRAPPER_HEAD + block.html + wrapperTail(block.visual_id);
  }, [block.html, block.visual_id, tooLarge]);

  // Lazy mount: only spin up the iframe once the container is near the viewport.
  useEffect(() => {
    if (tooLarge) return;
    const el = containerRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            // Once mounted, stop observing — keep the iframe alive so the
            // user can scroll away and back without losing chart state.
            io.disconnect();
            return;
          }
        }
      },
      { rootMargin: "300px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [tooLarge]);

  // Listen for height messages from the iframe. We no longer surface
  // runtime errors — the sandbox obscures them as "Script error." and
  // the iframe still renders whatever succeeded; a red error banner
  // over a working chart is worse than a bit of silent breakage.
  useEffect(() => {
    if (tooLarge || !inView) return;
    const handler = (e: MessageEvent) => {
      const data = e.data;
      if (!data || data.source !== "manthan-viz" || data.id !== block.visual_id) return;
      if (data.type === "height" && typeof data.height === "number") {
        const clamped = Math.max(MIN_HEIGHT, Math.min(data.height + 4, MAX_AUTO_HEIGHT));
        setHeight((prev) => (Math.abs(prev - clamped) > 2 ? clamped : prev));
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [block.visual_id, tooLarge, inView]);

  const copy = () => {
    navigator.clipboard.writeText(block.html).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const expand = () => {
    setExpandedVisual({
      visual_id: block.visual_id,
      visual_type: block.visual_type,
      html: block.html,
      height,
    });
  };

  return (
    <div
      ref={containerRef}
      className="rounded-md border border-border bg-surface-raised overflow-hidden"
    >
      {/* Slim toolbar — mirrors the artifact card affordance */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/70 bg-surface-1">
        <span className="text-[11px] text-text-faint font-body capitalize">
          {block.visual_type.replace(/_/g, " ")}
        </span>
        <div className="flex items-center gap-0.5">
          <button
            onClick={copy}
            title="Copy HTML"
            className="p-1 text-text-faint hover:text-text-secondary rounded hover:bg-surface-sunken transition-colors"
          >
            {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
          </button>
          <button
            onClick={expand}
            title="Expand to side panel"
            className="p-1 text-text-faint hover:text-text-secondary rounded hover:bg-surface-sunken transition-colors"
          >
            <Expand size={12} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="p-0">
        {tooLarge ? (
          <div className="p-3">
            <HtmlTooLargeFallback bytes={htmlBytes} />
          </div>
        ) : inView ? (
          <iframe
            srcDoc={srcDoc}
            className="w-full border-0 bg-transparent block"
            style={{ height }}
            sandbox="allow-scripts"
            loading="lazy"
            referrerPolicy="no-referrer"
            title={`Inline visual: ${block.visual_type}`}
          />
        ) : (
          // Placeholder before the iframe mounts — keeps scroll stable.
          <div
            className="w-full animate-shimmer"
            style={{ height }}
            aria-hidden="true"
          />
        )}
      </div>
    </div>
  );
}

export function InlineVisualBlock({ block }: Props) {
  return (
    <VisualErrorBoundary
      fallback={
        <div className="rounded-md border border-error/20 bg-error-soft/40 p-3 text-xs text-error font-body flex items-start gap-2">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>This inline view failed to render. Skipping it — the rest of the conversation is unaffected.</span>
        </div>
      }
    >
      <InlineVisualBlockInner block={block} />
    </VisualErrorBoundary>
  );
}
