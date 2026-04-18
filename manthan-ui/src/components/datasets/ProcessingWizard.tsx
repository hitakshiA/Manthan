import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Check, Sparkles, ShieldCheck, AlertTriangle } from "lucide-react";

import { useProcessingStore } from "@/stores/processing-store";
import { useDatasetStore } from "@/stores/dataset-store";
import { useSessionStore } from "@/stores/session-store";
import { connectPipelineProgress } from "@/api/pipeline-progress";
import { post } from "@/api/client";
import type { PipelineClarificationQuestion } from "@/types/pipeline";
import { cn } from "@/lib/utils";

const STEP_LOTTIE_URLS: Record<string, string> = {
  upload: "https://lottie.host/d6a89817-9e1e-40da-b749-8fea095451f5/kzlEE1po1S.lottie",
  scan: "https://lottie.host/7c650c07-4a82-40f7-82fa-ae435fe2e112/g4uEMaWqzQ.lottie",
  profile: "https://lottie.host/979ce672-da6d-4b0d-919c-7376eb6beadb/IhbY3f67VT.lottie",
  classify: "https://lottie.host/59c2b3a2-f415-450a-b932-0c273428e60c/UfODKaqtiE.lottie",
  enrich: "https://lottie.host/c6d0ea4c-02b7-439e-846a-57c1ffdb80c7/2dmNvVIH61.lottie",
  materialize: "https://lottie.host/6e369976-d2b4-488a-a774-f6e1e08bfb71/OwlKmGYEir.lottie",
};

function DotLottiePlayer({ src }: { src: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Create the web component imperatively so boolean attrs work
    const player = document.createElement("dotlottie-wc") as HTMLElement;
    player.setAttribute("src", src);
    player.setAttribute("autoplay", "");
    player.setAttribute("loop", "");
    player.style.width = "100%";
    player.style.height = "100%";
    player.style.background = "transparent";
    player.style.setProperty("--dotlottie-player-bg", "transparent");
    // Hide the internal canvas background via a style override
    const style = document.createElement("style");
    style.textContent = `dotlottie-wc canvas, dotlottie-wc svg { background: transparent !important; }`;
    el.appendChild(style);
    el.appendChild(player);

    return () => { el.innerHTML = ""; };
  }, [src]);

  return <div ref={containerRef} className="w-full h-full" style={{ mixBlendMode: "multiply" }} />;
}

// Load dotlottie-wc script once
if (typeof window !== "undefined" && !customElements.get("dotlottie-wc")) {
  const script = document.createElement("script");
  script.type = "module";
  script.src = "https://unpkg.com/@lottiefiles/dotlottie-wc@0.9.10/dist/dotlottie-wc.js";
  document.head.appendChild(script);
}

