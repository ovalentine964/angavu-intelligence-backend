"""User and auth models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User model — identity is anonymized via phone_hash."""
    __tablename__ = "users"

    external_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")


class Transaction(Base, UUIDPrimaryKeyMixin):
    """Financial transaction — core data for intelligence."""
    __tablename__ = "transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KES")
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(50))
    merchant_category: Mapped[str | None] = mapped_column(String(50))
    region: Mapped[str | None] = mapped_column(String(100), index=True)
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    channel: Mapped[str | None] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketSignal(Base, UUIDPrimaryKeyMixin):
    """Aggregated market signal for intelligence products."""
    __tablename__ = "market_signals"

    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[float] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    sample_size: Mapped[int] = mapped_column(nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditScore(Base, UUIDPrimaryKeyMixin):
    """Alama Score — credit scoring 300-850."""
    __tablename__ = "credit_scores"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    score: Mapped[int] = mapped_column(nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    factors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntelligenceReport(Base, UUIDPrimaryKeyMixin):
    """Published intelligence report with vector embedding."""
    __tablename__ = "intelligence_reports"

    report_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), index=True)
    sector: Mapped[str | None] = mapped_column(String(50), index=True)
    confidence: Mapped[float] = mapped_column(nullable=False)
    data_points: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail."""
    __tablename__ = "audit_log"

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class SyncState(Base, UUIDPrimaryKeyMixin):
    """Device sync tracking for federated learning."""
    __tablename__ = "sync_state"

    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sync_cursor: Mapped[str | None] = mapped_column(String(256))
    schema_version: Mapped[int] = mapped_column(nullable=False, default=1)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")


class MLModel(Base, UUIDPrimaryKeyMixin):
    """Model registry for ML artifacts."""
    __tablename__ = "ml_models"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="staging")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
