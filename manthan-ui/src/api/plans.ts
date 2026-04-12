import type { Plan } from "@/types/api";
import { get, post } from "./client";

export const approvePlan = (planId: string, feedback?: string) =>
  post<Plan>(`/plans/${planId}/approve`, { feedback });

export const rejectPlan = (planId: string, feedback?: string) =>
  post<Plan>(`/plans/${planId}/reject`, { feedback });

export const getPlan = (planId: string) =>
  get<Plan>(`/plans/${planId}`);

export const getPlanAudit = (planId: string) =>
  get<{ plan_id: string; events: unknown[] }>(`/plans/${planId}/audit`);
