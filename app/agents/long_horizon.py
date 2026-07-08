"""
Long-Horizon Orchestrator — DeerFlow-Inspired Task Orchestration.

Manages tasks lasting minutes to hours with:
- TaskPlanner     — breaks complex goals into sub-tasks with dependencies
- SubAgentDelegator — assigns sub-tasks to specialized agents
- ProgressTracker — tracks long-running task progress with checkpoints
- ResultAggregator — combines sub-task results into final output
- LongHorizonOrchestrator — top-level coordinator

Architecture (DeerFlow-inspired):
    User Request
         ▼
    LongHorizonOrchestrator
         ├── TaskPlanner (decompose goal → DAG of sub-tasks)
         ├── SubAgentDelegator (assign tasks to agents)
         ├── ProgressTracker (checkpoint + resume)
         └── ResultAggregator (combine results)

Key DeerFlow patterns borrowed:
1. Task decomposition into a DAG with dependencies
2. Parallel execution where dependencies allow
3. Durable checkpointing for crash recovery
4. Re-planning on sub-task failure
5. Timeout / kill switch for runaway tasks

Does NOT fork DeerFlow — builds directly on Angavu's existing
EventBus + PlanExecuteAgent + SupervisorAgent infrastructure.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import structlog

from app.agents.base import AgentEvent, AgentResult, BiasharaAgent, EventType
from app.agents.loops import (
    EventStore,
    ExecutionPlan,
    PlanStep,
    PlanExecuteAgent,
    SupervisedExecution,
    SupervisorAgent,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Task & Progress Types
# ════════════════════════════════════════════════════════════════════


class TaskStatus(str, Enum):
    """Status of a long-horizon task."""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class SubTaskStatus(str, Enum):
    """Status of an individual sub-task."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class SubTask:
    """A sub-task within a long-horizon task."""
    subtask_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # subtask_ids
    assigned_agent: Optional[str] = None
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    attempts: int = 0
    max_retries: int = 3
    timeout_seconds: float = 300.0  # 5 min default
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize sub-task to dictionary."""
        return {
            "subtask_id": self.subtask_id,
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "parameters": {k: str(v)[:200] for k, v in self.parameters.items()},
            "dependencies": self.dependencies,
            "assigned_agent": self.assigned_agent,
            "status": self.status.value,
            "result": str(self.result)[:300] if self.result else None,
            "error": self.error,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": (
                (self.completed_at or time.time()) - self.started_at
                if self.started_at else None
            ),
        }


@dataclass
class TaskCheckpoint:
    """Durable checkpoint for crash recovery."""
    checkpoint_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    task_id: str = ""
    task_status: TaskStatus = TaskStatus.EXECUTING
    subtask_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    aggregated_results: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    step_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize checkpoint to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "task_id": self.task_id,
            "task_status": self.task_status.value,
            "subtask_count": len(self.subtask_states),
            "aggregated_results_keys": list(self.aggregated_results.keys()),
            "created_at": self.created_at,
            "step_index": self.step_index,
        }


@dataclass
class LongHorizonTask:
    """A long-running task with sub-tasks, checkpoints, and progress."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    goal: str = ""
    description: str = ""
    subtasks: List[SubTask] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    progress_pct: float = 0.0
    checkpoints: List[TaskCheckpoint] = field(default_factory=list)
    aggregated_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    timeout_seconds: float = 3600.0  # 1 hour default
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_subtask(self, subtask_id: str) -> Optional[SubTask]:
        """Find a sub-task by its ID."""
        for st in self.subtasks:
            if st.subtask_id == subtask_id:
                return st
        return None

    def get_ready_subtasks(self) -> List[SubTask]:
        """Get sub-tasks whose dependencies are all completed."""
        ready = []
        for st in self.subtasks:
            if st.status != SubTaskStatus.PENDING:
                continue
            deps_met = all(
                self.get_subtask(dep_id) is not None
                and self.get_subtask(dep_id).status == SubTaskStatus.COMPLETED
                for dep_id in st.dependencies
            )
            if deps_met:
                ready.append(st)
        return ready

    def update_progress(self) -> None:
        """Recalculate progress percentage."""
        if not self.subtasks:
            self.progress_pct = 0.0
            return
        done = sum(
            1 for st in self.subtasks
            if st.status in (SubTaskStatus.COMPLETED, SubTaskStatus.SKIPPED)
        )
        self.progress_pct = round(done / len(self.subtasks) * 100, 1)

    def is_complete(self) -> bool:
        return all(
            st.status in (SubTaskStatus.COMPLETED, SubTaskStatus.SKIPPED)
            for st in self.subtasks
        )

    def has_failures(self) -> bool:
        return any(st.status == SubTaskStatus.FAILED for st in self.subtasks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "description": self.description,
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "subtask_count": len(self.subtasks),
            "subtasks": [st.to_dict() for st in self.subtasks],
            "checkpoint_count": len(self.checkpoints),
            "aggregated_result": (
                str(self.aggregated_result)[:500]
                if self.aggregated_result else None
            ),
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": (
                (self.completed_at or time.time()) - self.started_at
                if self.started_at else None
            ),
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════════
# TaskPlanner — Goal Decomposition into Sub-Task DAG
# ════════════════════════════════════════════════════════════════════


