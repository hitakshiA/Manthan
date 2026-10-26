/**
 * CaseList - focused, status-filtered ledger of cases.
 *
 * Backs /app/active, /app/done, /app/escalated. Renders the same
 * editorial card grid the Inbox uses, so the operator's visual model
 * stays consistent across views - same card shape, same Spectral
 * description line, same hairline + status accent. Previously these
 * pages collapsed to a thin `divide-y` list that read as a CSV dump
 * with no breathing room.
 *
 * Done & Escalated cases are rendered with the `muted` treatment
 * (cards drop to ~75% opacity) to signal "archival, not active."
 * Active stays full-opacity.
 */

import { useEffect, useMemo, useState } from "react";

import {
  EmptyRow,
  ErrorRow,
  LoadingRow,
  PageBody,
  PageHeader,
  Section,
} from "@/components/ui/Page";
import {
  listCases,
  type ApiCase,
  type CaseStatus,
} from "@/lib/api";
import { CaseCardGrid } from "@/components/app/CaseCardGrid";

export interface CaseListProps {
  title: string;
  description: string;
  statuses: CaseStatus[];
  emptyHint?: string;
}

export default function CaseList({
  title,
  description,
  statuses,
  emptyHint,
}: CaseListProps) {
  const [cases, setCases] = useState<ApiCase[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCases(null);
    setError(null);

    Promise.all(
      statuses.map((s) =>
        listCases({ status: s, limit: 100 }).catch(() => ({
          cases: [],
          total: 0,
        })),
      ),
    )
      .then((results) => {
        if (cancelled) return;
        const merged = results
          .flatMap((r) => r.cases)
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          );
        setCases(merged);
      })
      .catch((e) => !cancelled && setError((e as Error).message));

    return () => {
      cancelled = true;
    };
  }, [statuses]);

  // "Done" and "Escalated" feel archival - mute the surface so the
  // operator's eye reads the active band first when they have both in
  // view. "Active" pages stay full opacity.
  const archival = useMemo(
    () =>
      statuses.every(
        (s) => s === "resolved" || s === "escalated" || s === "errored",
      ),
    [statuses],
  );

  const metaLine = cases
    ? `${cases.length} ${cases.length === 1 ? "case" : "cases"} · ${description}`
    : description;

  return (
    <PageBody width="wide">
      <PageHeader eyebrow={title} title={title} meta={metaLine} />

      {error && <ErrorRow>Couldn&apos;t load cases: {error}</ErrorRow>}
      {cases === null && !error && <LoadingRow />}
      {cases !== null && cases.length === 0 && !error && (
        <EmptyRow>{emptyHint ?? "Nothing here yet."}</EmptyRow>
      )}

      {cases && cases.length > 0 && (
        <Section>
          <CaseCardGrid cases={cases} muted={archival} />
        </Section>
      )}
    </PageBody>
  );
}
