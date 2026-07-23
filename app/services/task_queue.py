"""
Task queue — Redis sorted set based priority queue.

Architecture: arch_backend.md §1.2
"""
import json
from typing import Any, Optional
import asyncio

import structlog

logger = structlog.get_logger(__name__)


class TaskQueue:
    """Redis-backed priority task queue."""

    QUEUE_KEY = "angavu:task_queue"
    PROCESSING_KEY = "angavu:task_processing"

    def __init__(self):
        self._redis = None
        self._handlers: dict[str, Any] = {}
        self._running = False

    async def connect(self):
        from app.db.redis import get_redis
        self._redis = await get_redis()
        logger.info("task_queue_connected")

    async def close(self):
        self._running = False
        logger.info("task_queue_closed")

    def register_handler(self, task_type: str, handler):
        self._handlers[task_type] = handler

    async def enqueue(self, task_type: str, payload: dict, priority: int = 5):
        """Add a task to the queue. Lower priority number = higher priority."""
        task = json.dumps({"type": task_type, "payload": payload})
        await self._redis.zadd(self.QUEUE_KEY, {task: priority})
        logger.info("task_enqueued", type=task_type, priority=priority)

    async def start_worker(self):
        """Start processing tasks from the queue."""
        self._running = True
        logger.info("task_worker_started")
        while self._running:
            try:
                result = await self._redis.zpopmin(self.QUEUE_KEY, count=1)
                if not result:
                    await asyncio.sleep(1)
                    continue

                task_data, score = result[0]
                task = json.loads(task_data)
                task_type = task["type"]
                payload = task["payload"]

                handler = self._handlers.get(task_type)
                if handler:
                    try:
                        await handler(payload)
                        logger.info("task_completed", type=task_type)
                    except Exception as e:
                        logger.error("task_failed", type=task_type, error=str(e))
                else:
                    logger.warning("no_handler", type=task_type)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("task_worker_error", error=str(e))
                await asyncio.sleep(1)


_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
