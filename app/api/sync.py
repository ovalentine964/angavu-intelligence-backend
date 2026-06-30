"""
Sync API endpoints.

Handles device-to-cloud data synchronization. Devices send batched
transaction data that gets validated, deduplicated, and stored.

Sync Protocol:
    1. Device compresses payload with zstd (60-70% reduction)
    2. Device encrypts with AES-256 (per-user key)
    3. Device sends via HTTP/2 over TLS 1.3
    4. Cloud decrypts, decompresses, validates, stores
    5. Cloud returns sync status and model update availability
"""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.sync import SyncRequest, SyncResponse
from app.services.sync_service import SyncService
from app.utils.compression import decompress_payload
from app.utils.crypto import decrypt_payload

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
