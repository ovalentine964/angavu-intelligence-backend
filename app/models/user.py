"""
Worker/User model — privacy-preserving design.

Architecture: arch_backend.md §1.2
- Phone stored encrypted (AES-256-GCM)
- Location stored as geohash-5 (no GPS coordinates)
- worker_id_hash is the primary external identifier
"""
import uuid
from datetime import datetime, UTC

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, JSON, Index
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    """Worker/User — the core entity. All intelligence is derived from aggregated user data."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    worker_id_hash = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone_encrypted = Column(Text, nullable=True)  # AES-256-GCM encrypted
    phone_hash = Column(String(64), nullable=True, index=True)  # For lookups without decrypting
    language = Column(String(10), default="sw")
    business_type = Column(String(50), default="unknown")
    business_description = Column(Text, nullable=True)
    location_geohash = Column(String(10), nullable=True, index=True)  # geohash-5
    device_id_hash = Column(String(64), nullable=True)
    consent_data_sharing = Column(Boolean, default=False)
    consent_fl_participation = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    vector_clock = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    transactions = relationship("Transaction", back_populates="user")
    inventory = relationship("Inventory", back_populates="user")

    __table_args__ = (
        Index("idx_user_geohash_active", "location_geohash", "is_active"),
    )


class OTPCode(Base):
    """One-time password for worker authentication."""
    __tablename__ = "otp_codes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_hash = Column(String(64), nullable=False, index=True)
    code_hash = Column(String(128), nullable=False)
    purpose = Column(String(20), default="login")  # login | register
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
