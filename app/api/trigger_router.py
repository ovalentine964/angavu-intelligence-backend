"""
Trigger Router — Factor 11: Trigger from Anywhere.

API endpoints for multi-channel agent triggering.
Exposes WhatsApp, USSD, SMS, and Voice triggers via REST.

Each endpoint:
1. Receives channel-specific input
2. Normalizes to TriggerIntent via the trigger
3. Routes to the appropriate agent
4. Returns response in the original channel format
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

try:
    from app.triggers.sms_trigger import SMSTrigger
    from app.triggers.ussd_trigger import USSDTrigger
    from app.triggers.voice_trigger import VoiceTrigger
    from app.triggers.whatsapp_trigger import WhatsAppTrigger
except ImportError:
    SMSTrigger = None
    USSDTrigger = None
    VoiceTrigger = None
    WhatsAppTrigger = None

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/triggers", tags=["Multi-Channel Triggers"])

# Singleton trigger instances
try:
    _whatsapp_trigger = WhatsAppTrigger()
    _ussd_trigger = USSDTrigger()
    _sms_trigger = SMSTrigger()
    _voice_trigger = VoiceTrigger()
except (TypeError, Exception):
    _whatsapp_trigger = None
    _ussd_trigger = None
    _sms_trigger = None
    _voice_trigger = None


# ── Request/Response Models ─────────────────────────────────────────


class WhatsAppTriggerRequest(BaseModel):
    """Incoming WhatsApp message for trigger processing."""
    from_number: str = Field(..., alias="from")
    body: str | None = None
    type: str = "text"
    media_url: str | None = None
    message_id: str | None = None


class USSDTriggerRequest(BaseModel):
    """Incoming USSD request."""
    session_id: str
    phone_number: str
    text: str = ""
    service_code: str = ""


class SMSTriggerRequest(BaseModel):
    """Incoming SMS message."""
    from_number: str = Field(..., alias="from")
    text: str
    id: str | None = None
    gateway: str = "generic"


class VoiceTriggerRequest(BaseModel):
    """Incoming voice/IVR request."""
    call_id: str
    caller: str
    dtmf: str | None = None
    speech: str | None = None
    language: str = "sw"


class TriggerResponseModel(BaseModel):
    """Response from trigger processing."""
    status: str
    intent: str | None = None
    response_text: str | None = None
    channel: str
    session_id: str | None = None
    data: dict[str, Any] = {}


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/whatsapp", response_model=TriggerResponseModel)
async def whatsapp_trigger_endpoint(request: WhatsAppTriggerRequest):
    """
    Process an incoming WhatsApp message through the trigger system.

    Normalizes the message into a TriggerIntent, which can then
    be routed to the appropriate agent.
    """
    try:
        intent = await _whatsapp_trigger.receive({
            "from": request.from_number,
            "body": request.body,
            "type": request.type,
            "media_url": request.media_url,
        })

        logger.info(
            "whatsapp_trigger_processed",
            from_number=request.from_number[:6] + "****",
            intent=intent.intent_type.value,
        )

        return TriggerResponseModel(
            status="ok",
            intent=intent.intent_type.value,
            channel="whatsapp",
            session_id=intent.session_id,
            data=intent.extracted_data,
        )

    except Exception as exc:
        logger.error("whatsapp_trigger_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trigger processing failed: {exc!s}",
        )


@router.post("/ussd", response_model=TriggerResponseModel)
async def ussd_trigger_endpoint(request: USSDTriggerRequest):
    """
    Process a USSD menu selection.

    Manages USSD session state and navigates the menu tree.
    Returns the appropriate response for the current menu level.
    """
    try:
        intent = await _ussd_trigger.receive({
            "session_id": request.session_id,
            "phone_number": request.phone_number,
            "text": request.text,
            "service_code": request.service_code,
        })

        logger.info(
            "ussd_trigger_processed",
            phone=request.phone_number[:6] + "****",
            intent=intent.intent_type.value,
            menu=intent.metadata.get("menu_key"),
        )

        return TriggerResponseModel(
            status="ok",
            intent=intent.intent_type.value,
            channel="ussd",
            session_id=intent.session_id,
            data=intent.extracted_data,
        )

    except Exception as exc:
        logger.error("ussd_trigger_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"USSD processing failed: {exc!s}",
        )


@router.post("/sms", response_model=TriggerResponseModel)
async def sms_trigger_endpoint(request: SMSTriggerRequest):
    """
    Process an incoming SMS message.

    SMS commands are stateless: each message is a complete command.
    Format: COMMAND [args...] (e.g., "SALE nyanya 500")
    """
    try:
        intent = await _sms_trigger.receive({
            "from": request.from_number,
            "text": request.text,
            "id": request.id,
            "gateway": request.gateway,
        })

        logger.info(
            "sms_trigger_processed",
            from_number=request.from_number[:6] + "****",
            intent=intent.intent_type.value,
        )

        return TriggerResponseModel(
            status="ok",
            intent=intent.intent_type.value,
            channel="sms",
            session_id=intent.session_id,
            data=intent.extracted_data,
        )

    except Exception as exc:
        logger.error("sms_trigger_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SMS processing failed: {exc!s}",
        )


@router.post("/voice", response_model=TriggerResponseModel)
async def voice_trigger_endpoint(request: VoiceTriggerRequest):
    """
    Process a voice/IVR input.

    Handles both DTMF (key presses) and speech recognition results.
    Returns the appropriate IVR response for the current state.
    """
    try:
        intent = await _voice_trigger.receive({
            "call_id": request.call_id,
            "caller": request.caller,
            "dtmf": request.dtmf,
            "speech": request.speech,
            "language": request.language,
        })

        logger.info(
            "voice_trigger_processed",
            caller=request.caller[:6] + "****",
            intent=intent.intent_type.value,
            input_type="dtmf" if request.dtmf else "speech",
        )

        return TriggerResponseModel(
            status="ok",
            intent=intent.intent_type.value,
            channel="voice",
            session_id=intent.session_id,
            data=intent.extracted_data,
        )

    except Exception as exc:
        logger.error("voice_trigger_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice processing failed: {exc!s}",
        )


@router.get("/health")
async def trigger_health():
    """Health check for all trigger channels."""
    return {
        "status": "ok",
        "triggers": {
            "whatsapp": _whatsapp_trigger.health_check(),
            "ussd": _ussd_trigger.health_check(),
            "sms": _sms_trigger.health_check(),
            "voice": _voice_trigger.health_check(),
        },
    }
