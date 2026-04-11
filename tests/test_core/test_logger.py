"""Tests for src.core.logger."""

from src.core.logger import configure_logging, get_logger


def test_configure_logging_is_idempotent() -> None:
    configure_logging(level="info", log_format="json")
    configure_logging(level="debug", log_format="console")
    configure_logging(level="info", log_format="json")


def test_get_logger_returns_a_usable_logger() -> None:
    configure_logging(level="info", log_format="json")
    logger = get_logger()
    logger.info("scaffold.event", step="smoke")


def test_get_logger_binds_initial_context() -> None:
    configure_logging(level="info", log_format="json")
    logger = get_logger(dataset_id="ds_fixture", stage="silver")
    logger.info("classification.complete", columns=3)


def test_get_logger_accepts_console_format() -> None:
    configure_logging(level="info", log_format="console")
    logger = get_logger()
    logger.info("console.event")