class TaskPlanner:
    """
    Decomposes complex goals into a DAG of sub-tasks with dependencies.

    Inspired by DeerFlow's task decomposition, but built on
    Angavu's existing PlanExecuteAgent patterns.

    Subclasses override _decompose() for domain-specific planning.
    """

    def __init__(self, name: str = "TaskPlanner"):
        self.name = name
        self._logger = logger.bind(component="task_planner")

    async def plan(
        self,
        goal: str,
        context: Dict[str, Any],
        available_agents: List[str],
    ) -> List[SubTask]:
        """
        Create a sub-task DAG for the given goal.

        Returns a list of SubTask objects with dependencies set.
        """
        self._logger.info("planning_task", goal=goal, agents=available_agents)
        subtasks = await self._decompose(goal, context, available_agents)
        self._logger.info(
            "plan_created",
            goal=goal,
            subtask_count=len(subtasks),
            subtasks=[s.name for s in subtasks],
        )
        return subtasks

    async def replan(
        self,
        task: LongHorizonTask,
        failed_subtask: SubTask,
        context: Dict[str, Any],
    ) -> List[SubTask]:
        """
        Re-plan after a sub-task failure.

        By default, retries the failed sub-task. Subclasses can
        override for more sophisticated re-planning (e.g., skip,
        substitute, or decompose further).
        """
        self._logger.info(
            "replanning",
            task_id=task.task_id,
            failed_subtask=failed_subtask.subtask_id,
            error=failed_subtask.error,
        )

        # Default: mark for retry if retries remaining
        if failed_subtask.attempts < failed_subtask.max_retries:
            failed_subtask.status = SubTaskStatus.PENDING
            failed_subtask.error = None
            return task.subtasks

        # Exhausted retries — skip and continue
        failed_subtask.status = SubTaskStatus.SKIPPED
        return task.subtasks

    async def _decompose(
        self,
        goal: str,
        context: Dict[str, Any],
        available_agents: List[str],
    ) -> List[SubTask]:
        """
        Decompose a goal into sub-tasks.

        Override in subclasses for domain-specific decomposition.
        Default creates a single sub-task.
        """
        return [
            SubTask(
                name="execute_goal",
                description=f"Execute: {goal}",
                action="default",
                parameters=context,
            )
        ]


# ════════════════════════════════════════════════════════════════════
# SubAgentDelegator — Assigns Sub-Tasks to Specialized Agents
# ════════════════════════════════════════════════════════════════════


