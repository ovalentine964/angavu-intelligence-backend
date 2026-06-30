"""
Sync service — handles device-to-cloud data synchronization.

This is the entry point for all field data. Devices send compressed,
encrypted payloads that get decompressed, decrypted, validated,
deduplicated, and stored.

Key responsibilities:
- Accept batched transaction data from devices
- Handle idempotent syncs (retry-safe)
- Validate data quality
- Update inventory levels
- Track sync status per device
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Inventory, Transaction
from app.models.user import User
from app.schemas.sync import (
    SyncRequest,
    SyncResponse,
    TransactionRecord,
    InventoryRecord,
)

logger = structlog.get_logger(__name__)


class SyncService:
    """
    Handles device-to-cloud data synchronization.

    The sync flow:
    1. Device sends SyncRequest with batched transactions
    2. Service validates the request and user
    3. Transactions are deduplicated (by timestamp + amount + item)
    4. Valid transactions are stored
    5. Inventory is updated
    6. Response tells device what happened
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_sync(self, request: SyncRequest) -> SyncResponse:
        """
        Process a sync request from a device.

        Args:
            request: The validated sync request from the device

        Returns:
            SyncResponse with status and details of what was processed
        """
        sync_id = str(uuid.uuid4())
        logger.info(
            "sync_started",
            sync_id=sync_id,
            device_id=request.device_id,
            user_id=str(request.user_id),
            txn_count=len(request.payload.transactions),
            inv_count=len(request.payload.inventory_updates),
        )

        # Verify user exists and is active
        user = await self._get_user(request.user_id)
        if not user:
            logger.warning("sync_user_not_found", user_id=request.user_id)
            return SyncResponse(
                status="error",
                sync_id=sync_id,
                rejection_reasons=["User not found or inactive"],
            )

        # Update user's last sync timestamp and device info
        user.last_sync_at = datetime.now(timezone.utc)
        user.device_id = request.device_id
        if request.device_metadata:
            user.app_version = request.device_metadata.app_version

        # Process transactions
        accepted, rejected, reasons = await self._process_transactions(
            user_id=user.id,
            transactions=request.payload.transactions,
            device_id=request.device_id,
            location_geohash=(
                request.device_metadata.location_geohash
                if request.device_metadata
                else None
            ),
        )

        # Process inventory updates
        inv_accepted = await self._process_inventory(
            user_id=user.id,
            updates=request.payload.inventory_updates,
        )

        logger.info(
            "sync_completed",
            sync_id=sync_id,
            accepted=accepted,
            rejected=rejected,
            inv_accepted=inv_accepted,
        )

        return SyncResponse(
            status="ok",
            sync_id=sync_id,
            transactions_received=len(request.payload.transactions),
            transactions_accepted=accepted,
            transactions_rejected=rejected,
            inventory_updates_received=len(request.payload.inventory_updates),
            inventory_updates_accepted=inv_accepted,
            rejection_reasons=reasons if reasons else None,
            model_update_available=False,
            next_sync_recommended_seconds=self._calculate_next_sync(
                request.device_metadata
            ),
        )

    async def _get_user(self, user_id: str) -> Optional[User]:
        """Fetch active user by ID."""
        try:
            result = await self.db.execute(
                select(User).where(
                    and_(User.id == user_id, User.is_active == True)
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("user_lookup_failed", error=str(e))
            return None

    async def _process_transactions(
        self,
        user_id,
        transactions: List[TransactionRecord],
        device_id: str,
        location_geohash: Optional[str],
    ) -> Tuple[int, int, List[str]]:
        """
        Process a batch of transactions.

        Returns:
            Tuple of (accepted_count, rejected_count, rejection_reasons)
        """
        accepted = 0
        rejected = 0
        reasons = []

        for record in transactions:
            try:
                # Check for duplicates (same user + timestamp + amount + item)
                is_dup = await self._is_duplicate(
                    user_id=user_id,
                    timestamp=record.timestamp,
                    amount=record.amount,
                    item=record.item,
                )
                if is_dup:
                    rejected += 1
                    reasons.append(f"Duplicate: {record.item} at {record.timestamp}")
                    continue

                # Validate transaction data
                validation_error = self._validate_transaction(record)
                if validation_error:
                    rejected += 1
                    reasons.append(f"Invalid: {validation_error}")
                    continue

                # Create transaction record
                txn = Transaction(
                    user_id=user_id,
                    transaction_type=record.transaction_type,
                    item=record.item,
                    item_category=record.item_category,
                    quantity=record.quantity or 0,
                    unit=record.unit,
                    unit_price=record.unit_price,
                    amount=record.amount,
                    profit=record.profit,
                    payment_method=record.payment_method,
                    customer_phone_hash=record.customer_phone_hash,
                    mpesa_receipt=record.mpesa_receipt,
                    recorded_via=record.recorded_via or "manual",
                    confidence_score=record.confidence_score or 1.0,
                    source_text=record.source_text,
                    timestamp=record.timestamp,
                    synced_at=datetime.now(timezone.utc),
                    device_id=device_id,
                    location_geohash=location_geohash or record.location_geohash,
                )
                self.db.add(txn)
                accepted += 1

            except Exception as e:
                rejected += 1
                reasons.append(f"Error processing {record.item}: {str(e)}")
                logger.warning("transaction_processing_error", error=str(e))

        return accepted, rejected, reasons

    async def _is_duplicate(
        self,
        user_id,
        timestamp: datetime,
        amount: float,
        item: Optional[str],
    ) -> bool:
        """
        Check if this transaction already exists (deduplication).

        Uses a combination of user_id + timestamp + amount + item
        to detect duplicates from retry syncs.
        """
        result = await self.db.execute(
            select(Transaction.id).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.timestamp == timestamp,
                    Transaction.amount == amount,
                    Transaction.item == item,
                )
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    def _validate_transaction(self, record: TransactionRecord) -> Optional[str]:
        """
        Validate a transaction record.

        Returns:
            Error message if invalid, None if valid.
        """
        # Amount must be positive
        if record.amount <= 0:
            return "Amount must be positive"

        # Transaction type must be valid
        if record.transaction_type not in ("SALE", "PURCHASE", "EXPENSE"):
            return f"Invalid transaction type: {record.transaction_type}"

        # Timestamp can't be in the future
        if record.timestamp > datetime.now(timezone.utc):
            return "Timestamp is in the future"

        # Timestamp can't be more than 90 days old
        from datetime import timedelta
        if record.timestamp < datetime.now(timezone.utc) - timedelta(days=90):
            return "Timestamp is more than 90 days old"

        # Quantity should be non-negative
        if record.quantity is not None and record.quantity < 0:
            return "Quantity cannot be negative"

        return None

    async def _process_inventory(
        self,
        user_id,
        updates: List[InventoryRecord],
    ) -> int:
        """
        Process inventory updates from the device.

        Upserts inventory records — creates new items or updates
        existing ones.
        """
        accepted = 0

        for record in updates:
            try:
                # Try to find existing inventory item
                result = await self.db.execute(
                    select(Inventory).where(
                        and_(
                            Inventory.user_id == user_id,
                            Inventory.item == record.item,
                        )
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing inventory
                    existing.current_stock = record.current_stock
                    existing.category = record.category or existing.category
                    existing.unit = record.unit or existing.unit
                    existing.avg_cost = record.avg_cost or existing.avg_cost
                    existing.sell_price = record.sell_price or existing.sell_price
                    existing.restock_threshold = (
                        record.restock_threshold or existing.restock_threshold
                    )
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new inventory item
                    inv = Inventory(
                        user_id=user_id,
                        item=record.item,
                        category=record.category,
                        current_stock=record.current_stock,
                        unit=record.unit,
                        avg_cost=record.avg_cost,
                        sell_price=record.sell_price,
                        restock_threshold=record.restock_threshold or 0,
                    )
                    self.db.add(inv)

                accepted += 1

            except Exception as e:
                logger.warning(
                    "inventory_update_error",
                    item=record.item,
                    error=str(e),
                )

        return accepted

    def _calculate_next_sync(self, metadata) -> int:
        """
        Calculate recommended seconds until next sync.

        Based on network type and battery level:
        - WiFi + charging: sync in 30 minutes
        - WiFi only: sync in 1 hour
        - Mobile data: sync in 2 hours
        - Low battery: sync in 4 hours
        """
        if not metadata:
            return 3600

        # Low battery — delay sync
        if metadata.battery_pct is not None and metadata.battery_pct < 20:
            return 14400  # 4 hours

        # WiFi — more frequent syncs
        if metadata.network_type == "wifi":
            return 1800  # 30 minutes

        # Mobile data
        if metadata.network_type and metadata.network_type.startswith("mobile"):
            return 7200  # 2 hours

        return 3600  # 1 hour default
