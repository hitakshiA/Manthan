import { create } from "zustand";
import { generateId } from "@/lib/utils";

interface QueryHistoryEntry {
  id: string;
  message: string;
  datasetId: string;
  timestamp: number;
  renderMode: "simple" | "moderate" | "complex" | null;
}

interface SessionState {
  sessionId: string;
  activeDatasetId: string | null;
  queryHistory: QueryHistoryEntry[];
  setActiveDataset: (id: string | null) => void;
  newSession: () => void;
  addQuery: (message: string, datasetId: string) => void;
  setQueryMode: (queryId: string, mode: "simple" | "moderate" | "complex") => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: generateId(),
  activeDatasetId: null,
  queryHistory: [],
  setActiveDataset: (id) => set({ activeDatasetId: id }),
  newSession: () => set({ sessionId: generateId() }),
  addQuery: (message, datasetId) =>
    set((s) => ({
      queryHistory: [
        {
          id: generateId(),
          message,
          datasetId,
          timestamp: Date.now(),
          renderMode: null,
        },
        ...s.queryHistory,
      ],
    })),
  setQueryMode: (queryId, mode) =>
    set((s) => ({
      queryHistory: s.queryHistory.map((q) =>
        q.id === queryId ? { ...q, renderMode: mode } : q,
      ),
    })),
}));
