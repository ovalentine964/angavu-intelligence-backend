"""
Reflexion Pattern — Self-Improving Agent Loop for Angavu Intelligence.

Implements the Reflexion pattern (Shinn et al., 2023) where agents:
    1. Execute a task
    2. Reflect on the result (self-critique)
    3. Identify improvements
    4. Apply improvements in the next iteration
    5. Loop until quality threshold or max iterations

This module provides the core ReflexionEngine that any autonomous
agent can use to wrap its execution with self-improvement loops.

Architecture:
    ┌──────────────┐
    │  Task Input   │
    └──────┬───────┘
           ▼
    ┌──────────────┐     ┌──────────────┐
    │   Execute     │────▶│   Critique   │
    └──────┬───────┘     └──────┬───────┘
           │                    │
           │    ┌───────────────┘
           ▼    ▼
    ┌──────────────┐     ┌──────────────┐
    │  Score < τ?  │─Yes─▶│   Revise     │
    └──────┬───────┘     └──────┬───────┘
           │ No                 │
           ▼                    │
    ┌──────────────┐            │
    │   Accept     │◀───────────┘
    └──────────────┘     (loop back to Execute)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


# ════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════


class ReflexionStatus(str, Enum):
    """Status of a Reflexion loop execution."""
    PENDING = "pending"
    EXECUTING = "executing"
    CRITIQUING = "critiquing"
    REVISING = "revising"
    ACCEPTED = "accepted"
    MAX_RETRIES = "max_retries"
    FAILED = "failed"


@dataclass
class ReflexionAttempt:
    """A single attempt in the Reflexion loop."""
    attempt_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    attempt_number: int = 0
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    # Execution
    execution_result: Any = None
    execution_success: bool = False
    execution_duration_ms: float = 0.0
    execution_error: str | None = None

    # Critique
    critique_score: float = 0.0
    critique_issues: list[str] = field(default_factory=list)
    critique_suggestions: list[str] = field(default_factory=list)

    # Revision
    revision_plan: str = ""
    revision_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "attempt_number": self.attempt_number,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "execution_success": self.execution_success,
            "execution_duration_ms": self.execution_duration_ms,
            "execution_error": self.execution_error,
            "critique_score": self.critique_score,
            "critique_issues": self.critique_issues,
            "critique_suggestions": self.critique_suggestions,
            "revision_plan": self.revision_plan,
            "revision_applied": self.revision_applied,
        }


@dataclass
class ReflexionResult:
    """Final result of a Reflexion loop execution."""
    loop_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    task_name: str = ""
    status: ReflexionStatus = ReflexionStatus.PENDING
    attempts: list[ReflexionAttempt] = field(default_factory=list)
    final_result: Any = None
    final_score: float = 0.0
    total_duration_ms: float = 0.0
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def best_score(self) -> float:
        if not self.attempts:
            return 0.0
        return max(a.critique_score for a in self.attempts)

    @property
    def improvement_delta(self) -> float:
        """Score improvement from first to last attempt."""
        if len(self.attempts) < 2:
            return 0.0
        return self.attempts[-1].critique_score - self.attempts[0].critique_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "task_name": self.task_name,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "attempts": [a.to_dict() for a in self.attempts],
            "final_score": self.final_score,
            "best_score": self.best_score,
            "improvement_delta": self.improvement_delta,
            "total_duration_ms": self.total_duration_ms,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


@dataclass
class ReflexionConfig:
    """Configuration for a Reflexion loop."""
    quality_threshold: float = 0.7       # Minimum acceptable score
    max_attempts: int = 3                # Maximum retry attempts
    improvement_threshold: float = 0.05  # Minimum score improvement to continue
    timeout_seconds: float = 300.0       # Max total loop time
    persist_attempts: bool = True        # Store attempt history
    emit_events: bool = True             # Publish events to EventBus


# ════════════════════════════════════════════════════════════════════
# Protocols (Dependency Injection)
# ════════════════════════════════════════════════════════════════════


class Executor(Protocol):
    """Protocol for task execution."""
    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a task and return result dict with 'success' key."""
        ...


class Critic(Protocol):
    """Protocol for self-critique evaluation."""
    async def critique(
        self,
        task: dict[str, Any],
        result: dict[str, Any],
        attempt_number: int,
    ) -> dict[str, Any]:
        """Evaluate result quality. Must return dict with 'score' (0-1), 'issues', 'suggestions'."""
        ...


