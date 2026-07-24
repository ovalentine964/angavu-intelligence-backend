"""
Referral Commission Engine — Data models.

Defines the data structures for:
  - Financial partner profiles
  - Product matching results
  - Referral lifecycle tracking
  - Commission calculation and reporting
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class ReferralStatus(str, Enum):
    """Lifecycle stages of a referral."""
    CLICKED = "clicked"              # User clicked the referral link
    APPLIED = "applied"              # User submitted application
    APPROVED = "approved"            # Partner approved the application
    DISBURSED = "disbursed"          # Loan/product activated
    REJECTED = "rejected"            # Application rejected
    EXPIRED = "expired"              # Referral link expired
    DEFAULTED = "defaulted"          # Loan defaulted (for clawback)


class CommissionType(str, Enum):
    """Types of commission structures."""
    PERCENTAGE_OF_AMOUNT = "percentage_of_amount"  # % of loan/financed amount
    PERCENTAGE_OF_PREMIUM = "percentage_of_premium"  # % of insurance premium
    FLAT_FEE = "flat_fee"            # Fixed amount per activation
    TIERED = "tiered"                # Varies by volume
    RECURRING = "recurring"          # Ongoing % of repayments


class CommissionStatus(str, Enum):
    """Status of a commission payment."""
    PENDING = "pending"              # Referral completed, commission pending
    APPROVED = "approved"            # Commission approved for payment
    PAID = "paid"                    # Commission paid out
    CLAWED_BACK = "clawed_back"      # Deducted due to default/cancellation
    DISPUTED = "disputed"            # Under review


class ProductCategory(str, Enum):
    """Categories of financial products."""
    LOAN = "loan"
    INSURANCE = "insurance"
    SAVINGS = "savings"
    EQUIPMENT_FINANCING = "equipment_financing"
    INVOICE_FINANCING = "invoice_financing"
    GROUP_LENDING = "group_lending"


# ── Financial Partner ────────────────────────────────────────────────────────

class FinancialPartner(BaseModel):
    """A financial institution that offers products through the platform."""
    partner_id: str = Field(..., description="Unique partner identifier")
    name: str = Field(..., description="Partner institution name")
    name_sw: str = Field(..., description="Partner name in Swahili")
    product_category: ProductCategory
    products: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of products offered by this partner",
    )
    commission_structure: dict[str, Any] = Field(
        ...,
        description="Commission rates and rules",
    )
    min_score_requirement: int = Field(
        default=0,
        ge=0,
        le=1000,
        description="Minimum Alama Score to refer",
    )
    supported_worker_types: list[str] = Field(
        default_factory=lambda: ["all"],
        description="Worker types this partner serves",
    )
    supported_regions: list[str] = Field(
        default_factory=lambda: ["all"],
        description="Regions this partner operates in",
    )
    is_active: bool = True
    api_endpoint: str | None = None
    api_key_ref: str | None = None


# ── Product Match ────────────────────────────────────────────────────────────

class ProductMatch(BaseModel):
    """A financial product matched to a worker's profile."""
    partner_id: str
    partner_name: str
    product_id: str
    product_name: str
    product_name_sw: str
    product_category: ProductCategory
    match_score: float = Field(..., ge=0, le=1, description="How well this product fits")
    match_reasons: list[str] = Field(default_factory=list)
    match_reasons_sw: list[str] = Field(default_factory=list)
    max_amount_kes: float | None = None
    estimated_rate_pct: float | None = None
    term_days: int | None = None
    commission_type: CommissionType
    commission_rate: float = Field(..., description="Commission rate (percentage or flat amount)")
    commission_amount_estimate: float = Field(
        default=0,
        description="Estimated commission if referred successfully",
    )
    referral_link: str | None = None
    referral_code: str | None = None
    eligibility_met: bool = True
    ineligibility_reasons: list[str] = Field(default_factory=list)


# ── Referral ─────────────────────────────────────────────────────────────────

class Referral(BaseModel):
    """A tracked referral from a worker to a financial product."""
    referral_id: str = Field(..., description="Unique referral tracking ID")
    user_id: str = Field(..., description="Worker who was referred")
    user_hash: str = Field(..., description="Anonymized user hash")
    partner_id: str
    product_id: str
    product_name: str
    product_category: ProductCategory
    status: ReferralStatus = ReferralStatus.CLICKED
    referral_code: str
    referral_link: str
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None = None
    approved_at: datetime | None = None
    disbursed_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    amount_applied: float | None = None
    amount_approved: float | None = None
    amount_disbursed: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Commission ───────────────────────────────────────────────────────────────

class Commission(BaseModel):
    """A commission earned from a successful referral."""
    commission_id: str = Field(..., description="Unique commission ID")
    referral_id: str = Field(..., description="Associated referral ID")
    partner_id: str
    user_id: str
    user_hash: str
    product_category: ProductCategory
    commission_type: CommissionType
    commission_rate: float
    base_amount: float = Field(..., description="Amount on which commission is calculated")
    commission_amount: float = Field(..., description="Actual commission earned")
    currency: str = "KES"
    status: CommissionStatus = CommissionStatus.PENDING
    created_at: datetime
    approved_at: datetime | None = None
    paid_at: datetime | None = None
    clawed_back_at: datetime | None = None
    clawback_reason: str | None = None
    settlement_period: str | None = Field(
        default=None,
        description="Settlement period (e.g., '2026-07')",
    )


# ── Reports ──────────────────────────────────────────────────────────────────

class CommissionReport(BaseModel):
    """Summary report of commissions for a period."""
    period: str = Field(..., description="Report period (e.g., '2026-07')")
    total_referrals: int
    successful_referrals: int
    conversion_rate: float
    total_commission_earned: float
    total_commission_paid: float
    total_commission_pending: float
    total_commission_clawed_back: float
    by_partner: list[dict[str, Any]]
    by_product_category: list[dict[str, Any]]
    by_status: dict[str, float]
    generated_at: datetime


class ReferralSummary(BaseModel):
    """Summary of referral activity for a user or period."""
    total_clicks: int
    total_applications: int
    total_approvals: int
    total_disbursals: int
    total_rejections: int
    conversion_rate: float
    total_commission_earned: float
    top_product: str | None = None
    top_partner: str | None = None
