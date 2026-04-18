"""Append-only change log for Data Context Documents.

Every write to ``data/<ds>/manthan-context.yaml`` is paired with a
line in ``data/<ds>/dcd_history.jsonl`` capturing who changed what,
when, and (optionally) why. An auditor who asks "what did 'Revenue'
mean on March 15?" can walk the log to reconstruct the state.

Intentionally simple — no git dependency, no diff library, no
versioned storage. Each entry is a full snapshot of the DCD so
replay is trivial. For high-churn production workloads a real
versioned store (dvc, lakefs, git-backed) is a later-phase swap.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.semantic.schema import DataContextDocument


def log_dcd_change(
    *,
    data_directory: Path,
    dataset_id: str,
    new_dcd: DataContextDocument,
    changed_by: str = "system",
    reason: str = "",
) -> None:
    """Append one change entry to ``data/<ds>/dcd_history.jsonl``.

    Failure to write the history never blocks the DCD update itself —
    the snapshot file is the source of truth, history is metadata.
    """
    try:
        ds_dir = data_directory / dataset_id
        ds_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "changed_by": changed_by,
            "reason": reason,
            "dcd_version": new_dcd.version,
            "entity_slug": (
                new_dcd.dataset.entity.slug
                if new_dcd.dataset.entity is not None
                else None
            ),
            "metric_count": (
                len(new_dcd.dataset.entity.metrics)
                if new_dcd.dataset.entity is not None
                else 0
            ),
            "snapshot": new_dcd.model_dump(mode="json", exclude_none=True),
        }
        log_path = ds_dir / "dcd_history.jsonl"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        # History write failures are non-fatal.
        pass


def read_dcd_history(
    *,
    data_directory: Path,
    dataset_id: str,
    limit: int = 50,
    include_snapshots: bool = False,
) -> list[dict[str, Any]]:
    """Return the most recent entries (newest first).

    ``include_snapshots=False`` omits the full DCD blob from each
    entry — the default, to keep list responses compact. Callers
    that need a specific historical snapshot should request it with
    ``include_snapshots=True`` and slice by timestamp.
    """
    log_path = data_directory / dataset_id / "dcd_history.jsonl"
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not include_snapshots:
            entry.pop("snapshot", None)
        entries.append(entry)
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries[:limit]
