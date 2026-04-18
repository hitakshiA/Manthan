import { useState, useRef, useCallback, useEffect } from "react";
import { ArrowUp, Loader2, Mic } from "lucide-react";
import { useAgentStore } from "@/stores/agent-store";
import { useSessionStore } from "@/stores/session-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { useUIStore } from "@/stores/ui-store";
import { queryStream } from "@/api/agent";
import { cn } from "@/lib/utils";

interface Props {
  variant?: "hero" | "compact";
}

// Browser-native speech recognition (Chrome, Edge, Safari 14.1+)
const SpeechRecognitionAPI =
  typeof window !== "undefined"
    ? (window as unknown as { SpeechRecognition?: new () => SpeechRecognition; webkitSpeechRecognition?: new () => SpeechRecognition })
        .SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognition })
        .webkitSpeechRecognition
    : undefined;

export function QueryInput({ variant = "compact" }: Props) {
  const [value, setValue] = useState("");
  const [listening, setListening] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recogRef = useRef<SpeechRecognition | null>(null);
  const phase = useAgentStore((s) => s.phase);
  const pushEvent = useAgentStore((s) => s.pushEvent);
  const reset = useAgentStore((s) => s.reset);
  const blocks = useAgentStore((s) => s.blocks);
  const setArtifactOpen = useUIStore((s) => s.setArtifactOpen);
  const setExpandedVisual = useUIStore((s) => s.setExpandedVisual);
  const { sessionId, activeDatasetId, addQuery } = useSessionStore();
  const datasets = useDatasetStore((s) => s.datasets);
  const activeDs = datasets.find((d) => d.dataset_id === activeDatasetId);

  const busy = phase !== "idle" && phase !== "done" && phase !== "error";
  const isHero = variant === "hero";
  const hasValue = value.trim().length > 0;

  // Auto-focus hero input
  useEffect(() => {
    if (activeDatasetId && !busy && isHero) inputRef.current?.focus();
  }, [activeDatasetId, busy, isHero]);

  // Cmd+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Cleanup recognition on unmount
  useEffect(() => {
    return () => { recogRef.current?.abort(); };
  }, []);

  const addUserMessage = useAgentStore((s) => s.addUserMessage);

  const send = useCallback(async () => {
    const msg = value.trim();
    if (!msg || !activeDatasetId || busy) return;
    // Only reset from the hero (first-open) input; follow-ups should keep
    // the prior conversation visible (and the backend threads the Q&A
    // history via session_history).
    if (isHero && blocks.length === 0) reset();
    // Close any open side-panel view (artifact from the prior turn or an
    // expanded inline visual) so the exec's attention lands on the new
    // work that's about to stream in. If the new turn produces another
    // artifact, it re-opens automatically.
    setArtifactOpen(false);
    setExpandedVisual(null);
    addQuery(msg, activeDatasetId);
    addUserMessage(msg);
    setValue("");
    try {
      await queryStream(sessionId, activeDatasetId, msg, pushEvent);
    } catch (e) {
      pushEvent({ type: "error", message: e instanceof Error ? e.message : "Connection failed", recoverable: false });
    }
  }, [value, activeDatasetId, busy, sessionId, pushEvent, reset, addQuery, addUserMessage, isHero, blocks.length, setArtifactOpen, setExpandedVisual]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const toggleVoice = useCallback(() => {
    if (!SpeechRecognitionAPI) return;

    if (listening) {
      recogRef.current?.stop();
      setListening(false);
      return;
    }

    const recog = new SpeechRecognitionAPI();
    recog.lang = "en-US";
    recog.interimResults = true;
    recog.continuous = false;

    recog.onresult = (e: SpeechRecognitionEvent) => {
      let transcript = "";
      for (let i = 0; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      setValue((prev) => {
        // Replace from the start of this recognition session
        const base = prev.trimEnd();
        return base ? `${base} ${transcript}` : transcript;
      });
    };

    recog.onend = () => setListening(false);
    recog.onerror = () => setListening(false);

    recogRef.current = recog;
    recog.start();
    setListening(true);
  }, [listening]);

  const hasMic = !!SpeechRecognitionAPI;

  // ── Compact variant (follow-up input at bottom of conversation) ──
  if (!isHero) {
    return (
      <div
        className={cn(
          "max-w-2xl mx-auto w-full rounded-2xl bg-surface-raised border border-border transition-all duration-150",
          "shadow-sm focus-within:shadow-md focus-within:border-border-strong",
          listening && "ring-2 ring-error/30",
          busy && "opacity-70",
        )}
      >
        <div className="px-4 pt-3.5 pb-2">
          <textarea
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={listening ? "Listening..." : "Ask a follow-up about your data..."}
            aria-label="Follow-up query"
            disabled={!activeDatasetId || busy}
            rows={1}
            className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-faint resize-none outline-none leading-relaxed min-h-[22px] max-h-[160px] font-body"
            style={{ fieldSizing: "content" } as React.CSSProperties}
          />
        </div>
        <div className="flex items-center justify-between px-3 pb-2.5">
          <span className="text-[11px] text-text-faint font-body pl-1">
            {activeDs?.name ?? ""}
          </span>
          <div className="flex items-center gap-1.5">
            {hasMic && (
              <button
                onClick={toggleVoice}
                aria-label={listening ? "Stop listening" : "Voice input"}
                className={cn(
                  "shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-all",
                  listening
                    ? "bg-error text-white animate-pulse"
                    : "text-text-faint hover:text-text-secondary hover:bg-surface-sunken",
                )}
              >
                <Mic size={14} />
              </button>
            )}
            <button
              onClick={send}
              disabled={!hasValue || !activeDatasetId || busy}
              aria-label={busy ? "Analysis in progress" : "Send follow-up"}
              className={cn(
                "shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-all",
                hasValue && activeDatasetId && !busy
                  ? "bg-text-primary text-surface-0 hover:bg-text-secondary active:scale-90"
                  : "bg-surface-sunken text-text-faint",
              )}
            >
              {busy ? <Loader2 size={14} className="animate-spin-slow" /> : <ArrowUp size={14} strokeWidth={2.5} />}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Hero variant ──
  return (
    <div
      className={cn(
        "rounded-2xl bg-surface-raised border border-border transition-all duration-200",
        "shadow-lg focus-within:shadow-xl focus-within:border-border-strong",
        listening && "ring-2 ring-error/30",
        busy && "opacity-60",
      )}
    >
      <div className="px-5 pt-5 pb-3">
        <textarea
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={listening ? "Listening..." : "Ask a question about your data..."}
          aria-label="Query input"
          disabled={!activeDatasetId || busy}
          rows={1}
          className="w-full bg-transparent text-base text-text-primary placeholder:text-text-faint resize-none outline-none leading-relaxed min-h-[28px] max-h-[160px] font-body"
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
      </div>

      <div className="flex items-center justify-between px-4 pb-3">
        <div className="flex items-center gap-2">
          {activeDs && (
            <span className="text-xs text-text-faint font-body">{activeDs.name}</span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {/* Mic button */}
          {hasMic && (
            <button
              onClick={toggleVoice}
              aria-label={listening ? "Stop listening" : "Voice input"}
              className={cn(
                "shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-150",
                listening
                  ? "bg-error text-white animate-pulse"
                  : "text-text-faint hover:text-text-secondary hover:bg-surface-sunken",
              )}
            >
              <Mic size={16} />
            </button>
          )}

          {/* Send button */}
          <button
            onClick={send}
            disabled={!hasValue || !activeDatasetId || busy}
            aria-label={busy ? "Analysis in progress" : "Send query"}
            className={cn(
              "shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-150",
              hasValue && activeDatasetId && !busy
                ? "bg-text-primary text-surface-0 hover:bg-text-secondary active:scale-90"
                : "bg-surface-sunken text-text-faint",
            )}
          >
            {busy ? <Loader2 size={16} className="animate-spin-slow" /> : <ArrowUp size={16} strokeWidth={2.5} />}
          </button>
        </div>
      </div>
    </div>
  );
}
