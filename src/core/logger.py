"""Structured JSON logging for the Manthan data layer.

Wraps ``structlog`` to emit JSON log lines with ISO-8601 timestamps, log
levels, and rich context bindings. Application code obtains a logger via
:func:`get_logger` and must not use the stdlib ``logging`` module directly
or fall back to ``print()``.

``configure_logging`` is safe to call multiple times; structlog's
``configure`` is idempotent and the stdlib ``basicConfig`` guard ensures we
do not stack handlers on re-initialisation.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(level: str = "info", log_format: str = "json") -> None:
    """Configure structlog and the stdlib logging bridge.

    Args:
        level: Log level name (``debug``, ``info``, ``warning``, ``error``,
            ``critical``). Case-insensitive.
        log_format: ``"json"`` for machine-readable output (default) or
            ``"console"`` for rich, colourised developer output.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Route stdlib logging to the same sink. Only configure if no handlers
    # have been installed yet — this keeps repeated calls idempotent.
    if not logging.getLogger().handlers:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=numeric_level,
        )
    else:
        logging.getLogger().setLevel(numeric_level)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_context: Any) -> Any:
    """Return a structlog logger, optionally pre-bound with context.

    Args:
        **initial_context: Key/value pairs to bind onto every log record
            emitted through the returned logger (e.g. ``dataset_id``,
            ``stage``).

    Returns:
        A ``structlog`` bound logger. Callers should treat the return type
        as opaque and use the standard structlog API (``.info``,
        ``.warning``, ``.bind``, ``.error``).
    """
    logger = structlog.get_logger()
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger
