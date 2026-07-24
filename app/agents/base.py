"""
Agent Base — Core types for the event-driven agent architecture.

Provides AgentEvent, EventType, and supporting types used across
the codebase for inter-component communication.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """Event types for the agent event bus."""
    # Market events
    MARKET_ALERT = "market_alert"
    PRICE_CHANGE = "price_change"
    DEMAND_SHIFT = "demand_shift"

    # Credit events
    CREDIT_ASSESSMENT = "credit_assessment"
    DEFAULT_RISK = "default_risk"

    # Learning events
    MODEL_UPDATE = "model_update"
    FL_AGGREGATION = "fl_aggregation"

    # Evolution events
    EVOLUTION_CYCLE_COMPLETE = "evolution_cycle_complete"
    FEEDBACK_RECEIVED = "feedback_received"
    STRATEGY_ADAPTED = "strategy_adapted"

    # Agent lifecycle
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # System events
    DRIFT_ALERT = "drift_alert"
    HEALTH_CHECK = "health_check"


class AgentStatus(str, Enum):
    """Agent lifecycle states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentEvent:
    """An event published on the agent event bus."""
    event_type: EventType
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result of an agent action."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BiasharaAgent:
    """Base class for domain agents."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.status = AgentStatus.IDLE

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Handle an incoming event."""
        raise NotImplementedError

    def health_check(self) -> dict:
        """Return health status."""
        return {
            "name": self.name,
            "status": self.status.value,
            "description": self.description,
        }
