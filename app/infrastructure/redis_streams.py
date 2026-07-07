"""
Redis Streams — Producer/Consumer pattern for inter-service communication.

Replaces simple pub/sub with durable, consumer-group-based message streams.
Supports horizontal scaling: multiple consumer instances process messages
exactly-once via Redis consumer groups.

Architecture:
    ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
    │   Producer    │──▶│  Redis Stream     │──▶│  Consumer     │
    │  (any svc)    │   │  (durable, trim)  │   │  Group A      │
    └──────────────┘    └──────────────────┘    │  - Worker 1   │
                                                 │  - Worker 2   │
                                                 └──────────────┘
                                                       │
                                                 ┌──────────────┐
                                                 │  Consumer     │
                                                 │  Group B      │
                                                 │  - Worker 1   │
                                                 └──────────────┘

Key Design Decisions:
- MAX_STREAM_LENGTH: 50K per stream (prevents unbounded memory growth)
- Consumer groups: exactly-once processing per group
- Claim stale messages: handles worker crashes gracefully
- Pending entry list: tracks unacknowledged messages
- Dead letter stream: messages that exceed max delivery count

References:
- Queuing Theory: Little's Law (L = λW) guides queue depth sizing
- Distributed Systems: Consumer groups provide partition-like scaling
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Constants ──────────────────────────────────────────────────────

STREAM_PREFIX = "biashara:streams:"
CONSUMER_GROUP_PREFIX = "biashara:cg:"
DEAD_LETTER_SUFFIX = ":dead_letters"

# Max entries per stream (prevents unbounded growth)
MAX_STREAM_LENGTH = 50_000

# Claim messages idle for more than 60 seconds (worker crash recovery)
CLAIM_IDLE_THRESHOLD_MS = 60_000

# Max delivery count before dead-lettering
MAX_DELIVERY_COUNT = 5

# Batch size for XREADGROUP
DEFAULT_BATCH_SIZE = 50

# Block timeout for XREADGROUP (ms)
BLOCK_TIMEOUT_MS = 2000


class DeliveryPolicy(str, Enum):
    """Message delivery guarantees."""
    AT_MOST_ONCE = "at_most_once"     # Fire and forget
    AT_LEAST_ONCE = "at_least_once"   # Ack required, may redeliver
    EXACTLY_ONCE = "exactly_once"     # Consumer group, idempotent processing


@dataclass
class StreamMessage:
    """A message read from a Redis Stream."""
    id: str
    stream: str
    data: Dict[str, Any]
    delivery_count: int = 0
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class ConsumerInfo:
    """Information about a consumer in a consumer group."""
    name: str
    group: str
    stream: str
    pending_count: int = 0
    idle_time_ms: int = 0


@dataclass
class StreamStats:
    """Statistics for a Redis Stream."""
    stream: str
    length: int = 0
    first_entry_id: str = ""
    last_entry_id: str = ""
    consumer_groups: int = 0
    pending_count: int = 0
    dead_letter_count: int = 0


class RedisStreamsProducer:
    """
    Produces messages to Redis Streams.

    Usage:
        producer = RedisStreamsProducer()
        await producer.connect()

        # Publish a message
        msg_id = await producer.publish("transaction.processed", {
            "transaction_id": "txn_123",
            "amount": 500,
            "currency": "KES",
        })

        # Publish with custom max length
        msg_id = await producer.publish("high_volume.events", data, max_length=10000)

    Thread-safe: uses a single Redis connection with connection pooling.
    """

    def __init__(self):
        self._redis = None
        self._connected = False
        self._logger = logger.bind(component="streams_producer")

    async def connect(self) -> None:
        """Connect to Redis."""
        if not settings.REDIS_URL:
            self._logger.warning("no_redis_url_producer_disabled")
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
            self._logger.info("streams_producer_connected")
        except (ImportError, ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("streams_producer_connect_failed", error=str(exc))

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._connected = False

    async def publish(
        self,
        stream: str,
        data: Dict[str, Any],
        max_length: int = MAX_STREAM_LENGTH,
        message_id: str = "*",
    ) -> Optional[str]:
        """
        Publish a message to a Redis Stream.

        Args:
            stream: Stream name (e.g., "transaction.processed")
            data: Message payload (must be JSON-serializable)
            max_length: Max stream length (approximate trimming)
            message_id: Redis stream ID ("*" for auto-generate)

        Returns:
            Stream entry ID, or None if Redis is unavailable
        """
        if not self._connected or not self._redis:
            self._logger.debug("publish_skipped_no_redis", stream=stream)
            return None

        stream_key = f"{STREAM_PREFIX}{stream}"

        # Serialize all values to strings
        serialized = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                serialized[k] = json.dumps(v, default=str)
            else:
                serialized[k] = str(v)

        # Add metadata
        serialized["_published_at"] = str(time.time())
        serialized["_stream"] = stream

        try:
            entry_id = await self._redis.xadd(
                stream_key,
                serialized,
                maxlen=max_length,
                approximate=True,
                id=message_id,
            )
            self._logger.debug(
                "message_published",
                stream=stream,
                entry_id=entry_id,
            )
            return entry_id
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("publish_failed", stream=stream, error=str(exc))
            return None

    async def publish_batch(
        self,
        stream: str,
        messages: List[Dict[str, Any]],
        max_length: int = MAX_STREAM_LENGTH,
    ) -> List[str]:
        """
        Publish multiple messages to a stream in a pipeline.

        Args:
            stream: Stream name
            messages: List of message payloads
            max_length: Max stream length

        Returns:
            List of entry IDs
        """
        if not self._connected or not self._redis:
            return []

        stream_key = f"{STREAM_PREFIX}{stream}"
        entry_ids = []

        try:
            pipe = self._redis.pipeline(transaction=False)
            for msg in messages:
                serialized = {}
                for k, v in msg.items():
                    if isinstance(v, (dict, list)):
                        serialized[k] = json.dumps(v, default=str)
                    else:
                        serialized[k] = str(v)
                serialized["_published_at"] = str(time.time())
                pipe.xadd(stream_key, serialized, maxlen=max_length, approximate=True)

            results = await pipe.execute()
            entry_ids = [r for r in results if r]
            self._logger.debug("batch_published", stream=stream, count=len(entry_ids))
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("batch_publish_failed", stream=stream, error=str(exc))

        return entry_ids

    @property
    def is_connected(self) -> bool:
        return self._connected


class RedisStreamsConsumer:
    """
    Consumes messages from Redis Streams using consumer groups.

    Features:
    - Consumer group: exactly-once processing per group
    - Stale message claiming: recovers from worker crashes
    - Dead letter queue: messages that exceed max delivery count
    - Backpressure: configurable batch size and block timeout
    - Graceful degradation: works without Redis (no-op)

    Usage:
        consumer = RedisStreamsConsumer(group="intelligence_generators")
        await consumer.connect()

        # Subscribe to streams
        await consumer.subscribe("transaction.processed", handler=my_handler)

        # Start consuming (blocks until stopped)
        await consumer.start()

    Scaling: Add more instances with the same group name. Redis distributes
    messages across consumers in the group automatically.
    """

    def __init__(
        self,
        group: str,
        consumer_name: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        block_timeout_ms: int = BLOCK_TIMEOUT_MS,
    ):
        self._group = f"{CONSUMER_GROUP_PREFIX}{group}"
        self._consumer_name = consumer_name or f"{group}_{uuid.uuid4().hex[:8]}"
        self._batch_size = batch_size
        self._block_timeout_ms = block_timeout_ms

        self._redis = None
        self._connected = False
        self._running = False
        self._consumer_task: Optional[asyncio.Task] = None

        # stream_name → handler_coroutine
        self._handlers: Dict[str, Callable[[StreamMessage], Coroutine]] = {}

        # Metrics
        self._messages_processed = 0
        self._messages_failed = 0
        self._last_message_time: Optional[float] = None

        self._logger = logger.bind(
            component="streams_consumer",
            group=group,
            consumer=self._consumer_name,
        )

    async def connect(self) -> None:
        """Connect to Redis."""
        if not settings.REDIS_URL:
            self._logger.warning("no_redis_url_consumer_disabled")
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
            self._logger.info("streams_consumer_connected")
        except (ImportError, ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("streams_consumer_connect_failed", error=str(exc))

    async def disconnect(self) -> None:
        """Stop consuming and close Redis connection."""
        await self.stop()
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._connected = False

    async def subscribe(
        self,
        stream: str,
        handler: Callable[[StreamMessage], Coroutine],
    ) -> None:
        """
        Subscribe to a stream with a message handler.

        Args:
            stream: Stream name (e.g., "transaction.processed")
            handler: Async function that processes a StreamMessage
        """
        stream_key = f"{STREAM_PREFIX}{stream}"
        self._handlers[stream_key] = handler

        # Ensure consumer group exists
        if self._connected and self._redis:
            try:
                await self._redis.xgroup_create(
                    stream_key, self._group, id="0", mkstream=True,
                )
                self._logger.debug("consumer_group_created", stream=stream_key)
            except (ConnectionError, OSError, TimeoutError) as exc:
                # Group already exists — idempotent
                self._logger.debug("consumer_group_exists", stream=stream_key, reason=str(exc))

        self._logger.info("subscribed_to_stream", stream=stream)

    async def start(self) -> None:
        """Start consuming messages in the background."""
        if self._running:
            return
        if not self._connected or not self._redis:
            self._logger.warning("cannot_start_not_connected")
            return

        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        self._logger.info(
            "consumer_started",
            streams=list(self._handlers.keys()),
            batch_size=self._batch_size,
        )

    async def stop(self) -> None:
        """Stop the consumer loop."""
        self._running = False
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        self._logger.info("consumer_stopped")

    async def _consume_loop(self) -> None:
        """Main consumer loop — reads from streams and dispatches to handlers."""
        streams = {stream: ">" for stream in self._handlers.keys()}

        while self._running:
            try:
                # XREADGROUP: read new messages
                entries = await self._redis.xreadgroup(
                    self._group,
                    self._consumer_name,
                    streams,
                    count=self._batch_size,
                    block=self._block_timeout_ms,
                )

                if not entries:
                    # No messages — claim stale messages from other consumers
                    await self._claim_stale_messages()
                    continue

                for stream_key, messages in entries:
                    handler = self._handlers.get(stream_key)
                    if not handler:
                        continue

                    for msg_id, fields in messages:
                        await self._process_message(stream_key, msg_id, fields, handler)

            except asyncio.CancelledError:
                break
            except (ConnectionError, OSError, TimeoutError) as exc:
                self._logger.warning("consume_loop_error", error=str(exc))
                await asyncio.sleep(1)
            except Exception as exc:
                self._logger.error("consume_loop_unexpected_error", error=str(exc), exc_info=True)
                await asyncio.sleep(1)

    async def _process_message(
        self,
        stream_key: str,
        msg_id: str,
        fields: Dict[str, str],
        handler: Callable[[StreamMessage], Coroutine],
    ) -> None:
        """Process a single message and acknowledge it."""
        # Deserialize JSON fields
        data = {}
        for k, v in fields.items():
            if k.startswith("_"):
                continue  # Skip metadata fields
            try:
                data[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                data[k] = v

        message = StreamMessage(
            id=msg_id,
            stream=stream_key.replace(STREAM_PREFIX, ""),
            data=data,
            timestamp=float(fields.get("_published_at", time.time())),
        )

        try:
            await handler(message)

            # Acknowledge successful processing
            await self._redis.xack(stream_key, self._group, msg_id)
            self._messages_processed += 1
            self._last_message_time = time.time()

            self._logger.debug(
                "message_processed",
                stream=message.stream,
                msg_id=msg_id,
            )
        except Exception as exc:
            self._messages_failed += 1
            self._logger.warning(
                "message_processing_failed",
                stream=message.stream,
                msg_id=msg_id,
                error=str(exc),
            )

            # Check delivery count — dead letter if exceeded
            delivery_count = await self._get_delivery_count(stream_key, msg_id)
            if delivery_count >= MAX_DELIVERY_COUNT:
                await self._dead_letter(stream_key, msg_id, data, str(exc))

    async def _get_delivery_count(self, stream_key: str, msg_id: str) -> int:
        """Get the delivery count for a pending message."""
        try:
            pending = await self._redis.xpending_range(
                stream_key, self._group,
                min=msg_id, max=msg_id, count=1,
            )
            if pending:
                return pending[0].get("times_delivered", 1)
        except (ConnectionError, OSError, TimeoutError):
            pass
        return 1

    async def _claim_stale_messages(self) -> None:
        """
        Claim messages that have been idle too long (worker crash recovery).

        This is the key mechanism for fault tolerance: if a consumer crashes
        while processing a message, another consumer will claim it after
        the idle threshold.
        """
        for stream_key in self._handlers:
            try:
                # Find idle pending messages
                pending = await self._redis.xpending_range(
                    stream_key, self._group,
                    min="-", max="+", count=10,
                    idle=CLAIM_IDLE_THRESHOLD_MS,
                )

                if not pending:
                    continue

                msg_ids = [p["message_id"] for p in pending]

                # Claim them
                claimed = await self._redis.xclaim(
                    stream_key, self._group,
                    self._consumer_name,
                    min_idle_time=CLAIM_IDLE_THRESHOLD_MS,
                    message_ids=msg_ids,
                )

                if claimed:
                    self._logger.info(
                        "claimed_stale_messages",
                        stream=stream_key,
                        count=len(claimed),
                    )

                    # Process claimed messages
                    handler = self._handlers[stream_key]
                    for msg_id, fields in claimed:
                        await self._process_message(stream_key, msg_id, fields, handler)

            except (ConnectionError, OSError, TimeoutError) as exc:
                self._logger.debug("claim_stale_failed", stream=stream_key, error=str(exc))

    async def _dead_letter(
        self,
        stream_key: str,
        msg_id: str,
        data: Dict[str, Any],
        error: str,
    ) -> None:
        """Move a message to the dead letter stream."""
        dl_key = f"{stream_key}{DEAD_LETTER_SUFFIX}"
        try:
            await self._redis.xadd(
                dl_key,
                {
                    "original_stream": stream_key,
                    "original_msg_id": msg_id,
                    "data": json.dumps(data, default=str),
                    "error": error,
                    "dead_lettered_at": str(time.time()),
                },
                maxlen=10_000,
            )
            # Ack the original message so it stops being redelivered
            await self._redis.xack(stream_key, self._group, msg_id)
            self._logger.warning(
                "message_dead_lettered",
                stream=stream_key,
                msg_id=msg_id,
                error=error,
            )
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.error("dead_letter_failed", error=str(exc))

    def get_stats(self) -> Dict[str, Any]:
        """Return consumer statistics."""
        return {
            "group": self._group,
            "consumer": self._consumer_name,
            "connected": self._connected,
            "running": self._running,
            "subscribed_streams": list(self._handlers.keys()),
            "messages_processed": self._messages_processed,
            "messages_failed": self._messages_failed,
            "last_message_time": self._last_message_time,
        }


class RedisStreamsManager:
    """
    Central manager for all Redis Streams producers and consumers.

    Provides a unified interface for the application to:
    - Create producers and consumers
    - Monitor stream health
    - Get aggregate statistics

    Usage:
        manager = RedisStreamsManager()
        await manager.connect()

        # Create a producer
        producer = manager.create_producer()

        # Create a consumer group
        consumer = manager.create_consumer("report_generators")
        await consumer.subscribe("intelligence.generated", handler=handle_report)
        await consumer.start()

        # Get stats
        stats = manager.get_all_stats()
    """

    def __init__(self):
        self._producers: List[RedisStreamsProducer] = []
        self._consumers: List[RedisStreamsConsumer] = []
        self._logger = logger.bind(component="streams_manager")

    async def connect(self) -> None:
        """Initialize the manager."""
        self._logger.info("streams_manager_initialized")

    async def disconnect(self) -> None:
        """Disconnect all producers and consumers."""
        for consumer in self._consumers:
            await consumer.disconnect()
        for producer in self._producers:
            await producer.disconnect()
        self._logger.info("streams_manager_disconnected")

    def create_producer(self) -> RedisStreamsProducer:
        """Create and register a new producer."""
        producer = RedisStreamsProducer()
        self._producers.append(producer)
        return producer

    def create_consumer(
        self,
        group: str,
        consumer_name: Optional[str] = None,
        **kwargs,
    ) -> RedisStreamsConsumer:
        """Create and register a new consumer."""
        consumer = RedisStreamsConsumer(group=group, consumer_name=consumer_name, **kwargs)
        self._consumers.append(consumer)
        return consumer

    async def get_stream_stats(self, stream: str) -> StreamStats:
        """Get statistics for a specific stream."""
        if not self._producers or not self._producers[0]._redis:
            return StreamStats(stream=stream)

        redis = self._producers[0]._redis
        stream_key = f"{STREAM_PREFIX}{stream}"

        try:
            info = await redis.xinfo_stream(stream_key)
            groups = await redis.xinfo_groups(stream_key)

            # Count dead letters
            dl_key = f"{stream_key}{DEAD_LETTER_SUFFIX}"
            dl_info = await redis.xinfo_stream(dl_key)
            dl_count = dl_info.get("length", 0)

            return StreamStats(
                stream=stream,
                length=info.get("length", 0),
                first_entry_id=info.get("first-entry", ("",))[0],
                last_entry_id=info.get("last-entry", ("",))[0],
                consumer_groups=len(groups),
                pending_count=sum(g.get("pending", 0) for g in groups),
                dead_letter_count=dl_count,
            )
        except (ConnectionError, OSError, TimeoutError) as exc:
            self._logger.warning("stream_stats_failed", stream=stream, error=str(exc))
            return StreamStats(stream=stream)

    def get_all_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics for all producers and consumers."""
        return {
            "producers": [p.is_connected for p in self._producers],
            "consumers": [c.get_stats() for c in self._consumers],
            "total_producers": len(self._producers),
            "total_consumers": len(self._consumers),
        }


# ── Singleton ──────────────────────────────────────────────────────

_streams_manager: Optional[RedisStreamsManager] = None


def get_streams_manager() -> RedisStreamsManager:
    """Get the singleton RedisStreamsManager."""
    global _streams_manager
    if _streams_manager is None:
        _streams_manager = RedisStreamsManager()
    return _streams_manager
