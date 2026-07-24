"""Authentication endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.deps import get_db
from app.models.domain import User

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenRequest(BaseModel):
    external_id: str
    phone_hash: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def create_access_token(user_id: str, role: str) -> tuple[str, int]:
    """Create JWT access token."""
    expires_delta = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": user_id, "role": role, "exp": expire}
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, int(expires_delta.total_seconds())


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(lambda: None),  # placeholder for OAuth2 scheme
) -> User:
    """Extract current user from JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


@router.post("/token", response_model=TokenResponse)
async def get_token(req: TokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchange credentials for JWT token."""
    result = await db.execute(
        select(User).where(
            User.external_id == req.external_id,
            User.phone_hash == req.phone_hash,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token, expires_in = create_access_token(str(user.id), user.role)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(req: TokenRequest, db: AsyncSession = Depends(get_db)):
    """Register a new anonymized user."""
    existing = await db.execute(select(User).where(User.external_id == req.external_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = User(external_id=req.external_id, phone_hash=req.phone_hash)
    db.add(user)
    await db.flush()
    return {"id": str(user.id), "status": "created"}
