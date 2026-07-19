"""
Default self-evaluation configurations for all Angavu agents.

Registers rule-based evaluation rules per agent type to ensure
quality gates are applied before outputs propagate downstream.
"""

from app.agents.self_evaluation import (
    SelfEvaluationMiddleware,
    NonEmptyOutputRule,
    NoErrorRule,
    SchemaValidationRule,
    RangeCheckRule,
    OutputLengthRule,
    ConfidenceThresholdRule,
)


def configure_default_evaluations(evaluator: SelfEvaluationMiddleware) -> None:
    """Register default evaluation rules for all agent types."""

    # ── Data Processing Swarm ──────────────────────────────────────

    evaluator.register_agent(
        "TransactionProcessor",
        quality_threshold=0.8,
        rules=[
            NonEmptyOutputRule(),
            NoErrorRule(),
            SchemaValidationRule(required_fields=["transactions", "summary"]),
            ConfidenceThresholdRule(min_confidence=0.6),
        ],
    )

    # ── Intelligence Swarm ─────────────────────────────────────────

    evaluator.register_agent(
        "IntelligenceGenerator",
        quality_threshold=0.75,
        enable_llm_evaluation=True,  # Complex domain — use LLM eval
        llm_evaluation_threshold=0.5,
        max_iterations=3,
        max_tokens_per_loop=3000,
        rules=[
            NonEmptyOutputRule(),
            NoErrorRule(),
            SchemaValidationRule(required_fields=["intelligence", "confidence"]),
            RangeCheckRule("confidence", 0.0, 1.0),
            OutputLengthRule(min_length=50, content_field="intelligence"),
        ],
    )

    evaluator.register_agent(
        "AlamaScoreAgent",
        quality_threshold=0.9,  # Credit scoring needs high quality
        rules=[
            NonEmptyOutputRule(),
            NoErrorRule(),
            RangeCheckRule("alama_score", 300, 850),
            RangeCheckRule("confidence", 0.5, 1.0),
        ],
    )

    # ── Report Swarm ───────────────────────────────────────────────

    evaluator.register_agent(
        "ReportGenerator",
        quality_threshold=0.7,
        enable_llm_evaluation=True,
        rules=[
            NonEmptyOutputRule(),
            NoErrorRule(),
            OutputLengthRule(min_length=100, content_field="content"),
        ],
    )

    # ── Self-Evolution Swarm ───────────────────────────────────────

    evaluator.register_agent(
        "SelfEvolution",
        quality_threshold=0.6,  # Lower threshold — evolution is exploratory
        max_iterations=2,
        rules=[
            NonEmptyOutputRule(),
            NoErrorRule(),
        ],
    )

    # ── Governance Swarm ───────────────────────────────────────────

    evaluator.register_agent(
        "AuditAgent",
        quality_threshold=0.85,  # Audit must be high quality
        rules=[
            NonEmptyOutputRule(),
            NoErrorRule(),
            SchemaValidationRule(required_fields=["findings", "severity"]),
        ],
    )

    evaluator.register_agent(
        "EthicsAgent",
        quality_threshold=0.8,
        rules=[
            NonEmptyOutputRule(),
            NoErrorRule(),
            ConfidenceThresholdRule(min_confidence=0.6),
        ],
    )
