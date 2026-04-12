import type { QuestionResponse } from "@/types/api";
import { get, post } from "./client";

export const answerQuestion = (questionId: string, answer: string) =>
  post<QuestionResponse>(`/ask_user/${questionId}/answer`, { answer });

export const getPendingQuestions = (sessionId: string) =>
  get<QuestionResponse[]>(`/ask_user/pending?session_id=${sessionId}`);

export const getQuestion = (questionId: string) =>
  get<QuestionResponse>(`/ask_user/${questionId}`);
