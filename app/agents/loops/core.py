"""
Agentic Loop Patterns for Angavu Intelligence.

Implements 5 foundational loop patterns from agentic AI research:

1. ReAct Loop — Reasoning + Acting with explicit trace
2. Reflexion Loop — Self-improvement through self-critique
3. Plan-and-Execute Loop — Multi-step task planning
4. Event Sourcing Loop — Auditability and replay
5. Supervisor Loop — Multi-agent coordination

These patterns build on the existing BiasharaAgent base class
and add structured reasoning, self-correction, planning,
event persistence, and supervision capabilities.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence, Type

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    AgentStatus,
    BiasharaAgent,
    EventType,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# 1. ReAct Loop — Reasoning + Acting with Explicit Trace
# ════════════════════════════════════════════════════════════════════


@dataclass
class ReasoningStep:
    """A single step in a ReAct reasoning trace."""
    step_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    timestamp: float = field(default_factory=time.time)
    phase: str = ""          # "think" | "act" | "observe" | "reflect"
    reasoning: str = ""      # What the agent is thinking
    action: str = ""         # What action was taken
    observation: str = ""    # What was observed
    confidence: float = 1.0  # Confidence in this step
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "reasoning": self.reasoning,
            "action": self.action,
            "observation": self.observation,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass
class ReActTrace:
    """Full trace of a ReAct loop execution."""
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_name: str = ""
    task: str = ""
    steps: List[ReasoningStep] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    final_result: Optional[Dict[str, Any]] = None
    success: bool = False
    total_reasoning_tokens: int = 0

    def add_step(self, step: ReasoningStep) -> None:
        self.steps.append(step)

    def get_reasoning_chain(self) -> List[str]:
        """Extract the reasoning chain as a list of strings."""
        return [s.reasoning for s in self.steps if s.reasoning]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "final_result": self.final_result,
            "success": self.success,
            "step_count": len(self.steps),
        }


class ReActAgent(BiasharaAgent):
    """
    Agent with explicit Reasoning + Acting (ReAct) loop.

    Each lifecycle step (think, act, observe, reflect) produces
    an explicit reasoning step stored in the trace. This makes
    the agent's decision-making process fully transparent and
    auditable.

    The trace can be:
    - Inspected via API for debugging
    - Used for few-shot learning (show past reasoning chains)
    - Fed back into the agent's context for self-improvement
    """

    def __init__(self, name: str, role: str, capabilities: Sequence[str]):
        super().__init__(name, role, capabilities)
        self._current_trace: Optional[ReActTrace] = None
        self._trace_history: List[ReActTrace] = []
        self._max_trace_history = 100

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Override to wrap the lifecycle with ReAct trace recording."""
        trace = ReActTrace(
            agent_name=self.name,
            task=f"{event.event_type.value}:{event.source}",
        )
        self._current_trace = trace

        # Run the standard lifecycle, which now records trace steps
        result = await super().handle_event(event)

        # Finalize trace
        trace.ended_at = time.time()
        trace.success = result.success
        trace.final_result = {
            "success": result.success,
            "data": str(result.data)[:500] if result.data else None,
            "error": result.error,
        }

        # Store trace
        self._trace_history.append(trace)
        if len(self._trace_history) > self._max_trace_history:
            self._trace_history = self._trace_history[-self._max_trace_history:]

        self._current_trace = None
        return result

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Generate reasoning about what to do.

        Subclasses implement _think_reasoning() which returns
        the decision with explicit reasoning text.
        """
        decision = await self._think_reasoning(context)

        # Record reasoning step
        if self._current_trace:
            step = ReasoningStep(
                phase="think",
                reasoning=decision.reasoning,
                action=decision.action,
                confidence=decision.confidence,
                metadata={"parameters": {k: str(v)[:200] for k, v in decision.parameters.items()}},
            )
            self._current_trace.add_step(step)

        return decision

    @abstractmethod
    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Subclasses implement this instead of think().

        Must return an AgentDecision with a meaningful reasoning string.
        """
        ...

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Execute the decision and record the action step.
        """
        result = await self._act_execute(decision)

        # Record action step
        if self._current_trace:
            step = ReasoningStep(
                phase="act",
                reasoning=f"Executing: {decision.action}",
                action=decision.action,
                observation=f"Success: {result.success}, Duration: {result.duration_ms:.1f}ms",
                confidence=decision.confidence,
                metadata={"result_success": result.success},
            )
            self._current_trace.add_step(step)

        return result

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """
        Subclasses implement this instead of act().

        Default delegates to the original act() if not overridden.
        """
        # If subclass doesn't override, use the parent's act
        raise NotImplementedError(f"{self.name} must implement _act_execute()")

    async def reflect(self, result: AgentResult) -> None:
        """
        Reflect on the result and record the reflection step.
        """
        await super().reflect(result)

        # Record reflection step
        if self._current_trace:
            recent = self.memory.recall_recent(3)
            step = ReasoningStep(
                phase="reflect",
                reasoning=(
                    f"Result: {'success' if result.success else 'failure'}. "
                    f"Error: {result.error or 'none'}. "
                    f"Recent context: {[m.get('event_type') for m in recent]}."
                ),
                observation=str(result.data)[:300] if result.data else "no data",
                confidence=1.0 if result.success else 0.5,
            )
            self._current_trace.add_step(step)

    def get_recent_traces(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent ReAct traces for inspection."""
        return [t.to_dict() for t in self._trace_history[-n:]]

    def get_reasoning_examples(self, n: int = 5) -> List[Dict[str, Any]]:
        """
        Get successful reasoning chains for few-shot learning.

        Returns traces where the final result was successful,
        which can be injected into the agent's context.
        """
        successful = [t for t in self._trace_history if t.success]
        return [
            {
                "task": t.task,
                "reasoning_chain": t.get_reasoning_chain(),
                "steps": len(t.steps),
            }
            for t in successful[-n:]
        ]


