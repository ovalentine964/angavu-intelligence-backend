"""
User model — represents a dukawallah, mama mboga, or other informal worker.

Users are the data producers in the Msaidizi ecosystem. They record
transactions via voice, text, or automatic M-Pesa integration, and
receive business insights in return.

Privacy: Phone numbers and names are stored encrypted. Location is
stored as geohash-5 (≈5km²) only — never exact GPS coordinates.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    """
    Informal worker using Msaidizi.

    Attributes:
        id: UUID primary key
        phone_hash: SHA-256 hash of phone number (for lookups without decryption)
        phone_encrypted: AES-256 encrypted phone number
        name_encrypted: AES-256 encrypted name
        business_type: Type of business (dukawallah, mama_mboga, boda_boda, vendor, tailor, other)
        location_geohash: Geohash-5 of business location (~5km² precision)
        location_name: Human-readable location name (e.g., "Gikomba Market")
        language: Preferred language (sw=Swahili, en=English, sh=Sheng)
        channel: Primary communication channel
        is_active: Whether the user is currently active
        last_sync_at: Timestamp of last successful data sync
        device_id: Unique device identifier
        app_version: Current app version
        consent_data_sharing: Whether user consented to anonymized data sharing
        created_at: Account creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique user identifier",
    )
    phone_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        doc="SHA-256 hash of phone number for secure lookups",
    )
    phone_encrypted = Column(
        Text,
        nullable=False,
        doc="AES-256 encrypted phone number",
    )
    name_encrypted = Column(
        Text,
        nullable=True,
        doc="AES-256 encrypted user name",
    )
    business_type = Column(
        Enum(
            "dukawallah", "mama_mboga", "boda_boda", "vendor",
            "tailor", "restaurant", "other",
            name="business_type_enum",
        ),
        nullable=False,
        default="dukawallah",
        doc="Type of informal business",
    )
    location_geohash = Column(
        String(12),
        nullable=True,
        index=True,
        doc="Geohash-5 of business location (~5km²)",
    )
    location_name = Column(
        String(200),
        nullable=True,
        doc="Human-readable location (e.g., Gikomba Market, Korogocho)",
    )
    language = Column(
        Enum("sw", "en", "sh", name="language_enum"),
        nullable=False,
        default="sw",
        doc="Preferred language: sw=Swahili, en=English, sh=Sheng",
    )
    channel = Column(
        Enum("whatsapp", "telegram", "sms", "ussd", "app", name="channel_enum"),
        nullable=False,
        default="whatsapp",
        doc="Primary communication channel",
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether user account is active",
    )
    last_sync_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last successful data sync",
    )
    device_id = Column(
        String(100),
        unique=True,
        nullable=True,
        doc="Unique device identifier (UUID from Android)",
    )
    app_version = Column(
        String(20),
        nullable=True,
        doc="Current Msaidizi app version",
    )
    consent_data_sharing = Column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether user explicitly consented to anonymized data sharing",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    transactions = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    inventory_items = relationship(
        "Inventory",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("idx_user_location_active", "location_geohash", "is_active"),
        Index("idx_user_business_type", "business_type", "is_active"),
        Index("idx_user_channel", "channel", "is_active"),
        Index("idx_user_sync", "last_sync_at"),
    )

    def __repr__(self) -> str:
        return f"<User {self.id} type={self.business_type} loc={self.location_name}>"

    @property
    def is_eligible_for_intelligence(self) -> bool:
        """Check if user data can be included in intelligence products."""
        return self.is_active and self.consent_data_sharing
