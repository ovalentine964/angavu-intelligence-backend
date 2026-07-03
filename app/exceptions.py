"""
Custom exception hierarchy for Angavu Intelligence.

All application exceptions inherit from BiasharaError so callers can
catch the base class for broad handling while still allowing specific
catches where needed.

Hierarchy:
    BiasharaError
    ├── AgentError           — agent lifecycle / processing failures
    │   ├── AgentStartError
    │   └── AgentStopError
    ├── EventBusError        — event publish / subscribe / consume failures
    │   ├── EventPublishError
    │   └── EventConsumeError
    ├── PipelineError        — intelligence / training pipeline failures
    │   ├── TrainingError
    │   └── EvaluationError
    ├── ServiceError         — external service integration failures
    │   ├── DatabaseError
    │   ├── CacheError
    │   └── ExternalAPIError
    └── ConfigurationError   — settings / config validation failures
"""

from __future__ import annotations


class BiasharaError(Exception):
    """Base exception for all Angavu Intelligence errors."""

    def __init__(self, message: str = "", *, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {}


# ── Agent Errors ─────────────────────────────────────────────────


class AgentError(BiasharaError):
    """Base for agent lifecycle and processing failures."""


class AgentStartError(AgentError):
    """Agent failed to start."""


class AgentStopError(AgentError):
    """Agent failed to stop gracefully."""


class AgentProcessingError(AgentError):
    """Agent failed while processing an event or task."""


# ── Event Bus Errors ─────────────────────────────────────────────


class EventBusError(BiasharaError):
    """Base for event bus failures."""


class EventPublishError(EventBusError):
    """Failed to publish an event to a stream."""


class EventConsumeError(EventBusError):
    """Failed to consume or parse an event from a stream."""


class EventBusConnectionError(EventBusError):
    """Failed to connect to the event bus backend (Redis)."""


# ── Pipeline Errors ──────────────────────────────────────────────


class PipelineError(BiasharaError):
    """Base for intelligence / training pipeline failures."""


class TrainingError(PipelineError):
    """Training cycle failed."""


class EvaluationError(PipelineError):
    """Model evaluation failed."""


class DataQualityError(PipelineError):
    """Training data did not pass quality gates."""


# ── Service Errors ───────────────────────────────────────────────


class ServiceError(BiasharaError):
    """Base for external service integration failures."""


class DatabaseError(ServiceError):
    """Database operation failed."""


class CacheError(ServiceError):
    """Cache operation failed."""


class ExternalAPIError(ServiceError):
    """External API call failed."""

    def __init__(self, message: str = "", *, status_code: int | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.status_code = status_code


class ConfigurationError(BiasharaError):
    """Application configuration is invalid or missing."""
