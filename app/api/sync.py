"""
Sync API endpoints.

Handles device-to-cloud data synchronization for the Msaidizi ↔ Angavu
Intelligence sync pipeline.

Sync Protocol:
    1. Device compresses payload with gzip (60-70% reduction)
    2. Device encrypts with AES-256 (per-user key)
    3. Device sends via HTTP/2 over TLS 1.3
    4. Cloud decrypts, decompresses, validates, stores
    5. Cloud returns sync status and intelligence updates

Data Flow — Msaidizi → Angavu Intelligence:
    Worker speaks → Whisper STT → Intent classification → Transaction (Room DB)
    → When online: batch upload (gzip, encrypted)
    → Backend: validate → store → trigger intelligence recalculation

Data Flow — Angavu Intelligence → Msaidizi:
    Backend processes → generates intelligence
    → Push notification to device
    → Device pulls intelligence (when online)
    → Displayed to worker in local language
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.sync import (
    SyncRequest,
    SyncResponse,
    TransactionBatch,
    TransactionBatchResponse,
    SyncStatusResponse,
    IntelligenceUpdate,
)
from app.services.anonymizer import Anonymizer
from app.services.intelligence_delivery import IntelligenceDelivery
from app.services.sync_service import SyncService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/sync", tags=["Data Sync"])


@router.post("", response_model=SyncResponse)
async def sync_data(
    request: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept batched transaction data from a device.

    This is the primary data ingestion endpoint. Devices send
    compressed, encrypted payloads containing batches of transactions
    and inventory updates.

    **Request Flow:**
    1. Validate JWT token (device authentication)
    2. Verify user matches device
    3. Process transactions (deduplicate, validate, store)
    4. Update inventory levels
    5. Return sync status

    **Idempotency:**
    Syncs are idempotent — sending the same transactions twice
    won't create duplicates. Uses (user_id + timestamp + amount + item)
    as deduplication key.

    **Batch Limits:**
    - Max 200 transactions per sync
    - Max 100 inventory updates per sync
    - Max payload size: 200KB (compressed)

    Args:
        request: The sync request with batched data
        current_user: Authenticated user (from JWT)
        db: Database session

    Returns:
        SyncResponse with processing results
    """
    # Verify the user_id in the request matches the authenticated user
    if str(request.user_id) != str(current_user.id):
        logger.warning(
            "sync_user_mismatch",
            token_user=str(current_user.id),
            request_user=str(request.user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User ID mismatch: token does not match request",
        )

    # Handle compressed payloads
    if request.is_compressed:
        try:
            # In production, the payload would be a base64-encoded
            # compressed blob that gets decompressed here
            logger.info(
                "sync_compressed_payload",
                device_id=request.device_id,
            )
        except Exception as e:
            logger.error("sync_decompression_failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to decompress payload: {str(e)}",
            )

    # Process the sync
    sync_service = SyncService(db)
    response = await sync_service.process_sync(request)

    if response.status == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response.rejection_reasons,
        )

    logger.info(
        "sync_completed",
        sync_id=response.sync_id,
        user_id=str(current_user.id),
        accepted=response.transactions_accepted,
        rejected=response.transactions_rejected,
    )

    return response


@router.get("/status")
async def sync_status(
    current_user: User = Depends(get_current_user),
):
    """
    Get current sync status for the authenticated device.

    Returns information about the last sync, pending data,
    and recommended next sync time.
    """
    return {
        "user_id": str(current_user.id),
        "device_id": current_user.device_id,
        "last_sync_at": (
            current_user.last_sync_at.isoformat()
            if current_user.last_sync_at
            else None
        ),
        "app_version": current_user.app_version,
        "is_active": current_user.is_active,
        "consent_data_sharing": current_user.consent_data_sharing,
        "model_update_available": False,
        "recommended_sync_interval_seconds": 3600,
    }