class SubAgentDelegator:
    """
    Assigns sub-tasks to the most appropriate specialized agent.

    Maintains a registry of agents and their capabilities.
    Uses capability matching to select the best agent for each sub-task.
    Falls back to a default agent if no match is found.
    """

    def __init__(self, name: str = "SubAgentDelegator"):
        self.name = name
        self._agent_capabilities: Dict[str, List[str]] = {}
        self._agents: Dict[str, BiasharaAgent] = {}
        self._logger = logger.bind(component="sub_agent_delegator")

    def register_agent(self, agent: BiasharaAgent) -> None:
        """Register an agent for delegation."""
        self._agents[agent.name] = agent
        self._agent_capabilities[agent.name] = agent.capabilities
        self._logger.info(
            "agent_registered_for_delegation",
            agent=agent.name,
            capabilities=agent.capabilities,
        )

    def select_agent(self, subtask: SubTask) -> Optional[BiasharaAgent]:
        """
        Select the best agent for a sub-task.

        Matching strategy:
        1. If subtask has a pre-assigned agent, use it
        2. Match by action → capability mapping
        3. Fall back to the first available agent
        """
        # Pre-assigned
        if subtask.assigned_agent and subtask.assigned_agent in self._agents:
            return self._agents[subtask.assigned_agent]

        # Capability matching
        best_agent = None
        best_score = 0

        for agent_name, caps in self._agent_capabilities.items():
            score = sum(
                1 for cap in caps
                if cap in subtask.action or cap in subtask.description.lower()
            )
            if score > best_score:
                best_score = score
                best_agent = self._agents[agent_name]

        if best_agent:
            return best_agent

        # Fallback to first available
        if self._agents:
            return next(iter(self._agents.values()))

        return None

    async def delegate(
        self,
        subtask: SubTask,
        event: AgentEvent,
    ) -> AgentResult:
        """
        Delegate a sub-task to the selected agent.

        Sets timeout, tracks attempts, handles errors.
        """
        agent = self.select_agent(subtask)
        if not agent:
            return AgentResult(
                success=False,
                error=f"No agent available for sub-task {subtask.name}",
            )

        subtask.assigned_agent = agent.name
        subtask.status = SubTaskStatus.RUNNING
        subtask.attempts += 1
        subtask.started_at = time.time()

        self._logger.info(
            "delegating_subtask",
            subtask_id=subtask.subtask_id,
            agent=agent.name,
            attempt=subtask.attempts,
        )

        try:
            result = await asyncio.wait_for(
                agent.handle_event(event),
                timeout=subtask.timeout_seconds,
            )

            if result.success:
                subtask.status = SubTaskStatus.COMPLETED
                subtask.result = {
                    "data": result.data,
                    "duration_ms": result.duration_ms,
                }
            else:
                subtask.status = SubTaskStatus.FAILED
                subtask.error = result.error

            subtask.completed_at = time.time()
            return result

        except asyncio.TimeoutError:
            subtask.status = SubTaskStatus.FAILED
            subtask.error = f"Timed out after {subtask.timeout_seconds}s"
            subtask.completed_at = time.time()
            return AgentResult(
                success=False,
                error=subtask.error,
                duration_ms=subtask.timeout_seconds * 1000,
            )

        except Exception as exc:
            subtask.status = SubTaskStatus.FAILED
            subtask.error = str(exc)
            subtask.completed_at = time.time()
            return AgentResult(
                success=False,
                error=str(exc),
            )

    def get_registered_agents(self) -> List[Dict[str, Any]]:
        """List all registered agents and their capabilities."""
        return [
            {
                "name": name,
                "capabilities": caps,
            }
            for name, caps in self._agent_capabilities.items()
        ]


# ════════════════════════════════════════════════════════════════════
# ProgressTracker — Checkpoint + Resume + Progress Reporting
# ════════════════════════════════════════════════════════════════════