class Reviser(Protocol):
    """Protocol for revision strategy."""
    async def revise(
        self,
        task: dict[str, Any],
        critique: dict[str, Any],
        previous_attempts: list[ReflexionAttempt],
    ) -> dict[str, Any]:
        """Create a revised task/context based on critique. Returns revised task dict."""
        ...


# ════════════════════════════════════════════════════════════════════
# Reflexion Engine
# ════════════════════════════════════════════════════════════════════


class ReflexionEngine:
    """
    Core Reflexion loop engine for self-improving agents.

    Wraps any task execution with the Reflexion pattern:
    execute → critique → revise → execute → ... → accept

    Usage:
        engine = ReflexionEngine(
            executor=my_executor,
            critic=my_critic,
            reviser=my_reviser,
            config=ReflexionConfig(quality_threshold=0.8),
        )
        result = await engine.run(task={"type": "generate_report", ...})

    The engine is agnostic to the task domain — it only orchestrates
    the execute-critique-revise loop. Domain logic lives in the
    executor, critic, and reviser implementations.
    """

    def __init__(
        self,
        executor: Executor,
        critic: Critic,
        reviser: Reviser | None = None,
        config: ReflexionConfig | None = None,
        event_bus: Any = None,
    ):
        self._executor = executor
        self._critic = critic
        self._reviser = reviser
        self._config = config or ReflexionConfig()
        self._event_bus = event_bus
        self._logger = logger.bind(component="reflexion_engine")

        # History for analytics
        self._loop_history: list[ReflexionResult] = []
        self._max_history = 100

    async def run(
        self,
        task: dict[str, Any],
        task_name: str = "unnamed",
    ) -> ReflexionResult:
        """
        Execute the Reflexion loop.

        Args:
            task: The task to execute (passed to executor.execute())
            task_name: Human-readable name for tracking

        Returns:
            ReflexionResult with full attempt history and final outcome
        """
        result = ReflexionResult(
            task_name=task_name,
            status=ReflexionStatus.EXECUTING,
        )
        current_task = dict(task)
        loop_start = time.time()

        self._logger.info(
            "reflexion_loop_started",
            task_name=task_name,
            threshold=self._config.quality_threshold,
            max_attempts=self._config.max_attempts,
        )

        for attempt_num in range(1, self._config.max_attempts + 1):
            # Check timeout
            elapsed = (time.time() - loop_start) * 1000
            if elapsed > self._config.timeout_seconds * 1000:
                self._logger.warning("reflexion_timeout", elapsed_ms=elapsed)
                result.status = ReflexionStatus.FAILED
                break

            attempt = ReflexionAttempt(attempt_number=attempt_num)

            # ── Execute ──────────────────────────────────────────────
            self._logger.debug("reflexion_executing", attempt=attempt_num)
            exec_start = time.time()

            try:
                exec_result = await self._executor.execute(
                    current_task,
                    context={
                        "attempt_number": attempt_num,
                        "previous_attempts": [a.to_dict() for a in result.attempts],
                    },
                )
                attempt.execution_result = exec_result
                attempt.execution_success = exec_result.get("success", False)
                attempt.execution_error = exec_result.get("error")
            except Exception as exc:
                attempt.execution_success = False
                attempt.execution_error = str(exc)
                self._logger.warning(
                    "reflexion_execution_error",
                    attempt=attempt_num,
                    error=str(exc),
                )

            attempt.execution_duration_ms = (time.time() - exec_start) * 1000

            # ── Critique ─────────────────────────────────────────────
            result.status = ReflexionStatus.CRITIQUING
            self._logger.debug("reflexion_critiquing", attempt=attempt_num)

            try:
                critique_result = await self._critic.critique(
                    current_task,
                    attempt.execution_result or {"success": False, "error": attempt.execution_error},
                    attempt_num,
                )
                attempt.critique_score = critique_result.get("score", 0.0)
                attempt.critique_issues = critique_result.get("issues", [])
                attempt.critique_suggestions = critique_result.get("suggestions", [])
            except Exception as exc:
                attempt.critique_score = 0.0
                attempt.critique_issues = [f"Critique failed: {exc}"]
                self._logger.warning("reflexion_critique_error", error=str(exc))

            attempt.ended_at = time.time()
            result.attempts.append(attempt)

            self._logger.info(
                "reflexion_attempt_complete",
                attempt=attempt_num,
                score=attempt.critique_score,
                success=attempt.execution_success,
                issues_count=len(attempt.critique_issues),
            )

            # ── Check acceptance ─────────────────────────────────────
            if attempt.critique_score >= self._config.quality_threshold:
                result.status = ReflexionStatus.ACCEPTED
                result.final_result = attempt.execution_result
                result.final_score = attempt.critique_score
                self._logger.info(
                    "reflexion_accepted",
                    attempt=attempt_num,
                    score=attempt.critique_score,
                )
                break

            # ── Check if improvement is possible ─────────────────────
            if attempt_num > 1:
                prev_score = result.attempts[-2].critique_score
                improvement = attempt.critique_score - prev_score
                if improvement < self._config.improvement_threshold and attempt_num >= 2:
                    self._logger.info(
                        "reflexion_no_improvement",
                        improvement=improvement,
                        threshold=self._config.improvement_threshold,
                    )
                    # Still continue if we haven't hit max attempts —
                    # the reviser might find a different approach

            # ── Revise ───────────────────────────────────────────────
            if attempt_num < self._config.max_attempts:
                result.status = ReflexionStatus.REVISING
                if self._reviser:
                    try:
                        revision = await self._reviser.revise(
                            current_task,
                            {
                                "score": attempt.critique_score,
                                "issues": attempt.critique_issues,
                                "suggestions": attempt.critique_suggestions,
                            },
                            result.attempts,
                        )
                        current_task = revision.get("revised_task", current_task)
                        attempt.revision_plan = revision.get("plan", "")
                        attempt.revision_applied = True
                        self._logger.debug(
                            "reflexion_revised",
                            attempt=attempt_num,
                            plan=attempt.revision_plan,
                        )
                    except Exception as exc:
                        self._logger.warning("reflexion_revision_error", error=str(exc))
                else:
                    # No reviser — inject critique as context for next attempt
                    current_task["_reflexion_feedback"] = {
                        "attempt": attempt_num,
                        "score": attempt.critique_score,
                        "issues": attempt.critique_issues,
                        "suggestions": attempt.critique_suggestions,
                    }
                    attempt.revision_plan = "Auto-injected critique as context"
                    attempt.revision_applied = True

        # ── Finalize ─────────────────────────────────────────────────
        if result.status not in (ReflexionStatus.ACCEPTED, ReflexionStatus.FAILED):
            result.status = ReflexionStatus.MAX_RETRIES
            # Use best attempt's result
            best = max(result.attempts, key=lambda a: a.critique_score)
            result.final_result = best.execution_result
            result.final_score = best.critique_score

        result.ended_at = time.time()
        result.total_duration_ms = (result.ended_at - result.started_at) * 1000

        # Store in history
        self._loop_history.append(result)
        if len(self._loop_history) > self._max_history:
            self._loop_history = self._loop_history[-self._max_history:]

        # Emit event
        if self._config.emit_events and self._event_bus:
            await self._emit_result_event(result)

        self._logger.info(
            "reflexion_loop_complete",
            task_name=task_name,
            status=result.status.value,
            attempts=result.attempt_count,
            final_score=result.final_score,
            improvement_delta=result.improvement_delta,
            total_ms=result.total_duration_ms,
        )

        return result

    async def _emit_result_event(self, result: ReflexionResult) -> None:
        """Publish Reflexion result to the EventBus."""
        try:
            from app.agents.base import AgentEvent, EventType

            event = AgentEvent(
                event_type=EventType.FEEDBACK_RECEIVED,
                source="ReflexionEngine",
                payload={
                    "loop_id": result.loop_id,
                    "task_name": result.task_name,
                    "status": result.status.value,
                    "attempts": result.attempt_count,
                    "final_score": result.final_score,
                    "improvement_delta": result.improvement_delta,
                    "total_duration_ms": result.total_duration_ms,
                },
            )
            await self._event_bus.publish(event)
        except Exception as exc:
            self._logger.debug("reflexion_event_emit_failed", error=str(exc))

    # ── Analytics ───────────────────────────────────────────────────

    def get_history(self, n: int = 10) -> list[dict[str, Any]]:
        """Get recent Reflexion loop results."""
        return [r.to_dict() for r in self._loop_history[-n:]]

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate Reflexion statistics."""
        if not self._loop_history:
            return {"total_loops": 0}

        scores = [r.final_score for r in self._loop_history]
        deltas = [r.improvement_delta for r in self._loop_history]
        attempts = [r.attempt_count for r in self._loop_history]

        return {
            "total_loops": len(self._loop_history),
            "avg_final_score": sum(scores) / len(scores),
            "avg_improvement_delta": sum(deltas) / len(deltas),
            "avg_attempts": sum(attempts) / len(attempts),
            "accepted_count": sum(
                1 for r in self._loop_history
                if r.status == ReflexionStatus.ACCEPTED
            ),
            "max_retries_count": sum(
                1 for r in self._loop_history
                if r.status == ReflexionStatus.MAX_RETRIES
            ),
            "best_score_ever": max(scores),
            "worst_score_ever": min(scores),
        }


# ════════════════════════════════════════════════════════════════════
# Default Implementations
# ════════════════════════════════════════════════════════════════════


class HeuristicCritic:
    """
    Default critic using heuristic rules.

    Evaluates results based on:
    - Execution success/failure
    - Execution time
    - Error patterns
    - Recent failure rate
    """

    async def critique(
        self,
        task: dict[str, Any],
        result: dict[str, Any],
        attempt_number: int,
    ) -> dict[str, Any]:
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        if not result.get("success", False):
            score -= 0.5
            error = result.get("error", "unknown error")
            issues.append(f"Execution failed: {error}")
            suggestions.append("Review error context and adjust parameters")

        duration_ms = result.get("duration_ms", 0)
        if duration_ms > 10000:
            score -= 0.15
            issues.append(f"Slow execution: {duration_ms:.0f}ms")
            suggestions.append("Optimize execution path or reduce scope")

        if not result.get("data"):
            score -= 0.1
            issues.append("No data returned")
            suggestions.append("Ensure execution produces meaningful output")

        # Penalize repeated attempts
        if attempt_number > 1:
            score -= 0.05 * (attempt_number - 1)
            suggestions.append("Consider alternative approach")

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }


class AdaptiveReviser:
    """
    Default reviser that adapts the task based on critique history.

    Injects critique feedback and adjusts task parameters.
    """

    async def revise(
        self,
        task: dict[str, Any],
        critique: dict[str, Any],
        previous_attempts: list[ReflexionAttempt],
    ) -> dict[str, Any]:
        revised_task = dict(task)

        # Inject critique as context
        revised_task["_reflexion_context"] = {
            "current_score": critique.get("score", 0),
            "issues": critique.get("issues", []),
            "suggestions": critique.get("suggestions", []),
            "attempt_count": len(previous_attempts),
            "score_trajectory": [a.critique_score for a in previous_attempts],
        }

        # Build revision plan
        plan_parts = []
        for suggestion in critique.get("suggestions", []):
            plan_parts.append(f"Apply: {suggestion}")

        return {
            "revised_task": revised_task,
            "plan": "; ".join(plan_parts) if plan_parts else "Retry with critique context",
        }


# ════════════════════════════════════════════════════════════════════
# Convenience Factory
# ════════════════════════════════════════════════════════════════════


def create_reflexion_engine(
    executor: Executor,
    critic: Critic | None = None,
    reviser: Reviser | None = None,
    quality_threshold: float = 0.7,
    max_attempts: int = 3,
    event_bus: Any = None,
) -> ReflexionEngine:
    """
    Factory function to create a ReflexionEngine with sensible defaults.

    Args:
        executor: The task executor (required)
        critic: The self-critic (defaults to HeuristicCritic)
        reviser: The reviser (defaults to AdaptiveReviser)
        quality_threshold: Minimum acceptable quality score
        max_attempts: Maximum retry attempts
        event_bus: Optional EventBus for event emission
    """
    return ReflexionEngine(
        executor=executor,
        critic=critic or HeuristicCritic(),
        reviser=reviser or AdaptiveReviser(),
        config=ReflexionConfig(
            quality_threshold=quality_threshold,
            max_attempts=max_attempts,
        ),
        event_bus=event_bus,
    )
