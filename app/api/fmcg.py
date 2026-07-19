"""
FMCG Intelligence API — Informal Channel Dashboard.

Endpoints for FMCG companies (Pwani Oil, Unilever, Bidco) to access
informal market intelligence, distribution analytics, and competitive
pricing data.

All responses enforce k-anonymity and differential privacy.
"""

import time
from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_buyer_from_api_key
from app.db.database import get_db
from app.models.buyer import Buyer
from app.services.anonymizer import Anonymizer
from app.services.intelligence.fmcg_intelligence import FMCGIntelligenceService
from app.services.intelligence.templates.pwani_oil import PwaniOilTemplate

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/fmcg", tags=["FMCG Intelligence"])


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard/{company}")
async def fmcg_dashboard(
    company: str,
    request: Request,
    region: str | None = Query(None, description="Region filter (e.g., coast, nairobi)"),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    FMCG-specific dashboard for companies like Pwani Oil.

    Aggregates informal channel sales, distribution gaps, competitive
    pricing, and fleet utilization into a single dashboard view.

    **Includes:**
    - Informal channel sales summary
    - Top products by revenue
    - Distribution coverage map
    - Competitive pricing position
    - Key alerts and recommendations

    Args:
        company: Company identifier (e.g., 'pwani_oil')
        region: Optional region filter

    Returns:
        Aggregated FMCG intelligence dashboard
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    service = FMCGIntelligenceService(db)

    # Verify FMCG buyer type
    if buyer.buyer_type not in ("FMCG", "MANUFACTURER", "DISTRIBUTOR", "OTHER"):
        # Allow access but log
        logger.warning("non_fmcg_buyer_accessing_fmcg_dashboard", buyer_type=buyer.buyer_type)

    # Gather dashboard data
    try:
        # Informal channel sales
        sales_data = await service.get_informal_channel_sales(
            company=company,
            region=region or "nairobi",
        )

        # Route analysis
        route_data = await service.get_route_to_market_analysis(company=company)

        # Competitive pricing (cooking oils as default category)
        pricing_data = await service.get_competitive_pricing(
            company=company,
            product_category="cooking_oils",
            region=region,
        )

    except Exception as e:
        logger.error("fmcg_dashboard_error", company=company, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating FMCG dashboard. Please try again.",
        )

    # Build company profile
    template = None
    templates_map = {"pwani_oil": PwaniOilTemplate, "pwani": PwaniOilTemplate}
    template_class = templates_map.get(company.lower())
    if template_class:
        template = template_class

    company_profile = None
    if template:
        company_profile = {
            "name": template.COMPANY_NAME,
            "headquarters": template.HEADQUARTERS,
            "product_categories": list(template.PRODUCTS.keys()),
            "total_products": sum(len(v) for v in template.PRODUCTS.values()),
            "regions_covered": list(template.REGIONS.keys()),
            "competitors": list(template.COMPETITORS.keys()),
        }

    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/fmcg/dashboard/{company}",
        query_params={"region": region},
        processing_time_ms=processing_time,
        ip_address=request.client.host if request.client else None,
        status_code=200,
    )

    return {
        "dashboard": "fmcg_intelligence",
        "version": "1.0",
        "company": company,
        "company_profile": company_profile,
        "region": region or "all",
        "generated_at": sales_data.get("generated_at") if isinstance(sales_data, dict) else None,
        "sections": {
            "informal_channel_sales": sales_data if isinstance(sales_data, dict) else None,
            "route_to_market": route_data if isinstance(route_data, dict) else None,
            "competitive_pricing": pricing_data if isinstance(pricing_data, dict) else None,
        },
        "alerts": _generate_alerts(sales_data, route_data, pricing_data),
        "processing_time_ms": round(processing_time, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Distribution Analysis
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/distribution/{company}/{region}")
async def distribution_analysis(
    company: str,
    region: str,
    request: Request,
    product: str | None = Query(None, description="Specific product to analyze"),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Distribution analysis for informal channels.

    Deep dive into a specific region's informal distribution network.
    Shows vendor density, product availability, channel breakdown,
    and distribution gaps.

    Args:
        company: Company identifier
        region: Geographic region (e.g., 'coast', 'nairobi', 'western')
        product: Optional specific product

    Returns:
        Detailed distribution analysis for the region
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    service = FMCGIntelligenceService(db)

    try:
        # Get informal channel sales for the region
        sales_data = await service.get_informal_channel_sales(
            company=company, region=region,
        )

        # Get distribution gaps
        gap_data = await service.get_distribution_gaps(
            company=company,
            product=product or "Fresh Fri",
            region=region,
        )

        # Get fleet optimization for region
        fleet_data = await service.get_fleet_utilization(company=company)

    except Exception as e:
        logger.error("distribution_analysis_error", company=company, region=region, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating distribution analysis.",
        )

    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/fmcg/distribution/{company}/{region}",
        query_params={"product": product},
        processing_time_ms=processing_time,
        ip_address=request.client.host if request.client else None,
        status_code=200,
    )

    return {
        "analysis": "fmcg_distribution",
        "version": "1.0",
        "company": company,
        "region": region,
        "product": product,
        "generated_at": sales_data.get("generated_at") if isinstance(sales_data, dict) else None,
        "channel_sales": sales_data if isinstance(sales_data, dict) else None,
        "distribution_gaps": gap_data if isinstance(gap_data, dict) else None,
        "fleet_optimization": fleet_data if isinstance(fleet_data, dict) else None,
        "recommendations": _generate_distribution_recommendations(sales_data, gap_data),
        "processing_time_ms": round(processing_time, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pricing Intelligence
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pricing/{company}/{product}")
async def pricing_intelligence(
    company: str,
    product: str,
    request: Request,
    region: str | None = Query(None, description="Region filter"),
    period_days: int = Query(30, ge=7, le=180, description="Analysis window in days"),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Competitive pricing intelligence for a specific product.

    Tracks pricing across informal markets, identifies price
    volatility, and provides competitive positioning analysis.

    Args:
        company: Company identifier
        product: Product name (e.g., 'Fresh Fri', 'Salit')
        region: Optional region filter
        period_days: Analysis window (7-180 days)

    Returns:
        Pricing intelligence with competitive analysis
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    service = FMCGIntelligenceService(db)

    # Determine product category
    template = None
    templates_map = {"pwani_oil": PwaniOilTemplate, "pwani": PwaniOilTemplate}
    template_class = templates_map.get(company.lower())
    if template_class:
        template = template_class

    category = None
    if template:
        for cat, products in template.PRODUCTS.items():
            if product in products:
                category = cat
                break

    if not category:
        # Default to cooking oils if category unknown
        category = "cooking_oils"

    try:
        pricing_data = await service.get_competitive_pricing(
            company=company,
            product_category=category,
            region=region,
            period_days=period_days,
        )

        # Also get trade promotion data if available
        promo_data = await service.get_trade_promotion_roi(
            company=company,
            promotion_id=f"default_{product}",
        )

    except Exception as e:
        logger.error("pricing_intelligence_error", company=company, product=product, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating pricing intelligence.",
        )

    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/fmcg/pricing/{company}/{product}",
        query_params={"region": region, "period_days": period_days},
        processing_time_ms=processing_time,
        ip_address=request.client.host if request.client else None,
        status_code=200,
    )

    return {
        "analysis": "fmcg_pricing_intelligence",
        "version": "1.0",
        "company": company,
        "product": product,
        "category": category,
        "region": region or "national",
        "period_days": period_days,
        "generated_at": pricing_data.get("generated_at") if isinstance(pricing_data, dict) else None,
        "pricing": pricing_data if isinstance(pricing_data, dict) else None,
        "promotion_roi": promo_data if isinstance(promo_data, dict) else None,
        "processing_time_ms": round(processing_time, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Trade Promotion Analysis
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/promotion/{company}/{promotion_id}")
async def promotion_analysis(
    company: str,
    promotion_id: str,
    request: Request,
    promotion_start: date | None = Query(None),
    promotion_end: date | None = Query(None),
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Trade promotion ROI analysis for informal channels.

    Measures whether promotions drive incremental sales or just
    shift timing. Tracks adoption across informal outlets.

    Args:
        company: Company identifier
        promotion_id: Promotion identifier
        promotion_start: Promotion start date
        promotion_end: Promotion end date

    Returns:
        Promotion ROI analysis
    """
    start_time = time.time()
    anonymizer = Anonymizer(db)
    service = FMCGIntelligenceService(db)

    try:
        promo_data = await service.get_trade_promotion_roi(
            company=company,
            promotion_id=promotion_id,
            promotion_start=promotion_start,
            promotion_end=promotion_end,
        )
    except Exception as e:
        logger.error("promotion_analysis_error", company=company, promotion=promotion_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating promotion analysis.",
        )

    processing_time = (time.time() - start_time) * 1000
    await anonymizer.log_data_access(
        buyer_id=str(buyer.id),
        api_key_id=None,
        endpoint=f"/fmcg/promotion/{company}/{promotion_id}",
        query_params={"promotion_start": str(promotion_start), "promotion_end": str(promotion_end)},
        processing_time_ms=processing_time,
        ip_address=request.client.host if request.client else None,
        status_code=200,
    )

    return promo_data


# ─────────────────────────────────────────────────────────────────────────────
# Client Templates
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/templates/{company}")
async def get_company_template(
    company: str,
    request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """
    Get company template with product portfolio and regional data.

    Returns the full client template including products, regions,
    competitors, and recommended service tiers.

    Args:
        company: Company identifier (e.g., 'pwani_oil')

    Returns:
        Company template details
    """
    templates_map = {"pwani_oil": PwaniOilTemplate, "pwani": PwaniOilTemplate}
    template = templates_map.get(company.lower())

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No template found for company: {company}. Available: {list(templates_map.keys())}",
        )

    return {
        "company": template.COMPANY_NAME,
        "headquarters": template.HEADQUARTERS,
        "manufacturing": template.MANUFACTURING,
        "founded": template.FOUNDED,
        "daily_capacity_tonnes": template.DAILY_CAPACITY_TONNES,
        "products": template.PRODUCTS,
        "regions": {
            k: {
                "name": v.name,
                "counties": v.counties,
                "population_estimate": v.population_estimate,
                "informal_market_density": v.informal_market_density,
                "key_distributor_hubs": v.key_distributor_hubs,
                "penetration_opportunity": v.penetration_opportunity,
            }
            for k, v in template.REGIONS.items()
        },
        "competitors": template.COMPETITORS,
        "recommended_services": template.RECOMMENDED_SERVICES,
        "expansion_priorities": template.get_expansion_priorities(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _generate_alerts(sales_data, route_data, pricing_data) -> list:
    """Generate actionable alerts from dashboard data."""
    alerts = []

    # Check if sales data indicates low coverage
    if isinstance(sales_data, dict) and sales_data.get("status") == "insufficient_data":
        alerts.append({
            "type": "data_gap",
            "severity": "info",
            "message": "Insufficient vendor data in this region. Consider expanding data collection.",
        })

    # Check pricing volatility
    if isinstance(pricing_data, dict):
        volatility_alerts = pricing_data.get("price_volatility_alerts", [])
        for alert in volatility_alerts[:3]:
            alerts.append({
                "type": "price_volatility",
                "severity": "warning",
                "product": alert.get("product"),
                "cv_pct": alert.get("coefficient_of_variation"),
                "message": f"High price volatility for {alert.get('product')} — CV: {alert.get('coefficient_of_variation')}%",
            })

    # Check route efficiency
    if isinstance(route_data, dict):
        route_analysis = route_data.get("route_analysis", {})
        low_eff = route_analysis.get("low_efficiency_routes", 0)
        if low_eff > 0:
            alerts.append({
                "type": "route_inefficiency",
                "severity": "warning",
                "count": low_eff,
                "message": f"{low_eff} routes with low efficiency scores. Review consolidation opportunities.",
            })

    return alerts


def _generate_distribution_recommendations(sales_data, gap_data) -> list:
    """Generate distribution recommendations from analysis data."""
    recommendations = []

    if isinstance(gap_data, dict):
        coverage = gap_data.get("coverage", {})
        coverage_pct = coverage.get("coverage_pct", 100)

        if coverage_pct < 50:
            recommendations.append({
                "priority": "high",
                "action": "expand_distribution",
                "reason": f"Only {coverage_pct}% market coverage",
                "impact": "high",
            })
        elif coverage_pct < 80:
            recommendations.append({
                "priority": "medium",
                "action": "fill_gaps",
                "reason": f"{coverage_pct}% coverage — {coverage.get('gap_pct', 0)}% remaining",
                "impact": "medium",
            })

        # Revenue potential from gaps
        gap_potential = gap_data.get("gap_revenue_potential_kes", 0)
        if gap_potential > 0:
            recommendations.append({
                "priority": "high",
                "action": "capture_gap_revenue",
                "estimated_impact_kes": gap_potential,
                "reason": "Identified revenue potential in uncovered markets",
            })

    return recommendations
