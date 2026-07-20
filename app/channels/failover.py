"""
Failover Manager — Multi-channel delivery with automatic fallback.

Wraps the delivery logic to automatically try backup channels when
the primary channel (WhatsApp) fails. Ensures messages always get
delivered, even when WhatsApp/OpenWA is down.

Delivery priority:
1. WhatsApp (primary) — workers' preferred channel
2. Telegram (backup) — stable API, common in East Africa
3. SMS (fallback) — works on any phone, no data needed
4. HTTP API (last resort) — always available, pull-based

Usage:
    failover = FailoverManager(registry, health_monitor)
    success = await failover.send(
        recipient_id="254712345678",
        content="Your daily report...",
        preferred_channel="whatsapp",
    )
"""

from __future__ import annotations

from typing import Any

import structlog

from app.channels.adapters.base import BaseChannelAdapter, ChannelType
from app.channels.health_monitor import ChannelHealthMonitor

logger = structlog.get_logger(__name__)

# Channel names (matching ChannelType values)
CHANNEL_WHATSAPP = ChannelType.WHATSAPP.value
CHANNEL_TELEGRAM = ChannelType.TELEGRAM.value
CHANNEL_SMS = ChannelType.SMS.value
CHANNEL_HTTP_API = ChannelType.HTTP_API.value

# Default channel priority
DEFAULT_PRIORITY = [CHANNEL_WHATSAPP, CHANNEL_TELEGRAM, CHANNEL_SMS, CHANNEL_HTTP_API]


