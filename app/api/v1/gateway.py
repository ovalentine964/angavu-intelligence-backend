"""
Gateway API Routes — FastAPI endpoints for the multi-channel gateway.

Exposes the MultiChannelGateway as REST endpoints that channel
adapters and external services can call.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/gateway", tags=["Multi-Channel Gateway"])

# These are injected at app startup
_gateway = None
_registry = None


def set_gateway(gateway: Any, registry: Any) -> None:
    """Set the gateway and registry instances (called at startup)."""
    global _gateway, _registry
    _gateway = gateway
    _registry = registry


def get_gateway() -> Any:
    """Dependency to get the gateway instance."""
    if _gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway not initialized",
        )
    return _gateway


# =========================================================================
# Schemas
# =========================================================================


class GatewayMessageRequest(BaseModel):
    """Generic message request for any channel."""

    channel: str = Field(
        ...,
        description="Channel type: app_text, app_voice, sms, voice_call",
    )
    worker_id: str = Field(..., description="Worker UUID or phone number")
    content: str = Field(..., description="Message content or ASR transcript")
    language: str | None = Field(default="sw", description="Language code")
    content_type: str | None = Field(
        default="text", description="text, audio, image"
    )
    media_url: str | None = Field(
        default=None, description="URL for audio/image content"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Additional metadata"
    )


class GatewayResponse(BaseModel):
    """Standard gateway response."""

    success: bool
    content: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    elapsed_ms: int | None = None
    error: str | None = None


class GatewayStatsResponse(BaseModel):
    """Gateway statistics."""

    registered_channels: list
    active_sessions: int
    initialized: bool


# =========================================================================
# Routes
# =========================================================================


@router.post("/message", response_model=GatewayResponse)
async def handle_message(
    request: GatewayMessageRequest,
    gateway: Any = Depends(get_gateway),
) -> GatewayResponse:
    """
    Generic endpoint for any channel to send a message.

    Used by:
    - Msaidizi app (app_text, app_voice)
    - SMS webhook (sms)
    - Voice call webhook (voice_call)
    """
    from app.channels.adapters.base import ChannelType, UnifiedMessage

    try:
        channel = ChannelType(request.channel)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown channel: {request.channel}. "
            f"Supported: {[c.value for c in ChannelType]}",
        )

    message = UnifiedMessage.create(
        channel=channel,
        worker_id=request.worker_id,
        content=request.content,
        language=request.language,
        content_type=request.content_type or "text",
        media_url=request.media_url,
        metadata=request.metadata or {},
    )

    result = await gateway.handle_message(message)

    return GatewayResponse(
        success=result.success,
        content=result.content,
        session_id=result.session_id,
        request_id=result.metadata.get("request_id"),
        elapsed_ms=result.metadata.get("elapsed_ms"),
        error=result.error,
    )


@router.post("/whatsapp", response_model=GatewayResponse)
async def handle_whatsapp(
    request: Request,
    gateway: Any = Depends(get_gateway),
) -> GatewayResponse:
    """
    WhatsApp webhook endpoint.

    Receives messages from OpenWA and routes through the gateway.
    Verifies HMAC signature if configured.
    """
    from app.channels.adapters.base import ChannelType, UnifiedMessage

    # Get raw body for signature verification
    body = await request.json()

    # Parse through WhatsApp adapter
    adapter = _registry.get_adapter(ChannelType.WHATSAPP) if _registry else None
    if adapter:
        message = await adapter.parse_raw_message(body)
    else:
        # Fallback: manual parsing
        phone = body.get("from", "").replace("@c.us", "")
        message = UnifiedMessage.create(
            channel=ChannelType.WHATSAPP,
            worker_id=phone,
            content=body.get("body", ""),
        )

    result = await gateway.handle_message(message)

    return GatewayResponse(
        success=result.success,
        content=result.content,
        session_id=result.session_id,
        request_id=result.metadata.get("request_id"),
        elapsed_ms=result.metadata.get("elapsed_ms"),
        error=result.error,
    )


@router.post("/sms", response_model=GatewayResponse)
async def handle_sms(
    request: Request,
    gateway: Any = Depends(get_gateway),
) -> GatewayResponse:
    """
    SMS webhook endpoint (Africa's Talking format).

    Receives inbound SMS and routes through the gateway.
    """
    from app.channels.adapters.base import ChannelType, UnifiedMessage

    body = await request.json()

    adapter = _registry.get_adapter(ChannelType.SMS) if _registry else None
    if adapter:
        message = await adapter.parse_raw_message(body)
    else:
        phone = body.get("from", "").lstrip("+")
        message = UnifiedMessage.create(
            channel=ChannelType.SMS,
            worker_id=phone,
            content=body.get("text", ""),
        )

    result = await gateway.handle_message(message)

    return GatewayResponse(
        success=result.success,
        content=result.content,
        session_id=result.session_id,
        request_id=result.metadata.get("request_id"),
        elapsed_ms=result.metadata.get("elapsed_ms"),
        error=result.error,
    )


@router.post("/voice", response_model=GatewayResponse)
async def handle_voice(
    request: Request,
    gateway: Any = Depends(get_gateway),
) -> GatewayResponse:
    """
    Voice call webhook endpoint (Twilio format).

    Receives ASR transcripts from voice calls and routes through the gateway.
    """
    from app.channels.adapters.base import ChannelType, UnifiedMessage

    body = await request.json()

    adapter = (
        _registry.get_adapter(ChannelType.VOICE_CALL) if _registry else None
    )
    if adapter:
        message = await adapter.parse_raw_message(body)
    else:
        phone = body.get("From", "").lstrip("+")
        content = body.get("SpeechResult", "") or body.get("Digits", "")
        message = UnifiedMessage.create(
            channel=ChannelType.VOICE_CALL,
            worker_id=phone,
            content=content,
        )

    result = await gateway.handle_message(message)

    return GatewayResponse(
        success=result.success,
        content=result.content,
        session_id=result.session_id,
        request_id=result.metadata.get("request_id"),
        elapsed_ms=result.metadata.get("elapsed_ms"),
        error=result.error,
    )


@router.get("/stats", response_model=GatewayStatsResponse)
async def get_stats(
    gateway: Any = Depends(get_gateway),
) -> GatewayStatsResponse:
    """Get gateway statistics."""
    stats = gateway.get_stats()
    return GatewayStatsResponse(**stats)


@router.post("/proactive")
async def send_proactive(
    worker_id: str,
    content: str,
    channel: str | None = None,
    gateway: Any = Depends(get_gateway),
) -> dict[str, bool]:
    """
    Send a proactive message to a worker on their preferred channel.
    Used for alerts, reminders, and notifications.
    """
    from app.channels.adapters.base import ChannelType

    preferred = None
    if channel:
        try:
            preferred = ChannelType(channel)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown channel: {channel}",
            )

    sent = await gateway.send_proactive(
        worker_id=worker_id,
        content=content,
        preferred_channel=preferred,
    )
    return {"sent": sent}
