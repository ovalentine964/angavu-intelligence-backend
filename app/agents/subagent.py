"""
SubAgent Orchestrator — Push-Based Sub-Agent Lifecycle Management.

Implements the sub-agent spawning and completion pattern:
- Parent agent spawns sub-agents for parallel or sequential sub-tasks
- Sub-agents execute autonomously and push results back on completion
- Parent aggregates results without busy-polling
- Supports depth-limited recursion (sub-agents can spawn their own sub-agents)

Architecture:
    Parent Agent
         ├── spawn SubAgent A ──→ [execute] ──→ push result back
         ├── spawn SubAgent B ──→ [execute] ──→ push result back
         └── spawn SubAgent C ──→ [execute] ──→ push result back
                                         │
                                    Parent aggregates
                                    all results

Key design principles:
1. Push-based: sub-agents push results, parent doesn't poll
2. Fire-and-forget with optional await: parent can continue or wait
3. Depth-limited: prevents runaway recursion
4. Resource-bounded: max concurrent sub-agents per parent
5. Failure-isolated: one sub-agent failure doesn't crash parent
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from app.agents.base import AgentEvent, BiasharaAgent, EventType

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Sub-Agent Types
# ════════════════════════════════════════════════════════════════════


class SubAgentStatus(str, Enum):
    """Lifecycle status of a sub-agent."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class SubAgentPriority(int, Enum):
    """Priority levels for sub-agent execution."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class SubAgentTask:
    """
    A task definition for a sub-agent.

    Contains everything the sub-agent needs to execute:
    - The task description and parameters
    - The agent class or handler to use
    - Timeout and retry configuration
    """
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    handler: Callable[..., Coroutine] | None = None
    agent: BiasharaAgent | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    priority: SubAgentPriority = SubAgentPriority.NORMAL
    timeout_seconds: float = 60.0
    max_retries: int = 0
    parent_task_id: str | None = None
    depth: int = 0  # How deep in the sub-agent tree
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize sub-agent task to dictionary."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "parameters": {k: str(v)[:100] for k, v in self.parameters.items()},
            "priority": self.priority.value,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "parent_task_id": self.parent_task_id,
            "depth": self.depth,
            "tags": self.tags,
        }


@dataclass
class SubAgentResult:
    """
    Result from a completed sub-agent.

    Pushed back to the parent when the sub-agent finishes.
    """
    task_id: str = ""
    status: SubAgentStatus = SubAgentStatus.COMPLETED
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    attempts: int = 1
    sub_results: list[SubAgentResult] = field(default_factory=list)  # Nested results

    @property
    def success(self) -> bool:
        """Check if the sub-agent completed successfully."""
        return self.status == SubAgentStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        """Serialize sub-agent result to dictionary."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "success": self.success,
            "data_summary": str(self.data)[:200] if self.data else None,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 1),
            "attempts": self.attempts,
            "sub_results_count": len(self.sub_results),
        }


@dataclass
class SubAgentMetrics:
    """Aggregated sub-agent orchestration metrics."""
    total_spawned: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_timed_out: int = 0
    total_cancelled: int = 0
    avg_duration_ms: float = 0.0
    max_concurrent: int = 0
    current_concurrent: int = 0
    total_retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_spawned": self.total_spawned,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
            "total_timed_out": self.total_timed_out,
            "total_cancelled": self.total_cancelled,
            "success_rate": round(
                self.total_completed / max(1, self.total_spawned), 3
            ),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "max_concurrent": self.max_concurrent,
            "current_concurrent": self.current_concurrent,
            "total_retries": self.total_retries,
        }


# ════════════════════════════════════════════════════════════════════
# SubAgentOrchestrator
# ════════════════════════════════════════════════════════════════════


