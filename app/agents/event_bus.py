"""
Event Bus — Redis Streams for inter-agent communication.

Events flow through named streams:
    transaction.processed  → IntelligenceGeneratorAgent
    intelligence.generated → ReportGeneratorAgent
    feedback.received      → SelfEvolutionAgent
    report.delivered       → (any agent listening)

Each agent has a consumer group so events are processed exactly once.
When Redis is unavailable, falls back to in-memory pub/sub so the
system degrades gracefully (same pattern as task_queue.py).

Stream topology:
    ┌─────────────────────┐
    │ TransactionProcessor│──▶ transaction.processed
    └─────────────────────┘              │
                                         ▼
                           ┌──────────────────────────┐
                           │ IntelligenceGeneratorAgent│──▶ intelligence.generated
                           └──────────────────────────┘              │
                                                                     ▼
                                                       ┌─────────────────────┐
                                                       │  ReportGeneratorAgent│──▶ report.delivered
                                                       └─────────────────────┘
                                                                     ▲
    ┌──────────────────┐                                             │
    │  SelfEvolution   │──▶ feedback.received ────────────────────────┘
    └──────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, TYPE_CHECKING

import structlog

from app.config import get_settings

if TYPE_CHECKING:
    from app.agents.base import AgentEvent, BiasharaAgent

logger = structlog.get_logger(__name__)
settings = get_settings()

# Redis key prefix for event bus streams
STREAM_PREFIX = "biashara:events:"
CONSUMER_GROUP = "biashara_agents"

# Default max length for streams (prevents unbounded growth)
MAX_STREAM_LENGTH = 10_000


class EventBus:
    """
    Redis Streams-based event bus for inter-agent communication.

    Features:
    - Consumer groups: each agent processes events exactly once
    - Automatic fallback to in-memory when Redis is unavailable
    - Dead letter tracking for failed events
    - Stream trimming to prevent memory exhaustion
    - Event correlation for request/response patterns
    """

    def __init__(self):
        self._redis: Any = None  # aioredis.Redis | None
        self._subscriptions: Dict[str, List[str]] = defaultdict(list)
        # event_type → [agent_name, ...]
        self._handlers: Dict[str, List[Callable[..., Coroutine]]] = defaultdict(list)
        # event_type → [handler_coroutine, ...]

        # In-memory fallback (when Redis is unavailable)
        self._in_memory_streams: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._in_memory_enabled: bool = False

        # Dead letter queue for events that fail processing
        self._dead_letters: List[Dict[str, Any]] = []

        self._logger = logger.bind(component="event_bus")

    # ── Lifecycle ───────────────────────────────────────────────────

    async def connect(self) -> None:
        """
        Connect to Redis. Falls back to in-memory mode if unavailable.

        Mirrors the graceful degradation pattern in task_queue.py.
        """
        redis_url = settings.REDIS_URL
        if not redis_url:
            self._logger.info("no_redis_url_fallback_in_memory")
            self._in_memory_enabled = True
            return

        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Verify connection
            await self._redis.ping()
            self._logger.info("event_bus_connected", redis_url=redis_url.split("@")[-1])
        except Exception as exc:
            self._logger.warning(
                "redis_unavailable_fallback",
                error=str(exc),
            )
            self._redis = None
            self._in_memory_enabled = True

    async def disconnect(self) -> None:
        """Clean up Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._logger.info("event_bus_disconnected")

    # ── Publish ─────────────────────────────────────────────────────

    async def publish(self, event: AgentEvent) -> str:
        """
        Publish an event to the appropriate stream.

        Returns the event ID (Redis stream ID or generated ID).
        """
        stream_key = f"{STREAM_PREFIX}{event.event_type.value}"
        event_data = event.to_dict()

        if self._redis and not self._in_memory_enabled:
            try:
                entry_id = await self._redis.xadd(
                    stream_key,
                    {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                     for k, v in event_data.items()},
                    maxlen=MAX_STREAM_LENGTH,
                    approximate=True,
                )
                self._logger.debug(
                    "event_published",
                    event_type=event.event_type.value,
                    source=event.source,
                    stream_id=entry_id,
                )
                return entry_id
            except Exception as exc:
                self._logger.warning(
                    "publish_redis_failed",
                    error=str(exc),
                    event_type=event.event_type.value,
                )
                # Fall through to in-memory

        # In-memory fallback
        self._in_memory_streams[stream_key].append(event_data)
        # Trim to max length
        if len(self._in_memory_streams[stream_key]) > MAX_STREAM_LENGTH:
            self._in_memory_streams[stream_key] = self._in_memory_streams[stream_key][-MAX_STREAM_LENGTH:]

        # Trigger in-memory handlers
        await self._dispatch_in_memory(event)

        self._logger.debug(
            "event_published_in_memory",
            event_type=event.event_type.value,
            source=event.source,
        )
        return event.event_id

    # ── Subscribe ───────────────────────────────────────────────────

    async def subscribe(
        self,
        agent: BiasharaAgent,
        event_types: list,
    ) -> None:
        """
        Subscribe an agent to one or more event types.

        Creates a Redis consumer group if using Redis, or registers
        an in-memory handler.
        """
        for event_type in event_types:
            etype = event_type.value if hasattr(event_type, "value") else event_type
            self._subscriptions[etype].append(agent.name)

            if self._redis and not self._in_memory_enabled:
                stream_key = f"{STREAM_PREFIX}{etype}"
                try:
                    await self._redis.xgroup_create(
                        stream_key, CONSUMER_GROUP, id="0", mkstream=True,
                    )
                except Exception:
                    pass  # Group already exists — that's fine

            # Register in-memory handler
            self._handlers[etype].append(agent.handle_event)

            self._logger.info(
                "agent_subscribed",
                agent=agent.name,
                event_type=etype,
            )

    # ── Receive ─────────────────────────────────────────────────────

    async def get_events(
        self,
        agent: BiasharaAgent,
        event_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[AgentEvent]:
        """
        Pull new events for an agent.

        Uses Redis XREADGROUP when available, otherwise reads from
        the in-memory buffer.
        """
        from app.agents.base import AgentEvent

        target_types = event_types or [
            et for et, agents in self._subscriptions.items()
            if agent.name in agents
        ]

        if not target_types:
            return []

        if self._redis and not self._in_memory_enabled:
            return await self._get_events_redis(agent, target_types, limit)

        return self._get_events_in_memory(agent, target_types, limit)

    async def _get_events_redis(
        self,
        agent: BiasharaAgent,
        event_types: List[str],
        limit: int,
    ) -> List[AgentEvent]:
        """Pull events from Redis Streams using consumer groups."""
        from app.agents.base import AgentEvent

        streams = {f"{STREAM_PREFIX}{et}": ">" for et in event_types}
        results = []

        try:
            entries = await self._redis.xreadgroup(
                CONSUMER_GROUP,
                agent.name,
                streams,
                count=limit,
                block=100,  # ms — don't block forever
            )
            for stream_key, messages in entries:
                for msg_id, fields in messages:
                    try:
                        event_data = {}
                        for k, v in fields.items():
                            try:
                                event_data[k] = json.loads(v)
                            except (json.JSONDecodeError, TypeError):
                                event_data[k] = v
                        event = AgentEvent.from_dict(event_data)
                        results.append(event)

                        # Acknowledge processing
                        await self._redis.xack(
                            stream_key, CONSUMER_GROUP, msg_id,
                        )
                    except Exception as exc:
                        self._logger.warning(
                            "event_parse_error",
                            msg_id=msg_id,
                            error=str(exc),
                        )
                        # Track dead letter
                        self._dead_letters.append({
                            "stream": stream_key,
                            "msg_id": msg_id,
                            "error": str(exc),
                            "timestamp": time.time(),
                        })

        except Exception as exc:
            self._logger.warning("xreadgroup_failed", error=str(exc))

        return results

    def _get_events_in_memory(
        self,
        agent: BiasharaAgent,
        event_types: List[str],
        limit: int,
    ) -> List[AgentEvent]:
        """Pull events from in-memory buffers."""
        from app.agents.base import AgentEvent

        results = []
        for etype in event_types:
            stream_key = f"{STREAM_PREFIX}{etype}"
            buffer = self._in_memory_streams.get(stream_key, [])
            # Take up to limit events from the buffer
            taken = buffer[:limit - len(results)]
            remaining = buffer[len(taken):]
            self._in_memory_streams[stream_key] = remaining

            for data in taken:
                try:
                    results.append(AgentEvent.from_dict(data))
                except Exception as exc:
                    self._logger.warning("in_memory_parse_error", error=str(exc))

            if len(results) >= limit:
                break

        return results

    async def _dispatch_in_memory(self, event: AgentEvent) -> None:
        """Dispatch an event to in-memory handlers (fire-and-forget)."""
        etype = event.event_type.value
        handlers = self._handlers.get(etype, [])

        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                self._logger.warning(
                    "handler_error",
                    event_type=etype,
                    error=str(exc),
                )
                self._dead_letters.append({
                    "event_type": etype,
                    "error": str(exc),
                    "timestamp": time.time(),
                })

    # ── Monitoring ──────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return event bus statistics for monitoring."""
        return {
            "mode": "redis" if (self._redis and not self._in_memory_enabled) else "in_memory",
            "subscriptions": {
                etype: agents for etype, agents in self._subscriptions.items()
            },
            "in_memory_streams": {
                k: len(v) for k, v in self._in_memory_streams.items()
            },
            "dead_letter_count": len(self._dead_letters),
            "dead_letters_recent": self._dead_letters[-5:],
        }

    def get_dead_letters(self) -> List[Dict[str, Any]]:
        """Return dead letter events for debugging."""
        return list(self._dead_letters)
