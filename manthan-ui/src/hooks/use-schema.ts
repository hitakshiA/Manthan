import { useCallback, useEffect, useState } from "react";
import type { SchemaSummary } from "@/types/api";
import { getSchema } from "@/api/datasets";

const cache = new Map<string, SchemaSummary>();
const failed = new Set<string>();

export function useSchema(datasetId: string | null) {
  const [schema, setSchema] = useState<SchemaSummary | null>(
    datasetId ? cache.get(datasetId) ?? null : null,
  );
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!datasetId) {
      setSchema(null);
      return;
    }
    if (cache.has(datasetId)) {
      setSchema(cache.get(datasetId)!);
      return;
    }
    if (failed.has(datasetId)) return; // Don't retry failed fetches

    setLoading(true);
    getSchema(datasetId)
      .then((s) => {
        cache.set(datasetId, s);
        setSchema(s);
      })
      .catch(() => {
        failed.add(datasetId);
      })
      .finally(() => setLoading(false));
  }, [datasetId]);

  // Invalidate + reload — used after /refresh so the entity stats, metrics,
  // and column list reflect the new underlying parquet.
  const refetch = useCallback(async () => {
    if (!datasetId) return;
    cache.delete(datasetId);
    failed.delete(datasetId);
    setLoading(true);
    try {
      const s = await getSchema(datasetId);
      cache.set(datasetId, s);
      setSchema(s);
    } catch {
      failed.add(datasetId);
    } finally {
      setLoading(false);
    }
  }, [datasetId]);

  return { schema, loading, refetch };
}

export function prefetchSchemas(ids: string[]) {
  for (const id of ids) {
    if (!cache.has(id) && !failed.has(id)) {
      getSchema(id)
        .then((s) => cache.set(id, s))
        .catch(() => failed.add(id));
    }
  }
}
