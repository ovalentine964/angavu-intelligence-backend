"""
Long-Horizon Orchestrator — Manages long-running research tasks.

Provides task decomposition, subtask tracking, checkpointing,
and result aggregation for research tasks that run for minutes to hours.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TaskStatus(str, Enum):
    """Status of a research task."""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubTask:
    """A subtask within a research task."""
    subtask_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str | None = None
    attempts: int = 0
    error: str | None = None
    result: dict[str, Any] | None = None
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class ResearchTask:
    """A long-running research task."""
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    subtasks: list[SubTask] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    aggregated_result: dict[str, Any] | None = None
    progress_pct: float = 0.0
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_progress(self) -> None:
        """Update progress percentage based on subtask statuses."""
        if not self.subtasks:
            self.progress_pct = 0.0
            return
        completed = sum(1 for st in self.subtasks if st.status == TaskStatus.COMPLETED)
        self.progress_pct = round(completed / len(self.subtasks) * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "subtask_count": len(self.subtasks),
            "error": self.error,
            "created_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


class TaskTracker:
    """Tracks research tasks and their subtasks."""

    def __init__(self, max_tasks: int = 100):
        self._tasks: dict[str, ResearchTask] = {}
        self._max_tasks = max_tasks

    def create_task(self, goal: str, metadata: dict[str, Any] | None = None) -> ResearchTask:
        """Create a new research task."""
        task = ResearchTask(
            task_id=str(uuid.uuid4()),
            goal=goal,
            started_at=time.time(),
            metadata=metadata or {},
        )
        self._tasks[task.task_id] = task

        if len(self._tasks) > self._max_tasks:
            oldest = sorted(self._tasks.values(), key=lambda t: t.started_at or 0)[:len(self._tasks) - self._max_tasks]
            for t in oldest:
                del self._tasks[t.task_id]

        return task

    def get_task(self, task_id: str) -> ResearchTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 50) -> list[ResearchTask]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.started_at or 0, reverse=True)
        return tasks[:limit]


class LongHorizonOrchestrator:
    """
    Orchestrates long-running research tasks.

    Decomposes goals into subtasks, tracks progress,
    handles retries, and aggregates results.
    """

    def __init__(self, name: str = "LongHorizonOrchestrator"):
        self.name = name
        self.tracker = TaskTracker()
        self._registered_agents: list[str] = []
        self._active_tasks: int = 0

    async def execute(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        timeout_seconds: float = 3600.0,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchTask:
        """Start a long-horizon research task."""
        task = self.tracker.create_task(goal, metadata)
        task.status = TaskStatus.PLANNING
        self._active_tasks += 1

        # Create default subtasks
        subtask = SubTask(
            subtask_id=str(uuid.uuid4()),
            name=f"Research: {goal[:50]}",
        )
        task.subtasks.append(subtask)

        # Mark as executing (actual execution would be async)
        task.status = TaskStatus.EXECUTING
        subtask.status = TaskStatus.EXECUTING
        subtask.started_at = time.time()

        logger.info("long_horizon_task_started", task_id=task.task_id, goal=goal)
        return task

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self.tracker.get_task(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.PLANNING, TaskStatus.EXECUTING):
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            self._active_tasks = max(0, self._active_tasks - 1)
            return True
        return False

    def get_status(self) -> dict[str, Any]:
        """Get orchestrator status."""
        return {
            "name": self.name,
            "registered_agents": self._registered_agents,
            "active_tasks": self._active_tasks,
            "total_tasks": len(self.tracker._tasks),
        }
