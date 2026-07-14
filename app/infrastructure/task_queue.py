"""
Async Task Queue — Redis-based background job processing.

Lightweight alternative to Celery (which is overkill for current scale).
Designed for the Angavu Intelligence workload:
- Report generation (heavy, ~30s)
- Model training aggregation (~5min)
- Data aggregation (daily/weekly)
- Intelligence product updates (~10s)

Features:
- Priority queues: CRITICAL, HIGH, NORMAL, LOW
- Delayed tasks: scheduled execution (daily reports)
- Task result storage: retrieve results after completion
- Dead letter queue: failed tasks after max retries
- Task dependencies: wait for prerequisite tasks

Priority Queue Design (Queuing Theory):
    - CRITICAL: System alerts, fraud detection (p99 < 100ms)
    - HIGH: User-facing reports (p99 < 5s)
    - NORMAL: Background aggregation (p99 < 30s)
    - LOW: Analytics, model training (p99 < 5min)

    Using Redis Sorted Sets with priority as score ensures
    O(log N) enqueue and O(1) dequeue for highest priority.

References:
- Queuing Theory: M/M/c queue model for worker sizing
- Distributed Systems: At-least-once delivery with idempotent handlers
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class Priority(IntEnum):
    """Task priority levels. Lower number = higher priority."""
    CRITICAL = 0   # System alerts, fraud detection
    HIGH = 1       # User-facing reports
    NORMAL = 2     # Background aggregation
    LOW = 3        # Analytics, model training


class TaskStatus(str, Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


# Redis key patterns
TASK_KEY = "biashara:task:{task_id}"
QUEUE_KEY = "biashara:task_queue:{priority}"
RESULT_KEY = "biashara:task_result:{task_id}"
DEAD_LETTER_KEY = "biashara:task_dead_letter"
SCHEDULED_KEY = "biashara:task_scheduled"
TASK_INDEX_KEY = "biashara:task_index:{status}"

DEFAULT_MAX_RETRIES = 3
DEFAULT_RESULT_TTL = 86400      # 24 hours
DEFAULT_TASK_TTL = 172800       # 48 hours


@dataclass
class Task:
    """Represents a background task."""
    id: str
    type: str
    payload: Dict[str, Any]
    priority: Priority = Priority.NORMAL
    status: str = TaskStatus.PENDING
    created_at: float = 0.0
    updated_at: float = 0.0
    scheduled_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retries: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    error: Optional[str] = None
    result: Optional[Any] = None
    depends_on: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "priority": self.priority.value,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "error": self.error,
            "result": self.result,
            "depends_on": self.depends_on,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        data["priority"] = Priority(data.get("priority", Priority.NORMAL))
        return cls(**data)


# Type alias for task handlers
TaskHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Any]]


class AsyncTaskQueue:
    """
    Redis-based async task queue with priority support.

    Architecture:
    ┌──────────┐     ┌─────────────────┐     ┌──────────────┐
    │ Producer  │────▶│ Redis Sorted    │────▶│  Worker Pool │
    │ (API)     │     │ Set per Priority│     │  (N workers) │
    └──────────┘     └─────────────────┘     └──────────────┘
                            │                        │
                            ▼                        ▼
                     ┌─────────────┐         ┌─────────────┐
                     │  Scheduled  │         │   Results   │
                     │   (ZSET)    │         │   (HASH)    │
                     └─────────────┘         └─────────────┘

    Usage:
        queue = AsyncTaskQueue()
        await queue.connect()

        # Register handlers
        @queue.handler("report_generation")
        async def generate_report(payload):
            ...

        # Enqueue tasks
        task_id = await queue.enqueue("report_generation", {
            "business_id": "biz_123",
        }, priority=Priority.HIGH)

        # Start processing
        await queue.start_workers(concurrency=4)
    """

    def __init__(self, num_workers: int = 4):
        self._redis = None
        self._connected = False
        self._running = False
        self._num_workers = num_workers
        self._worker_tasks: List[asyncio.Task] = []
        self._handlers: Dict[str, TaskHandler] = {}

        # Metrics
        self._tasks_enqueued = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._tasks_dead_lettered = 0

        self._logger = logger.bind(component="async_task_queue")

    async def connect(self) -> None:
        """Connect to Redis."""
        if not settings.REDIS_URL:
            self._logger.warning("no_redis_url_task_queue_disabled")
            return

        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
            )
            await self._redis.ping()
            self._connected = True
            self._logger.info("async_task_queue_connected")
        except (ImportError, ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("async_task_queue_connect_failed", error=str(exc))

    async def disconnect(self) -> None:
        """Stop workers and close connection."""
        await self.stop_workers()
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._connected = False

    def handler(self, task_type: str):
        """Decorator to register a task handler."""
        def decorator(func: TaskHandler):
            self._handlers[task_type] = func
            self._logger.debug("handler_registered", task_type=task_type)
            return func
        return decorator

    # ── Enqueue ─────────────────────────────────────────────────────

    async def enqueue(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: Priority = Priority.NORMAL,
        scheduled_at: Optional[float] = None,
        depends_on: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Enqueue a new task.

        Args:
            task_type: Handler type (e.g., "report_generation")
            payload: Task-specific data
            priority: Task priority (CRITICAL, HIGH, NORMAL, LOW)
            scheduled_at: Unix timestamp for delayed execution
            depends_on: Task ID that must complete first
            max_retries: Max retry attempts on failure
            metadata: Additional metadata (user_id, trace_id, etc.)

        Returns:
            task_id for tracking
        """
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            type=task_type,
            payload=payload,
            priority=priority,
            scheduled_at=scheduled_at,
            depends_on=depends_on,
            max_retries=max_retries,
            metadata=metadata or {},
        )

        if not self._connected or not self._redis:
            # Inline execution fallback
            self._logger.info("task_inline_execution", task_type=task_type, task_id=task_id)
            asyncio.create_task(self._execute_inline(task))
            return task_id

        try:
            pipe = self._redis.pipeline(transaction=True)

            # Store task data
            pipe.set(
                TASK_KEY.format(task_id=task_id),
                json.dumps(task.to_dict(), default=str),
                ex=DEFAULT_TASK_TTL,
            )

            if scheduled_at and scheduled_at > time.time():
                # Delayed task — add to scheduled set
                pipe.zadd(SCHEDULED_KEY, {task_id: scheduled_at})
                task.status = TaskStatus.SCHEDULED
                self._logger.info("task_scheduled", task_id=task_id, at=scheduled_at)
            else:
                # Immediate — add to priority queue
                queue_key = QUEUE_KEY.format(priority=priority.value)
                pipe.lpush(queue_key, task_id)

                # Add to status index
                pipe.sadd(TASK_INDEX_KEY.format(status=TaskStatus.PENDING), task_id)

            pipe.execute()
            self._tasks_enqueued += 1

            self._logger.info(
                "task_enqueued",
                task_type=task_type,
                task_id=task_id,
                priority=priority.name,
            )
            return task_id

        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.error("task_enqueue_error", error=str(exc))
            asyncio.create_task(self._execute_inline(task))
            return task_id

    async def enqueue_batch(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Enqueue multiple tasks in a single pipeline.

        Args:
            tasks: List of dicts with keys: type, payload, priority, etc.

        Returns:
            List of task IDs
        """
        if not self._connected or not self._redis:
            return [await self.enqueue(**t) for t in tasks]

        task_ids = []
        try:
            pipe = self._redis.pipeline(transaction=True)

            for task_def in tasks:
                task_id = str(uuid.uuid4())
                task = Task(
                    id=task_id,
                    type=task_def["type"],
                    payload=task_def["payload"],
                    priority=task_def.get("priority", Priority.NORMAL),
                    scheduled_at=task_def.get("scheduled_at"),
                    depends_on=task_def.get("depends_on"),
                    max_retries=task_def.get("max_retries", DEFAULT_MAX_RETRIES),
                    metadata=task_def.get("metadata", {}),
                )

                pipe.set(
                    TASK_KEY.format(task_id=task_id),
                    json.dumps(task.to_dict(), default=str),
                    ex=DEFAULT_TASK_TTL,
                )

                queue_key = QUEUE_KEY.format(priority=task.priority.value)
                pipe.lpush(queue_key, task_id)
                task_ids.append(task_id)

            await pipe.execute()
            self._tasks_enqueued += len(task_ids)

        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.error("batch_enqueue_error", error=str(exc))

        return task_ids

    # ── Task Status ─────────────────────────────────────────────────

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        if not self._connected or not self._redis:
            return None

        try:
            raw = await self._redis.get(TASK_KEY.format(task_id=task_id))
            if raw:
                return Task.from_dict(json.loads(raw))
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("get_task_error", task_id=task_id, error=str(exc))
        return None

    async def get_result(self, task_id: str) -> Optional[Any]:
        """
        Get the result of a completed task.

        Returns None if the task hasn't completed yet.
        """
        task = await self.get_task(task_id)
        if task and task.status == TaskStatus.COMPLETED:
            return task.result
        return None

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending task."""
        task = await self.get_task(task_id)
        if not task or task.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
            return False

        task.status = TaskStatus.CANCELLED
        task.updated_at = time.time()

        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.set(
                TASK_KEY.format(task_id=task_id),
                json.dumps(task.to_dict(), default=str),
                ex=DEFAULT_TASK_TTL,
            )
            pipe.srem(TASK_INDEX_KEY.format(status=TaskStatus.PENDING), task_id)
            pipe.sadd(TASK_INDEX_KEY.format(status=TaskStatus.CANCELLED), task_id)
            await pipe.execute()
            return True
        except (ConnectionError, OSError, TimeoutError):
            return False

    # ── Workers ─────────────────────────────────────────────────────

    async def start_workers(self, concurrency: Optional[int] = None) -> None:
        """Start background worker tasks."""
        if self._running:
            return

        self._running = True
        num_workers = concurrency or self._num_workers

        # Worker per priority level
        for i in range(num_workers):
            task = asyncio.create_task(self._worker_loop(f"worker_{i}"))
            self._worker_tasks.append(task)

        # Scheduled task mover
        mover = asyncio.create_task(self._scheduled_mover_loop())
        self._worker_tasks.append(mover)

        self._logger.info("workers_started", count=num_workers)

    async def stop_workers(self) -> None:
        """Stop all workers gracefully."""
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        self._logger.info("workers_stopped")

    async def _worker_loop(self, worker_name: str) -> None:
        """
        Worker loop: dequeue and process tasks.

        Dequeues from highest priority first:
        CRITICAL → HIGH → NORMAL → LOW

        This implements priority scheduling per Queuing Theory:
        - Shortest Job First (SJF) approximation via priority
        - Prevents starvation by processing lower priorities
          when higher queues are empty
        """
        wlogger = self._logger.bind(worker=worker_name)

        while self._running and self._connected:
            task_id = None

            try:
                # Try each priority level (highest first)
                for priority in Priority:
                    queue_key = QUEUE_KEY.format(priority=priority.value)
                    result = await self._redis.rpop(queue_key)
                    if result:
                        task_id = result
                        break

                if not task_id:
                    # No tasks in any queue — wait briefly
                    await asyncio.sleep(0.5)
                    continue

                # Get task data
                task = await self.get_task(task_id)
                if not task:
                    continue

                # Skip cancelled tasks
                if task.status == TaskStatus.CANCELLED:
                    continue

                # Check dependencies
                if task.depends_on:
                    dep = await self.get_task(task.depends_on)
                    if dep and dep.status != TaskStatus.COMPLETED:
                        # Re-enqueue and wait
                        queue_key = QUEUE_KEY.format(priority=task.priority.value)
                        await self._redis.lpush(queue_key, task_id)
                        await asyncio.sleep(1)
                        continue

                # Execute
                await self._execute_task(task, wlogger)

            except asyncio.CancelledError:
                break
            except (ConnectionError, OSError, TimeoutError) as exc:
                wlogger.warning("worker_error", error=str(exc))
                await asyncio.sleep(1)
            except Exception as exc:
                wlogger.error("worker_unexpected_error", error=str(exc), exc_info=True)
                await asyncio.sleep(1)

    async def _execute_task(self, task: Task, wlogger) -> None:
        """Execute a single task and update its status."""
        handler = self._handlers.get(task.type)
        if not handler:
            wlogger.warning("no_handler", task_type=task.type, task_id=task.id)
            await self._mark_failed(task, f"No handler for task type: {task.type}")
            return

        # Mark as running
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        task.updated_at = time.time()
        await self._save_task(task)

        try:
            result = await handler(task.payload)

            # Mark as completed
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()
            task.updated_at = time.time()
            await self._save_task(task)

            # Store result separately (with shorter TTL)
            if self._redis:
                await self._redis.set(
                    RESULT_KEY.format(task_id=task.id),
                    json.dumps(result, default=str),
                    ex=DEFAULT_RESULT_TTL,
                )

            self._tasks_completed += 1
            wlogger.info("task_completed", task_type=task.type, task_id=task.id)

        except Exception as exc:
            wlogger.warning("task_failed", task_type=task.type, task_id=task.id, error=str(exc))
            await self._handle_failure(task, str(exc))

    async def _handle_failure(self, task: Task, error: str) -> None:
        """Handle task failure — retry with exponential backoff or dead letter."""
        task.retries += 1
        task.error = error

        if task.retries < task.max_retries:
            # Exponential backoff: delay = base * 2^(retry-1), capped at 5 minutes
            backoff_delay = min(300, 2 ** (task.retries - 1))  # 1s, 2s, 4s, 8s, ... max 300s
            scheduled_time = time.time() + backoff_delay

            # Use scheduled set for delayed retry
            task.status = TaskStatus.SCHEDULED
            task.scheduled_at = scheduled_time
            task.updated_at = time.time()
            await self._save_task(task)

            await self._redis.zadd(SCHEDULED_KEY, {task.id: scheduled_time})
            self._logger.info(
                "task_retry_scheduled",
                task_id=task.id,
                retry=task.retries,
                backoff_seconds=backoff_delay,
            )
        else:
            # Dead letter
            await self._mark_dead_lettered(task, error)

    async def _mark_failed(self, task: Task, error: str) -> None:
        """Mark a task as permanently failed."""
        task.status = TaskStatus.FAILED
        task.error = error
        task.updated_at = time.time()
        await self._save_task(task)
        self._tasks_failed += 1

    async def _mark_dead_lettered(self, task: Task, error: str) -> None:
        """Move a task to the dead letter queue."""
        task.status = TaskStatus.DEAD_LETTERED
        task.error = error
        task.updated_at = time.time()
        await self._save_task(task)

        # Add to dead letter set
        if self._redis:
            await self._redis.zadd(
                DEAD_LETTER_KEY,
                {task.id: time.time()},
            )

        self._tasks_dead_lettered += 1
        self._logger.error(
            "task_dead_lettered",
            task_type=task.type,
            task_id=task.id,
            error=error,
            retries=task.retries,
        )

    async def _save_task(self, task: Task) -> None:
        """Save task state to Redis."""
        if not self._redis:
            return
        try:
            await self._redis.set(
                TASK_KEY.format(task_id=task.id),
                json.dumps(task.to_dict(), default=str),
                ex=DEFAULT_TASK_TTL,
            )
        except (ConnectionError, OSError, TimeoutError):
            pass

    async def _execute_inline(self, task: Task) -> None:
        """Execute a task inline (fallback when Redis is unavailable)."""
        handler = self._handlers.get(task.type)
        if not handler:
            self._logger.warning("inline_no_handler", task_type=task.type)
            return

        try:
            result = await handler(task.payload)
            self._logger.info("task_inline_completed", task_type=task.type, task_id=task.id)
        except Exception as exc:
            self._logger.error("task_inline_error", task_id=task.id, error=str(exc))

    # ── Scheduled Task Mover ────────────────────────────────────────

    async def _scheduled_mover_loop(self) -> None:
        """
        Periodically moves scheduled tasks to the active queue
        when their scheduled time has arrived.
        """
        while self._running and self._connected:
            try:
                now = time.time()

                # Get tasks whose scheduled time has passed
                due_tasks = await self._redis.zrangebyscore(
                    SCHEDULED_KEY, 0, now, start=0, num=100,
                )

                for task_id in due_tasks:
                    task = await self.get_task(task_id)
                    if not task:
                        # Remove orphaned scheduled entry
                        await self._redis.zrem(SCHEDULED_KEY, task_id)
                        continue

                    # Move to active queue
                    queue_key = QUEUE_KEY.format(priority=task.priority.value)
                    pipe = self._redis.pipeline(transaction=True)
                    pipe.lpush(queue_key, task_id)
                    pipe.zrem(SCHEDULED_KEY, task_id)

                    task.status = TaskStatus.PENDING
                    task.updated_at = now
                    pipe.set(
                        TASK_KEY.format(task_id=task_id),
                        json.dumps(task.to_dict(), default=str),
                        ex=DEFAULT_TASK_TTL,
                    )

                    await pipe.execute()
                    self._logger.info("scheduled_task_moved", task_id=task_id)

                await asyncio.sleep(1)  # Check every second

            except asyncio.CancelledError:
                break
            except (ConnectionError, OSError, TimeoutError) as exc:
                self._logger.warning("scheduled_mover_error", error=str(exc))
                await asyncio.sleep(5)
            except Exception as exc:
                self._logger.error("scheduled_mover_unexpected_error", error=str(exc))
                await asyncio.sleep(5)

    # ── Monitoring ──────────────────────────────────────────────────

    async def get_queue_depths(self) -> Dict[str, int]:
        """Get the depth of each priority queue."""
        if not self._connected or not self._redis:
            return {}

        depths = {}
        for priority in Priority:
            queue_key = QUEUE_KEY.format(priority=priority.value)
            depth = await self._redis.llen(queue_key)
            depths[priority.name] = depth

        return depths

    async def get_dead_letters(self, limit: int = 50) -> List[Task]:
        """Get tasks in the dead letter queue."""
        if not self._connected or not self._redis:
            return []

        try:
            task_ids = await self._redis.zrevrange(DEAD_LETTER_KEY, 0, limit - 1)
            tasks = []
            for tid in task_ids:
                task = await self.get_task(tid)
                if task:
                    tasks.append(task)
            return tasks
        except (ConnectionError, OSError, TimeoutError):
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "connected": self._connected,
            "running": self._running,
            "workers": len(self._worker_tasks),
            "handlers": list(self._handlers.keys()),
            "tasks_enqueued": self._tasks_enqueued,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "tasks_dead_lettered": self._tasks_dead_lettered,
        }


# ── Singleton ──────────────────────────────────────────────────────

_async_queue: Optional[AsyncTaskQueue] = None


def get_async_task_queue() -> AsyncTaskQueue:
    """Get the singleton AsyncTaskQueue."""
    global _async_queue
    if _async_queue is None:
        _async_queue = AsyncTaskQueue()
    return _async_queue
