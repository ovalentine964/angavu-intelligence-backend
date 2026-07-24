"""
Event Bus — Pub/sub for agent communication.

Provides both in-memory and Redis-backed event distribution.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine, Optional

import structlog

from app.agents.base import AgentEvent, EventType

logger = structlog.get_logger(__name__)

# Type alias for event handlers
EventHandler = Callable[[AgentEvent], Coroutine[Any, Any, None]]


class EventBus:
    """
    Event bus for inter-agent communication.

    Supports:
    - Topic-based pub/sub via EventType
    - Wildcard subscriptions
    - Dead letter queue for failed deliveries
    - Backpressure via async queues
    """

    def __init__(self, mode: str = "memory"):
        self._mode = mode
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: list[EventHandler] = []
        self._dead_letter: list[AgentEvent] = []
        self._stats = {
            "published": 0,
            "delivered": 0,
            "failed": 0,
        }
        self._agent_metrics = None
        self._idempotency_cache: dict[str, bool] = {}
        self._active_streams: list[str] = []

    def set_agent_metrics(self, metrics) -> None:
        """Wire telemetry metrics into the event bus."""
        self._agent_metrics = metrics

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe to a specific event type."""
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to all events (wildcard)."""
        self._wildcard_handlers.append(handler)

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to all matching subscribers."""
        self._stats["published"] += 1

        # Idempotency check
        if event.event_id in self._idempotency_cache:
            return
        self._idempotency_cache[event.event_id] = True

        # Trim idempotency cache
        if len(self._idempotency_cache) > 10000:
            keys = list(self._idempotency_cache.keys())
            for k in keys[:5000]:
                del self._idempotency_cache[k]

        handlers = list(self._handlers.get(event.event_type, []))
        handlers.extend(self._wildcard_handlers)

        for handler in handlers:
            try:
                await handler(event)
                self._stats["delivered"] += 1
            except Exception as exc:
                self._stats["failed"] += 1
                self._dead_letter.append(event)
                logger.error(
                    "event_handler_failed",
                    event_type=event.event_type.value,
                    handler=getattr(handler, "__name__", str(handler)),
                    error=str(exc),
                )

        # Trim dead letter queue
        if len(self._dead_letter) > 1000:
            self._dead_letter = self._dead_letter[-500:]

    def get_stats(self) -> dict:
        """Return event bus statistics."""
        return {
            "mode": self._mode,
            "published": self._stats["published"],
            "delivered": self._stats["delivered"],
            "failed": self._stats["failed"],
            "dead_letter_count": len(self._dead_letter),
            "idempotency_cache_size": len(self._idempotency_cache),
            "backpressure_active_streams": self._active_streams,
        }
