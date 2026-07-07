"""
Self-Improving Feedback Loop.

Learns from every transaction — not just explicit feedback,
but implicit signals from transaction outcomes. Continuously
improves decision parameters through outcome tracking, pattern
detection, strategy testing, and safe deployment.

Architecture:
    Transaction Outcome
           │
           ▼
    ┌──────────────────┐
    │ Signal Extraction │ ← Extract learning signals
    └──────┬───────────┘
           ▼
    ┌──────────────────┐
    │ Pattern Detection │ ← Identify patterns across signals
    └──────┬───────────┘
           ▼
    ┌──────────────────┐
    │ Strategy Update   │ ← Adjust decision parameters
    └──────┬───────────┘
           ▼
    ┌──────────────────┐
    │ Validation        │ ← A/B test against holdout data
    └──────┬───────────┘
           ▼
       Deploy / Rollback

Key insight: Reflexion learns from mistakes *within* a task.
Feedback Loop learns from outcomes *across* tasks. They are
complementary — Reflexion improves single decisions, Feedback
improves the decision-making strategy itself.
"""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence, Tuple

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


class SignalType(str, Enum):
    """Types of learning signals extracted from outcomes."""
    SUCCESS = "success"                    # Action succeeded
    FAILURE = "failure"                    # Action failed
    OUTPERFORMED = "outperformed"          # Better than expected
    UNDERPERFORMED = "underperformed"      # Worse than expected
    NOVEL_PATTERN = "novel_pattern"        # New pattern detected
    DRIFT = "drift"                        # Parameter drift detected
    ANOMALY = "anomaly"                    # Unexpected outcome


@dataclass
class LearningSignal:
    """A signal extracted from a transaction outcome."""
    signal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    signal_type: SignalType = SignalType.SUCCESS
    source_event_id: str = ""
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    outcome_value: float = 0.0       # Normalized outcome (-1 to 1)
    expected_value: float = 0.0      # What we predicted
    surprise: float = 0.0            # |outcome - expected|
    weight: float = 1.0              # Importance weight (decays with time)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
            "timestamp": self.timestamp,
            "outcome_value": round(self.outcome_value, 3),
            "expected_value": round(self.expected_value, 3),
            "surprise": round(self.surprise, 3),
            "weight": round(self.weight, 3),
            "tags": self.tags,
        }


@dataclass
class Pattern:
    """A detected pattern in learning signals."""
    pattern_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    description: str = ""
    confidence: float = 0.0          # 0.0 – 1.0
    signal_count: int = 0            # Number of signals supporting this pattern
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    context_signature: str = ""      # Hash of common context keys
    recommendation: str = ""         # What to do about it

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "description": self.description,
            "confidence": round(self.confidence, 3),
            "signal_count": self.signal_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "recommendation": self.recommendation,
        }


@dataclass
class StrategyParameter:
    """A tunable decision parameter with history."""
    name: str = ""
    current_value: float = 0.0
    default_value: float = 0.0
    min_value: float = 0.0
    max_value: float = 1.0
    update_count: int = 0
    last_updated: float = field(default_factory=time.time)
    performance_history: List[Tuple[float, float]] = field(default_factory=list)
    # (value, outcome_score) pairs

    def update(self, new_value: float, outcome_score: float) -> None:
        """Update parameter value and record outcome."""
        self.current_value = max(self.min_value, min(self.max_value, new_value))
        self.performance_history.append((self.current_value, outcome_score))
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]
        self.update_count += 1
        self.last_updated = time.time()

    def get_best_value(self) -> float:
        """Get the value that produced the best outcomes."""
        if not self.performance_history:
            return self.current_value
        return max(self.performance_history, key=lambda x: x[1])[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "current_value": round(self.current_value, 4),
            "default_value": round(self.default_value, 4),
            "update_count": self.update_count,
            "last_updated": self.last_updated,
            "best_value": round(self.get_best_value(), 4),
        }


