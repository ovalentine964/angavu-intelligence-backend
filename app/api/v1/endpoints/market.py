"""Market signal endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.domain import MarketSignal
from app.models.schemas import (
    MarketSignalCreate,
    MarketSignalResponse,
    PaginatedResponse,
)

router = APIRouter()


@router.post("/", response_model=MarketSignalResponse, status_code=201)
async def create_market_signal(
    payload: MarketSignalCreate,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a market signal."""
    signal = MarketSignal(
        signal_type=payload.signal_type,
        region=payload.region,
        sector=payload.sector,
        value=payload.value,
        confidence=payload.confidence,
        sample_size=payload.sample_size,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    db.add(signal)
    await db.flush()
    return signal


@router.get("/", response_model=PaginatedResponse)
async def list_market_signals(
    signal_type: str | None = None,
    region: str | None = None,
    sector: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List market signals with filters."""
    stmt = select(MarketSignal)
    count_stmt = select(func.count()).select_from(MarketSignal)

    if signal_type:
        stmt = stmt.where(MarketSignal.signal_type == signal_type)
        count_stmt = count_stmt.where(MarketSignal.signal_type == signal_type)
    if region:
        stmt = stmt.where(MarketSignal.region == region)
        count_stmt = count_stmt.where(MarketSignal.region == region)
    if sector:
        stmt = stmt.where(MarketSignal.sector == sector)
        count_stmt = count_stmt.where(MarketSignal.sector == sector)

    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        stmt.order_by(MarketSignal.created_at.desc()).offset(offset).limit(page_size)
    )
    items = result.scalars().all()

    return PaginatedResponse(
        items=[MarketSignalResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/aggregate")
async def aggregate_signals(
    signal_type: str = Query(...),
    region: str | None = None,
    sector: str | None = None,
    period_days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate market signals for dashboard consumption."""
    from datetime import timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
    stmt = select(
        MarketSignal.signal_type,
        MarketSignal.region,
        MarketSignal.sector,
        func.avg(MarketSignal.value).label("avg_value"),
        func.avg(MarketSignal.confidence).label("avg_confidence"),
        func.sum(MarketSignal.sample_size).label("total_samples"),
        func.count().label("signal_count"),
    ).where(
        MarketSignal.signal_type == signal_type,
        MarketSignal.created_at >= cutoff,
    )

    if region:
        stmt = stmt.where(MarketSignal.region == region)
    if sector:
        stmt = stmt.where(MarketSignal.sector == sector)

    stmt = stmt.group_by(
        MarketSignal.signal_type, MarketSignal.region, MarketSignal.sector
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "signal_type": r.signal_type,
            "region": r.region,
            "sector": r.sector,
            "avg_value": float(r.avg_value),
            "avg_confidence": float(r.avg_confidence),
            "total_samples": r.total_samples,
            "signal_count": r.signal_count,
        }
        for r in rows
    ]
