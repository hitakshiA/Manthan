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

export const uploadDatasetAsync = (file: File) =>
  upload<{ dataset_id: string; status: string }>("/datasets/upload-async", file);

export const uploadMultiDataset = (files: File[], opts: { primary?: string } = {}) =>
  uploadMulti<DatasetSummary>("/datasets/upload-multi", files, opts);

/** Phase 4 — re-ingest an existing dataset in place.
 *  Preserves the entity slug, metrics, column labels/synonyms/pii. */
export const refreshDataset = (slugOrId: string, file: File) =>
  upload<DatasetSummary>(`/datasets/${slugOrId}/refresh`, file);

/** Phase 3 — append-only DCD change log. */
export const getDatasetHistory = (id: string, opts: { limit?: number; includeSnapshots?: boolean } = {}) => {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.includeSnapshots) params.set("include_snapshots", "true");
  const q = params.toString() ? `?${params.toString()}` : "";
  return get<Array<{
    timestamp: string;
    changed_by: string;
    reason: string;
    dcd_version: string;
    entity_slug: string | null;
    metric_count: number;
  }>>(`/datasets/${id}/history${q}`);
};

export const fetchOutputFile = async (datasetId: string, filename: string): Promise<string> => {
  const res = await fetch(`${BASE_URL}/datasets/${datasetId}/output/${filename}`);
  if (!res.ok) throw new Error(`Artifact not found: ${filename}`);
  return res.text();
};
