"""
WhatsApp Channel Adapter — Wraps existing OpenWA integration.

The existing whatsapp_bot.py and whatsapp_connection.py handle
low-level WhatsApp communication. This adapter wraps them into
the unified channel pattern, routing messages through the gateway
instead of handling them directly.
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


class WhatsAppAdapter(BaseChannelAdapter):
    """
    Adapter for WhatsApp via OpenWA.

    Wraps the existing WhatsAppBot to normalize messages into
    the multi-channel gateway pattern. The existing webhook
    endpoints (/api/v1/webhooks/whatsapp) continue to work —
    this adapter sits on top, not replacing them.

    Worker identity resolution: phone number → canonical worker UUID
    via the worker_channel_map in SessionSync.
    """

    def __init__(self, bot: Any = None):
        self._bot = bot
        self._initialized = False

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.WHATSAPP

    async def initialize(self) -> None:
        """Initialize WhatsApp adapter."""
        if self._bot is None:
            logger.warning(
                "whatsapp_adapter_no_bot",
                message="No WhatsAppBot instance provided. "
                "Pass bot to constructor.",
            )
        self._initialized = True
        logger.info("whatsapp_adapter_initialized")

    async def shutdown(self) -> None:
        """Shutdown WhatsApp adapter."""
        self._initialized = False
        logger.info("whatsapp_adapter_shutdown")

    async def parse_raw_message(
        self, raw_data: Dict[str, Any]
    ) -> UnifiedMessage:
        """
        Parse OpenWA webhook payload into UnifiedMessage.

        Expected payload (from OpenWA webhook):
        {
            "from": "254712345678@c.us",
            "body": "message text",
            "timestamp": 1234567890,
            "id": "message-id",
            "type": "chat" | "image" | "audio",
            ...
        }
        """
        from_number = raw_data.get("from", "")
        # Strip @c.us suffix for phone number
        phone = from_number.replace("@c.us", "").replace("@g.us", "")

        content_type = "text"
        content = raw_data.get("body", "")
        media_url = None

        msg_type = raw_data.get("type", "chat")
        if msg_type == "image":
            content_type = "image"
            media_url = raw_data.get("mediaUrl") or raw_data.get("body", "")
            content = raw_data.get("caption", "")
        elif msg_type == "audio":
            content_type = "audio"
            media_url = raw_data.get("mediaUrl")
            content = raw_data.get("body", "")  # May contain ASR transcript

        return UnifiedMessage.create(
            channel=ChannelType.WHATSAPP,
            worker_id=phone,  # Will be resolved to UUID by gateway
            content=content,
            language=self._detect_language(content),
            content_type=content_type,
            media_url=media_url,
            metadata={
                "wa_message_id": raw_data.get("id"),
                "wa_from": from_number,
                "wa_type": msg_type,
                "is_group": "@g.us" in from_number,
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
        Send message back through WhatsApp.

        Uses the existing WhatsAppBot to send via OpenWA.
        """
        if self._bot is None:
            logger.error("whatsapp_send_no_bot")
            return False

        try:
            # Format for WhatsApp: ensure recipient has @c.us suffix
            wa_recipient = (
                recipient_id
                if "@" in recipient_id
                else f"{recipient_id}@c.us"
            )

            await self._bot.send_message(
                to=wa_recipient,
                message=content,
            )
            logger.info(
                "whatsapp_message_sent",
                recipient=wa_recipient[:8] + "***",
                content_length=len(content),
            )
            return True
        except Exception as e:
            logger.error(
                "whatsapp_send_failed",
                recipient=recipient_id[:8] + "***",
                error=str(e),
            )
            return False

    async def resolve_worker_id(self, channel_user_id: str) -> Optional[str]:
        """
        Resolve WhatsApp phone number to canonical worker UUID.

        Looks up the phone in the worker_channel_map.
        Falls back to returning the phone number if no mapping exists.
        """
        # The registry handles the actual lookup via SessionSync
        # This method just strips the @c.us suffix
        phone = channel_user_id.replace("@c.us", "").replace("@g.us", "")
        return phone  # Registry will resolve to UUID if mapping exists

    def _detect_language(self, text: str) -> str:
        """
        Simple language detection for WhatsApp messages.
        Defaults to Swahili ('sw') — the primary language for Msaidizi.
        """
        if not text:
            return "sw"

        # Simple heuristic — could be enhanced with a proper detector
        english_indicators = [
            "the", "and", "is", "how", "what", "can", "please",
            "help", "report", "stock",
        ]
        text_lower = text.lower()
        english_count = sum(
            1 for w in english_indicators if w in text_lower
        )

        if english_count >= 2:
            return "en"
        return "sw"
