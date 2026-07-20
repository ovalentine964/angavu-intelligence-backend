"""
Auth Domain — /api/v1/auth/*

Aggregates:
    - JWT Authentication       (app.api.auth)
    - OTP Authentication       (app.api.otp_auth)
"""

from fastapi import APIRouter

# Import existing routers (keep originals untouched)
from app.api.auth import router as _jwt_auth
from app.api.otp_auth import router as _otp_auth

auth_router = APIRouter(tags=["Authentication"])
auth_router.include_router(_jwt_auth)
auth_router.include_router(_otp_auth)
