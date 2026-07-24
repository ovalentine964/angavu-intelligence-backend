"""
Long-Horizon Research — Orchestrates long-running research tasks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class TaskStatus(str, Enum):
    """Status of a long-horizon research task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ResearchTask:
    """A long-running research task."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    results: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: Optional[str] = None


class LongHorizonOrchestrator:
    """
    Orchestrates long-running research tasks.

    Manages task lifecycle, progress tracking, and result collection
    for complex multi-step research workflows.
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._tasks: dict[str, ResearchTask] = {}

    async def start_task(self, task_type: str, params: dict = None) -> ResearchTask:
        """Start a new research task."""
        task = ResearchTask(task_type=task_type, status=TaskStatus.RUNNING)
        self._tasks[task.task_id] = task
        logger.info("research_task_started", task_id=task.task_id, type=task_type)
        return task

    async def get_status(self, task_id: str) -> Optional[dict]:
        """Get task status."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status.value,
            "progress": task.progress,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }

    async def get_results(self, task_id: str) -> Optional[dict]:
        """Get task results."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "results": task.results,
        }

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.CANCELLED
            return True
        return False

    def list_tasks(self) -> list[dict]:
        """List all tasks."""
        return [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "status": t.status.value,
                "progress": t.progress,
            }
            for t in self._tasks.values()
        ]

    def get_health(self) -> dict:
        """Get orchestrator health."""
        statuses = {}
        for t in self._tasks.values():
            statuses[t.status.value] = statuses.get(t.status.value, 0) + 1
        return {
            "name": self.name,
            "total_tasks": len(self._tasks),
            "status_breakdown": statuses,
        }
