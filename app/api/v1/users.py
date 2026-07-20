"""
User Profile API — /api/v1/users/*

Endpoints:
    GET   /users/me  — Return current user profile
    PATCH /users/me  — Update user profile fields
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.utils.crypto import decrypt_value

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class UserProfileResponse(BaseModel):
    """Current user profile."""

    id: str
    name: str | None = None
    phone: str | None = None
    business_type: str
    language: str
    channel: str
    location_geohash: str | None = None
    location_name: str | None = None
    device_id: str | None = None
    app_version: str | None = None
    is_active: bool
    consent_data_sharing: bool
    created_at: str
    updated_at: str


class UserUpdateRequest(BaseModel):
    """Fields that can be updated on a user profile."""

    name: str | None = Field(None, max_length=200, description="Display name")
    business_type: str | None = Field(
        None,
        pattern=r"^(dukawallah|mama_mboga|boda_boda|vendor|tailor|restaurant|other)$",
        description="Business type",
    )
    language: str | None = Field(
        None,
        pattern=r"^(sw|en|sh)$",
        description="Preferred language",
    )
    location_geohash: str | None = Field(None, max_length=12, description="Location geohash")
    location_name: str | None = Field(None, max_length=200, description="Human-readable location")
    consent_data_sharing: bool | None = Field(None, description="Data sharing consent")


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """
    Return the authenticated user's profile.

    Decrypts sensitive fields (name, phone) before returning.
    """
    try:
        name = decrypt_value(current_user.name_encrypted) if current_user.name_encrypted else None
    except Exception:
        name = None

    try:
        phone = decrypt_value(current_user.phone_encrypted) if current_user.phone_encrypted else None
    except Exception:
        phone = None

    return UserProfileResponse(
        id=str(current_user.id),
        name=name,
        phone=phone,
        business_type=current_user.business_type,
        language=current_user.language,
        channel=current_user.channel,
        location_geohash=current_user.location_geohash,
        location_name=current_user.location_name,
        device_id=current_user.device_id,
        app_version=current_user.app_version,
        is_active=current_user.is_active,
        consent_data_sharing=current_user.consent_data_sharing,
        created_at=current_user.created_at.isoformat(),
        updated_at=current_user.updated_at.isoformat(),
    )


@router.patch("/me", response_model=UserProfileResponse)
async def update_current_user_profile(
    request: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update the authenticated user's profile fields.

    Only provided fields are updated; omitted fields remain unchanged.
    """
    from app.utils.crypto import encrypt_value
    import hashlib

    if request.name is not None:
        current_user.name_encrypted = encrypt_value(request.name)
    if request.business_type is not None:
        current_user.business_type = request.business_type
    if request.language is not None:
        current_user.language = request.language
    if request.location_geohash is not None:
        current_user.location_geohash = request.location_geohash
    if request.location_name is not None:
        current_user.location_name = request.location_name
    if request.consent_data_sharing is not None:
        current_user.consent_data_sharing = request.consent_data_sharing

    await db.flush()

    logger.info("user_profile_updated", user_id=str(current_user.id))

    try:
        name = decrypt_value(current_user.name_encrypted) if current_user.name_encrypted else None
    except Exception:
        name = None

    try:
        phone = decrypt_value(current_user.phone_encrypted) if current_user.phone_encrypted else None
    except Exception:
        phone = None

    return UserProfileResponse(
        id=str(current_user.id),
        name=name,
        phone=phone,
        business_type=current_user.business_type,
        language=current_user.language,
        channel=current_user.channel,
        location_geohash=current_user.location_geohash,
        location_name=current_user.location_name,
        device_id=current_user.device_id,
        app_version=current_user.app_version,
        is_active=current_user.is_active,
        consent_data_sharing=current_user.consent_data_sharing,
        created_at=current_user.created_at.isoformat(),
        updated_at=current_user.updated_at.isoformat(),
    )
