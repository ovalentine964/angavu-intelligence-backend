"""
Voice Call Channel Adapter — Placeholder for Twilio/SIP integration.

Voice is critical for workers who are illiterate or prefer speaking.
Supports both IVR (press 1 for...) and natural conversation via ASR.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.channels.adapters.base import (
    BaseChannelAdapter,
    ChannelType,
    UnifiedMessage,
)

logger = structlog.get_logger(__name__)


class VoiceAdapter(BaseChannelAdapter):
    """
    Adapter for voice calls via Twilio Voice or SIP.

    Placeholder implementation — defines the interface for when
    voice integration is activated.

    Flow:
    1. Worker calls Msaidizi number
    2. Twilio sends webhook → this adapter
    3. Twilio streams audio to ASR service
    4. ASR transcript → UnifiedMessage
    5. Response → TTS → audio back to caller
    """

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        phone_number: str | None = None,
    ):
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._phone_number = phone_number
        self._initialized = False

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.VOICE_CALL

    async def initialize(self) -> None:
        """Initialize voice adapter."""
        if not self._account_sid:
            logger.warning(
                "voice_adapter_no_credentials",
                message="Voice adapter running without Twilio credentials. "
                "Set TWILIO_ACCOUNT_SID to activate.",
            )
        self._initialized = True
        logger.info("voice_adapter_initialized")

    async def shutdown(self) -> None:
        """Shutdown voice adapter."""
        self._initialized = False
        logger.info("voice_adapter_shutdown")

    async def parse_raw_message(
        self, raw_data: dict[str, Any]
    ) -> UnifiedMessage:
        """
        Parse Twilio webhook into UnifiedMessage.

        Expected payload (from Twilio speech recognition):
        {
            "CallSid": "CA...",
            "From": "+254712345678",
            "To": "+254700000000",
            "SpeechResult": "Nataka kuona ripoti ya leo",
            "Confidence": "0.95",
            "RecordingUrl": "https://...",
            "CallStatus": "in-progress"
        }
        """
        phone = raw_data.get("From", "").lstrip("+")

        # Use ASR transcript as content
        content = raw_data.get("SpeechResult", "")
        if not content:
            content = raw_data.get("Digits", "")  # DTMF fallback

        return UnifiedMessage.create(
            channel=ChannelType.VOICE_CALL,
            worker_id=phone,
            content=content,
            language="sw",
            content_type="audio",
            media_url=raw_data.get("RecordingUrl"),
            metadata={
                "call_sid": raw_data.get("CallSid"),
                "call_from": raw_data.get("From"),
                "call_to": raw_data.get("To"),
                "asr_confidence": raw_data.get("Confidence"),
                "call_status": raw_data.get("CallStatus"),
                "is_dtmf": "Digits" in raw_data
                and "SpeechResult" not in raw_data,
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
        Send voice response back to caller.

        For active calls: uses Twilio <Say> or <Play> TwiML.
        For missed calls: initiates callback with TTS message.
        """
        if not self._account_sid:
            logger.warning("voice_send_no_credentials")
            return False

        phone = (
            recipient_id
            if recipient_id.startswith("+")
            else f"+{recipient_id}"
        )

        call_sid = kwargs.get("call_sid")

        try:
            if call_sid:
                # Active call — update TwiML
                # TODO: Implement Twilio call update
                # twilio_client.calls(call_sid).update(twimml=twiml)
                logger.info(
                    "voice_twiml_sent",
                    call_sid=call_sid,
                    content_length=len(content),
                )
            else:
                # No active call — initiate callback
                # TODO: Implement Twilio outbound call
                # twilio_client.calls.create(
                #     to=phone, from_=self._phone_number, twiml=twiml
                # )
                logger.info(
                    "voice_callback_queued",
                    recipient=phone[:8] + "***",
                )
            return True
        except Exception as e:
            logger.error("voice_send_failed", error=str(e))
            return False

    async def resolve_worker_id(self, channel_user_id: str) -> str | None:
        """Resolve phone number to worker UUID."""
        phone = channel_user_id.lstrip("+")
        return phone

    async def health_check(self) -> bool:
        """Check Twilio connectivity."""
        if not self._account_sid:
            return False
        # TODO: Ping Twilio API
        return True