# ════════════════════════════════════════════════════════════════════
# 2. Reflexion Loop — Self-Improvement Through Self-Critique
# ════════════════════════════════════════════════════════════════════


@dataclass
class Critique:
    """Result of a self-critique evaluation."""
    score: float = 0.0           # 0.0 – 1.0 quality score
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    should_retry: bool = False   # Whether a retry is warranted
    revision_plan: str = ""      # How to improve on retry

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "should_retry": self.should_retry,
            "revision_plan": self.revision_plan,
        }


class ReflexionAgent(ReActAgent):
    """
    Agent with Reflexion loop — self-improvement through self-critique.

    After producing a result, the agent critiques its own output.
    If the quality is below threshold, it revises its approach
    and retries, incorporating the critique as feedback.

    This closes the gap between "the agent reflected" and
    "the reflection actually changed behavior."

    Reflexion Loop:
        execute → critique → (revise → execute → critique)* → accept

    Key insight: The critique is injected into the next iteration's
    context, so the agent literally learns from its mistakes
    within a single task execution.
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        quality_threshold: float = 0.7,
        max_retries: int = 3,
    ):
        super().__init__(name, role, capabilities)
        self._quality_threshold = quality_threshold
        self._max_retries = max_retries
        self._critique_history: List[Critique] = []

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """
        Override to add Reflexion loop around the execution.

        Flow: execute → critique → (revise → execute → critique)* → accept
        """
        cycle_start = time.time()
        attempt = 0
        last_result = None
        critiques: List[Critique] = []

        while attempt <= self._max_retries:
            attempt += 1

            # Execute the standard ReAct lifecycle
            if attempt == 1:
                result = await super().handle_event(event)
            else:
                # On retry, inject critique into the event metadata
                revised_event = self._inject_critique_context(event, critiques)
                result = await super().handle_event(revised_event)

            last_result = result

            # Critique the result
            critique = await self._critique(event, result)
            critiques.append(critique)
            self._critique_history.append(critique)

            self._logger.info(
                "reflexion_critique",
                attempt=attempt,
                score=critique.score,
                should_retry=critique.should_retry,
                issues=critique.issues,
            )

            # If quality is acceptable or max retries reached, stop
            if critique.score >= self._quality_threshold or not critique.should_retry:
                break

            if attempt > self._max_retries:
                self._logger.warning(
                    "reflexion_max_retries",
                    attempts=attempt,
                    best_score=max(c.score for c in critiques),
                )
                break

            # Store critique in memory for the next attempt
            self.memory.store(f"reflexion_critique:{attempt}", critique.to_dict())

        # Store the full Reflexion trace
        if self._current_trace:
            self._current_trace.steps.append(ReasoningStep(
                phase="reflexion",
                reasoning=f"Completed {attempt} attempt(s). Critiques: {[c.score for c in critiques]}",
                metadata={"critiques": [c.to_dict() for c in critiques]},
            ))

        return last_result

    async def _critique(self, event: AgentEvent, result: AgentResult) -> Critique:
        """
        Evaluate the quality of the result.

        Subclasses can override for domain-specific critique logic.
        Default implementation uses heuristics.
        """
        issues = []
        suggestions = []
        score = 1.0

        # Check for errors
        if not result.success:
            score -= 0.5
            issues.append(f"Execution failed: {result.error}")
            suggestions.append("Check error context and retry with adjusted parameters")

        # Check for slow execution
        if result.duration_ms > 5000:
            score -= 0.1
            issues.append(f"Slow execution: {result.duration_ms:.0f}ms")

        # Check if downstream events were produced
        if result.success and not result.events_to_publish:
            score -= 0.1
            suggestions.append("Consider producing downstream events for pipeline continuity")

        # Check recent failure rate
        recent = self.memory.recall_recent(5)
        recent_failures = sum(1 for r in recent if not r.get("success", True))
        if recent_failures >= 3:
            score -= 0.2
            issues.append(f"High recent failure rate: {recent_failures}/5")
            suggestions.append("Adjust strategy parameters or check upstream data quality")

        score = max(0.0, min(1.0, score))

        return Critique(
            score=score,
            issues=issues,
            suggestions=suggestions,
            should_retry=score < self._quality_threshold,
            revision_plan="; ".join(suggestions) if suggestions else "No changes needed",
        )

    def _inject_critique_context(
        self, event: AgentEvent, critiques: List[Critique]
    ) -> AgentEvent:
        """
        Inject critique feedback into the event for the next attempt.

        This is how Reflexion changes behavior: the agent sees its
        own critique and adjusts accordingly.
        """
        latest = critiques[-1]
        enriched_metadata = {
            **event.metadata,
            "reflexion_feedback": {
                "previous_score": latest.score,
                "issues": latest.issues,
                "suggestions": latest.suggestions,
                "revision_plan": latest.revision_plan,
                "attempt": len(critiques) + 1,
            },
        }
        return AgentEvent(
            event_type=event.event_type,
            source=event.source,
            payload=event.payload,
            event_id=event.event_id,
            timestamp=event.timestamp,
            correlation_id=event.correlation_id,
            metadata=enriched_metadata,
        )

    def get_critique_history(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent critiques for analysis."""
        return [c.to_dict() for c in self._critique_history[-n:]]


