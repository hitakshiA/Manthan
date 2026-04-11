"""Custom exception hierarchy for the Manthan data layer.

Every application error inherits from ``ManthanError`` so that callers can
catch "any Manthan error" with a single ``except`` clause while still being
able to catch specific sub-classes when they want finer-grained handling.

Per AGENTS.md, no bare ``except:`` clauses are allowed in application code —
always catch a specific subclass of ``ManthanError`` or a concrete
third-party exception.
"""


class ManthanError(Exception):
    """Base class for all Manthan data layer errors."""


class ConfigurationError(ManthanError):
    """Raised when application configuration is invalid or missing."""


class IngestionError(ManthanError):
    """Raised when a Bronze-stage loader fails to read or validate a source."""


class ProfilingError(ManthanError):
    """Raised when the Silver-stage profiling agent cannot classify a dataset."""


class ProfilingRetryableError(ProfilingError):
    """Raised for transient profiling failures that the agent should retry."""


class DcdValidationError(ManthanError):
    """Raised when a Data Context Document fails schema validation."""


class MaterializationError(ManthanError):
    """Raised when the Gold-stage materialization pipeline fails."""


class ToolError(ManthanError):
    """Raised when an agent-facing tool fails."""


class SqlValidationError(ToolError):
    """Raised when a SQL statement fails parse or catalog validation."""


class SandboxError(ToolError):
    """Raised when the Python sandbox fails to start, run, or terminate."""


class LlmError(ManthanError):
    """Raised when the LLM client fails for any reason."""


class LlmTimeoutError(LlmError):
    """Raised when an LLM API call exceeds its timeout."""
