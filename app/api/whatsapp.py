"""
WhatsApp webhook endpoint — Pure Report Delivery Channel.

Handles incoming messages from OpenWA (self-hosted WhatsApp Web API).
Routes report requests to the WhatsAppBot service.

WhatsApp is ONLY for:
- Sending scheduled reports (daily, weekly, monthly, 6-month, yearly)
- Sending alerts (restock, price, credit, unusual activity)
- Receiving report requests ("Ripoti ya leo")

WhatsApp is NOT for:
- Transaction recording (Msaidizi app, offline)
- Interactive business advice (Msaidizi app → Angavu Intelligence cloud)
"""

import hashlib
import hmac

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_db
from app.services.whatsapp_bot import WhatsAppBot

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["WhatsApp Webhook"])


class WhatsAppMessage(BaseModel):
    """Incoming WhatsApp message from OpenWA."""

    from_number: str = Field(..., alias="from")
    message_id: str | None = None
    timestamp: str | None = None
    type: str = Field("text", description="text, voice, image, document")
    body: str | None = None
    media_url: str | None = None
    caption: str | None = None
    is_group: bool = False
    group_id: str | None = None
    push_name: str | None = None


class WebhookPayload(BaseModel):
    """OpenWA webhook payload wrapper."""

    event: str = Field(..., description="Event type: message, ack, etc.")
    data: WhatsAppMessage


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive incoming WhatsApp messages from OpenWA.

    This endpoint is called by the OpenWA service whenever a new
    message arrives. It routes the message to the WhatsAppBot service
    for processing and returns the response.

    **Supported message types:**
    - text: Report requests ("Ripoti ya leo", "Ripoti ya wiki")
    - help: Show available commands
    - Other messages: Redirected to Msaidizi App

    **NOT handled here:**
    - Transaction recording (Msaidizi app)
    - Voice commands for transactions (Msaidizi app)
    - Interactive business advice (Msaidizi app → cloud)

    **Security:**
    Validates HMAC signature from OpenWA to ensure authenticity.

    Args:
        request: Raw HTTP request (for signature validation)
        db: Database session

    Returns:
        Response with status
    """
    # Get raw body for signature validation
    body = await request.body()

    # Validate HMAC signature (fail-closed: always require valid signature)
    signature = request.headers.get("X-OpenWA-Signature")
    if not signature:
        logger.warning("whatsapp_webhook_missing_signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature",
        )
    expected = hmac.new(
        settings.OPENWA_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        logger.warning("whatsapp_webhook_invalid_signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # Parse payload
    try:
        payload = WebhookPayload.model_validate_json(body)
    except Exception as e:
        logger.error("whatsapp_webhook_parse_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {e!s}",
        )

    # Only process text and voice messages
    if payload.event != "message":
        return {"status": "ignored", "reason": f"event type: {payload.event}"}

    msg = payload.data

    # Skip group messages (for now)
    if msg.is_group:
        return {"status": "ignored", "reason": "group message"}

    # Get message text
    message_text = msg.body or msg.caption or ""
    if msg.type == "voice" and msg.media_url:
        # Voice messages should be transcribed by OpenWA
        # If body is set, it's already a transcription
        message_text = msg.body or ""

    if not message_text.strip():
        return {"status": "ignored", "reason": "empty message"}

    # Process message
    bot = WhatsAppBot(db)
    try:
        response_text = await bot.process_message(
            phone=msg.from_number,
            message=message_text,
            message_type=msg.type,
            media_url=msg.media_url,
        )

        # Send response back via OpenWA
        await bot.send_message(msg.from_number, response_text)

        logger.info(
            "whatsapp_message_processed",
            phone=msg.from_number[:6] + "****",
            type=msg.type,
            response_length=len(response_text),
        )

        return {
            "status": "ok",
            "response_sent": True,
        }

    except Exception as e:
        logger.error(
            "whatsapp_message_processing_error",
            phone=msg.from_number[:6] + "****",
            error=str(e),
        )
        # Don't expose internal errors to webhook caller
        return {
            "status": "error",
            "response_sent": False,
        }


@router.get("/whatsapp/health")
async def whatsapp_health():
    """
    Health check for WhatsApp webhook endpoint.

    Used by OpenWA to verify connectivity.
    """
    return {
        "status": "ok",
        "service": "msaidizi-whatsapp-webhook",
        "version": "0.2.0",
    }


@router.post("/whatsapp/daily-reports")
async def trigger_daily_reports(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger daily reports to all WhatsApp-connected users.

    Called by the backend scheduler (NOT OpenWA) at 7 PM EAT.
    Also callable manually for testing.

    Returns:
        Dict with total, sent, failed counts
    """
    # Validate signature
    body = await request.body()
    signature = request.headers.get("X-OpenWA-Signature")
    if signature:
        expected = hmac.new(
            settings.OPENWA_WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    from app.services.whatsapp_delivery import WhatsAppDelivery

    delivery = WhatsAppDelivery(db)
    result = await delivery.send_daily_reports_to_all()

    logger.info(
        "daily_reports_triggered",
        total=result["total"],
        sent=result["sent"],
        failed=result["failed"],
    )

    return result


@router.post("/whatsapp/weekly-reports")
async def trigger_weekly_reports(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger weekly reports to all WhatsApp-connected users.

    Called by the backend scheduler on Monday 8 AM EAT.
    """
    from app.services.whatsapp_delivery import WhatsAppDelivery

    delivery = WhatsAppDelivery(db)
    result = await delivery.send_weekly_reports_to_all()

    logger.info("weekly_reports_triggered", **result)
    return result


@router.post("/whatsapp/monthly-reports")
async def trigger_monthly_reports(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger monthly reports to all WhatsApp-connected users.

    Called by the backend scheduler on 1st of month 9 AM EAT.
    """
    from app.services.whatsapp_delivery import WhatsAppDelivery

    delivery = WhatsAppDelivery(db)
    result = await delivery.send_monthly_reports_to_all()

    logger.info("monthly_reports_triggered", **result)
    return result


@router.get("/whatsapp/openwa-health")
async def openwa_health_check():
    """
    Check OpenWA service health.

    Proxies to OpenWA's /health endpoint for monitoring.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.OPENWA_URL}/health",
                timeout=5.0,
            )
            return response.json()
    except Exception as e:
        logger.error("openwa_health_check_failed", error=str(e))
        return {
            "status": "error",
            "service": "msaidizi-openwa",
            "error": str(e),
            "connected": False,
        }
