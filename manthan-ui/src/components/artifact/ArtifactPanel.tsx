import { useEffect, useMemo, useState } from "react";
import {
  X,
  Maximize2,
  Minimize2,
  Download,
  Sparkles,
  AlertTriangle,
  RotateCw,
} from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";
import { useRetryLastQuery } from "@/hooks/use-send-query";
import { cn } from "@/lib/utils";

interface ArtifactPanelProps {
  fullscreen?: boolean;
  onToggleFullscreen?: () => void;
  onClose?: () => void;
}

/** Small script we inject into every artifact srcDoc so runtime errors
 *  (the kind ``node --check`` can't see — Chart.js throwing at plugin
 *  registration, typos in canvas context calls, missing DOM elements)
 *  surface as a postMessage up to the parent. Without this the dashboard
 *  silently blanks out and the exec sees nothing. */
const ARTIFACT_ERROR_BRIDGE = `
<script>
(function(){
  function post(kind, payload){
    try {
      parent.postMessage({__manthan_artifact:true, kind: kind, payload: payload}, '*');
    } catch (e) { /* sandboxed / no parent — nothing to do */ }
  }
  window.addEventListener('error', function(ev){
    // Ignore ResizeObserver loop spam and cross-origin script errors
    // (the latter come through as empty messages which add nothing).
    var msg = ev.message || '';
    if (!msg || /ResizeObserver loop/.test(msg) || msg === 'Script error.') return;
    post('runtime_error', {
      message: msg,
      source: ev.filename || '',
      line: ev.lineno || 0,
      column: ev.colno || 0,
      stack: ev.error && ev.error.stack ? String(ev.error.stack).slice(0, 2000) : ''
    });
  });
  window.addEventListener('unhandledrejection', function(ev){
    var reason = ev.reason && (ev.reason.message || ev.reason.toString()) || 'unhandled promise rejection';
    post('runtime_error', { message: String(reason).slice(0, 500), source: 'promise', line: 0, column: 0, stack: '' });
  });
})();
</script>
`;

interface ArtifactRuntimeError {
  message: string;
  source: string;
  line: number;
  column: number;
  stack: string;
}

export function ArtifactPanel({ fullscreen = false, onToggleFullscreen, onClose }: ArtifactPanelProps) {
  const artifact = useAgentStore((s) => s.artifact);
  const repairing = useAgentStore((s) => s.repairingArtifact);
  const [runtimeError, setRuntimeError] =
    useState<ArtifactRuntimeError | null>(null);
  const { retry, busy: retryBusy, lastQuestion } = useRetryLastQuery();

  // Inject the error bridge right after <head> (or before </body> if no
  // head is present). Doing it here not server-side because the agent
  // output is already written; this is a render-time safety net.
  const codeWithBridge = useMemo(() => {
    if (!artifact?.code) return "";
    const code = artifact.code;
    if (/<head[^>]*>/i.test(code)) {
      return code.replace(/<head([^>]*)>/i, `<head$1>${ARTIFACT_ERROR_BRIDGE}`);
    }
    if (/<\/body>/i.test(code)) {
      return code.replace("</body>", `${ARTIFACT_ERROR_BRIDGE}</body>`);
    }
    return ARTIFACT_ERROR_BRIDGE + code;
  }, [artifact?.code]);

  // Clear runtime-error state whenever a new artifact version lands —
  // the repair loop may have already fixed it upstream.
  useEffect(() => {
    setRuntimeError(null);
  }, [artifact?.code]);

  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      const data = ev.data as unknown;
      if (!data || typeof data !== "object") return;
      const obj = data as { __manthan_artifact?: boolean; kind?: string; payload?: ArtifactRuntimeError };
      if (!obj.__manthan_artifact) return;
      if (obj.kind === "runtime_error" && obj.payload) {
        setRuntimeError(obj.payload);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  if (!artifact) return null;

  const downloadHTML = () => {
    const blob = new Blob([artifact.code], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = artifact.filename || "dashboard.html";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className={cn("flex flex-col h-full bg-surface-0", !fullscreen && "border-l border-border")}
    >
      {/* Header — title first; HTML is an implementation detail execs
          never need to see, so the code view toggle is gone. */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-surface-1 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] text-text-faint font-body uppercase tracking-wider">
            Dashboard
          </span>
          <span className="text-sm text-text-primary font-body font-medium truncate">
            {artifact.title}
          </span>
        </div>

        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={downloadHTML}
            className="p-1.5 text-text-faint hover:text-text-secondary rounded-md hover:bg-surface-sunken transition-all"
            title="Download HTML"
          >
            <Download size={14} />
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

      {/* Repair banner — in flight while a server-side fix pass runs.
          Cleared by the next artifact_created/updated event. */}
      {repairing && (
        <div className="flex items-center gap-2 px-4 py-2 bg-accent-soft/50 border-b border-accent/20 text-[12px] text-accent font-body shrink-0">
          <Sparkles size={12} className="animate-pulse shrink-0" />
          <span className="font-medium">Polishing dashboard…</span>
          <span className="text-text-tertiary truncate">
            {repairing.reason.split("\n")[0] || "Regenerating chart code"}
          </span>
        </div>
      )}

      {/* Runtime-error banner — shown when the injected error bridge
          catches something the static validator missed (Chart.js
          config throwing, undefined global, etc.). Sits above the
          iframe so the exec sees WHY the dashboard is blank. */}
      {runtimeError && (
        <div className="flex items-start gap-2.5 px-4 py-3 bg-error-soft border-b border-error/30 font-body shrink-0">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-error" />
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-semibold text-error">
              Your query failed
            </div>
            {lastQuestion && (
              <div className="mt-1 text-[12px] text-text-primary">
                <span className="text-text-tertiary">You asked: </span>
                <span className="italic">
                  “
                  {lastQuestion.length > 140
                    ? lastQuestion.slice(0, 140) + "…"
                    : lastQuestion}
                  ”
                </span>
              </div>
            )}
            <div className="mt-1 text-[11px] text-text-secondary truncate font-mono">
              Error: {runtimeError.message}
              {runtimeError.source && (
                <span className="text-text-tertiary ml-1">
                  · {runtimeError.source.split("/").pop()}:{runtimeError.line}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-2">
              {retry && (
                <button
                  onClick={() => {
                    const reason = runtimeError.message;
                    setRuntimeError(null);
                    retry(reason);
                  }}
                  disabled={retryBusy}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-error text-white text-[11px] font-medium hover:bg-error/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  title="Replace the failed turn with a retry. The agent will see why the prior attempt failed."
                >
                  <RotateCw
                    size={11}
                    className={retryBusy ? "animate-spin" : ""}
                  />
                  {retryBusy ? "Retrying…" : "Retry query"}
                </button>
              )}
              <span className="text-text-tertiary text-[11px]">
                The failed answer will be replaced and the agent will
                see the error so it can try a different approach.
              </span>
            </div>
          </div>
          <button
            onClick={() => setRuntimeError(null)}
            className="text-text-faint hover:text-text-secondary self-start"
            title="Dismiss"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-hidden bg-surface-0">
        <iframe
          srcDoc={codeWithBridge}
          className="w-full h-full border-0 bg-white"
          sandbox="allow-scripts allow-same-origin"
          title={artifact.title}
        />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-1.5 border-t border-border bg-surface-1 text-[10px] text-text-faint font-body shrink-0">
        <span className="font-mono">{artifact.filename}</span>
        {artifact.versions.length > 1 && (
          <span>v{artifact.versions.length}</span>
        )}
      </div>
    </div>
  );
}
