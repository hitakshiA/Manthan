import { create } from "zustand";
import type { DatasetSummary, ClarificationQuestion } from "@/types/api";
import * as datasetsApi from "@/api/datasets";

interface DatasetState {
  datasets: DatasetSummary[];
  loading: boolean;
  uploading: boolean;
  pendingClarifications: Map<string, ClarificationQuestion[]>;
  fetchDatasets: () => Promise<void>;
  uploadDataset: (file: File) => Promise<DatasetSummary>;
  removeDataset: (id: string) => Promise<void>;
}

export const useDatasetStore = create<DatasetState>((set, get) => ({
  datasets: [],
  loading: false,
  uploading: false,
  pendingClarifications: new Map(),

  fetchDatasets: async () => {
    set({ loading: true });
    try {
      const datasets = await datasetsApi.listDatasets();
      set({ datasets, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  uploadDataset: async (file: File) => {
    set({ uploading: true });
    try {
      const dataset = await datasetsApi.uploadDataset(file);
      await get().fetchDatasets();
      set({ uploading: false });
      return dataset;
    } catch (e) {
      set({ uploading: false });
      throw e;
    }
  },

  removeDataset: async (id: string) => {
    await datasetsApi.deleteDataset(id);
    set((s) => ({ datasets: s.datasets.filter((d) => d.dataset_id !== id) }));
  },
}));
