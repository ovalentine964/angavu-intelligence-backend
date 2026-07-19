"""
Business report schemas.

These define the structure of reports generated for users.
Reports are delivered via WhatsApp, Telegram, SMS, or the app.
"""

from datetime import date, datetime

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
    category: str | None = None
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
    top_products: list[TopProduct] = Field(
        default_factory=list,
        max_length=10,
        description="Top 5 products by revenue",
    )

    # Time breakdown
    hourly_breakdown: list[HourlyBreakdown] = Field(
        default_factory=list,
        description="Sales by hour of day",
    )

    # Comparisons
    vs_yesterday_pct: float | None = Field(
        None,
        description="Percentage change vs yesterday's sales",
    )
    vs_last_week_avg_pct: float | None = Field(
        None,
        description="Percentage change vs last week's daily average",
    )

    # Insights
    busiest_hour: int | None = None
    peak_sales_amount: float | None = None

    # Inventory alerts
    low_stock_items: list[str] = Field(
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
    daily_summaries: list[TransactionSummary] = Field(
        default_factory=list,
        description="One summary per day of the week",
    )

    # Trends
    trends: list[WeeklyTrend] = Field(default_factory=list)

    # Top and bottom products
    top_products: list[TopProduct] = Field(default_factory=list, max_length=10)
    bottom_products: list[TopProduct] = Field(
        default_factory=list,
        max_length=5,
        description="Worst performing products",
    )

    # Patterns
    best_day: str | None = None
    worst_day: str | None = None
    busiest_hour: int | None = None

    # Payment method mix
    mpesa_pct: float = 0
    cash_pct: float = 0
    credit_pct: float = 0

    # Week-over-week comparison
    wow_sales_change_pct: float | None = None
    wow_profit_change_pct: float | None = None

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
    title_sw: str | None = Field(None, description="Swahili translation")
    detail: str
    detail_sw: str | None = None
    expected_impact: str | None = None
    action_items: list[str] = Field(default_factory=list)


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
    advice: list[AdviceItem] = Field(
        default_factory=list,
        max_length=5,
        description="Top 5 most impactful recommendations",
    )

    # Quick stats for context
    avg_daily_revenue_7d: float = 0
    avg_daily_profit_7d: float = 0
    revenue_trend: str = "stable"
    top_growing_category: str | None = None
    top_declining_category: str | None = None

    # Market context
    market_prices_summary: str | None = None

    language: str = "sw"
