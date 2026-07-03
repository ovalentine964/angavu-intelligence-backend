"""
Phase 1 Intelligence API Endpoints.

New endpoints for the Phase 1 implementation:
1. GDP Estimator — Real-time informal GDP by county
2. Inflation Tracker — Daily price indices across 47 counties
3. Outcome-Based Pricing — Value-aligned pricing calculations

These endpoints extend the existing intelligence products API
with the new macroeconomic intelligence capabilities.
"""

import time
from datetime import date, datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_buyer_from_api_key
from app.db.database import get_db
from app.models.buyer import Buyer
from app.services.anonymizer import Anonymizer
from app.services.intelligence.gdp_estimator import GDPEstimatorService
from app.services.intelligence.inflation_tracker import InflationTrackerService
from app.services.pricing.outcome_pricing import OutcomePricingEngine

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/intelligence", tags=["Phase 1 Intelligence"])


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────

class GDPRequest(BaseModel):
    """Request for GDP estimation."""

    county: str = Field(
        ...,
        description="County code (e.g., '047' for Nairobi) or 'national'",
    )
    period: str = Field(
        "quarterly",
        pattern=r"^(monthly|quarterly|annual)$",
        description="Estimation period",
    )
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class InflationRequest(BaseModel):
    """Request for inflation tracking."""

    county: str = Field(
        ...,
        description="County code (e.g., '047' for Nairobi) or 'national'",
    )
    period: str = Field(
        "daily",
        pattern=r"^(daily|weekly|monthly)$",
        description="Tracking period",
    )
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class OutcomePricingRequest(BaseModel):
    """Request for outcome-based pricing calculation."""

    product: str = Field(
        ...,
        description="Product code: alama_score, tax_base, distribution_gap, soko_pulse",
    )
    client_id: Optional[str] = Field(None, description="Client identifier")

    # Alama Score params
    approved_loan_value_usd: Optional[float] = Field(None, description="Total approved loan value")
    score_tier: Optional[str] = Field("basic", description="Score tier: basic, enhanced, full")
    volume_discount_pct: Optional[float] = Field(0, description="Volume discount (0-30%)")

    # Tax Base params
    incremental_tax_revenue_kes: Optional[float] = Field(None, description="New tax revenue (KES)")
    collection_rate_pct: Optional[float] = Field(100, description="Collection rate (0-100)")

    # Distribution Gap params
    first_year_new_market_revenue_usd: Optional[float] = Field(None, description="New market revenue")
    margin_pct: Optional[float] = Field(25, description="Product margin %")
    expansion_success_pct: Optional[float] = Field(100, description="Expansion success %")

    # Soko Pulse params
    base_monthly_fee_usd: Optional[float] = Field(2000, description="Base monthly fee")
    forecast_accuracy_pct: Optional[float] = Field(0, description="Forecast accuracy (0-100)")


