"""
Authentication endpoints — Worker OTP + Buyer API key + OAuth2.

Architecture: arch_backend.md §7
"""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User, OTPCode
from app.models.buyer import BuyerOrg, BuyerAPIKey, BuyerSubscription
from app.services.auth import (
    create_otp,
    verify_otp,
    create_worker_token,
    verify_worker_token,
    create_buyer_token,
    verify_buyer_api_key,
    generate_api_key,
    hash_phone,
)
from app.config import settings

router = APIRouter()


# ─── Worker Auth ──────────────────────────────────────────────────────────────

class WorkerRegisterRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    name: str = Field(..., min_length=1, max_length=100)
    language: str = "sw"
    business_type: str = "unknown"


class OTPVerifyRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    code: str = Field(..., min_length=4, max_length=8)


@router.post("/worker/register")
async def register_worker(request: WorkerRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new worker — sends OTP to phone."""
    phone_h = hash_phone(request.phone)

    # Check if user exists
    result = await db.execute(select(User).where(User.phone_hash == phone_h))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Phone already registered. Use login instead.")

    # Create user
    worker_id_hash = hashlib.sha256(f"{request.phone}:{secrets.token_hex(8)}".encode()).hexdigest()
    user = User(
        worker_id_hash=worker_id_hash,
        name=request.name,
        phone_hash=phone_h,
        language=request.language,
        business_type=request.business_type,
    )
    db.add(user)
    await db.flush()

    # Send OTP
    code = await create_otp(db, request.phone, purpose="register")

    return {
        "status": "otp_sent",
        "worker_id_hash": worker_id_hash,
        "message": f"OTP sent to {request.phone[-4:].rjust(len(request.phone), '*')}",
        "otp_dev": code if settings.DEBUG else None,  # Remove in production
    }


@router.post("/worker/verify")
async def verify_worker_otp(request: OTPVerifyRequest, db: AsyncSession = Depends(get_db)):
    """Verify OTP and complete registration/login."""
    otp = await verify_otp(db, request.phone, request.code)
    if not otp:
        raise HTTPException(401, "Invalid or expired OTP code")

    phone_h = hash_phone(request.phone)
    result = await db.execute(select(User).where(User.phone_hash == phone_h))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found. Please register first.")

    user.is_active = True
    await db.flush()

    tokens = create_worker_token(user.id, user.worker_id_hash, user.language)
    return {**tokens, "worker_id_hash": user.worker_id_hash, "name": user.name}


@router.post("/worker/login")
async def login_worker(phone: str = Field(...), db: AsyncSession = Depends(get_db)):
    """Initiate worker login — sends OTP."""
    phone_h = hash_phone(phone)
    result = await db.execute(select(User).where(User.phone_hash == phone_h))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Phone not registered")

    code = await create_otp(db, phone, purpose="login")
    return {
        "status": "otp_sent",
        "message": f"OTP sent to {phone[-4:].rjust(len(phone), '*')}",
        "otp_dev": code if settings.DEBUG else None,
    }


@router.post("/worker/refresh")
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    """Refresh an expired access token."""
    from app.services.auth import verify_worker_token
    claims = verify_worker_token(refresh_token)
    if not claims or claims.get("type") != "refresh":
        raise HTTPException(401, "Invalid refresh token")

    result = await db.execute(select(User).where(User.id == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    tokens = create_worker_token(user.id, user.worker_id_hash, user.language)
    return tokens


# ─── Buyer Auth ───────────────────────────────────────────────────────────────

class BuyerRegisterRequest(BaseModel):
    company: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=5, max_length=255)
    industry: str = "other"
    product: str = "soko_pulse"  # Primary product interest


class BuyerTokenRequest(BaseModel):
    api_key: str = Field(...)


@router.post("/buyer/register")
async def register_buyer(request: BuyerRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a B2B buyer organization."""
    # Check existing
    result = await db.execute(select(BuyerOrg).where(BuyerOrg.contact_email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(409, "Email already registered")

    # Create org
    org = BuyerOrg(
        name=request.company,
        industry=request.industry,
        contact_email=request.email,
    )
    db.add(org)
    await db.flush()

    # Generate API key
    raw_key, key_hash, key_prefix = generate_api_key()
    api_key = BuyerAPIKey(
        buyer_id=org.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        org_name=request.company,
    )
    db.add(api_key)

    # Create starter subscription
    sub = BuyerSubscription(
        buyer_id=org.id,
        tier="starter",
        products=[request.product],
        starts_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=30),
        monthly_budget_usd=100.0,
    )
    db.add(sub)
    await db.flush()

    return {
        "status": "registered",
        "buyer_id": org.id,
        "api_key": raw_key,  # Show once, never again
        "tier": "starter",
        "products": [request.product],
        "message": "Save your API key securely. It cannot be retrieved later.",
    }


@router.post("/buyer/token")
async def get_buyer_token(request: BuyerTokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchange API key for OAuth2 bearer token (24h TTL)."""
    buyer_info = await verify_buyer_api_key(db, request.api_key)
    if not buyer_info:
        raise HTTPException(401, "Invalid API key or no active subscription")

    token = create_buyer_token(
        buyer_info["buyer_id"],
        buyer_info["org_name"],
        buyer_info["tier"],
        buyer_info["products"],
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
        "tier": buyer_info["tier"],
        "products": buyer_info["products"],
    }
