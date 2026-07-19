"""
Sync request/response schemas.

These schemas define the data contract between the on-device Msaidizi app
and the cloud backend. The device sends compressed, encrypted payloads
that get decompressed, decrypted, validated, and stored.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class TransactionRecord(BaseModel):
    """A single transaction record from the device."""

    transaction_type: str = Field(
        ...,
        description="SALE, PURCHASE, or EXPENSE",
        pattern=r"^(SALE|PURCHASE|EXPENSE)$",
        alias="type",
    )
    item: str | None = Field(None, max_length=200)
    item_category: str | None = Field(None, max_length=50, alias="category")
    quantity: float | None = Field(None, ge=0)
    unit: str | None = Field(None, max_length=20)
    unit_price: float | None = Field(None, ge=0)
    amount: float = Field(..., ge=0, description="Total amount in KES", alias="total_amount")
    profit: float | None = None
    payment_method: str | None = Field(
        None,
        pattern=r"^(mpesa|cash|credit|bank|other)$",
    )
    customer_phone_hash: str | None = Field(None, max_length=64)
    mpesa_receipt: str | None = Field(None, max_length=50)
    recorded_via: str | None = Field(
        "manual",
        pattern=r"^(text|voice|mpesa_auto|ussd|manual)$",
    )
    confidence_score: float | None = Field(1.0, ge=0, le=1)
    source_text: str | None = None
    timestamp: datetime = Field(..., alias="occurred_at")
    location_geohash: str | None = Field(None, max_length=12)

    model_config = {"populate_by_name": True}


class InventoryRecord(BaseModel):
    """An inventory update from the device."""

    item: str = Field(..., max_length=200)
    category: str | None = Field(None, max_length=50)
    current_stock: float = Field(..., ge=0)
    unit: str | None = Field(None, max_length=20)
    avg_cost: float | None = Field(None, ge=0)
    sell_price: float | None = Field(None, ge=0)
    restock_threshold: float | None = Field(None, ge=0)


class DeviceMetadata(BaseModel):
    """Metadata about the syncing device."""

    app_version: str = Field(..., max_length=20)
    android_api: int | None = None
    battery_pct: int | None = Field(None, ge=0, le=100)
    network_type: str | None = Field(
        None,
        pattern=r"^(wifi|mobile_2g|mobile_3g|mobile_4g|mobile_5g|offline)$",
    )
    storage_free_mb: int | None = None
    location_geohash: str | None = Field(None, max_length=12)


class SyncPayload(BaseModel):
    """
    The data payload inside a sync request.

    Contains batches of transactions and inventory updates.
    Max 200 records per sync to keep payloads under 200KB.
    """

    transactions: list[TransactionRecord] = Field(
        default_factory=list,
        max_length=200,
        description="Batch of transaction records",
    )
    inventory_updates: list[InventoryRecord] = Field(
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
    device_metadata: DeviceMetadata | None = None
    is_compressed: bool = Field(
        False,
        description="Whether the payload is zstd compressed",
    )
    compression_level: int | None = Field(None, ge=1, le=22)


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
    rejection_reasons: list[str] | None = None
    model_update_available: bool = Field(
        False,
        description="Whether new on-device model is available for download",
    )
    model_update_url: str | None = None
    next_sync_recommended_seconds: int = Field(
        3600,
        description="Recommended seconds until next sync",
    )
    server_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Current server time for clock sync",
    )


# =========================================================================
# Msaidizi ↔ Angavu Intelligence Sync Pipeline Schemas
# =========================================================================


class AnonymizedTransaction(BaseModel):
    """
    Transaction with PII stripped for sync.

    KEEP: type, category, amount, timestamp, worker_type, dialect, coarse_location
    REMOVE: customer_name, exact_location, personal_notes
    HASH: worker_id (one-way hash for privacy)
    """

    transaction_type: str = Field(..., alias="type")
    item: str | None = None
    item_category: str | None = Field(None, alias="category")
    amount: float = Field(..., alias="total_amount")
    timestamp: datetime = Field(..., alias="occurred_at")
    worker_type: str | None = None
    location_geohash: str | None = Field(
        None,
        description="Coarsened to geohash-5 (~5km²)",
    )
    worker_id_hash: str = Field(
        ...,
        description="HMAC-SHA256 hashed worker ID (one-way)",
    )
    recorded_via: str | None = None
    confidence_score: float | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    profit: float | None = None
    payment_method: str | None = None
    dialect: str | None = Field(
        None,
        description="Language dialect detected from voice input",
    )

    model_config = {"populate_by_name": True}


class TransactionBatch(BaseModel):
    """
    Batch of anonymized transactions from Msaidizi device.

    Sent as gzipped, encrypted payload. Checksum ensures integrity.
    """

    worker_id_hash: str = Field(
        ...,
        max_length=64,
        description="HMAC-SHA256 of worker ID",
    )
    device_id: str = Field(
        ...,
        max_length=100,
        description="Unique device identifier",
    )
    batch_id: str = Field(
        ...,
        max_length=64,
        description="Unique batch ID for idempotency",
    )
    transactions: list[AnonymizedTransaction] = Field(
        ...,
        max_length=200,
        description="Batch of anonymized transactions",
    )
    checksum: str = Field(
        ...,
        max_length=64,
        description="SHA-256 checksum of serialized transactions for integrity",
    )
    is_compressed: bool = Field(
        True,
        description="Whether the batch is gzip compressed",
    )
    sync_timestamp: datetime = Field(
        ...,
        description="When the device created this batch",
    )
    device_metadata: DeviceMetadata | None = None

    @field_validator("transactions")
    @classmethod
    def validate_batch_size(cls, v):
        if len(v) > 200:
            raise ValueError("Maximum 200 transactions per batch")
        return v


class TransactionBatchResponse(BaseModel):
    """
    Response after receiving a transaction batch.
    """

    status: str = Field("ok", description="ok | error | partial")
    batch_id: str
    sync_id: str = Field(..., description="Unique sync operation ID")
    transactions_accepted: int = 0
    transactions_rejected: int = 0
    rejection_reasons: list[str] | None = None
    intelligence_updates_available: bool = Field(
        False,
        description="Whether new intelligence is available for this worker",
    )
    next_sync_recommended_seconds: int = 3600
    server_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class AlertItem(BaseModel):
    """An urgent alert for a worker."""

    alert_type: str = Field(
        ...,
        description="restock | price_drop | credit_opportunity | demand_spike | seasonal_tip",
    )
    severity: str = Field(
        ...,
        description="critical | warning | info",
    )
    title: str
    message: str
    action_label: str | None = Field(
        None,
        description="Suggested action button text",
    )
    action_payload: dict | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    expires_at: datetime | None = None


class DailyBriefing(BaseModel):
    """Daily business briefing for a worker."""

    worker_id_hash: str
    date: str = Field(..., description="YYYY-MM-DD")
    language: str = Field("sw", description="sw | en | sh")
    summary: str = Field(..., description="One-line summary in local language")
    profit_today: float | None = Field(
        None,
        description="Today's profit in KES",
    )
    revenue_today: float | None = None
    transactions_today: int | None = None
    top_item: str | None = Field(
        None,
        description="Best-selling item today",
    )
    alerts: list[AlertItem] = Field(default_factory=list)
    recommendations: list[str] = Field(
        default_factory=list,
        description="Actionable recommendations in local language",
    )
    market_trend: str | None = Field(
        None,
        description="Brief market trend note",
    )


class IntelligenceUpdate(BaseModel):
    """
    Intelligence update formatted for device display.
    """

    worker_id_hash: str
    language: str = "sw"
    briefing: DailyBriefing | None = None
    alerts: list[AlertItem] = Field(default_factory=list)
    alama_score: int | None = Field(
        None,
        description="Credit score 300-850, if available",
    )
    alama_score_band: str | None = None
    market_insights: dict | None = Field(
        None,
        description="Relevant market intelligence for worker's area/product",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class SyncStatusResponse(BaseModel):
    """
    Sync status for a worker — tracks last sync, pending data, freshness.
    """

    worker_id_hash: str
    last_sync_at: datetime | None = None
    last_intelligence_update: datetime | None = None
    pending_transactions: int = Field(
        0,
        description="Number of transactions awaiting sync",
    )
    intelligence_freshness_hours: float | None = Field(
        None,
        description="Hours since last intelligence update",
    )
    sync_health: str = Field(
        "healthy",
        description="healthy | stale | critical",
    )
    total_synced_transactions: int = 0
    next_sync_recommended_seconds: int = 3600
    server_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
