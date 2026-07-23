"""
Buyer Dashboard — B2B intelligence product access.

Architecture: arch_backend.md §3.8, §7
Separate auth (API key + OAuth2), rate limiting, per-product subscriptions.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.redis import get_redis
from app.services.buyer_auth import get_current_buyer, require_product
from app.services.buyer_rate_limiter import BuyerRateLimiter
from app.services.intelligence_engine import IntelligenceEngine
from app.infrastructure.metrics import INTEL_GENERATION
import time

router = APIRouter()


# ─── Rate Limit Dependency ────────────────────────────────────────────────────

async def check_rate_limit(claims: dict = Depends(get_current_buyer)):
    """Check buyer rate limit before processing."""
    r = await get_redis()
    limiter = BuyerRateLimiter(r)
    allowed = await limiter.check_and_consume(claims["sub"], claims["tier"])
    if not allowed:
        raise HTTPException(429, "Daily rate limit exceeded for your tier")
    return claims


# ─── Soko Pulse ───────────────────────────────────────────────────────────────

@router.get("/soko-pulse")
async def buyer_soko_pulse(
    product_category: str = Query(..., description="Product category"),
    region: str = Query(..., description="Geohash-5 region"),
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    include_elasticity: bool = Query(False),
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Soko Pulse — FMCG demand forecasting for buyers."""
    start = time.monotonic()
    engine = IntelligenceEngine(db)
    result = await engine.generate_soko_pulse(
        region=region,
        product_category=product_category,
        period_start=period_start,
        period_end=period_end,
        tier=claims["tier"],
    )
    INTEL_GENERATION.labels(product="buyer_soko_pulse").observe(time.monotonic() - start)
    return {"product": "soko-pulse", "buyer_tier": claims["tier"], **result}


@router.get("/soko-pulse/regions")
async def list_soko_pulse_regions(
    product_category: str = Query(...),
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """List regions with available Soko Pulse data."""
    from app.models.intelligence import IntelligenceProduct
    from sqlalchemy import select
    result = await db.execute(
        select(IntelligenceProduct.region).where(
            IntelligenceProduct.product_type == "soko_pulse",
            IntelligenceProduct.category == product_category,
            IntelligenceProduct.status == "ready",
        ).distinct()
    )
    return {"regions": [row[0] for row in result.all()]}


# ─── Alama Score ──────────────────────────────────────────────────────────────

@router.get("/alama-score/{worker_id_hash}")
async def buyer_alama_score(
    worker_id_hash: str,
    include_factors: bool = Query(False),
    include_history: bool = Query(False),
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Alama Score — Credit scoring for banks and fintechs."""
    import re
    if not re.match(r"^[a-f0-9]{64}$", worker_id_hash):
        raise HTTPException(400, "Invalid worker_id_hash format")

    engine = IntelligenceEngine(db)
    result = await engine.generate_alama_score(worker_id_hash=worker_id_hash, tier=claims["tier"])

    if not include_factors:
        result.pop("factors", None)

    if include_history:
        from app.models.intelligence import IntelligenceProduct
        from sqlalchemy import select
        hist_result = await db.execute(
            select(IntelligenceProduct).where(
                IntelligenceProduct.product_type == "alama_score",
                IntelligenceProduct.region == worker_id_hash,
            ).order_by(IntelligenceProduct.created_at.desc()).limit(6)
        )
        history = hist_result.scalars().all()
        result["history"] = [
            {"score": h.data.get("score"), "date": h.created_at.isoformat() if h.created_at else None, "band": h.data.get("risk_band")}
            for h in history
        ]

    return {"product": "alama-score", "buyer_tier": claims["tier"], **result}


class AlamaBatchRequest(BaseModel):
    worker_hashes: list[str] = Field(..., max_length=100)


@router.post("/alama-score/batch")
async def batch_alama_scores(
    request: AlamaBatchRequest,
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Batch credit scoring — up to 100 workers per request."""
    engine = IntelligenceEngine(db)
    scores = {}
    missing = []
    for h in request.worker_hashes:
        result = await engine.generate_alama_score(worker_id_hash=h, tier=claims["tier"])
        if result.get("score") is not None:
            scores[h] = {"score": result["score"], "band": result.get("risk_band"), "confidence": result.get("confidence")}
        else:
            missing.append(h)
    return {"product": "alama-score", "scores": scores, "missing": missing}


# ─── Angavu Pulse ─────────────────────────────────────────────────────────────

@router.get("/angavu-pulse")
async def buyer_angavu_pulse(
    region: str = Query(..., description="Geohash-5 or 'national'"),
    sector: Optional[str] = None,
    period: str = Query("weekly"),
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Angavu Pulse — MSME activity for government and investors."""
    engine = IntelligenceEngine(db)
    result = await engine.generate_angavu_pulse(region=region, period=period, sector=sector)
    return {"product": "angavu-pulse", "buyer_tier": claims["tier"], **result}


@router.get("/angavu-pulse/compare")
async def buyer_compare_regions(
    regions: str = Query(..., description="Comma-separated geohash-5 codes"),
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Compare MSME activity across regions."""
    region_list = [r.strip() for r in regions.split(",")][:10]
    if len(region_list) < 2:
        raise HTTPException(400, "At least 2 regions required")
    engine = IntelligenceEngine(db)
    results = await engine.compare_regions(region_list)
    return {"product": "angavu-pulse", "comparison": results}


# ─── Jamii Insights ───────────────────────────────────────────────────────────

@router.get("/jamii-insights")
async def buyer_jamii_insights(
    region: str = Query(...),
    dimension: Optional[str] = None,
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Jamii Insights — Financial inclusion for NGOs and government."""
    engine = IntelligenceEngine(db)
    result = await engine.generate_jamii_insights(region=region, dimension=dimension)
    return {"product": "jamii-insights", "buyer_tier": claims["tier"], **result}


# ─── Reports ──────────────────────────────────────────────────────────────────

@router.get("/report/{product_type}")
async def generate_report(
    product_type: str,
    region: str = Query(...),
    format: str = Query("json", pattern="^(json|pdf|html)$"),
    claims: dict = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Generate intelligence report."""
    engine = IntelligenceEngine(db)

    generators = {
        "soko-pulse": lambda: engine.generate_soko_pulse(region=region, product_category="general"),
        "alama-score": lambda: engine.generate_alama_score(worker_id_hash=region),
        "angavu-pulse": lambda: engine.generate_angavu_pulse(region=region),
        "jamii-insights": lambda: engine.generate_jamii_insights(region=region),
    }

    generator = generators.get(product_type)
    if not generator:
        raise HTTPException(400, f"Unknown product type: {product_type}")

    result = await generator()

    if format == "json":
        return result

    # For PDF/HTML, return JSON with a note (PDF generation would need WeasyPrint)
    return {"product": product_type, "format": format, "data": result, "note": "PDF/HTML generation available in enterprise tier"}
