"""
Event Bus — Pub/Sub for inter-agent communication.

Provides a lightweight in-process event bus with support for:
- Typed event subscriptions
- Async event publishing
- Dead letter queue for failed deliveries
- Statistics and observability
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import structlog

from app.agents.base import AgentEvent, AgentResult, BiasharaAgent, EventType

logger = structlog.get_logger(__name__)

# Type alias for event handlers
EventHandler = Callable[[AgentEvent], Coroutine[Any, Any, AgentResult | None]]


@dataclass
class EventBusStats:
    """Statistics for the event bus."""
    total_published: int = 0
    total_delivered: int = 0
    total_failed: int = 0
    dead_letter_count: int = 0


class EventBus:
    """
    In-process event bus for inter-agent communication.

    Supports:
    - subscribe(agent, event_types): Register an agent for specific event types
    - publish(event): Publish an event to all matching subscribers
    - get_stats(): Return bus statistics
    - set_agent_metrics(metrics): Wire in telemetry metrics
    """

    def __init__(self):
        self._subscribers: dict[EventType, list[tuple[BiasharaAgent, list[EventType]]]] = defaultdict(list)
        self._handler_map: dict[str, list[tuple[list[EventType], EventHandler]]] = defaultdict(list)
        self._stats = EventBusStats()
        self._dead_letters: list[dict[str, Any]] = []
        self._agent_metrics: Any = None
        self._mode = "in-process"

    def set_agent_metrics(self, metrics: Any) -> None:
        """Wire in telemetry metrics collector."""
        self._agent_metrics = metrics

    async def subscribe(
        self,
        agent: BiasharaAgent,
        event_types: list[EventType],
    ) -> None:
        """Subscribe an agent to specific event types."""
        for et in event_types:
            self._subscribers[et].append((agent, event_types))
        logger.debug("event_bus_subscribe", agent=agent.name, events=[e.value for e in event_types])

    async def subscribe_handler(
        self,
        handler_id: str,
        event_types: list[EventType],
        handler: EventHandler,
    ) -> None:
        """Subscribe a raw handler function to specific event types."""
        for et in event_types:
            self._handler_map[et.value].append((event_types, handler))
        logger.debug("event_bus_subscribe_handler", handler_id=handler_id, events=[e.value for e in event_types])

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to all matching subscribers."""
        self._stats.total_published += 1

        # Deliver to agent subscribers
        subscribers = self._subscribers.get(event.event_type, [])
        for agent, _event_types in subscribers:
            try:
                await agent.handle_event(event)
                self._stats.total_delivered += 1
            except Exception as exc:
                self._stats.total_failed += 1
                self._dead_letters.append({
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "subscriber": agent.name,
                    "error": str(exc),
                    "timestamp": time.time(),
                })
                logger.error(
                    "event_delivery_failed",
                    event_id=event.event_id,
                    agent=agent.name,
                    error=str(exc),
                )

        # Deliver to raw handler subscribers
        handlers = self._handler_map.get(event.event_type.value, [])
        for _event_types, handler in handlers:
            try:
                await handler(event)
                self._stats.total_delivered += 1
            except Exception as exc:
                self._stats.total_failed += 1
                logger.error(
                    "event_handler_failed",
                    event_id=event.event_id,
                    error=str(exc),
                )

        # Trim dead letter queue
        if len(self._dead_letters) > 1000:
            self._dead_letters = self._dead_letters[-500:]

    def get_stats(self) -> dict[str, Any]:
        """Return event bus statistics."""
        return {
            "mode": self._mode,
            "total_published": self._stats.total_published,
            "total_delivered": self._stats.total_delivered,
            "total_failed": self._stats.total_failed,
            "dead_letter_count": len(self._dead_letters),
            "idempotency_cache_size": 0,
            "backpressure_active_streams": [],
        }
