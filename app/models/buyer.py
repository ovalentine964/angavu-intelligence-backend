"""
Buyer model — represents organizations that purchase economic intelligence.

Buyers are the revenue side of Msaidizi. They include FMCG companies,
government agencies, financial institutions, and development organizations.
Each buyer gets scoped API keys and pays for intelligence products.
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.db.database import Base


class Buyer(Base):
    """
    An organization that purchases economic intelligence from Msaidizi.

    Attributes:
        id: UUID primary key
        company_name: Organization name
        buyer_type: Industry segment
        tier: Service tier (standard, premium, enterprise)
        contact_name: Primary contact person
        contact_email: Contact email
        contact_phone: Contact phone
        country: Country code (KE, UG, TZ, etc.)
        regions_authorized: Geographic regions this buyer can access
        products_subscribed: Intelligence product types subscribed
        monthly_budget_kes: Monthly spending limit
        total_spent_kes: Total amount spent to date
        is_active: Whether buyer account is active
        contract_start: When the contract started
        contract_end: When the contract ends
        metadata_extra: Additional metadata (industry, use case, etc.)
        created_at: Account creation
        updated_at: Last update
    """

    __tablename__ = "buyers"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_name = Column(
        String(200),
        nullable=False,
        doc="Organization name",
    )
    buyer_type = Column(
        Enum(
            "FMCG", "GOVT", "BANK", "MFI", "INSURANCE", "NGO",
            "RESEARCH", "SUPPLY_CHAIN", "OTHER",
            name="buyer_type_enum",
        ),
        nullable=False,
        index=True,
    )
    tier = Column(
        Enum("standard", "premium", "enterprise", name="buyer_tier_enum"),
        nullable=False,
        default="standard",
    )
    contact_name = Column(
        String(200),
        nullable=True,
    )
    contact_email = Column(
        String(200),
        nullable=True,
    )
    contact_phone = Column(
        String(20),
        nullable=True,
    )
    country = Column(
        String(5),
        nullable=False,
        default="KE",
        doc="Country code",
    )
    regions_authorized = Column(
        JSON,
        nullable=True,
        default=list,
        doc="List of authorized geographic regions (geohash prefixes or county codes)",
    )
    products_subscribed = Column(
        JSON,
        nullable=True,
        default=list,
        doc="List of subscribed intelligence product types",
    )
    monthly_budget_kes = Column(
        Float,
        nullable=True,
        doc="Monthly spending limit in KES",
    )
    total_spent_kes = Column(
        Float,
        nullable=False,
        default=0,
        doc="Total amount spent to date in KES",
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )
    contract_start = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    contract_end = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_extra = Column(
        JSON,
        nullable=True,
        doc="Additional metadata (industry, use case, etc.)",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    api_keys = relationship(
        "BuyerAPIKey",
        back_populates="buyer",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    intelligence_products = relationship(
        "IntelligenceProduct",
        back_populates=None,
        lazy="dynamic",
    )

    __table_args__ = (
        Index("idx_buyer_type_tier", "buyer_type", "tier"),
        Index("idx_buyer_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Buyer {self.company_name} type={self.buyer_type} tier={self.tier}>"

    @property
    def is_contract_active(self) -> bool:
        """Check if the buyer's contract is currently active."""
        if not self.is_active:
            return False
        now = datetime.now(timezone.utc)
        if self.contract_start and now < self.contract_start:
            return False
        if self.contract_end and now > self.contract_end:
            return False
        return True


class BuyerAPIKey(Base):
    """
    API keys for buyer authentication.

    Each buyer can have multiple API keys for different integrations.
    Keys are scoped to specific datasets and geographic regions.

    Attributes:
        id: UUID primary key
        buyer_id: Foreign key to buyer
        key_hash: SHA-256 hash of the API key
        key_prefix: First 8 chars of key for identification
        name: Human-readable key name
        scopes: List of allowed scopes
        rate_limit: Requests per minute for this key
        is_active: Whether this key is active
        last_used_at: Last time this key was used
        expires_at: When this key expires
        created_at: Key creation timestamp
    """

    __tablename__ = "buyer_api_keys"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    buyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        doc="SHA-256 hash of the API key",
    )
    key_prefix = Column(
        String(10),
        nullable=False,
        doc="First 8 chars of key for identification (msai_xxxx)",
    )
    name = Column(
        String(100),
        nullable=True,
        doc="Human-readable key name (e.g., 'Production', 'Testing')",
    )
    scopes = Column(
        JSON,
        nullable=True,
        default=list,
        doc="List of allowed scopes: ['market_data', 'demand', 'pricing', 'credit']",
    )
    rate_limit = Column(
        Integer,
        nullable=False,
        default=1000,
        doc="Requests per minute for this key",
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )
    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    buyer = relationship("Buyer", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<BuyerAPIKey {self.key_prefix}... buyer={self.buyer_id}>"

    @property
    def is_expired(self) -> bool:
        """Check if this key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @staticmethod
    def generate_key() -> tuple[str, str, str]:
        """
        Generate a new API key.

        Returns:
            Tuple of (full_key, key_hash, key_prefix)
        """
        full_key = f"msai_{secrets.token_urlsafe(32)}"
        import hashlib
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        key_prefix = full_key[:10]
        return full_key, key_hash, key_prefix
