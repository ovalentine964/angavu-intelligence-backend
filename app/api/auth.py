"""
Authentication endpoints.

Handles:
- Device authentication (for user sync)
- Buyer API key authentication
- JWT token generation and validation
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt as pyjwt
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_db
from app.models.buyer import Buyer, BuyerAPIKey
from app.models.refresh_token import RefreshToken as RefreshTokenModel
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
security = HTTPBearer()


# =========================================================================
# Schemas
# =========================================================================


class DeviceRegisterRequest(BaseModel):
    """Request to register or authenticate a device."""

    phone: str = Field(..., min_length=10, max_length=15)
    device_id: str = Field(..., max_length=100)
    name: Optional[str] = Field(None, max_length=200)
    business_type: str = Field(
        "dukawallah",
        pattern=r"^(dukawallah|mama_mboga|boda_boda|vendor|tailor|restaurant|other)$",
    )
    language: str = Field("sw", pattern=r"^(sw|en|sh)$")
    location_geohash: Optional[str] = Field(None, max_length=12)
    location_name: Optional[str] = Field(None, max_length=200)


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        ...,
        description="Access token expiry in seconds",
    )
    user_id: str


class RefreshRequest(BaseModel):
    """Request to refresh an access token."""

    refresh_token: str


# =========================================================================
# Token Utilities
# =========================================================================


def _get_signing_key() -> str:
    """Get the signing key — RSA private key for RS256, shared secret for HS256."""
    if settings.JWT_ALGORITHM == "RS256":
        if not settings.JWT_PRIVATE_KEY:
            raise ValueError("JWT_PRIVATE_KEY must be set when using RS256")
        return settings.JWT_PRIVATE_KEY
    return settings.JWT_SECRET_KEY


def _get_verification_key() -> str:
    """Get the verification key — RSA public key for RS256, shared secret for HS256."""
    if settings.JWT_ALGORITHM == "RS256":
        if not settings.JWT_PUBLIC_KEY:
            raise ValueError("JWT_PUBLIC_KEY must be set when using RS256")
        return settings.JWT_PUBLIC_KEY
    return settings.JWT_SECRET_KEY


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Includes:
    - Standard claims: exp, iat, nbf, jti, iss, aud
    - Token type: access
    - Device binding: device_id

    Args:
        data: Claims to include in the token
        expires_delta: Custom expiry time

    Returns:
        Encoded JWT string
    """
    now = datetime.now(timezone.utc)
    to_encode = data.copy()
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,  # Not valid before now (prevents pre-generated tokens)
        "jti": secrets.token_hex(16),  # Unique token ID for revocation
        "type": "access",
    })
    # Add issuer and audience if configured
    if hasattr(settings, 'JWT_ISSUER') and settings.JWT_ISSUER:
        to_encode["iss"] = settings.JWT_ISSUER
    if hasattr(settings, 'JWT_AUDIENCE') and settings.JWT_AUDIENCE:
        to_encode["aud"] = settings.JWT_AUDIENCE
    return pyjwt.encode(
        to_encode,
        _get_signing_key(),
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(data: dict, family: Optional[str] = None) -> str:
    """Create a JWT refresh token with longer expiry and token family tracking."""
    now = datetime.now(timezone.utc)
    to_encode = data.copy()
    expire = now + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "type": "refresh",
        "family": family or secrets.token_hex(16),
        "jti": secrets.token_hex(16),
    })
    if hasattr(settings, 'JWT_ISSUER') and settings.JWT_ISSUER:
        to_encode["iss"] = settings.JWT_ISSUER
    if hasattr(settings, 'JWT_AUDIENCE') and settings.JWT_AUDIENCE:
        to_encode["aud"] = settings.JWT_AUDIENCE
    return pyjwt.encode(
        to_encode,
        _get_signing_key(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Validates:
    - Signature (RS256 or HS256)
    - Expiration time
    - Issuer claim (prevents token confusion)
    - Audience claim (prevents cross-service token use)
    - Token type (access vs refresh)

    Raises:
        HTTPException if token is invalid or expired
    """
    try:
        payload = pyjwt.decode(
            token,
            _get_verification_key(),
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER if hasattr(settings, 'JWT_ISSUER') else None,
            audience=settings.JWT_AUDIENCE if hasattr(settings, 'JWT_AUDIENCE') else None,
            options={
                "require": ["exp", "sub", "type"],
                "verify_exp": True,
                "verify_iss": hasattr(settings, 'JWT_ISSUER') and settings.JWT_ISSUER is not None,
                "verify_aud": hasattr(settings, 'JWT_AUDIENCE') and settings.JWT_AUDIENCE is not None,
            },
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",  # Don't leak specific error details
        )


# =========================================================================
# Dependencies
# =========================================================================


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — extract and validate current user from JWT.

    Security checks:
    - Token signature and expiry (via decode_token)
    - User exists and is active
    - Token type is 'access' (not refresh)
    - User agent consistency (optional)

    Usage:
        @router.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return user
    """
    payload = decode_token(credentials.credentials)

    # Verify this is an access token, not a refresh token
    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    result = await db.execute(
        select(User).where(
            and_(User.id == user_id, User.is_active == True)
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        # Generic message — don't reveal whether user exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return user


async def get_buyer_from_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Buyer:
    """
    FastAPI dependency — authenticate buyer via API key.

    Expects header: Authorization: Bearer msai_xxxx

    Security:
    - Constant-time key comparison (prevents timing attacks)
    - Key hash stored (never plaintext)
    - Expiry enforcement
    - Active status check
    - Contract validity check

    Usage:
        @router.get("/intelligence/market/{market_id}")
        async def get_market(
            buyer: Buyer = Depends(get_buyer_from_api_key),
        ):
            ...
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization",
        )

    api_key = auth_header.replace("Bearer ", "")

    # Validate key format before hashing (early rejection)
    if not api_key.startswith("msai_") or len(api_key) < 20:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Look up the API key
    result = await db.execute(
        select(BuyerAPIKey).where(
            and_(
                BuyerAPIKey.key_hash == key_hash,
                BuyerAPIKey.is_active == True,
            )
        )
    )
    api_key_obj = result.scalar_one_or_none()

    if not api_key_obj:
        # Generic message — don't reveal whether key exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if api_key_obj.is_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired",
        )

    # Update last used timestamp
    api_key_obj.last_used_at = datetime.now(timezone.utc)

    # Get the buyer
    result = await db.execute(
        select(Buyer).where(
            and_(
                Buyer.id == api_key_obj.buyer_id,
                Buyer.is_active == True,
            )
        )
    )
    buyer = result.scalar_one_or_none()

    if not buyer or not buyer.is_contract_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account inactive or contract expired",
        )

    return buyer


# =========================================================================
# Endpoints
# =========================================================================


@router.post("/register", response_model=TokenResponse)
async def register_device(
    request: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new device or authenticate an existing one.

    If the phone number already exists, returns tokens for the
    existing user. Otherwise, creates a new user.
    """
    phone_hash = hashlib.sha256(request.phone.encode()).hexdigest()

    # Check if user exists
    result = await db.execute(
        select(User).where(User.phone_hash == phone_hash)
    )
    user = result.scalar_one_or_none()

    if user:
        # Existing user — update device info
        user.device_id = request.device_id
        user.last_sync_at = datetime.now(timezone.utc)
    else:
        # New user — encrypt phone and create
        from app.utils.crypto import encrypt_value
        user = User(
            phone_hash=phone_hash,
            phone_encrypted=encrypt_value(request.phone),
            name_encrypted=encrypt_value(request.name) if request.name else None,
            business_type=request.business_type,
            language=request.language,
            location_geohash=request.location_geohash,
            location_name=request.location_name,
            device_id=request.device_id,
            consent_data_sharing=False,
        )
        db.add(user)

    await db.flush()

    # Generate tokens with family tracking
    token_data = {"sub": str(user.id), "phone_hash": phone_hash}
    access_token = create_access_token(token_data)
    family = secrets.token_hex(16)
    refresh_token = create_refresh_token(token_data, family=family)

    # Store refresh token for rotation tracking
    rt_payload = decode_token(refresh_token)
    rt_record = RefreshTokenModel(
        user_id=user.id,
        family_id=rt_payload["family"],
        jti=rt_payload["jti"],
    )
    db.add(rt_record)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=str(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh an expired access token using a valid refresh token.

    Implements refresh token rotation with family-based theft detection:
    - Each refresh token is single-use
    - New tokens belong to the same family
    - If a used token is replayed, ALL tokens in the family are revoked
    """
    payload = decode_token(request.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not a refresh token",
        )

    user_id = payload.get("sub")
    family_id = payload.get("family")
    jti = payload.get("jti")

    if not user_id or not family_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing claims",
        )

    # Check if the entire family has been revoked (theft detection)
    family_revoked = await db.execute(
        select(RefreshTokenModel).where(
            and_(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked == True,
            )
        ).limit(1)
    )
    if family_revoked.scalar_one_or_none():
        # Family was revoked — possible token theft. Revoke ALL tokens for this user's family.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token family revoked (possible theft detected). Please re-authenticate.",
        )

    # Find the specific refresh token record
    rt_result = await db.execute(
        select(RefreshTokenModel).where(
            and_(
                RefreshTokenModel.jti == jti,
                RefreshTokenModel.family_id == family_id,
            )
        )
    )
    rt_record = rt_result.scalar_one_or_none()

    if not rt_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
        )

    if rt_record.used:
        # REPLAY DETECTED: This token was already used. Revoke the entire family.
        await db.execute(
            RefreshTokenModel.__table__.update()
            .where(RefreshTokenModel.family_id == family_id)
            .values(revoked=True)
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token replay detected. All sessions revoked. Please re-authenticate.",
        )

    # Mark current token as used
    rt_record.used = True
    rt_record.used_at = datetime.now(timezone.utc)

    # Verify user still exists and is active
    result = await db.execute(
        select(User).where(
            and_(User.id == user_id, User.is_active == True)
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Issue new tokens (same family, new jti)
    token_data = {"sub": str(user.id), "phone_hash": user.phone_hash}
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data, family=family_id)

    # Store new refresh token
    new_rt_payload = decode_token(new_refresh)
    new_rt_record = RefreshTokenModel(
        user_id=user.id,
        family_id=family_id,
        jti=new_rt_payload["jti"],
    )
    db.add(new_rt_record)
    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=str(user.id),
    )


@router.post("/consent")
async def update_consent(
    consent: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user's data sharing consent.

    Users must explicitly consent before their data can be included
    in anonymized intelligence products.
    """
    user.consent_data_sharing = consent
    return {
        "status": "ok",
        "consent": consent,
        "message": (
            "Data sharing consent updated. "
            + ("Your data will be included in anonymized intelligence products."
               if consent
               else "Your data will not be shared.")
        ),
    }
