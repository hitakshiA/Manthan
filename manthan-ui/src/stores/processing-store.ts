import { create } from "zustand";
import type {
  PipelineClarificationQuestion,
  PipelineEvent,
  WizardStep,
  WizardStepKey,
} from "@/types/pipeline";
import { WIZARD_STEPS } from "@/types/pipeline";

/** Minimum time (ms) each step must be visible before advancing */
const MIN_STEP_MS = 2200;

interface ProcessingState {
  active: boolean;
  datasetId: string | null;
  realDatasetId: string | null;
  steps: WizardStep[];
  currentStepIndex: number;
  message: string;
  clarificationQuestions: PipelineClarificationQuestion[] | null;
  askUserIds: string[] | null;
  clarificationSessionId: string | null;
  error: string | null;

  startProcessing: (datasetId: string) => void;
  handleEvent: (event: PipelineEvent) => void;
  reset: () => void;
}

const STEP_KEYS: WizardStepKey[] = [
  "upload", "scan", "profile", "classify", "enrich", "materialize",
];

// Event queue + scheduling state (module-level, not in Zustand)
let queue: PipelineEvent[] = [];
let processing = false;
let timer: ReturnType<typeof setTimeout> | null = null;

// Reference to store API set during creation
let storeSet: (s: Partial<ProcessingState>) => void;
let storeGet: () => ProcessingState;

function clearSchedule() {
  queue = [];
  processing = false;
  if (timer) { clearTimeout(timer); timer = null; }
}

function applyNow(event: PipelineEvent) {
  const state = storeGet();

  switch (event.type) {
    case "progress": {
      const stepIndex = STEP_KEYS.indexOf(event.step);
      if (stepIndex === -1 || stepIndex <= state.currentStepIndex) return;

      const newSteps = state.steps.map((s, i) => {
        if (i < stepIndex) return { ...s, status: "complete" as const };
        if (i === stepIndex) return { ...s, status: "active" as const };
        return { ...s, status: "pending" as const };
      });

      storeSet({
        steps: newSteps,
        currentStepIndex: stepIndex,
        message: event.message,
        ...(stepIndex > STEP_KEYS.indexOf("classify")
          ? { clarificationQuestions: null, askUserIds: null, clarificationSessionId: null }
          : {}),
      });
      break;
    }
    case "clarification": {
      const ci = STEP_KEYS.indexOf("classify");
      const newSteps = state.steps.map((s, i) => {
        if (i < ci) return { ...s, status: "complete" as const };
        if (i === ci) return { ...s, status: "clarification" as const };
        return { ...s, status: "pending" as const };
      });
      storeSet({
        steps: newSteps,
        currentStepIndex: ci,
        message: `${event.questions.length} column(s) need your input`,
        clarificationQuestions: event.questions,
        askUserIds: event.ask_user_ids,
        clarificationSessionId: event.session_id,
      });
      break;
    }
    case "complete": {
      const newSteps = state.steps.map((s) => ({ ...s, status: "complete" as const }));
      storeSet({
        steps: newSteps,
        currentStepIndex: STEP_KEYS.length - 1,
        message: "Done!",
        realDatasetId: event.dataset_id,
      });
      break;
    }
    case "error": {
      const idx = state.currentStepIndex;
      const newSteps = state.steps.map((s, i) => {
        if (i < idx) return { ...s, status: "complete" as const };
        if (i === idx) return { ...s, status: "error" as const };
        return { ...s, status: "pending" as const };
      });
      storeSet({ steps: newSteps, message: event.message, error: event.message });
      break;
    }
  }
}

function processNext() {
  if (queue.length === 0) { processing = false; return; }

  processing = true;
  const next = queue.shift()!;
  applyNow(next);

  // If there are more events, wait MIN_STEP_MS before processing the next
  if (queue.length > 0) {
    timer = setTimeout(() => { timer = null; processNext(); }, MIN_STEP_MS);
  } else {
    processing = false;
  }
}

function enqueueEvent(event: PipelineEvent) {
  // Terminal events: flush all queued steps with MIN_STEP_MS delays, then apply terminal
  if (event.type === "complete" || event.type === "error") {
    queue.push(event);
    if (!processing) processNext();
    return;
  }

  if (!processing && queue.length === 0) {
    // Nothing pending — apply immediately and start the min-timer
    processing = true;
    applyNow(event);
    // Hold for MIN_STEP_MS before allowing next
    timer = setTimeout(() => {
      timer = null;
      processing = false;
      processNext(); // flush any queued events
    }, MIN_STEP_MS);
  } else {
    // Currently displaying a step — queue this one
    queue.push(event);
  }
}

export const useProcessingStore = create<ProcessingState>((set, get) => {
  storeSet = set;
  storeGet = get;

  return {
    active: false,
    datasetId: null,
    realDatasetId: null,
    steps: WIZARD_STEPS.map((s) => ({ ...s })),
    currentStepIndex: -1,
    message: "",
    clarificationQuestions: null,
    askUserIds: null,
    clarificationSessionId: null,
    error: null,

    startProcessing: (datasetId) => {
      clearSchedule();
      set({
        active: true,
        datasetId,
        realDatasetId: null,
        steps: WIZARD_STEPS.map((s) => ({ ...s, status: "pending" })),
        currentStepIndex: -1,
        message: "Starting pipeline...",
        clarificationQuestions: null,
        askUserIds: null,
        clarificationSessionId: null,
        error: null,
      });
    },

    handleEvent: (event) => enqueueEvent(event),

    reset: () => {
      clearSchedule();
      set({
        active: false,
        datasetId: null,
        realDatasetId: null,
        steps: WIZARD_STEPS.map((s) => ({ ...s })),
        currentStepIndex: -1,
        message: "",
        clarificationQuestions: null,
        askUserIds: null,
        clarificationSessionId: null,
        error: null,
      });
    },
  };
});
