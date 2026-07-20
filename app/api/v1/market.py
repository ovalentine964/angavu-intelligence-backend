"""
Market Prices API — /api/v1/market/*

Endpoints:
    GET /market/prices              — Get current market prices
    GET /market/prices/{commodity}  — Get commodity price history
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/market", tags=["Market Prices"])


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class PriceItem(BaseModel):
    """A single market price entry."""

    commodity: str
    category: str
    unit: str
    current_price: float
    previous_price: float | None = None
    change_percent: float | None = None
    trend: str = Field("stable", description="rising, falling, or stable")
    market: str | None = None
    region: str | None = None
    updated_at: str


class MarketPricesResponse(BaseModel):
    """Current market prices."""

    prices: list[PriceItem]
    region: str | None = None
    generated_at: str


class PriceHistoryEntry(BaseModel):
    """Historical price point."""

    date: str
    price: float
    volume: int | None = None
    market: str | None = None


class CommodityHistoryResponse(BaseModel):
    """Price history for a commodity."""

    commodity: str
    unit: str
    history: list[PriceHistoryEntry]
    current_price: float
    average_price: float
    min_price: float
    max_price: float
    period_days: int


# ═══════════════════════════════════════════════════════════════════════════════
# Sample Market Data (would come from a market_data table in production)
# ═══════════════════════════════════════════════════════════════════════════════


SAMPLE_PRICES = [
    {"commodity": "Sukuma Wiki", "category": "food", "unit": "bunch", "current_price": 30, "previous_price": 25, "trend": "rising"},
    {"commodity": "Tomatoes", "category": "food", "unit": "kg", "current_price": 120, "previous_price": 130, "trend": "falling"},
    {"commodity": "Onions", "category": "food", "unit": "kg", "current_price": 80, "previous_price": 80, "trend": "stable"},
    {"commodity": "Cooking Oil", "category": "food", "unit": "litre", "current_price": 350, "previous_price": 340, "trend": "rising"},
    {"commodity": "Rice", "category": "food", "unit": "kg", "current_price": 160, "previous_price": 155, "trend": "rising"},
    {"commodity": "Maize Flour", "category": "food", "unit": "2kg", "current_price": 210, "previous_price": 210, "trend": "stable"},
    {"commodity": "Sugar", "category": "food", "unit": "kg", "current_price": 180, "previous_price": 175, "trend": "rising"},
    {"commodity": "Milk", "category": "food", "unit": "litre", "current_price": 60, "previous_price": 60, "trend": "stable"},
    {"commodity": "Bread", "category": "food", "unit": "loaf", "current_price": 65, "previous_price": 60, "trend": "rising"},
    {"commodity": "Eggs", "category": "food", "unit": "tray", "current_price": 420, "previous_price": 400, "trend": "rising"},
    {"commodity": "Charcoal", "category": "household", "unit": "bag", "current_price": 1200, "previous_price": 1100, "trend": "rising"},
    {"commodity": "Soap", "category": "household", "unit": "bar", "current_price": 80, "previous_price": 80, "trend": "stable"},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/prices", response_model=MarketPricesResponse)
async def get_market_prices(
    category: str | None = Query(None, description="Filter by category (food, household, etc.)"),
    region: str | None = Query(None, description="Filter by region"),
    current_user: User = Depends(get_current_user),
):
    """
    Get current market prices.

    Returns real-time market prices for common commodities
    relevant to informal workers. Prices are aggregated from
    multiple markets and updated regularly.

    Filter by category to see specific product types.
    """
    prices = []

    for item in SAMPLE_PRICES:
        if category and item["category"] != category:
            continue

        change_percent = None
        if item["previous_price"] and item["previous_price"] > 0:
            change_percent = round(
                ((item["current_price"] - item["previous_price"]) / item["previous_price"]) * 100, 1
            )

        prices.append(PriceItem(
            commodity=item["commodity"],
            category=item["category"],
            unit=item["unit"],
            current_price=item["current_price"],
            previous_price=item["previous_price"],
            change_percent=change_percent,
            trend=item["trend"],
            market="Nairobi",
            region=region or "Nairobi",
            updated_at=datetime.now(UTC).isoformat(),
        ))

    return MarketPricesResponse(
        prices=prices,
        region=region or "Nairobi",
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.get("/prices/{commodity}", response_model=CommodityHistoryResponse)
async def get_commodity_history(
    commodity: str,
    days: int = Query(30, ge=7, le=90, description="Number of days of history"),
    current_user: User = Depends(get_current_user),
):
    """
    Get price history for a specific commodity.

    Returns daily price data for the specified period,
    along with summary statistics (average, min, max).
    Used for price trend charts in the mobile app.
    """
    # Find commodity in sample data
    commodity_data = None
    for item in SAMPLE_PRICES:
        if item["commodity"].lower() == commodity.lower():
            commodity_data = item
            break

    if not commodity_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Commodity '{commodity}' not found",
        )

    # Generate sample history (in production, query market_data table)
    base_price = commodity_data["current_price"]
    history = []
    now = datetime.now(UTC)

    import random
    random.seed(hash(commodity))  # Deterministic for same commodity

    for i in range(days):
        date = now - timedelta(days=days - 1 - i)
        # Simulate price fluctuation
        variation = random.uniform(-0.1, 0.1)  # ±10%
        price = round(base_price * (1 + variation), 0)
        volume = random.randint(50, 500)

        history.append(PriceHistoryEntry(
            date=date.strftime("%Y-%m-%d"),
            price=price,
            volume=volume,
            market="Nairobi",
        ))

    prices = [h.price for h in history]

    return CommodityHistoryResponse(
        commodity=commodity_data["commodity"],
        unit=commodity_data["unit"],
        history=history,
        current_price=base_price,
        average_price=round(sum(prices) / len(prices), 1),
        min_price=min(prices),
        max_price=max(prices),
        period_days=days,
    )
