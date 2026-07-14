"""
WhatsApp Connection Management Endpoints.

These endpoints handle the Msaidizi app's WhatsApp onboarding flow:
- Connect WhatsApp (initiate verification)
- Verify WhatsApp (confirm code)
- Check verification status
- Get connection status
- Disconnect WhatsApp
- Send report via WhatsApp

The Msaidizi app uses these during onboarding and daily report delivery.
This is SEPARATE from the webhook endpoint (/webhooks/whatsapp) which
handles incoming messages from OpenWA.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.services.whatsapp_bot import WhatsAppBot

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Connection"])

# Verification store — uses Redis if available, falls back to in-memory
import json
_verifications: dict = {}  # Fallback when Redis unavailable
_redis_client = None

async def _get_redis():
    """Get Redis client for verification storage."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            from app.config import get_settings
            settings = get_settings()
            _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client

async def _store_verification(verification_id: str, data: dict, ttl: int = 600):
    """Store verification in Redis (survives restart) or in-memory fallback."""
    redis = await _get_redis()
    if redis:
        await redis.setex(f"wa_verify:{verification_id}", ttl, json.dumps(data))
    else:
        _verifications[verification_id] = data

async def _get_verification(verification_id: str) -> dict:
    """Retrieve verification from Redis or in-memory."""
    redis = await _get_redis()
    if redis:
        data = await redis.get(f"wa_verify:{verification_id}")
        return json.loads(data) if data else None
    return _verifications.get(verification_id)

async def _delete_verification(verification_id: str):
    """Delete verification from Redis or in-memory."""
    redis = await _get_redis()
    if redis:
        await redis.delete(f"wa_verify:{verification_id}")
    else:
        _verifications.pop(verification_id, None)


# =========================================================================
# Schemas
# =========================================================================


class WhatsAppConnectRequest(BaseModel):
    """Request to initiate WhatsApp connection."""
    phone: str = Field(..., min_length=10, max_length=15)
    user_id: str = Field(..., description="User UUID")
    name: str = Field(..., max_length=200)
    assistant_name: str = Field("Msaidizi", max_length=50)
    language: str = Field("sw", pattern=r"^(sw|en|sh)$")
    report_time: str = Field("evening", pattern=r"^(morning|afternoon|evening)$")


class WhatsAppConnectResponse(BaseModel):
    """Response from WhatsApp connect request."""
    status: str
    verification_id: Optional[str] = None
    message: Optional[str] = None
    error_code: Optional[str] = None


class WhatsAppVerifyRequest(BaseModel):
    """Request to verify WhatsApp connection with code."""
    verification_id: str
    code: Optional[str] = None


class WhatsAppVerifyResponse(BaseModel):
    """Response from WhatsApp verification."""
    status: str
    whatsapp_id: Optional[str] = None
    message: Optional[str] = None


class WhatsAppConnection(BaseModel):
    """WhatsApp connection status."""
    user_id: str
    phone: str
    connected: bool
    connected_at: Optional[str] = None
    assistant_name: Optional[str] = None
    language: str
    report_time: str
    last_report_sent: Optional[str] = None


class SendReportRequest(BaseModel):
    """Request to send a report via WhatsApp."""
    user_id: str
    report_type: str = Field(..., description="daily, weekly, monthly")
    date: Optional[str] = None


class SendReportResponse(BaseModel):
    """Response from send report request."""
    status: str
    message_id: Optional[str] = None
    message: Optional[str] = None


# =========================================================================
# Endpoints
# =========================================================================


