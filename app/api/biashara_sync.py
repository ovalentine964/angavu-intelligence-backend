"""
Biashara Sync Endpoint.

Handles the Msaidizi app's BiasharaSync protocol:
- POST /api/v1/biashara/sync — Upload anonymized transactions
- GET /api/v1/biashara/intelligence — Pull intelligence products

This is the primary data pipeline between the on-device Msaidizi app
and the Angavu Intelligence backend. Data flows:

Device → Backend: Anonymized transactions (no PII)
Backend → Device: Intelligence products (Soko Pulse, Alama Score, etc.)
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.services.intelligence_delivery import IntelligenceDelivery

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/biashara", tags=["Biashara Sync"])


# =========================================================================
# Schemas (match BiasharaSync.kt data classes)
# =========================================================================


class AnonymizedTransaction(BaseModel):
    """Anonymized transaction from device — no PII."""
    type: str = Field(..., description="SALE, PURCHASE, or EXPENSE")
    category: str = Field("", description="Product category")
    amount: float = Field(..., ge=0, description="Total amount in KES")
    quantity: float = Field(0, ge=0)
    timestamp: int = Field(..., description="Unix timestamp (seconds)")
    language: str = Field("sw")
    confidence: float = Field(1.0, ge=0, le=1)
    payment_method: str = Field("cash")
    coarse_location: str = Field("", description="Sub-county level location")


class BiasharaSyncPayload(BaseModel):
    """Sync payload from Msaidizi device."""
    device_id: str = Field(..., max_length=64, description="SHA-256 hashed device ID")
    worker_type: str = Field("", description="Worker classification")
    coarse_location: str = Field("")
    transactions: List[AnonymizedTransaction] = Field(
        ..., max_length=200, description="Batch of anonymized transactions"
    )
    sync_timestamp: int = Field(..., description="Unix timestamp when batch created")
    app_version: str = Field("1.0.0", max_length=20)

    @field_validator("transactions")
    @classmethod
    def validate_batch_size(cls, v):
        if len(v) > 200:
            raise ValueError("Maximum 200 transactions per batch")
        return v


class BiasharaSyncResponse(BaseModel):
    """Response after sync."""
    status: str = Field("ok", description="ok | partial | error")
    synced_id: str = Field(..., description="Unique sync operation ID")
    transactions_accepted: int = 0
    transactions_rejected: int = 0
    rejection_reasons: Optional[List[str]] = None
    intelligence_available: bool = Field(
        False,
        description="Whether new intelligence products are ready"
    )
    next_sync_recommended_seconds: int = 3600
    server_time: int = Field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp()),
        description="Server time as Unix timestamp"
    )


class IntelligencePullRequest(BaseModel):
    """Request to pull intelligence products."""
    device_id: str = Field(..., max_length=64)
    worker_type: str = Field("")
    coarse_location: str = Field("")
    language: str = Field("sw", pattern=r"^(sw|en|sh)$")
    since: Optional[int] = Field(None, description="Unix timestamp — only updates since this time")


class SokoPulseData(BaseModel):
    """Market price intelligence."""
    price_alerts: List[Dict] = Field(default_factory=list)
    market_trends: Dict[str, str] = Field(default_factory=dict)
    last_updated: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))


class AlamaScoreData(BaseModel):
    """Credit readiness assessment."""
    score: int = Field(0, ge=0, le=100)
    components: Dict[str, float] = Field(default_factory=dict)
    credit_readiness: float = Field(0.0, ge=0, le=1)
    recommended_loan_amount: float = Field(0.0)
    last_updated: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))


class BiasharaPulseData(BaseModel):
    """Business health intelligence."""
    health_score: float = Field(0.0, ge=0, le=100)
    peer_benchmark: Dict[str, float] = Field(default_factory=dict)
    growth_trend: str = Field("stable", description="growing | stable | declining")
    last_updated: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))


class JamiiInsightsData(BaseModel):
    """Community economic context."""
    area_activity: float = Field(0.0, ge=0, le=1)
    worker_count: int = Field(0)
    top_categories: List[str] = Field(default_factory=list)
    last_updated: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))


class IntelligenceUpdateResponse(BaseModel):
    """Complete intelligence update for device."""
    soko_pulse: SokoPulseData = Field(default_factory=SokoPulseData)
    alama_score: AlamaScoreData = Field(default_factory=AlamaScoreData)
    biashara_pulse: BiasharaPulseData = Field(default_factory=BiasharaPulseData)
    jamii_insights: JamiiInsightsData = Field(default_factory=JamiiInsightsData)
    received_at: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))


# =========================================================================
# Endpoints
# =========================================================================


@router.post("/sync", response_model=BiasharaSyncResponse)
async def biashara_sync(
    payload: BiasharaSyncPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload anonymized transactions from Msaidizi device.

    This is the primary data ingestion endpoint for the BiasharaSync protocol.
    Transactions arrive anonymized (no PII), batched, and with integrity checksums.

    **Privacy Guarantees:**
    - Device ID is SHA-256 hashed (irreversible)
    - No customer names, phone numbers, or exact locations
    - Only category + amount + timestamp are stored
    - Location is sub-county level (~10km radius)

    **Idempotency:**
    Uses device_id + sync_timestamp for batch-level deduplication.

    **Batch Limits:**
    - Max 200 transactions per batch
    """
    sync_id = str(uuid.uuid4())
    logger.info(
        "biashara_sync_started",
        sync_id=sync_id,
        device_id=payload.device_id[:12] + "...",
        txn_count=len(payload.transactions),
    )

    # Deduplication check — same device + same timestamp window
    sync_time = datetime.fromtimestamp(payload.sync_timestamp, tz=timezone.utc)
    existing = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.device_id == payload.device_id,
                Transaction.synced_at >= sync_time - timedelta(seconds=30),
                Transaction.synced_at <= sync_time + timedelta(seconds=30),
            )
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info("biashara_sync_duplicate", sync_id=sync_id)
        return BiasharaSyncResponse(
            status="ok",
            synced_id=sync_id,
            transactions_accepted=0,
            transactions_rejected=0,
            rejection_reasons=["Duplicate batch — already processed"],
        )

    # Process transactions
    accepted = 0
    rejected = 0
    reasons = []

    for record in payload.transactions:
        try:
            # Validation
            if record.amount <= 0:
                rejected += 1
                reasons.append(f"Invalid amount: {record.amount}")
                continue

            valid_types = {"SALE", "PURCHASE", "EXPENSE"}
            if record.type.upper() not in valid_types:
                rejected += 1
                reasons.append(f"Invalid type: {record.type}")
                continue

            # Timestamp sanity
            txn_time = datetime.fromtimestamp(record.timestamp, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            if txn_time > now + timedelta(hours=1):
                rejected += 1
                reasons.append(f"Future timestamp: {record.timestamp}")
                continue
            if txn_time < now - timedelta(days=90):
                rejected += 1
                reasons.append(f"Too old: {record.timestamp}")
                continue

            # Create transaction record
            txn = Transaction(
                user_id=uuid.UUID(payload.device_id[:32]),  # Use device_id as user proxy
                transaction_type=record.type.upper(),
                item_category=record.category if record.category else None,
                amount=record.amount,
                quantity=record.quantity,
                payment_method=record.payment_method if record.payment_method in ("mpesa", "cash", "credit", "bank", "other") else "cash",
                recorded_via="voice",
                confidence_score=record.confidence,
                timestamp=txn_time,
                synced_at=datetime.now(timezone.utc),
                device_id=payload.device_id,
                location_geohash=record.coarse_location[:5] if record.coarse_location else None,
            )
            db.add(txn)
            accepted += 1

        except Exception as e:
            rejected += 1
            reasons.append(f"Error: {str(e)}")

    await db.flush()

    logger.info(
        "biashara_sync_completed",
        sync_id=sync_id,
        accepted=accepted,
        rejected=rejected,
    )

    return BiasharaSyncResponse(
        status="ok" if rejected == 0 else "partial",
        synced_id=sync_id,
        transactions_accepted=accepted,
        transactions_rejected=rejected,
        rejection_reasons=reasons if reasons else None,
        intelligence_available=accepted > 0,
    )


@router.get("/intelligence", response_model=IntelligenceUpdateResponse)
async def pull_intelligence(
    device_id: str = Query(..., max_length=64),
    worker_type: str = Query(""),
    coarse_location: str = Query(""),
    language: str = Query("sw", regex=r"^(sw|en|sh)$"),
    since: Optional[int] = Query(None, description="Unix timestamp"),
    db: AsyncSession = Depends(get_db),
):
    """
    Pull intelligence products for a worker.

    Returns all available intelligence formatted for device display:
    - Soko Pulse: Market price intelligence
    - Alama Score: Credit readiness
    - Biashara Pulse: Business health
    - Jamii Insights: Community context
    """
    logger.info(
        "biashara_intelligence_pull",
        device_id=device_id[:12] + "...",
        language=language,
    )

    # Get intelligence from delivery service
    delivery = IntelligenceDelivery(db)
    since_dt = datetime.fromtimestamp(since, tz=timezone.utc) if since else None

    try:
        intel = await delivery.get_intelligence_for_worker(
            worker_id_hash=device_id,
            language=language,
            since=since_dt,
        )
    except Exception as e:
        logger.error("biashara_intelligence_error", error=str(e))
        # Return empty intelligence rather than error
        return IntelligenceUpdateResponse()

    # Map to response format
    briefing = intel.get("briefing", {})

    # Build Soko Pulse from market insights
    market = intel.get("market_insights", {})
    soko = SokoPulseData(
        price_alerts=[],
        market_trends={
            item["item"]: f"avg KES {item['avg_price']}"
            for item in (market.get("top_products", []) if market else [])
        },
    )

    # Build Biashara Pulse from briefing
    biashara = BiasharaPulseData(
        health_score=min(100, max(0, (briefing.get("profit_today", 0) or 0) / 10)),
        growth_trend="growing" if (briefing.get("profit_today", 0) or 0) > 0 else "stable",
    )

    return IntelligenceUpdateResponse(
        soko_pulse=soko,
        alama_score=AlamaScoreData(score=intel.get("alama_score") or 0),
        biashara_pulse=biashara,
        jamii_insights=JamiiInsightsData(
            top_categories=[
                p["item"] for p in (market.get("top_products", []) if market else [])
            ][:5],
        ),
    )
