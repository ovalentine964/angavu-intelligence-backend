"""
Intelligence product report models for the 6 cloud intelligence products.

Each model stores pre-computed reports that are sold to institutional buyers.
Reports enforce k-anonymity (k≥10) and are generated from anonymized transaction data.

Products:
1. Soko Pulse — FMCG demand forecasting
2. Angavu Pulse — Government MSME Activity Index
3. Alama Score — Bank credit scoring (300-850)
4. Jamii Insights — NGO financial inclusion
5. Tax Base Estimation — Government revenue
6. Distribution Gap Analysis — FMCG market coverage
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from app.db.database import Base

# =========================================================================
# 1. Soko Pulse — FMCG Demand Forecasting
# =========================================================================


class SokoPulseReport(Base):
    """
    FMCG demand forecasting report.

    Provides real-time demand patterns from informal markets:
    what sells, where, when, and seasonal trends.

    Buyers: FMCG companies (Unilever, Coca-Cola, P&G, EABL, etc.)
    """

    __tablename__ = "soko_pulse_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_category = Column(
        String(100), nullable=False, index=True,
        doc="Product category (food, household, beverages, etc.)",
    )
    product_name = Column(
        String(200), nullable=True, default="all",
        doc="Specific product or 'all' for category-level",
    )
    region = Column(String(100), nullable=False, index=True)
    market_ids = Column(
        JSON, nullable=True,
        doc="List of market geohashes covered",
    )
    time_period = Column(String(20), nullable=False, doc="e.g., '2026-W26', '2026-06'")
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Demand metrics
    total_volume = Column(Float, nullable=True, doc="Total units sold in period")
    avg_daily_volume = Column(Float, nullable=True)
    forecast_next_period = Column(Float, nullable=True, doc="Forecasted volume")
    forecast_confidence = Column(Float, nullable=True, doc="Forecast confidence 0-1")
    demand_trend = Column(
        Enum("rising", "stable", "declining", name="demand_trend_enum"),
        nullable=True,
    )
    seasonal_factor = Column(Float, nullable=True, doc="Seasonal multiplier")

    # Price intelligence
    avg_price = Column(Float, nullable=True)
    price_min = Column(Float, nullable=True)
    price_max = Column(Float, nullable=True)
    price_trend = Column(
        Enum("rising", "stable", "declining", name="price_trend_enum"),
        nullable=True,
    )

    # Temporal patterns
    day_of_week_pattern = Column(JSON, nullable=True, doc="DOW demand index")
    monthly_trend = Column(JSON, nullable=True, doc="Month-over-month data")
    peak_demand_days = Column(JSON, nullable=True, doc="High-demand day list")

    # Supply signals
    vendor_count = Column(Integer, nullable=True)
    stockout_frequency = Column(Float, nullable=True, doc="Stockout rate 0-1")

    # Data quality
    users_included = Column(Integer, nullable=True)
    k_anonymity_value = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)
    data_points = Column(Integer, nullable=True)

    # Pricing
    tier = Column(
        Enum("standard", "premium", "enterprise", name="soko_tier_enum"),
        nullable=False, default="standard",
    )
    price_charged_kes = Column(Float, nullable=True, default=0)

    # Metadata
    status = Column(
        Enum("pending", "processing", "ready", "delivered", "expired",
             name="soko_status_enum"),
        nullable=False, default="pending", index=True,
    )
    methodology = Column(JSON, nullable=True, doc="Forecast methodology info")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_soko_region_period", "region", "time_period"),
        Index("idx_soko_product_region", "product_category", "region"),
        Index("idx_soko_created", "created_at"),
    )


# =========================================================================
# 2. Angavu Pulse — Government MSME Activity Index
# =========================================================================


class BiasharaPulseReport(Base):
    """
    Government MSME Activity Index report.

    Economic activity heatmaps by county/sub-county with
    business formation/destruction rates.

    Buyers: Government (KNBS, CBK, county governments)
    """

    __tablename__ = "biashara_pulse_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    region = Column(String(100), nullable=False, index=True)
    region_type = Column(
        Enum("ward", "sub_county", "county", "national",
             name="bp_region_type_enum"),
        nullable=False,
    )
    county_code = Column(String(10), nullable=True, index=True)
    time_period = Column(String(20), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Activity indices (0-100)
    activity_index = Column(Float, nullable=True, doc="Overall MSME activity 0-100")
    growth_index = Column(Float, nullable=True, doc="Growth rate index")
    formalization_index = Column(Float, nullable=True, doc="Business formalization rate")

    # Business formation/destruction
    estimated_businesses = Column(Integer, nullable=True)
    active_businesses = Column(Integer, nullable=True)
    new_businesses_est = Column(Integer, nullable=True, doc="Estimated new businesses")
    closed_businesses_est = Column(Integer, nullable=True, doc="Estimated closures")
    net_business_change = Column(Integer, nullable=True)

    # Economic metrics
    total_transactions = Column(Integer, nullable=True)
    total_volume_kes = Column(Float, nullable=True)
    avg_transaction_value = Column(Float, nullable=True)
    avg_daily_revenue_per_business = Column(Float, nullable=True)

    # Sector breakdown
    sector_breakdown = Column(JSON, nullable=True, doc="Sector share percentages")
    top_sectors = Column(JSON, nullable=True, doc="Top 5 sectors by activity")

    # Infrastructure signals
    mpesa_penetration_pct = Column(Float, nullable=True)
    digital_payment_adoption = Column(Float, nullable=True)
    avg_operating_hours = Column(Float, nullable=True)
    avg_operating_days_per_week = Column(Float, nullable=True)

    # Comparisons
    vs_previous_period_pct = Column(Float, nullable=True)
    vs_national_avg_pct = Column(Float, nullable=True)
    county_rank = Column(Integer, nullable=True, doc="Rank among all counties")

    # Employment estimates
    estimated_employment = Column(Integer, nullable=True)
    employment_per_business = Column(Float, nullable=True)

    # Data quality
    users_included = Column(Integer, nullable=True)
    k_anonymity_value = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)

    # Metadata
    status = Column(
        Enum("pending", "processing", "ready", "delivered", "expired",
             name="bp_status_enum"),
        nullable=False, default="pending", index=True,
    )
    price_charged_kes = Column(Float, nullable=True, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_bp_region_period", "region", "time_period"),
        Index("idx_bp_county", "county_code", "time_period"),
        Index("idx_bp_created", "created_at"),
    )


# =========================================================================
# 3. Alama Score — Bank Credit Scoring (300-850)
# =========================================================================


class AlamaScore(Base):
    """
    Transaction-based credit scoring for informal businesses.

    Score range: 300-850 (standard credit score range).
    Uses Heckman correction for selection bias.

    Buyers: Banks, microfinance, fintech
    """

    __tablename__ = "alama_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    business_hash = Column(
        String(64), nullable=False, index=True,
        doc="Anonymized business identifier (HMAC-SHA256)",
    )
    business_type = Column(String(50), nullable=True)
    market_id = Column(String(20), nullable=True, index=True)
    region = Column(String(100), nullable=True)

    # Core score
    alama_score = Column(
        Integer, nullable=False,
        doc="Credit score 300-850",
    )
    score_band = Column(
        String(20), nullable=True,
        doc="excellent/good/fair/poor/very_poor",
    )
    percentile = Column(Float, nullable=True, doc="Percentile rank among peers")

    # Score components (each 0-100)
    activity_score = Column(Float, nullable=True, doc="Business activity level")
    stability_score = Column(Float, nullable=True, doc="Revenue stability")
    growth_score = Column(Float, nullable=True, doc="Growth trajectory")
    consistency_score = Column(Float, nullable=True, doc="Operating consistency")
    diversity_score = Column(Float, nullable=True, doc="Product/customer diversity")

    # Business signals
    avg_daily_revenue_kes = Column(Float, nullable=True)
    avg_daily_transactions = Column(Float, nullable=True)
    operating_days_per_week = Column(Float, nullable=True)
    revenue_volatility = Column(Float, nullable=True, doc="CV of daily revenue")
    growth_trajectory = Column(
        Enum("growing", "stable", "declining", name="alama_trajectory_enum"),
        nullable=True,
    )

    # Heckman correction
    heckman_lambda = Column(Float, nullable=True, doc="Inverse Mills ratio")
    selection_corrected = Column(Boolean, default=False)
    correction_method = Column(String(50), nullable=True)

    # Risk indicators
    category_risk = Column(
        Enum("low", "medium", "high", name="alama_risk_enum"),
        nullable=True,
    )
    default_probability = Column(Float, nullable=True, doc="Estimated PD 0-1")
    recommended_credit_limit_kes = Column(Float, nullable=True)

    # Peer comparison
    vs_market_avg = Column(JSON, nullable=True, doc="Comparison to market averages")
    peer_rank_pct = Column(Float, nullable=True, doc="Percentile among peers")

    # Data quality
    data_points = Column(Integer, nullable=True)
    data_period_days = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True, doc="Confidence 0-1")
    users_in_cohort = Column(Integer, nullable=True)
    k_anonymity_value = Column(Integer, nullable=True)

    # Pricing
    query_tier = Column(
        Enum("basic", "enhanced", "full", name="alama_query_tier_enum"),
        nullable=False, default="basic",
    )
    price_charged_kes = Column(Float, nullable=True, default=0)

    # Metadata
    status = Column(
        Enum("pending", "processing", "ready", "delivered", "expired",
             name="alama_status_enum"),
        nullable=False, default="pending", index=True,
    )
    computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("alama_score >= 300 AND alama_score <= 850",
                        name="ck_alama_score_range"),
        Index("idx_alama_business", "business_hash", "created_at"),
        Index("idx_alama_market", "market_id", "alama_score"),
        Index("idx_alama_region", "region", "created_at"),
    )


# =========================================================================
# 4. Jamii Insights — NGO Financial Inclusion
# =========================================================================


class JamiiInsightsReport(Base):
    """
    Financial inclusion metrics for NGO/development buyers.

    Provides demographic-level financial inclusion data
    and impact measurement for development programs.

    Buyers: NGOs, development organizations (World Bank, USAID, DFID, etc.)
    """

    __tablename__ = "jamii_insights_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    region = Column(String(100), nullable=False, index=True)
    county_code = Column(String(10), nullable=True, index=True)
    demographic_segment = Column(
        String(50), nullable=True,
        doc="youth, women, rural, urban, etc.",
    )
    time_period = Column(String(20), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Financial inclusion metrics
    financial_inclusion_index = Column(
        Float, nullable=True,
        doc="Composite inclusion score 0-100",
    )
    digital_payment_adoption = Column(Float, nullable=True, doc="% using digital payments")
    savings_behavior_score = Column(Float, nullable=True, doc="0-100")
    credit_access_score = Column(Float, nullable=True, doc="0-100")
    insurance_coverage_pct = Column(Float, nullable=True)

    # Business formalization
    business_registration_pct = Column(Float, nullable=True)
    tax_compliance_pct = Column(Float, nullable=True)
    formal_banking_pct = Column(Float, nullable=True)

    # Demographics
    youth_owned_pct = Column(Float, nullable=True, doc="% businesses owned by <35")
    women_owned_pct = Column(Float, nullable=True)
    avg_owner_age = Column(Float, nullable=True)

    # Economic impact
    avg_monthly_income_kes = Column(Float, nullable=True)
    income_growth_pct = Column(Float, nullable=True)
    employment_created = Column(Integer, nullable=True)
    livelihoods_supported = Column(Integer, nullable=True)

    # Program impact (for evaluation)
    program_name = Column(String(200), nullable=True)
    beneficiary_count = Column(Integer, nullable=True)
    pre_program_index = Column(Float, nullable=True)
    post_program_index = Column(Float, nullable=True)
    impact_delta = Column(Float, nullable=True)
    cost_per_beneficiary_kes = Column(Float, nullable=True)

    # Barriers to inclusion
    top_barriers = Column(JSON, nullable=True, doc="Ranked list of barriers")
    barrier_severity = Column(JSON, nullable=True, doc="Severity scores per barrier")

    # Data quality
    sample_size = Column(Integer, nullable=True)
    k_anonymity_value = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)
    methodology = Column(Text, nullable=True)

    # Metadata
    status = Column(
        Enum("pending", "processing", "ready", "delivered", "expired",
             name="jamii_status_enum"),
        nullable=False, default="pending", index=True,
    )
    price_charged_kes = Column(Float, nullable=True, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_jamii_region_period", "region", "time_period"),
        Index("idx_jamii_county", "county_code", "time_period"),
        Index("idx_jamii_demographic", "demographic_segment", "region"),
        Index("idx_jamii_created", "created_at"),
    )


# =========================================================================
# 5. Tax Base Estimation — Government Revenue
# =========================================================================


class TaxBaseEstimation(Base):
    """
    Estimated tax liability for informal businesses.

    Estimates VAT collection potential by sector/region
    to help government revenue authorities.

    Buyers: KRA, county governments
    """

    __tablename__ = "tax_base_estimations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    region = Column(String(100), nullable=False, index=True)
    region_type = Column(
        Enum("ward", "sub_county", "county", "national",
             name="tax_region_type_enum"),
        nullable=False,
    )
    county_code = Column(String(10), nullable=True, index=True)
    sector = Column(String(100), nullable=True, index=True, doc="Economic sector")
    time_period = Column(String(20), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Business estimates
    estimated_businesses = Column(Integer, nullable=True)
    active_businesses = Column(Integer, nullable=True)
    formalized_businesses = Column(Integer, nullable=True)
    formalization_gap_pct = Column(Float, nullable=True)

    # Revenue estimates
    estimated_total_revenue_kes = Column(Float, nullable=True)
    estimated_vat_base_kes = Column(Float, nullable=True, doc="VAT-liable revenue")
    estimated_vat_collectible_kes = Column(Float, nullable=True)
    estimated_income_tax_base_kes = Column(Float, nullable=True)

    # Tax potential
    vat_effective_rate = Column(Float, nullable=True, doc="Effective VAT collection rate")
    tax_gap_kes = Column(Float, nullable=True, doc="Difference between potential and actual")
    tax_compliance_rate = Column(Float, nullable=True)
    revenue_per_capita_kes = Column(Float, nullable=True)

    # Sector breakdown
    sector_breakdown = Column(
        JSON, nullable=True,
        doc="Per-sector revenue and tax estimates",
    )
    top_tax_contributors = Column(JSON, nullable=True)

    # Growth metrics
    revenue_growth_pct = Column(Float, nullable=True)
    tax_base_growth_pct = Column(Float, nullable=True)
    new_registrations_est = Column(Integer, nullable=True)

    # Comparisons
    vs_previous_period_pct = Column(Float, nullable=True)
    county_rank = Column(Integer, nullable=True)
    collection_efficiency_rank = Column(Integer, nullable=True)

    # Data quality
    users_included = Column(Integer, nullable=True)
    k_anonymity_value = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)
    confidence_interval = Column(JSON, nullable=True, doc="[lower, upper] bounds")

    # Metadata
    status = Column(
        Enum("pending", "processing", "ready", "delivered", "expired",
             name="tax_status_enum"),
        nullable=False, default="pending", index=True,
    )
    price_charged_kes = Column(Float, nullable=True, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_tax_region_period", "region", "time_period"),
        Index("idx_tax_county_sector", "county_code", "sector"),
        Index("idx_tax_created", "created_at"),
    )


# =========================================================================
# 6. Distribution Gap Analysis — FMCG Market Coverage
# =========================================================================


class DistributionGapReport(Base):
    """
    Market coverage gap analysis for FMCG distribution.

    Identifies where products are NOT reaching and
    underserved market opportunities.

    Buyers: FMCG distribution companies
    """

    __tablename__ = "distribution_gap_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("buyers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    product_category = Column(String(100), nullable=False, index=True)
    product_name = Column(String(200), nullable=True, default="all")
    region = Column(String(100), nullable=False, index=True)
    county_code = Column(String(10), nullable=True, index=True)
    time_period = Column(String(20), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Coverage metrics
    total_markets_surveyed = Column(Integer, nullable=True)
    markets_with_product = Column(Integer, nullable=True)
    markets_without_product = Column(Integer, nullable=True)
    coverage_pct = Column(Float, nullable=True, doc="% markets with product available")
    penetration_rate = Column(Float, nullable=True, doc="% of potential customers reached")

    # Gap identification
    gap_markets = Column(
        JSON, nullable=True,
        doc="List of markets without product coverage",
    )
    gap_market_population = Column(Integer, nullable=True, doc="Total pop in gap markets")
    gap_revenue_potential_kes = Column(Float, nullable=True, doc="Estimated lost revenue")
    priority_gaps = Column(
        JSON, nullable=True,
        doc="Ranked gap markets by opportunity size",
    )

    # Underserved segments
    underserved_regions = Column(JSON, nullable=True)
    underserved_demographics = Column(JSON, nullable=True)
    demand_without_supply = Column(
        Float, nullable=True,
        doc="Demand index in gap markets",
    )

    # Competitive landscape
    competitor_presence = Column(JSON, nullable=True, doc="Competitor coverage by market")
    competitive_gap_pct = Column(Float, nullable=True)
    market_share_estimate = Column(Float, nullable=True)

    # Distribution efficiency
    avg_distribution_cost_per_unit = Column(Float, nullable=True)
    optimal_route_suggestions = Column(JSON, nullable=True)
    distribution_density = Column(Float, nullable=True, doc="Units per market")

    # Recommendations
    recommended_expansion_markets = Column(JSON, nullable=True)
    estimated_roi_pct = Column(Float, nullable=True)
    investment_required_kes = Column(Float, nullable=True)

    # Data quality
    users_included = Column(Integer, nullable=True)
    k_anonymity_value = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True)

    # Metadata
    status = Column(
        Enum("pending", "processing", "ready", "delivered", "expired",
             name="dist_gap_status_enum"),
        nullable=False, default="pending", index=True,
    )
    price_charged_kes = Column(Float, nullable=True, default=0)
    report_type = Column(
        Enum("one_time", "monitoring", name="dist_gap_report_type_enum"),
        nullable=False, default="one_time",
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_distgap_region_period", "region", "time_period"),
        Index("idx_distgap_product_region", "product_category", "region"),
        Index("idx_distgap_created", "created_at"),
    )


# =========================================================================
# 7. Alama Score — Outcome Tracking for Calibration
# =========================================================================


class AlamaScoreOutcome(Base):
    """
    Tracks actual credit outcomes (repayment/default) for Alama Score calibration.

    This implements the feedback loop:
    1. Score predicts default probability
    2. Loan is issued
    3. Outcome is observed
    4. Outcome updates Bayesian priors
    5. Updated priors improve future scoring

    Academic Foundation:
    - STA 341 (Theory of Estimation): Bayesian updating
    - STA 346 (Quality Control): Calibration monitoring
    - ECO 209 (Money and Banking): Credit risk validation
    """

    __tablename__ = "alama_score_outcomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_hash = Column(String(128), nullable=False, index=True)
    outcome_type = Column(
        Enum("repayment", "default", name="alama_outcome_enum"),
        nullable=False,
    )
    amount = Column(Float, nullable=True)
    predicted_default_prob = Column(Float, nullable=True)
    alama_score_at_issue = Column(Integer, nullable=True)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_alama_outcome_business", "business_hash"),
        Index("idx_alama_outcome_type", "outcome_type"),
        Index("idx_alama_outcome_recorded", "recorded_at"),
    )
