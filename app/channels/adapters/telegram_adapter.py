"""
Telegram Channel Adapter — Fallback communication channel.

Telegram Bot API as a reliable fallback when WhatsApp/OpenWA is down.
Uses the standard Telegram Bot API (python-telegram-bot or httpx).

Why Telegram as fallback:
- Stable, official API (no reverse-engineering like OpenWA)
- Free, no rate-limit bans for reasonable usage
- Supports text, images, voice, documents
- Workers in East Africa commonly have Telegram
- Works without phone SIM (Wi-Fi only)

Configuration:
    TELEGRAM_BOT_TOKEN: Bot token from @BotFather
    TELEGRAM_API_URL: Override for self-hosted Telegram Bot API (optional)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.channels.adapters.base import (
    BaseChannelAdapter,
    ChannelType,
    UnifiedMessage,
)

logger = structlog.get_logger(__name__)

# Telegram Bot API base URL
TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramAdapter(BaseChannelAdapter):
    """
    Adapter for Telegram Bot API.

    Provides bidirectional messaging:
    - Inbound: Receives updates via webhook or polling
    - Outbound: Sends messages via Bot API

    Used as a fallback channel when WhatsApp/OpenWA is unavailable.
    """

    def __init__(
        self,
        bot_token: str | None = None,
        api_base: str | None = None,
    ):
        self._bot_token = bot_token
        self._api_base = (api_base or TELEGRAM_API_BASE).rstrip("/")
        self._initialized = False
        self._bot_info: dict | None = None
        self._last_error: str | None = None
        self._send_count: int = 0
        self._fail_count: int = 0

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.TELEGRAM

    @property
    def bot_username(self) -> str | None:
        """Bot username (set after initialize)."""
        if self._bot_info:
            return self._bot_info.get("username")
        return None

    async def initialize(self) -> None:
        """Initialize Telegram adapter and verify bot token."""
        if not self._bot_token:
            logger.warning(
                "telegram_adapter_no_token",
                message="No Telegram bot token provided. "
                "Set TELEGRAM_BOT_TOKEN to activate.",
            )
            self._initialized = True
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._api_base}/bot{self._bot_token}/getMe"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        self._bot_info = data.get("result", {})
                        logger.info(
                            "telegram_adapter_initialized",
                            bot_username=self._bot_info.get("username"),
                        )
                    else:
                        logger.error(
                            "telegram_adapter_init_failed",
                            error=data.get("description", "Unknown error"),
                        )
                else:
                    logger.error(
                        "telegram_adapter_init_http_error",
                        status=resp.status_code,
                    )
        except Exception as e:
            logger.error(
                "telegram_adapter_init_error",
                error=str(e),
            )

        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown Telegram adapter."""
        self._initialized = False
        logger.info("telegram_adapter_shutdown")

    async def parse_raw_message(
        self, raw_data: dict[str, Any]
    ) -> UnifiedMessage:
        """
        Parse Telegram update into UnifiedMessage.

        Expected payload (Telegram Bot API update):
        {
            "update_id": 123,
            "message": {
                "message_id": 456,
                "from": {"id": 789, "first_name": "Juma"},
                "chat": {"id": 789, "type": "private"},
                "text": "Ripoti ya leo",
                "date": 1234567890
            }
        }
        """
        message = raw_data.get("message", {})
        from_user = message.get("from", {})
        chat = message.get("chat", {})

        # Use chat_id as the worker identifier (will be resolved later)
        chat_id = str(chat.get("id", from_user.get("id", "")))

        content = message.get("text", "")
        content_type = "text"
        media_url = None

        # Handle different message types
        if message.get("photo"):
            content_type = "image"
            # Get the largest photo
            photo = message["photo"][-1]
            media_url = photo.get("file_id")
            content = message.get("caption", "")
        elif message.get("voice") or message.get("audio"):
            content_type = "audio"
            audio = message.get("voice") or message.get("audio", {})
            media_url = audio.get("file_id")
            content = message.get("caption", "")
        elif message.get("document"):
            content_type = "document"
            doc = message["document"]
            media_url = doc.get("file_id")
            content = message.get("caption", "")

        return UnifiedMessage.create(
            channel=ChannelType.TELEGRAM,
            worker_id=chat_id,
            content=content,
            language=self._detect_language(content),
            content_type=content_type,
            media_url=media_url,
            metadata={
                "telegram_update_id": raw_data.get("update_id"),
                "telegram_message_id": message.get("message_id"),
                "telegram_chat_id": chat_id,
                "telegram_from_id": from_user.get("id"),
                "telegram_from_name": from_user.get("first_name", ""),
                "telegram_chat_type": chat.get("type", "private"),
                "actual_channel": "telegram",
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
        Send message via Telegram Bot API.

        Args:
            recipient_id: Telegram chat_id
            content: Message text
            content_type: "text", "image", "document"
            **kwargs: Additional params (image_url, parse_mode, etc.)

        Returns:
            True if sent successfully
        """
        if not self._bot_token:
            logger.warning("telegram_send_no_token")
            return False

        try:
            parse_mode = kwargs.get("parse_mode", "Markdown")

            # Truncate if too long (Telegram limit: 4096 chars)
            if len(content) > 4000:
                content = content[:3950] + "\n\n... (ripoti imefupishwa)"

            async with httpx.AsyncClient(timeout=30) as client:
                if content_type == "image" and kwargs.get("image_url"):
                    # Send photo
                    resp = await client.post(
                        f"{self._api_base}/bot{self._bot_token}/sendPhoto",
                        json={
                            "chat_id": recipient_id,
                            "photo": kwargs["image_url"],
                            "caption": content[:1024],  # Telegram caption limit
                            "parse_mode": parse_mode,
                        },
                    )
                elif content_type == "document" and kwargs.get("document_url"):
                    # Send document
                    resp = await client.post(
                        f"{self._api_base}/bot{self._bot_token}/sendDocument",
                        json={
                            "chat_id": recipient_id,
                            "document": kwargs["document_url"],
                            "caption": content[:1024],
                            "parse_mode": parse_mode,
                        },
                    )
                else:
                    # Send text message
                    resp = await client.post(
                        f"{self._api_base}/bot{self._bot_token}/sendMessage",
                        json={
                            "chat_id": recipient_id,
                            "text": content,
                            "parse_mode": parse_mode,
                        },
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        self._send_count += 1
                        self._last_error = None
                        logger.info(
                            "telegram_message_sent",
                            chat_id=recipient_id[:6] + "***",
                            content_length=len(content),
                        )
                        return True
                    else:
                        self._fail_count += 1
                        self._last_error = data.get("description", "Unknown error")
                        logger.error(
                            "telegram_send_api_error",
                            error=self._last_error,
                        )
                        return False
                else:
                    self._fail_count += 1
                    self._last_error = f"HTTP {resp.status_code}"
                    logger.error(
                        "telegram_send_http_error",
                        status=resp.status_code,
                    )
                    return False

        except Exception as e:
            self._fail_count += 1
            self._last_error = str(e)
            logger.error("telegram_send_error", error=str(e))
            return False

    async def send_image(
        self,
        recipient_id: str,
        image_data: bytes,
        caption: str = "",
    ) -> bool:
        """
        Send image as bytes via Telegram.

        Args:
            recipient_id: Telegram chat_id
            image_data: Image bytes (PNG/JPEG)
            caption: Optional caption

        Returns:
            True if sent successfully
        """
        if not self._bot_token:
            return False

        try:
            import base64
            image_b64 = base64.b64encode(image_data).decode("utf-8")

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._api_base}/bot{self._bot_token}/sendPhoto",
                    json={
                        "chat_id": recipient_id,
                        "photo": f"data:image/png;base64,{image_b64}",
                        "caption": caption[:1024],
                    },
                )

                if resp.status_code == 200 and resp.json().get("ok"):
                    self._send_count += 1
                    return True
                else:
                    self._fail_count += 1
                    return False

        except Exception as e:
            self._fail_count += 1
            logger.error("telegram_image_send_error", error=str(e))
            return False

    async def resolve_worker_id(self, channel_user_id: str) -> str | None:
        """
        Resolve Telegram chat_id to canonical worker ID.
        The registry handles the actual mapping.
        """
        return channel_user_id

    async def health_check(self) -> bool:
        """Check if Telegram Bot API is reachable and token is valid."""
        if not self._bot_token:
            return False

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self._api_base}/bot{self._bot_token}/getMe"
                )
                return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception:
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get adapter statistics."""
        return {
            "initialized": self._initialized,
            "has_token": bool(self._bot_token),
            "bot_username": self.bot_username,
            "send_count": self._send_count,
            "fail_count": self._fail_count,
            "last_error": self._last_error,
        }

    def _detect_language(self, text: str) -> str:
        """Simple language detection. Default to Swahili."""
        if not text:
            return "sw"

        english_indicators = [
            "the", "and", "is", "how", "what", "can", "please",
            "help", "report", "stock", "daily", "weekly",
        ]
        text_lower = text.lower()
        english_count = sum(
            1 for w in english_indicators if w in text_lower
        )

        if english_count >= 2:
            return "en"
        return "sw"
