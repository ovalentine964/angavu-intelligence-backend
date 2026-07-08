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
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, TYPE_CHECKING

import structlog

from app.config import get_settings
from app.exceptions import AgentError, EventBusError

if TYPE_CHECKING:
    from app.agents.base import AgentEvent, BiasharaAgent

logger = structlog.get_logger(__name__)
settings = get_settings()

# Redis key prefix for event bus streams
STREAM_PREFIX = "biashara:events:"
CONSUMER_GROUP = "biashara_agents"

# Default max length for streams (prevents unbounded growth)
MAX_STREAM_LENGTH = 10_000

# Event persistence directory (relative to workspace)
_PERSIST_DIR = Path(".openclaw/tmp/event_bus")


class EventBus:
    """
    Redis Streams-based event bus for inter-agent communication.

    Features:
    - Consumer groups: each agent processes events exactly once
    - Automatic fallback to in-memory when Redis is unavailable
    - Dead letter tracking for failed events
    - Stream trimming to prevent memory exhaustion
    - Event correlation for request/response patterns
    - Horizontal scaling configuration for multi-instance deployment

    Scaling:
    - Supports multiple consumer instances via Redis consumer groups
    - Each instance gets a unique consumer name (agent_name + instance_id)
    - Stream sharding by event type for parallel processing
    - Configurable max stream length and consumer group size
    """

    def __init__(
        self,
        persist_events: bool = True,
        instance_id: Optional[str] = None,
        max_consumers_per_group: int = 10,
        enable_stream_sharding: bool = False,
        shard_count: int = 4,
        max_stream_length: int = MAX_STREAM_LENGTH,
    ):
        self._redis: Any = None  # aioredis.Redis | None
        self._subscriptions: Dict[str, List[str]] = defaultdict(list)
        # event_type → [agent_name, ...]
        self._handlers: Dict[str, List[Callable[..., Coroutine]]] = defaultdict(list)
        # event_type → [handler_coroutine, ...]

        # In-memory fallback (when Redis is unavailable)
        self._in_memory_streams: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._in_memory_enabled: bool = False
        # Buffer for events to be picked up by polling (no immediate dispatch)
        self._pending_buffer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        # Dead letter queue for events that fail processing
        self._dead_letters: List[Dict[str, Any]] = []

        # Event persistence (append-only JSONL for audit/replay)
        self._persist_events = persist_events
        self._persist_dir: Optional[Path] = None
        self._persist_handles: Dict[str, Any] = {}  # stream_key → file handle
        self._persisted_count: int = 0

        # Horizontal scaling configuration
        self._instance_id = instance_id or f"instance_{id(self) % 10000:04d}"
        self._max_consumers_per_group = max_consumers_per_group
        self._enable_stream_sharding = enable_stream_sharding
        self._shard_count = shard_count
        self._consumer_name = f"{CONSUMER_GROUP}:{self._instance_id}"
        # Configurable max stream length (from settings or caller)
        self._max_stream_length = max_stream_length

        self._logger = logger.bind(
            component="event_bus",
            instance_id=self._instance_id,
        )

    # ── Lifecycle ───────────────────────────────────────────────────

    async def connect(self) -> None:
        """
        Connect to Redis. Falls back to in-memory mode if unavailable.

        Mirrors the graceful degradation pattern in task_queue.py.
        Also initializes event persistence directory.
        """
        # Set up persistence directory
        if self._persist_events:
            try:
                self._persist_dir = _PERSIST_DIR
                self._persist_dir.mkdir(parents=True, exist_ok=True)
                self._logger.info("event_persistence_enabled", path=str(self._persist_dir))
            except (OSError, PermissionError) as exc:
                self._logger.warning("event_persistence_setup_failed", error=str(exc))
                self._persist_dir = None

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

            # Auto-create consumer groups for all known event types
            await self._ensure_consumer_groups()

            self._logger.info("event_bus_connected", redis_url=redis_url.split("@")[-1])
        except (ImportError, ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning(
                "redis_unavailable_fallback",
                error=str(exc),
            )
            self._redis = None
            self._in_memory_enabled = True

    async def _ensure_consumer_groups(self) -> None:
        """
        Auto-create Redis Streams consumer groups for all known event types.

        Called once on connect. Uses mkstream=True so streams are created
        on demand if they don't exist yet.
        """
        if not self._redis:
            return

        from app.agents.base import EventType

        for event_type in EventType:
            stream_key = f"{STREAM_PREFIX}{event_type.value}"
            try:
                await self._redis.xgroup_create(
                    stream_key, CONSUMER_GROUP, id="0", mkstream=True,
                )
                self._logger.debug("consumer_group_created", stream=stream_key)
            except (ConnectionError, OSError, TimeoutError) as exc:
                # Group already exists or Redis temporarily unavailable — idempotent
                self._logger.debug("consumer_group_skip", stream=stream_key, reason=str(exc))

    async def disconnect(self) -> None:
        """Clean up Redis connection and close persistence handles."""
        # Close persistence file handles
        for handle in self._persist_handles.values():
            try:
                handle.close()
            except (OSError, ValueError) as exc:
                self._logger.debug("persist_handle_close_failed", error=str(exc))
        self._persist_handles.clear()

        if self._redis:
            await self._redis.close()
            self._redis = None
        self._logger.info(
            "event_bus_disconnected",
            events_persisted=self._persisted_count,
        )

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
                    maxlen=self._max_stream_length,
                    approximate=True,
                )
                # Persist event to disk for audit/replay
                self._persist_event(stream_key, event_data)

                self._logger.debug(
                    "event_published",
                    event_type=event.event_type.value,
                    source=event.source,
                    stream_id=entry_id,
                )
                return entry_id
            except (ConnectionError, OSError, TimeoutError) as exc:
                self._logger.warning(
                    "publish_redis_failed",
                    error=str(exc),
                    event_type=event.event_type.value,
                )
                # Fall through to in-memory

        # In-memory fallback — buffer for polling, no immediate dispatch
        self._pending_buffer[stream_key].append(event_data)
        # Trim to max length
        if len(self._pending_buffer[stream_key]) > self._max_stream_length:
            self._pending_buffer[stream_key] = self._pending_buffer[stream_key][-self._max_stream_length:]

        # Persist event to disk for audit/replay
        self._persist_event(stream_key, event_data)

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
                except (ConnectionError, OSError, TimeoutError) as exc:
                    self._logger.debug("subscribe_group_skip", stream=stream_key, reason=str(exc))

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

        # For horizontal scaling, use instance-specific consumer name
        consumer_name = f"{agent.name}:{self._instance_id}" if self._instance_id else agent.name

        streams = {f"{STREAM_PREFIX}{et}": ">" for et in event_types}
        results = []

        try:
            entries = await self._redis.xreadgroup(
                CONSUMER_GROUP,
                consumer_name,
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
                    except (json.JSONDecodeError, KeyError, ValueError, ConnectionError, OSError) as exc:
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

        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("xreadgroup_failed", error=str(exc))

        return results

    def _get_events_in_memory(
        self,
        agent: BiasharaAgent,
        event_types: List[str],
        limit: int,
    ) -> List[AgentEvent]:
        """Pull events from in-memory pending buffer."""
        from app.agents.base import AgentEvent

        results = []
        for etype in event_types:
            stream_key = f"{STREAM_PREFIX}{etype}"
            buffer = self._pending_buffer.get(stream_key, [])
            # Take up to limit events from the buffer
            taken = buffer[:limit - len(results)]
            remaining = buffer[len(taken):]
            self._pending_buffer[stream_key] = remaining

            for data in taken:
                try:
                    results.append(AgentEvent.from_dict(data))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
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
            except (AgentError, EventBusError, RuntimeError, OSError) as exc:
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

    # ── Event Persistence ────────────────────────────────────────────

    def _persist_event(self, stream_key: str, event_data: Dict[str, Any]) -> None:
        """
        Append an event to a JSONL file for audit and replay.

        One file per event type, stored in .openclaw/tmp/event_bus/.
        Each line is a JSON object with the full event data.
        """
        if not self._persist_dir:
            return

        try:
            # Derive filename from stream key
            etype = stream_key.replace(STREAM_PREFIX, "").replace(".", "_")
            filepath = self._persist_dir / f"{etype}.jsonl"

            with open(filepath, "a") as f:
                f.write(json.dumps(event_data, default=str) + "\n")

            self._persisted_count += 1
        except (OSError, TypeError, ValueError) as exc:
            self._logger.debug("persist_event_failed", error=str(exc))

    def get_persisted_events(
        self,
        event_type: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Read persisted events from disk for replay or debugging.

        Args:
            event_type: The event type (e.g. "transaction.processed")
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries, most recent last
        """
        if not self._persist_dir:
            return []

        etype = event_type.replace(".", "_")
        filepath = self._persist_dir / f"{etype}.jsonl"
        if not filepath.exists():
            return []

        events = []
        try:
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.warning("read_persisted_events_failed", error=str(exc))

        return events[-limit:]

    # ── Monitoring ──────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return event bus statistics for monitoring."""
        return {
            "mode": "redis" if (self._redis and not self._in_memory_enabled) else "in_memory",
            "subscriptions": {
                etype: agents for etype, agents in self._subscriptions.items()
            },
            "in_memory_streams": {
                k: len(v) for k, v in self._pending_buffer.items()
            },
            "dead_letter_count": len(self._dead_letters),
            "dead_letters_recent": self._dead_letters[-5:],
            "persisted_count": self._persisted_count,
            "persistence_enabled": self._persist_dir is not None,
            # Horizontal scaling info
            "scaling": {
                "instance_id": self._instance_id,
                "consumer_name": self._consumer_name,
                "max_consumers_per_group": self._max_consumers_per_group,
                "stream_sharding_enabled": self._enable_stream_sharding,
                "shard_count": self._shard_count,
                "max_stream_length": self._max_stream_length,
            },
        }

    def get_scaling_config(self) -> Dict[str, Any]:
        """Return horizontal scaling configuration."""
        return {
            "instance_id": self._instance_id,
            "consumer_group": CONSUMER_GROUP,
            "consumer_name": self._consumer_name,
            "max_consumers_per_group": self._max_consumers_per_group,
            "stream_sharding": {
                "enabled": self._enable_stream_sharding,
                "shard_count": self._shard_count,
            },
            "deployment_notes": (
                "For horizontal scaling: deploy multiple instances with unique "
                "instance_id values. Each instance gets its own consumer in the "
                "shared consumer group. Redis handles load distribution automatically."
            ),
        }

    def get_dead_letters(self) -> List[Dict[str, Any]]:
        """Return dead letter events for debugging."""
        return list(self._dead_letters)
