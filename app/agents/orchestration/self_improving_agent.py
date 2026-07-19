"""
Self-Improving Agent — Feedback-driven agent skill optimization.

Inspired by: awesome-llm-apps/agent_skills/self-improving-agent-skills/
Pattern: executor (run + score) → analyst (diagnose failures) → mutator (apply fix)

Agents that learn from feedback loops:
- Collect performance feedback from events and user ratings
- Diagnose failure patterns using structured analysis
- Apply targeted improvements to agent behavior parameters
- Track improvement metrics over time

Architecture:
    FeedbackAnalyzer → collects and categorizes feedback signals
    SkillMutator → applies targeted behavior adjustments
    SelfImprovingAgent → wraps any BiasharaAgent with self-improvement

Integrates with:
    - Angavu EventBus (feedback.received events)
    - BiasharaAgent.memory for storing improvement history
    - Existing reflect() method for closing the loop
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

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
# Feedback Types
# ════════════════════════════════════════════════════════════════════


class FeedbackType(StrEnum):
    """Types of feedback signals."""
    USER_RATING = "user_rating"           # Explicit user score (1-5)
    SUCCESS_RATE = "success_rate"         # Task completion success
    LATENCY = "latency"                   # Response time feedback
    ACCURACY = "accuracy"                 # Output quality assessment
    COST_EFFICIENCY = "cost_efficiency"   # Token/cost optimization
    ERROR_PATTERN = "error_pattern"       # Recurring failure detection
    MANUAL_CORRECTION = "manual_correction"  # Human-in-the-loop fix


class MutationStrategy(StrEnum):
    """Strategies for agent behavior improvement."""
    ADJUST_CONFIDENCE = "adjust_confidence"       # Tune confidence thresholds
    ADD_CONTEXT = "add_context"                   # Include more context in decisions
    REFINE_FILTERING = "refine_filtering"         # Better event/data filtering
    OPTIMIZE_PARAMETERS = "optimize_parameters"   # Tune numeric parameters
    ADD_FALLBACK = "add_fallback"                 # Add fallback behavior paths
    RESTRICT_SCOPE = "restrict_scope"             # Narrow agent's operational scope
    EXPAND_CAPABILITY = "expand_capability"       # Add new behavior patterns


@dataclass(frozen=True)
class FeedbackSignal:
    """A single feedback observation."""
    feedback_type: FeedbackType
    agent_name: str
    value: float              # Normalized 0.0-1.0 (or raw score for ratings)
    context: dict[str, Any]   # What was the agent doing
    source: str               # Who/what gave this feedback
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FailureDiagnosis:
    """Analysis of why an agent failed."""
    root_cause: str
    failure_category: str
    mutation_strategy: MutationStrategy
    target_parameter: str
    suggested_change: str
    confidence: float         # How confident in this diagnosis

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorMutation:
    """A targeted change to agent behavior."""
    description: str
    reasoning: str
    strategy: MutationStrategy
    parameter_changes: dict[str, Any]
    expected_improvement: str
    applied_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementCycle:
    """Record of one improvement attempt."""
    cycle_number: int
    diagnosis: FailureDiagnosis
    mutation: BehaviorMutation
    score_before: float
    score_after: float
    kept: bool
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# FeedbackAnalyzer — Collect and Diagnose
# ════════════════════════════════════════════════════════════════════


class FeedbackAnalyzer:
    """
    Collects feedback signals and diagnoses failure patterns.

    Inspired by the self-improving-agent-skills 'analyst' agent:
    - Aggregates feedback over time windows
    - Detects failure patterns and trends
    - Recommends specific mutation strategies
    """

    def __init__(self, window_size: int = 50):
        self._window_size = window_size
        self._feedback_buffer: dict[str, list[FeedbackSignal]] = {}
        self._diagnosis_history: list[FailureDiagnosis] = []
        self._logger = logger.bind(component="feedback_analyzer")

    def record_feedback(self, signal: FeedbackSignal) -> None:
        """Record a feedback signal."""
        agent = signal.agent_name
        if agent not in self._feedback_buffer:
            self._feedback_buffer[agent] = []
        self._feedback_buffer[agent].append(signal)
        # Trim to window size
        if len(self._feedback_buffer[agent]) > self._window_size:
            self._feedback_buffer[agent] = self._feedback_buffer[agent][-self._window_size:]

    def get_feedback_summary(self, agent_name: str) -> dict[str, Any]:
        """Get aggregated feedback summary for an agent."""
        signals = self._feedback_buffer.get(agent_name, [])
        if not signals:
            return {"agent": agent_name, "signal_count": 0, "status": "no_data"}

        by_type: dict[str, list[float]] = {}
        for s in signals:
            by_type.setdefault(s.feedback_type.value, []).append(s.value)

        summary = {}
        for ftype, values in by_type.items():
            summary[ftype] = {
                "count": len(values),
                "mean": round(sum(values) / len(values), 3),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "trend": self._compute_trend(values),
            }

        return {
            "agent": agent_name,
            "signal_count": len(signals),
            "by_type": summary,
            "overall_score": self._compute_overall_score(signals),
        }

    def diagnose(
        self,
        agent_name: str,
        recent_results: list[dict[str, Any]],
    ) -> FailureDiagnosis | None:
        """
        Analyze recent results and diagnose improvement opportunities.

        Returns None if agent is performing well.
        """
        summary = self.get_feedback_summary(agent_name)

        if summary.get("signal_count", 0) < 5:
            return None  # Not enough data

        overall = summary.get("overall_score", 1.0)

        # Check for success rate issues
        success_signals = [
            s for s in self._feedback_buffer.get(agent_name, [])
            if s.feedback_type == FeedbackType.SUCCESS_RATE
        ]
        if success_signals:
            recent_success = [s.value for s in success_signals[-10:]]
            success_rate = sum(recent_success) / len(recent_success)
            if success_rate < 0.7:
                diagnosis = FailureDiagnosis(
                    root_cause=f"Low success rate: {success_rate:.1%}",
                    failure_category="reliability",
                    mutation_strategy=MutationStrategy.ADD_FALLBACK,
                    target_parameter="error_handling",
                    suggested_change="Add fallback behavior for common failure modes",
                    confidence=0.8,
                )
                self._diagnosis_history.append(diagnosis)
                return diagnosis

        # Check for latency issues
        latency_signals = [
            s for s in self._feedback_buffer.get(agent_name, [])
            if s.feedback_type == FeedbackType.LATENCY
        ]
        if latency_signals:
            recent_latency = [s.value for s in latency_signals[-10:]]
            avg_latency = sum(recent_latency) / len(recent_latency)
            if avg_latency < 0.5:  # Low score = high latency
                diagnosis = FailureDiagnosis(
                    root_cause=f"High latency: score={avg_latency:.2f}",
                    failure_category="performance",
                    mutation_strategy=MutationStrategy.OPTIMIZE_PARAMETERS,
                    target_parameter="timeout_ms",
                    suggested_change="Reduce processing scope or increase timeouts",
                    confidence=0.7,
                )
                self._diagnosis_history.append(diagnosis)
                return diagnosis

        # Check for accuracy issues
        accuracy_signals = [
            s for s in self._feedback_buffer.get(agent_name, [])
            if s.feedback_type == FeedbackType.ACCURACY
        ]
        if accuracy_signals:
            recent_accuracy = [s.value for s in accuracy_signals[-10:]]
            avg_accuracy = sum(recent_accuracy) / len(recent_accuracy)
            if avg_accuracy < 0.6:
                diagnosis = FailureDiagnosis(
                    root_cause=f"Low accuracy: score={avg_accuracy:.2f}",
                    failure_category="quality",
                    mutation_strategy=MutationStrategy.ADD_CONTEXT,
                    target_parameter="context_window",
                    suggested_change="Include more context in decision-making",
                    confidence=0.75,
                )
                self._diagnosis_history.append(diagnosis)
                return diagnosis

        # Check for cost inefficiency
        cost_signals = [
            s for s in self._feedback_buffer.get(agent_name, [])
            if s.feedback_type == FeedbackType.COST_EFFICIENCY
        ]
        if cost_signals:
            recent_cost = [s.value for s in cost_signals[-10:]]
            avg_cost = sum(recent_cost) / len(recent_cost)
            if avg_cost < 0.5:
                diagnosis = FailureDiagnosis(
                    root_cause=f"Cost inefficient: score={avg_cost:.2f}",
                    failure_category="efficiency",
                    mutation_strategy=MutationStrategy.RESTRICT_SCOPE,
                    target_parameter="max_tokens",
                    suggested_change="Restrict scope to reduce token usage",
                    confidence=0.65,
                )
                self._diagnosis_history.append(diagnosis)
                return diagnosis

        return None  # Performing well

    def _compute_trend(self, values: list[float]) -> str:
        """Compute trend direction from a sequence of values."""
        if len(values) < 3:
            return "insufficient_data"
        recent = values[-5:]
        earlier = values[-10:-5] if len(values) >= 10 else values[:len(values)//2]
        if not earlier:
            return "insufficient_data"
        recent_avg = sum(recent) / len(recent)
        earlier_avg = sum(earlier) / len(earlier)
        diff = recent_avg - earlier_avg
        if diff > 0.05:
            return "improving"
        if diff < -0.05:
            return "declining"
        return "stable"

    def _compute_overall_score(self, signals: list[FeedbackSignal]) -> float:
        """Compute a weighted overall score."""
        if not signals:
            return 1.0

        weights = {
            FeedbackType.SUCCESS_RATE: 0.3,
            FeedbackType.ACCURACY: 0.25,
            FeedbackType.USER_RATING: 0.2,
            FeedbackType.LATENCY: 0.1,
            FeedbackType.COST_EFFICIENCY: 0.1,
            FeedbackType.ERROR_PATTERN: 0.05,
        }

        by_type: dict[str, list[float]] = {}
        for s in signals:
            by_type.setdefault(s.feedback_type.value, []).append(s.value)

        weighted_sum = 0.0
        total_weight = 0.0
        for ftype, values in by_type.items():
            try:
                fb_type = FeedbackType(ftype)
            except ValueError:
                continue
            weight = weights.get(fb_type, 0.05)
            avg = sum(values) / len(values)
            weighted_sum += avg * weight
            total_weight += weight

        return round(weighted_sum / max(total_weight, 0.01), 3)


# ════════════════════════════════════════════════════════════════════
# SkillMutator — Apply Targeted Improvements
# ════════════════════════════════════════════════════════════════════


class SkillMutator:
    """
    Applies targeted behavior adjustments to agents.

    Inspired by the self-improving-agent-skills 'mutator' agent:
    - Takes a diagnosis and produces a specific behavior change
    - Changes are reversible (stored in mutation history)
    - One change per cycle to isolate effects
    """

    def __init__(self):
        self._mutation_history: list[BehaviorMutation] = []
        self._logger = logger.bind(component="skill_mutator")

    def mutate(
        self,
        agent: BiasharaAgent,
        diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """
        Apply a targeted mutation based on the diagnosis.

        Returns the mutation that was applied.
        """
        strategy = diagnosis.mutation_strategy
        mutation = self._apply_strategy(agent, strategy, diagnosis)
        self._mutation_history.append(mutation)
        self._logger.info(
            "mutation_applied",
            agent=agent.name,
            strategy=strategy.value,
            description=mutation.description,
        )
        return mutation

    def _apply_strategy(
        self,
        agent: BiasharaAgent,
        strategy: MutationStrategy,
        diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Apply a specific mutation strategy."""
        if strategy == MutationStrategy.ADJUST_CONFIDENCE:
            return self._adjust_confidence(agent, diagnosis)
        if strategy == MutationStrategy.ADD_CONTEXT:
            return self._add_context(agent, diagnosis)
        if strategy == MutationStrategy.REFINE_FILTERING:
            return self._refine_filtering(agent, diagnosis)
        if strategy == MutationStrategy.OPTIMIZE_PARAMETERS:
            return self._optimize_parameters(agent, diagnosis)
        if strategy == MutationStrategy.ADD_FALLBACK:
            return self._add_fallback(agent, diagnosis)
        if strategy == MutationStrategy.RESTRICT_SCOPE:
            return self._restrict_scope(agent, diagnosis)
        if strategy == MutationStrategy.EXPAND_CAPABILITY:
            return self._expand_capability(agent, diagnosis)

        return BehaviorMutation(
            description=f"No mutation for strategy: {strategy.value}",
            reasoning="Unknown strategy",
            strategy=strategy,
            parameter_changes={},
            expected_improvement="none",
        )

    def _adjust_confidence(
        self, agent: BiasharaAgent, diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Adjust confidence thresholds based on performance."""
        current = agent.memory.retrieve("adaptive_base_confidence", 0.8)
        # Lower confidence if too many failures
        new_confidence = max(0.5, current - 0.1)
        agent.memory.store("adaptive_base_confidence", new_confidence)

        return BehaviorMutation(
            description=f"Lowered confidence threshold from {current:.2f} to {new_confidence:.2f}",
            reasoning=diagnosis.root_cause,
            strategy=MutationStrategy.ADJUST_CONFIDENCE,
            parameter_changes={"confidence_threshold": new_confidence},
            expected_improvement="Fewer overconfident decisions, more cautious behavior",
        )

    def _add_context(
        self, agent: BiasharaAgent, diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Increase context window for better decisions."""
        current_window = agent.memory.retrieve("context_window_size", 10)
        new_window = min(50, current_window + 5)
        agent.memory.store("context_window_size", new_window)

        return BehaviorMutation(
            description=f"Increased context window from {current_window} to {new_window}",
            reasoning=diagnosis.root_cause,
            strategy=MutationStrategy.ADD_CONTEXT,
            parameter_changes={"context_window_size": new_window},
            expected_improvement="Better decisions with more historical context",
        )

    def _refine_filtering(
        self, agent: BiasharaAgent, diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Refine event filtering to reduce noise."""
        current_threshold = agent.memory.retrieve("event_relevance_threshold", 0.3)
        new_threshold = min(0.8, current_threshold + 0.1)
        agent.memory.store("event_relevance_threshold", new_threshold)

        return BehaviorMutation(
            description=f"Raised event relevance threshold from {current_threshold:.2f} to {new_threshold:.2f}",
            reasoning=diagnosis.root_cause,
            strategy=MutationStrategy.REFINE_FILTERING,
            parameter_changes={"event_relevance_threshold": new_threshold},
            expected_improvement="Less noise, more focused processing",
        )

    def _optimize_parameters(
        self, agent: BiasharaAgent, diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Optimize numeric parameters for performance."""
        current_timeout = agent.memory.retrieve("timeout_ms", 30000)
        new_timeout = max(5000, current_timeout - 5000)
        agent.memory.store("timeout_ms", new_timeout)

        return BehaviorMutation(
            description=f"Reduced timeout from {current_timeout}ms to {new_timeout}ms",
            reasoning=diagnosis.root_cause,
            strategy=MutationStrategy.OPTIMIZE_PARAMETERS,
            parameter_changes={"timeout_ms": new_timeout},
            expected_improvement="Faster failures, quicker recovery",
        )

    def _add_fallback(
        self, agent: BiasharaAgent, diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Add fallback behavior for common failure modes."""
        fallback_count = agent.memory.retrieve("fallback_count", 0)
        agent.memory.store("fallback_count", fallback_count + 1)
        agent.memory.store("last_fallback_reason", diagnosis.root_cause)

        return BehaviorMutation(
            description=f"Registered fallback for: {diagnosis.root_cause[:80]}",
            reasoning=diagnosis.root_cause,
            strategy=MutationStrategy.ADD_FALLBACK,
            parameter_changes={"fallback_count": fallback_count + 1},
            expected_improvement="Graceful degradation on common failures",
        )

    def _restrict_scope(
        self, agent: BiasharaAgent, diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Restrict agent scope to reduce costs."""
        current_max = agent.memory.retrieve("max_output_tokens", 1024)
        new_max = max(256, current_max - 128)
        agent.memory.store("max_output_tokens", new_max)

        return BehaviorMutation(
            description=f"Reduced max output tokens from {current_max} to {new_max}",
            reasoning=diagnosis.root_cause,
            strategy=MutationStrategy.RESTRICT_SCOPE,
            parameter_changes={"max_output_tokens": new_max},
            expected_improvement="Lower token costs with focused outputs",
        )

    def _expand_capability(
        self, agent: BiasharaAgent, diagnosis: FailureDiagnosis,
    ) -> BehaviorMutation:
        """Expand agent capability with new patterns."""
        patterns = agent.memory.retrieve("learned_patterns", [])
        new_pattern = {
            "pattern": diagnosis.root_cause,
            "strategy": diagnosis.mutation_strategy.value,
            "learned_at": time.time(),
        }
        patterns.append(new_pattern)
        agent.memory.store("learned_patterns", patterns[-20:])  # Keep last 20

        return BehaviorMutation(
            description=f"Learned new pattern: {diagnosis.root_cause[:60]}",
            reasoning=diagnosis.root_cause,
            strategy=MutationStrategy.EXPAND_CAPABILITY,
            parameter_changes={"learned_patterns_count": len(patterns)},
            expected_improvement="Better handling of similar situations in future",
        )


# ════════════════════════════════════════════════════════════════════
# SelfImprovingAgent — Wrapper Agent
# ════════════════════════════════════════════════════════════════════


class SelfImprovingAgent(BiasharaAgent):
    """
    Agent that monitors and improves other agents' performance.

    Subscribes to feedback events, diagnoses issues, and applies
    targeted mutations to improve agent behavior over time.

    Subscribes to: feedback.received, agent.performance.recorded
    Publishes: hermes.skill.improved, evolution.cycle.complete

    This agent wraps the FeedbackAnalyzer + SkillMutator pattern
    into the BiasharaAgent lifecycle for consistent integration.
    """

    def __init__(self, improvement_interval: float = 3600.0):
        super().__init__(
            name="SelfImprovingAgent",
            role="Agent performance monitoring and self-improvement",
            capabilities=[
                "feedback_collection",
                "failure_diagnosis",
                "behavior_mutation",
                "performance_tracking",
                "improvement_orchestration",
            ],
        )
        self._analyzer = FeedbackAnalyzer()
        self._mutator = SkillMutator()
        self._improvement_interval = improvement_interval
        self._cycle_count = 0
        self._improvement_history: list[ImprovementCycle] = []
        self._target_agents: dict[str, BiasharaAgent] = {}
        self._logger = logger.bind(agent="SelfImprovingAgent")

    def register_target(self, agent: BiasharaAgent) -> None:
        """Register an agent for monitoring and improvement."""
        self._target_agents[agent.name] = agent
        self._logger.info("target_registered", agent=agent.name)

    def record_feedback(self, signal: FeedbackSignal) -> None:
        """Record a feedback signal for analysis."""
        self._analyzer.record_feedback(signal)

    # ── BiasharaAgent lifecycle ─────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Observe feedback and performance events."""
        await super().observe(event)

        # Extract feedback from events
        if event.event_type == EventType.FEEDBACK_RECEIVED:
            payload = event.payload
            signal = FeedbackSignal(
                feedback_type=FeedbackType(payload.get("type", "user_rating")),
                agent_name=payload.get("agent_name", event.source),
                value=float(payload.get("value", 0.5)),
                context=payload.get("context", {}),
                source=event.source,
            )
            self._analyzer.record_feedback(signal)

        elif event.event_type == EventType.AGENT_PERFORMANCE_RECORDED:
            payload = event.payload
            # Record success rate feedback
            signal = FeedbackSignal(
                feedback_type=FeedbackType.SUCCESS_RATE,
                agent_name=payload.get("agent_name", event.source),
                value=1.0 if payload.get("success", False) else 0.0,
                context=payload,
                source=event.source,
            )
            self._analyzer.record_feedback(signal)

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Decide which agent to analyze and potentially improve.
        """
        # Find the agent with the most feedback data
        best_agent = None
        best_score = 1.0

        for agent_name in self._target_agents:
            summary = self._analyzer.get_feedback_summary(agent_name)
            if summary.get("signal_count", 0) >= 5:
                score = summary.get("overall_score", 1.0)
                if score < best_score:
                    best_score = score
                    best_agent = agent_name

        if best_agent and best_score < 0.8:
            return AgentDecision(
                action="improve_agent",
                parameters={"agent_name": best_agent, "current_score": best_score},
                confidence=0.9,
                reasoning=f"Agent {best_agent} has low score ({best_score:.2f}) — needs improvement.",
            )

        return AgentDecision(
            action="collect_feedback",
            parameters={},
            confidence=0.5,
            reasoning="No agents need improvement right now — collecting more feedback.",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute improvement or feedback collection."""
        start = time.time()

        if decision.action == "improve_agent":
            return await self._improve_agent(decision.parameters)

        if decision.action == "collect_feedback":
            return await self._collect_feedback(decision.parameters)

        return AgentResult(
            success=False,
            error=f"Unknown action: {decision.action}",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _improve_agent(self, params: dict) -> AgentResult:
        """Run one improvement cycle on a target agent."""
        start = time.time()
        agent_name = params.get("agent_name")
        current_score = params.get("current_score", 0.5)
        agent = self._target_agents.get(agent_name)

        if not agent:
            return AgentResult(
                success=False,
                error=f"Agent {agent_name} not registered",
                duration_ms=(time.time() - start) * 1000,
            )

        try:
            # 1. Diagnose
            recent_results = [
                m for m in agent.memory.recall_recent(20)
                if "success" in m
            ]
            diagnosis = self._analyzer.diagnose(agent_name, recent_results)

            if not diagnosis:
                return AgentResult(
                    success=True,
                    data={"status": "no_improvement_needed", "agent": agent_name},
                    duration_ms=(time.time() - start) * 1000,
                )

            # 2. Mutate
            mutation = self._mutator.mutate(agent, diagnosis)

            # 3. Record cycle
            self._cycle_count += 1
            cycle = ImprovementCycle(
                cycle_number=self._cycle_count,
                diagnosis=diagnosis,
                mutation=mutation,
                score_before=current_score,
                score_after=current_score,  # Will be updated after re-evaluation
                kept=True,  # Optimistically kept until proven otherwise
                duration_ms=(time.time() - start) * 1000,
            )
            self._improvement_history.append(cycle)

            # 4. Emit improvement event
            events_to_publish = [
                AgentEvent(
                    event_type=EventType.HERMES_SKILL_IMPROVED,
                    source=self.name,
                    payload={
                        "agent_name": agent_name,
                        "diagnosis": diagnosis.to_dict(),
                        "mutation": mutation.to_dict(),
                        "cycle_number": self._cycle_count,
                    },
                ),
                AgentEvent(
                    event_type=EventType.EVOLUTION_CYCLE_COMPLETE,
                    source=self.name,
                    payload={
                        "cycle": self._cycle_count,
                        "agent": agent_name,
                        "strategy": mutation.strategy.value,
                        "score_before": current_score,
                    },
                ),
            ]

            self._logger.info(
                "improvement_cycle_complete",
                agent=agent_name,
                cycle=self._cycle_count,
                strategy=mutation.strategy.value,
                diagnosis=diagnosis.root_cause[:80],
            )

            return AgentResult(
                success=True,
                data={
                    "cycle": cycle.to_dict(),
                    "agent": agent_name,
                },
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            self._logger.error("improvement_cycle_failed", agent=agent_name, error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _collect_feedback(self, params: dict) -> AgentResult:
        """Collect and aggregate feedback — no mutation needed."""
        summaries = {}
        for agent_name in self._target_agents:
            summary = self._analyzer.get_feedback_summary(agent_name)
            if summary.get("signal_count", 0) > 0:
                summaries[agent_name] = summary

        return AgentResult(
            success=True,
            data={
                "status": "collecting",
                "summaries": summaries,
                "cycle_count": self._cycle_count,
            },
            duration_ms=0,
        )

    def get_improvement_history(self, limit: int = 20) -> list[dict]:
        """Return recent improvement cycles."""
        return [c.to_dict() for c in self._improvement_history[-limit:]]

    def get_agent_health_report(self) -> dict[str, Any]:
        """Generate a health report for all monitored agents."""
        report = {}
        for agent_name in self._target_agents:
            summary = self._analyzer.get_feedback_summary(agent_name)
            mutations = [
                m for m in self._mutator._mutation_history
                if agent_name.lower() in m.description.lower()
            ]
            report[agent_name] = {
                "feedback_summary": summary,
                "mutations_applied": len(mutations),
                "recent_mutations": [m.to_dict() for m in mutations[-3:]],
            }
        return report