# ════════════════════════════════════════════════════════════════════
# 3. Plan-and-Execute Loop — Multi-Step Task Planning
# ════════════════════════════════════════════════════════════════════


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    step_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    description: str = ""
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # step_ids this depends on
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "action": self.action,
            "parameters": {k: str(v)[:200] for k, v in self.parameters.items()},
            "dependencies": self.dependencies,
            "status": self.status,
            "result": str(self.result)[:300] if self.result else None,
            "error": self.error,
        }


@dataclass
class ExecutionPlan:
    """A plan for executing a complex multi-step task."""
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    goal: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: str = "active"  # active | completed | failed | replanned
    replan_count: int = 0

    def get_next_step(self) -> Optional[PlanStep]:
        """Get the next pending step that has all dependencies met."""
        for step in self.steps:
            if step.status != "pending":
                continue
            # Check if all dependencies are completed
            deps_met = all(
                self._get_step(dep_id) and self._get_step(dep_id).status == "completed"
                for dep_id in step.dependencies
            )
            if deps_met:
                return step
        return None

    def _get_step(self, step_id: str) -> Optional[PlanStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def mark_step(self, step_id: str, status: str, result: Any = None, error: str = None) -> None:
        step = self._get_step(step_id)
        if step:
            step.status = status
            step.result = result
            step.error = error

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)

    def has_failures(self) -> bool:
        return any(s.status == "failed" for s in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "replan_count": self.replan_count,
            "progress": f"{sum(1 for s in self.steps if s.status in ('completed', 'skipped'))}/{len(self.steps)}",
        }


