"""
Sync request/response schemas.

These schemas define the data contract between the on-device Msaidizi app
and the cloud backend. The device sends compressed, encrypted payloads
that get decompressed, decrypted, validated, and stored.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class TransactionRecord(BaseModel):
    """A single transaction record from the device."""

    transaction_type: str = Field(
        ...,
        description="SALE, PURCHASE, or EXPENSE",
        pattern=r"^(SALE|PURCHASE|EXPENSE)$",
    )
    item: Optional[str] = Field(None, max_length=200)
    item_category: Optional[str] = Field(None, max_length=50)
    quantity: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    unit_price: Optional[float] = Field(None, ge=0)
    amount: float = Field(..., ge=0, description="Total amount in KES")
    profit: Optional[float] = None
    payment_method: Optional[str] = Field(
        None,
        pattern=r"^(mpesa|cash|credit|bank|other)$",
    )
    customer_phone_hash: Optional[str] = Field(None, max_length=64)
    mpesa_receipt: Optional[str] = Field(None, max_length=50)
    recorded_via: Optional[str] = Field(
        "manual",
        pattern=r"^(text|voice|mpesa_auto|ussd|manual)$",
    )
    confidence_score: Optional[float] = Field(1.0, ge=0, le=1)
    source_text: Optional[str] = None
    timestamp: datetime
    location_geohash: Optional[str] = Field(None, max_length=12)


class InventoryRecord(BaseModel):
    """An inventory update from the device."""

    item: str = Field(..., max_length=200)
    category: Optional[str] = Field(None, max_length=50)
    current_stock: float = Field(..., ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    avg_cost: Optional[float] = Field(None, ge=0)
    sell_price: Optional[float] = Field(None, ge=0)
    restock_threshold: Optional[float] = Field(None, ge=0)


class DeviceMetadata(BaseModel):
    """Metadata about the syncing device."""

    app_version: str = Field(..., max_length=20)
    android_api: Optional[int] = None
    battery_pct: Optional[int] = Field(None, ge=0, le=100)
    network_type: Optional[str] = Field(
        None,
        pattern=r"^(wifi|mobile_2g|mobile_3g|mobile_4g|mobile_5g|offline)$",
    )
    storage_free_mb: Optional[int] = None
    location_geohash: Optional[str] = Field(None, max_length=12)


class SyncPayload(BaseModel):
    """
    The data payload inside a sync request.

    Contains batches of transactions and inventory updates.
    Max 200 records per sync to keep payloads under 200KB.
    """

    transactions: List[TransactionRecord] = Field(
        default_factory=list,
        max_length=200,
        description="Batch of transaction records",
    )
    inventory_updates: List[InventoryRecord] = Field(
        default_factory=list,
        max_length=100,
        description="Inventory level updates",
    )

    @field_validator("transactions")
    @classmethod
    def validate_batch_size(cls, v):
        """Ensure batch doesn't exceed max size."""
        if len(v) > 200:
            raise ValueError("Maximum 200 transactions per sync batch")
        return v


class SyncRequest(BaseModel):
    """
    Complete sync request from a device.

    The payload field contains the raw (possibly compressed) data.
    The device_id and sync_timestamp are required for idempotency.
    """

    device_id: str = Field(
        ...,
        max_length=100,
        description="Unique device identifier",
    )
    user_id: str = Field(
        ...,
        description="User UUID",
    )
    sync_timestamp: datetime = Field(
        ...,
        description="When the device initiated this sync",
    )
    sync_offset: int = Field(
        0,
        ge=0,
        description="Offset for resumable syncs",
    )
    payload: SyncPayload
    device_metadata: Optional[DeviceMetadata] = None
    is_compressed: bool = Field(
        False,
        description="Whether the payload is zstd compressed",
    )
    compression_level: Optional[int] = Field(None, ge=1, le=22)


class SyncResponse(BaseModel):
    """
    Response after successful sync.

    Tells the device what happened and if there are updates available.
    """

    status: str = "ok"
    sync_id: str = Field(..., description="Unique sync operation ID")
    transactions_received: int = 0
    transactions_accepted: int = 0
    transactions_rejected: int = 0
    inventory_updates_received: int = 0
    inventory_updates_accepted: int = 0
    rejection_reasons: Optional[List[str]] = None
    model_update_available: bool = Field(
        False,
        description="Whether new on-device model is available for download",
    )
    model_update_url: Optional[str] = None
    next_sync_recommended_seconds: int = Field(
        3600,
        description="Recommended seconds until next sync",
    )
    server_time: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="Current server time for clock sync",
    )
