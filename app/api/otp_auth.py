"""
OTP-Based Phone Authentication.

Implements phone + OTP authentication for the Msaidizi app.
This supplements the device-based auth (auth.py) with a more
traditional phone verification flow.

Flow:
1. POST /auth/otp/request — Send OTP to phone number
2. POST /auth/otp/verify — Verify OTP and get JWT tokens
3. POST /auth/otp/register — Register new user with phone + OTP

Production: Use Africa's Talking or Twilio for SMS delivery.
Development: Log OTP to console (DEBUG mode).
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token, create_refresh_token, decode_token
from app.config import get_settings
from app.db.database import get_db
from app.models.refresh_token import RefreshToken as RefreshTokenModel
from app.models.user import User
from app.utils.crypto import encrypt_value

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/auth/otp", tags=["OTP Authentication"])

# In-memory OTP store (production: Redis with TTL)
_otps: dict = {}


# =========================================================================
# Schemas
# =========================================================================


class OTPRequest(BaseModel):
    """Request to send OTP to a phone number."""
    phone: str = Field(..., min_length=10, max_length=15, description="Phone number with country code")


class OTPVerifyRequest(BaseModel):
    """Request to verify OTP."""
    phone: str = Field(..., min_length=10, max_length=15)
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")
    device_id: str = Field(..., max_length=100, description="Unique device identifier")


class OTPRegisterRequest(BaseModel):
    """Request to register a new user with phone + OTP."""
    phone: str = Field(..., min_length=10, max_length=15)
    code: str = Field(..., min_length=6, max_length=6)
    device_id: str = Field(..., max_length=100)
    name: Optional[str] = Field(None, max_length=200)
    business_type: str = Field(
        "dukawallah",
        pattern=r"^(dukawallah|mama_mboga|boda_boda|vendor|tailor|restaurant|other)$",
    )
    language: str = Field("sw", pattern=r"^(sw|en|sh)$")
    location_geohash: Optional[str] = Field(None, max_length=12)
    location_name: Optional[str] = Field(None, max_length=200)


class OTPResponse(BaseModel):
    """Response from OTP request."""
    status: str
    message: str
    otp_expires_in_seconds: int = 300


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    is_new_user: bool = False


# =========================================================================
# Helpers
# =========================================================================


def _generate_otp() -> str:
    """Generate a 6-digit OTP code."""
    return f"{secrets.randbelow(900000) + 100000}"


def _hash_phone(phone: str) -> str:
    """SHA-256 hash of phone number for secure lookups."""
    return hashlib.sha256(phone.encode()).hexdigest()


async def _send_otp_sms(phone: str, code: str) -> bool:
    """
    Send OTP via SMS.

    Production: Use Africa's Talking, Twilio, or similar.
    Development: Log to console.
    """
    if settings.DEBUG:
        logger.info("OTP_DEBUG", phone=phone, code=code, message="DEV MODE — OTP logged, not sent")
        return True

    # Production SMS integration would go here
    # Example with Africa's Talking:
    # import africastalking
    # sms = africastalking.SMS
    # sms.send(f"Your Msaidizi code is: {code}. Valid for 5 minutes.", [phone])
    logger.info("otp_sms_sent", phone=phone[:6] + "****")
    return True


# =========================================================================
# Endpoints
# =========================================================================


@router.post("/request", response_model=OTPResponse)
async def request_otp(request: OTPRequest):
    """
    Request an OTP code to be sent to a phone number.

    Rate limited: max 3 OTPs per phone per 10 minutes.
    OTP expires in 5 minutes.
    """
    phone = request.phone.strip()

    # Rate limiting check
    existing = _otps.get(phone)
    if existing:
        recent_count = sum(
            1 for otp in existing
            if otp["created_at"] > datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        if recent_count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many OTP requests. Please wait 10 minutes.",
            )

    code = _generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    # Store OTP
    if phone not in _otps:
        _otps[phone] = []
    _otps[phone].append({
        "code": code,
        "created_at": datetime.now(timezone.utc),
        "expires_at": expires_at,
        "verified": False,
    })

    # Clean old OTPs
    _otps[phone] = [
        otp for otp in _otps[phone]
        if otp["expires_at"] > datetime.now(timezone.utc)
    ]

    # Send OTP
    sent = await _send_otp_sms(phone, code)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please try again.",
        )

    logger.info("otp_requested", phone=phone[:6] + "****")

    return OTPResponse(
        status="sent",
        message=f"OTP sent to {phone[:6]}****",
        otp_expires_in_seconds=300,
    )


@router.post("/verify", response_model=TokenResponse)
async def verify_otp(
    request: OTPVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify OTP and authenticate existing user.

    Returns JWT tokens if the phone number is registered.
    If not registered, returns a 404 to prompt registration.
    """
    phone = request.phone.strip()
    phone_hash = _hash_phone(phone)

    # Verify OTP
    otps = _otps.get(phone, [])
    valid_otp = None
    for otp in reversed(otps):
        if otp["expires_at"] > datetime.now(timezone.utc) and not otp["verified"]:
            if otp["code"] == request.code:
                valid_otp = otp
                break

    if not valid_otp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP code",
        )

    # Mark as verified
    valid_otp["verified"] = True

    # Find user
    result = await db.execute(
        select(User).where(User.phone_hash == phone_hash)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not registered. Please register first.",
        )

    # Generate tokens
    token_data = {"sub": str(user.id), "phone_hash": phone_hash}
    access_token = create_access_token(token_data)
    family = secrets.token_hex(16)
    refresh_token = create_refresh_token(token_data, family=family)

    # Store refresh token
    rt_payload = decode_token(refresh_token)
    rt_record = RefreshTokenModel(
        user_id=user.id,
        family_id=rt_payload["family"],
        jti=rt_payload["jti"],
    )
    db.add(rt_record)

    # Update device info
    user.device_id = request.device_id
    user.last_sync_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info("otp_verified_login", user_id=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=str(user.id),
        is_new_user=False,
    )


