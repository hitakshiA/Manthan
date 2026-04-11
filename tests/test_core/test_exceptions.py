"""Tests for the custom exception hierarchy."""

from src.core.exceptions import (
    ConfigurationError,
    DcdValidationError,
    IngestionError,
    LlmError,
    LlmTimeoutError,
    ManthanError,
    MaterializationError,
    ProfilingError,
    ProfilingRetryableError,
    SandboxError,
    SqlValidationError,
    ToolError,
)


def test_top_level_errors_inherit_from_manthan_error() -> None:
    for cls in (
        ConfigurationError,
        IngestionError,
        ProfilingError,
        MaterializationError,
        ToolError,
        LlmError,
        DcdValidationError,
    ):
        assert issubclass(cls, ManthanError)
        assert issubclass(cls, Exception)


def test_profiling_retryable_inherits_from_profiling_error() -> None:
    assert issubclass(ProfilingRetryableError, ProfilingError)


def test_llm_timeout_inherits_from_llm_error() -> None:
    assert issubclass(LlmTimeoutError, LlmError)


def test_sql_validation_and_sandbox_are_tool_errors() -> None:
    assert issubclass(SqlValidationError, ToolError)
    assert issubclass(SandboxError, ToolError)


def test_errors_carry_message() -> None:
    exc = ProfilingError("column classification failed")
    assert str(exc) == "column classification failed"
