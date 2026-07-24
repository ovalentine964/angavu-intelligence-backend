"""
Agent Loops — Loop pattern implementations for agentic reasoning.

Provides:
- EventStore: Event sourcing store for audit and replay
- OODAAgent: Observe-Orient-Decide-Act loop agent
- FeedbackAgent: Self-improving feedback loop agent
- HumanInTheLoopAgent: Human escalation and trust management
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class StoredEvent:
    """An event stored in the event store."""
    event_id: str
    event_type: str
    source: str
    payload: dict[str, Any]
    sequence: int
    aggregate_id: str | None = None
    correlation_id: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
            "sequence": self.sequence,
            "aggregate_id": self.aggregate_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }


class EventStore:
    """
    In-memory event store for agent event sourcing.

    Provides append-only storage, replay, and correlation
    for debugging and audit trails.
    """

    def __init__(self, max_events: int = 10000):
        self._events: list[StoredEvent] = []
        self._max_events = max_events
        self._sequence = 0
        self._by_type: dict[str, list[StoredEvent]] = defaultdict(list)
        self._by_aggregate: dict[str, list[StoredEvent]] = defaultdict(list)
        self._by_correlation: dict[str, list[StoredEvent]] = defaultdict(list)

    def append(
        self,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        aggregate_id: str | None = None,
        correlation_id: str | None = None,
    ) -> StoredEvent:
        """Append an event to the store."""
        self._sequence += 1
        event = StoredEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source=source,
            payload=payload,
            sequence=self._sequence,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
        )
        self._events.append(event)
        self._by_type[event_type].append(event)
        if aggregate_id:
            self._by_aggregate[aggregate_id].append(event)
        if correlation_id:
            self._by_correlation[correlation_id].append(event)

        if len(self._events) > self._max_events:
            self._trim()

        return event

    def get_events(
        self,
        event_type: str | None = None,
        source: str | None = None,
        aggregate_id: str | None = None,
        since_sequence: int = 0,
        limit: int = 50,
    ) -> list[StoredEvent]:
        """Query events with filters."""
        events = self._events

        if event_type:
            events = self._by_type.get(event_type, [])
        if aggregate_id:
            events = self._by_aggregate.get(aggregate_id, events)
        if source:
            events = [e for e in events if e.source == source]
        if since_sequence > 0:
            events = [e for e in events if e.sequence > since_sequence]

        return events[-limit:]

    def replay(
        self,
        from_sequence: int = 0,
        to_sequence: int | None = None,
    ) -> list[StoredEvent]:
        """Replay events from a sequence range."""
        events = [e for e in self._events if e.sequence > from_sequence]
        if to_sequence is not None:
            events = [e for e in events if e.sequence <= to_sequence]
        return events

    def get_correlated_events(self, correlation_id: str) -> list[StoredEvent]:
        """Get all events sharing a correlation ID."""
        return self._by_correlation.get(correlation_id, [])

    def get_stats(self) -> dict[str, Any]:
        """Return store statistics."""
        return {
            "total_events": len(self._events),
            "current_sequence": self._sequence,
            "event_types": {k: len(v) for k, v in self._by_type.items()},
        }

    def _trim(self) -> None:
        """Trim old events to stay within limits."""
        keep = self._max_events // 2
        self._events = self._events[-keep:]
        # Rebuild indexes
        self._by_type.clear()
        self._by_aggregate.clear()
        self._by_correlation.clear()
        for e in self._events:
            self._by_type[e.event_type].append(e)
            if e.aggregate_id:
                self._by_aggregate[e.aggregate_id].append(e)
            if e.correlation_id:
                self._by_correlation[e.correlation_id].append(e)
