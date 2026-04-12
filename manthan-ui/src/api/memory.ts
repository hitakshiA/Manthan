import type { MemoryEntry } from "@/types/api";
import { get, post, del } from "./client";

export const putMemory = (body: {
  scope_type: string;
  scope_id: string;
  key: string;
  value: unknown;
  category?: string;
  description?: string;
}) => post<MemoryEntry>("/memory", body);

export const getMemory = (scopeType: string, scopeId: string, key: string) =>
  get<MemoryEntry>(`/memory/${scopeType}/${scopeId}/${key}`);

export const listMemory = (scopeType: string, scopeId: string, category?: string) => {
  const q = category ? `?category=${category}` : "";
  return get<MemoryEntry[]>(`/memory/${scopeType}/${scopeId}${q}`);
};

export const searchMemory = (query: string, scopeType?: string) => {
  const params = new URLSearchParams({ query });
  if (scopeType) params.set("scope_type", scopeType);
  return get<MemoryEntry[]>(`/memory/search/?${params}`);
};

export const deleteMemory = (scopeType: string, scopeId: string, key: string) =>
  del<{ removed: boolean }>(`/memory/${scopeType}/${scopeId}/${key}`);
