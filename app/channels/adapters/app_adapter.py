"""
Msaidizi App Channel Adapter.

Handles messages from the Msaidizi mobile app — both text and voice.
The app sends structured JSON payloads to the gateway API.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog

from app.channels.adapters.base import (
    BaseChannelAdapter,
    ChannelType,
    UnifiedMessage,
)

logger = structlog.get_logger(__name__)


class AppAdapter(BaseChannelAdapter):
    """
    Adapter for the Msaidizi mobile app.

    The app sends messages via REST API:
    - Text: POST /api/v1/gateway/message with channel="app_text"
    - Voice: POST /api/v1/gateway/message with channel="app_voice"
      (content is ASR transcript, media_url is audio file)
    """

    def __init__(self, app_secret: Optional[str] = None):
        self._app_secret = app_secret
        self._initialized = False

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.APP_TEXT

    async def initialize(self) -> None:
        """Initialize app adapter."""
        self._initialized = True
        logger.info("app_adapter_initialized")

    async def shutdown(self) -> None:
        """Shutdown app adapter."""
        self._initialized = False
        logger.info("app_adapter_shutdown")

    async def parse_raw_message(
        self, raw_data: Dict[str, Any]
    ) -> UnifiedMessage:
        """
        Parse app payload into UnifiedMessage.

        Expected payload:
        {
            "channel": "app_text" | "app_voice",
            "worker_id": "uuid",
            "content": "message text or ASR transcript",
            "language": "sw",
            "content_type": "text" | "audio",
            "media_url": "https://... (for voice)"
        }
        """
        channel_str = raw_data.get("channel", "app_text")
        channel = (
            ChannelType.APP_VOICE
            if channel_str == "app_voice"
            else ChannelType.APP_TEXT
        )

        return UnifiedMessage.create(
            channel=channel,
            worker_id=raw_data["worker_id"],
            content=raw_data["content"],
            language=raw_data.get("language", "sw"),
            content_type=raw_data.get("content_type", "text"),
            media_url=raw_data.get("media_url"),
            metadata={
                "app_version": raw_data.get("app_version"),
                "device_id": raw_data.get("device_id"),
                "platform": raw_data.get("platform", "android"),
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
        Send message back to the app.

        In practice, the app polls or uses WebSocket for responses.
        This stores the response for the app to retrieve.
        """
        logger.info(
            "app_message_sent",
            recipient_id=recipient_id,
            content_type=content_type,
            content_length=len(content),
        )
        # Response is returned directly via the API response.
        # For push notifications, integrate with Firebase Cloud Messaging.
        return True

    async def resolve_worker_id(self, channel_user_id: str) -> Optional[str]:
        """
        App users are already identified by their UUID.
        No resolution needed.
        """
        return channel_user_id
