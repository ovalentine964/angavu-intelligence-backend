"""
Alama Score — Pydantic models for lender-facing API.

Defines request/response schemas for credit score queries,
score components, risk categorization, and product recommendations.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class RiskCategory(str, Enum):
    """Risk categories for lender decision-making."""
    VERY_LOW = "very_low"      # Score 800-1000
    LOW = "low"                 # Score 650-799
    MODERATE = "moderate"       # Score 500-649
    HIGH = "high"               # Score 350-499
    VERY_HIGH = "very_high"     # Score 0-349


class ScoreBand(str, Enum):
    """Descriptive score bands."""
    EXCEPTIONAL = "exceptional"  # 900-1000
    EXCELLENT = "excellent"      # 800-899
    GOOD = "good"                # 700-799
    FAIR = "fair"                # 600-699
    POOR = "poor"                # 500-599
    VERY_POOR = "very_poor"      # 300-499
    NO_SCORE = "no_score"        # 0-299 / insufficient data


class LoanProductType(str, Enum):
    """Types of financial products for matching."""
    WORKING_CAPITAL = "working_capital"
    STOCK_FINANCING = "stock_financing"
    EQUIPMENT_LOAN = "equipment_loan"
    EMERGENCY_LOAN = "emergency_loan"
    INSURANCE = "insurance"
    INVOICE_FINANCING = "invoice_financing"
    GROUP_LOAN = "group_loan"


# ── Score Component ──────────────────────────────────────────────────────────

class ScoreComponent(BaseModel):
    """A single scoring factor with its weight and contribution."""
    name: str = Field(..., description="Factor name")
    name_sw: str = Field(..., description="Factor name in Swahili")
    weight: float = Field(..., description="Weight in composite score (0-1)")
    raw_value: float = Field(..., description="Raw metric value")
    normalized_score: float = Field(..., description="Normalized score (0-100)")
    weighted_contribution: float = Field(..., description="Contribution to final score")
    interpretation: str = Field(..., description="Human-readable interpretation")
    interpretation_sw: str = Field(..., description="Swahili interpretation")


# ── Request Models ───────────────────────────────────────────────────────────

class LenderQueryRequest(BaseModel):
    """Request from a lender to query an Alama Score."""
    business_id: str = Field(
        ...,
        description="Anonymized business hash (HMAC-SHA256 of user_id)",
    )
    lender_id: str = Field(
        ...,
        description="Registered lender institution ID",
    )
    query_tier: str = Field(
        default="standard",
        description="Query tier: basic, standard, or premium",
    )
    lookback_days: int = Field(
        default=90,
        ge=30,
        le=365,
        description="Analysis window in days",
    )
    loan_purpose: str | None = Field(
        default=None,
        description="Intended loan purpose for product matching",
    )
    requested_amount: float | None = Field(
        default=None,
        ge=0,
        description="Requested loan amount in KES for affordability check",
    )
    include_peer_comparison: bool = Field(
        default=True,
        description="Include anonymized peer cohort comparison",
    )
    include_product_match: bool = Field(
        default=True,
        description="Include recommended financial products",
    )


# ── Response Models ──────────────────────────────────────────────────────────

class AffordabilityAssessment(BaseModel):
    """Assessment of whether the business can afford a requested loan."""
    affordable: bool
    max_recommended_amount_kes: float
    monthly_repayment_capacity_kes: float
    debt_to_revenue_ratio: float
    warning: str | None = None
    warning_sw: str | None = None


class ProductRecommendation(BaseModel):
    """A recommended financial product for this business."""
    product_type: LoanProductType
    product_name: str
    product_name_sw: str
    max_amount_kes: float
    recommended_term_days: int
    estimated_interest_rate_pct: float
    match_score: float = Field(..., description="How well this product fits (0-1)")
    rationale: str
    rationale_sw: str


class PeerComparison(BaseModel):
    """Anonymized comparison against peer cohort."""
    cohort_size: int
    percentile_rank: float = Field(..., description="Percentile rank (0-100)")
    vs_cohort_avg: float = Field(..., description="Score ratio vs cohort average")
    cohort_business_type: str
    cohort_region: str
    top_strength: str
    top_weakness: str


class AlamaScoreReport(BaseModel):
    """Complete Alama Score report for a lender query."""
    # Metadata
    product: str = "alama_score_lender_api"
    version: str = "1.0"
    generated_at: datetime
    query_id: str = Field(..., description="Unique query ID for audit trail")
    business_hash: str
    lender_id: str

    # Core Score
    alama_score: int = Field(..., ge=0, le=1000, description="Credit score 0-1000")
    score_band: ScoreBand
    risk_category: RiskCategory
    confidence: float = Field(..., ge=0, le=1, description="Score confidence level")

    # Components
    components: list[ScoreComponent]
    component_summary: dict[str, float] = Field(
        ..., description="Component name → normalized score (0-100)"
    )

    # Risk Assessment
    default_probability: float = Field(..., ge=0, le=1)
    recommended_credit_limit_kes: float
    risk_factors: list[str]
    risk_factors_sw: list[str]
    positive_factors: list[str]
    positive_factors_sw: list[str]

    # Optional enrichments
    affordability: AffordabilityAssessment | None = None
    product_recommendations: list[ProductRecommendation] = []
    peer_comparison: PeerComparison | None = None

    # Data quality
    data_points: int
    data_period_days: int
    operating_days: int
    data_quality_score: float = Field(..., ge=0, le=1)


class LenderQueryResponse(BaseModel):
    """Wrapper response for lender API calls."""
    status: str = "success"
    report: AlamaScoreReport | None = None
    error: str | None = None
    error_sw: str | None = None
    rate_limit_remaining: int | None = None
    cached: bool = False
