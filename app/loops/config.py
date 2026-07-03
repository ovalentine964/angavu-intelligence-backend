"""
Biashara Loop Configuration — Maps features to DeerFlow loop patterns.

Each Biashara feature (tithe tracking, goal progress, loan management,
intelligence generation) is configured as a DeerFlow goal with:
- Which loop pattern to use (goal-driven, plan-execute, reflexion)
- Evaluation criteria (when is the goal "satisfied"?)
- Continuation limits (max retries, no-progress detection)
- Agent assignments (which agent handles which phase)

This configures DeerFlow's existing patterns — it doesn't create new ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LoopType(str, Enum):
    """Types of loops available via DeerFlow."""
    GOAL = "goal"               # Goal-driven (evaluate → continue/stop)
    PLAN_EXECUTE = "plan_execute"  # Multi-step planning
    REACT = "react"             # Reasoning + Acting
    REFLEXION = "reflexion"     # Self-critique + retry
    EVENT_SOURCED = "event_sourced"  # Full audit trail


class EvaluationMode(str, Enum):
    """How to evaluate if the loop's goal is satisfied."""
    THRESHOLD = "threshold"     # Numeric threshold (e.g., score >= 0.8)
    COMPLETION = "completion"   # All steps completed
    CONVERGENCE = "convergence" # Result converged (no change between iterations)
    MANUAL = "manual"           # User or external system confirms


@dataclass
class LoopPhaseConfig:
    """Configuration for a single phase within a loop."""
    name: str
    description: str
    agent_name: Optional[str] = None  # Which agent handles this phase
    timeout_seconds: float = 30.0
    retry_count: int = 1
    required: bool = True


@dataclass
class EvaluationConfig:
    """Configuration for goal evaluation."""
    mode: EvaluationMode = EvaluationMode.THRESHOLD
    threshold: float = 0.7  # For THRESHOLD mode
    max_continuations: int = 8  # DeerFlow DEFAULT_MAX_GOAL_CONTINUATIONS
    max_no_progress: int = 2   # DeerFlow DEFAULT_MAX_NO_PROGRESS_CONTINUATIONS
    evidence_fields: List[str] = field(default_factory=list)  # Fields to check for evidence


@dataclass
class BiasharaLoopConfig:
    """
    Configuration for a Biashara-specific loop.

    Maps a feature to DeerFlow's goal system:
    - loop_type: Which DeerFlow pattern to use
    - phases: Ordered phases of the loop
    - evaluation: How to evaluate goal completion
    - metadata: Feature-specific configuration
    """
    feature_name: str
    description: str
    loop_type: LoopType
    phases: List[LoopPhaseConfig]
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_goal_objective(self) -> str:
        """Convert this config to a DeerFlow goal objective string."""
        phase_names = " → ".join(p.name for p in self.phases)
        return f"[{self.feature_name}] {self.description}: {phase_names}"


# ════════════════════════════════════════════════════════════════════
# Global Registry
# ════════════════════════════════════════════════════════════════════

_loop_configs: Dict[str, BiasharaLoopConfig] = {}


def register_loop_config(config: BiasharaLoopConfig) -> None:
    """Register a loop configuration globally."""
    _loop_configs[config.feature_name] = config


def get_loop_config(feature_name: str) -> Optional[BiasharaLoopConfig]:
    """Get a registered loop configuration by feature name."""
    return _loop_configs.get(feature_name)


def get_all_loop_configs() -> Dict[str, BiasharaLoopConfig]:
    """Get all registered loop configurations."""
    return dict(_loop_configs)


def get_enabled_loop_configs() -> Dict[str, BiasharaLoopConfig]:
    """Get only enabled loop configurations."""
    return {k: v for k, v in _loop_configs.items() if v.enabled}


# ════════════════════════════════════════════════════════════════════
# Default Configurations — Register on import
# ════════════════════════════════════════════════════════════════════