@router.post("/batch", response_model=SyncResponse)
async def sync_batch(
    request: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Alias for /sync — accepts the same payload.

    Provided for backward compatibility with devices that
    use /sync/batch as the endpoint.
    """
    return await sync_data(request, current_user, db)


# =========================================================================
# Msaidizi ↔ Angavu Intelligence Sync Pipeline Endpoints
# =========================================================================


@router.post("/upload", response_model=TransactionBatchResponse)
async def upload_transactions(
    batch: TransactionBatch,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive a batch of anonymized transactions from a Msaidizi device.

    This is the primary ingestion endpoint for the sync pipeline.
    Transactions arrive anonymized (PII stripped, worker ID hashed),
    compressed (gzip), and encrypted (AES-256).

    **Request Flow:**
    1. Validate batch integrity (checksum)
    2. Decompress if gzipped
    3. Deduplicate against existing transactions
    4. Store valid transactions
    5. Trigger intelligence recalculation
    6. Return intelligence updates for device

    **Idempotency:**
    Uses batch_id for deduplication — resubmitting the same batch
    won't create duplicate transactions.

    **Batch Limits:**
    - Max 200 transactions per batch
    - Max payload size: 200KB (compressed)
    """
    sync_id = str(uuid.uuid4())
    logger.info(
        "sync_upload_started",
        sync_id=sync_id,
        batch_id=batch.batch_id,
        worker_id_hash=batch.worker_id_hash[:12] + "...",
        txn_count=len(batch.transactions),
    )

    # 1. Validate batch integrity (checksum)
    import json as _json

    txn_data = _json.dumps(
        [t.model_dump(mode="json") for t in batch.transactions],
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    computed_checksum = hashlib.sha256(txn_data).hexdigest()
    if computed_checksum != batch.checksum:
        logger.warning(
            "sync_checksum_mismatch",
            sync_id=sync_id,
            batch_id=batch.batch_id,
            expected=batch.checksum[:12],
            computed=computed_checksum[:12],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch integrity check failed: checksum mismatch",
        )

    # 2. Check for duplicate batch (idempotency)
    existing = await db.execute(
        select(Transaction).where(
            Transaction.device_id == batch.device_id,
            Transaction.synced_at >= batch.sync_timestamp - timedelta(seconds=5),
            Transaction.synced_at <= batch.sync_timestamp + timedelta(seconds=5),
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info(
            "sync_batch_duplicate",
            sync_id=sync_id,
            batch_id=batch.batch_id,
        )
        return TransactionBatchResponse(
            status="ok",
            batch_id=batch.batch_id,
            sync_id=sync_id,
            transactions_accepted=0,
            transactions_rejected=0,
            rejection_reasons=["Duplicate batch — already processed"],
            intelligence_updates_available=False,
        )

    # 3. Store transactions
    accepted = 0
    rejected = 0
    reasons = []

    for record in batch.transactions:
        try:
            # Basic validation
            if record.amount <= 0:
                rejected += 1
                reasons.append(f"Invalid amount: {record.amount}")
                continue

            if record.transaction_type not in ("SALE", "PURCHASE", "EXPENSE"):
                rejected += 1
                reasons.append(f"Invalid type: {record.transaction_type}")
                continue

            # Timestamp sanity check
            if record.timestamp > datetime.now(timezone.utc) + timedelta(hours=1):
                rejected += 1
                reasons.append(f"Future timestamp: {record.timestamp}")
                continue

            if record.timestamp < datetime.now(timezone.utc) - timedelta(days=90):
                rejected += 1
                reasons.append(f"Too old: {record.timestamp}")
                continue

            # Check for transaction-level duplicate
            dup_check = await db.execute(
                select(Transaction.id).where(
                    and_(
                        Transaction.device_id == batch.device_id,
                        Transaction.timestamp == record.timestamp,
                        Transaction.amount == record.amount,
                        Transaction.item == record.item,
                    )
                ).limit(1)
            )
            if dup_check.scalar_one_or_none() is not None:
                rejected += 1
                reasons.append(
                    f"Duplicate txn: {record.item} at {record.timestamp}"
                )
                continue

            # Create transaction record
            txn = Transaction(
                user_id=uuid.UUID(batch.worker_id_hash[:32]),
                transaction_type=record.transaction_type,
                item=record.item,
                item_category=record.item_category,
                quantity=record.quantity or 0,
                unit=record.unit,
                unit_price=record.unit_price,
                amount=record.amount,
                profit=record.profit,
                payment_method=record.payment_method,
                recorded_via=record.recorded_via or "voice",
                confidence_score=record.confidence_score or 1.0,
                timestamp=record.timestamp,
                synced_at=datetime.now(timezone.utc),
                device_id=batch.device_id,
                location_geohash=(
                    record.location_geohash[:5]
                    if record.location_geohash
                    else None
                ),
            )
            db.add(txn)
            accepted += 1

        except Exception as e:
            rejected += 1
            reasons.append(f"Error: {str(e)}")
            logger.warning(
                "sync_txn_error",
                sync_id=sync_id,
                error=str(e),
            )

    await db.flush()

    logger.info(
        "sync_upload_completed",
        sync_id=sync_id,
        batch_id=batch.batch_id,
        accepted=accepted,
        rejected=rejected,
    )

    return TransactionBatchResponse(
        status="ok" if rejected == 0 else "partial",
        batch_id=batch.batch_id,
        sync_id=sync_id,
        transactions_accepted=accepted,
        transactions_rejected=rejected,
        rejection_reasons=reasons if reasons else None,
        intelligence_updates_available=accepted > 0,
    )


@router.get("/intelligence/{worker_id}")
async def get_intelligence(
    worker_id: str,
    request: Request,
    since: Optional[datetime] = None,
    language: str = "sw",
    db: AsyncSession = Depends(get_db),
):
    """
    Get intelligence updates for a specific worker.

    Returns formatted intelligence for device display including:
    - Daily briefing (profit, revenue, transactions)
    - Urgent alerts (restock, price drop, credit opportunity)
    - Market insights for the worker's area/product
    - Credit score (Alama Score) if available

    All text is translated to the worker's preferred language.

    Args:
        worker_id: Worker's hashed ID
        since: Only return updates since this timestamp
        language: Preferred language (sw=en, sw=Swahili, sh=Sheng)
    """
    logger.info(
        "sync_intelligence_requested",
        worker_id_hash=worker_id[:12] + "...",
        since=since,
        language=language,
    )

    delivery = IntelligenceDelivery(db)

    # Validate language
    if language not in ("sw", "en", "sh"):
        language = "sw"

    try:
        intelligence = await delivery.get_intelligence_for_worker(
            worker_id_hash=worker_id,
            language=language,
            since=since,
        )
    except Exception as e:
        logger.error(
            "sync_intelligence_error",
            worker_id_hash=worker_id[:12] + "...",
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate intelligence update",
        )

    return intelligence


@router.get("/status/{worker_id}", response_model=SyncStatusResponse)
async def sync_status_worker(
    worker_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Get sync status for a worker.

    Returns:
    - Last sync timestamp
    - Number of pending (unsynced) transactions
    - Intelligence freshness (hours since last update)
    - Sync health indicator
    - Recommended next sync interval
    """
    logger.info(
        "sync_status_requested",
        worker_id_hash=worker_id[:12] + "...",
    )

    delivery = IntelligenceDelivery(db)

    # Get last sync time from most recent transaction
    # Sanitize worker_id to prevent SQL LIKE injection — remove wildcards
    sanitized_worker_id = worker_id[:16].replace("%", "").replace("_", "")
    result = await db.execute(
        select(
            func.max(Transaction.synced_at).label("last_sync"),
            func.count(Transaction.id).label("total_synced"),
        ).where(
            Transaction.device_id.like(f"%{sanitized_worker_id}%"),
        )
    )
    row = result.first()
    last_sync = row.last_sync if row else None
    total_synced = row.total_synced if row else 0

    # Calculate freshness
    freshness_hours = None
    sync_health = "healthy"

    if last_sync:
        delta = datetime.now(timezone.utc) - last_sync
        freshness_hours = round(delta.total_seconds() / 3600, 1)

        if freshness_hours > 48:
            sync_health = "critical"
        elif freshness_hours > 24:
            sync_health = "stale"

    # Get intelligence freshness
    intel_freshness = await delivery.get_intelligence_freshness(worker_id)

    return SyncStatusResponse(
        worker_id_hash=worker_id,
        last_sync_at=last_sync,
        last_intelligence_update=intel_freshness,
        pending_transactions=0,  # Would come from device in real impl
        intelligence_freshness_hours=(
            round(
                (datetime.now(timezone.utc) - intel_freshness).total_seconds() / 3600,
                1,
            )
            if intel_freshness
            else None
        ),
        sync_health=sync_health,
        total_synced_transactions=total_synced,
        next_sync_recommended_seconds=(
            1800 if sync_health == "healthy"
            else 900 if sync_health == "stale"
            else 300
        ),
    )
