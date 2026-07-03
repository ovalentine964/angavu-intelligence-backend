"""
Agent Learning System — Continuous Performance Improvement.

Tracks agent performance over time, identifies patterns in failures,
auto-adjusts prompts/strategies based on results, and provides
continuous improvement metrics.

Architecture:
    ┌───────────────────────────────────────────┐
    │           LearningSystem                   │
    │                                            │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
    │  │Performance│  │ Failure  │  │ Prompt   │ │
    │  │ Tracker  │  │ Analyzer │  │Optimizer │ │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
    │       │              │              │       │
    │  ┌────▼──────────────▼──────────────▼────┐ │
    │  │         Learning Metrics Store         │ │
    │  └───────────────────────────────────────┘ │
    └───────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════


class MetricType(str, Enum):
    """Types of metrics tracked by the learning system."""
    SUCCESS_RATE = "success_rate"
    DURATION_MS = "duration_ms"
    QUALITY_SCORE = "quality_score"
    ERROR_COUNT = "error_count"
    REFLEXION_IMPROVEMENT = "reflexion_improvement"
    CUSTOMER_SATISFACTION = "customer_satisfaction"
    CONTENT_QUALITY = "content_quality"
    REVENUE_IMPACT = "revenue_impact"


class PatternType(str, Enum):
    """Types of patterns detected in agent behavior."""
    RECURRING_ERROR = "recurring_error"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    IMPROVEMENT_OPPORTUNITY = "improvement_opportunity"
    CONSISTENT_FAILURE = "consistent_failure"
    RAPID_IMPROVEMENT = "rapid_improvement"


@dataclass
class PerformanceRecord:
    """A single performance measurement."""
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    task_name: str = ""
    metric_type: MetricType = MetricType.SUCCESS_RATE
    value: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "agent_name": self.agent_name,
            "task_name": self.task_name,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class DetectedPattern:
    """A pattern detected in agent performance data."""
    pattern_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    pattern_type: PatternType = PatternType.RECURRING_ERROR
    agent_name: str = ""
    description: str = ""
    confidence: float = 0.0
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "agent_name": self.agent_name,
            "description": self.description,
            "confidence": self.confidence,
            "evidence_count": len(self.evidence),
            "recommendation": self.recommendation,
            "detected_at": self.detected_at,
        }


@dataclass
class PromptAdjustment:
    """A suggested or applied adjustment to an agent's prompt/strategy."""
    adjustment_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = ""
    adjustment_type: str = ""  # "prompt_injection", "parameter_change", "strategy_shift"
    description: str = ""
    old_value: Any = None
    new_value: Any = None
    reason: str = ""
    applied: bool = False
    applied_at: Optional[float] = None
    impact_score: Optional[float] = None  # Measured after application

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adjustment_id": self.adjustment_id,
            "agent_name": self.agent_name,
            "adjustment_type": self.adjustment_type,
            "description": self.description,
            "reason": self.reason,
            "applied": self.applied,
            "applied_at": self.applied_at,
            "impact_score": self.impact_score,
        }


@dataclass
class AgentLearningProfile:
    """Aggregated learning profile for a single agent."""
    agent_name: str = ""
    total_executions: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_quality_score: float = 0.0
    avg_duration_ms: float = 0.0
    recent_success_rate: float = 0.0  # Last 20 executions
    trend: str = "stable"  # "improving", "degrading", "stable"
    patterns: List[DetectedPattern] = field(default_factory=list)
    adjustments: List[PromptAdjustment] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.total_successes / self.total_executions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_executions": self.total_executions,
            "success_rate": self.success_rate,
            "avg_quality_score": self.avg_quality_score,
            "avg_duration_ms": self.avg_duration_ms,
            "recent_success_rate": self.recent_success_rate,
            "trend": self.trend,
            "active_patterns": len(self.patterns),
            "applied_adjustments": sum(1 for a in self.adjustments if a.applied),
            "last_updated": self.last_updated,
        }


# ════════════════════════════════════════════════════════════════════
# Performance Tracker
# ════════════════════════════════════════════════════════════════════