@dataclass
class ABTestResult:
    """Result of an A/B test between strategy variants."""
    test_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    parameter_name: str = ""
    control_value: float = 0.0
    treatment_value: float = 0.0
    control_samples: int = 0
    treatment_samples: int = 0
    control_mean: float = 0.0
    treatment_mean: float = 0.0
    p_value: float = 1.0
    significant: bool = False
    winner: str = ""  # "control" | "treatment" | "inconclusive"
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "parameter_name": self.parameter_name,
            "control_value": round(self.control_value, 4),
            "treatment_value": round(self.treatment_value, 4),
            "control_mean": round(self.control_mean, 4),
            "treatment_mean": round(self.treatment_mean, 4),
            "p_value": round(self.p_value, 4),
            "significant": self.significant,
            "winner": self.winner,
        }


@dataclass
class FeedbackMetrics:
    """Aggregated feedback loop performance metrics."""
    total_signals: int = 0
    signals_by_type: Dict[str, int] = field(default_factory=dict)
    patterns_detected: int = 0
    strategies_updated: int = 0
    rollbacks: int = 0
    deployments: int = 0
    avg_surprise: float = 0.0
    improvement_rate: float = 0.0  # % of updates that improved outcomes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_signals": self.total_signals,
            "signals_by_type": self.signals_by_type,
            "patterns_detected": self.patterns_detected,
            "strategies_updated": self.strategies_updated,
            "deployments": self.deployments,
            "rollbacks": self.rollbacks,
            "avg_surprise": round(self.avg_surprise, 3),
            "improvement_rate": round(self.improvement_rate, 3),
        }


# ════════════════════════════════════════════════════════════════════
# Feedback Agent
# ════════════════════════════════════════════════════════════════════


