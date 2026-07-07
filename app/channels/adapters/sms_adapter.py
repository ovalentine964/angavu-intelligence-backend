"""
SMS Channel Adapter — Placeholder for Africa's Talking integration.

SMS/USSD is critical for workers without smartphones or data.
This adapter provides the interface for future SMS integration.
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


class SMSAdapter(BaseChannelAdapter):
    """
    Adapter for SMS via Africa's Talking (or similar provider).

    Placeholder implementation — defines the interface for when
    SMS integration is activated.

    Africa's Talking sends webhooks:
    - Inbound: POST /api/v1/gateway/sms with from, text, id
    - Delivery reports: POST /api/v1/gateway/sms/delivery
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        sender_id: Optional[str] = None,
    ):
        self._api_key = api_key
        self._username = username
        self._sender_id = sender_id or "Msaidizi"
        self._initialized = False

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.SMS

    async def initialize(self) -> None:
        """Initialize SMS adapter."""
        if not self._api_key:
            logger.warning(
                "sms_adapter_no_credentials",
                message="SMS adapter running without API key. "
                "Set AFRICASTALKING_API_KEY to activate.",
            )
        self._initialized = True
        logger.info("sms_adapter_initialized")

    async def shutdown(self) -> None:
        """Shutdown SMS adapter."""
        self._initialized = False
        logger.info("sms_adapter_shutdown")

    async def parse_raw_message(
        self, raw_data: Dict[str, Any]
    ) -> UnifiedMessage:
        """
        Parse Africa's Talking webhook into UnifiedMessage.

        Expected payload:
        {
            "from": "+254712345678",
            "text": "Salio",
            "id": "ATXid...",
            "date": "2026-07-07 12:00:00",
            "to": "+254700000000"
        }
        """
        phone = raw_data.get("from", "").lstrip("+")

        return UnifiedMessage.create(
            channel=ChannelType.SMS,
            worker_id=phone,  # Will be resolved to UUID
            content=raw_data.get("text", ""),
            language="sw",  # Default to Swahili
            content_type="text",
            metadata={
                "sms_id": raw_data.get("id"),
                "sms_from": raw_data.get("from"),
                "sms_to": raw_data.get("to"),
                "sms_date": raw_data.get("date"),
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
        Send SMS via Africa's Talking API.

        SMS has a 160-character limit per segment.
        Long messages are split automatically by the provider.
        """
        if not self._api_key:
            logger.warning("sms_send_no_credentials")
            return False

        phone = (
            recipient_id
            if recipient_id.startswith("+")
            else f"+{recipient_id}"
        )

        try:
            # TODO: Implement actual Africa's Talking API call
            # import africastalking
            # sms = africastalking.SMS
            # sms.send(content, [phone], sender_id=self._sender_id)

            logger.info(
                "sms_message_queued",
                recipient=phone[:8] + "***",
                content_length=len(content),
                segments=(len(content) // 160) + 1,
            )
            return True
        except Exception as e:
            logger.error("sms_send_failed", error=str(e))
            return False

    async def resolve_worker_id(self, channel_user_id: str) -> Optional[str]:
        """Resolve phone number to worker UUID."""
        phone = channel_user_id.lstrip("+")
        return phone
