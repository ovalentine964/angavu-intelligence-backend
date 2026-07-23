"""
Sync endpoints — Device-to-cloud synchronization.

Architecture: arch_backend.md §2.6
- Push: device sends transactions, backend stores + resolves conflicts
- Pull: device gets server-side changes since last sync
- Gradients: device submits FL gradients
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.auth import verify_worker_token
from app.services.sync import process_sync_upload
from app.services.fl_service import FLService
from app.infrastructure.metrics import SYNC_TRANSACTIONS, SYNC_DURATION
import time

router = APIRouter()


# ─── Request/Response Models ─────────────────────────────────────────────────

class TransactionItem(BaseModel):
    id: Optional[str] = None
    idempotency_key: Optional[str] = None
    tx_type: str = Field(default="sale", pattern="^(sale|purchase|expense)$")
    amount: float = Field(..., gt=0)
    currency: str = "KES"
    description: Optional[str] = None
    product_name: Optional[str] = None
    product_category: Optional[str] = None
    quantity: int = Field(default=1, ge=1)
    payment_method: str = "cash"
    location_geohash: Optional[str] = None
    vector_clock: dict = {}
    device_timestamp: Optional[str] = None


class SyncPushRequest(BaseModel):
    worker_id_hash: str
    device_id: str
    transactions: list[TransactionItem]
    vector_clock: dict = {}
    checksum: Optional[str] = None


class GradientSyncRequest(BaseModel):
    device_id_hash: str
    dialect: str = Field(..., min_length=2, max_length=20)
    calibration_params: Optional[dict] = None
    correction_patterns: Optional[list] = None
    sample_count: int = Field(default=1, ge=1)
    privacy_epsilon: float = Field(default=0.1, gt=0, le=10)


class SyncResponse(BaseModel):
    status: str
    synced_count: int = 0
    conflicts: list = []
    backend_clock: dict = {}
    intelligence_updates_available: bool = False


# ─── Auth Dependency ──────────────────────────────────────────────────────────

async def get_current_worker(authorization: str = Header(...)):
    """Extract and verify worker JWT from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")
    token = authorization[7:]
    claims = verify_worker_token(token)
    if not claims:
        raise HTTPException(401, "Invalid or expired token")
    return claims


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/push", response_model=SyncResponse)
async def sync_push(
    payload: SyncPushRequest,
    worker=Depends(get_current_worker),
    db: AsyncSession = Depends(get_db),
):
    """Receive transaction data from device. Stores, deduplicates, resolves conflicts."""
    start = time.monotonic()

    # Verify worker owns this data
    if payload.worker_id_hash != worker.get("wid"):
        raise HTTPException(403, "Cannot sync data for another worker")

    tx_dicts = [tx.model_dump() for tx in payload.transactions]

    result = await process_sync_upload(
        db=db,
        worker_id_hash=payload.worker_id_hash,
        device_id=payload.device_id,
        transactions=tx_dicts,
        vector_clock=payload.vector_clock,
    )

    SYNC_TRANSACTIONS.inc(result["synced_count"])
    SYNC_DURATION.observe(time.monotonic() - start)

    return result


@router.get("/pull")
async def sync_pull(
    since_clock: Optional[str] = None,
    worker=Depends(get_current_worker),
    db: AsyncSession = Depends(get_db),
):
    """Get server-side changes since device's last known clock."""
    from app.models.transaction import Transaction
    from sqlalchemy import select, and_

    worker_id = worker.get("wid")

    result = await db.execute(
        select(Transaction).where(
            Transaction.user_id == worker_id,
        ).order_by(Transaction.created_at.desc()).limit(100)
    )
    transactions = result.scalars().all()

    return {
        "status": "ok",
        "transactions": [
            {
                "id": str(t.id),
                "tx_type": t.tx_type,
                "amount": float(t.amount),
                "product_name": t.product_name,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "vector_clock": t.vector_clock,
            }
            for t in transactions
        ],
        "backend_clock": {"backend:primary": len(transactions)},
    }


@router.post("/gradients")
async def receive_gradients(
    payload: GradientSyncRequest,
    worker=Depends(get_current_worker),
    db: AsyncSession = Depends(get_db),
):
    """Receive federated learning gradients from device."""
    # Verify worker consented to FL
    if not worker.get("wid"):
        raise HTTPException(403, "Worker not authenticated")

    service = FLService(db)
    result = await service.upload_update(
        device_id_hash=payload.device_id_hash,
        dialect=payload.dialect,
        calibration_params=payload.calibration_params,
        correction_patterns=payload.correction_patterns,
        sample_count=payload.sample_count,
        privacy_epsilon=payload.privacy_epsilon,
    )
    return result


@router.get("/intelligence/{worker_id_hash}")
async def get_intelligence_updates(
    worker_id_hash: str,
    worker=Depends(get_current_worker),
    db: AsyncSession = Depends(get_db),
):
    """Get pre-computed intelligence for worker's region."""
    if worker_id_hash != worker.get("wid"):
        raise HTTPException(403, "Cannot access another worker's intelligence")

    from app.models.user import User
    from app.models.intelligence import IntelligenceProduct
    from sqlalchemy import select, and_

    # Get worker's region
    result = await db.execute(select(User).where(User.worker_id_hash == worker_id_hash))
    user = result.scalar_one_or_none()
    if not user or not user.location_geohash:
        return {"status": "no_region", "intelligence": []}

    region = user.location_geohash[:5]

    # Get available intelligence
    result = await db.execute(
        select(IntelligenceProduct).where(
            and_(
                IntelligenceProduct.region == region,
                IntelligenceProduct.status == "ready",
            )
        ).order_by(IntelligenceProduct.created_at.desc()).limit(10)
    )
    products = result.scalars().all()

    return {
        "status": "ok",
        "region": region,
        "intelligence": [
            {
                "product_type": p.product_type,
                "category": p.category,
                "generated_at": p.generated_at.isoformat() if p.generated_at else None,
                "data": p.data,
            }
            for p in products
        ],
    }