export function ProcessingWizard() {
  const {
    datasetId,
    realDatasetId,
    steps,
    currentStepIndex,
    message,
    clarificationQuestions,
    askUserIds,
    error,
    handleEvent,
    reset,
  } = useProcessingStore();

  const fetchDatasets = useDatasetStore((s) => s.fetchDatasets);
  const setActiveDataset = useSessionStore((s) => s.setActiveDataset);
  const abortRef = useRef<AbortController | null>(null);
  const completedRef = useRef(false);

  // Connect to SSE stream
  useEffect(() => {
    if (!datasetId) return;
    const controller = new AbortController();
    abortRef.current = controller;
    connectPipelineProgress(datasetId, handleEvent, controller.signal).catch(() => {});
    return () => { controller.abort(); abortRef.current = null; };
  }, [datasetId, handleEvent]);

  // Handle completion
  useEffect(() => {
    if (!realDatasetId || completedRef.current) return;
    completedRef.current = true;
    const timer = setTimeout(async () => {
      await fetchDatasets();
      setActiveDataset(realDatasetId);
      reset();
    }, 1500);
    return () => clearTimeout(timer);
  }, [realDatasetId, fetchDatasets, setActiveDataset, reset]);

  const allComplete = steps.every((s) => s.status === "complete");
  const activeStep = currentStepIndex >= 0 ? steps[currentStepIndex] : null;
  const activeKey = activeStep?.key ?? "upload";
  const activeUrl = STEP_LOTTIE_URLS[activeKey];
  const stepCount = steps.length;
  const displayIndex = Math.max(0, currentStepIndex);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="flex h-full items-center justify-center px-6 py-10"
    >
      <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-8">
        {/* Animation */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeKey}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.85 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
            className="h-48 w-48"
          >
            <DotLottiePlayer src={activeUrl} />
          </motion.div>
        </AnimatePresence>

        {/* Title + message */}
        <AnimatePresence mode="wait">
          <motion.div
            key={allComplete ? "done" : activeKey}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.25 }}
            className="text-center"
          >
            <h2 className="font-display text-3xl text-text-primary tracking-tight">
              {allComplete
                ? "Your dataset is governed."
                : activeStep?.title ?? "Starting…"}
            </h2>
            <p className="mt-2 text-sm text-text-tertiary font-body max-w-sm mx-auto">
              {allComplete
                ? "Metrics, rollups, and column labels are wired into the agent."
                : (message || activeStep?.subtitle || "")}
            </p>
          </motion.div>
        </AnimatePresence>

        {/* Step rail — all six stages visible at once so the exec sees
            what the pipeline is actually doing, not a single spinner. */}
        <div className="w-full">
          <div className="grid grid-cols-6 gap-1.5">
            {steps.map((s, i) => {
              const isActive = i === displayIndex && !allComplete;
              const isDone = s.status === "complete" || allComplete;
              const isClarifying = s.status === "clarification";
              return (
                <div key={s.key} className="flex flex-col items-center gap-1.5">
                  <div
                    className={cn(
                      "w-full h-1 rounded-full transition-colors",
                      isDone
                        ? "bg-accent"
                        : isActive
                          ? "bg-accent/60 animate-pulse"
                          : isClarifying
                            ? "bg-warning"
                            : "bg-border",
                    )}
                  />
                  <div
                    className={cn(
                      "flex items-center gap-1 text-[10px] font-body uppercase tracking-wider transition-colors",
                      isDone
                        ? "text-accent"
                        : isActive
                          ? "text-text-primary"
                          : isClarifying
                            ? "text-warning"
                            : "text-text-faint",
                    )}
                  >
                    {isDone ? <Check size={10} /> : null}
                    <span className="truncate">{s.title}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Tagline that reinforces what we're building — semantic layer
            language instead of a generic "processing" message. */}
        {!allComplete && (
          <div className="flex items-center gap-2 text-[11px] text-text-faint font-body">
            <ShieldCheck size={11} className="text-accent" />
            <span>
              Building a governed Layer 1 — every metric will be traceable to a
              declaration, not a prompt guess.
            </span>
          </div>
        )}
        {allComplete && (
          <div className="flex items-center gap-2 text-[11px] text-accent font-body">
            <Sparkles size={11} />
            <span>Opening the dataset…</span>
          </div>
        )}

        {/* Inline clarification */}
        {clarificationQuestions && askUserIds && (
          <ClarificationPanel questions={clarificationQuestions} askUserIds={askUserIds} />
        )}

        {/* Error */}
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-start gap-2 rounded-xl bg-error-soft/40 border border-error/30 px-4 py-3 text-sm text-error font-body max-w-sm"
          >
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}

function ClarificationPanel({
  questions,
  askUserIds,
}: {
  questions: PipelineClarificationQuestion[];
  askUserIds: string[];
}) {
  // Track answers in state (not a ref) so the picked chip visibly
  // highlights and the pending/done indicators actually re-render.
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [pending, setPending] = useState<Record<number, boolean>>({});

  const handleAnswer = useCallback(
    async (qIndex: number, label: string) => {
      if (picked[qIndex] != null) return;
      setPicked((m) => ({ ...m, [qIndex]: label }));
      setPending((m) => ({ ...m, [qIndex]: true }));
      const askUserId = askUserIds[qIndex];
      if (!askUserId) return;
      try {
        await post(`/ask_user/${askUserId}/answer`, { answer: label });
      } catch {
        /* timeout fallback handled on the backend */
      }
      setPending((m) => ({ ...m, [qIndex]: false }));
    },
    [askUserIds, picked],
  );

  const allAnswered =
    questions.length > 0 &&
    questions.every((_, i) => picked[i] != null);
  const anyPending = Object.values(pending).some(Boolean);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="w-full space-y-3 max-w-md">
      <p className="text-center text-sm font-medium text-warning font-body">
        A few columns are ambiguous — confirm their role so the metrics lock in correctly.
      </p>
      {questions.map((q, i) => {
        const chosen = picked[i];
        const isPending = pending[i];
        return (
          <div
            key={q.column_name}
            className="rounded-xl border border-warning/30 bg-warning-soft/20 p-3.5"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-text-primary font-body capitalize">
                {q.column_name.replace(/[_-]+/g, " ")}
              </p>
              {chosen && !isPending && (
                <span className="flex items-center gap-1 text-[11px] text-success font-medium">
                  <Check size={11} /> saved
                </span>
              )}
              {isPending && (
                <span className="text-[11px] text-text-tertiary">saving…</span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-text-tertiary font-body">{q.prompt}</p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {q.options.map((opt) => {
                const isChosen = chosen === opt.label;
                return (
                  <button
                    key={opt.value}
                    onClick={() => handleAnswer(i, opt.label)}
                    disabled={chosen != null}
                    className={cn(
                      "rounded-md border px-2.5 py-1 text-xs font-medium transition-all",
                      isChosen
                        ? "border-accent bg-accent text-accent-text"
                        : chosen != null
                          ? "border-border bg-surface-raised text-text-faint opacity-50 cursor-not-allowed"
                          : "border-border bg-surface-raised text-text-secondary hover:border-accent hover:bg-accent-soft hover:text-accent",
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
      {allAnswered && !anyPending && (
        <p className="text-center text-[11px] text-text-tertiary font-body">
          Moving to the next step…
        </p>
      )}
    </motion.div>
  );
}

