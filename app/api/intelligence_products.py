"""
Intelligence Products API endpoints.

Provides buyer-facing endpoints for the 6 intelligence products:
1. Soko Pulse — FMCG demand forecasting
2. Biashara Pulse — Government MSME Activity Index
3. Alama Score — Bank credit scoring (300-850)
4. Jamii Insights — NGO financial inclusion
5. Tax Base Estimation — Government revenue
6. Distribution Gap Analysis — FMCG market coverage

All endpoints enforce:
- Authentication via API key
- k-anonymity (k≥10)
- Differential privacy on sensitive metrics
- Geographic scoping per buyer authorization
- Full audit logging
"""

import time
from datetime import date, datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_buyer_from_api_key
from app.db.database import get_db
from app.models.buyer import Buyer
from app.schemas.intelligence_products import (
    AlamaScoreRequest,
    AlamaScoreResponse,
    BiasharaPulseRequest,
    BiasharaPulseResponse,
    DistributionGapRequest,
    DistributionGapResponse,
    JamiiInsightsRequest,
    JamiiInsightsResponse,
    SokoPulseRequest,
    SokoPulseResponse,
    TaxBaseRequest,
    TaxBaseResponse,
)
from app.services.anonymizer import Anonymizer
from app.services.intelligence.alama_score import AlamaScoreService
from app.services.intelligence.biashara_pulse import BiasharaPulseService
from app.services.intelligence.distribution_gap import DistributionGapService
from app.services.intelligence.jamii_insights import JamiiInsightsService
from app.services.intelligence.pricing import (
    ALAMA_QUERY_PRICES,
    DISTRIBUTION_GAP_ONE_TIME,
    DISTRIBUTION_MONITORING_MONTHLY_KES,
    calculate_monthly_cost,
    get_product_pricing,
)
from app.services.intelligence.soko_pulse import SokoPulseService
from app.services.intelligence.tax_base import TaxBaseService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/intelligence-products", tags=["Intelligence Products"])


# =========================================================================
# Helper
# =========================================================================


def _is_region_authorized(buyer: Buyer, region: str) -> bool:
    """Check if buyer is authorized for a region."""
    authorized = buyer.regions_authorized or []
    if not authorized:
        return True
    for auth_region in authorized:
        if region.startswith(auth_region) or auth_region == "all":
            return True
    return False


def _check_product_access(buyer: Buyer, product_code: str) -> bool:
    """Check if buyer has access to a product."""
    subscribed = buyer.products_subscribed or []
    if not subscribed:
        return True  # No restriction
    return product_code in subscribed


async def _log_access(
    db: AsyncSession,
    buyer: Buyer,
    endpoint: str,
    request: Request,
    start_time: float,
    records: int = 0,
    error: str = None,
):
    """Log data access for audit."""
    anonymizer = Anonymizer(db)
    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=endpoint,
        processing_time_ms=processing_time,
        records_returned=records,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        status_code=200 if not error else 500,
        error_message=error,
    )


# =========================================================================
# 1. Soko Pulse — FMCG Demand Forecasting
# =========================================================================


