import { useMemo, useState } from "react";
import { X, Maximize2, Minimize2, Copy, Check } from "lucide-react";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

/** Right-side panel that mirrors ArtifactPanel for an inline visual
 *  the user promoted via the Expand affordance. Reuses the same
 *  header toolbar language so visuals and artifacts feel unified.
 *
 *  The visual HTML runs in a sandboxed iframe so the panel can't
 *  crash the main app even if the agent emits broken markup. We
 *  don't auto-size here — the panel gives the visual its full
 *  vertical space, which is the whole point of expanding it.
 */

const PANEL_WRAPPER_HEAD = `<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{background:transparent;height:100%}
body{font-family:'Inter',sans-serif;color:#262625;line-height:1.55;
  -webkit-font-smoothing:antialiased;padding:24px 28px;overflow:auto}
.serif{font-family:'Instrument Serif',serif}
.card{background:#fff;border:1px solid #e8e8e7;border-radius:10px;padding:20px 24px}
.kpi-value{font-family:'Instrument Serif',serif;font-size:36px;color:#262625;line-height:1}
.kpi-label{font-size:12px;font-weight:600;color:#919190;text-transform:uppercase;letter-spacing:0.5px}
.flex{display:flex}.gap-3{gap:12px}.gap-4{gap:16px}
.grid{display:grid;gap:14px}
.grid-2{grid-template-columns:1fr 1fr}.grid-3{grid-template-columns:1fr 1fr 1fr}.grid-4{grid-template-columns:1fr 1fr 1fr 1fr}
.callout{border-radius:10px;padding:16px 20px;font-size:14px;line-height:1.5}
.callout-insight{background:#eae3fc;color:#5d42b0}
.callout-warning{background:#fcf5e0;color:#8a7200}
.callout-tip{background:#e7f6f0;color:#2d6b4f}
.callout-error{background:#feeced;color:#a12324}
.callout-title{font-weight:700;margin-bottom:4px}
canvas{max-width:100%!important}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #f0f0ef}
th{color:#919190;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.4px}
</style></head><body>`;

const PANEL_WRAPPER_TAIL = `<script>
(function(){
  try {
    if (typeof Chart !== 'undefined') {
      Chart.defaults.font.family = "'Inter',sans-serif";
      Chart.defaults.font.size = 12;
      Chart.defaults.color = '#919190';
      Chart.defaults.plugins.legend.labels.usePointStyle = true;
      Chart.defaults.plugins.legend.labels.padding = 14;
      Chart.defaults.elements.line.tension = 0.3;
      Chart.defaults.elements.line.borderWidth = 2;
    }
  } catch (_) {}
})();
</script></body></html>`;

interface Props {
  fullscreen?: boolean;
  onToggleFullscreen?: () => void;
  onClose?: () => void;
}

export function InlineVisualPanel({ fullscreen = false, onToggleFullscreen, onClose }: Props) {
  const visual = useUIStore((s) => s.expandedVisual);
  const [copied, setCopied] = useState(false);

  const srcDoc = useMemo(() => {
    if (!visual) return "";
    return PANEL_WRAPPER_HEAD + visual.html + PANEL_WRAPPER_TAIL;
  }, [visual]);

  if (!visual) return null;

  const copyHtml = () => {
    navigator.clipboard.writeText(visual.html);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={cn("flex flex-col h-full bg-surface-0", !fullscreen && "border-l border-border")}>
      {/* Header — matches ArtifactPanel for visual consistency */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface-1 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-[11px] text-text-faint font-body uppercase tracking-wider">
            Visual
          </span>
          <span className="text-sm text-text-primary font-body font-medium truncate capitalize">
            {visual.visual_type.replace(/_/g, " ")}
          </span>
        </div>

        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={copyHtml}
            className="p-1.5 text-text-faint hover:text-text-secondary rounded-md hover:bg-surface-sunken transition-all"
            title="Copy HTML"
          >
            {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
          </button>
          {onToggleFullscreen && (
            <button
              onClick={onToggleFullscreen}
              className="p-1.5 text-text-faint hover:text-text-secondary rounded-md hover:bg-surface-sunken transition-all"
              title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 text-text-faint hover:text-text-secondary rounded-md hover:bg-surface-sunken transition-all"
              title="Close"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-hidden bg-surface-0">
        <iframe
          srcDoc={srcDoc}
          className="w-full h-full border-0 bg-white"
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
          title={`Expanded visual: ${visual.visual_type}`}
        />
      </div>
    </div>
  );
}