class SubAgentOrchestrator:
    """
    Orchestrates sub-agent spawning, execution, and result aggregation.

    Push-based pattern: sub-agents push results back to the parent
    via asyncio futures. The parent either awaits specific results
    or collects all results when they're ready.

    Features:
    - Push-based completion (no busy-polling)
    - Configurable max concurrency
    - Depth-limited recursion (sub-agents can spawn sub-sub-agents)
    - Timeout per sub-agent
    - Automatic retry on failure
    - Result aggregation
    - Cancellation support
    - Resource tracking

    Usage:
        orchestrator = SubAgentOrchestrator(
            parent_agent=my_agent,
            max_concurrency=5,
            max_depth=3,
        )

        # Spawn sub-agents
        task_a = orchestrator.spawn(
            name="analyze_market",
            handler=market_analysis_handler,
            parameters={"item": "nyanya"},
        )
        task_b = orchestrator.spawn(
            name="check_inventory",
            handler=inventory_handler,
            parameters={"warehouse": "nairobi"},
        )

        # Wait for all results (push-based — no polling)
        results = await orchestrator.wait_all()

        # Or wait for specific result
        result_a = await orchestrator.wait_for(task_a)
    """

    def __init__(
        self,
        parent_agent: BiasharaAgent | None = None,
        max_concurrency: int = 10,
        max_depth: int = 3,
        default_timeout: float = 60.0,
    ):
        self._parent = parent_agent
        self._parent_name = parent_agent.name if parent_agent else "root"
        self._max_concurrency = max_concurrency
        self._max_depth = max_depth
        self._default_timeout = default_timeout

        # Active sub-agents
        self._tasks: dict[str, SubAgentTask] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._results: dict[str, SubAgentResult] = {}
        self._running: set[str] = set()

        # Metrics
        self._metrics = SubAgentMetrics()

        # Semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrency)

        self._logger = logger.bind(
            component="subagent_orchestrator",
            parent=self._parent_name,
        )

    # ── Spawning ────────────────────────────────────────────────────

    def spawn(
        self,
        name: str,
        handler: Callable[..., Coroutine] | None = None,
        agent: BiasharaAgent | None = None,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
        priority: SubAgentPriority = SubAgentPriority.NORMAL,
        max_retries: int = 0,
        tags: list[str] | None = None,
    ) -> str:
        """
        Spawn a sub-agent for a task.

        The sub-agent will execute asynchronously and push its
        result back when complete. Returns a task_id that can
        be used to await the specific result.

        Args:
            name: Human-readable task name
            handler: Async function to execute
            agent: BiasharaAgent to use (alternative to handler)
            parameters: Parameters for the handler/agent
            timeout_seconds: Max execution time
            priority: Task priority
            max_retries: Number of retries on failure
            tags: Tags for categorization

        Returns:
            task_id for awaiting the result
        """
        # Check depth limit
        parent_task_id = None
        depth = 0
        if self._parent and hasattr(self._parent, '_current_subagent_depth'):
            depth = self._parent._current_subagent_depth + 1

        if depth > self._max_depth:
            self._logger.warning(
                "subagent_depth_exceeded",
                depth=depth,
                max_depth=self._max_depth,
            )
            raise RuntimeError(
                f"Sub-agent depth {depth} exceeds maximum {self._max_depth}"
            )

        task = SubAgentTask(
            name=name,
            description=f"Sub-task: {name}",
            handler=handler,
            agent=agent,
            parameters=parameters or {},
            priority=priority,
            timeout_seconds=timeout_seconds or self._default_timeout,
            max_retries=max_retries,
            parent_task_id=parent_task_id,
            depth=depth,
            tags=tags or [],
        )

        self._tasks[task.task_id] = task

        # Create a future for push-based completion
        loop = asyncio.get_event_loop()
        self._futures[task.task_id] = loop.create_future()

        # Schedule execution
        asyncio.create_task(self._execute_with_semaphore(task))

        self._metrics.total_spawned += 1
        self._logger.info(
            "subagent_spawned",
            task_id=task.task_id,
            name=name,
            depth=depth,
            priority=priority.value,
        )

        return task.task_id

    async def _execute_with_semaphore(self, task: SubAgentTask) -> None:
        """Execute a sub-agent with concurrency control."""
        async with self._semaphore:
            await self._execute(task)

    async def _execute(self, task: SubAgentTask) -> None:
        """Execute a sub-agent task with timeout and retry."""
        self._running.add(task.task_id)
        self._metrics.current_concurrent = len(self._running)
        self._metrics.max_concurrent = max(
            self._metrics.max_concurrent,
            self._metrics.current_concurrent,
        )

        attempts = 0
        last_error = None

        while attempts <= task.max_retries:
            attempts += 1
            start_time = time.time()

            try:
                # Execute with timeout
                if task.handler:
                    result_data = await asyncio.wait_for(
                        task.handler(**task.parameters),
                        timeout=task.timeout_seconds,
                    )
                elif task.agent:
                    # Create event from parameters
                    event = AgentEvent(
                        event_type=EventType.INTELLIGENCE_REQUESTED,
                        source=self._parent_name,
                        payload=task.parameters,
                    )
                    agent_result = await asyncio.wait_for(
                        task.agent.handle_event(event),
                        timeout=task.timeout_seconds,
                    )
                    result_data = agent_result.data if agent_result.success else agent_result.error
                    if not agent_result.success:
                        raise RuntimeError(str(agent_result.error))
                else:
                    raise ValueError(f"No handler or agent for task {task.name}")

                # Success — push result
                duration_ms = (time.time() - start_time) * 1000
                result = SubAgentResult(
                    task_id=task.task_id,
                    status=SubAgentStatus.COMPLETED,
                    data=result_data,
                    duration_ms=duration_ms,
                    started_at=start_time,
                    completed_at=time.time(),
                    attempts=attempts,
                )

                self._push_result(task.task_id, result)
                return

            except TimeoutError:
                last_error = f"Timeout after {task.timeout_seconds}s"
                self._logger.warning(
                    "subagent_timeout",
                    task_id=task.task_id,
                    attempt=attempts,
                    timeout=task.timeout_seconds,
                )
                if attempts <= task.max_retries:
                    self._metrics.total_retries += 1
                    continue

                # Final timeout
                result = SubAgentResult(
                    task_id=task.task_id,
                    status=SubAgentStatus.TIMED_OUT,
                    error=last_error,
                    duration_ms=(time.time() - start_time) * 1000,
                    started_at=start_time,
                    completed_at=time.time(),
                    attempts=attempts,
                )
                self._push_result(task.task_id, result)
                return

            except Exception as exc:
                last_error = str(exc)
                self._logger.warning(
                    "subagent_error",
                    task_id=task.task_id,
                    attempt=attempts,
                    error=last_error,
                )
                if attempts <= task.max_retries:
                    self._metrics.total_retries += 1
                    continue

                # Final failure
                result = SubAgentResult(
                    task_id=task.task_id,
                    status=SubAgentStatus.FAILED,
                    error=last_error,
                    duration_ms=(time.time() - start_time) * 1000,
                    started_at=start_time,
                    completed_at=time.time(),
                    attempts=attempts,
                )
                self._push_result(task.task_id, result)
                return

    def _push_result(self, task_id: str, result: SubAgentResult) -> None:
        """Push a result to the waiting future (push-based completion)."""
        self._results[task_id] = result
        self._running.discard(task_id)
        self._metrics.current_concurrent = len(self._running)

        # Update metrics
        if result.success:
            self._metrics.total_completed += 1
        elif result.status == SubAgentStatus.TIMED_OUT:
            self._metrics.total_timed_out += 1
        else:
            self._metrics.total_failed += 1

        # Update running average duration
        n = self._metrics.total_completed + self._metrics.total_failed + self._metrics.total_timed_out
        self._metrics.avg_duration_ms = (
            self._metrics.avg_duration_ms + (result.duration_ms - self._metrics.avg_duration_ms) / n
        )

        # Resolve the future (push-based notification)
        future = self._futures.get(task_id)
        if future and not future.done():
            future.set_result(result)

        self._logger.info(
            "subagent_completed",
            task_id=task_id,
            status=result.status.value,
            duration_ms=round(result.duration_ms, 1),
            attempts=result.attempts,
        )

    # ── Awaiting Results ────────────────────────────────────────────

    async def wait_for(self, task_id: str) -> SubAgentResult:
        """
        Wait for a specific sub-agent to complete.

        Push-based: this just awaits the future that the sub-agent
        will resolve when it finishes. No polling involved.
        """
        future = self._futures.get(task_id)
        if not future:
            # Already completed
            if task_id in self._results:
                return self._results[task_id]
            raise ValueError(f"Unknown task_id: {task_id}")

        return await future

    async def wait_all(
        self,
        timeout_seconds: float | None = None,
    ) -> list[SubAgentResult]:
        """
        Wait for all spawned sub-agents to complete.

        Push-based: awaits all futures simultaneously.
        """
        if not self._futures:
            return []

        futures = list(self._futures.values())

        if timeout_seconds:
            done, pending = await asyncio.wait(
                futures, timeout=timeout_seconds, return_when=asyncio.ALL_COMPLETED
            )
            # Cancel pending
            for f in pending:
                if not f.done():
                    f.cancel()
        else:
            await asyncio.gather(*futures, return_exceptions=True)

        return [self._results[tid] for tid in self._tasks if tid in self._results]

    async def wait_first(
        self,
        timeout_seconds: float | None = None,
    ) -> SubAgentResult | None:
        """Wait for the first sub-agent to complete."""
        if not self._futures:
            return None

        futures = list(self._futures.values())
        done, _ = await asyncio.wait(
            futures,
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if done:
            return done.pop().result()
        return None

    # ── Cancellation ────────────────────────────────────────────────

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running sub-agent."""
        future = self._futures.get(task_id)
        if future and not future.done():
            future.cancel()

        result = SubAgentResult(
            task_id=task_id,
            status=SubAgentStatus.CANCELLED,
            error="Cancelled by parent",
        )
        self._push_result(task_id, result)
        self._metrics.total_cancelled += 1
        return True

    async def cancel_all(self) -> int:
        """Cancel all running sub-agents."""
        cancelled = 0
        for task_id in list(self._running):
            await self.cancel(task_id)
            cancelled += 1
        return cancelled

    # ── Query ───────────────────────────────────────────────────────

    def get_result(self, task_id: str) -> SubAgentResult | None:
        """Get a cached result (doesn't wait)."""
        return self._results.get(task_id)

    def get_pending_tasks(self) -> list[dict[str, Any]]:
        """Get list of pending/running tasks."""
        return [
            t.to_dict() for t in self._tasks.values()
            if t.task_id in self._running
        ]

    def get_all_results(self) -> list[SubAgentResult]:
        """Get all completed results."""
        return list(self._results.values())

    def get_metrics(self) -> dict[str, Any]:
        """Get orchestration metrics."""
        return self._metrics.to_dict()

    def get_stats(self) -> dict[str, Any]:
        """Get full orchestrator statistics."""
        return {
            "parent": self._parent_name,
            "max_concurrency": self._max_concurrency,
            "max_depth": self._max_depth,
            "tasks": len(self._tasks),
            "running": len(self._running),
            "completed": len(self._results),
            "metrics": self._metrics.to_dict(),
        }

    @property
    def is_idle(self) -> bool:
        """Check if all sub-agents have completed."""
        return len(self._running) == 0

    @property
    def pending_count(self) -> int:
        """Number of currently running sub-agents."""
        return len(self._running)


# ════════════════════════════════════════════════════════════════════
# Convenience: Sub-agent-aware BiasharaAgent mixin
# ════════════════════════════════════════════════════════════════════


class SubAgentCapableMixin:
    """
    Mixin that adds sub-agent spawning capabilities to any agent.

    Usage:
        class MyAgent(SubAgentCapableMixin, BiasharaAgent):
            async def handle_event(self, event):
                orch = self.get_or_create_orchestrator()
                task_id = orch.spawn("analyze", handler=my_handler)
                result = await orch.wait_for(task_id)
    """

    _orchestrator: SubAgentOrchestrator | None = None
    _current_subagent_depth: int = 0

    def get_or_create_orchestrator(
        self,
        max_concurrency: int = 10,
        max_depth: int = 3,
    ) -> SubAgentOrchestrator:
        """Get or create the sub-agent orchestrator for this agent."""
        if self._orchestrator is None:
            self._orchestrator = SubAgentOrchestrator(
                parent_agent=self if isinstance(self, BiasharaAgent) else None,
                max_concurrency=max_concurrency,
                max_depth=max_depth,
            )
        return self._orchestrator

    def get_subagent_metrics(self) -> dict[str, Any]:
        """Get sub-agent metrics if orchestrator exists."""
        if self._orchestrator:
            return self._orchestrator.get_metrics()
        return {}