class PlanExecuteAgent(ReflexionAgent):
    """
    Agent with Plan-and-Execute loop for complex multi-step tasks.

    Instead of executing tasks sequentially with no planning,
    this agent:
    1. Plans: Breaks the goal into steps with dependencies
    2. Executes: Runs each step, tracking progress
    3. Re-plans: If a step fails, creates a revised plan
    4. Aggregates: Combines step results into final output

    This handles tasks like:
    - Generate intelligence → produce report → deliver via WhatsApp
    - Classify worker → fetch domain data → generate insights → create recommendations
    - Collect feedback → cluster → generate feature spec → notify team
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        max_replans: int = 3,
        **kwargs,
    ):
        super().__init__(name, role, capabilities, **kwargs)
        self._max_replans = max_replans
        self._current_plan: Optional[ExecutionPlan] = None
        self._plan_history: List[ExecutionPlan] = []

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Think phase: Create or retrieve an execution plan.

        If no plan exists, create one. If a plan exists, return
        the next step to execute.
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})
        goal = self._extract_goal(event_data)

        # Check for Reflexion feedback (plan revision)
        reflexion_feedback = event_data.get("metadata", {}).get("reflexion_feedback")

        if self._current_plan is None or reflexion_feedback:
            # Create or revise plan
            plan = await self._create_plan(goal, context, reflexion_feedback)
            self._current_plan = plan
            self._plan_history.append(plan)

            next_step = plan.get_next_step()
            if next_step:
                return AgentDecision(
                    action="execute_plan_step",
                    parameters={
                        "plan_id": plan.plan_id,
                        "step_id": next_step.step_id,
                        "step_action": next_step.action,
                        "step_parameters": next_step.parameters,
                        "goal": goal,
                    },
                    confidence=0.9,
                    reasoning=(
                        f"Created plan with {len(plan.steps)} steps for goal: {goal}. "
                        f"First step: {next_step.description}"
                    ),
                )
            else:
                return AgentDecision(
                    action="no_steps",
                    parameters={"goal": goal},
                    confidence=0.5,
                    reasoning="Plan created but no executable steps found.",
                )

        # Plan exists — get next step
        next_step = self._current_plan.get_next_step()
        if next_step:
            return AgentDecision(
                action="execute_plan_step",
                parameters={
                    "plan_id": self._current_plan.plan_id,
                    "step_id": next_step.step_id,
                    "step_action": next_step.action,
                    "step_parameters": next_step.parameters,
                    "goal": goal,
                },
                confidence=0.85,
                reasoning=(
                    f"Continuing plan {self._current_plan.plan_id}. "
                    f"Next step: {next_step.description} "
                    f"(progress: {self._current_plan.to_dict()['progress']})"
                ),
            )

        # All steps done
        return AgentDecision(
            action="plan_complete",
            parameters={"plan_id": self._current_plan.plan_id, "goal": goal},
            confidence=1.0,
            reasoning=f"Plan {self._current_plan.plan_id} completed all steps.",
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """
        Execute the current plan step.
        """
        action = decision.action

        if action == "execute_plan_step":
            step_id = decision.parameters.get("step_id")
            step_action = decision.parameters.get("step_action")
            step_params = decision.parameters.get("step_parameters", {})

            # Mark step as running
            self._current_plan.mark_step(step_id, "running")

            try:
                # Execute the step (subclasses implement _execute_plan_step)
                step_result = await self._execute_plan_step(step_action, step_params)

                if step_result.get("success", False):
                    self._current_plan.mark_step(step_id, "completed", result=step_result)
                else:
                    self._current_plan.mark_step(step_id, "failed", error=step_result.get("error"))

                # Check if plan needs revision
                if self._current_plan.has_failures() and self._current_plan.replan_count < self._max_replans:
                    # Trigger replan on next think cycle
                    self._current_plan.status = "replanned"
                    self._current_plan.replan_count += 1

                return AgentResult(
                    success=step_result.get("success", False),
                    data=step_result,
                    error=step_result.get("error"),
                    duration_ms=step_result.get("duration_ms", 0),
                )

            except Exception as exc:
                self._current_plan.mark_step(step_id, "failed", error=str(exc))
                return AgentResult(success=False, error=str(exc))

        elif action == "plan_complete":
            # Aggregate all step results
            results = self._aggregate_results()
            self._current_plan.completed_at = time.time()
            self._current_plan.status = "completed"

            return AgentResult(
                success=True,
                data=results,
                duration_ms=(time.time() - self._current_plan.created_at) * 1000,
            )

        elif action == "no_steps":
            return AgentResult(success=False, error="No executable steps in plan")

        return AgentResult(success=False, error=f"Unknown action: {action}")

    async def _create_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        reflexion_feedback: Optional[Dict] = None,
    ) -> ExecutionPlan:
        """
        Create an execution plan for the given goal.

        Subclasses should override this for domain-specific planning.
        Default implementation creates a simple single-step plan.
        """
        return ExecutionPlan(
            goal=goal,
            steps=[
                PlanStep(
                    description=f"Execute: {goal}",
                    action="default",
                    parameters=context.get("event", {}).get("payload", {}),
                )
            ],
        )

    async def _execute_plan_step(
        self, action: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single plan step.

        Subclasses must implement this for domain-specific execution.
        """
        raise NotImplementedError(f"{self.name} must implement _execute_plan_step()")

    def _extract_goal(self, event_data: Dict[str, Any]) -> str:
        """Extract the goal from the event data."""
        event_type = event_data.get("event_type", "unknown")
        payload = event_data.get("payload", {})
        return payload.get("goal", f"Process {event_type}")

    def _aggregate_results(self) -> Dict[str, Any]:
        """Aggregate results from all completed plan steps."""
        if not self._current_plan:
            return {}

        results = {}
        for step in self._current_plan.steps:
            if step.status == "completed" and step.result:
                results[step.step_id] = step.result

        return {
            "plan_id": self._current_plan.plan_id,
            "goal": self._current_plan.goal,
            "step_results": results,
            "total_steps": len(self._current_plan.steps),
            "completed_steps": sum(1 for s in self._current_plan.steps if s.status == "completed"),
            "failed_steps": sum(1 for s in self._current_plan.steps if s.status == "failed"),
        }

    def get_plan_history(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent execution plans."""
        return [p.to_dict() for p in self._plan_history[-n:]]


# ════════════════════════════════════════════════════════════════════
# 4. Event Sourcing Loop — Auditability and Replay
# ════════════════════════════════════════════════════════════════════


@dataclass
class StoredEvent:
    """An event stored in the event store with full audit metadata."""
    sequence: int = 0                # Global sequence number
    event_type: str = ""
    source: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    stored_at: float = field(default_factory=time.time)
    event_id: str = ""
    correlation_id: Optional[str] = None
    # For state reconstruction
    aggregate_id: Optional[str] = None  # Which entity this belongs to
    aggregate_type: Optional[str] = None  # "agent" | "plan" | "pipeline"
    version: int = 0  # Aggregate version after this event

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
            "metadata": self.metadata,
            "stored_at": self.stored_at,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "version": self.version,
        }


class EventStore:
    """
    Append-only event store for auditability and replay.

    Stores every event that flows through the system, enabling:
    - Full audit trail: "What happened and when?"
    - Replay: Reconstruct state at any point in time
    - Debugging: Trace the exact sequence of events that led to an issue
    - Analytics: Aggregate event patterns for system optimization

    Storage: In-memory with optional persistence to file/database.
    In production, this would backed by PostgreSQL or EventStoreDB.
    """

    def __init__(self, max_events: int = 50_000, persist_path: Optional[str] = None):
        self._events: List[StoredEvent] = []
        self._sequence: int = 0
        self._max_events = max_events
        self._persist_path = persist_path
        self._aggregate_versions: Dict[str, int] = {}  # aggregate_id → version
        self._logger = logger.bind(component="event_store")

    async def append(
        self,
        event: AgentEvent,
        aggregate_id: Optional[str] = None,
        aggregate_type: Optional[str] = None,
    ) -> int:
        """
        Append an event to the store.

        Returns the global sequence number.
        """
        self._sequence += 1

        # Track aggregate version
        if aggregate_id:
            version = self._aggregate_versions.get(aggregate_id, 0) + 1
            self._aggregate_versions[aggregate_id] = version
        else:
            version = 0

        stored = StoredEvent(
            sequence=self._sequence,
            event_type=event.event_type.value,
            source=event.source,
            payload=event.payload,
            metadata=event.metadata,
            stored_at=time.time(),
            event_id=event.event_id,
            correlation_id=event.correlation_id,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            version=version,
        )

        self._events.append(stored)

        # Trim to max size
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        self._logger.debug(
            "event_stored",
            sequence=self._sequence,
            event_type=event.event_type.value,
            source=event.source,
            aggregate_id=aggregate_id,
        )

        return self._sequence

    def get_events(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        aggregate_id: Optional[str] = None,
        since_sequence: int = 0,
        limit: int = 100,
    ) -> List[StoredEvent]:
        """
        Query stored events with filters.

        All filters are AND-combined.
        """
        results = self._events

        if since_sequence > 0:
            results = [e for e in results if e.sequence > since_sequence]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if source:
            results = [e for e in results if e.source == source]
        if aggregate_id:
            results = [e for e in results if e.aggregate_id == aggregate_id]

        return results[-limit:]

    def get_aggregate_events(
        self, aggregate_id: str, since_version: int = 0
    ) -> List[StoredEvent]:
        """Get all events for a specific aggregate (for state reconstruction)."""
        return [
            e for e in self._events
            if e.aggregate_id == aggregate_id and e.version > since_version
        ]

    def get_correlated_events(self, correlation_id: str) -> List[StoredEvent]:
        """Get all events sharing a correlation ID (for request tracing)."""
        return [
            e for e in self._events
            if e.correlation_id == correlation_id
        ]

    def replay(
        self,
        from_sequence: int = 0,
        to_sequence: Optional[int] = None,
    ) -> List[StoredEvent]:
        """
        Replay events from a sequence range.

        Useful for:
        - Rebuilding projections/read models
        - Debugging by replaying the exact event sequence
        - Testing by replaying production events
        """
        events = [e for e in self._events if e.sequence > from_sequence]
        if to_sequence is not None:
            events = [e for e in events if e.sequence <= to_sequence]
        return events

    def get_stats(self) -> Dict[str, Any]:
        """Get event store statistics."""
        type_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        for e in self._events:
            type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1
            source_counts[e.source] = source_counts.get(e.source, 0) + 1

        return {
            "total_events": len(self._events),
            "current_sequence": self._sequence,
            "aggregate_count": len(self._aggregate_versions),
            "event_type_counts": type_counts,
            "source_counts": source_counts,
            "max_events": self._max_events,
        }


class EventSourcedAgent(PlanExecuteAgent):
    """
    Agent with event sourcing — every action is stored as an event.

    Extends PlanExecuteAgent to automatically store all lifecycle
    events in the event store. This provides:
    - Full audit trail of every agent decision
    - Ability to replay and reconstruct agent state
    - Correlation tracking across multi-agent pipelines
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        event_store: Optional[EventStore] = None,
        **kwargs,
    ):
        super().__init__(name, role, capabilities, **kwargs)
        self._event_store = event_store

    def set_event_store(self, store: EventStore) -> None:
        """Inject the event store."""
        self._event_store = store

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Override to store events in the event store."""
        # Store the incoming event
        if self._event_store:
            await self._event_store.append(
                event,
                aggregate_id=self.name,
                aggregate_type="agent",
            )

        # Run the standard lifecycle (with Reflexion + Plan-Execute)
        result = await super().handle_event(event)

        # Store the result as an event
        if self._event_store:
            result_event = AgentEvent(
                event_type=EventType.AGENT_HEALTH_CHECK,  # generic lifecycle event
                source=self.name,
                payload={
                    "lifecycle": "result",
                    "success": result.success,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                    "data_summary": str(result.data)[:500] if result.data else None,
                },
                correlation_id=event.correlation_id or event.event_id,
            )
            await self._event_store.append(
                result_event,
                aggregate_id=self.name,
                aggregate_type="agent",
            )

            # Store downstream events
            for downstream in result.events_to_publish:
                await self._event_store.append(
                    downstream,
                    aggregate_id=self.name,
                    aggregate_type="pipeline",
                )

        return result

    def get_audit_trail(
        self, since_sequence: int = 0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get the audit trail for this agent."""
        if not self._event_store:
            return []
        events = self._event_store.get_events(
            source=self.name, since_sequence=since_sequence, limit=limit
        )
        return [e.to_dict() for e in events]