class FailoverManager:
    """
    Manages multi-channel message delivery with automatic failover.

    When sending a message, tries channels in priority order.
    If the preferred channel is unhealthy, automatically falls
    through to the next available channel.

    Tracks failover events for monitoring and alerting.
    """

    def __init__(
        self,
        registry: Any = None,
        health_monitor: ChannelHealthMonitor | None = None,
    ):
        self._registry = registry
        self._health_monitor = health_monitor
        self._failover_count: int = 0
        self._total_sent: int = 0
        self._total_failed: int = 0
        self._channel_send_counts: dict[str, int] = {}
        self._channel_fail_counts: dict[str, int] = {}
        # Track which recipient_id maps to which Telegram chat_id
        self._telegram_id_map: dict[str, str] = {}

    def set_telegram_id(self, worker_id: str, telegram_chat_id: str) -> None:
        """
        Map a worker_id to their Telegram chat_id.

        Called during onboarding or when a worker connects Telegram.
        """
        self._telegram_id_map[worker_id] = telegram_chat_id
        logger.info(
            "telegram_id_mapped",
            worker_id=worker_id[:8] + "***",
        )

    def get_telegram_id(self, worker_id: str) -> str | None:
        """Get the Telegram chat_id for a worker."""
        return self._telegram_id_map.get(worker_id)

    async def send(
        self,
        recipient_id: str,
        content: str,
        content_type: str = "text",
        preferred_channel: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send a message with automatic failover.

        Tries channels in priority order until one succeeds.

        Args:
            recipient_id: Worker ID or phone number
            content: Message content
            content_type: Type of content (text, image, document)
            preferred_channel: Override the default priority for first attempt
            **kwargs: Additional params (image_data, caption, etc.)

        Returns:
            Dict with:
            - success: bool
            - channel_used: str (which channel delivered)
            - attempted: list[str] (channels tried)
            - failover_triggered: bool
        """
        result = {
            "success": False,
            "channel_used": None,
            "attempted": [],
            "failover_triggered": False,
            "error": None,
        }

        # Determine channel order
        channels = self._get_channel_order(preferred_channel)

        for channel_name in channels:
            # Check if channel is healthy
            if self._health_monitor and not self._health_monitor.is_channel_healthy(channel_name):
                # Skip unhealthy channels (except http_api which is always available)
                if channel_name != CHANNEL_HTTP_API:
                    result["attempted"].append(
                        f"{channel_name}:skipped_unhealthy"
                    )
                    continue

            # Get the adapter for this channel
            adapter = self._get_adapter(channel_name)
            if adapter is None:
                result["attempted"].append(f"{channel_name}:no_adapter")
                continue

            # Resolve recipient ID for this channel
            channel_recipient = self._resolve_recipient(
                recipient_id, channel_name
            )

            # Try sending
            try:
                if content_type == "image" and kwargs.get("image_data"):
                    success = await adapter.send_image(
                        channel_recipient,
                        kwargs["image_data"],
                        kwargs.get("caption", ""),
                    )
                else:
                    success = await adapter.send_message(
                        channel_recipient,
                        content,
                        content_type,
                        **kwargs,
                    )

                result["attempted"].append(
                    f"{channel_name}:{'success' if success else 'failed'}"
                )

                if success:
                    result["success"] = True
                    result["channel_used"] = channel_name
                    self._total_sent += 1
                    self._channel_send_counts[channel_name] = (
                        self._channel_send_counts.get(channel_name, 0) + 1
                    )

                    if len(result["attempted"]) > 1:
                        result["failover_triggered"] = True
                        self._failover_count += 1
                        logger.info(
                            "failover_delivery_success",
                            recipient=recipient_id[:8] + "***",
                            channel_used=channel_name,
                            channels_tried=result["attempted"],
                        )

                    return result
                else:
                    self._channel_fail_counts[channel_name] = (
                        self._channel_fail_counts.get(channel_name, 0) + 1
                    )

            except Exception as e:
                result["attempted"].append(f"{channel_name}:error:{e!s}")
                self._channel_fail_counts[channel_name] = (
                    self._channel_fail_counts.get(channel_name, 0) + 1
                )
                logger.error(
                    "channel_send_error",
                    channel=channel_name,
                    error=str(e),
                )

        # All channels failed
        self._total_failed += 1
        result["error"] = "All channels failed"
        logger.error(
            "all_channels_failed",
            recipient=recipient_id[:8] + "***",
            attempted=result["attempted"],
        )
        return result

    async def send_image(
        self,
        recipient_id: str,
        image_data: bytes,
        caption: str = "",
        preferred_channel: str | None = None,
    ) -> dict[str, Any]:
        """
        Send an image with automatic failover.

        Args:
            recipient_id: Worker ID or phone number
            image_data: Image bytes
            caption: Image caption
            preferred_channel: Override default channel priority

        Returns:
            Dict with delivery result
        """
        return await self.send(
            recipient_id=recipient_id,
            content=caption,
            content_type="image",
            preferred_channel=preferred_channel,
            image_data=image_data,
            caption=caption,
        )

    def _get_channel_order(
        self, preferred_channel: str | None = None
    ) -> list[str]:
        """
        Get the ordered list of channels to try.

        If preferred_channel is specified, it goes first.
        """
        if preferred_channel and preferred_channel in DEFAULT_PRIORITY:
            channels = [preferred_channel]
            channels.extend(
                ch for ch in DEFAULT_PRIORITY if ch != preferred_channel
            )
            return channels
        return list(DEFAULT_PRIORITY)

    def _get_adapter(self, channel_name: str) -> BaseChannelAdapter | None:
        """Get the adapter for a channel name."""
        if not self._registry:
            return None

        channel_type_map = {
            CHANNEL_WHATSAPP: ChannelType.WHATSAPP,
            CHANNEL_TELEGRAM: ChannelType.TELEGRAM,
            CHANNEL_SMS: ChannelType.SMS,
            CHANNEL_HTTP_API: ChannelType.HTTP_API,
        }

        channel_type = channel_type_map.get(channel_name)
        if channel_type:
            return self._registry.get_adapter(channel_type)

        return None

    def _resolve_recipient(
        self, recipient_id: str, channel_name: str
    ) -> str:
        """
        Resolve recipient_id to a channel-specific identifier.

        For WhatsApp: phone number (as-is)
        For Telegram: mapped chat_id or fallback
        For SMS: phone number (as-is)
        For HTTP API: worker_id (as-is)
        """
        if channel_name == CHANNEL_TELEGRAM:
            # Look up Telegram chat_id mapping
            telegram_id = self._telegram_id_map.get(recipient_id)
            if telegram_id:
                return telegram_id
            # Fallback: try using recipient_id as-is
            return recipient_id

        # For other channels, use recipient_id as-is
        return recipient_id

    def get_stats(self) -> dict[str, Any]:
        """Get failover manager statistics."""
        return {
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "failover_count": self._failover_count,
            "channel_send_counts": dict(self._channel_send_counts),
            "channel_fail_counts": dict(self._channel_fail_counts),
            "telegram_id_mappings": len(self._telegram_id_map),
        }