# ─────────────────────────────────────────────────────────────────────────────
# 1. GDP Estimator Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/gdp/{county}/{period}")
async def get_gdp_estimate(
    county: str,
    period: str,
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    request: Request = None,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Real-Time Informal GDP Estimation.

    **GDP Estimator** nowcasts the contribution of Kenya's informal
    sector (~34% of GDP) using transaction data from Angavu workers.

    **Methodology:**
    - Transaction volumes × average margins × sector multipliers
    - Fisher ideal deflator (ECO 203)
    - HP filter business cycle detection (ECO 205)
    - MIDAS nowcasting from daily data (STA 244)
    - Bootstrap confidence intervals (STA 341)

    **Buyers:** KNBS, CBK, Treasury, IMF, World Bank

    **Path Parameters:**
    - county: County code (e.g., '047' for Nairobi) or 'national'
    - period: 'monthly', 'quarterly', or 'annual'
    """
    start_time = time.time()

    if period not in ("monthly", "quarterly", "annual"):
        raise HTTPException(status_code=400, detail="Period must be monthly, quarterly, or annual")

    service = GDPEstimatorService(db)
    result = await service.estimate_gdp(
        county=county,
        period=period,
        period_start=period_start,
        period_end=period_end,
        buyer_id=str(buyer.id),
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Insufficient data for GDP estimation (k-anonymity not met or no transactions)",
        )

    processing_time = (time.time() - start_time) * 1000
    result["processing_time_ms"] = round(processing_time, 2)
    result["buyer"] = buyer.company_name

    return result


@router.post("/gdp/estimate")
async def post_gdp_estimate(
    req: GDPRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Real-Time Informal GDP Estimation (POST variant).

    Same as GET /gdp/{county}/{period} but with body parameters
    for more complex queries.
    """
    start_time = time.time()

    service = GDPEstimatorService(db)
    result = await service.estimate_gdp(
        county=req.county,
        period=req.period,
        period_start=req.period_start,
        period_end=req.period_end,
        buyer_id=str(buyer.id),
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Insufficient data for GDP estimation",
        )

    processing_time = (time.time() - start_time) * 1000
    result["processing_time_ms"] = round(processing_time, 2)
    result["buyer"] = buyer.company_name

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. Inflation Tracker Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/inflation/{county}/{period}")
async def get_inflation(
    county: str,
    period: str,
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    request: Request = None,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Real-Time Inflation Tracking.

    **Inflation Tracker** computes daily price indices from actual
    transactions across all 47 Kenyan counties — not a 200-basket
    monthly survey.

    **Four Index Types (ECO 203):**
    - Laspeyres: Base-period weights (overstates inflation)
    - Paasche: Current-period weights (understates inflation)
    - Fisher Ideal: Superlative "ideal" index
    - Törnqvist: Discrete Divisia approximation

    **Buyers:** CBK (monetary policy), Treasury, KNBS, financial institutions, media

    **Path Parameters:**
    - county: County code (e.g., '047' for Nairobi) or 'national'
    - period: 'daily', 'weekly', or 'monthly'
    """
    start_time = time.time()

    if period not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="Period must be daily, weekly, or monthly")

    service = InflationTrackerService(db)
    result = await service.compute_inflation(
        county=county,
        period=period,
        period_start=period_start,
        period_end=period_end,
        buyer_id=str(buyer.id),
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Insufficient data for inflation tracking (k-anonymity not met or no transactions)",
        )

    processing_time = (time.time() - start_time) * 1000
    result["processing_time_ms"] = round(processing_time, 2)
    result["buyer"] = buyer.company_name

    return result


@router.post("/inflation/track")
async def post_inflation(
    req: InflationRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Real-Time Inflation Tracking (POST variant).

    Same as GET /inflation/{county}/{period} but with body parameters.
    """
    start_time = time.time()

    service = InflationTrackerService(db)
    result = await service.compute_inflation(
        county=req.county,
        period=req.period,
        period_start=req.period_start,
        period_end=req.period_end,
        buyer_id=str(buyer.id),
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Insufficient data for inflation tracking",
        )

    processing_time = (time.time() - start_time) * 1000
    result["processing_time_ms"] = round(processing_time, 2)
    result["buyer"] = buyer.company_name

    return result


@router.get("/inflation/{county}/timeseries")
async def get_inflation_timeseries(
    county: str,
    periods: int = Query(30, ge=7, le=365),
    period_type: str = Query("daily", pattern=r"^(daily|weekly)$"),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Inflation time series — historical price indices.

    Returns daily or weekly price index values for trend analysis.
    """
    service = InflationTrackerService(db)
    result = await service.get_inflation_timeseries(
        county=county,
        periods=periods,
        period_type=period_type,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Insufficient data for time series")

    result["buyer"] = buyer.company_name
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3. Outcome-Based Pricing Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pricing/outcome/{product}")
async def get_outcome_pricing(
    product: str,
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """
    Get outcome-based pricing configuration for a product.

    Shows the pricing model, rates, caps, and floors for
    outcome-based billing.

    **Products:**
    - alama_score: 0.5–1.5% of approved loan value
    - tax_base: 2–5% of incremental tax revenue
    - distribution_gap: 1–3% of first-year new market revenue
    - soko_pulse: +30% bonus for >90% forecast accuracy
    """
    config = OutcomePricingEngine.get_pricing_config(product)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown product: {product}. Available: alama_score, tax_base, distribution_gap, soko_pulse",
        )

    return {
        "product": product,
        "config": config,
        "buyer": buyer.company_name,
    }


@router.post("/pricing/outcome/calculate")
async def calculate_outcome_pricing(
    req: OutcomePricingRequest,
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """
    Calculate outcome-based pricing for a product.

    **Outcome-Based Model:** Buyers pay based on the VALUE they
    receive, not flat subscriptions. This aligns incentives —
    Angavu gets paid more when buyers get more value.

    **Product-Specific Parameters:**

    **Alama Score:**
    - approved_loan_value_usd: Total loan value approved using Alama
    - score_tier: basic ($0.05), enhanced ($0.15), full ($0.50)
    - volume_discount_pct: Discount for high volume (0–30%)

    **Tax Base:**
    - incremental_tax_revenue_kes: New tax revenue from identified businesses
    - collection_rate_pct: How much was actually collected (0–100)

    **Distribution Gap:**
    - first_year_new_market_revenue_usd: Revenue from new markets
    - margin_pct: Product margin (affects rate)
    - expansion_success_pct: Market entry success (0–100)

    **Soko Pulse:**
    - base_monthly_fee_usd: Base subscription
    - forecast_accuracy_pct: Measured accuracy (0–100)
    """
    kwargs = {}

    if req.product == "alama_score":
        if req.approved_loan_value_usd is None:
            raise HTTPException(status_code=400, detail="approved_loan_value_usd required for Alama Score")
        kwargs = {
            "approved_loan_value_usd": req.approved_loan_value_usd,
            "score_tier": req.score_tier or "basic",
            "volume_discount_pct": req.volume_discount_pct or 0,
        }
    elif req.product == "tax_base":
        if req.incremental_tax_revenue_kes is None:
            raise HTTPException(status_code=400, detail="incremental_tax_revenue_kes required for Tax Base")
        kwargs = {
            "incremental_tax_revenue_kes": req.incremental_tax_revenue_kes,
            "collection_rate_pct": req.collection_rate_pct or 100,
        }
    elif req.product == "distribution_gap":
        if req.first_year_new_market_revenue_usd is None:
            raise HTTPException(status_code=400, detail="first_year_new_market_revenue_usd required for Distribution Gap")
        kwargs = {
            "first_year_new_market_revenue_usd": req.first_year_new_market_revenue_usd,
            "margin_pct": req.margin_pct or 25,
            "expansion_success_pct": req.expansion_success_pct or 100,
        }
    elif req.product == "soko_pulse":
        kwargs = {
            "base_monthly_fee_usd": req.base_monthly_fee_usd or 2000,
            "forecast_accuracy_pct": req.forecast_accuracy_pct or 0,
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product: {req.product}",
        )

    result = OutcomePricingEngine.calculate(
        product=req.product,
        client_id=req.client_id or str(buyer.id),
        **kwargs,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    result["requested_by"] = buyer.company_name
    return result


@router.get("/pricing/outcome")
async def get_all_outcome_pricing(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """
    Get all outcome-based pricing configurations.

    Returns the complete pricing framework for all 4 products.
    """
    result = OutcomePricingEngine.get_all_pricing()
    result["buyer"] = buyer.company_name
    return result
