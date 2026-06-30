"""
Intelligence API schemas.

These define the response structures for buyer-facing intelligence endpoints.
All data is anonymized and aggregated with k-anonymity (k≥10) enforced.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnonymizedMetric(BaseModel):
    """A single anonymized metric with confidence interval."""

    metric_name: str
    value: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    sample_size: int = Field(
        ...,
        description="Number of users contributing to this metric",
    )
    k_anonymity: int = Field(
        ...,
        ge=10,
        description="k-anonymity value (always >= 10)",
    )
    quality_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Data quality score",
    )


class MarketIntelligence(BaseModel):
    """
    Market-level economic intelligence.

    Represents aggregated data for a specific geographic market
    (ward, market, or geohash-5 area).
    """

    market_id: str = Field(..., description="Geohash-5 or ward code")
    market_name: str
    region: str
    county: Optional[str] = None

    # Time period
    period_start: date
    period_end: date

    # Activity metrics
    active_businesses: int = Field(
        ...,
        description="Number of active businesses in this market",
    )
    total_transactions: int = 0
    total_revenue_kes: float = 0

    # Averages (anonymized)
    avg_daily_revenue: AnonymizedMetric
    avg_transaction_value: AnonymizedMetric
    avg_transactions_per_day: AnonymizedMetric
    avg_operating_hours: AnonymizedMetric

    # Product mix
    top_categories: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top product categories by volume",
    )

    # Trends
    revenue_trend_pct: Optional[float] = None
    transaction_volume_trend_pct: Optional[float] = None

    # Payment methods
    mpesa_share_pct: float = 0
    cash_share_pct: float = 0

    # Metadata
    data_freshness: datetime = Field(
        ...,
        description="When this intelligence was last computed",
    )
    confidence_level: float = Field(
        ...,
        ge=0,
        le=1,
        description="Overall confidence in the data",
    )


class DemandPattern(BaseModel):
    """
    Demand patterns for a specific product or category.

    Shows how demand varies over time and geography,
    useful for FMCG distribution planning.
    """

    product: str
    product_category: Optional[str] = None

    # Geographic scope
    region: str
    market_ids: List[str] = Field(default_factory=list)

    # Time period
    period_start: date
    period_end: date

    # Demand metrics
    total_volume: AnonymizedMetric
    avg_daily_volume: AnonymizedMetric
    price_range: Dict[str, float] = Field(
        default_factory=dict,
        description="{'min': 80, 'max': 120, 'median': 95, 'unit': 'KES/kg'}",
    )

    # Temporal patterns
    day_of_week_pattern: Dict[str, float] = Field(
        default_factory=dict,
        description="{'mon': 0.85, 'tue': 0.92, ...} relative to average",
    )
    monthly_trend: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="[{'month': '2026-06', 'volume': 15000, 'change_pct': 5.2}]",
    )

    # Seasonality
    seasonal_factors: Dict[str, float] = Field(
        default_factory=dict,
        description="{'ramadan': 1.3, 'school_term': 1.1, 'harvest': 0.8}",
    )

    # Supply signals
    vendor_count: AnonymizedMetric
    avg_stock_days: Optional[AnonymizedMetric] = None

    # Metadata
    data_freshness: datetime
    confidence_level: float


class EconomicActivity(BaseModel):
    """
    Regional economic activity intelligence.

    Aggregated economic activity metrics for a geographic region,
    suitable for government dashboards and infrastructure planning.
    """

    region: str
    region_type: str = Field(
        ...,
        description="ward, sub_county, county, national",
    )
    county: Optional[str] = None

    # Time period
    period_start: date
    period_end: date

    # Activity indices (0-100 scale)
    activity_index: AnonymizedMetric = Field(
        ...,
        description="Overall economic activity index (0-100)",
    )
    growth_index: AnonymizedMetric = Field(
        ...,
        description="Growth rate index compared to previous period",
    )

    # Business metrics
    estimated_businesses: int = 0
    active_businesses: int = 0
    new_businesses_est: int = Field(
        0,
        description="Estimated new businesses in period",
    )

    # Transaction metrics
    total_transactions: int = 0
    total_volume_kes: float = 0
    avg_transaction_value: AnonymizedMetric

    # Sector breakdown
    sector_breakdown: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="[{'sector': 'food', 'share_pct': 45, 'trend': 'up'}]",
    )

    # Infrastructure signals
    mpesa_penetration_pct: float = Field(
        0,
        description="Percentage of transactions via M-Pesa",
    )
    avg_operating_hours: float = 0

    # Comparison
    vs_previous_period_pct: Optional[float] = None
    vs_national_avg_pct: Optional[float] = None

    # Metadata
    data_freshness: datetime
    confidence_level: float
    users_contributing: int = Field(
        ...,
        ge=10,
        description="Number of users whose data contributed (always >= 10)",
    )


class CreditSignal(BaseModel):
    """
    Credit scoring signal for a business.

    Provides anonymized business health indicators that financial
    institutions can use for credit decisions.
    """

    # Identity (anonymized)
    business_hash: str = Field(
        ...,
        description="Anonymized business identifier",
    )
    market_id: str
    business_type: str

    # Scoring
    activity_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Business activity score (0-100)",
    )
    stability_index: float = Field(
        ...,
        ge=0,
        le=1,
        description="Revenue stability (0=volatile, 1=very stable)",
    )
    growth_trajectory: str = Field(
        ...,
        description="growing, stable, declining",
        pattern=r"^(growing|stable|declining)$",
    )

    # Activity signals
    avg_daily_transactions: float = 0
    avg_daily_revenue_kes: float = 0
    operating_days_per_week: float = 0
    avg_operating_hours: float = 0

    # Business health
    revenue_consistency: float = Field(
        ...,
        ge=0,
        le=1,
        description="How consistent revenue is (coefficient of variation inverse)",
    )
    category_risk: str = Field(
        "medium",
        description="low, medium, high — based on business category stability",
    )

    # Peer comparison
    vs_market_avg: Dict[str, float] = Field(
        default_factory=dict,
        description="How this business compares to market averages",
    )

    # Data quality
    data_points: int = Field(
        ...,
        description="Number of data points used for scoring",
    )
    data_period_days: int = 90
    confidence: float = Field(..., ge=0, le=1)


class BuyerQueryParams(BaseModel):
    """Common query parameters for intelligence endpoints."""

    market_id: Optional[str] = None
    region: Optional[str] = None
    product: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    granularity: Optional[str] = Field(
        None,
        pattern=r"^(daily|weekly|monthly|quarterly)$",
    )
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


# =========================================================================
# Heckman Selection Correction Schemas
# =========================================================================

class HeckmanCorrectionRequest(BaseModel):
    """Request for Heckman-corrected credit scores."""

    market_id: Optional[str] = Field(
        None, description="Geographic market filter"
    )
    lookback_days: int = Field(
        90, ge=30, le=365,
        description="Analysis window in days",
    )
    include_diagnostics: bool = Field(
        False,
        description="Include model diagnostics in response",
    )
    confidence_level: float = Field(
        0.95, ge=0.80, le=0.99,
        description="Confidence level for intervals",
    )


class CorrectedScoreResponse(BaseModel):
    """A single bias-corrected credit score."""

    business_hash: str = Field(
        ..., description="Anonymized business identifier"
    )
    raw_score: float = Field(
        ..., description="Score from naive (potentially biased) model"
    )
    corrected_score: float = Field(
        ..., description="Score after Heckman selection correction"
    )
    bias_adjustment: float = Field(
        ..., description="Difference: corrected - raw (positive = underestimated)"
    )
    confidence_interval: Dict[str, float] = Field(
        ..., description="{lower, upper} 95% CI for corrected score"
    )
    selection_probability: float = Field(
        ..., description="Estimated P(approval) from selection equation"
    )
    mills_ratio_contribution: float = Field(
        ..., description="Inverse Mills ratio contribution to this prediction"
    )
    risk_category: str = Field(
        ..., description="Risk classification: very_low, low, medium, high, very_high"
    )
    correction_applied: bool = Field(
        ..., description="Whether Heckman correction was statistically significant"
    )


class HeckmanDiagnosticsResponse(BaseModel):
    """Diagnostics for the Heckman selection model."""

    selection_equation: Dict[str, Any] = Field(
        ..., description="Probit selection equation parameters"
    )
    outcome_equation: Dict[str, Any] = Field(
        ..., description="Corrected outcome equation parameters"
    )
    correction_summary: Dict[str, Any] = Field(
        ..., description="Selection bias correction diagnostics"
    )
    sample_info: Dict[str, Any] = Field(
        ..., description="Sample composition details"
    )
    confidence_intervals: Optional[Dict[str, Any]] = Field(
        None, description="Parameter confidence intervals"
    )


class HeckmanCorrectionResponse(BaseModel):
    """Response containing Heckman-corrected credit scores."""

    scores: List[CorrectedScoreResponse]
    diagnostics: Optional[HeckmanDiagnosticsResponse] = None
    processing_time_ms: float
    correction_method: str = "heckman_two_step"


# =========================================================================
# CUSUM Drift Detection Schemas
# =========================================================================

class DriftAlertResponse(BaseModel):
    """A drift detection alert."""

    timestamp: str = Field(..., description="ISO timestamp of alert")
    direction: str = Field(
        ..., description="Drift direction: degradation or improvement"
    )
    severity: str = Field(
        ..., description="Alert severity: info, warning, critical"
    )
    cusum_value: float = Field(..., description="CUSUM statistic at detection")
    threshold: float = Field(..., description="Threshold that was breached")
    drift_magnitude_sigma: float = Field(
        ..., description="Drift magnitude in standard deviation units"
    )
    metric_name: str
    metric_value: float
    baseline_value: float
    samples_since_last_alert: int
    recommendation: str


class MetricStatusResponse(BaseModel):
    """Status of a single monitored metric."""

    metric_name: str
    status: str = Field(
        ..., description="stable, warning, drift_detected, retraining_required"
    )
    observations: int
    alerts_total: int
    samples_since_last_alert: int
    cusum_upper: float
    cusum_lower: float
    threshold: float
    baseline: Dict[str, Any]
    recent_performance: Dict[str, Any]
    drift_detected: bool
    last_alert: Optional[DriftAlertResponse] = None


class DriftStatusResponse(BaseModel):
    """Overall drift monitoring status."""

    overall_status: str = Field(
        ..., description="stable, warning, drift_detected"
    )
    metrics_monitored: int
    drift_detected_in_any: bool
    metrics: Dict[str, MetricStatusResponse]
    timestamp: str


class DriftAlertsResponse(BaseModel):
    """List of drift alerts."""

    alerts: List[DriftAlertResponse]
    total: int
    limit: int


class PerformanceTrendResponse(BaseModel):
    """Performance trend analysis for a metric."""

    status: str
    window: int
    current_value: Optional[float] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    min_val: Optional[float] = Field(None, alias="min")
    max_val: Optional[float] = Field(None, alias="max")
    trend: Optional[str] = None
    trend_slope: Optional[float] = None
    mean_z_score: Optional[float] = None
    latest_z_score: Optional[float] = None
    observations_outside_2sigma: Optional[int] = None
