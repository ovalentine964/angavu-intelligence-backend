"""
Agent Execution Harness — Unified control plane for all agent calls.

Components:
    - AgentExecutionHarness: Wraps agent calls with timeout, retry, circuit breaker
    - CircuitBreaker: Prevents cascading failures
    - AgentMetricsCollector: Tracks latency, success rate, tokens, cost
    - OutputValidator: Validates agent outputs against schemas
    - CanaryRouter: Gradual rollout of new agent versions

Usage:
    from app.agents.harness import get_execution_harness, AgentExecutionHarness

    harness = get_execution_harness()
    result = await harness.execute(agent, event)
"""

from app.agents.harness.execution import (
    AgentExecutionHarness,
    AgentMetricsCollector,
    CanaryRouter,
    CircuitBreaker,
    CircuitState,
    ExecutionRecord,
    HarnessConfig,
    OutputValidator,
    ValidationResult,
    create_default_validator,
    create_harness,
    get_execution_harness,
)

__all__ = [
    "AgentExecutionHarness",
    "AgentMetricsCollector",
    "CanaryRouter",
    "CircuitBreaker",
    "CircuitState",
    "ExecutionRecord",
    "HarnessConfig",
    "OutputValidator",
    "ValidationResult",
    "create_default_validator",
    "create_harness",
    "get_execution_harness",
]