# ════════════════════════════════════════════════════════════════════
# 5. Supervisor Loop — Multi-Agent Coordination
# ════════════════════════════════════════════════════════════════════


class SupervisionPolicy(str, Enum):
    """How the supervisor handles agent failures."""
    RETRY = "retry"              # Retry the same agent
    FALLBACK = "fallback"        # Try a fallback agent
    ESCALATE = "escalate"        # Escalate to human or higher-level agent
    SKIP = "skip"                # Skip and continue


@dataclass
class SupervisionDecision:
    """A supervisor's decision about how to handle an agent result."""
    policy: SupervisionPolicy = SupervisionPolicy.RETRY
    target_agent: Optional[str] = None  # For FALLBACK: which agent to try
    reason: str = ""
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy.value,
            "target_agent": self.target_agent,
            "reason": self.reason,
            "max_retries": self.max_retries,
        }


@dataclass
class SupervisedExecution:
    """Record of a supervised execution."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    original_agent: str = ""
    actual_agent: str = ""  # May differ if fallback was used
    attempts: int = 0
    result: Optional[Dict[str, Any]] = None
    supervision_decisions: List[SupervisionDecision] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "original_agent": self.original_agent,
            "actual_agent": self.actual_agent,
            "attempts": self.attempts,
            "result": str(self.result)[:500] if self.result else None,
            "supervision_decisions": [d.to_dict() for d in self.supervision_decisions],
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "success": self.success,
        }


class SupervisorAgent(EventSourcedAgent):
    """
    Supervisor agent that coordinates and monitors other agents.

    The supervisor:
    1. Receives tasks and selects the best agent to handle them
    2. Monitors agent execution
    3. Validates results
    4. Handles failures (retry, fallback, escalate, skip)
    5. Tracks performance metrics across all agents

    This is the "manager" in a multi-agent system — it doesn't
    do the work itself, but ensures the work gets done correctly.
    """

    def __init__(
        self,
        name: str = "Supervisor",
        role: str = "Multi-agent coordinator",
        event_store: Optional[EventStore] = None,
    ):
        super().__init__(
            name=name,
            role=role,
            capabilities=[
                "agent_selection",
                "result_validation",
                "failure_handling",
                "performance_monitoring",
                "load_balancing",
            ],
            event_store=event_store,
        )
        self._managed_agents: Dict[str, BiasharaAgent] = {}
        self._fallback_map: Dict[str, List[str]] = {}  # agent → [fallback agents]
        self._execution_history: List[SupervisedExecution] = []
        self._agent_metrics: Dict[str, Dict[str, Any]] = {}

    def register_agent(
        self,
        agent: BiasharaAgent,
        fallbacks: Optional[List[str]] = None,
    ) -> None:
        """Register an agent under supervision."""
        self._managed_agents[agent.name] = agent
        if fallbacks:
            self._fallback_map[agent.name] = fallbacks
        self._agent_metrics[agent.name] = {
            "total_executions": 0,
            "successes": 0,
            "failures": 0,
            "avg_duration_ms": 0.0,
            "last_execution": None,
        }
        self._logger.info(
            "agent_registered",
            agent=agent.name,
            fallbacks=fallbacks,
        )

    async def supervise(
        self,
        agent_name: str,
        event: AgentEvent,
        validation_fn: Optional[Callable[[AgentResult], bool]] = None,
    ) -> AgentResult:
        """
        Supervise the execution of a task by an agent.

        1. Select the agent (or fallback)
        2. Execute with monitoring
        3. Validate the result
        4. Handle failures according to policy
        """
        execution = SupervisedExecution(
            original_agent=agent_name,
            actual_agent=agent_name,
        )

        current_agent_name = agent_name
        attempt = 0
        max_attempts = 3

        while attempt < max_attempts:
            attempt += 1
            execution.attempts = attempt

            agent = self._managed_agents.get(current_agent_name)
            if not agent:
                # Try fallback
                decision = SupervisionDecision(
                    policy=SupervisionPolicy.FALLBACK,
                    reason=f"Agent {current_agent_name} not found",
                )
                execution.supervision_decisions.append(decision)

                fallback_name = self._select_fallback(current_agent_name)
                if fallback_name:
                    current_agent_name = fallback_name
                    execution.actual_agent = fallback_name
                    continue
                else:
                    return AgentResult(
                        success=False,
                        error=f"No agent available for {agent_name} (no fallbacks)",
                    )

            # Execute
            try:
                result = await agent.handle_event(event)
            except Exception as exc:
                result = AgentResult(success=False, error=str(exc))

            # Update metrics
            self._update_metrics(current_agent_name, result)

            # Validate
            is_valid = True
            if validation_fn:
                try:
                    is_valid = validation_fn(result)
                except Exception:
                    is_valid = False

            if result.success and is_valid:
                execution.success = True
                execution.result = {
                    "success": True,
                    "data": str(result.data)[:500] if result.data else None,
                }
                execution.ended_at = time.time()
                self._execution_history.append(execution)
                return result

            # Handle failure
            decision = self._decide_on_failure(
                current_agent_name, result, attempt, max_attempts, is_valid
            )
            execution.supervision_decisions.append(decision)

            self._logger.warning(
                "supervision_failure",
                agent=current_agent_name,
                attempt=attempt,
                policy=decision.policy.value,
                reason=decision.reason,
            )

            if decision.policy == SupervisionPolicy.RETRY:
                continue
            elif decision.policy == SupervisionPolicy.FALLBACK:
                fallback_name = decision.target_agent or self._select_fallback(current_agent_name)
                if fallback_name:
                    current_agent_name = fallback_name
                    execution.actual_agent = fallback_name
                    continue
                # No fallback — escalate
                decision = SupervisionDecision(
                    policy=SupervisionPolicy.ESCALATE,
                    reason="No fallback available",
                )
                execution.supervision_decisions.append(decision)

            elif decision.policy == SupervisionPolicy.ESCALATE:
                execution.ended_at = time.time()
                execution.result = {"success": False, "error": "escalated", "original_error": result.error}
                self._execution_history.append(execution)
                return AgentResult(
                    success=False,
                    error=f"Escalated: {result.error}",
                    data={"escalated_from": current_agent_name, "attempt": attempt},
                )

            elif decision.policy == SupervisionPolicy.SKIP:
                execution.ended_at = time.time()
                execution.result = {"success": False, "error": "skipped"}
                self._execution_history.append(execution)
                return AgentResult(
                    success=False,
                    error=f"Skipped after {attempt} attempts: {result.error}",
                )

        # Exhausted all attempts
        execution.ended_at = time.time()
        execution.result = {"success": False, "error": "max_attempts_exceeded"}
        self._execution_history.append(execution)
        return AgentResult(
            success=False,
            error=f"Failed after {max_attempts} attempts for {agent_name}",
        )

    def _decide_on_failure(
        self,
        agent_name: str,
        result: AgentResult,
        attempt: int,
        max_attempts: int,
        is_valid: bool,
    ) -> SupervisionDecision:
        """Decide how to handle a failed execution."""
        # Check agent's success rate
        metrics = self._agent_metrics.get(agent_name, {})
        success_rate = metrics.get("successes", 0) / max(1, metrics.get("total_executions", 1))

        # If agent has low success rate, prefer fallback
        if success_rate < 0.5 and agent_name in self._fallback_map:
            return SupervisionDecision(
                policy=SupervisionPolicy.FALLBACK,
                target_agent=self._select_fallback(agent_name),
                reason=f"Agent {agent_name} has low success rate ({success_rate:.0%})",
            )

        # If validation failed but execution succeeded, retry
        if result.success and not is_valid:
            if attempt < max_attempts:
                return SupervisionDecision(
                    policy=SupervisionPolicy.RETRY,
                    reason="Result validation failed, retrying",
                )
            else:
                return SupervisionDecision(
                    policy=SupervisionPolicy.ESCALATE,
                    reason="Validation keeps failing",
                )

        # If execution failed, try fallback
        if not result.success and agent_name in self._fallback_map:
            return SupervisionDecision(
                policy=SupervisionPolicy.FALLBACK,
                target_agent=self._select_fallback(agent_name),
                reason=f"Execution failed: {result.error}",
            )

        # Default: retry if attempts remaining
        if attempt < max_attempts:
            return SupervisionDecision(
                policy=SupervisionPolicy.RETRY,
                reason="Retrying execution",
            )

        # Give up
        return SupervisionDecision(
            policy= SupervisionPolicy.SKIP,
            reason="Max attempts exhausted",
        )

    def _select_fallback(self, agent_name: str) -> Optional[str]:
        """Select a fallback agent."""
        fallbacks = self._fallback_map.get(agent_name, [])
        for fb in fallbacks:
            if fb in self._managed_agents:
                return fb
        return None

    def _update_metrics(self, agent_name: str, result: AgentResult) -> None:
        """Update agent performance metrics."""
        metrics = self._agent_metrics.get(agent_name)
        if not metrics:
            return

        metrics["total_executions"] += 1
        if result.success:
            metrics["successes"] += 1
        else:
            metrics["failures"] += 1

        # Running average duration
        n = metrics["total_executions"]
        old_avg = metrics["avg_duration_ms"]
        metrics["avg_duration_ms"] = old_avg + (result.duration_ms - old_avg) / n
        metrics["last_execution"] = time.time()

    async def _think_reasoning(self, context: Dict[str, Any]) -> AgentDecision:
        """The supervisor's own think phase — decides which agent to route to."""
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})

        # Determine which agent should handle this
        target = self._select_agent_for_event(event_data)

        return AgentDecision(
            action="supervise_agent",
            parameters={
                "target_agent": target,
                "event": event_data,
            },
            confidence=0.85,
            reasoning=f"Routing to {target} based on event type and agent capabilities",
        )

    async def _act_execute(self, decision: AgentDecision) -> AgentResult:
        """Execute supervision — delegate to the selected agent."""
        target = decision.parameters.get("target_agent")
        if not target:
            return AgentResult(success=False, error="No target agent selected")

        # Reconstruct the event from the decision parameters
        event_data = decision.parameters.get("event", {})
        event = AgentEvent(
            event_type=EventType(event_data.get("event_type", "agent.health.check")),
            source=event_data.get("source", "unknown"),
            payload=event_data.get("payload", {}),
            correlation_id=event_data.get("correlation_id"),
        )

        return await self.supervise(target, event)

    def _select_agent_for_event(self, event_data: Dict[str, Any]) -> str:
        """Select the best agent for the given event."""
        event_type = event_data.get("event_type", "")

        # Map event types to preferred agents
        routing = {
            "transaction.received": "TransactionProcessor",
            "transaction.processed": "IntelligenceGenerator",
            "intelligence.generated": "ReportGenerator",
            "feedback.received": "SelfEvolution",
            "report.requested": "ReportGenerator",
        }

        preferred = routing.get(event_type)
        if preferred and preferred in self._managed_agents:
            return preferred

        # Default to first available agent
        return next(iter(self._managed_agents), "unknown")

    def get_agent_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for all managed agents."""
        return dict(self._agent_metrics)

    def get_execution_history(self, n: int = 20) -> List[Dict[str, Any]]:
        """Get recent supervised executions."""
        return [e.to_dict() for e in self._execution_history[-n:]]

    def get_supervision_stats(self) -> Dict[str, Any]:
        """Get overall supervision statistics."""
        total = len(self._execution_history)
        successes = sum(1 for e in self._execution_history if e.success)

        fallback_count = sum(
            1 for e in self._execution_history
            for d in e.supervision_decisions
            if d.policy == SupervisionPolicy.FALLBACK
        )
        retry_count = sum(
            1 for e in self._execution_history
            for d in e.supervision_decisions
            if d.policy == SupervisionPolicy.RETRY
        )

        return {
            "total_executions": total,
            "successes": successes,
            "success_rate": successes / max(1, total),
            "fallback_count": fallback_count,
            "retry_count": retry_count,
            "managed_agents": len(self._managed_agents),
            "agent_metrics": self._agent_metrics,
        }