class PerformanceTracker:
    """
    Tracks agent performance metrics over time.

    Stores records in memory with optional disk persistence.
    Provides aggregation and trend analysis.
    """

    def __init__(self, persist_path: Optional[str] = None, max_records: int = 10_000):
        self._records: List[PerformanceRecord] = []
        self._persist_path = persist_path
        self._max_records = max_records
        self._logger = logger.bind(component="performance_tracker")

    def record(
        self,
        agent_name: str,
        task_name: str,
        metric_type: MetricType,
        value: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PerformanceRecord:
        """Record a performance measurement."""
        rec = PerformanceRecord(
            agent_name=agent_name,
            task_name=task_name,
            metric_type=metric_type,
            value=value,
            metadata=metadata or {},
        )
        self._records.append(rec)

        # Trim
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

        self._logger.debug(
            "performance_recorded",
            agent=agent_name,
            metric=metric_type.value,
            value=value,
        )
        return rec

    def get_records(
        self,
        agent_name: Optional[str] = None,
        metric_type: Optional[MetricType] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[PerformanceRecord]:
        """Query performance records with filters."""
        results = self._records
        if agent_name:
            results = [r for r in results if r.agent_name == agent_name]
        if metric_type:
            results = [r for r in results if r.metric_type == metric_type]
        if since:
            results = [r for r in results if r.timestamp >= since]
        return results[-limit:]

    def get_agent_stats(self, agent_name: str) -> Dict[str, Any]:
        """Get aggregated stats for an agent."""
        records = [r for r in self._records if r.agent_name == agent_name]
        if not records:
            return {"agent_name": agent_name, "record_count": 0}

        by_metric: Dict[str, List[float]] = defaultdict(list)
        for r in records:
            by_metric[r.metric_type.value].append(r.value)

        stats: Dict[str, Any] = {
            "agent_name": agent_name,
            "record_count": len(records),
        }
        for metric, values in by_metric.items():
            stats[metric] = {
                "count": len(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "min": min(values),
                "max": max(values),
            }
        return stats

    def get_trend(
        self,
        agent_name: str,
        metric_type: MetricType,
        window: int = 20,
    ) -> str:
        """
        Determine the trend for a metric.

        Returns: "improving", "degrading", or "stable"
        """
        records = [
            r for r in self._records
            if r.agent_name == agent_name and r.metric_type == metric_type
        ]
        if len(records) < 4:
            return "stable"

        recent = records[-window:]
        values = [r.value for r in recent]

        # Split into halves and compare
        mid = len(values) // 2
        first_half = statistics.mean(values[:mid])
        second_half = statistics.mean(values[mid:])

        diff = second_half - first_half
        if abs(diff) < 0.05:
            return "stable"
        return "improving" if diff > 0 else "degrading"


# ════════════════════════════════════════════════════════════════════
# Failure Analyzer
# ════════════════════════════════════════════════════════════════════


class FailureAnalyzer:
    """
    Analyzes failure patterns in agent execution.

    Identifies:
    - Recurring error messages
    - Failure clustering by task type
    - Temporal patterns (failures at specific times)
    - Cascading failures across agents
    """

    def __init__(self):
        self._errors: List[Dict[str, Any]] = []
        self._max_errors = 5000
        self._logger = logger.bind(component="failure_analyzer")

    def record_error(
        self,
        agent_name: str,
        task_name: str,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an error for pattern analysis."""
        self._errors.append({
            "agent_name": agent_name,
            "task_name": task_name,
            "error": error,
            "error_hash": hash(error) % 10**8,
            "timestamp": time.time(),
            "metadata": metadata or {},
        })
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]

    def analyze(self, agent_name: Optional[str] = None) -> List[DetectedPattern]:
        """
        Analyze errors and detect patterns.

        Returns a list of detected patterns sorted by confidence.
        """
        errors = self._errors
        if agent_name:
            errors = [e for e in errors if e["agent_name"] == agent_name]

        patterns: List[DetectedPattern] = []

        # 1. Recurring errors (same error hash appearing 3+ times)
        patterns.extend(self._find_recurring_errors(errors))

        # 2. High failure rate tasks
        patterns.extend(self._find_high_failure_tasks(errors))

        # 3. Recent degradation
        patterns.extend(self._detect_degradation(errors))

        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns

    def _find_recurring_errors(self, errors: List[Dict]) -> List[DetectedPattern]:
        """Find errors that recur frequently."""
        patterns = []
        hash_counts: Dict[int, List[Dict]] = defaultdict(list)
        for e in errors:
            hash_counts[e["error_hash"]].append(e)

        for error_hash, occurrences in hash_counts.items():
            if len(occurrences) >= 3:
                # Group by agent
                by_agent: Dict[str, int] = defaultdict(int)
                for o in occurrences:
                    by_agent[o["agent_name"]] += 1

                for agent, count in by_agent.items():
                    if count >= 2:
                        patterns.append(DetectedPattern(
                            pattern_type=PatternType.RECURRING_ERROR,
                            agent_name=agent,
                            description=f"Recurring error ({count}x): {occurrences[0]['error'][:100]}",
                            confidence=min(0.95, 0.5 + count * 0.1),
                            evidence=occurrences[-5:],
                            recommendation=f"Investigate root cause of recurring error in {agent}",
                        ))
        return patterns

    def _find_high_failure_tasks(self, errors: List[Dict]) -> List[DetectedPattern]:
        """Find tasks with abnormally high failure rates."""
        patterns = []
        task_attempts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "errors": 0})

        for e in errors:
            key = f"{e['agent_name']}:{e['task_name']}"
            task_attempts[key]["errors"] += 1

        for key, counts in task_attempts.items():
            if counts["errors"] >= 5:
                agent, task = key.split(":", 1)
                patterns.append(DetectedPattern(
                    pattern_type=PatternType.CONSISTENT_FAILURE,
                    agent_name=agent,
                    description=f"Task '{task}' has {counts['errors']} failures",
                    confidence=min(0.9, 0.4 + counts["errors"] * 0.05),
                    recommendation=f"Review task '{task}' implementation or input validation",
                ))
        return patterns

    def _detect_degradation(self, errors: List[Dict]) -> List[DetectedPattern]:
        """Detect if error rate is increasing over time."""
        patterns = []
        if len(errors) < 10:
            return patterns

        now = time.time()
        recent_window = 3600  # 1 hour
        older_window = 7200   # 2 hours

        recent_errors = [e for e in errors if now - e["timestamp"] < recent_window]
        older_errors = [e for e in errors if recent_window <= now - e["timestamp"] < older_window]

        if len(older_errors) > 0:
            recent_rate = len(recent_errors) / max(1, recent_window / 60)
            older_rate = len(older_errors) / max(1, older_window / 60)

            if recent_rate > older_rate * 1.5 and len(recent_errors) >= 3:
                # Group by agent
                by_agent: Dict[str, int] = defaultdict(int)
                for e in recent_errors:
                    by_agent[e["agent_name"]] += 1

                for agent, count in by_agent.items():
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.PERFORMANCE_DEGRADATION,
                        agent_name=agent,
                        description=f"Error rate increasing: {count} errors in last hour",
                        confidence=0.7,
                        recommendation=f"Check {agent} for recent changes or data quality issues",
                    ))
        return patterns


# ════════════════════════════════════════════════════════════════════
# Prompt Optimizer
# ════════════════════════════════════════════════════════════════════


class PromptOptimizer:
    """
    Auto-adjusts agent prompts and strategies based on performance data.

    Generates PromptAdjustment recommendations based on:
    - Low success rate → add error-handling instructions
    - Slow execution → suggest scope reduction
    - Quality issues → inject quality criteria
    - Pattern-detected issues → add specific mitigations
    """

    def __init__(self):
        self._adjustments: List[PromptAdjustment] = []
        self._logger = logger.bind(component="prompt_optimizer")

    def generate_adjustments(
        self,
        profile: AgentLearningProfile,
        patterns: List[DetectedPattern],
    ) -> List[PromptAdjustment]:
        """
        Generate prompt/strategy adjustments based on learning data.

        Returns a list of recommended adjustments (not yet applied).
        """
        adjustments: List[PromptAdjustment] = []

        # 1. Low success rate → error handling prompt
        if profile.success_rate < 0.6 and profile.total_executions >= 5:
            adjustments.append(PromptAdjustment(
                agent_name=profile.agent_name,
                adjustment_type="prompt_injection",
                description="Add error-handling instructions to agent prompt",
                old_value=None,
                new_value=(
                    "IMPORTANT: When encountering errors, log the full context "
                    "and attempt an alternative approach before failing. "
                    "Check input data quality before processing."
                ),
                reason=f"Success rate is {profile.success_rate:.0%} (threshold: 60%)",
            ))

        # 2. Slow execution → scope suggestion
        if profile.avg_duration_ms > 15000:
            adjustments.append(PromptAdjustment(
                agent_name=profile.agent_name,
                adjustment_type="parameter_change",
                description="Reduce processing scope to improve speed",
                old_value=profile.avg_duration_ms,
                new_value=profile.avg_duration_ms * 0.7,
                reason=f"Average duration {profile.avg_duration_ms:.0f}ms exceeds 15s threshold",
            ))

        # 3. Quality score issues
        if profile.avg_quality_score < 0.7 and profile.avg_quality_score > 0:
            adjustments.append(PromptAdjustment(
                agent_name=profile.agent_name,
                adjustment_type="prompt_injection",
                description="Add quality criteria to agent prompt",
                new_value=(
                    "Quality checklist: Verify completeness, accuracy, "
                    "formatting, and relevance before returning results. "
                    "Self-score each dimension 0-1."
                ),
                reason=f"Average quality score {profile.avg_quality_score:.2f} below 0.7",
            ))

        # 4. Pattern-based adjustments
        for pattern in patterns:
            if pattern.pattern_type == PatternType.RECURRING_ERROR:
                adjustments.append(PromptAdjustment(
                    agent_name=profile.agent_name,
                    adjustment_type="strategy_shift",
                    description=f"Mitigate recurring pattern: {pattern.description[:80]}",
                    reason=pattern.recommendation,
                ))

        self._logger.info(
            "adjustments_generated",
            agent=profile.agent_name,
            count=len(adjustments),
        )
        return adjustments

    def record_adjustment(self, adjustment: PromptAdjustment) -> None:
        """Record an adjustment for tracking."""
        self._adjustments.append(adjustment)

    def get_adjustments(
        self,
        agent_name: Optional[str] = None,
        applied_only: bool = False,
    ) -> List[PromptAdjustment]:
        """Get adjustments with optional filters."""
        results = self._adjustments
        if agent_name:
            results = [a for a in results if a.agent_name == agent_name]
        if applied_only:
            results = [a for a in results if a.applied]
        return results


# ════════════════════════════════════════════════════════════════════
# Learning System (Main Entry Point)
# ════════════════════════════════════════════════════════════════════


class LearningSystem:
    """
    Central learning system that ties together performance tracking,
    failure analysis, and prompt optimization.

    Usage:
        learning = LearningSystem()

        # Record outcomes
        learning.record_success("ContentAgent", "generate_post", 0.85, 2500)
        learning.record_failure("ContentAgent", "generate_post", "API timeout")

        # Get insights
        profile = learning.get_profile("ContentAgent")
        patterns = learning.detect_patterns("ContentAgent")
        adjustments = learning.suggest_adjustments("ContentAgent")
    """

    def __init__(self, event_bus: Any = None):
        self.tracker = PerformanceTracker()
        self.analyzer = FailureAnalyzer()
        self.optimizer = PromptOptimizer()
        self._event_bus = event_bus
        self._profiles: Dict[str, AgentLearningProfile] = {}
        self._logger = logger.bind(component="learning_system")

    def record_success(
        self,
        agent_name: str,
        task_name: str,
        quality_score: float = 1.0,
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a successful execution."""
        self.tracker.record(
            agent_name, task_name, MetricType.SUCCESS_RATE, 1.0, metadata,
        )
        self.tracker.record(
            agent_name, task_name, MetricType.QUALITY_SCORE, quality_score, metadata,
        )
        if duration_ms > 0:
            self.tracker.record(
                agent_name, task_name, MetricType.DURATION_MS, duration_ms, metadata,
            )
        self._update_profile(agent_name)

    def record_failure(
        self,
        agent_name: str,
        task_name: str,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a failed execution."""
        self.tracker.record(
            agent_name, task_name, MetricType.SUCCESS_RATE, 0.0, metadata,
        )
        self.analyzer.record_error(agent_name, task_name, error, metadata)
        self._update_profile(agent_name)

    def record_metric(
        self,
        agent_name: str,
        task_name: str,
        metric_type: MetricType,
        value: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a custom metric."""
        self.tracker.record(agent_name, task_name, metric_type, value, metadata)
        self._update_profile(agent_name)

    def get_profile(self, agent_name: str) -> AgentLearningProfile:
        """Get the learning profile for an agent."""
        if agent_name not in self._profiles:
            self._update_profile(agent_name)
        return self._profiles.get(agent_name, AgentLearningProfile(agent_name=agent_name))

    def detect_patterns(self, agent_name: Optional[str] = None) -> List[DetectedPattern]:
        """Detect patterns in agent performance."""
        return self.analyzer.analyze(agent_name)

    def suggest_adjustments(self, agent_name: str) -> List[PromptAdjustment]:
        """Suggest prompt/strategy adjustments for an agent."""
        profile = self.get_profile(agent_name)
        patterns = self.detect_patterns(agent_name)
        return self.optimizer.generate_adjustments(profile, patterns)

    def get_all_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Get all agent profiles."""
        # Refresh all profiles
        agent_names = set(r.agent_name for r in self.tracker._records)
        for name in agent_names:
            self._update_profile(name)
        return {name: p.to_dict() for name, p in self._profiles.items()}

    def get_system_stats(self) -> Dict[str, Any]:
        """Get system-wide learning statistics."""
        all_patterns = self.detect_patterns()
        return {
            "total_records": len(self.tracker._records),
            "total_errors": len(self.analyzer._errors),
            "agent_count": len(self._profiles),
            "detected_patterns": len(all_patterns),
            "pattern_breakdown": {
                pt.value: sum(1 for p in all_patterns if p.pattern_type == pt)
                for pt in PatternType
            },
            "profiles": {
                name: p.to_dict() for name, p in self._profiles.items()
            },
        }

    def _update_profile(self, agent_name: str) -> None:
        """Refresh the learning profile for an agent."""
        stats = self.tracker.get_agent_stats(agent_name)

        profile = AgentLearningProfile(agent_name=agent_name)

        sr_stats = stats.get("success_rate", {})
        if sr_stats:
            sr_count = sr_stats.get("count", 0)
            profile.total_executions = sr_count
            profile.total_successes = int(sr_stats.get("mean", 0) * sr_count)
            profile.total_failures = sr_count - profile.total_successes

        qs_stats = stats.get("quality_score", {})
        if qs_stats:
            profile.avg_quality_score = qs_stats.get("mean", 0.0)

        dur_stats = stats.get("duration_ms", {})
        if dur_stats:
            profile.avg_duration_ms = dur_stats.get("mean", 0.0)

        # Recent success rate
        recent = self.tracker.get_records(
            agent_name=agent_name,
            metric_type=MetricType.SUCCESS_RATE,
            limit=20,
        )
        if recent:
            profile.recent_success_rate = statistics.mean(r.value for r in recent)

        # Trend
        profile.trend = self.tracker.get_trend(
            agent_name, MetricType.SUCCESS_RATE,
        )

        # Patterns
        profile.patterns = self.detect_patterns(agent_name)

        profile.last_updated = time.time()
        self._profiles[agent_name] = profile
