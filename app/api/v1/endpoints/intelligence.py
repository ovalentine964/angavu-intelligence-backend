"""Intelligence report endpoints — all 15 revenue engines."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.domain import IntelligenceReport
from app.models.schemas import (
    IntelligenceQuery,
    IntelligenceReportResponse,
    PaginatedResponse,
)

router = APIRouter()

# All 15 revenue engine types
REPORT_TYPES = [
    "soko_pulse",       # FMCG demand forecasting
    "alama_score",      # Credit scoring 300-850
    "angavu_pulse",     # Government economic intelligence
    "distribution_intel",  # Supply chain optimization
    "fmcg_intelligence",   # Consumer goods analytics
    "market_heat_maps",    # Geographic demand visualization
    "price_index",         # Real-time pricing intelligence
    "trade_routes",        # Logistics optimization
    "vendor_score",        # Supplier reliability metrics
    "consumer_pulse",      # Demand pattern analysis
    "inventory_optimizer", # Stock level intelligence
    "cash_flow_predictor", # Working capital forecasting
    "risk_radar",          # Business risk assessment
    "growth_atlas",        # Market expansion intelligence
    "sector_benchmark",    # Industry comparison metrics
]


@router.get("/types")
async def list_report_types():
    """List all available intelligence product types."""
    return {"types": REPORT_TYPES}


@router.post("/query", response_model=list[IntelligenceReportResponse])
async def query_intelligence(
    query: IntelligenceQuery,
    db: AsyncSession = Depends(get_db),
):
    """Query intelligence reports by type, region, sector, and date range."""
    stmt = select(IntelligenceReport).where(
        IntelligenceReport.report_type == query.report_type
    )

    if query.region:
        stmt = stmt.where(IntelligenceReport.region == query.region)
    if query.sector:
        stmt = stmt.where(IntelligenceReport.sector == query.sector)
    if query.date_from:
        stmt = stmt.where(IntelligenceReport.published_at >= query.date_from)
    if query.date_to:
        stmt = stmt.where(IntelligenceReport.published_at <= query.date_to)

    stmt = stmt.order_by(IntelligenceReport.published_at.desc()).limit(query.limit)

    result = await db.execute(stmt)
    reports = result.scalars().all()
    return [IntelligenceReportResponse.model_validate(r) for r in reports]


@router.get("/{report_type}", response_model=PaginatedResponse)
async def get_reports_by_type(
    report_type: str,
    region: str | None = None,
    sector: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated intelligence reports for a specific product type."""
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}")

    stmt = select(IntelligenceReport).where(IntelligenceReport.report_type == report_type)
    count_stmt = (
        select(func.count())
        .select_from(IntelligenceReport)
        .where(IntelligenceReport.report_type == report_type)
    )

    if region:
        stmt = stmt.where(IntelligenceReport.region == region)
        count_stmt = count_stmt.where(IntelligenceReport.region == region)
    if sector:
        stmt = stmt.where(IntelligenceReport.sector == sector)
        count_stmt = count_stmt.where(IntelligenceReport.sector == sector)

    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        stmt.order_by(IntelligenceReport.published_at.desc()).offset(offset).limit(page_size)
    )
    items = result.scalars().all()

    return PaginatedResponse(
        items=[IntelligenceReportResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/report/{report_id}", response_model=IntelligenceReportResponse)
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a single intelligence report by ID."""
    result = await db.execute(
        select(IntelligenceReport).where(IntelligenceReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/generate/{report_type}")
async def trigger_report_generation(
    report_type: str,
    region: str = Query(...),
    sector: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger on-demand intelligence report generation."""
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}")

    # This dispatches to the appropriate intelligence engine
    from app.superagent.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    result = await orchestrator.execute_capability(
        capability=report_type,
        query=f"Generate {report_type} report for {region}" + (f" sector={sector}" if sector else ""),
        context={"region": region, "sector": sector, "trigger": "api"},
    )
    return result
