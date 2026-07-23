"""
Federated Learning models — gradient updates, global models, rounds.

Architecture: arch_backend.md §2.4, §4.3
"""
import uuid
from datetime import datetime, UTC

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, JSON, LargeBinary, Float, Index
)

from app.db.database import Base


class FLUpdate(Base):
    """Gradient update submitted by a device."""
    __tablename__ = "fl_updates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id_hash = Column(String(64), nullable=False, index=True)
    dialect = Column(String(20), nullable=False, index=True)
    calibration_params = Column(JSON, nullable=True)
    correction_patterns = Column(JSON, nullable=True)
    adapter_deltas = Column(LargeBinary, nullable=True)
    sample_count = Column(Integer, default=1)
    privacy_epsilon = Column(Float, default=0.1)
    metadata_ = Column("metadata", JSON, default=dict)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_fl_update_dialect_processed", "dialect", "processed"),
    )


class FLGlobalModel(Base):
    """Aggregated global model for a dialect."""
    __tablename__ = "fl_global_models"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dialect = Column(String(20), nullable=False, index=True)
    version = Column(String(50), nullable=False, unique=True)
    calibration_params = Column(JSON, nullable=True)
    vocabulary_updates = Column(JSON, nullable=True)
    adapter_deltas = Column(LargeBinary, nullable=True)
    updates_included = Column(Integer, default=0)
    dp_epsilon = Column(Float, default=0.1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class FLRound(Base):
    """FL aggregation round metadata."""
    __tablename__ = "fl_rounds"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dialect = Column(String(20), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    clients_participated = Column(Integer, default=0)
    clients_failed = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)  # 0-1
    status = Column(String(20), default="completed")  # pending | aggregating | completed | failed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
