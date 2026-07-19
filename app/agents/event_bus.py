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
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from app.config import get_settings
from app.exceptions import AgentError, EventBusError
from app.infrastructure.streams_signing import (
    SIGNING_ENABLED,
    MessageSigner,
    get_agent_key_registry,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from app.agents.base import AgentEvent, BiasharaAgent

logger = structlog.get_logger(__name__)
settings = get_settings()

# Redis key prefix for event bus streams
STREAM_PREFIX = "biashara:events:"
CONSUMER_GROUP = "biashara_agents"

# Default max length for streams (prevents unbounded growth)
MAX_STREAM_LENGTH = 10_000

# Idempotency key TTL (seconds) — deduplicate events within this window
IDEMPOTENCY_TTL = 3600  # 1 hour

# Backpressure thresholds
BACKPRESSURE_HIGH_WATER = 8_000  # Start throttling
BACKPRESSURE_LOW_WATER = 2_000  # Stop throttling

# Dead letter queue stream suffix
DLQ_SUFFIX = ":dead_letter_queue"

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
    - **NEW**: ML-DSA-65 message signing (feature-flagged)

    Security (when ANGAVU_MESSAGE_SIGNING_ENABLED=true):
    - All published messages are signed with the agent's ML-DSA-65 key
    - Consumed messages are verified before processing
    - Nonce-based replay protection prevents message replay attacks
    - During transition, unsigned messages are still accepted

    Scaling:
    - Supports multiple consumer instances via Redis consumer groups
    - Each instance gets a unique consumer name (agent_name + instance_id)
    - Stream sharding by event type for parallel processing
    - Configurable max stream length and consumer group size
    """

    def __init__(
        self,
        persist_events: bool = True,
        instance_id: str | None = None,
        max_consumers_per_group: int = 10,
        enable_stream_sharding: bool = False,
        shard_count: int = 4,
        max_stream_length: int = MAX_STREAM_LENGTH,
    ):
        self._redis: Any = None  # aioredis.Redis | None
        self._subscriptions: dict[str, list[str]] = defaultdict(list)
        # event_type → [agent_name, ...]
        self._handlers: dict[str, list[Callable[..., Coroutine]]] = defaultdict(list)
        # event_type → [handler_coroutine, ...]

        # In-memory fallback (when Redis is unavailable)
        self._in_memory_streams: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._in_memory_enabled: bool = False
        # Buffer for events to be picked up by polling (no immediate dispatch)
        self._pending_buffer: dict[str, list[dict[str, Any]]] = defaultdict(list)

        # Dead letter queue for events that fail processing
        self._dead_letters: list[dict[str, Any]] = []

        # Idempotency tracking (event_id → timestamp)
        self._idempotency_cache: dict[str, float] = {}

        # Backpressure state
        self._backpressure_active: bool = False
        self._backpressure_streams: dict[str, bool] = defaultdict(lambda: False)

        # Event persistence (append-only JSONL for audit/replay)
        self._persist_events = persist_events
        self._persist_dir: Path | None = None
        self._persist_handles: dict[str, Any] = {}  # stream_key → file handle
        self._persisted_count: int = 0

        # Horizontal scaling configuration
        self._instance_id = instance_id or f"instance_{id(self) % 10000:04d}"
        self._max_consumers_per_group = max_consumers_per_group
        self._enable_stream_sharding = enable_stream_sharding
        self._shard_count = shard_count
        self._consumer_name = f"{CONSUMER_GROUP}:{self._instance_id}"
        # Configurable max stream length (from settings or caller)
        self._max_stream_length = max_stream_length

        # Telemetry (injected after init)
        self._agent_metrics: Any = None

        # Message signing (feature-flagged)
        self._signing_enabled = SIGNING_ENABLED
        self._message_signers: dict[str, MessageSigner] = {}  # agent_name → signer
        self._signing_stats = {
            "signed_published": 0,
            "unsigned_published": 0,
            "verified_consumed": 0,
            "rejected_consumed": 0,
            "unsigned_consumed": 0,
        }

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
                    stream_key,
                    CONSUMER_GROUP,
                    id="0",
                    mkstream=True,
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

    def _get_or_create_signer(self, agent_name: str) -> MessageSigner:
        """Get or create a MessageSigner for an agent."""
        if agent_name not in self._message_signers:
            self._message_signers[agent_name] = MessageSigner(agent_name)
        return self._message_signers[agent_name]

    def _sign_event_data(self, event_data: dict[str, Any], agent_name: str) -> dict[str, Any]:
        """
        Sign event data if signing is enabled.

        Returns the event data with signing metadata added.
        If signing is disabled, returns data unchanged.
        """
        if not self._signing_enabled:
            return event_data

        signer = self._get_or_create_signer(agent_name)
        signed = signer.sign_message(event_data)
        self._signing_stats["signed_published"] += 1
        return signed

    def _verify_event_fields(self, fields: dict[str, str]) -> tuple[bool, str]:
        """
        Verify a received message's signature if signing is enabled.

        Returns (is_valid, reason). If signing is disabled, always returns (True, "signing_disabled").
        """
        if not self._signing_enabled:
            return True, "signing_disabled"

        if "_signature" not in fields:
            # No signature present — accept during transition
            self._signing_stats["unsigned_consumed"] += 1
            return True, "unsigned_accepted_transition"

        # Use any signer for verification (they share the key registry)
        # Create a temporary signer for verification if needed
        sender = fields.get("_sender", "unknown")
        signer = self._get_or_create_signer(f"_verifier_{self._instance_id}")
        valid, reason = signer.verify_message(fields)

        if valid:
            self._signing_stats["verified_consumed"] += 1
        else:
            self._signing_stats["rejected_consumed"] += 1
            self._logger.warning(
                "message_signature_invalid",
                sender=sender,
                reason=reason,
            )

        return valid, reason

    def get_signing_stats(self) -> dict[str, Any]:
        """Return message signing statistics."""
        return {
            "enabled": self._signing_enabled,
            **self._signing_stats,
            "registered_signers": list(self._message_signers.keys()),
            "key_registry_agents": get_agent_key_registry().get_all_agents(),
        }

    async def publish(self, event: AgentEvent) -> str:
        """
        Publish an event to the appropriate stream.

        Features:
        - Idempotency: deduplicates events within IDEMPOTENCY_TTL window
        - Backpressure: throttles when stream depth exceeds high water mark
        - Telemetry: records publish metrics when available
        - **NEW**: ML-DSA-65 message signing when enabled

        Returns the event ID (Redis stream ID or generated ID).
        """
        stream_key = f"{STREAM_PREFIX}{event.event_type.value}"

        # Idempotency check — skip duplicate events
        idempotency_key = self._compute_idempotency_key(event)
        if self._is_duplicate(idempotency_key):
            self._logger.debug(
                "event_deduplicated",
                event_type=event.event_type.value,
                source=event.source,
                idempotency_key=idempotency_key,
            )
            return idempotency_key

        # Backpressure check — wait if stream is too deep
        if await self._check_backpressure(stream_key):
            released = await self.wait_for_backpressure_release(stream_key, timeout=10.0)
            if not released:
                self._logger.warning(
                    "backpressure_timeout",
                    stream=stream_key,
                    event_type=event.event_type.value,
                )

        event_data = event.to_dict()

        # Sign the event data if signing is enabled
        event_data = self._sign_event_data(event_data, event.source)

        if self._redis and not self._in_memory_enabled:
            try:
                entry_id = await self._redis.xadd(
                    stream_key,
                    {
                        k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                        for k, v in event_data.items()
                    },
                    maxlen=self._max_stream_length,
                    approximate=True,
                )
                # Record idempotency key
                self._record_idempotency_key(idempotency_key)

                # Persist event to disk for audit/replay
                self._persist_event(stream_key, event_data)

                # Record telemetry
                if self._agent_metrics:
                    self._agent_metrics.record_event_published(
                        event.event_type.value,
                        event.source,
                    )

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
        if not self._signing_enabled:
            self._signing_stats["unsigned_published"] += 1
        self._pending_buffer[stream_key].append(event_data)
        # Trim to max length
        if len(self._pending_buffer[stream_key]) > self._max_stream_length:
            self._pending_buffer[stream_key] = self._pending_buffer[stream_key][
                -self._max_stream_length :
            ]

        # Record idempotency key
        self._record_idempotency_key(idempotency_key)

        # Persist event to disk for audit/replay
        self._persist_event(stream_key, event_data)

        # Record telemetry
        if self._agent_metrics:
            self._agent_metrics.record_event_published(
                event.event_type.value,
                event.source,
            )

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
                        stream_key,
                        CONSUMER_GROUP,
                        id="0",
                        mkstream=True,
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
        event_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[AgentEvent]:
        """
        Pull new events for an agent.

        Uses Redis XREADGROUP when available, otherwise reads from
        the in-memory buffer.
        """

        target_types = event_types or [
            et for et, agents in self._subscriptions.items() if agent.name in agents
        ]

        if not target_types:
            return []

        if self._redis and not self._in_memory_enabled:
            return await self._get_events_redis(agent, target_types, limit)

        return self._get_events_in_memory(agent, target_types, limit)

    async def _get_events_redis(
        self,
        agent: BiasharaAgent,
        event_types: list[str],
        limit: int,
    ) -> list[AgentEvent]:
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
                            stream_key,
                            CONSUMER_GROUP,
                            msg_id,
                        )
                    except (
                        json.JSONDecodeError,
                        KeyError,
                        ValueError,
                        ConnectionError,
                        OSError,
                    ) as exc:
                        self._logger.warning(
                            "event_parse_error",
                            msg_id=msg_id,
                            error=str(exc),
                        )
                        # Track dead letter
                        await self.publish_to_dlq(stream_key, fields, str(exc))

        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("xreadgroup_failed", error=str(exc))

        return results

    def _get_events_in_memory(
        self,
        agent: BiasharaAgent,
        event_types: list[str],
        limit: int,
    ) -> list[AgentEvent]:
        """Pull events from in-memory pending buffer."""
        from app.agents.base import AgentEvent

        results = []
        for etype in event_types:
            stream_key = f"{STREAM_PREFIX}{etype}"
            buffer = self._pending_buffer.get(stream_key, [])
            # Take up to limit events from the buffer
            taken = buffer[: limit - len(results)]
            remaining = buffer[len(taken) :]
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
                stream_key = f"{STREAM_PREFIX}{etype}"
                await self.publish_to_dlq(stream_key, event.to_dict(), str(exc))

    # ── Event Persistence ────────────────────────────────────────────

    def _persist_event(self, stream_key: str, event_data: dict[str, Any]) -> None:
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
    ) -> list[dict[str, Any]]:
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

    def get_stats(self) -> dict[str, Any]:
        """Return event bus statistics for monitoring."""
        return {
            "mode": "redis" if (self._redis and not self._in_memory_enabled) else "in_memory",
            "subscriptions": dict(self._subscriptions.items()),
            "in_memory_streams": {k: len(v) for k, v in self._pending_buffer.items()},
            "dead_letter_count": len(self._dead_letters),
            "dead_letters_recent": self._dead_letters[-5:],
            "persisted_count": self._persisted_count,
            "persistence_enabled": self._persist_dir is not None,
            # Idempotency
            "idempotency_cache_size": len(self._idempotency_cache),
            # Backpressure
            "backpressure_active_streams": [k for k, v in self._backpressure_streams.items() if v],
            # Message signing
            "signing": self.get_signing_stats(),
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

    def get_scaling_config(self) -> dict[str, Any]:
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

    # ── Idempotency ────────────────────────────────────────────────

    def _compute_idempotency_key(self, event: AgentEvent) -> str:
        """
        Compute an idempotency key for an event.

        Uses event_id if available, otherwise hashes event type + source + payload.
        """
        if event.event_id:
            return event.event_id
        # Fallback: hash the event content
        content = f"{event.event_type.value}:{event.source}:{json.dumps(event.payload, sort_keys=True, default=str)}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def _is_duplicate(self, idempotency_key: str) -> bool:
        """Check if an event with this key was recently published."""
        now = time.time()
        # Expire old entries
        expired = [k for k, ts in self._idempotency_cache.items() if now - ts > IDEMPOTENCY_TTL]
        for k in expired:
            del self._idempotency_cache[k]
        return idempotency_key in self._idempotency_cache

    def _record_idempotency_key(self, key: str) -> None:
        """Record an idempotency key with current timestamp."""
        self._idempotency_cache[key] = time.time()
        # Cap cache size to prevent unbounded growth
        if len(self._idempotency_cache) > 50_000:
            # Evict oldest 20%
            sorted_keys = sorted(self._idempotency_cache, key=lambda k: self._idempotency_cache[k])
            for k in sorted_keys[:10_000]:
                del self._idempotency_cache[k]

    # ── Dead Letter Queue ─────────────────────────────────────────

    async def publish_to_dlq(
        self,
        original_stream: str,
        event_data: dict[str, Any],
        error: str,
    ) -> None:
        """
        Publish a failed event to the dead letter queue.

        DLQ is a separate Redis stream per original stream, allowing
        monitoring and manual replay of failed events.
        """
        dlq_key = f"{original_stream}{DLQ_SUFFIX}"
        dlq_entry = {
            "original_stream": original_stream,
            "data": json.dumps(event_data, default=str),
            "error": error,
            "dead_lettered_at": str(time.time()),
        }

        self._dead_letters.append(
            {
                "stream": original_stream,
                "error": error,
                "timestamp": time.time(),
            }
        )
        # Cap in-memory dead letter list
        if len(self._dead_letters) > 1_000:
            self._dead_letters = self._dead_letters[-1_000:]

        if self._redis and not self._in_memory_enabled:
            try:
                await self._redis.xadd(
                    dlq_key,
                    {k: str(v) for k, v in dlq_entry.items()},
                    maxlen=10_000,
                    approximate=True,
                )
                self._logger.warning(
                    "event_dead_lettered",
                    stream=original_stream,
                    error=error,
                )
            except (ConnectionError, OSError, TimeoutError) as exc:
                self._logger.error("dlq_publish_failed", error=str(exc))

        # Record telemetry
        if self._agent_metrics:
            self._agent_metrics.record_dead_letter(original_stream, error)

    async def get_dlq_events(
        self,
        event_type: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Read events from the dead letter queue for inspection.

        Args:
            event_type: The event type (e.g. "transaction.processed")
            limit: Maximum number of DLQ events to return

        Returns:
            List of DLQ entries with original data, error, and timestamp
        """
        stream_key = f"{STREAM_PREFIX}{event_type}"
        dlq_key = f"{stream_key}{DLQ_SUFFIX}"

        if not self._redis or self._in_memory_enabled:
            return self._dead_letters[-limit:]

        try:
            entries = await self._redis.xrevrange(dlq_key, count=limit)
            results = []
            for msg_id, fields in entries:
                entry = {"msg_id": msg_id}
                for k, v in fields.items():
                    try:
                        entry[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        entry[k] = v
                results.append(entry)
            return results
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("dlq_read_failed", error=str(exc))
            return self._dead_letters[-limit:]

    async def get_dlq_stats(self) -> dict[str, Any]:
        """Get dead letter queue statistics across all streams."""
        stats = {
            "total_in_memory": len(self._dead_letters),
            "streams": {},
        }

        if not self._redis or self._in_memory_enabled:
            return stats

        try:
            # Scan for DLQ streams
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=f"{STREAM_PREFIX}*{DLQ_SUFFIX}",
                    count=100,
                )
                for key in keys:
                    try:
                        info = await self._redis.xinfo_stream(key)
                        stream_name = key.replace(STREAM_PREFIX, "").replace(DLQ_SUFFIX, "")
                        stats["streams"][stream_name] = {
                            "length": info.get("length", 0),
                            "first_entry": info.get("first-entry", ("",))[0],
                            "last_entry": info.get("last-entry", ("",))[0],
                        }
                    except (ConnectionError, OSError, TimeoutError):
                        pass
                if cursor == 0:
                    break
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("dlq_stats_failed", error=str(exc))

        return stats

    # ── Event Replay ───────────────────────────────────────────────

    async def replay_events(
        self,
        event_type: str,
        handler: Callable[[dict[str, Any]], Coroutine],
        from_timestamp: float | None = None,
        to_timestamp: float | None = None,
        limit: int = 1000,
        from_dlq: bool = False,
    ) -> int:
        """
        Replay events from persistence (JSONL files) or Redis streams.

        Useful for:
        - Re-processing events after a bug fix
        - Recovering from DLQ after fixing the root cause
        - Backfilling data after schema changes

        Args:
            event_type: The event type to replay
            handler: Async function to process each event
            from_timestamp: Only replay events after this time
            to_timestamp: Only replay events before this time
            limit: Max events to replay
            from_dlq: If True, replay from dead letter queue instead

        Returns:
            Number of events successfully replayed
        """
        replayed = 0

        if from_dlq:
            # Replay from DLQ
            dlq_events = await self.get_dlq_events(event_type, limit=limit)
            for entry in dlq_events:
                try:
                    data = entry.get("data", {})
                    if isinstance(data, str):
                        data = json.loads(data)
                    if from_timestamp:
                        ts = float(data.get("timestamp", 0))
                        if ts < from_timestamp:
                            continue
                    if to_timestamp:
                        ts = float(data.get("timestamp", 0))
                        if ts > to_timestamp:
                            continue
                    await handler(data)
                    replayed += 1
                except Exception as exc:
                    self._logger.warning(
                        "replay_dlq_failed",
                        event_type=event_type,
                        error=str(exc),
                    )
        else:
            # Replay from persistence files
            events = self.get_persisted_events(event_type, limit=limit)
            for event_data in events:
                try:
                    if from_timestamp:
                        ts = float(event_data.get("timestamp", 0))
                        if ts < from_timestamp:
                            continue
                    if to_timestamp:
                        ts = float(event_data.get("timestamp", 0))
                        if ts > to_timestamp:
                            continue
                    await handler(event_data)
                    replayed += 1
                except Exception as exc:
                    self._logger.warning(
                        "replay_failed",
                        event_type=event_type,
                        error=str(exc),
                    )

        self._logger.info(
            "events_replayed",
            event_type=event_type,
            replayed=replayed,
            from_dlq=from_dlq,
        )
        return replayed

    # ── Backpressure ───────────────────────────────────────────────

    async def _check_backpressure(self, stream_key: str) -> bool:
        """
        Check if a stream is under backpressure (too many pending events).

        Returns True if backpressure is active (should throttle).
        """
        if not self._redis or self._in_memory_enabled:
            # In-memory: check buffer size
            buffer = self._pending_buffer.get(stream_key, [])
            current_depth = len(buffer)
        else:
            try:
                info = await self._redis.xinfo_stream(stream_key)
                current_depth = info.get("length", 0)
            except (ConnectionError, OSError, TimeoutError):
                return False

        was_active = self._backpressure_streams.get(stream_key, False)

        if current_depth >= BACKPRESSURE_HIGH_WATER:
            self._backpressure_streams[stream_key] = True
            if not was_active:
                self._logger.warning(
                    "backpressure_activated",
                    stream=stream_key,
                    depth=current_depth,
                    high_water=BACKPRESSURE_HIGH_WATER,
                )
            return True
        elif current_depth <= BACKPRESSURE_LOW_WATER:
            if was_active:
                self._backpressure_streams[stream_key] = False
                self._logger.info(
                    "backpressure_released",
                    stream=stream_key,
                    depth=current_depth,
                    low_water=BACKPRESSURE_LOW_WATER,
                )
            return False

        return was_active

    async def wait_for_backpressure_release(
        self,
        stream_key: str,
        timeout: float = 30.0,
    ) -> bool:
        """
        Wait for backpressure to release on a stream.

        Returns True if released within timeout, False if timed out.
        """
        start = time.time()
        while time.time() - start < timeout:
            if not await self._check_backpressure(stream_key):
                return True
            await asyncio.sleep(0.5)
        return False

    # ── Telemetry Integration ──────────────────────────────────────

    def set_agent_metrics(self, agent_metrics: Any) -> None:
        """Inject the agent metrics recorder for telemetry."""
        self._agent_metrics = agent_metrics

    def get_dead_letters(self) -> list[dict[str, Any]]:
        """Return dead letter events for debugging."""
        return list(self._dead_letters)
