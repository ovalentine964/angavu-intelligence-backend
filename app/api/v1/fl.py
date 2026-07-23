"""
Federated Learning API — Device-to-server gradient aggregation.

Architecture: arch_backend.md §2.4, §4.3
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.fl_service import FLService

router = APIRouter(prefix="/fl", tags=["Federated Learning"])


class FLUploadRequest(BaseModel):
    device_id_hash: str
    dialect: str = Field(..., min_length=2, max_length=20)
    calibration_params: Optional[dict] = None
    correction_patterns: Optional[list] = None
    adapter_deltas: Optional[bytes] = None
    sample_count: int = Field(default=1, ge=1)
    privacy_epsilon: float = Field(default=0.1, gt=0, le=10)
    metadata: Optional[dict] = None


@router.post("/upload")
async def upload_gradient(
    request: FLUploadRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit gradient update from device. Aggregates when threshold met."""
    service = FLService(db)
    result = await service.upload_update(
        device_id_hash=request.device_id_hash,
        dialect=request.dialect,
        calibration_params=request.calibration_params,
        correction_patterns=request.correction_patterns,
        adapter_deltas=request.adapter_deltas,
        sample_count=request.sample_count,
        privacy_epsilon=request.privacy_epsilon,
        metadata=request.metadata,
    )
    return result


@router.get("/model/{dialect}")
async def get_global_model(dialect: str, db: AsyncSession = Depends(get_db)):
    """Get latest aggregated global model for a dialect."""
    service = FLService(db)
    model = await service.get_global_model(dialect)
    if model is None:
        raise HTTPException(404, f"No model available for dialect: {dialect}")
    return model


@router.get("/status")
async def fl_status(db: AsyncSession = Depends(get_db)):
    """Get FL system status — pending updates, models, rounds."""
    service = FLService(db)
    return await service.get_status()
