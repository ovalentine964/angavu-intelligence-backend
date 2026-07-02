"""
Base Trigger — Factor 11: Trigger from Anywhere.

Abstract base for all trigger channels. Normalizes diverse input
formats (WhatsApp, USSD, SMS, Voice) into a standard TriggerIntent
that agents can process uniformly.

Flow:
    Raw Input → Trigger.receive() → TriggerIntent → Agent.handle() → TriggerResponse → Trigger.send()
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class TriggerChannel(str, Enum):
    """Supported trigger channels."""
    WHATSAPP = "whatsapp"
    USSD = "ussd"
    SMS = "sms"
    VOICE = "voice"
    APP = "app"  # Android app (direct)
    WEB = "web"  # Web dashboard


class IntentType(str, Enum):
    """Standardized intent types across all channels."""
    # Transaction
    RECORD_SALE = "record_sale"
    RECORD_PURCHASE = "record_purchase"
    RECORD_EXPENSE = "record_expense"

    # Query
    CHECK_BALANCE = "check_balance"
    CHECK_SALES = "check_sales"
    CHECK_STOCK = "check_stock"
    CHECK_PROFIT = "check_profit"
    CHECK_REPORT = "check_report"

    # Finance
    TITHE_RECORD = "tithe_record"
    GOAL_CREATE = "goal_create"
    GOAL_PROGRESS = "goal_progress"
    LOAN_CHECK = "loan_check"

    # System
    HELP = "help"
    FEEDBACK = "feedback"
    LANGUAGE_SWITCH = "language_switch"

    # Fallback
    UNKNOWN = "unknown"


@dataclass
class TriggerIntent:
    """
    Standardized intent extracted from any trigger channel.

    All triggers normalize their input to this format.
    Agents process TriggerIntents without knowing the source channel.
    """
    intent_type: IntentType
    raw_input: str
    channel: TriggerChannel
    user_id: str  # Phone number, USSD session ID, etc.
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    language: str = "sw"  # Default Swahili
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_type": self.intent_type.value,
            "raw_input": self.raw_input,
            "channel": self.channel.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "language": self.language,
            "extracted_data": self.extracted_data,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
        }


@dataclass
class TriggerResponse:
    """
    Response from an agent to be delivered back through the trigger channel.
    """
    text: str
    response_type: str = "text"  # text, voice, menu, image
    data: Dict[str, Any] = field(default_factory=dict)
    follow_up: Optional[str] = None  # Prompt for next input
    session_end: bool = False  # End the conversation session
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "response_type": self.response_type,
            "data": self.data,
            "follow_up": self.follow_up,
            "session_end": self.session_end,
            "metadata": self.metadata,
        }


class BaseTrigger(ABC):
    """
    Abstract base class for all trigger channels.

    Subclasses implement:
    - receive(): Parse raw channel input into TriggerIntent
    - send(): Format TriggerResponse for the channel
    - get_channel(): Return the channel type

    The trigger system handles:
    - Intent normalization
    - Session management
    - Error handling
    - Metrics collection
    """

    def __init__(self):
        self._logger = logger.bind(
            channel=self.get_channel().value,
            component="trigger",
        )
        self._sessions: Dict[str, Dict[str, Any]] = {}  # session_id → session state

    @abstractmethod
    def get_channel(self) -> TriggerChannel:
        """Return the channel type."""
        ...

    @abstractmethod
    async def receive(self, raw_input: Any) -> TriggerIntent:
        """
        Parse raw channel input into a TriggerIntent.

        Args:
            raw_input: Channel-specific input (webhook payload, USSD menu selection, etc.)

        Returns:
            Normalized TriggerIntent
        """
        ...

    @abstractmethod
    async def send(
        self,
        response: TriggerResponse,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Send a response back through the channel.

        Args:
            response: The agent's response
            user_id: Target user
            session_id: Optional session for multi-turn

        Returns:
            True if sent successfully
        """
        ...

    # ── Session Management ──────────────────────────────────────────

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get or create a session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "session_id": session_id,
                "created_at": time.time(),
                "turn_count": 0,
                "context": {},
            }
        return self._sessions[session_id]

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> None:
        """Update session state."""
        session = self.get_session(session_id)
        session.update(updates)
        session["turn_count"] = session.get("turn_count", 0) + 1
        session["last_active"] = time.time()

    def end_session(self, session_id: str) -> None:
        """End and clean up a session."""
        self._sessions.pop(session_id, None)

    def cleanup_expired_sessions(self, max_age: float = 1800.0) -> int:
        """Clean up sessions older than max_age seconds."""
        now = time.time()
        expired = [
            sid for sid, session in self._sessions.items()
            if now - session.get("last_active", session.get("created_at", 0)) > max_age
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    # ── Health ──────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Return trigger health status."""
        return {
            "channel": self.get_channel().value,
            "active_sessions": len(self._sessions),
            "status": "healthy",
        }