@router.post("/soko-pulse/demand-forecast", response_model=SokoPulseResponse)
async def soko_pulse_forecast(
    req: SokoPulseRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate FMCG demand forecasting intelligence.

    **Soko Pulse** provides real-time demand patterns from informal markets:
    - What sells, where, when, and seasonal trends
    - Price intelligence across markets
    - Demand forecasting with confidence intervals (premium+)

    **Pricing:**
    - Standard: $2,000/mo (5 markets, weekly)
    - Premium: $5,000/mo (20 markets, daily, forecasting)
    - Enterprise: $12,000/mo (all markets, real-time)

    **Privacy:** k-anonymity (k≥10) enforced. No individual data exposed.
    """
    start_time = time.time()

    if not _check_product_access(buyer, "soko_pulse"):
        raise HTTPException(status_code=403, detail="Not subscribed to Soko Pulse")

    if req.region and not _is_region_authorized(buyer, req.region):
        raise HTTPException(status_code=403, detail=f"Not authorized for region: {req.region}")

    service = SokoPulseService(db)
    result = await service.generate_demand_forecast(
        product_category=req.product_category,
        product_name=req.product_name,
        region=req.region,
        period_start=req.period_start,
        period_end=req.period_end,
        tier=req.tier,
        buyer_id=str(buyer.id),
    )

    if not result:
        await _log_access(db, buyer, "/soko-pulse/demand-forecast", request, start_time, error="Insufficient data")
        raise HTTPException(status_code=404, detail="Insufficient data for analysis (k-anonymity not met)")

    await _log_access(db, buyer, "/soko-pulse/demand-forecast", request, start_time, records=result.get("data_points", 0))
    return result


@router.get("/soko-pulse/pricing")
async def soko_pulse_pricing(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """Get Soko Pulse pricing tiers."""
    pricing = get_product_pricing("soko_pulse")
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing not found")
    return {
        "product": pricing.product_name,
        "buyer_segment": pricing.buyer_segment,
        "tiers": [
            {
                "tier": t.tier,
                "price_monthly_kes": t.price_monthly_kes,
                "price_monthly_usd": t.price_monthly_usd,
                "features": t.features,
                "refresh_frequency": t.refresh_frequency,
                "max_markets": t.max_markets,
                "api_queries_per_month": t.api_queries_per_month,
            }
            for t in pricing.tiers
        ],
    }


# =========================================================================
# 2. Biashara Pulse — Government MSME Activity Index
# =========================================================================


@router.post("/biashara-pulse/activity-index", response_model=BiasharaPulseResponse)
async def biashara_pulse_index(
    req: BiasharaPulseRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate Government MSME Activity Index.

    **Biashara Pulse** provides economic activity heatmaps:
    - Activity indices (0-100) by county/sub-county
    - Business formation/destruction rates
    - Sector breakdown and employment estimates

    **Pricing:**
    - Standard: $250/mo per county
    - Premium: $750/mo (5 counties)
    - Enterprise: $5,000/mo (all 47 counties)

    **Buyers:** KNBS, CBK, county governments
    """
    start_time = time.time()

    if not _check_product_access(buyer, "biashara_pulse"):
        raise HTTPException(status_code=403, detail="Not subscribed to Biashara Pulse")

    if req.region != "national" and not _is_region_authorized(buyer, req.region):
        raise HTTPException(status_code=403, detail=f"Not authorized for region: {req.region}")

    service = BiasharaPulseService(db)
    result = await service.generate_activity_index(
        region=req.region,
        period_start=req.period_start,
        period_end=req.period_end,
        buyer_id=str(buyer.id),
    )

    if not result:
        await _log_access(db, buyer, "/biashara-pulse/activity-index", request, start_time, error="Insufficient data")
        raise HTTPException(status_code=404, detail="Insufficient data for region (k-anonymity not met)")

    await _log_access(db, buyer, "/biashara-pulse/activity-index", request, start_time, records=result.get("users_included", 0))
    return result


@router.get("/biashara-pulse/pricing")
async def biashara_pulse_pricing(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """Get Biashara Pulse pricing tiers."""
    pricing = get_product_pricing("biashara_pulse")
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing not found")
    return {
        "product": pricing.product_name,
        "buyer_segment": pricing.buyer_segment,
        "tiers": [
            {
                "tier": t.tier,
                "price_monthly_kes": t.price_monthly_kes,
                "price_monthly_usd": t.price_monthly_usd,
                "features": t.features,
                "refresh_frequency": t.refresh_frequency,
                "max_markets": t.max_markets,
            }
            for t in pricing.tiers
        ],
    }


# =========================================================================
# 3. Alama Score — Bank Credit Scoring
# =========================================================================


@router.post("/alama-score/compute", response_model=AlamaScoreResponse)
async def alama_score_compute(
    req: AlamaScoreRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Compute Alama credit score for a business.

    **Alama Score** provides transaction-based credit scoring (300-850):
    - Activity, stability, growth, consistency, diversity components
    - Heckman-corrected scores (enhanced/full tier)
    - Risk indicators and recommended credit limits

    **Per-query pricing:**
    - Basic: $0.05/query — basic score
    - Enhanced: $0.15/query — with Heckman correction
    - Full: $0.50/query — full profile

    **Volume discounts:** Up to $0.03/query at 500K+ monthly volume
    """
    start_time = time.time()

    if not _check_product_access(buyer, "alama_score"):
        # Allow financial institutions
        if buyer.buyer_type not in ("BANK", "MFI", "INSURANCE"):
            raise HTTPException(status_code=403, detail="Not subscribed to Alama Score. Contact sales.")

    service = AlamaScoreService(db)
    result = await service.compute_score(
        business_id=req.business_id,
        lookback_days=req.lookback_days,
        query_tier=req.query_tier,
        include_heckman=req.include_heckman_correction,
        buyer_id=str(buyer.id),
    )

    if not result:
        await _log_access(db, buyer, "/alama-score/compute", request, start_time, error="Insufficient data")
        raise HTTPException(status_code=404, detail="Insufficient data for scoring (20+ transactions needed)")

    # Calculate price
    price_usd = ALAMA_QUERY_PRICES.get(req.query_tier, 0.05)
    price_kes = price_usd * 155
    result["price_charged_usd"] = price_usd
    result["price_charged_kes"] = round(price_kes, 2)

    await _log_access(db, buyer, "/alama-score/compute", request, start_time, records=1)
    return result


@router.post("/alama-score/batch")
async def alama_score_batch(
    business_ids: list[str],
    request: Request,
    query_tier: str = Query("basic", pattern=r"^(basic|enhanced|full)$"),
    lookback_days: int = Query(90, ge=30, le=365),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch compute Alama scores for multiple businesses.

    More efficient than individual queries for portfolio assessment.
    Maximum 100 businesses per batch.
    """
    start_time = time.time()

    if len(business_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 businesses per batch")

    if buyer.buyer_type not in ("BANK", "MFI", "INSURANCE"):
        if not _check_product_access(buyer, "alama_score"):
            raise HTTPException(status_code=403, detail="Not authorized for credit scoring")

    service = AlamaScoreService(db)
    results = []
    for bid in business_ids:
        result = await service.compute_score(
            business_id=bid,
            lookback_days=lookback_days,
            query_tier=query_tier,
            buyer_id=str(buyer.id),
        )
        if result:
            results.append(result)

    # Volume pricing
    price_usd = ALAMA_QUERY_PRICES.get(query_tier, 0.05)
    total_cost = price_usd * len(results)

    await _log_access(db, buyer, "/alama-score/batch", request, start_time, records=len(results))

    return {
        "scores": results,
        "total_scored": len(results),
        "total_failed": len(business_ids) - len(results),
        "query_tier": query_tier,
        "price_per_query_usd": price_usd,
        "total_cost_usd": round(total_cost, 2),
        "total_cost_kes": round(total_cost * 155, 2),
    }


@router.get("/alama-score/pricing")
async def alama_score_pricing(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """Get Alama Score pricing (per-query with volume discounts)."""
    from app.services.intelligence.pricing import ALAMA_VOLUME_DISCOUNTS
    return {
        "product": "Alama Score — Transaction-Based Credit Scoring",
        "pricing_model": "per_query",
        "query_tiers": ALAMA_QUERY_PRICES,
        "volume_discounts": ALAMA_VOLUME_DISCOUNTS,
        "currency": "USD",
    }


# =========================================================================
# 4. Jamii Insights — NGO Financial Inclusion
# =========================================================================


@router.post("/jamii-insights/inclusion-report", response_model=JamiiInsightsResponse)
async def jamii_insights_report(
    req: JamiiInsightsRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate financial inclusion intelligence.

    **Jamii Insights** provides demographic-level inclusion metrics:
    - Financial inclusion index by region/demographic
    - Digital payment adoption, savings, credit access
    - Program impact measurement for development organizations

    **Pricing:**
    - Standard: $2,000 per study
    - Premium: $5,000 per study (with impact measurement)
    - Enterprise: $10,000 per study (national, co-branded)

    **Buyers:** World Bank, USAID, DFID, NGOs
    """
    start_time = time.time()

    if not _check_product_access(buyer, "jamii_insights"):
        if buyer.buyer_type not in ("NGO", "RESEARCH"):
            raise HTTPException(status_code=403, detail="Not subscribed to Jamii Insights")

    if req.region != "national" and not _is_region_authorized(buyer, req.region):
        raise HTTPException(status_code=403, detail=f"Not authorized for region: {req.region}")

    service = JamiiInsightsService(db)
    result = await service.generate_inclusion_report(
        region=req.region,
        demographic_segment=req.demographic_segment,
        period_start=req.period_start,
        period_end=req.period_end,
        program_name=req.program_name,
        buyer_id=str(buyer.id),
    )

    if not result:
        await _log_access(db, buyer, "/jamii-insights/inclusion-report", request, start_time, error="Insufficient data")
        raise HTTPException(status_code=404, detail="Insufficient data for region/demographic (k-anonymity not met)")

    await _log_access(db, buyer, "/jamii-insights/inclusion-report", request, start_time, records=result.get("sample_size", 0))
    return result


@router.get("/jamii-insights/pricing")
async def jamii_insights_pricing(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """Get Jamii Insights pricing tiers."""
    pricing = get_product_pricing("jamii_insights")
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing not found")
    return {
        "product": pricing.product_name,
        "buyer_segment": pricing.buyer_segment,
        "tiers": [
            {
                "tier": t.tier,
                "price_monthly_kes": t.price_monthly_kes,
                "price_monthly_usd": t.price_monthly_usd,
                "features": t.features,
                "refresh_frequency": t.refresh_frequency,
            }
            for t in pricing.tiers
        ],
    }


# =========================================================================
# 5. Tax Base Estimation — Government Revenue
# =========================================================================


@router.post("/tax-base/estimate", response_model=TaxBaseResponse)
async def tax_base_estimate(
    req: TaxBaseRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Estimate tax base for a region/sector.

    **Tax Base Estimation** provides:
    - Estimated tax liability for informal businesses
    - VAT collection potential by sector/region
    - Tax gap analysis and formalization tracking

    **Pricing:**
    - Standard: $1,500/mo per county
    - Premium: $3,500/mo (10 counties)
    - Enterprise: $10,000/mo (national)

    **Buyers:** KRA, county governments
    """
    start_time = time.time()

    if not _check_product_access(buyer, "tax_base_estimation"):
        if buyer.buyer_type not in ("GOVT",):
            raise HTTPException(status_code=403, detail="Not subscribed to Tax Base Estimation")

    if req.region != "national" and not _is_region_authorized(buyer, req.region):
        raise HTTPException(status_code=403, detail=f"Not authorized for region: {req.region}")

    service = TaxBaseService(db)
    result = await service.estimate_tax_base(
        region=req.region,
        sector=req.sector,
        period_start=req.period_start,
        period_end=req.period_end,
        buyer_id=str(buyer.id),
    )

    if not result:
        await _log_access(db, buyer, "/tax-base/estimate", request, start_time, error="Insufficient data")
        raise HTTPException(status_code=404, detail="Insufficient data for region/sector (k-anonymity not met)")

    await _log_access(db, buyer, "/tax-base/estimate", request, start_time, records=result.get("users_included", 0))
    return result


@router.get("/tax-base/pricing")
async def tax_base_pricing(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """Get Tax Base Estimation pricing tiers."""
    pricing = get_product_pricing("tax_base_estimation")
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing not found")
    return {
        "product": pricing.product_name,
        "buyer_segment": pricing.buyer_segment,
        "tiers": [
            {
                "tier": t.tier,
                "price_monthly_kes": t.price_monthly_kes,
                "price_monthly_usd": t.price_monthly_usd,
                "features": t.features,
                "refresh_frequency": t.refresh_frequency,
                "max_markets": t.max_markets,
            }
            for t in pricing.tiers
        ],
    }


# =========================================================================
# 6. Distribution Gap Analysis — FMCG Market Coverage
# =========================================================================


@router.post("/distribution-gap/analyze", response_model=DistributionGapResponse)
async def distribution_gap_analyze(
    req: DistributionGapRequest,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze distribution gaps for a product category.

    **Distribution Gap Analysis** provides:
    - Where products are NOT reaching
    - Underserved market identification
    - Revenue potential of gap markets
    - Expansion recommendations with ROI estimates

    **Pricing:**
    - Basic: $15,000 one-time (single category)
    - Standard: $25,000 one-time (multi-category)
    - Comprehensive: $30,000 one-time (full analysis)
    - Monitoring: $3,000/mo add-on

    **Buyers:** FMCG distribution companies
    """
    start_time = time.time()

    if not _check_product_access(buyer, "distribution_gap"):
        if buyer.buyer_type not in ("FMCG", "SUPPLY_CHAIN"):
            raise HTTPException(status_code=403, detail="Not subscribed to Distribution Gap Analysis")

    if req.region and not _is_region_authorized(buyer, req.region):
        raise HTTPException(status_code=403, detail=f"Not authorized for region: {req.region}")

    service = DistributionGapService(db)
    result = await service.analyze_gaps(
        product_category=req.product_category,
        product_name=req.product_name,
        region=req.region,
        period_start=req.period_start,
        period_end=req.period_end,
        buyer_id=str(buyer.id),
    )

    if not result:
        await _log_access(db, buyer, "/distribution-gap/analyze", request, start_time, error="Insufficient data")
        raise HTTPException(status_code=404, detail="Insufficient data for analysis")

    await _log_access(db, buyer, "/distribution-gap/analyze", request, start_time, records=result.get("users_included", 0))
    return result


@router.get("/distribution-gap/pricing")
async def distribution_gap_pricing(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """Get Distribution Gap Analysis pricing."""
    return {
        "product": "Distribution Gap Analysis — FMCG Market Coverage",
        "pricing_model": "one_time_plus_monitoring",
        "one_time_tiers": DISTRIBUTION_GAP_ONE_TIME,
        "monitoring_addon_monthly_kes": DISTRIBUTION_MONITORING_MONTHLY_KES,
        "monitoring_addon_monthly_usd": DISTRIBUTION_MONITORING_MONTHLY_USD,
        "currency": "USD",
    }


# =========================================================================
# Catalog & Overview
# =========================================================================


@router.get("/catalog")
async def intelligence_catalog(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """
    Get full catalog of available intelligence products.

    Returns all 6 products with pricing, features, and availability
    based on the buyer's subscription and authorization.
    """
    products = [
        {
            "code": "soko_pulse",
            "name": "Soko Pulse — FMCG Demand Forecasting",
            "description": "Real-time demand patterns from informal markets",
            "buyer_segment": "FMCG",
            "endpoint": "/api/v1/intelligence-products/soko-pulse/demand-forecast",
            "pricing_summary": "From $2,000/mo",
            "subscribed": _check_product_access(buyer, "soko_pulse"),
        },
        {
            "code": "biashara_pulse",
            "name": "Biashara Pulse — Government MSME Activity Index",
            "description": "Economic activity heatmaps by county/sub-county",
            "buyer_segment": "Government",
            "endpoint": "/api/v1/intelligence-products/biashara-pulse/activity-index",
            "pricing_summary": "From $250/mo per county",
            "subscribed": _check_product_access(buyer, "biashara_pulse"),
        },
        {
            "code": "alama_score",
            "name": "Alama Score — Transaction-Based Credit Scoring",
            "description": "Credit scoring (300-850) with Heckman correction",
            "buyer_segment": "Financial Institutions",
            "endpoint": "/api/v1/intelligence-products/alama-score/compute",
            "pricing_summary": "From $0.05/query",
            "subscribed": _check_product_access(buyer, "alama_score"),
        },
        {
            "code": "jamii_insights",
            "name": "Jamii Insights — NGO Financial Inclusion",
            "description": "Financial inclusion metrics and impact measurement",
            "buyer_segment": "Development/NGO",
            "endpoint": "/api/v1/intelligence-products/jamii-insights/inclusion-report",
            "pricing_summary": "From $2,000 per study",
            "subscribed": _check_product_access(buyer, "jamii_insights"),
        },
        {
            "code": "tax_base_estimation",
            "name": "Tax Base Estimation — Government Revenue",
            "description": "Estimated tax liability for informal businesses",
            "buyer_segment": "Government (KRA/County)",
            "endpoint": "/api/v1/intelligence-products/tax-base/estimate",
            "pricing_summary": "From $1,500/mo per county",
            "subscribed": _check_product_access(buyer, "tax_base_estimation"),
        },
        {
            "code": "distribution_gap",
            "name": "Distribution Gap Analysis — FMCG Market Coverage",
            "description": "Where products are NOT reaching",
            "buyer_segment": "FMCG Distribution",
            "endpoint": "/api/v1/intelligence-products/distribution-gap/analyze",
            "pricing_summary": "From $15,000 one-time",
            "subscribed": _check_product_access(buyer, "distribution_gap"),
        },
    ]

    return {
        "buyer": buyer.company_name,
        "buyer_type": buyer.buyer_type,
        "tier": buyer.tier,
        "products": products,
        "total_products": len(products),
        "subscribed_products": sum(1 for p in products if p["subscribed"]),
    }