@router.post("/connect", response_model=WhatsAppConnectResponse)
async def connect_whatsapp(
    request: WhatsAppConnectRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate WhatsApp connection for a user.

    Sends a verification code to the user's WhatsApp number.
    The user must then call /verify with the code to complete connection.

    Flow:
    1. Validate phone number
    2. Generate verification code
    3. Send code via WhatsApp (OpenWA)
    4. Return verification_id for polling
    """
    # Validate user exists
    try:
        user_uuid = uuid.UUID(request.user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Generate verification code (6 digits)
    code = f"{secrets.randbelow(900000) + 100000}"
    verification_id = str(uuid.uuid4())

    # Store verification in memory (production: Redis with TTL)
    await _store_verification(verification_id, {
        "user_id": str(user.id),
        "phone": request.phone,
        "code": code,
        "assistant_name": request.assistant_name,
        "language": request.language,
        "report_time": request.report_time,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "verified": False,
        "attempts": 0,
    })

    # Send verification code via WhatsApp
    try:
        bot = WhatsAppBot(db)
        await bot.send_message(
            request.phone,
            f"Your Msaidizi verification code is: {code}\n"
            f"This code expires in 10 minutes.",
        )
        logger.info(
            "whatsapp_verification_sent",
            user_id=request.user_id,
            phone=request.phone[:6] + "****",
            verification_id=verification_id,
        )
    except Exception as e:
        logger.warning(
            "whatsapp_verification_send_failed",
            user_id=request.user_id,
            error=str(e),
        )
        # Still return verification_id — user can retry verify
        return WhatsAppConnectResponse(
            status="pending",
            verification_id=verification_id,
            message="Verification code could not be sent. Please try again.",
            error_code="SEND_FAILED",
        )

    return WhatsAppConnectResponse(
        status="pending",
        verification_id=verification_id,
        message="Verification code sent to your WhatsApp.",
    )


@router.post("/verify", response_model=WhatsAppVerifyResponse)
async def verify_whatsapp(
    request: WhatsAppVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify WhatsApp connection with the code sent to the user.

    On success, marks the user's WhatsApp as connected and
    stores connection preferences (language, report_time, etc.).
    """
    verification = await _get_verification(request.verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification not found or expired",
        )

    # Check expiry
    if datetime.now(timezone.utc) > verification["expires_at"]:
        await _delete_verification(request.verification_id)
        return WhatsAppVerifyResponse(
            status="expired",
            message="Verification code has expired. Please request a new one.",
        )

    # Check attempts
    verification["attempts"] += 1
    if verification["attempts"] > 5:
        await _delete_verification(request.verification_id)
        return WhatsAppVerifyResponse(
            status="failed",
            message="Too many attempts. Please request a new code.",
        )

    # Verify code
    if request.code and request.code != verification["code"]:
        return WhatsAppVerifyResponse(
            status="pending",
            message=f"Invalid code. {5 - verification['attempts']} attempts remaining.",
        )

    # Mark as verified
    verification["verified"] = True

    # Update user record with WhatsApp connection info
    try:
        user_uuid = uuid.UUID(verification["user_id"])
        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()
        if user:
            # Store connection metadata (channel already exists on User model)
            user.channel = "whatsapp"
            user.language = verification["language"]
            await db.flush()
    except Exception as e:
        logger.warning("whatsapp_user_update_failed", error=str(e))

    # Generate a WhatsApp ID (in production: actual OpenWA session ID)
    whatsapp_id = f"wa_{secrets.token_hex(8)}"

    logger.info(
        "whatsapp_verified",
        user_id=verification["user_id"],
        phone=verification["phone"][:6] + "****",
    )

    return WhatsAppVerifyResponse(
        status="connected",
        whatsapp_id=whatsapp_id,
        message="WhatsApp connected successfully!",
    )


@router.get("/verify/{verification_id}/status")
async def check_verification_status(
    verification_id: str,
):
    """
    Check the status of a WhatsApp verification.

    Polls the verification state until it's completed or expired.
    """
    verification = await _get_verification(verification_id)
    if not verification:
        return WhatsAppVerifyResponse(
            status="expired",
            message="Verification not found or expired.",
        )

    if datetime.now(timezone.utc) > verification["expires_at"]:
        await _delete_verification(verification_id)
        return WhatsAppVerifyResponse(
            status="expired",
            message="Verification has expired.",
        )

    if verification["verified"]:
        return WhatsAppVerifyResponse(
            status="connected",
            whatsapp_id=f"wa_{secrets.token_hex(8)}",
            message="WhatsApp connected!",
        )

    return WhatsAppVerifyResponse(
        status="pending",
        message=f"Waiting for verification. {5 - verification['attempts']} attempts remaining.",
    )


@router.get("/connection/{user_id}", response_model=WhatsAppConnection)
async def get_connection(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get WhatsApp connection status for a user.

    Returns connection details including preferences.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if user has an active WhatsApp connection
    connected = user.channel == "whatsapp"

    return WhatsAppConnection(
        user_id=str(user.id),
        phone="****",  # Never expose actual phone
        connected=connected,
        connected_at=user.last_sync_at.isoformat() if user.last_sync_at else None,
        assistant_name="Msaidizi",
        language=user.language or "sw",
        report_time="evening",  # Default, stored in preferences
        last_report_sent=None,
    )


@router.post("/disconnect/{user_id}", response_model=WhatsAppConnectResponse)
async def disconnect_whatsapp(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Disconnect WhatsApp for a user.

    Stops report delivery via WhatsApp. User can still use
    the Msaidizi app directly.
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update channel to app (default)
    user.channel = "app"
    await db.flush()

    logger.info(
        "whatsapp_disconnected",
        user_id=user_id,
    )

    return WhatsAppConnectResponse(
        status="disconnected",
        message="WhatsApp disconnected. You can still use the Msaidizi app.",
    )


@router.post("/send-report", response_model=SendReportResponse)
async def send_report(
    request: SendReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a business report via WhatsApp.

    Generates and sends a formatted report (daily, weekly, or monthly)
    to the user's connected WhatsApp number.
    """
    try:
        user_uuid = uuid.UUID(request.user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format",
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.channel != "whatsapp":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have WhatsApp connected",
        )

    # Generate report using WhatsAppBot
    try:
        from app.utils.crypto import decrypt_value
        bot = WhatsAppBot(db)
        phone = decrypt_value(user.phone_encrypted)
        # Use the existing report handling method
        report_text = await bot._handle_report_request(user, request.report_type)
        # Send via WhatsApp
        success = await bot.send_message(phone, report_text)
        message_id = f"msg_{secrets.token_hex(8)}"

        logger.info(
            "whatsapp_report_sent",
            user_id=request.user_id,
            report_type=request.report_type,
        )

        return SendReportResponse(
            status="sent",
            message_id=message_id,
            message=f"{request.report_type.capitalize()} report sent to WhatsApp.",
        )
    except Exception as e:
        logger.error("whatsapp_report_send_failed", error=str(e))
        return SendReportResponse(
            status="failed",
            message="Failed to send report. Please try again.",
        )
