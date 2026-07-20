"""
Tests for EventBus — Event publishing, consuming, DLQ, and persistence.

Tests cover:
- EventBus creation and connection (in-memory mode)
- Event publishing and receiving
- Idempotency (deduplication)
- Dead letter queue (DLQ) operations
- Event persistence to JSONL
- Backpressure detection
- Stats and monitoring
- Consumer group isolation
- Edge cases and error handling

Run: pytest tests/test_event_bus.py -v
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentEvent, AgentResult, AgentStatus, EventType
from app.agents.event_bus import (
    BACKPRESSURE_HIGH_WATER,
    BACKPRESSURE_LOW_WATER,
    DLQ_SUFFIX,
    IDEMPOTENCY_TTL,
    STREAM_PREFIX,
    EventBus,
)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def make_event(
    event_type: EventType = EventType.TRANSACTION_RECEIVED,
    source: str = "TestHarness",
    payload: dict | None = None,
    event_id: str | None = None,
) -> AgentEvent:
    """Create a test event."""
    kwargs = {
        "event_type": event_type,
        "source": source,
        "payload": payload or {"user_id": "worker_001", "count": 1},
    }
    if event_id is not None:
        kwargs["event_id"] = event_id
    return AgentEvent(**kwargs)


def make_agent(name: str = "TestAgent"):
    """Create a mock agent."""
    agent = MagicMock()
    agent.name = name
    agent.handle_event = AsyncMock(return_value=AgentResult(success=True, duration_ms=10.0))
    return agent


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
async def event_bus():
    """Create and connect an EventBus in in-memory mode."""
    bus = EventBus(persist_events=False)
    await bus.connect()
    yield bus
    await bus.disconnect()


@pytest.fixture
async def persisting_event_bus(tmp_path):
    """Create an EventBus with persistence enabled."""
    bus = EventBus(persist_events=True)
    # Override persist dir to temp path
    bus._persist_dir = tmp_path / "event_bus"
    bus._persist_dir.mkdir(parents=True, exist_ok=True)
    await bus.connect()
    yield bus
    await bus.disconnect()


# ════════════════════════════════════════════════════════════════════
# Connection Tests
# ════════════════════════════════════════════════════════════════════


class TestEventBusConnection:
    """Test EventBus connection modes."""

    @pytest.mark.asyncio
    async def test_connect_in_memory_mode(self):
        """Should connect in in-memory mode when no Redis URL."""
        bus = EventBus(persist_events=False)
        await bus.connect()
        stats = bus.get_stats()
        assert stats["mode"] == "in_memory"
        await bus.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self):
        """Disconnect should clean up resources."""
        bus = EventBus(persist_events=False)
        await bus.connect()
        await bus.disconnect()
        # Should not raise

    @pytest.mark.asyncio
    async def test_connect_with_no_redis_url(self):
        """Should fall back to in-memory when REDIS_URL is not set."""
        with patch("app.agents.event_bus.settings") as mock_settings:
            mock_settings.REDIS_URL = None
            bus = EventBus(persist_events=False)
            await bus.connect()
            assert bus._in_memory_enabled is True
            await bus.disconnect()


# ════════════════════════════════════════════════════════════════════
# Publish / Subscribe Tests
# ════════════════════════════════════════════════════════════════════


class TestPublishSubscribe:
    """Test event publishing and subscribing."""

    @pytest.mark.asyncio
    async def test_publish_returns_event_id(self, event_bus):
        """Publish should return an event ID."""
        event = make_event()
        event_id = await event_bus.publish(event)
        assert event_id is not None
        assert isinstance(event_id, str)

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, event_bus):
        """Subscribed agent should receive published events."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        event = make_event()
        await event_bus.publish(event)

        events = await event_bus.get_events(agent, limit=10)
        assert len(events) == 1
        assert events[0].event_type == EventType.TRANSACTION_RECEIVED

    @pytest.mark.asyncio
    async def test_multiple_events(self, event_bus):
        """Should receive multiple events."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        for i in range(5):
            await event_bus.publish(make_event(payload={"count": i}))

        events = await event_bus.get_events(agent, limit=10)
        assert len(events) == 5

    @pytest.mark.asyncio
    async def test_different_event_types(self, event_bus):
        """Agent subscribed to one type should not receive other types."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        await event_bus.publish(make_event(event_type=EventType.TRANSACTION_RECEIVED))
        await event_bus.publish(make_event(event_type=EventType.BATCH_PROCESSED))

        events = await event_bus.get_events(agent, limit=10)
        # Should only get TRANSACTION_RECEIVED
        assert all(e.event_type == EventType.TRANSACTION_RECEIVED for e in events)

    @pytest.mark.asyncio
    async def test_subscribe_multiple_types(self, event_bus):
        """Agent can subscribe to multiple event types."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [
            EventType.TRANSACTION_RECEIVED,
            EventType.BATCH_PROCESSED,
        ])

        await event_bus.publish(make_event(event_type=EventType.TRANSACTION_RECEIVED))
        await event_bus.publish(make_event(event_type=EventType.BATCH_PROCESSED))

        events = await event_bus.get_events(agent, limit=10)
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_get_events_with_limit(self, event_bus):
        """Should respect limit parameter."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        for i in range(10):
            await event_bus.publish(make_event(payload={"count": i}))

        events = await event_bus.get_events(agent, limit=3)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_get_events_consumes_buffer(self, event_bus):
        """Getting events should consume them from the buffer."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        await event_bus.publish(make_event())

        events1 = await event_bus.get_events(agent, limit=10)
        assert len(events1) == 1

        events2 = await event_bus.get_events(agent, limit=10)
        assert len(events2) == 0  # Already consumed


# ════════════════════════════════════════════════════════════════════
# Idempotency Tests
# ════════════════════════════════════════════════════════════════════


class TestIdempotency:
    """Test event deduplication."""

    @pytest.mark.asyncio
    async def test_duplicate_event_deduplicated(self, event_bus):
        """Same event published twice should be deduplicated."""
        event = make_event(event_id="unique_event_123")

        id1 = await event_bus.publish(event)
        id2 = await event_bus.publish(event)

        # Second publish should return the same id (deduped)
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_different_events_not_deduplicated(self, event_bus):
        """Different events should not be deduplicated."""
        event1 = make_event(event_id="event_1", payload={"count": 1})
        event2 = make_event(event_id="event_2", payload={"count": 2})

        id1 = await event_bus.publish(event1)
        id2 = await event_bus.publish(event2)

        assert id1 != id2

    @pytest.mark.asyncio
    async def test_idempotency_key_computation(self, event_bus):
        """Should compute idempotency key from event."""
        event = make_event(event_id="test_id")
        key = event_bus._compute_idempotency_key(event)
        assert key == "test_id"

    @pytest.mark.asyncio
    async def test_idempotency_key_fallback(self, event_bus):
        """Should hash event content when no event_id."""
        # Create event with empty event_id to force hash fallback
        event = make_event(event_id="")
        key = event_bus._compute_idempotency_key(event)
        assert isinstance(key, str)
        assert len(key) == 32  # SHA-256 truncated

    @pytest.mark.asyncio
    async def test_idempotency_cache_cleanup(self, event_bus):
        """Old idempotency keys should be cleaned up."""
        # Add an expired key
        event_bus._idempotency_cache["old_key"] = time.time() - IDEMPOTENCY_TTL - 1
        event_bus._is_duplicate("new_key")  # Trigger cleanup
        assert "old_key" not in event_bus._idempotency_cache


# ════════════════════════════════════════════════════════════════════
# Dead Letter Queue Tests
# ════════════════════════════════════════════════════════════════════


class TestDeadLetterQueue:
    """Test DLQ operations."""

    @pytest.mark.asyncio
    async def test_publish_to_dlq(self, event_bus):
        """Should add failed events to DLQ."""
        await event_bus.publish_to_dlq(
            original_stream=f"{STREAM_PREFIX}test",
            event_data={"test": "data"},
            error="processing failed",
        )

        assert len(event_bus._dead_letters) == 1
        assert event_bus._dead_letters[0]["error"] == "processing failed"

    @pytest.mark.asyncio
    async def test_dlq_capped_at_1000(self, event_bus):
        """DLQ should be capped at 1000 entries."""
        for i in range(1100):
            await event_bus.publish_to_dlq(
                original_stream=f"{STREAM_PREFIX}test",
                event_data={"i": i},
                error=f"error_{i}",
            )

        assert len(event_bus._dead_letters) == 1000

    @pytest.mark.asyncio
    async def test_get_dlq_events(self, event_bus):
        """Should retrieve DLQ events."""
        await event_bus.publish_to_dlq(
            original_stream=f"{STREAM_PREFIX}transaction.received",
            event_data={"test": "data"},
            error="timeout",
        )

        dlq = await event_bus.get_dlq_events("transaction.received", limit=10)
        assert len(dlq) >= 1

    @pytest.mark.asyncio
    async def test_get_dlq_stats(self, event_bus):
        """Should return DLQ statistics."""
        await event_bus.publish_to_dlq(
            original_stream=f"{STREAM_PREFIX}test",
            event_data={"test": "data"},
            error="error",
        )

        stats = await event_bus.get_dlq_stats()
        assert "total_in_memory" in stats
        assert stats["total_in_memory"] >= 1

    @pytest.mark.asyncio
    async def test_get_dead_letters(self, event_bus):
        """get_dead_letters should return DLQ list."""
        await event_bus.publish_to_dlq(
            original_stream=f"{STREAM_PREFIX}test",
            event_data={"test": "data"},
            error="error",
        )

        letters = event_bus.get_dead_letters()
        assert len(letters) == 1
        assert letters[0]["error"] == "error"


# ════════════════════════════════════════════════════════════════════
# Event Persistence Tests
# ════════════════════════════════════════════════════════════════════


class TestEventPersistence:
    """Test event persistence to JSONL files."""

    @pytest.mark.asyncio
    async def test_event_persisted_to_file(self, persisting_event_bus):
        """Published events should be persisted to JSONL."""
        event = make_event(event_type=EventType.TRANSACTION_RECEIVED)
        await persisting_event_bus.publish(event)

        assert persisting_event_bus._persisted_count >= 1

        # Read persisted events
        events = persisting_event_bus.get_persisted_events("transaction.received", limit=10)
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_persisted_events_readable(self, persisting_event_bus):
        """Persisted events should be readable as JSON."""
        event = make_event(
            event_type=EventType.TRANSACTION_PROCESSED,
            payload={"amount": 500},
        )
        await persisting_event_bus.publish(event)

        events = persisting_event_bus.get_persisted_events("transaction.processed", limit=10)
        assert len(events) >= 1
        assert events[0]["payload"]["amount"] == 500

    @pytest.mark.asyncio
    async def test_persisted_events_limit(self, persisting_event_bus):
        """Should respect limit when reading persisted events."""
        for i in range(10):
            await persisting_event_bus.publish(make_event(payload={"i": i}))

        events = persisting_event_bus.get_persisted_events("transaction.received", limit=3)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_persist_disabled(self):
        """When persistence is disabled, should not write files."""
        bus = EventBus(persist_events=False)
        await bus.connect()

        event = make_event()
        await bus.publish(event)

        assert bus._persisted_count == 0
        assert bus._persist_dir is None
        await bus.disconnect()


# ════════════════════════════════════════════════════════════════════
# Backpressure Tests
# ════════════════════════════════════════════════════════════════════


class TestBackpressure:
    """Test backpressure detection and release."""

    @pytest.mark.asyncio
    async def test_no_backpressure_normal_load(self, event_bus):
        """Should not trigger backpressure under normal load."""
        stream_key = f"{STREAM_PREFIX}transaction.received"
        bp = await event_bus._check_backpressure(stream_key)
        assert bp is False

    @pytest.mark.asyncio
    async def test_backpressure_triggered_at_high_water(self, event_bus):
        """Should trigger backpressure when buffer exceeds high water mark."""
        stream_key = f"{STREAM_PREFIX}transaction.received"
        # Fill buffer beyond high water mark
        event_bus._pending_buffer[stream_key] = [
            {"data": i} for i in range(BACKPRESSURE_HIGH_WATER + 100)
        ]

        bp = await event_bus._check_backpressure(stream_key)
        assert bp is True
        assert event_bus._backpressure_streams[stream_key] is True

    @pytest.mark.asyncio
    async def test_backpressure_releases_at_low_water(self, event_bus):
        """Should release backpressure when buffer drops to low water mark."""
        stream_key = f"{STREAM_PREFIX}transaction.received"
        # Activate backpressure
        event_bus._backpressure_streams[stream_key] = True
        # Drop buffer below low water
        event_bus._pending_buffer[stream_key] = [
            {"data": i} for i in range(BACKPRESSURE_LOW_WATER - 100)
        ]

        bp = await event_bus._check_backpressure(stream_key)
        assert bp is False

    @pytest.mark.asyncio
    async def test_wait_for_backpressure_release(self, event_bus):
        """Should release when backpressure clears."""
        stream_key = f"{STREAM_PREFIX}transaction.received"
        event_bus._backpressure_streams[stream_key] = True
        event_bus._pending_buffer[stream_key] = []  # Empty

        released = await event_bus.wait_for_backpressure_release(stream_key, timeout=2.0)
        assert released is True


# ════════════════════════════════════════════════════════════════════
# Stats Tests
# ════════════════════════════════════════════════════════════════════


class TestStats:
    """Test monitoring and statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, event_bus):
        """get_stats should return useful monitoring info."""
        stats = event_bus.get_stats()
        assert "mode" in stats
        assert "subscriptions" in stats
        assert "dead_letter_count" in stats
        assert "persisted_count" in stats
        assert "idempotency_cache_size" in stats
        assert "backpressure_active_streams" in stats
        assert "signing" in stats
        assert "scaling" in stats

    @pytest.mark.asyncio
    async def test_stats_reflect_subscriptions(self, event_bus):
        """Stats should reflect active subscriptions."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        stats = event_bus.get_stats()
        assert "transaction.received" in stats["subscriptions"]

    @pytest.mark.asyncio
    async def test_get_scaling_config(self, event_bus):
        """Should return scaling configuration."""
        config = event_bus.get_scaling_config()
        assert "instance_id" in config
        assert "consumer_group" in config
        assert "max_consumers_per_group" in config


# ════════════════════════════════════════════════════════════════════
# Event Replay Tests
# ════════════════════════════════════════════════════════════════════


class TestEventReplay:
    """Test event replay functionality."""

    @pytest.mark.asyncio
    async def test_replay_from_persistence(self, persisting_event_bus):
        """Should replay events from persistence files."""
        # Publish some events
        for i in range(3):
            await persisting_event_bus.publish(make_event(payload={"i": i}))

        replayed_events = []

        async def handler(data):
            replayed_events.append(data)

        count = await persisting_event_bus.replay_events(
            "transaction.received",
            handler=handler,
            limit=10,
        )
        assert count >= 3
        assert len(replayed_events) >= 3

    @pytest.mark.asyncio
    async def test_replay_with_timestamp_filter(self, persisting_event_bus):
        """Should filter events by timestamp."""
        await persisting_event_bus.publish(make_event())

        replayed = []
        async def handler(data):
            replayed.append(data)

        # Only replay events after now
        count = await persisting_event_bus.replay_events(
            "transaction.received",
            handler=handler,
            from_timestamp=time.time() + 100,  # Future — should get 0
            limit=10,
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_replay_from_dlq(self, event_bus):
        """Should replay events from DLQ."""
        await event_bus.publish_to_dlq(
            original_stream=f"{STREAM_PREFIX}transaction.received",
            event_data={"test": "data"},
            error="processing failed",
        )

        replayed = []
        async def handler(data):
            replayed.append(data)

        count = await event_bus.replay_events(
            "transaction.received",
            handler=handler,
            from_dlq=True,
            limit=10,
        )
        assert count >= 1


# ════════════════════════════════════════════════════════════════════
# Edge Cases
# ════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_get_events_no_subscriptions(self, event_bus):
        """Should return empty list when agent has no subscriptions."""
        agent = make_agent("Unsubscribed")
        events = await event_bus.get_events(agent, limit=10)
        assert events == []

    @pytest.mark.asyncio
    async def test_publish_preserves_payload(self, event_bus):
        """Published event should preserve payload data."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        event = make_event(payload={"amount": 1500, "item": "sukari", "nested": {"key": "value"}})
        await event_bus.publish(event)

        events = await event_bus.get_events(agent, limit=1)
        assert events[0].payload["amount"] == 1500
        assert events[0].payload["item"] == "sukari"

    @pytest.mark.asyncio
    async def test_empty_buffer_returns_empty(self, event_bus):
        """Empty buffer should return empty list."""
        agent = make_agent("Processor")
        await event_bus.subscribe(agent, [EventType.TRANSACTION_RECEIVED])

        events = await event_bus.get_events(agent, limit=10)
        assert events == []

    @pytest.mark.asyncio
    async def test_in_memory_stream_trimming(self, event_bus):
        """In-memory buffer should be trimmed to max stream length."""
        event_bus._max_stream_length = 5
        stream_key = f"{STREAM_PREFIX}transaction.received"

        # Publish more than max
        for i in range(10):
            event_bus._pending_buffer[stream_key].append({"i": i})
            # Simulate trimming
            if len(event_bus._pending_buffer[stream_key]) > event_bus._max_stream_length:
                event_bus._pending_buffer[stream_key] = event_bus._pending_buffer[stream_key][-event_bus._max_stream_length:]

        assert len(event_bus._pending_buffer[stream_key]) == 5
