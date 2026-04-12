import type { DatasetSummary, SchemaSummary } from "@/types/api";
import { get, del, upload, uploadMulti, BASE_URL } from "./client";

export const listDatasets = () => get<DatasetSummary[]>("/datasets");

export const getDataset = (id: string) => get<DatasetSummary>(`/datasets/${id}`);

export const deleteDataset = (id: string) => del<{ dataset_id: string; status: string }>(`/datasets/${id}`);

export const getSchema = (id: string) => get<SchemaSummary>(`/datasets/${id}/schema`);

export const getContext = (id: string, query?: string) => {
  const q = query ? `?query=${encodeURIComponent(query)}` : "";
  return get<{ dataset_id: string; yaml: string }>(`/datasets/${id}/context${q}`);
};

export const uploadDataset = (file: File) => upload<DatasetSummary>("/datasets/upload", file);

export const uploadMultiDataset = (files: File[]) => uploadMulti<DatasetSummary>("/datasets/upload-multi", files);

export const fetchOutputFile = async (datasetId: string, filename: string): Promise<string> => {
  const res = await fetch(`${BASE_URL}/datasets/${datasetId}/output/${filename}`);
  if (!res.ok) throw new Error(`Artifact not found: ${filename}`);
  return res.text();
};