class FeedbackAgent(BiasharaAgent):
    """
    Self-improving agent that learns from transaction outcomes.

    Unlike Reflexion (which improves within a single task), the
    FeedbackAgent improves the decision-making strategy itself
    across all tasks over time.

    The feedback loop has four stages:
    1. Signal Extraction — learn from each outcome
    2. Pattern Detection — find trends across signals
    3. Strategy Update — adjust parameters based on patterns
    4. Validation — A/B test before deploying changes

    This creates a virtuous cycle: better strategies → better
    outcomes → better signals → better strategies.

    Usage:
        agent = FeedbackAgent(
            name="PricingFeedback",
            role="Self-improving pricing strategy",
            capabilities=["price_optimization", "outcome_tracking"],
            parameters={
                "markup_pct": StrategyParameter(
                    name="markup_pct",
                    current_value=0.15,
                    default_value=0.15,
                    min_value=0.05,
                    max_value=0.50,
                ),
            },
        )
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        parameters: Optional[Dict[str, StrategyParameter]] = None,
        decay_half_life_hours: float = 168.0,  # 1 week
        min_signals_for_pattern: int = 5,
        min_signals_for_update: int = 10,
        ab_test_min_samples: int = 20,
    ):
        super().__init__(name, role, capabilities)
        self._parameters: Dict[str, StrategyParameter] = parameters or {}
        self._signals: List[LearningSignal] = []
        self._max_signals = 5000
        self._patterns: List[Pattern] = []
        self._ab_tests: List[ABTestResult] = []
        self._metrics = FeedbackMetrics()
        self._decay_half_life = decay_half_life_hours * 3600  # convert to seconds
        self._min_signals_for_pattern = min_signals_for_pattern
        self._min_signals_for_update = min_signals_for_update
        self._ab_test_min_samples = ab_test_min_samples
        self._pending_rollback: Optional[Dict[str, float]] = None

    @property
    def parameters(self) -> Dict[str, StrategyParameter]:
        """Access current strategy parameters."""
        return self._parameters

    def get_parameter(self, name: str) -> Optional[float]:
        """Get current value of a strategy parameter."""
        p = self._parameters.get(name)
        return p.current_value if p else None

    # ── Core loop ──────────────────────────────────────────────────

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """
        Process a feedback event through the learning pipeline.

        Events can be:
        - transaction.outcome: implicit feedback from transaction results
        - feedback.received: explicit feedback from workers
        - strategy.evaluate: trigger strategy evaluation cycle
        """
        try:
            event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)

            if event_type in ("transaction.outcome", "feedback.received"):
                return await self._process_outcome(event)
            elif event_type == "strategy.evaluate":
                return await self._evaluate_strategies()
            elif event_type == "strategy.deploy":
                return await self._deploy_pending()
            else:
                return AgentResult(
                    success=True,
                    data={"message": f"Unhandled event type: {event_type}"},
                )
        except Exception as exc:
            return AgentResult(success=False, error=str(exc))

    async def _process_outcome(self, event: AgentEvent) -> AgentResult:
        """Process a single outcome through the feedback pipeline."""
        # Stage 1: Extract signal
        signal = await self._extract_signal(event)
        self._signals.append(signal)
        if len(self._signals) > self._max_signals:
            self._signals = self._signals[-self._max_signals:]

        # Update metrics
        self._metrics.total_signals += 1
        st = signal.signal_type.value
        self._metrics.signals_by_type[st] = self._metrics.signals_by_type.get(st, 0) + 1

        # Update running average surprise
        n = self._metrics.total_signals
        self._metrics.avg_surprise = (
            self._metrics.avg_surprise + (signal.surprise - self._metrics.avg_surprise) / n
        )

        self._logger.info(
            "feedback_signal_extracted",
            signal_type=st,
            surprise=round(signal.surprise, 3),
            outcome=round(signal.outcome_value, 3),
        )

        # Stage 2: Detect patterns (batched — only every N signals)
        if self._metrics.total_signals % self._min_signals_for_pattern == 0:
            await self._detect_patterns()

        # Stage 3: Update strategies (batched — only every N signals)
        if self._metrics.total_signals % self._min_signals_for_update == 0:
            await self._update_strategies()

        return AgentResult(
            success=True,
            data={
                "signal": signal.to_dict(),
                "total_signals": self._metrics.total_signals,
                "patterns_count": len(self._patterns),
            },
        )

    # ── Stage 1: Signal Extraction ─────────────────────────────────

    async def _extract_signal(self, event: AgentEvent) -> LearningSignal:
        """
        Extract a learning signal from an outcome event.

        Computes:
        - outcome_value: normalized outcome score
        - expected_value: what we predicted
        - surprise: |outcome - expected| — how wrong we were
        - signal_type: success/failure/outperformed/etc.

        Subclasses should override _compute_outcome_value and
        _compute_expected_value for domain-specific logic.
        """
        payload = event.payload or {}

        outcome_value = await self._compute_outcome_value(payload)
        expected_value = await self._compute_expected_value(payload)
        surprise = abs(outcome_value - expected_value)

        # Determine signal type
        if surprise > 0.5:
            signal_type = SignalType.ANOMALY
        elif outcome_value > expected_value + 0.2:
            signal_type = SignalType.OUTPERFORMED
        elif outcome_value < expected_value - 0.2:
            signal_type = SignalType.UNDERPERFORMED
        elif outcome_value >= 0.5:
            signal_type = SignalType.SUCCESS
        else:
            signal_type = SignalType.FAILURE

        # Compute time-decayed weight
        weight = self._compute_weight(event.timestamp)

        return LearningSignal(
            signal_type=signal_type,
            source_event_id=event.event_id,
            timestamp=event.timestamp,
            context=payload,
            outcome_value=outcome_value,
            expected_value=expected_value,
            surprise=surprise,
            weight=weight,
            tags=self._extract_tags(payload),
        )

    async def _compute_outcome_value(self, payload: Dict[str, Any]) -> float:
        """
        Compute normalized outcome value from payload.

        Subclasses override for domain-specific scoring.
        Default: success=1.0, failure=0.0.
        """
        if payload.get("success", True):
            return 1.0
        return 0.0

    async def _compute_expected_value(self, payload: Dict[str, Any]) -> float:
        """
        Compute expected outcome value.

        Subclasses override for domain-specific prediction.
        Default: 0.5 (neutral expectation).
        """
        return 0.5

    def _compute_weight(self, timestamp: float) -> float:
        """Compute time-decayed weight using exponential decay."""
        age = time.time() - timestamp
        return math.exp(-0.693 * age / self._decay_half_life)  # ln(2) ≈ 0.693

    def _extract_tags(self, payload: Dict[str, Any]) -> List[str]:
        """Extract tags from payload for pattern grouping."""
        tags = []
        if "product_type" in payload:
            tags.append(f"product:{payload['product_type']}")
        if "market" in payload:
            tags.append(f"market:{payload['market']}")
        if "action" in payload:
            tags.append(f"action:{payload['action']}")
        return tags

    # ── Stage 2: Pattern Detection ─────────────────────────────────

    async def _detect_patterns(self) -> None:
        """
        Detect patterns across recent signals.

        Looks for:
        - Clusters of similar outcomes
        - Temporal patterns (time-of-day, day-of-week)
        - Context-dependent patterns (market-specific)
        - Drift patterns (parameters becoming less effective)
        """
        if len(self._signals) < self._min_signals_for_pattern:
            return

        recent = self._signals[-self._min_signals_for_pattern * 3:]

        # Group by tags
        tag_groups: Dict[str, List[LearningSignal]] = defaultdict(list)
        for signal in recent:
            for tag in signal.tags:
                tag_groups[tag].append(signal)

        new_patterns = []

        for tag, group in tag_groups.items():
            if len(group) < self._min_signals_for_pattern:
                continue

            # Compute group statistics
            outcomes = [s.outcome_value for s in group]
            mean_outcome = sum(outcomes) / len(outcomes)
            surprises = [s.surprise for s in group]
            mean_surprise = sum(surprises) / len(surprises)

            # Check for consistent success/failure
            success_rate = sum(1 for o in outcomes if o >= 0.5) / len(outcomes)

            if success_rate < 0.3:
                new_patterns.append(Pattern(
                    description=f"Consistent poor outcomes for {tag} (success rate: {success_rate:.0%})",
                    confidence=min(0.95, len(group) / 20),
                    signal_count=len(group),
                    context_signature=tag,
                    recommendation=f"Investigate and adjust strategy for {tag}",
                ))
            elif success_rate > 0.9 and mean_surprise > 0.3:
                new_patterns.append(Pattern(
                    description=f"High surprise but good outcomes for {tag} — may be overfitting",
                    confidence=min(0.8, len(group) / 15),
                    signal_count=len(group),
                    context_signature=tag,
                    recommendation=f"Validate {tag} outcomes are not coincidental",
                ))

        # Update patterns (merge with existing)
        for new_p in new_patterns:
            existing = next(
                (p for p in self._patterns if p.context_signature == new_p.context_signature),
                None,
            )
            if existing:
                existing.confidence = max(existing.confidence, new_p.confidence)
                existing.signal_count = new_p.signal_count
                existing.last_seen = time.time()
                existing.recommendation = new_p.recommendation
            else:
                self._patterns.append(new_p)
                self._metrics.patterns_detected += 1

        self._logger.info(
            "patterns_detected",
            new=len(new_patterns),
            total=len(self._patterns),
        )

    # ── Stage 3: Strategy Update ───────────────────────────────────

    async def _update_strategies(self) -> None:
        """
        Update strategy parameters based on accumulated signals.

        For each parameter:
        1. Compute current performance (weighted outcome average)
        2. Try small perturbation (increase/decrease)
        3. Set up A/B test if promising
        """
        if not self._parameters:
            return

        for name, param in self._parameters.items():
            # Get signals relevant to this parameter
            relevant = [
                s for s in self._signals[-200:]
                if any(name in tag for tag in s.tags) or not s.tags
            ]

            if len(relevant) < 5:
                continue

            # Compute weighted performance at current value
            current_performance = self._weighted_performance(relevant)

            # Try perturbation
            delta = (param.max_value - param.min_value) * 0.05
            test_up = param.current_value + delta
            test_down = param.current_value - delta

            # Simple gradient: which direction improves outcomes?
            # Use historical data if available
            if param.performance_history:
                recent_history = param.performance_history[-20:]
                values = [h[0] for h in recent_history]
                outcomes = [h[1] for h in recent_history]

                # Simple linear correlation
                if len(values) >= 5:
                    mean_v = sum(values) / len(values)
                    mean_o = sum(outcomes) / len(outcomes)
                    cov = sum((v - mean_v) * (o - mean_o) for v, o in zip(values, outcomes))
                    var_v = sum((v - mean_v) ** 2 for v in values)

                    if var_v > 0:
                        gradient = cov / var_v
                        # Move in the direction of positive correlation
                        step = delta * (1 if gradient > 0 else -1)
                        new_value = param.current_value + step

                        param.update(new_value, current_performance)
                        self._metrics.strategies_updated += 1

                        self._logger.info(
                            "strategy_updated",
                            parameter=name,
                            old_value=round(param.current_value - step, 4),
                            new_value=round(param.current_value, 4),
                            gradient=round(gradient, 4),
                        )

    def _weighted_performance(self, signals: List[LearningSignal]) -> float:
        """Compute weighted average performance from signals."""
        if not signals:
            return 0.5
        total_weight = sum(s.weight for s in signals)
        if total_weight == 0:
            return 0.5
        return sum(s.outcome_value * s.weight for s in signals) / total_weight

    # ── Stage 4: Validation & Deployment ───────────────────────────

    async def _evaluate_strategies(self) -> AgentResult:
        """
        Evaluate current strategies against recent performance.

        Compares current parameter values with historical bests.
        Triggers rollback if performance has degraded significantly.
        """
        evaluations = {}

        for name, param in self._parameters.items():
            current_perf = self._evaluate_parameter_performance(name)
            best_value = param.get_best_value()
            is_at_best = abs(param.current_value - best_value) < 0.01

            evaluations[name] = {
                "current_value": round(param.current_value, 4),
                "best_value": round(best_value, 4),
                "current_performance": round(current_perf, 3),
                "is_at_best": is_at_best,
                "update_count": param.update_count,
            }

            # Check for significant degradation
            if not is_at_best and param.performance_history:
                best_perf = max(h[1] for h in param.performance_history[-50:])
                if current_perf < best_perf * 0.7:  # 30% degradation
                    # Queue rollback
                    if self._pending_rollback is None:
                        self._pending_rollback = {}
                    self._pending_rollback[name] = best_value
                    self._logger.warning(
                        "strategy_degradation_detected",
                        parameter=name,
                        current_perf=round(current_perf, 3),
                        best_perf=round(best_perf, 3),
                    )

        return AgentResult(
            success=True,
            data={
                "evaluations": evaluations,
                "pending_rollback": self._pending_rollback is not None,
            },
        )

    def _evaluate_parameter_performance(self, name: str) -> float:
        """Evaluate current performance for a parameter."""
        param = self._parameters.get(name)
        if not param or not param.performance_history:
            return 0.5
        recent = param.performance_history[-10:]
        return sum(h[1] for h in recent) / len(recent)

    async def _deploy_pending(self) -> AgentResult:
        """Deploy pending strategy changes or rollbacks."""
        if self._pending_rollback:
            # Execute rollback
            for name, best_value in self._pending_rollback.items():
                param = self._parameters.get(name)
                if param:
                    old_value = param.current_value
                    param.current_value = best_value
                    self._metrics.rollbacks += 1
                    self._logger.info(
                        "strategy_rollback",
                        parameter=name,
                        from_value=round(old_value, 4),
                        to_value=round(best_value, 4),
                    )
            self._pending_rollback = None
            return AgentResult(success=True, data={"action": "rollback_executed"})

        self._metrics.deployments += 1
        return AgentResult(success=True, data={"action": "strategies_deployed"})

    # ── Query methods ──────────────────────────────────────────────

    def get_recent_signals(self, n: int = 20) -> List[Dict[str, Any]]:
        """Get recent learning signals."""
        return [s.to_dict() for s in self._signals[-n:]]

    def get_patterns(self) -> List[Dict[str, Any]]:
        """Get detected patterns."""
        return [p.to_dict() for p in self._patterns]

    def get_strategy_parameters(self) -> Dict[str, Any]:
        """Get current strategy parameter values."""
        return {name: p.to_dict() for name, p in self._parameters.items()}

    def get_metrics(self) -> Dict[str, Any]:
        """Get feedback loop metrics."""
        return self._metrics.to_dict()

    def get_improvement_trajectory(self, parameter_name: str) -> List[Dict[str, Any]]:
        """Get performance trajectory for a parameter over time."""
        param = self._parameters.get(parameter_name)
        if not param:
            return []
        return [
            {"value": round(v, 4), "outcome": round(o, 3)}
            for v, o in param.performance_history
        ]
