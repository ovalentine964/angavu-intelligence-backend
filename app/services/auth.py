"""
Authentication service — Worker OTP + Buyer API key + JWT RS256.

Architecture: arch_backend.md §7, impl_buyer_dashboard
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import jwt
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User, OTPCode
from app.models.buyer import BuyerOrg, BuyerAPIKey, BuyerSubscription

logger = structlog.get_logger(__name__)

# ─── JWT Key Management ─────────────────────────────────────────────────────

_jwt_private_key = None
_jwt_public_key = None


def _load_keys():
    """Load RSA keys for JWT signing. Generate ephemeral keys if files don't exist."""
    global _jwt_private_key, _jwt_public_key

    priv_path = Path(settings.JWT_PRIVATE_KEY_PATH)
    pub_path = Path(settings.JWT_PUBLIC_KEY_PATH)

    if priv_path.exists() and pub_path.exists():
        _jwt_private_key = priv_path.read_text()
        _jwt_public_key = pub_path.read_text()
    else:
        # Generate ephemeral RSA keys for dev
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _jwt_private_key = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        _jwt_public_key = key.public_key().bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        priv_path.parent.mkdir(parents=True, exist_ok=True)
        priv_path.write_text(_jwt_private_key)
        pub_path.write_text(_jwt_public_key)
        logger.warning("generated_ephemeral_jwt_keys", path=str(priv_path.parent))


def get_private_key() -> str:
    if _jwt_private_key is None:
        _load_keys()
    return _jwt_private_key


def get_public_key() -> str:
    if _jwt_public_key is None:
        _load_keys()
    return _jwt_public_key


# ─── JWT Token Creation ──────────────────────────────────────────────────────

def create_worker_token(user_id: str, worker_id_hash: str, language: str = "sw") -> dict:
    """Create JWT access + refresh tokens for a worker."""
    now = datetime.now(UTC)
    access_payload = {
        "sub": user_id,
        "wid": worker_id_hash,
        "lang": language,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        "iss": "angavu-backend",
    }
    refresh_payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        "iss": "angavu-backend",
    }
    return {
        "access_token": jwt.encode(access_payload, get_private_key(), algorithm="RS256"),
        "refresh_token": jwt.encode(refresh_payload, get_private_key(), algorithm="RS256"),
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60,
    }


def verify_worker_token(token: str) -> Optional[dict]:
    """Verify and decode a worker JWT. Returns claims or None."""
    try:
        return jwt.decode(token, get_public_key(), algorithms=["RS256"])
    except jwt.ExpiredSignatureError:
        logger.warning("token_expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("token_invalid", error=str(e))
        return None


def create_buyer_token(buyer_id: str, org_name: str, tier: str, products: list[str]) -> str:
    """Create JWT for buyer OAuth2 flow."""
    now = datetime.now(UTC)
    payload = {
        "sub": buyer_id,
        "org": org_name,
        "tier": tier,
        "products": products,
        "type": "buyer",
        "iat": now,
        "exp": now + timedelta(hours=24),
        "iss": "angavu-buyer",
    }
    return jwt.encode(payload, settings.BUYER_JWT_SECRET, algorithm="HS256")


def verify_buyer_token(token: str) -> Optional[dict]:
    """Verify and decode a buyer JWT."""
    try:
        return jwt.decode(token, settings.BUYER_JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ─── OTP Flow ────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """Generate a cryptographically secure OTP."""
    return "".join(secrets.choice("0123456789") for _ in range(settings.OTP_LENGTH))


def hash_otp(code: str) -> str:
    """Hash OTP for storage (timing-safe comparison via hmac.compare_digest)."""
    return hashlib.sha256(code.encode()).hexdigest()


def hash_phone(phone: str) -> str:
    """Hash phone number for privacy-preserving lookups."""
    return hashlib.sha256(phone.encode()).hexdigest()


async def create_otp(db: AsyncSession, phone: str, purpose: str = "login") -> str:
    """Create and store an OTP code. Returns the raw code (to send to user)."""
    code = generate_otp()
    phone_h = hash_phone(phone)

    otp = OTPCode(
        phone_hash=phone_h,
        code_hash=hash_otp(code),
        purpose=purpose,
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(otp)
    await db.flush()
    logger.info("otp_created", phone_hash=phone_h[:8], purpose=purpose)
    return code


async def verify_otp(db: AsyncSession, phone: str, code: str) -> Optional[OTPCode]:
    """Verify an OTP code. Returns the OTP record if valid, None otherwise."""
    phone_h = hash_phone(phone)
    code_h = hash_otp(code)

    result = await db.execute(
        select(OTPCode).where(
            OTPCode.phone_hash == phone_h,
            OTPCode.code_hash == code_h,
            OTPCode.is_used == False,
            OTPCode.expires_at > datetime.now(UTC),
        ).order_by(OTPCode.created_at.desc()).limit(1)
    )
    otp = result.scalar_one_or_none()

    if otp is None:
        logger.warning("otp_verification_failed", phone_hash=phone_h[:8])
        return None

    otp.is_used = True
    await db.flush()
    logger.info("otp_verified", phone_hash=phone_h[:8])
    return otp


# ─── Buyer Auth ──────────────────────────────────────────────────────────────

def generate_api_key() -> tuple[str, str, str]:
    """Generate a buyer API key. Returns (raw_key, key_hash, key_prefix)."""
    raw_key = f"angavu_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


async def verify_buyer_api_key(db: AsyncSession, api_key: str) -> Optional[dict]:
    """Verify a buyer API key and return buyer info."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    result = await db.execute(
        select(BuyerAPIKey).where(
            BuyerAPIKey.key_hash == key_hash,
            BuyerAPIKey.is_active == True,
        )
    )
    api_key_obj = result.scalar_one_or_none()
    if api_key_obj is None:
        return None

    # Check active subscription
    result = await db.execute(
        select(BuyerSubscription).where(
            BuyerSubscription.buyer_id == api_key_obj.buyer_id,
            BuyerSubscription.status == "active",
            BuyerSubscription.expires_at > datetime.now(UTC),
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return None

    # Update last used
    api_key_obj.last_used_at = datetime.now(UTC)
    await db.flush()

    return {
        "buyer_id": api_key_obj.buyer_id,
        "org_name": api_key_obj.org_name or "",
        "tier": sub.tier,
        "products": sub.products or [],
    }
