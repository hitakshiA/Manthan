import { useEffect, useState } from "react";
import type { SchemaSummary } from "@/types/api";
import { getSchema } from "@/api/datasets";

/**
 * Load every schema in parallel and return a stable id→schema map.
 * Used by the semantic-layer graph to materialize nodes + derive FK
 * edges without waiting for the per-row useSchema calls. Schemas are
 * cached in a module-level map so revisits are instant.
 */

const cache = new Map<string, SchemaSummary>();
const inFlight = new Map<string, Promise<SchemaSummary | null>>();

async function loadOne(id: string): Promise<SchemaSummary | null> {
  const hit = cache.get(id);
  if (hit) return hit;
  let p = inFlight.get(id);
  if (!p) {
    p = getSchema(id)
      .then((s) => {
        cache.set(id, s);
        inFlight.delete(id);
        return s;
      })
      .catch(() => {
        inFlight.delete(id);
        return null;
      });
    inFlight.set(id, p);
  }
  return p;
}

export function useAllSchemas(ids: string[]): {
  schemas: Map<string, SchemaSummary>;
  loading: boolean;
} {
  const key = ids.join("|");
  const [schemas, setSchemas] = useState<Map<string, SchemaSummary>>(() => {
    const m = new Map<string, SchemaSummary>();
    for (const id of ids) {
      const hit = cache.get(id);
      if (hit) m.set(id, hit);
    }
    return m;
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (ids.length === 0) return;
    let cancelled = false;
    setLoading(true);
    Promise.all(ids.map(loadOne)).then((results) => {
      if (cancelled) return;
      const m = new Map<string, SchemaSummary>();
      results.forEach((s, i) => {
        if (s) m.set(ids[i], s);
      });
      setSchemas(m);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { schemas, loading };
}
