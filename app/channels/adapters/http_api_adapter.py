"""
HTTP API Channel Adapter — Last-resort communication fallback.

A simple REST API endpoint that clients can poll for pending messages.
This is the ultimate fallback when all other channels (WhatsApp, Telegram, SMS)
are unavailable.

Use cases:
- Emergency dashboard notifications
- Mobile app polling for messages
- Webhook delivery to third-party systems
- Integration with local USSD gateways

The HTTP API adapter stores messages in a queue and exposes them
via a REST endpoint. Clients poll for pending messages.

Configuration:
    HTTP_API_ENABLED: Enable the HTTP API channel (default: true)
    HTTP_API_SECRET: Shared secret for API authentication
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

import structlog

from app.channels.adapters.base import (
    BaseChannelAdapter,
    ChannelType,
    UnifiedMessage,
)

logger = structlog.get_logger(__name__)

# Maximum messages to queue per recipient
MAX_QUEUE_SIZE = 100

# Message TTL in seconds (messages expire after this)
MESSAGE_TTL_SECONDS = 86400  # 24 hours


class PendingMessage:
    """A message queued for delivery via HTTP API."""

    def __init__(
        self,
        message_id: str,
        recipient_id: str,
        content: str,
        content_type: str = "text",
        metadata: dict | None = None,
    ):
        self.message_id = message_id
        self.recipient_id = recipient_id
        self.content = content
        self.content_type = content_type
        self.metadata = metadata or {}
        self.created_at = datetime.now(UTC)
        self.delivered = False
        self.delivery_count = 0

    def is_expired(self) -> bool:
        """Check if the message has expired."""
        age = (datetime.now(UTC) - self.created_at).total_seconds()
        return age > MESSAGE_TTL_SECONDS

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "message_id": self.message_id,
            "content": self.content,
            "content_type": self.content_type,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class HttpApiAdapter(BaseChannelAdapter):
    """
    HTTP API adapter — last-resort message delivery.

    Messages are queued in memory and exposed via REST endpoints.
    Clients poll for pending messages using their recipient_id.

    This is the fallback of last resort — it doesn't push messages,
    but makes them available for pull-based delivery.
    """

    def __init__(self, api_secret: str | None = None):
        self._api_secret = api_secret
        self._initialized = False
        self._message_queue: dict[str, deque[PendingMessage]] = {}
        self._send_count: int = 0
        self._poll_count: int = 0

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.HTTP_API

    async def initialize(self) -> None:
        """Initialize HTTP API adapter."""
        self._initialized = True
        logger.info("http_api_adapter_initialized")

    async def shutdown(self) -> None:
        """Shutdown HTTP API adapter."""
        self._initialized = False
        logger.info("http_api_adapter_shutdown")

    async def parse_raw_message(
        self, raw_data: dict[str, Any]
    ) -> UnifiedMessage:
        """
        Parse HTTP API request into UnifiedMessage.

        Expected payload:
        {
            "worker_id": "uuid or phone",
            "content": "message text",
            "language": "sw",
            "content_type": "text"
        }
        """
        return UnifiedMessage.create(
            channel=ChannelType.APP_TEXT,
            worker_id=raw_data.get("worker_id", ""),
            content=raw_data.get("content", ""),
            language=raw_data.get("language", "sw"),
            content_type=raw_data.get("content_type", "text"),
            metadata={
                "source": "http_api",
                "remote_addr": raw_data.get("remote_addr"),
            },
        )

    async def send_message(
        self,
        recipient_id: str,
        content: str,
        content_type: str = "text",
        **kwargs: Any,
    ) -> bool:
        """
        Queue a message for HTTP API delivery.

        The message is stored in an in-memory queue and will be
        delivered when the client polls for pending messages.

        Args:
            recipient_id: Worker ID or phone number
            content: Message content
            content_type: Type of content

        Returns:
            True (message is always queued successfully in memory)
        """
        message_id = str(uuid.uuid4())

        # Initialize queue for recipient if needed
        if recipient_id not in self._message_queue:
            self._message_queue[recipient_id] = deque(maxlen=MAX_QUEUE_SIZE)

        # Queue the message
        pending = PendingMessage(
            message_id=message_id,
            recipient_id=recipient_id,
            content=content,
            content_type=content_type,
            metadata=kwargs.get("metadata", {}),
        )
        self._message_queue[recipient_id].append(pending)
        self._send_count += 1

        logger.info(
            "http_api_message_queued",
            recipient_id=recipient_id[:8] + "***",
            message_id=message_id,
            queue_size=len(self._message_queue[recipient_id]),
        )
        return True

    async def send_image(
        self,
        recipient_id: str,
        image_data: bytes,
        caption: str = "",
    ) -> bool:
        """Queue an image message (stored as base64 for API retrieval)."""
        import base64

        image_b64 = base64.b64encode(image_data).decode("utf-8")
        message_id = str(uuid.uuid4())

        if recipient_id not in self._message_queue:
            self._message_queue[recipient_id] = deque(maxlen=MAX_QUEUE_SIZE)

        pending = PendingMessage(
            message_id=message_id,
            recipient_id=recipient_id,
            content=caption,
            content_type="image",
            metadata={"image_base64": image_b64},
        )
        self._message_queue[recipient_id].append(pending)
        self._send_count += 1
        return True

    async def get_pending_messages(
        self,
        recipient_id: str,
        mark_delivered: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get pending messages for a recipient.

        Called by the HTTP API endpoint when a client polls.

        Args:
            recipient_id: Worker ID or phone number
            mark_delivered: If True, mark messages as delivered

        Returns:
            List of pending message dicts
        """
        self._poll_count += 1

        if recipient_id not in self._message_queue:
            return []

        # Clean expired messages
        queue = self._message_queue[recipient_id]
        valid_messages = []
        while queue:
            msg = queue[0]
            if msg.is_expired():
                queue.popleft()
            else:
                valid_messages.append(msg)
                queue.popleft()

        # Get undelivered messages
        pending = [msg for msg in valid_messages if not msg.delivered]

        if mark_delivered:
            for msg in pending:
                msg.delivered = True
                msg.delivery_count += 1

        logger.info(
            "http_api_messages_polled",
            recipient_id=recipient_id[:8] + "***",
            pending_count=len(pending),
        )

        return [msg.to_dict() for msg in pending]

    async def get_queue_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        total_pending = sum(
            len(q) for q in self._message_queue.values()
        )
        return {
            "total_recipients": len(self._message_queue),
            "total_pending": total_pending,
            "total_sent": self._send_count,
            "total_polled": self._poll_count,
        }

    async def resolve_worker_id(self, channel_user_id: str) -> str | None:
        """HTTP API users are already identified by their worker ID."""
        return channel_user_id

    async def health_check(self) -> bool:
        """HTTP API adapter is always healthy (in-memory)."""
        return self._initialized

    def get_stats(self) -> dict[str, Any]:
        """Get adapter statistics."""
        return {
            "initialized": self._initialized,
            "send_count": self._send_count,
            "poll_count": self._poll_count,
            "queue_sizes": {
                k: len(v) for k, v in self._message_queue.items()
            },
        }
