"""PII detection pipeline — column-name and statistical heuristics.

Per SPEC §6 the full pipeline has three layers:

1. **Column-name heuristics** — fast regex matches on the column name
   itself against known PII labels (name, email, phone, SSN, address...).
2. **Value-pattern detection (Presidio)** — slower content scan. Deferred
   to a later phase so we don't take on the spaCy + Presidio install in
   this commit.
3. **Statistical heuristics** — high-cardinality string columns that look
   like identifiers, UUID-shaped values, fixed-width numeric identifiers.

This module implements Layers 1 and 3 only. Every flagged column receives
a sensitivity classification, a suggested handling strategy, and a human-
readable reason so that downstream agents can explain their caveats to
users.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.profiling.statistical import ColumnProfile, is_string_type

Sensitivity = Literal["public", "quasi_identifier", "pii"]
Handling = Literal[
    "expose",
    "mask_in_outputs",
    "aggregate_only",
    "never_expose_in_outputs",
]

# Heuristic confidence scores. Column-name matches are high-confidence;
# statistical patterns are more tentative and invite user confirmation.
_NAME_MATCH_CONFIDENCE = 0.85
_UUID_PATTERN_CONFIDENCE = 0.95
_HIGH_CARDINALITY_CONFIDENCE = 0.6
_NO_MATCH_CONFIDENCE = 0.5

# A column must have at least this many distinct values before we flag it
# as a high-cardinality quasi-identifier; below this the "approaches row
# count" signal is too noisy on tiny tables.
_HIGH_CARDINALITY_MIN_DISTINCT = 100
_HIGH_CARDINALITY_RATIO_THRESHOLD = 0.9


class PiiFlag(BaseModel):
    """Result of running the PII pipeline against one column."""

    model_config = ConfigDict(frozen=True)

    column_name: str
    sensitivity: Sensitivity
    pii_type: str | None = None
    handling: Handling
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


# --- Layer 1: column-name patterns ---------------------------------------
# Mapping from PII entity type to a case-insensitive regex matched against
# the column name. Patterns are conservative: they match common prefixes
# and exact words but try to avoid obvious false positives (e.g. "region"
# does not match "name" just because both end in "n").
_NAME_PATTERNS: dict[str, re.Pattern[str]] = {
    "PERSON": re.compile(
        r"(?i)(^|_)(first|last|full|customer|user|employee|person)?[_ ]?name($|_)"
    ),
    "EMAIL_ADDRESS": re.compile(r"(?i)(^|_)e?[_ ]?mail([_ ]?address)?($|_)"),
    "PHONE_NUMBER": re.compile(
        r"(?i)(^|_)(phone|mobile|telephone|tel|cell|fax)([_ ]?number)?($|_)"
    ),
    "US_SSN": re.compile(r"(?i)(^|_)(ssn|social[_ ]?security)($|_)"),
    "CREDIT_CARD": re.compile(r"(?i)(^|_)(credit[_ ]?card|card[_ ]?number|ccn)($|_)"),
    "AADHAAR": re.compile(r"(?i)(^|_)(aadhaar|aadhar)([_ ]?number)?($|_)"),
    "PAN_CARD": re.compile(r"(?i)(^|_)pan[_ ]?(card|number)?($|_)"),
    "PASSPORT": re.compile(r"(?i)(^|_)passport([_ ]?number)?($|_)"),
    "DRIVING_LICENSE": re.compile(r"(?i)(^|_)driv(er|ing)[_ ]?licen[sc]e($|_)"),
    "BANK_ACCOUNT": re.compile(
        r"(?i)(^|_)(account[_ ]?no(umber)?|iban|routing([_ ]?number)?|swift)($|_)"
    ),
    "LOCATION_ADDRESS": re.compile(
        r"(?i)(^|_)(address|street|zip([_ ]?code)?|postal[_ ]?code)($|_)"
    ),
}

# --- Layer 3: value patterns ---------------------------------------------
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Numeric PII heuristic: strings of digits of fixed, "typical" lengths —
# 10 digits for US / India phone numbers, 12 for Aadhaar, 16 for credit
# cards. We only fire this heuristic for string columns where samples
# are uniform-length digit runs.
_PII_NUMERIC_LENGTHS: dict[int, str] = {
    10: "PHONE_NUMBER",
    12: "AADHAAR",
    16: "CREDIT_CARD",
}
_NUMERIC_PII_MIN_HIT_RATIO = 0.8


def classify_by_column_name(column_name: str) -> PiiFlag | None:
    """Run Layer 1 against ``column_name``.

    Returns:
        A :class:`PiiFlag` if the name matches a known pattern; ``None``
        otherwise so that callers can fall through to Layer 3.
    """
    for pii_type, pattern in _NAME_PATTERNS.items():
        if pattern.search(column_name):
            return PiiFlag(
                column_name=column_name,
                sensitivity="pii",
                pii_type=pii_type,
                handling="never_expose_in_outputs",
                reason=f"Column name matches {pii_type} pattern",
                confidence=_NAME_MATCH_CONFIDENCE,
            )
    return None


def detect_statistical_pii(profile: ColumnProfile) -> PiiFlag | None:
    """Run Layer 3 statistical heuristics against ``profile``.

    Checks for:

    * UUID-shaped sample values → quasi-identifier
    * High-cardinality string columns that approach the row count →
      quasi-identifier (likely a natural id)

    Returns:
        A :class:`PiiFlag` if any heuristic fires; ``None`` otherwise.
    """
    string_samples = [v for v in profile.sample_values if isinstance(v, str)]
    if string_samples and all(_UUID_PATTERN.match(v) for v in string_samples):
        return PiiFlag(
            column_name=profile.name,
            sensitivity="quasi_identifier",
            pii_type="UUID",
            handling="aggregate_only",
            reason="All sampled values match the UUID/GUID pattern",
            confidence=_UUID_PATTERN_CONFIDENCE,
        )

    if (
        is_string_type(profile.dtype)
        and profile.cardinality_ratio >= _HIGH_CARDINALITY_RATIO_THRESHOLD
        and profile.distinct_count >= _HIGH_CARDINALITY_MIN_DISTINCT
    ):
        return PiiFlag(
            column_name=profile.name,
            sensitivity="quasi_identifier",
            pii_type=None,
            handling="aggregate_only",
            reason=(
                f"High cardinality ratio {profile.cardinality_ratio:.2f} "
                f"over {profile.distinct_count} distinct values — "
                "likely a natural identifier"
            ),
            confidence=_HIGH_CARDINALITY_CONFIDENCE,
        )

    numeric_flag = _detect_fixed_width_numeric_pii(profile)
    if numeric_flag is not None:
        return numeric_flag

    return None


def _detect_fixed_width_numeric_pii(profile: ColumnProfile) -> PiiFlag | None:
    """Flag string columns whose samples are uniform-length digit runs."""
    if not is_string_type(profile.dtype):
        return None
    string_samples = [v for v in profile.sample_values if isinstance(v, str)]
    if len(string_samples) < 5:
        return None
    digit_samples = [s for s in string_samples if s.isdigit()]
    if len(digit_samples) / len(string_samples) < _NUMERIC_PII_MIN_HIT_RATIO:
        return None
    lengths = {len(s) for s in digit_samples}
    if len(lengths) != 1:
        return None
    width = lengths.pop()
    entity = _PII_NUMERIC_LENGTHS.get(width)
    if entity is None:
        return None
    return PiiFlag(
        column_name=profile.name,
        sensitivity="pii",
        pii_type=entity,
        handling="never_expose_in_outputs",
        reason=(
            f"All sampled values are {width}-digit numeric strings — "
            f"matches the {entity} shape"
        ),
        confidence=0.75,
    )


def classify_column(
    profile: ColumnProfile,
    *,
    enable_presidio: bool = True,
) -> PiiFlag:
    """Run Layers 1 → 2 → 3 and return a composite classification.

    Layer 1 (column-name heuristics) takes precedence because it is the
    highest-signal, lowest-cost check. If Layer 1 does not fire, Layer 2
    (Presidio value-pattern scanning) runs when ``enable_presidio`` is
    true and the module is available. Finally Layer 3 (statistical
    heuristics) picks up quasi-identifiers and fixed-width numeric
    identifiers. If no layer fires, the column is marked ``public`` with
    a low confidence so downstream agents can still surface the decision
    explicitly.
    """
    by_name = classify_by_column_name(profile.name)
    if by_name is not None:
        return by_name

    if enable_presidio:
        # Import lazily so projects that do not install Presidio can still
        # use the deterministic layers. If Presidio isn't available the
        # module's detect_value_pii returns None.
        try:
            from src.profiling.presidio_layer import detect_value_pii

            by_value = detect_value_pii(profile)
            if by_value is not None:
                return by_value
        except ImportError:
            pass

    by_stats = detect_statistical_pii(profile)
    if by_stats is not None:
        return by_stats

    return PiiFlag(
        column_name=profile.name,
        sensitivity="public",
        pii_type=None,
        handling="expose",
        reason="No PII indicators detected",
        confidence=_NO_MATCH_CONFIDENCE,
    )