class ProgressTracker:
    """
    Tracks long-running task progress with durable checkpoints.

    Enables:
    - Crash recovery: resume from last checkpoint
    - Progress reporting: real-time progress percentage
    - Audit trail: full history of task execution
    """

    def __init__(self, name: str = "ProgressTracker"):
        self.name = name
        self._tasks: Dict[str, LongHorizonTask] = {}
        self._logger = logger.bind(component="progress_tracker")

    def register_task(self, task: LongHorizonTask) -> None:
        """Register a task for tracking."""
        self._tasks[task.task_id] = task
        self._logger.info("task_registered", task_id=task.task_id, goal=task.goal)

    def get_task(self, task_id: str) -> Optional[LongHorizonTask]:
        """Get a tracked task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[LongHorizonTask]:
        """List tracked tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]

    def save_checkpoint(self, task: LongHorizonTask) -> TaskCheckpoint:
        """Save a durable checkpoint of the current task state."""
        checkpoint = TaskCheckpoint(
            task_id=task.task_id,
            task_status=task.status,
            subtask_states={
                st.subtask_id: st.to_dict() for st in task.subtasks
            },
            aggregated_results=task.aggregated_result or {},
        )
        task.checkpoints.append(checkpoint)
        self._logger.info(
            "checkpoint_saved",
            task_id=task.task_id,
            checkpoint_id=checkpoint.checkpoint_id,
            progress_pct=task.progress_pct,
        )
        return checkpoint

    def restore_checkpoint(
        self,
        task: LongHorizonTask,
        checkpoint_id: Optional[str] = None,
    ) -> bool:
        """
        Restore task state from a checkpoint.

        If no checkpoint_id given, restores from the latest checkpoint.
        """
        if not task.checkpoints:
            self._logger.warning("no_checkpoints", task_id=task.task_id)
            return False

        if checkpoint_id:
            checkpoint = next(
                (cp for cp in task.checkpoints if cp.checkpoint_id == checkpoint_id),
                None,
            )
        else:
            checkpoint = task.checkpoints[-1]

        if not checkpoint:
            return False

        # Restore sub-task states
        for st in task.subtasks:
            state = checkpoint.subtask_states.get(st.subtask_id)
            if state:
                st.status = SubTaskStatus(state["status"])
                st.result = state.get("result")
                st.error = state.get("error")
                st.attempts = state.get("attempts", 0)

        task.aggregated_result = checkpoint.aggregated_results
        task.update_progress()

        self._logger.info(
            "checkpoint_restored",
            task_id=task.task_id,
            checkpoint_id=checkpoint.checkpoint_id,
        )
        return True

    def get_progress_report(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a detailed progress report for a task."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        task.update_progress()

        return {
            "task_id": task.task_id,
            "goal": task.goal,
            "status": task.status.value,
            "progress_pct": task.progress_pct,
            "subtasks": {
                "total": len(task.subtasks),
                "completed": sum(
                    1 for st in task.subtasks
                    if st.status == SubTaskStatus.COMPLETED
                ),
                "running": sum(
                    1 for st in task.subtasks
                    if st.status == SubTaskStatus.RUNNING
                ),
                "failed": sum(
                    1 for st in task.subtasks
                    if st.status == SubTaskStatus.FAILED
                ),
                "pending": sum(
                    1 for st in task.subtasks
                    if st.status == SubTaskStatus.PENDING
                ),
                "skipped": sum(
                    1 for st in task.subtasks
                    if st.status == SubTaskStatus.SKIPPED
                ),
            },
            "elapsed_seconds": (
                (task.completed_at or time.time()) - task.started_at
                if task.started_at else None
            ),
            "checkpoint_count": len(task.checkpoints),
            "error": task.error,
        }


# ════════════════════════════════════════════════════════════════════
# ResultAggregator — Combines Sub-Task Results
# ════════════════════════════════════════════════════════════════════


class ResultAggregator:
    """
    Combines sub-task results into a final aggregated output.

    Subclasses override _merge() for domain-specific aggregation
    (e.g., merging market analysis + credit score into a unified report).
    """

    def __init__(self, name: str = "ResultAggregator"):
        self.name = name
        self._logger = logger.bind(component="result_aggregator")

    def aggregate(self, task: LongHorizonTask) -> Dict[str, Any]:
        """
        Aggregate all completed sub-task results.

        Returns a merged result dictionary.
        """
        subtask_results = {}
        errors = {}

        for st in task.subtasks:
            if st.status == SubTaskStatus.COMPLETED and st.result:
                subtask_results[st.subtask_id] = {
                    "name": st.name,
                    "action": st.action,
                    "assigned_agent": st.assigned_agent,
                    "result": st.result,
                    "duration_seconds": (
                        (st.completed_at - st.started_at)
                        if st.started_at and st.completed_at else None
                    ),
                }
            elif st.status == SubTaskStatus.FAILED:
                errors[st.subtask_id] = {
                    "name": st.name,
                    "error": st.error,
                    "attempts": st.attempts,
                }

        aggregated = self._merge(subtask_results, errors)

        self._logger.info(
            "results_aggregated",
            task_id=task.task_id,
            successful=len(subtask_results),
            failed=len(errors),
        )

        return aggregated

    def _merge(
        self,
        results: Dict[str, Dict[str, Any]],
        errors: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Merge results from all sub-tasks.

        Override for domain-specific merging logic.
        Default: return all results with metadata.
        """
        return {
            "subtask_results": results,
            "errors": errors,
            "total_subtasks": len(results) + len(errors),
            "successful": len(results),
            "failed": len(errors),
            "aggregated_at": time.time(),
        }


# ════════════════════════════════════════════════════════════════════
# LongHorizonOrchestrator — Top-Level Coordinator
# ════════════════════════════════════════════════════════════════════


class LongHorizonOrchestrator:
    """
    Orchestrates long-running tasks (minutes to hours).

    Coordinates TaskPlanner, SubAgentDelegator, ProgressTracker,
    and ResultAggregator to execute complex multi-step workflows.

    Key DeerFlow patterns:
    1. Task decomposition into a DAG
    2. Parallel execution where dependencies allow
    3. Checkpointing for crash recovery
    4. Re-planning on failure
    5. Timeout / kill switch

    Usage:
        orchestrator = LongHorizonOrchestrator()
        orchestrator.delegator.register_agent(my_agent)
        task = await orchestrator.execute("Analyze market trends in Nairobi", context={})
        progress = orchestrator.tracker.get_progress_report(task.task_id)
    """

    def __init__(
        self,
        name: str = "LongHorizonOrchestrator",
        planner: Optional[TaskPlanner] = None,
        delegator: Optional[SubAgentDelegator] = None,
        tracker: Optional[ProgressTracker] = None,
        aggregator: Optional[ResultAggregator] = None,
        max_parallel: int = 5,
        checkpoint_interval: float = 60.0,  # seconds between auto-checkpoints
        event_store: Optional[EventStore] = None,
    ):
        self.name = name
        self.planner = planner or TaskPlanner()
        self.delegator = delegator or SubAgentDelegator()
        self.tracker = tracker or ProgressTracker()
        self.aggregator = aggregator or ResultAggregator()
        self._max_parallel = max_parallel
        self._checkpoint_interval = checkpoint_interval
        self._event_store = event_store
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._logger = logger.bind(component="long_horizon_orchestrator")

    async def execute(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = 3600.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LongHorizonTask:
        """
        Execute a long-horizon task.

        1. Plan: decompose goal into sub-tasks
        2. Execute: run sub-tasks respecting dependencies
        3. Checkpoint: save progress periodically
        4. Re-plan: handle failures
        5. Aggregate: combine results
        """
        ctx = context or {}

        # Create task
        task = LongHorizonTask(
            goal=goal,
            description=goal,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
        )
        task.status = TaskStatus.PLANNING
        task.started_at = time.time()

        self.tracker.register_task(task)

        self._logger.info(
            "task_started",
            task_id=task.task_id,
            goal=goal,
            timeout=timeout_seconds,
        )

        try:
            # 1. Plan
            available_agents = list(self.delegator._agents.keys())
            subtasks = await self.planner.plan(goal, ctx, available_agents)
            task.subtasks = subtasks
            task.status = TaskStatus.EXECUTING

            # Store in event store
            if self._event_store:
                from app.agents.base import AgentEvent as _AE
                await self._event_store.append(
                    _AE(
                        event_type=EventType.INTELLIGENCE_REQUESTED,
                        source=self.name,
                        payload={"task_id": task.task_id, "goal": goal, "subtask_count": len(subtasks)},
                    ),
                    aggregate_id=task.task_id,
                    aggregate_type="long_horizon_task",
                )

            # 2. Execute with dependency-aware parallel scheduling
            await self._execute_dag(task)

            # 3. Aggregate results
            task.status = TaskStatus.AGGREGATING
            task.aggregated_result = self.aggregator.aggregate(task)

            # 4. Finalize
            if task.is_complete():
                task.status = TaskStatus.COMPLETED
            elif task.has_failures():
                task.status = TaskStatus.FAILED
                task.error = "Some sub-tasks failed"

            task.completed_at = time.time()
            task.update_progress()

            # Final checkpoint
            self.tracker.save_checkpoint(task)

            self._logger.info(
                "task_completed",
                task_id=task.task_id,
                status=task.status.value,
                progress_pct=task.progress_pct,
                elapsed=(task.completed_at - task.started_at),
            )

        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMED_OUT
            task.error = f"Task timed out after {timeout_seconds}s"
            task.completed_at = time.time()
            self._logger.warning("task_timed_out", task_id=task.task_id)

        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.completed_at = time.time()
            self._logger.exception("task_failed", task_id=task.task_id, error=str(exc))

        return task

    async def _execute_dag(self, task: LongHorizonTask) -> None:
        """
        Execute sub-tasks respecting dependency ordering.

        Runs independent sub-tasks in parallel up to _max_parallel.
        """
        checkpoint_timer = 0.0
        last_checkpoint = time.time()

        while not task.is_complete() and not task.has_failures():
            # Check overall timeout
            elapsed = time.time() - task.started_at
            if elapsed > task.timeout_seconds:
                raise asyncio.TimeoutError()

            # Get ready sub-tasks
            ready = task.get_ready_subtasks()

            if not ready:
                # Check if anything is still running
                running = [
                    st for st in task.subtasks
                    if st.status == SubTaskStatus.RUNNING
                ]
                if not running:
                    # Nothing ready, nothing running — deadlock or all done
                    break
                # Wait a bit for running tasks
                await asyncio.sleep(0.5)
                continue

            # Launch up to max_parallel sub-tasks
            batch = ready[: self._max_parallel]
            tasks = []

            for st in batch:
                event = self._subtask_to_event(task, st)
                tasks.append(self._execute_subtask(task, st, event))

            # Wait for batch to complete
            await asyncio.gather(*tasks, return_exceptions=True)

            # Auto-checkpoint
            if time.time() - last_checkpoint > self._checkpoint_interval:
                self.tracker.save_checkpoint(task)
                last_checkpoint = time.time()

            # Re-plan on failures
            for st in task.subtasks:
                if st.status == SubTaskStatus.FAILED:
                    await self.planner.replan(task, st, {})

            task.update_progress()

    async def _execute_subtask(
        self,
        task: LongHorizonTask,
        subtask: SubTask,
        event: AgentEvent,
    ) -> None:
        """Execute a single sub-task via the delegator."""
        result = await self.delegator.delegate(subtask, event)

        # Publish result event
        if self._event_store:
            from app.agents.base import AgentEvent as _AE
            await self._event_store.append(
                _AE(
                    event_type=EventType.INTELLIGENCE_GENERATED if result.success else EventType.PIPELINE_ERROR,
                    source=subtask.assigned_agent or "unknown",
                    payload={
                        "subtask_id": subtask.subtask_id,
                        "task_id": task.task_id,
                        "success": result.success,
                        "error": result.error,
                    },
                ),
                aggregate_id=task.task_id,
                aggregate_type="long_horizon_task",
            )

    def _subtask_to_event(
        self,
        task: LongHorizonTask,
        subtask: SubTask,
    ) -> AgentEvent:
        """Convert a sub-task to an AgentEvent for the delegator."""
        return AgentEvent(
            event_type=EventType.INTELLIGENCE_REQUESTED,
            source=self.name,
            payload={
                "task_id": task.task_id,
                "subtask_id": subtask.subtask_id,
                "action": subtask.action,
                "parameters": subtask.parameters,
                "goal": task.goal,
            },
            correlation_id=task.task_id,
        )

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self.tracker.get_task(task_id)
        if not task or task.status not in (
            TaskStatus.PENDING, TaskStatus.PLANNING, TaskStatus.EXECUTING
        ):
            return False

        task.status = TaskStatus.CANCELLED
        task.completed_at = time.time()

        # Cancel any active asyncio tasks
        active = self._active_tasks.pop(task_id, None)
        if active and not active.done():
            active.cancel()

        self._logger.info("task_cancelled", task_id=task_id)
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        all_tasks = self.tracker.list_tasks(limit=100)
        return {
            "name": self.name,
            "registered_agents": self.delegator.get_registered_agents(),
            "active_tasks": sum(
                1 for t in all_tasks
                if t.status in (TaskStatus.EXECUTING, TaskStatus.PLANNING)
            ),
            "total_tasks": len(all_tasks),
            "completed_tasks": sum(
                1 for t in all_tasks if t.status == TaskStatus.COMPLETED
            ),
            "failed_tasks": sum(
                1 for t in all_tasks if t.status == TaskStatus.FAILED
            ),
            "max_parallel": self._max_parallel,
            "checkpoint_interval_seconds": self._checkpoint_interval,
        }
