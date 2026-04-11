"""Presidio-backed value-pattern PII detection (SPEC §6 Layer 2).

Runs Microsoft Presidio's ``AnalyzerEngine`` against a sample of the
string values in a column and decides whether the column should be
flagged as PII. Engine construction is expensive (spaCy model load on
cold start) so this module caches a single engine per process.

The analyzer is optional from an installation standpoint in principle —
any ImportError is caught and :func:`detect_value_pii` returns ``None``
so the deterministic Layers 1 and 3 still run normally. This keeps the
data layer resilient if a deployment intentionally strips Presidio out.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.config import get_settings
from src.core.logger import get_logger
from src.profiling.pii_detector import PiiFlag
from src.profiling.statistical import ColumnProfile, is_string_type

_logger = get_logger()

# Presidio entity types mapped to our handling policy. Anything in this
# list is treated as PII with "never expose" handling when detected with
# a confidence above the configured threshold.
_PRESIDIO_ENTITIES_TO_SCAN = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IBAN_CODE",
    "IP_ADDRESS",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "LOCATION",
    "MEDICAL_LICENSE",
    "URL",
)

# Sampled values must hit the PII pattern in at least this fraction of
# non-null cells before we flag the column. Keeps us from flagging a
# column that happens to contain one person's name in an otherwise
# generic notes field.
_MIN_HIT_RATIO = 0.05


class PresidioHit(BaseModel):
    """Aggregated Presidio output for a single column."""

    model_config = ConfigDict(frozen=True)

    entity_type: str
    hit_ratio: float = Field(ge=0.0, le=1.0)
    avg_confidence: float = Field(ge=0.0, le=1.0)


@lru_cache(maxsize=1)
def _engine() -> Any:
    """Return a cached Presidio AnalyzerEngine, or ``None`` if unavailable."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError as exc:
        _logger.warning("presidio.import_failed", error=str(exc))
        return None

    settings = get_settings()
    try:
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [
                    {
                        "lang_code": "en",
                        "model_name": settings.presidio_nlp_model,
                    }
                ],
            }
        )
        nlp_engine = provider.create_engine()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    except Exception as exc:
        _logger.warning("presidio.engine_build_failed", error=str(exc))
        return None


def scan_samples(profile: ColumnProfile) -> PresidioHit | None:
    """Run Presidio against ``profile``'s sample values.

    Returns ``None`` when the column is not string-like, Presidio is
    unavailable, or no PII entity fires above the configured hit ratio.
    Otherwise returns the single highest-signal :class:`PresidioHit`.
    """
    if not is_string_type(profile.dtype):
        return None
    engine = _engine()
    if engine is None:
        return None

    settings = get_settings()
    threshold = settings.pii_confidence_threshold
    samples = [str(value) for value in profile.sample_values if value is not None]
    if not samples:
        return None

    entity_totals: dict[str, list[float]] = {}
    for sample in samples[: settings.pii_sample_size]:
        try:
            results = engine.analyze(
                text=sample,
                language="en",
                entities=list(_PRESIDIO_ENTITIES_TO_SCAN),
            )
        except Exception as exc:
            _logger.warning(
                "presidio.analyze_failed",
                column=profile.name,
                error=str(exc),
            )
            continue
        for result in results:
            if result.score < threshold:
                continue
            entity_totals.setdefault(result.entity_type, []).append(result.score)

    if not entity_totals:
        return None

    best_entity, confidences = max(
        entity_totals.items(),
        key=lambda item: (len(item[1]), sum(item[1]) / max(len(item[1]), 1)),
    )
    hit_ratio = len(confidences) / len(samples)
    if hit_ratio < _MIN_HIT_RATIO:
        return None
    avg_confidence = sum(confidences) / len(confidences)
    return PresidioHit(
        entity_type=best_entity,
        hit_ratio=hit_ratio,
        avg_confidence=avg_confidence,
    )


def detect_value_pii(profile: ColumnProfile) -> PiiFlag | None:
    """Return a :class:`PiiFlag` for ``profile`` if Presidio flags its values."""
    hit = scan_samples(profile)
    if hit is None:
        return None
    return PiiFlag(
        column_name=profile.name,
        sensitivity="pii",
        pii_type=hit.entity_type,
        handling="never_expose_in_outputs",
        reason=(
            f"Presidio detected {hit.entity_type} in "
            f"{hit.hit_ratio * 100:.0f}% of sampled values "
            f"(avg confidence {hit.avg_confidence:.2f})"
        ),
        confidence=max(hit.avg_confidence, hit.hit_ratio),
    )
