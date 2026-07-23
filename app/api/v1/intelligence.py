"""
Intelligence endpoints — Soko Pulse, Alama Score, Angavu Pulse, Jamii Insights.

Architecture: arch_backend.md §2.5
Direct service calls — no agent indirection.
"""
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.intelligence_engine import IntelligenceEngine
from app.infrastructure.metrics import INTEL_GENERATION
import time

router = APIRouter()


# ─── Soko Pulse ───────────────────────────────────────────────────────────────

@router.get("/soko-pulse/{region}")
async def get_soko_pulse(
    region: str,
    commodity: Optional[str] = Query(None, description="Product category"),
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Soko Pulse — FMCG demand forecasting and market intelligence."""
    start = time.monotonic()
    engine = IntelligenceEngine(db)
    result = await engine.generate_soko_pulse(
        region=region,
        product_category=commodity or "general",
        period_start=period_start,
        period_end=period_end,
    )
    INTEL_GENERATION.labels(product="soko_pulse").observe(time.monotonic() - start)
    return result


# ─── Alama Score ──────────────────────────────────────────────────────────────

@router.get("/alama-score/{worker_id}")
async def get_alama_score(
    worker_id: str,
    include_factors: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Alama Score — Credit scoring without formal records."""
    start = time.monotonic()
    engine = IntelligenceEngine(db)
    result = await engine.generate_alama_score(worker_id_hash=worker_id)
    INTEL_GENERATION.labels(product="alama_score").observe(time.monotonic() - start)

    if not include_factors and "factors" in result:
        del result["factors"]
    return result


# ─── Angavu Pulse ─────────────────────────────────────────────────────────────

@router.get("/angavu-pulse/{region}")
async def get_angavu_pulse(
    region: str,
    period: str = Query("weekly", pattern="^(weekly|monthly|quarterly)$"),
    sector: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Angavu Pulse — MSME activity index."""
    start = time.monotonic()
    engine = IntelligenceEngine(db)
    result = await engine.generate_angavu_pulse(region=region, period=period, sector=sector)
    INTEL_GENERATION.labels(product="angavu_pulse").observe(time.monotonic() - start)
    return result


# ─── Jamii Insights ───────────────────────────────────────────────────────────

@router.get("/jamii-insights/{region}")
async def get_jamii_insights(
    region: str,
    dimension: Optional[str] = Query(None, description="Focus: savings, credit_access, digital_payments"),
    db: AsyncSession = Depends(get_db),
):
    """Jamii Insights — Financial inclusion analytics."""
    start = time.monotonic()
    engine = IntelligenceEngine(db)
    result = await engine.generate_jamii_insights(region=region, dimension=dimension)
    INTEL_GENERATION.labels(product="jamii_insights").observe(time.monotonic() - start)
    return result


# ─── Region Comparison ────────────────────────────────────────────────────────

@router.get("/compare")
async def compare_regions(
    regions: str = Query(..., description="Comma-separated geohash-5 codes"),
    db: AsyncSession = Depends(get_db),
):
    """Compare Angavu Pulse across multiple regions."""
    region_list = [r.strip() for r in regions.split(",")][:10]
    if len(region_list) < 2:
        raise HTTPException(400, "At least 2 regions required")

    engine = IntelligenceEngine(db)
    results = await engine.compare_regions(region_list)
    return {"product": "angavu-pulse", "comparison": results}
