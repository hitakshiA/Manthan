"""Tests for src.core.metrics."""

from __future__ import annotations

from src.core import metrics


def test_counters_and_histograms() -> None:
    metrics.reset()
    metrics.increment("test.counter", 3)
    metrics.increment("test.counter", 2)
    metrics.observe("test.latency_ms", 10.0)
    metrics.observe("test.latency_ms", 20.0)
    metrics.observe("test.latency_ms", 30.0)

    snapshot = metrics.snapshot()
    assert snapshot["counters"]["test.counter"] == 5
    histogram = snapshot["histograms"]["test.latency_ms"]
    assert histogram["count"] == 3
    assert histogram["avg"] == 20.0
    assert histogram["min"] == 10.0
    assert histogram["max"] == 30.0


def test_reset() -> None:
    metrics.increment("x", 1)
    metrics.reset()
    snapshot = metrics.snapshot()
    assert snapshot["counters"] == {}
    assert snapshot["histograms"] == {}
