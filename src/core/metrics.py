"""In-process metrics collection.

Tracks the metrics listed in SPEC §12.1: ingestion counts, profiling
LLM + token usage, materialization file sizes, tool execution latency,
and data-quality scores. The collector is a thread-safe singleton keyed
by metric name; values are served through ``GET /metrics``.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class _MetricsStore:
    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    histograms: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    lock: threading.Lock = field(default_factory=threading.Lock)


@lru_cache(maxsize=1)
def _store() -> _MetricsStore:
    return _MetricsStore()


def increment(name: str, amount: float = 1.0) -> None:
    """Add ``amount`` to the counter ``name``."""
    store = _store()
    with store.lock:
        store.counters[name] += amount


def observe(name: str, value: float) -> None:
    """Record an observation in the histogram ``name``."""
    store = _store()
    with store.lock:
        store.histograms[name].append(value)


def snapshot() -> dict[str, object]:
    """Return a serializable snapshot of all current metrics."""
    store = _store()
    with store.lock:
        counters = dict(store.counters)
        histograms_summary = {
            name: _summarize(values) for name, values in store.histograms.items()
        }
    return {"counters": counters, "histograms": histograms_summary}


def reset() -> None:
    """Clear all metrics (used in tests)."""
    store = _store()
    with store.lock:
        store.counters.clear()
        store.histograms.clear()


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": float(len(values)),
        "sum": float(sum(values)),
        "avg": float(sum(values) / len(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }
