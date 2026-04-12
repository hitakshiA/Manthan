import type { ClarificationQuestion } from "@/types/api";
import { get, post } from "./client";

export const getPendingClarifications = (datasetId: string) =>
  get<ClarificationQuestion[]>(`/clarification/${datasetId}`);

export const submitClarifications = (
  datasetId: string,
  answers: Array<{ question_id: string; column_name: string; chosen_role: string; aggregation?: string }>,
) => post<{ dataset_id: string; answers_received: number }>(`/clarification/${datasetId}`, { answers });
