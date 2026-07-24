"""
Base agent abstractions for Angavu Intelligence.

Provides the core types used across the agent system:
- AgentEvent: Events flowing through the system
- AgentResult: Results returned from agent processing
- AgentStatus: Agent lifecycle states
- BiasharaAgent: Base class for all agents
- EventType: Enumeration of all event types
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional


class AgentStatus(str, Enum):
    """Agent lifecycle states."""
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


class EventType(str, Enum):
    """All event types flowing through the system."""
    # Task lifecycle
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_STARTED = "task.started"

    # Market / intelligence
    MARKET_ALERT = "market.alert"
    TRANSACTION_PROCESSED = "transaction.processed"

    # Evolution / learning
    EVOLUTION_CYCLE_COMPLETE = "evolution.cycle.complete"
    FEEDBACK_RECEIVED = "feedback.received"
    CUSTOMER_FEEDBACK_RECEIVED = "customer.feedback.received"
    ADAPTIVE_LEARNING_SYNCED = "adaptive_learning.synced"
    MEMORY_CONSOLIDATED = "memory.consolidated"

    # Sessions
    SESSION_CREATED = "session.created"
    SESSION_RESUMED = "session.resumed"

    # Skills
    SKILL_DISCOVERED = "skill.discovered"

    # Performance
    AGENT_PERFORMANCE_RECORDED = "agent.performance.recorded"

    # Security / PQC
    KEY_GENERATED = "key.generated"
    KEY_EXCHANGE_FAILURE = "key_exchange.failure"
    ENCRYPT_FAILURE = "encrypt.failure"
    DECRYPT_FAILURE = "decrypt.failure"
    SIGN_FAILURE = "sign.failure"
    VERIFY_FAILURE = "verify.failure"
    ALGORITHM_CHANGE = "algorithm.change"


@dataclass
class AgentEvent:
    """An event flowing through the agent system."""
    event_type: EventType
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
        }


@dataclass
class AgentResult:
    """Result returned from agent processing."""
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            d["data"] = self.data
        if self.error is not None:
            d["error"] = self.error
        return d


class BiasharaAgent:
    """Base class for all agents in the system."""

    def __init__(self, name: str = "BiasharaAgent", description: str = ""):
        self.name = name
        self.description = description
        self.status = AgentStatus.IDLE

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Handle an incoming event. Override in subclasses."""
        return AgentResult(success=True, data={"handled_by": self.name})

    def health_check(self) -> dict[str, Any]:
        """Return agent health status."""
        return {
            "name": self.name,
            "status": self.status.value,
        }

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a task. Override in subclasses."""
        return {"status": "not_implemented", "agent": self.name}
