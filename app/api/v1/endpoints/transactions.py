"""Transaction endpoints — CRUD + batch ingest."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.domain import Transaction
from app.models.schemas import (
    PaginatedResponse,
    PaginationParams,
    TransactionCreate,
    TransactionResponse,
)

router = APIRouter()


@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Record a single transaction."""
    txn = Transaction(
        user_id=user_id,
        amount=payload.amount,
        currency=payload.currency,
        category=payload.category,
        subcategory=payload.subcategory,
        merchant_category=payload.merchant_category,
        region=payload.region,
        lat=payload.lat,
        lon=payload.lon,
        channel=payload.channel,
        recorded_at=payload.recorded_at,
    )
    db.add(txn)
    await db.flush()
    return txn


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def create_transactions_batch(
    transactions: list[TransactionCreate],
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Batch ingest transactions (up to 500)."""
    if len(transactions) > 500:
        raise HTTPException(status_code=400, detail="Max 500 transactions per batch")

    txns = [
        Transaction(
            user_id=user_id,
            amount=t.amount,
            currency=t.currency,
            category=t.category,
            subcategory=t.subcategory,
            merchant_category=t.merchant_category,
            region=t.region,
            lat=t.lat,
            lon=t.lon,
            channel=t.channel,
            recorded_at=t.recorded_at,
        )
        for t in transactions
    ]
    db.add_all(txns)
    await db.flush()
    return {"inserted": len(txns)}


@router.get("/", response_model=PaginatedResponse)
async def list_transactions(
    user_id: uuid.UUID = Query(...),
    category: str | None = None,
    region: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List transactions with filters and pagination."""
    query = select(Transaction).where(Transaction.user_id == user_id)
    count_query = select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)

    if category:
        query = query.where(Transaction.category == category)
        count_query = count_query.where(Transaction.category == category)
    if region:
        query = query.where(Transaction.region == region)
        count_query = count_query.where(Transaction.region == region)
    if date_from:
        query = query.where(Transaction.recorded_at >= date_from)
        count_query = count_query.where(Transaction.recorded_at >= date_from)
    if date_to:
        query = query.where(Transaction.recorded_at <= date_to)
        count_query = count_query.where(Transaction.recorded_at <= date_to)

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Transaction.recorded_at.desc()).offset(offset).limit(page_size)
    )
    items = result.scalars().all()

    return PaginatedResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a single transaction by ID."""
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn
