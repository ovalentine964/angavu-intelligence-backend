"""
Business report schemas.

These define the structure of reports generated for users.
Reports are delivered via WhatsApp, Telegram, SMS, or the app.
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TransactionSummary(BaseModel):
    """Summary statistics for a set of transactions."""

    total_sales: float = Field(0, description="Total sales amount in KES")
    total_purchases: float = Field(0, description="Total purchases in KES")
    total_expenses: float = Field(0, description="Total expenses in KES")
    gross_profit: float = Field(0, description="Sales minus purchases")
    net_profit: float = Field(0, description="Sales minus all costs")
    transaction_count: int = 0
    average_transaction_value: float = 0
    profit_margin_pct: float = Field(
        0,
        description="Net profit as percentage of sales",
    )


class TopProduct(BaseModel):
    """A top-performing product."""

    item: str
    category: Optional[str] = None
    quantity_sold: float = 0
    revenue: float = 0
    profit: float = 0
    transaction_count: int = 0
    avg_price: float = 0


class HourlyBreakdown(BaseModel):
    """Sales breakdown by hour of day."""

    hour: int = Field(..., ge=0, le=23)
    sales: float = 0
    transaction_count: int = 0


class DailyReport(BaseModel):
    """
    Daily business report for a user.

    Generated at end of business day (typically 7 PM EAT).
    Delivered via the user's preferred channel.
    """

    user_id: str
    report_date: date
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Core metrics
    summary: TransactionSummary

    # Top products
    top_products: List[TopProduct] = Field(
        default_factory=list,
        max_length=10,
        description="Top 5 products by revenue",
    )

    # Time breakdown
    hourly_breakdown: List[HourlyBreakdown] = Field(
        default_factory=list,
        description="Sales by hour of day",
    )

    # Comparisons
    vs_yesterday_pct: Optional[float] = Field(
        None,
        description="Percentage change vs yesterday's sales",
    )
    vs_last_week_avg_pct: Optional[float] = Field(
        None,
        description="Percentage change vs last week's daily average",
    )

    # Insights
    busiest_hour: Optional[int] = None
    peak_sales_amount: Optional[float] = None

    # Inventory alerts
    low_stock_items: List[str] = Field(
        default_factory=list,
        description="Items below restock threshold",
    )

    # Debt summary
    outstanding_debts_count: int = 0
    outstanding_debts_total: float = 0

    # Language for display
    language: str = "sw"


class WeeklyTrend(BaseModel):
    """A trend indicator for the week."""

    metric: str = Field(..., description="Metric name (sales, profit, etc.)")
    current_value: float
    previous_value: float
    change_pct: float
    direction: str = Field(
        ...,
        description="up, down, or stable",
        pattern=r"^(up|down|stable)$",
    )


class WeeklyReport(BaseModel):
    """
    Weekly business report.

    Generated every Monday morning. Shows trends, patterns,
    and actionable insights for the week ahead.
    """

    user_id: str
    week_start: date
    week_end: date
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Weekly summary
    summary: TransactionSummary

    # Daily breakdown
    daily_summaries: List[TransactionSummary] = Field(
        default_factory=list,
        description="One summary per day of the week",
    )

    # Trends
    trends: List[WeeklyTrend] = Field(default_factory=list)

    # Top and bottom products
    top_products: List[TopProduct] = Field(default_factory=list, max_length=10)
    bottom_products: List[TopProduct] = Field(
        default_factory=list,
        max_length=5,
        description="Worst performing products",
    )

    # Patterns
    best_day: Optional[str] = None
    worst_day: Optional[str] = None
    busiest_hour: Optional[int] = None

    # Payment method mix
    mpesa_pct: float = 0
    cash_pct: float = 0
    credit_pct: float = 0

    # Week-over-week comparison
    wow_sales_change_pct: Optional[float] = None
    wow_profit_change_pct: Optional[float] = None

    language: str = "sw"


class AdviceItem(BaseModel):
    """A single piece of business advice."""

    category: str = Field(
        ...,
        description="pricing, inventory, operations, marketing, finance",
    )
    priority: str = Field(
        "medium",
        pattern=r"^(low|medium|high|critical)$",
    )
    title: str
    title_sw: Optional[str] = Field(None, description="Swahili translation")
    detail: str
    detail_sw: Optional[str] = None
    expected_impact: Optional[str] = None
    action_items: List[str] = Field(default_factory=list)


class AdviceReport(BaseModel):
    """
    AI-generated business advice report.

    Based on analysis of the user's transaction patterns,
    inventory levels, and market context.
    """

    user_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Overall business health score (0-100)
    health_score: int = Field(..., ge=0, le=100)
    health_label: str = Field(
        ...,
        description="excellent, good, fair, needs_attention, critical",
    )

    # Specific advice items
    advice: List[AdviceItem] = Field(
        default_factory=list,
        max_length=5,
        description="Top 5 most impactful recommendations",
    )

    # Quick stats for context
    avg_daily_revenue_7d: float = 0
    avg_daily_profit_7d: float = 0
    revenue_trend: str = "stable"
    top_growing_category: Optional[str] = None
    top_declining_category: Optional[str] = None

    # Market context
    market_prices_summary: Optional[str] = None

    language: str = "sw"
