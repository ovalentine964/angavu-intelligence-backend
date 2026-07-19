"""
Pydantic schemas for the 6 intelligence products.

Request/response models for buyer-facing API endpoints.
All schemas enforce k-anonymity constraints in documentation.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

# =========================================================================
# Common / Shared Schemas
# =========================================================================


class ProductTierConfig(BaseModel):
    """Pricing tier configuration for an intelligence product."""

    tier: str
    price_monthly_kes: float
    price_monthly_usd: float
    features: list[str]
    refresh_frequency: str
    markets_included: int | None = None
    api_queries_per_month: int | None = None


class PaginationParams(BaseModel):
    """Pagination parameters."""

    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class IntelligenceResponse(BaseModel):
    """Base response wrapper for intelligence products."""

    product: str
    version: str = "1.0"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    data_freshness: datetime
    k_anonymity_threshold: int = 10
    quality_score: float = Field(..., ge=0, le=1)
    confidence_level: float = Field(..., ge=0, le=1)
    disclaimer: str = (
        "All data is anonymized and aggregated. k-anonymity (k≥10) enforced. "
        "No individual business data is exposed."
    )


# =========================================================================
# 1. Soko Pulse — FMCG Demand Forecasting
# =========================================================================


class SokoPulseRequest(BaseModel):
    """Request for Soko Pulse demand forecasting."""

    product_category: str = Field(
        ..., description="Product category (food, household, beverages, etc.)",
    )
    product_name: str | None = Field(
        None, description="Specific product or omit for category-level",
    )
    region: str | None = Field(None, description="Geographic region")
    period_start: date | None = None
    period_end: date | None = None
    tier: str = Field("standard", pattern=r"^(standard|premium|enterprise)$")
    include_forecast: bool = Field(True, description="Include demand forecast")
    include_seasonality: bool = Field(True, description="Include seasonal analysis")


class DemandForecast(BaseModel):
    """Demand forecast for next period."""

    forecasted_volume: float
    confidence_interval_low: float
    confidence_interval_high: float
    forecast_method: str = "exponential_smoothing"
    mape: float | None = Field(None, description="Mean Absolute Percentage Error")


class PriceIntelligence(BaseModel):
    """Price intelligence data."""

    avg_price: float
    min_price: float
    max_price: float
    median_price: float
    price_trend: str = Field(..., pattern=r"^(rising|stable|declining)$")
    price_change_pct: float | None = None
    unit: str = "KES"


class SokoPulseResponse(IntelligenceResponse):
    """Response for Soko Pulse demand forecasting."""

    product = "soko_pulse"
    region: str
    product_category: str
    product_name: str = "all"
    time_period: str

    # Demand
    total_volume: float
    avg_daily_volume: float
    demand_trend: str = Field(..., pattern=r"^(rising|stable|declining)$")
    forecast: DemandForecast | None = None

    # Price
    price_intelligence: PriceIntelligence

    # Temporal patterns
    day_of_week_pattern: dict[str, float] = {}
    monthly_trend: list[dict[str, Any]] = []
    peak_demand_days: list[str] = []

    # Supply
    vendor_count: int
    stockout_frequency: float | None = None

    # Seasonality
    seasonal_factor: float | None = None
    seasonal_events: list[dict[str, Any]] = []

    # Data quality
    users_included: int
    data_points: int
    tier: str = "standard"


# =========================================================================
# 2. Angavu Pulse — Government MSME Activity Index
# =========================================================================


class BiasharaPulseRequest(BaseModel):
    """Request for Angavu Pulse MSME Activity Index."""

    region: str = Field(..., description="County code, sub-county, or 'national'")
    period_start: date | None = None
    period_end: date | None = None
    include_sector_breakdown: bool = True
    include_comparisons: bool = True
    include_employment: bool = True


class SectorActivity(BaseModel):
    """Sector-level activity data."""

    sector: str
    activity_share_pct: float
    revenue_share_pct: float
    business_count: int
    trend: str = Field(..., pattern=r"^(growing|stable|declining)$")
    growth_pct: float | None = None


class BusinessFormation(BaseModel):
    """Business formation/destruction metrics."""

    new_businesses_est: int
    closed_businesses_est: int
    net_change: int
    formation_rate: float = Field(..., description="New businesses per 1000 existing")
    survival_rate: float | None = Field(None, description="% surviving after 1 year")


class BiasharaPulseResponse(IntelligenceResponse):
    """Response for Angavu Pulse MSME Activity Index."""

    product = "biashara_pulse"
    region: str
    region_type: str
    time_period: str

    # Indices
    activity_index: float = Field(..., ge=0, le=100)
    growth_index: float = Field(..., ge=0, le=100)
    formalization_index: float | None = Field(None, ge=0, le=100)

    # Business counts
    estimated_businesses: int
    active_businesses: int
    business_formation: BusinessFormation | None = None

    # Economic metrics
    total_transactions: int
    total_volume_kes: float
    avg_transaction_value: float
    avg_daily_revenue_per_business: float

    # Sectors
    sector_breakdown: list[SectorActivity] = []
    top_sectors: list[str] = []

    # Infrastructure
    mpesa_penetration_pct: float
    digital_payment_adoption: float | None = None
    avg_operating_hours: float
    avg_operating_days_per_week: float

    # Employment
    estimated_employment: int | None = None
    employment_per_business: float | None = None

    # Comparisons
    vs_previous_period_pct: float | None = None
    vs_national_avg_pct: float | None = None
    county_rank: int | None = None

    # Data quality
    users_included: int


# =========================================================================
# 3. Alama Score — Bank Credit Scoring
# =========================================================================


class AlamaScoreRequest(BaseModel):
    """Request for Alama credit scoring."""

    business_id: str = Field(
        ..., description="Anonymized business identifier (hash)",
    )
    lookback_days: int = Field(90, ge=30, le=365)
    query_tier: str = Field(
        "basic", pattern=r"^(basic|enhanced|full)$",
        description="basic=$0.05, enhanced=$0.15, full=$0.50",
    )
    include_peer_comparison: bool = True
    include_heckman_correction: bool = True


class ScoreComponents(BaseModel):
    """Breakdown of score components."""

    activity: float = Field(..., ge=0, le=100)
    stability: float = Field(..., ge=0, le=100)
    growth: float = Field(..., ge=0, le=100)
    consistency: float = Field(..., ge=0, le=100)
    diversity: float = Field(..., ge=0, le=100)


class RiskIndicators(BaseModel):
    """Risk assessment indicators."""

    category_risk: str = Field(..., pattern=r"^(low|medium|high)$")
    default_probability: float | None = Field(None, ge=0, le=1)
    recommended_credit_limit_kes: float | None = None
    risk_factors: list[str] = []


class AlamaScoreResponse(IntelligenceResponse):
    """Response for Alama credit scoring."""

    product = "alama_score"
    business_hash: str
    business_type: str
    market_id: str | None = None
    region: str | None = None

    # Score
    alama_score: int = Field(..., ge=300, le=850)
    score_band: str = Field(
        ..., description="excellent/good/fair/poor/very_poor",
    )
    percentile: float = Field(..., ge=0, le=100)

    # Components
    components: ScoreComponents

    # Business signals
    avg_daily_revenue_kes: float
    avg_daily_transactions: float
    operating_days_per_week: float
    revenue_volatility: float
    growth_trajectory: str = Field(..., pattern=r"^(growing|stable|declining)$")

    # Heckman correction
    heckman_corrected: bool = False
    heckman_lambda: float | None = None

    # Risk
    risk_indicators: RiskIndicators

    # Peer comparison
    vs_market_avg: dict[str, float] = {}
    peer_rank_pct: float | None = None

    # Data quality
    data_points: int
    data_period_days: int
    confidence: float
    query_tier: str = "basic"


# =========================================================================
# 4. Jamii Insights — NGO Financial Inclusion
# =========================================================================


class JamiiInsightsRequest(BaseModel):
    """Request for Jamii Insights financial inclusion data."""

    region: str = Field(..., description="Region or 'national'")
    demographic_segment: str | None = Field(
        None,
        description="youth, women, rural, urban, etc.",
    )
    period_start: date | None = None
    period_end: date | None = None
    program_name: str | None = Field(
        None,
        description="Specific program for impact evaluation",
    )
    include_barriers: bool = True
    include_impact: bool = True


class InclusionMetrics(BaseModel):
    """Financial inclusion metrics."""

    financial_inclusion_index: float = Field(..., ge=0, le=100)
    digital_payment_adoption: float = Field(..., ge=0, le=100)
    savings_behavior_score: float = Field(..., ge=0, le=100)
    credit_access_score: float = Field(..., ge=0, le=100)
    insurance_coverage_pct: float = Field(..., ge=0, le=100)


class ProgramImpact(BaseModel):
    """Program impact assessment."""

    program_name: str
    beneficiary_count: int
    pre_program_index: float
    post_program_index: float
    impact_delta: float
    cost_per_beneficiary_kes: float | None = None
    statistical_significance: float | None = None


class Barrier(BaseModel):
    """Barrier to financial inclusion."""

    barrier: str
    severity: float = Field(..., ge=0, le=100)
    affected_pct: float = Field(..., ge=0, le=100)
    recommended_intervention: str | None = None


class JamiiInsightsResponse(IntelligenceResponse):
    """Response for Jamii Insights financial inclusion."""

    product = "jamii_insights"
    region: str
    demographic_segment: str | None = None
    time_period: str

    # Inclusion metrics
    inclusion_metrics: InclusionMetrics

    # Business formalization
    business_registration_pct: float
    tax_compliance_pct: float
    formal_banking_pct: float

    # Demographics
    youth_owned_pct: float | None = None
    women_owned_pct: float | None = None
    avg_owner_age: float | None = None

    # Economic impact
    avg_monthly_income_kes: float | None = None
    income_growth_pct: float | None = None
    employment_created: int | None = None
    livelihoods_supported: int | None = None

    # Program impact
    program_impact: ProgramImpact | None = None

    # Barriers
    barriers: list[Barrier] = []

    # Data quality
    sample_size: int


# =========================================================================
# 5. Tax Base Estimation — Government Revenue
# =========================================================================


class TaxBaseRequest(BaseModel):
    """Request for Tax Base Estimation."""

    region: str = Field(..., description="County code or 'national'")
    sector: str | None = Field(None, description="Specific sector or all")
    period_start: date | None = None
    period_end: date | None = None
    include_sector_breakdown: bool = True
    include_projections: bool = True


class TaxEstimates(BaseModel):
    """Tax revenue estimates."""

    estimated_total_revenue_kes: float
    estimated_vat_base_kes: float
    estimated_vat_collectible_kes: float
    estimated_income_tax_base_kes: float
    vat_effective_rate: float
    tax_gap_kes: float
    tax_compliance_rate: float


class SectorTaxBreakdown(BaseModel):
    """Per-sector tax breakdown."""

    sector: str
    estimated_revenue_kes: float
    vat_base_kes: float
    vat_collectible_kes: float
    business_count: int
    compliance_rate: float


class TaxBaseResponse(IntelligenceResponse):
    """Response for Tax Base Estimation."""

    product = "tax_base_estimation"
    region: str
    region_type: str
    sector: str | None = None
    time_period: str

    # Business estimates
    estimated_businesses: int
    active_businesses: int
    formalized_businesses: int
    formalization_gap_pct: float

    # Tax estimates
    tax_estimates: TaxEstimates

    # Sector breakdown
    sector_breakdown: list[SectorTaxBreakdown] = []
    top_tax_contributors: list[dict[str, Any]] = []

    # Growth
    revenue_growth_pct: float | None = None
    tax_base_growth_pct: float | None = None
    new_registrations_est: int | None = None

    # Comparisons
    vs_previous_period_pct: float | None = None
    county_rank: int | None = None

    # Data quality
    users_included: int
    confidence_interval: dict[str, float] | None = None


# =========================================================================
# 6. Distribution Gap Analysis — FMCG Market Coverage
# =========================================================================


class DistributionGapRequest(BaseModel):
    """Request for Distribution Gap Analysis."""

    product_category: str = Field(..., description="Product category to analyze")
    product_name: str | None = Field(None, description="Specific product")
    region: str | None = Field(None, description="Geographic region")
    period_start: date | None = None
    period_end: date | None = None
    include_competitors: bool = True
    include_recommendations: bool = True


class GapMarket(BaseModel):
    """A market with distribution gap."""

    market_id: str
    market_name: str
    region: str
    population_estimate: int | None = None
    demand_index: float = Field(..., ge=0, le=100)
    revenue_potential_kes: float
    competitor_presence: str | None = None
    priority_rank: int
    recommended_action: str | None = None


class DistributionCoverage(BaseModel):
    """Distribution coverage metrics."""

    total_markets_surveyed: int
    markets_with_product: int
    markets_without_product: int
    coverage_pct: float = Field(..., ge=0, le=100)
    penetration_rate: float = Field(..., ge=0, le=100)


class DistributionGapResponse(IntelligenceResponse):
    """Response for Distribution Gap Analysis."""

    product = "distribution_gap"
    product_category: str
    product_name: str = "all"
    region: str
    time_period: str

    # Coverage
    coverage: DistributionCoverage

    # Gaps
    gap_markets: list[GapMarket] = []
    gap_market_population: int
    gap_revenue_potential_kes: float
    demand_without_supply: float | None = None

    # Underserved
    underserved_regions: list[dict[str, Any]] = []
    underserved_demographics: list[dict[str, Any]] = []

    # Competitive
    competitor_presence: dict[str, Any] = {}
    competitive_gap_pct: float | None = None
    market_share_estimate: float | None = None

    # Distribution efficiency
    avg_distribution_cost_per_unit: float | None = None
    distribution_density: float | None = None

    # Recommendations
    recommended_expansion_markets: list[dict[str, Any]] = []
    estimated_roi_pct: float | None = None
    investment_required_kes: float | None = None

    # Data quality
    users_included: int
    report_type: str = "one_time"
