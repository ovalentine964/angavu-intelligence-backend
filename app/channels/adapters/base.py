"""
Base Channel Adapter — Abstract base and unified message types.

All channel adapters extend BaseChannelAdapter and normalize their
raw input into UnifiedMessage objects. The gateway only sees
UnifiedMessage — it never touches raw WhatsApp JIDs, SMS numbers,
or voice DTMF codes.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ChannelType(str, Enum):
    """Supported communication channels."""

    APP_TEXT = "app_text"
    APP_VOICE = "app_voice"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    USSD = "ussd"
    VOICE_CALL = "voice_call"


@dataclass
class UnifiedMessage:
    """
    Normalized message format across all channels.

    Every channel adapter converts its raw data into this format.
    The gateway only ever sees UnifiedMessage objects.
    """

    message_id: str
    channel: ChannelType
    worker_id: str
    content: str
    timestamp: str
    language: str | None = None
    content_type: str = "text"  # text, audio, image, location
    media_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        channel: ChannelType,
        worker_id: str,
        content: str,
        language: str | None = None,
        content_type: str = "text",
        **kwargs: Any,
    ) -> UnifiedMessage:
        """Create a new UnifiedMessage with auto-generated ID and timestamp."""
        return cls(
            message_id=str(uuid.uuid4()),
            channel=channel,
            worker_id=worker_id,
            content=content,
            timestamp=datetime.now(UTC).isoformat(),
            language=language,
            content_type=content_type,
            **kwargs,
        )


@dataclass
class ChannelResponse:
    """Response from the gateway to be delivered through a channel adapter."""

    success: bool
    content: str | None = None
    channel: ChannelType | None = None
    session_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseChannelAdapter(ABC):
    """
    Abstract base class for all channel adapters.

    Each adapter must:
    1. Implement parse_raw_message() to convert channel-specific data
       into a UnifiedMessage
    2. Implement send_message() to deliver responses back through the channel
    3. Set channel_type to identify itself
    """

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType:
        """The channel type this adapter handles."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the adapter (connect, verify credentials, etc.)."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean shutdown of the adapter."""
        ...

    @abstractmethod
    async def parse_raw_message(
        self, raw_data: dict[str, Any]
    ) -> UnifiedMessage:
        """Convert channel-specific raw data into a UnifiedMessage."""
        ...

    @abstractmethod
    async def send_message(
        self,
        recipient_id: str,
        content: str,
        content_type: str = "text",
        **kwargs: Any,
    ) -> bool:
        """Send a message through this channel. Returns True on success."""
        ...

    async def resolve_worker_id(self, channel_user_id: str) -> str | None:
        """
        Resolve a channel-specific user ID to a canonical worker ID.
        Override in adapters that have a mapping (e.g., phone → UUID).
        """
        return None

    async def health_check(self) -> bool:
        """Check if the adapter is healthy and can send/receive."""
        return True
