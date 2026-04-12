import { useEffect, useState } from "react";
import type { SchemaSummary } from "@/types/api";
import { getSchema } from "@/api/datasets";

const cache = new Map<string, SchemaSummary>();

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
    setLoading(true);
    getSchema(datasetId)
      .then((s) => {
        cache.set(datasetId, s);
        setSchema(s);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [datasetId]);

  return { schema, loading };
}

/** Pre-fetch schemas for a list of dataset IDs */
export function prefetchSchemas(ids: string[]) {
  for (const id of ids) {
    if (!cache.has(id)) {
      getSchema(id)
        .then((s) => cache.set(id, s))
        .catch(() => {});
    }
  }
}
