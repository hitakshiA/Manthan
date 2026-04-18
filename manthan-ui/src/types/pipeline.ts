/** Pipeline processing wizard types */

export type WizardStepKey =
  | "upload"
  | "scan"
  | "profile"
  | "classify"
  | "enrich"
  | "materialize";

export type WizardStepStatus =
  | "pending"
  | "active"
  | "complete"
  | "error"
  | "clarification";

export interface WizardStep {
  key: WizardStepKey;
  title: string;
  subtitle: string;
  status: WizardStepStatus;
}

export interface PipelineProgressEvent {
  type: "progress";
  step: WizardStepKey;
  message: string;
  step_index: number;
  total_steps: number;
}

export interface ClarificationOption {
  label: string;
  value: string;
  aggregation: string | null;
}

export interface PipelineClarificationQuestion {
  column_name: string;
  prompt: string;
  current_role: string;
  recommended: string | null;
  options: ClarificationOption[];
}

export interface PipelineClarificationEvent {
  type: "clarification";
  questions: PipelineClarificationQuestion[];
  ask_user_ids: string[];
  session_id: string;
}

export interface PipelineCompleteEvent {
  type: "complete";
  dataset_id: string;
}

export interface PipelineErrorEvent {
  type: "error";
  message: string;
}

export type PipelineEvent =
  | PipelineProgressEvent
  | PipelineClarificationEvent
  | PipelineCompleteEvent
  | PipelineErrorEvent;

export const WIZARD_STEPS: WizardStep[] = [
  { key: "upload", title: "Upload", subtitle: "Reading the file", status: "pending" },
  { key: "scan", title: "Scan", subtitle: "Detecting columns and relationships", status: "pending" },
  { key: "profile", title: "Profile", subtitle: "Computing statistics per column", status: "pending" },
  { key: "classify", title: "Classify", subtitle: "Proposing governed metrics", status: "pending" },
  { key: "enrich", title: "Enrich", subtitle: "Writing the business contract", status: "pending" },
  { key: "materialize", title: "Materialize", subtitle: "Pre-building rollups the agent will query", status: "pending" },
];
