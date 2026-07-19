"""
Background task queue for Angavu Intelligence.

Uses Redis as a lightweight task broker to manage async work:
    - Report generation (heavy computation)
    - Model training (federated learning aggregation)
    - Data aggregation (daily / weekly / monthly)
    - Intelligence product updates

Task Lifecycle:
    PENDING → RUNNING → COMPLETED
                    ↘ FAILED → (retry up to max_retries)

When Redis is unavailable, tasks execute inline (synchronous fallback).
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from enum import Enum

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Task status constants
TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELLED = "cancelled"

# Redis key prefixes
TASK_KEY_PREFIX = "task:"
TASK_QUEUE_KEY = "biashara:task_queue"
TASK_RESULT_PREFIX = "task_result:"

# Default max retries for failed tasks
DEFAULT_MAX_RETRIES = 3


class TaskType(str, Enum):
    """Supported background task types."""
    REPORT_GENERATION = "report_generation"
    MODEL_TRAINING = "model_training"
    DATA_AGGREGATION = "data_aggregation"
    INTELLIGENCE_UPDATE = "intelligence_update"
    PRICE_AGGREGATION = "price_aggregation"
    CACHE_WARMUP = "cache_warmup"


# Task handler registry — maps task types to async callables
_task_handlers: dict[str, Callable[..., Coroutine]] = {}


def register_handler(task_type: str):
    """Decorator to register a handler function for a task type."""
    def decorator(func: Callable[..., Coroutine]):
        _task_handlers[task_type] = func
        return func
    return decorator


class TaskQueue:
    """
    Background task queue backed by Redis Lists.

    Usage:
        queue = TaskQueue()
        await queue.connect()

        # Enqueue a task
        task_id = await queue.enqueue("report_generation", {
            "business_id": "biz_123",
            "report_type": "monthly",
        })

        # Check status
        status = await queue.get_status(task_id)

        # Cancel if needed
        await queue.cancel(task_id)
    """

    def __init__(self):
        self._redis: aioredis.Redis | None = None
        self._connected = False
        self._worker_task: asyncio.Task | None = None
        self._running = False

    async def connect(self) -> None:
        """Connect to Redis for task storage."""
        if not settings.REDIS_URL:
            logger.warning("REDIS_URL not set — task queue will run tasks inline (no background processing)")
            self._connected = True
            return

        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            await self._redis.ping()
            self._connected = True
            logger.info("task_queue_connected")
        except Exception as exc:
            logger.warning("task_queue_connection_failed", error=str(exc))
            self._connected = True  # Still mark connected — will use inline fallback

    async def close(self) -> None:
        """Shut down the task queue and stop the worker loop."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.close()
        self._connected = False

    # ------------------------------------------------------------------
    # Task Management
    # ------------------------------------------------------------------

    async def enqueue(self, task_type: str, payload: dict, priority: int = 0) -> str:
        """
        Enqueue a new background task.

        Args:
            task_type: One of TaskType values (e.g., "report_generation")
            payload: Task-specific data
            priority: Lower number = higher priority (default: 0)

        Returns:
            task_id: Unique identifier for tracking the task
        """
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "type": task_type,
            "payload": payload,
            "status": TASK_STATUS_PENDING,
            "priority": priority,
            "created_at": time.time(),
            "updated_at": time.time(),
            "retries": 0,
            "max_retries": DEFAULT_MAX_RETRIES,
            "error": None,
            "result": None,
        }

        if not self._redis:
            # Inline execution fallback (no Redis available)
            logger.info("task_inline_execution", task_type=task_type, task_id=task_id)
            asyncio.create_task(self._execute_inline(task))
            return task_id

        try:
            # Store task metadata
            await self._redis.set(
                f"{TASK_KEY_PREFIX}{task_id}",
                json.dumps(task, default=str),
                ex=86400,  # Expire after 24 hours
            )
            # Push to the queue (sorted by priority via LPUSH for FIFO)
            await self._redis.lpush(TASK_QUEUE_KEY, task_id)
            logger.info("task_enqueued", task_type=task_type, task_id=task_id)
            return task_id
        except Exception as exc:
            logger.error("task_enqueue_error", error=str(exc))
            # Fallback to inline execution
            asyncio.create_task(self._execute_inline(task))
            return task_id

    async def get_status(self, task_id: str) -> dict:
        """
        Get the current status of a task.

        Returns:
            dict with keys: id, type, status, created_at, updated_at,
                            retries, error, result
        """
        if not self._redis:
            return {"id": task_id, "status": "unknown", "error": "Redis not available"}

        try:
            raw = await self._redis.get(f"{TASK_KEY_PREFIX}{task_id}")
            if raw is None:
                return {"id": task_id, "status": "not_found"}
            return json.loads(raw)
        except Exception as exc:
            logger.warning("task_status_error", task_id=task_id, error=str(exc))
            return {"id": task_id, "status": "error", "error": str(exc)}

    async def cancel(self, task_id: str) -> bool:
        """
        Cancel a pending task.

        Running tasks cannot be cancelled (they'll complete or fail).
        Returns True if the task was cancelled.
        """
        try:
            task = await self.get_status(task_id)
            if task.get("status") == TASK_STATUS_PENDING:
                task["status"] = TASK_STATUS_CANCELLED
                task["updated_at"] = time.time()
                if self._redis:
                    await self._redis.set(
                        f"{TASK_KEY_PREFIX}{task_id}",
                        json.dumps(task, default=str),
                        ex=86400,
                    )
                logger.info("task_cancelled", task_id=task_id)
                return True
            return False
        except Exception as exc:
            logger.warning("task_cancel_error", task_id=task_id, error=str(exc))
            return False

    async def list_pending(self, limit: int = 50) -> list[dict]:
        """List pending tasks (for monitoring / dashboard)."""
        if not self._redis:
            return []

        try:
            task_ids = await self._redis.lrange(TASK_QUEUE_KEY, 0, limit - 1)
            tasks = []
            for tid in task_ids:
                raw = await self._redis.get(f"{TASK_KEY_PREFIX}{tid}")
                if raw:
                    tasks.append(json.loads(raw))
            return tasks
        except Exception as exc:
            logger.warning("task_list_error", error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Worker Loop
    # ------------------------------------------------------------------

    async def start_worker(self) -> None:
        """Start the background worker that processes tasks from the queue."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("task_worker_started")

    async def _worker_loop(self) -> None:
        """Main worker loop — pops tasks from Redis and executes them."""
        while self._running and self._redis:
            try:
                # Block-pop from queue (timeout: 5 seconds)
                result = await self._redis.brpop(TASK_QUEUE_KEY, timeout=5)
                if result is None:
                    continue

                _, task_id = result
                await self._process_task(task_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("task_worker_error", error=str(exc))
                await asyncio.sleep(1)

    async def _process_task(self, task_id: str) -> None:
        """Process a single task by its ID."""
        try:
            raw = await self._redis.get(f"{TASK_KEY_PREFIX}{task_id}")
            if raw is None:
                logger.warning("task_not_found", task_id=task_id)
                return

            task = json.loads(raw)

            # Skip cancelled tasks
            if task["status"] == TASK_STATUS_CANCELLED:
                return

            # Mark as running
            task["status"] = TASK_STATUS_RUNNING
            task["updated_at"] = time.time()
            await self._redis.set(
                f"{TASK_KEY_PREFIX}{task_id}",
                json.dumps(task, default=str),
                ex=86400,
            )

            # Execute the handler
            handler = _task_handlers.get(task["type"])
            if handler is None:
                raise ValueError(f"No handler registered for task type: {task['type']}")

            result = await handler(task["payload"])

            # Mark as completed
            task["status"] = TASK_STATUS_COMPLETED
            task["result"] = result
            task["updated_at"] = time.time()
            await self._redis.set(
                f"{TASK_KEY_PREFIX}{task_id}",
                json.dumps(task, default=str),
                ex=86400,
            )
            logger.info("task_completed", task_type=task["type"], task_id=task_id)

        except Exception as exc:
            logger.error("task_execution_error", task_id=task_id, error=str(exc))
            await self._handle_task_failure(task_id, str(exc))

    async def _handle_task_failure(self, task_id: str, error: str) -> None:
        """Handle a failed task — retry if under max retries, else mark failed."""
        if not self._redis:
            return

        try:
            raw = await self._redis.get(f"{TASK_KEY_PREFIX}{task_id}")
            if raw is None:
                return

            task = json.loads(raw)
            task["retries"] += 1
            task["error"] = error

            if task["retries"] < task.get("max_retries", DEFAULT_MAX_RETRIES):
                # Re-enqueue for retry
                task["status"] = TASK_STATUS_PENDING
                task["updated_at"] = time.time()
                await self._redis.set(
                    f"{TASK_KEY_PREFIX}{task_id}",
                    json.dumps(task, default=str),
                    ex=86400,
                )
                await self._redis.lpush(TASK_QUEUE_KEY, task_id)
                logger.info("task_retry", task_id=task_id, retry=task["retries"])
            else:
                # Max retries exceeded — mark as failed
                task["status"] = TASK_STATUS_FAILED
                task["updated_at"] = time.time()
                await self._redis.set(
                    f"{TASK_KEY_PREFIX}{task_id}",
                    json.dumps(task, default=str),
                    ex=86400,
                )
                logger.error("task_failed_permanently", task_id=task_id, error=error)
        except Exception as exc:
            logger.error("task_failure_handler_error", task_id=task_id, error=str(exc))

    async def _execute_inline(self, task: dict) -> None:
        """Execute a task inline (fallback when Redis is unavailable)."""
        task_id = task["id"]
        try:
            handler = _task_handlers.get(task["type"])
            if handler is None:
                logger.warning("task_no_handler_inline", task_type=task["type"], task_id=task_id)
                return

            result = await handler(task["payload"])
            logger.info("task_completed_inline", task_type=task["type"], task_id=task_id, result=result)
        except Exception as exc:
            logger.error("task_inline_error", task_id=task_id, error=str(exc))


# Singleton instance
_task_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    """Get the singleton TaskQueue instance."""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
