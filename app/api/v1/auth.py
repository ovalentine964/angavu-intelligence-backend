"""
Authentication endpoints — Worker auth + Buyer auth.
Architecture: arch_backend.md, impl_buyer_dashboard
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class WorkerRegisterRequest(BaseModel):
    phone: str
    name: str
    language: str = "sw"
    business_type: str = "unknown"


class BuyerRegisterRequest(BaseModel):
    company: str
    email: str
    product: str  # soko_pulse, alama_score, angavu_pulse, jamii_insights


@router.post("/worker/register")
async def register_worker(request: WorkerRegisterRequest):
    """Register a new worker (phone + OTP)."""
    # TODO: Implement OTP flow
    return {"status": "pending", "message": "OTP sent to phone"}


@router.post("/worker/login")
async def login_worker(phone: str, otp: str):
    """Login with OTP."""
    # TODO: Implement OTP verification
    return {"status": "pending", "message": "OTP verification needed"}


@router.post("/buyer/register")
async def register_buyer(request: BuyerRegisterRequest):
    """Register a B2B buyer."""
    # TODO: Implement buyer registration
    return {"status": "pending", "message": "Buyer registration pending"}


@router.post("/buyer/login")
async def login_buyer(email: str, api_key: str):
    """Login with API key."""
    # TODO: Implement buyer auth
    return {"status": "pending", "message": "Buyer login pending"}