def _register_defaults() -> None:
    """Register default Biashara loop configurations."""

    # Tithe Tracking Loop: Record → Analyze → Encourage
    register_loop_config(BiasharaLoopConfig(
        feature_name="tithe_tracking",
        description="Track tithe payments, analyze patterns, and encourage consistent giving",
        loop_type=LoopType.GOAL,
        phases=[
            LoopPhaseConfig(
                name="record",
                description="Record tithe payment or missed payment",
                agent_name="TransactionProcessor",
                timeout_seconds=10.0,
            ),
            LoopPhaseConfig(
                name="analyze",
                description="Analyze tithe patterns and consistency",
                agent_name="IntelligenceGenerator",
                timeout_seconds=30.0,
            ),
            LoopPhaseConfig(
                name="encourage",
                description="Generate encouragement message or streak alert",
                agent_name="ReportGenerator",
                timeout_seconds=15.0,
            ),
        ],
        evaluation=EvaluationConfig(
            mode=EvaluationMode.COMPLETION,
            max_continuations=3,
            max_no_progress=1,
            evidence_fields=["payment_recorded", "analysis_complete", "message_sent"],
        ),
        metadata={
            "streak_threshold_days": 7,
            "encouragement_frequency": "weekly",
            "missed_payment_alert_after_days": 14,
        },
    ))

    # Goal Progress Loop: Track → Predict → Nudge
    register_loop_config(BiasharaLoopConfig(
        feature_name="goal_progress",
        description="Track savings goals, predict completion, and nudge toward targets",
        loop_type=LoopType.REACT,
        phases=[
            LoopPhaseConfig(
                name="track",
                description="Record goal contribution and update progress",
                agent_name="TransactionProcessor",
                timeout_seconds=10.0,
            ),
            LoopPhaseConfig(
                name="predict",
                description="Predict goal completion date based on current trajectory",
                agent_name="IntelligenceGenerator",
                timeout_seconds=20.0,
            ),
            LoopPhaseConfig(
                name="nudge",
                description="Generate motivational nudge or adjustment suggestion",
                agent_name="ReportGenerator",
                timeout_seconds=15.0,
            ),
        ],
        evaluation=EvaluationConfig(
            mode=EvaluationMode.THRESHOLD,
            threshold=0.8,
            max_continuations=5,
            max_no_progress=2,
            evidence_fields=["progress_updated", "prediction_generated", "nudge_sent"],
        ),
        metadata={
            "prediction_lookahead_days": 90,
            "nudge_frequency_days": 7,
            "on_track_threshold": 0.8,
        },
    ))

    # Loan Management Loop: Record → Verify → Alert
    register_loop_config(BiasharaLoopConfig(
        feature_name="loan_management",
        description="Manage loan lifecycle from disbursement through repayment tracking",
        loop_type=LoopType.REFLEXION,
        phases=[
            LoopPhaseConfig(
                name="record",
                description="Record loan disbursement or repayment",
                agent_name="TransactionProcessor",
                timeout_seconds=10.0,
            ),
            LoopPhaseConfig(
                name="verify",
                description="Verify repayment against schedule and update balance",
                agent_name="IntelligenceGenerator",
                timeout_seconds=20.0,
                retry_count=2,
            ),
            LoopPhaseConfig(
                name="alert",
                description="Generate alerts for overdue payments or milestones",
                agent_name="ReportGenerator",
                timeout_seconds=15.0,
            ),
        ],
        evaluation=EvaluationConfig(
            mode=EvaluationMode.THRESHOLD,
            threshold=0.85,
            max_continuations=4,
            max_no_progress=2,
            evidence_fields=["payment_recorded", "verification_complete", "alert_sent"],
        ),
        metadata={
            "grace_period_days": 3,
            "overdue_alert_frequency_days": 3,
            "partial_payment_threshold": 0.1,
            "default_escalation_days": 30,
        },
    ))

    # Intelligence Generation Loop: Collect → Analyze → Deliver
    register_loop_config(BiasharaLoopConfig(
        feature_name="intelligence_generation",
        description="Collect data, generate intelligence products, and deliver insights",
        loop_type=LoopType.PLAN_EXECUTE,
        phases=[
            LoopPhaseConfig(
                name="collect",
                description="Collect transaction data, market data, and user context",
                agent_name="TransactionProcessor",
                timeout_seconds=60.0,
            ),
            LoopPhaseConfig(
                name="analyze",
                description="Run Soko Pulse, Alama Score, and econometric analysis",
                agent_name="IntelligenceGenerator",
                timeout_seconds=120.0,
                retry_count=2,
            ),
            LoopPhaseConfig(
                name="deliver",
                description="Format and deliver intelligence via WhatsApp",
                agent_name="ReportGenerator",
                timeout_seconds=30.0,
            ),
        ],
        evaluation=EvaluationConfig(
            mode=EvaluationMode.COMPLETION,
            max_continuations=3,
            max_no_progress=1,
            evidence_fields=["data_collected", "analysis_complete", "report_delivered"],
        ),
        metadata={
            "products": ["market_intelligence", "price_forecast", "credit_score"],
            "delivery_channel": "whatsapp",
            "report_language": "sw",
        },
    ))


# Register defaults on module import
_register_defaults()
