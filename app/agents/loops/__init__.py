"""
Agent Loops — Event store and loop pattern implementations.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class StoredEvent:
    """An event stored in the event store."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 0
    event_type: str = ""
    source: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventStore:
    """
    Append-only event store for loop patterns.

    Stores events for replay, debugging, and audit.
    """

    def __init__(self):
        self._events: list[StoredEvent] = []
        self._by_type: dict[str, list[StoredEvent]] = defaultdict(list)
        self._sequence = 0

    def append(self, event_type: str, source: str, payload: dict = None) -> StoredEvent:
        """Append an event to the store."""
        self._sequence += 1
        event = StoredEvent(
            sequence=self._sequence,
            event_type=event_type,
            source=source,
            payload=payload or {},
        )
        self._events.append(event)
        self._by_type[event_type].append(event)
        return event

    def query(
        self,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[StoredEvent]:
        """Query events with optional filters."""
        if event_type:
            events = self._by_type.get(event_type, [])
        else:
            events = self._events

        if since:
            events = [e for e in events if e.timestamp >= since]

        return events[-limit:]

    def replay(self, from_sequence: int = 0) -> list[StoredEvent]:
        """Replay events from a given sequence number."""
        return [e for e in self._events if e.sequence > from_sequence]

    def get_stats(self) -> dict:
        """Get event store statistics."""
        return {
            "total_events": len(self._events),
            "event_types": {k: len(v) for k, v in self._by_type.items()},
            "last_sequence": self._sequence,
        }