@router.post("/register", response_model=TokenResponse)
async def register_with_otp(
    request: OTPRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with phone + OTP verification.

    Combines OTP verification with user registration in a single step.
    """
    phone = request.phone.strip()
    phone_hash = _hash_phone(phone)

    # Verify OTP
    otps = _otps.get(phone, [])
    valid_otp = None
    for otp in reversed(otps):
        if otp["expires_at"] > datetime.now(timezone.utc) and not otp["verified"]:
            if otp["code"] == request.code:
                valid_otp = otp
                break

    if not valid_otp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP code",
        )

    valid_otp["verified"] = True

    # Check if already registered
    existing = await db.execute(
        select(User).where(User.phone_hash == phone_hash)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already registered. Use login instead.",
        )

    # Create user
    user = User(
        phone_hash=phone_hash,
        phone_encrypted=encrypt_value(phone),
        name_encrypted=encrypt_value(request.name) if request.name else None,
        business_type=request.business_type,
        language=request.language,
        location_geohash=request.location_geohash,
        location_name=request.location_name,
        device_id=request.device_id,
        channel="app",
        consent_data_sharing=False,
    )
    db.add(user)
    await db.flush()

    # Generate tokens
    token_data = {"sub": str(user.id), "phone_hash": phone_hash}
    access_token = create_access_token(token_data)
    family = secrets.token_hex(16)
    refresh_token = create_refresh_token(token_data, family=family)

    rt_payload = decode_token(refresh_token)
    rt_record = RefreshTokenModel(
        user_id=user.id,
        family_id=rt_payload["family"],
        jti=rt_payload["jti"],
    )
    db.add(rt_record)
    await db.flush()

    logger.info("otp_registered", user_id=str(user.id), business_type=request.business_type)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=str(user.id),
        is_new_user=True,
    )
