"""
Agent Harness — Unified control plane for all Angavu agent operations.

Components:
    - AgentExecutionHarness: Wraps agent calls with monitoring, timeout, retry, circuit breaker
    - DataPipelineHarness: Wraps intelligence pipeline with validation, drift detection, quality scoring
    - InferenceHarness: Wraps LLM calls with fallback chains, cost tracking, quality validation
    - DeploymentHarness: Canary deployment (1% → 10% → 50% → 100%)

Usage:
    from app.agents.harness import (
        get_execution_harness,
        get_data_pipeline_harness,
    )
    from app.services.ml.inference_harness import get_inference_harness
    from app.infrastructure.deployment_harness import get_deployment_harness
"""

# ── Agent Execution Harness ────────────────────────────────────────
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

# ── Data Pipeline Harness ──────────────────────────────────────────
from app.agents.harness.data_harness import (
    DataPipelineHarness,
    DataHarnessConfig,
    DataDriftDetector,
    DataQualityScorer,
    DriftAlert,
    PipelineExecutionRecord,
    QualityDimension,
    QualityScore,
    create_data_pipeline_harness,
    get_data_pipeline_harness,
)

__all__ = [
    # Execution Harness
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
    # Data Pipeline Harness
    "DataPipelineHarness",
    "DataHarnessConfig",
    "DataDriftDetector",
    "DataQualityScorer",
    "DriftAlert",
    "PipelineExecutionRecord",
    "QualityDimension",
    "QualityScore",
    "create_data_pipeline_harness",
    "get_data_pipeline_harness",
]
