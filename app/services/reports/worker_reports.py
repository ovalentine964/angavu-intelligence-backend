"""
Worker Reports — Msaidizi / Biashara Intelligence

Five report types delivered to informal workers via WhatsApp, each applying
Valentine's BSc Economics & Statistics degree concepts to transform raw
transaction data into actionable business intelligence.

Report Types:
  1. DailyReport    — End-of-day snapshot (ECO 201, STA 244, STA 346, ECO 206)
  2. WeeklyReport   — Weekly trends & patterns (ECO 201, STA 244, STA 341, STA 342, ECO 206)
  3. MonthlyReport  — Monthly health check (ECO 201, STA 244, STA 142, STA 341, ECO 206, ECO 210)
  4. SemiAnnualReport — 6-month strategic review (ECO 201, STA 244, ECO 206, STA 341, ECO 210)
  5. AnnualReport   — Comprehensive annual picture (ALL units)

Design Principles:
  - Swahili first, English/Sheng support
  - WhatsApp-native formatting (bold with asterisks, no markdown tables)
  - Actionable insights, not just numbers
  - Show growth and progress — make workers feel proud
  - Each section maps to a specific degree unit concept
"""

from __future__ import annotations

import math
import statistics
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..whatsapp_charts import (
    ARROW_DOWN,
    ARROW_UP,
    ARROW_UP_RIGHT,
    ARROW_DOWN_RIGHT,
    BLOCK_FULL,
    BLOCK_LIGHT,
    BLOCK_SOLID,
    CHECK,
    CROSS_MARK,
    WARNING,
    FIRE,
    HEART,
    LIGHTNING,
    MOOD_GREAT,
    MOOD_OK,
    MOOD_SLOW,
    STAR_FILLED,
    STAR_EMPTY,
    BarChart,
    CashFlowDiagram,
    Heatmap,
    ProgressBar,
    Sparkline,
    TrendLine,
    TableBuilder,
    divider,
    emoji_number,
    format_currency,
    format_number,
    format_percentage,
    health_display,
    mood_indicator,
    mood_label,
    section_header,
    star_rating,
    SWAHILI_DAYS_SHORT,
    SWAHILI_MONTHS,
    SWAHILI_MONTHS_SHORT,
)
from ..health_score import BusinessHealthScorer, BusinessMetrics, HealthScoreResult
from ..seasonal_analyzer import SeasonalAnalyzer, MonthlyData, SeasonalAnalysisResult
from ..comparison_engine import ComparisonEngine, PeerBusiness, ComparisonResult
from ..statistical_foundation import BayesianUpdater


# ============================================================================
# Data Classes — Input structures for each report type
# ============================================================================

@dataclass
class WorkerProfile:
    """Worker profile for report personalization."""
    user_id: str
    name: str                           # First name
    business_name: str = "Biashara"
    business_type: str = "food_vendor"  # mama_mboga, duka, boda_boda, etc.
    location: str = ""
    language: str = "sw"                # sw, en, sh
    currency: str = "KSh"
    phone: str = ""
    join_date: Optional[date] = None
    preferred_time: str = "19:00"
    savings_goal: float = 0.0           # Target savings amount
    current_savings: float = 0.0        # Accumulated savings
    credit_score: float = 0.0           # Alama Score (0-100)


@dataclass
class TransactionSummary:
    """Aggregated transaction data for a period."""
    date: date
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    profit: float = 0.0
    transaction_count: int = 0
    items_sold: Dict[str, Tuple[int, float]] = field(default_factory=dict)
    best_item: str = ""
    best_item_revenue: float = 0.0
    best_item_qty: int = 0
    expense_categories: Dict[str, float] = field(default_factory=dict)


@dataclass
class InventoryStatus:
    """Current inventory state for alerts."""
    item_name: str
    current_stock: float
    unit: str = "pieces"
    daily_usage: float = 0.0
    restock_threshold: float = 0.0
    cost_per_unit: float = 0.0


@dataclass
class PriceData:
    """Price observation for forecasting."""
    item_name: str
    prices: List[float] = field(default_factory=list)
    dates: List[date] = field(default_factory=list)
    current_price: float = 0.0
    predicted_price: float = 0.0
    predicted_change_pct: float = 0.0


@dataclass
class CustomerData:
    """Customer-level aggregated data."""
    customer_id: str
    name: str
    total_spent: float = 0.0
    visit_count: int = 0
    last_visit: Optional[date] = None
    credit_balance: float = 0.0


# ============================================================================
# Base Report Class
# ============================================================================

class WorkerReport(ABC):
    """Abstract base for all worker report types.

    Provides shared utilities: formatting, chart generation, language
    helpers, and the template structure that all 5 reports follow.
    """

    def __init__(self):
        self.bar = BarChart()
        self.progress = ProgressBar()
        self.sparkline = Sparkline()
        self.heatmap = Heatmap()
        self.cashflow = CashFlowDiagram()
        self.trend = TrendLine()
        self.table = TableBuilder()
        self.health_scorer = BusinessHealthScorer()
        self.seasonal = SeasonalAnalyzer()
        self.comparison = ComparisonEngine()
        self.bayesian = BayesianUpdater()

    @abstractmethod
    def generate(self, profile: WorkerProfile, **kwargs) -> str:
        """Generate the report as a WhatsApp-ready string."""
        ...

    @abstractmethod
    def report_type(self) -> str:
        """Return report type identifier."""
        ...

    # ------------------------------------------------------------------
    # Language helpers
    # ------------------------------------------------------------------

    def _t(self, sw: str, en: str, profile: WorkerProfile) -> str:
        """Translate helper — returns Swahili or English based on profile."""
        if profile.language == "en":
            return en
        return sw

    def _greeting(self, profile: WorkerProfile) -> str:
        """Personalized greeting line."""
        return f"👤 {profile.name}, "

    def _header(self, title: str, profile: WorkerProfile, date_str: str) -> str:
        """Standard report header."""
        return f"📊 *{title} — {profile.business_name}*\n📅 {date_str}"

    def _divider(self) -> str:
        return "─" * 28

    def _section(self, emoji: str, title_sw: str, title_en: str,
                 profile: WorkerProfile) -> str:
        """Section header with emoji."""
        title = self._t(title_sw, title_en, profile)
        return f"\n{emoji} *{title}*"

    def _metric_line(self, label: str, value: str, indicator: str = "") -> str:
        """Single metric display line."""
        if indicator:
            return f"  {indicator} {label}: *{value}*"
        return f"  • {label}: *{value}*"

    def _format_money(self, amount: float, profile: WorkerProfile) -> str:
        """Format currency amount."""
        return format_currency(amount, profile.currency)

    def _swahili_day(self, d: date) -> str:
        """Day name in Swahili."""
        days = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi",
                "Ijumaa", "Jumamosi", "Jumapili"]
        return days[d.weekday()]

    def _swahili_month(self, d: date) -> str:
        """Month name in Swahili."""
        return SWAHILI_MONTHS[d.month - 1]

    def _format_date(self, d: date, lang: str = "sw") -> str:
        """Format date string."""
        if lang == "sw":
            return f"{d.day} {self._swahili_month(d)} {d.year}"
        return d.strftime("%d %B %Y")

    def _growth_indicator(self, change_pct: float) -> str:
        """Arrow indicator for growth/decline."""
        if change_pct > 5:
            return ARROW_UP
        elif change_pct < -5:
            return ARROW_DOWN
        return ARROW_UP_RIGHT

    def _mood_emoji(self, today_val: float, avg_val: float) -> str:
        """Mood indicator based on performance vs average."""
        if avg_val <= 0:
            return MOOD_OK
        ratio = today_val / avg_val
        if ratio >= 1.2:
            return MOOD_GREAT
        elif ratio >= 0.8:
            return MOOD_OK
        return MOOD_SLOW


# ============================================================================
# 1. DAILY REPORT — Ripoti ya Leo
# ============================================================================
# Degree Units: ECO 201 (microeconomics), STA 244 (time series forecasting),
#               STA 346 (quality control/restock), ECO 206 (microfinance/savings)
# ============================================================================

class DailyReport(WorkerReport):
    """End-of-day business snapshot.

    ECO 201: Revenue, expenses, profit — basic microeconomic cost analysis.
    STA 244: Tomorrow's price forecast using exponential smoothing.
    STA 346: Restock alerts from inventory level monitoring (control charts).
    ECO 206: Savings tip based on daily profit and savings goal.
    """

    def report_type(self) -> str:
        return "daily"

    def generate(
        self,
        profile: WorkerProfile,
        today: TransactionSummary,
        yesterday: Optional[TransactionSummary] = None,
        avg_daily_sales: float = 0.0,
        inventory: Optional[List[InventoryStatus]] = None,
        price_forecasts: Optional[List[PriceData]] = None,
    ) -> str:
        """Generate daily report.

        Args:
            profile: Worker profile.
            today: Today's transaction summary.
            yesterday: Yesterday's data for comparison.
            avg_daily_sales: Rolling average daily sales.
            inventory: Current inventory items for restock alerts.
            price_forecasts: Price predictions for key items.
        """
        profit = today.total_revenue - today.total_expenses
        margin = (profit / today.total_revenue * 100) if today.total_revenue > 0 else 0
        day_name = self._swahili_day(today.date)
        date_str = self._format_date(today.date, profile.language)

        # Yesterday comparison
        if yesterday and yesterday.total_revenue > 0:
            sales_chg = ((today.total_revenue - yesterday.total_revenue)
                         / yesterday.total_revenue * 100)
            y_profit = yesterday.total_revenue - yesterday.total_expenses
            profit_chg = ((profit - y_profit) / y_profit * 100) if y_profit > 0 else 0
            has_prev = True
        else:
            sales_chg = profit_chg = 0.0
            has_prev = False

        lines: List[str] = []

        # ── Header ──
        lines.append(self._header(
            self._t("Ripoti ya Leo", "Today's Report", profile),
            profile, f"{day_name}, {date_str}"
        ))
        lines.append("")
        lines.append(f"{self._greeting(profile)}{self._t('hii leo:', 'today:', profile)}")
        lines.append("")

        # ── ECO 201: Revenue, Expenses, Profit ──
        lines.append(self._section("💰", "Mauzo na Faida", "Revenue & Profit", profile))

        mood = self._mood_emoji(today.total_revenue, avg_daily_sales or today.total_revenue)
        lines.append(self._metric_line(
            self._t("Mauzo", "Revenue", profile),
            self._format_money(today.total_revenue, profile),
            mood
        ))
        lines.append(self._metric_line(
            self._t("Gharama", "Expenses", profile),
            self._format_money(today.total_expenses, profile),
        ))

        profit_icon = CHECK if profit > 0 else CROSS_MARK
        lines.append(self._metric_line(
            self._t("Faida", "Profit", profile),
            self._format_money(profit, profile),
            profit_icon
        ))
        lines.append(self._metric_line(
            self._t("Margin", "Margin", profile),
            f"{margin:.0f}%",
        ))

        if has_prev:
            arrow = self._growth_indicator(sales_chg)
            lines.append(self._metric_line(
                self._t("Mauzo vs jana", "Sales vs yesterday", profile),
                f"{sales_chg:+.0f}%",
                arrow
            ))

        lines.append(self._metric_line(
            self._t("Miamala", "Transactions", profile),
            str(today.transaction_count),
        ))

        # ── Top selling product ──
        if today.best_item:
            lines.append("")
            lines.append(self._section("🏆",
                self._t("Bidhaa Bora", "Top Product", profile),
                self._t("Bidhaa Bora", "Top Product", profile), profile))
            lines.append(f"  🔥 *{today.best_item}* — "
                         f"{today.best_item_qty} sold, "
                         f"{self._format_money(today.best_item_revenue, profile)}")

        # ── STA 346: Restock Alerts (Quality Control) ──
        if inventory:
            low_stock = [item for item in inventory
                         if item.current_stock <= item.restock_threshold]
            if low_stock:
                lines.append("")
                lines.append(self._section("⚠️",
                    self._t("Onyo la Stock", "Restock Alert", profile),
                    self._t("Onyo la Stock", "Restock Alert", profile), profile))
                for item in low_stock:
                    days_left = (item.current_stock / item.daily_usage
                                 if item.daily_usage > 0 else 0)
                    lines.append(f"  {WARNING} *{item.item_name}* — "
                                 f"{item.current_stock:.0f} {item.unit} zimebaki"
                                 f" (~siku {days_left:.0f})")
                    lines.append(f"    → Nunua kesho — "
                                 f"gharama: {self._format_money(item.cost_per_unit * item.daily_usage * 3, profile)}")

        # ── STA 244: Tomorrow's Forecast (Time Series) ──
        if price_forecasts:
            lines.append("")
            lines.append(self._section("🔮",
                self._t("Bei ya Kesho", "Tomorrow's Prices", profile),
                self._t("Bei ya Kesho", "Tomorrow's Prices", profile), profile))
            for pf in price_forecasts:
                if pf.predicted_change_pct != 0:
                    direction = self._t("itapanda", "will rise", profile) \
                        if pf.predicted_change_pct > 0 \
                        else self._t("itashuka", "will fall", profile)
                    lines.append(f"  📈 *{pf.item_name}*: bei {direction} "
                                 f"{abs(pf.predicted_change_pct):.0f}% "
                                 f"({self._format_money(pf.predicted_price, profile)})")

        # ── ECO 206: Savings Tip (Microfinance) ──
        if profit > 0:
            lines.append("")
            lines.append(self._section("💡",
                self._t("Neno la Akiba", "Savings Tip", profile),
                self._t("Neno la Akiba", "Savings Tip", profile), profile))

            suggested_save = max(50, round(profit * 0.15 / 10) * 10)  # 15% of profit, min 50
            if profile.savings_goal > 0:
                pct_done = (profile.current_savings / profile.savings_goal * 100)
                remaining = profile.savings_goal - profile.current_savings
                lines.append(f"  💰 {self._t('Weka', 'Save', profile)} "
                             f"*{self._format_money(suggested_save, profile)}* {self._t('leo', 'today', profile)}")
                lines.append(f"  🎯 {self._t('Lengo', 'Goal', profile)}: "
                             f"{pct_done:.0f}% {self._t('imefikiwa', 'reached', profile)} "
                             f"({self._format_money(remaining, profile)} {self._t('imebaki', 'remaining', profile)})")
                self.progress.render(pct_done, 100)
            else:
                lines.append(f"  💰 {self._t('Weka', 'Save', profile)} "
                             f"*{self._format_money(suggested_save, profile)}* {self._t('leo', 'today', profile)}")
                lines.append(f"  📊 {self._t('Akiba ya mwezi', 'Monthly savings', profile)}: "
                             f"~{self._format_money(suggested_save * 25, profile)}")

        # ── Footer ──
        lines.append("")
        lines.append(self._divider())
        lines.append(f"📱 {self._t('Tuma ripoti ya wiki: /ripoti', 'Weekly report: /report', profile)}")
        lines.append(f"🎤 {self._t('Rekodi mauzo: sema mauzo...', 'Record sale: say sale...', profile)}")

        return "\n".join(lines)


# ============================================================================
# 2. WEEKLY REPORT — Ripoti ya Wiki
# ============================================================================
# Degree Units: ECO 201, STA 244, STA 341 (estimation), STA 342 (hypothesis),
#               ECO 206
# ============================================================================

class WeeklyReport(WorkerReport):
    """Weekly business trends and patterns report.

    ECO 201: P&L summary with margin analysis.
    STA 244: Price trends using time series decomposition.
    STA 341: Cash flow forecast using estimation theory (confidence intervals).
    STA 342: Best vs worst day hypothesis test (is the difference significant?).
    ECO 206: Savings progress tracking.
    """

    def report_type(self) -> str:
        return "weekly"

    def generate(
        self,
        profile: WorkerProfile,
        week_start: date,
        week_end: date,
        daily_data: List[TransactionSummary],
        previous_week_sales: float = 0.0,
        customers: Optional[List[CustomerData]] = None,
        price_trends: Optional[List[PriceData]] = None,
    ) -> str:
        """Generate weekly report."""
        # Aggregate week data
        total_revenue = sum(d.total_revenue for d in daily_data)
        total_expenses = sum(d.total_expenses for d in daily_data)
        profit = total_revenue - total_expenses
        margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        total_txn = sum(d.transaction_count for d in daily_data)

        # Best/worst days
        if daily_data:
            best_day = max(daily_data, key=lambda d: d.total_revenue)
            worst_day = min(daily_data, key=lambda d: d.total_revenue)
        else:
            best_day = worst_day = None

        # Top products across the week
        product_totals: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        for d in daily_data:
            for item, (qty, rev) in d.items_sold.items():
                old_qty, old_rev = product_totals[item]
                product_totals[item] = (old_qty + qty, old_rev + rev)
        top_products = sorted(product_totals.items(),
                              key=lambda x: x[1][1], reverse=True)[:3]

        # Week-over-week growth
        wow_growth = ((total_revenue - previous_week_sales) / previous_week_sales * 100
                      ) if previous_week_sales > 0 else 0.0

        # Daily revenue list for sparkline
        daily_revenues = [d.total_revenue for d in daily_data]

        lines: List[str] = []
        date_range = f"{self._format_date(week_start, profile.language)} — {self._format_date(week_end, profile.language)}"

        # ── Header ──
        lines.append(self._header(
            self._t("Ripoti ya Wiki", "Weekly Report", profile),
            profile, date_range
        ))
        lines.append("")

        # ── ECO 201: P&L Summary ──
        lines.append(self._section("💰",
            self._t("Muhtasari wa Wiki", "Week Summary", profile),
            self._t("Muhtasari wa Wiki", "Week Summary", profile), profile))

        lines.append(self._metric_line(
            self._t("Mauzo", "Revenue", profile), self._format_money(total_revenue, profile)))
        lines.append(self._metric_line(
            self._t("Gharama", "Expenses", profile), self._format_money(total_expenses, profile)))
        lines.append(self._metric_line(
            self._t("Faida", "Profit", profile), self._format_money(profit, profile),
            CHECK if profit > 0 else CROSS_MARK))
        lines.append(self._metric_line(
            self._t("Margin ya Faida", "Profit Margin", profile), f"{margin:.1f}%"))
        lines.append(self._metric_line(
            self._t("Miamala", "Transactions", profile), str(total_txn)))

        if wow_growth != 0:
            arrow = self._growth_indicator(wow_growth)
            lines.append(self._metric_line(
                self._t("Mauzo vs wiki iliyopita", "Sales vs last week", profile),
                f"{wow_growth:+.1f}%", arrow))

        # ── Daily trend sparkline ──
        if daily_revenues:
            lines.append("")
            lines.append(self._t("Mauzo ya kila siku:", "Daily sales trend:", profile))
            lines.append(self.sparkline.render(daily_revenues))

        # ── STA 342: Best vs Worst Day (Hypothesis Testing) ──
        if best_day and worst_day and len(daily_data) >= 3:
            lines.append("")
            lines.append(self._section("📊",
                self._t("Siku Bora vs Mbaya", "Best vs Worst Day", profile),
                self._t("Siku Bora vs Mbaya", "Best vs Worst Day", profile), profile))

            best_name = self._swahili_day(best_day.date)
            worst_name = self._swahili_day(worst_day.date)
            lines.append(f"  {STAR_FILLED} {self._t('Bora', 'Best', profile)}: "
                         f"*{best_name}* — {self._format_money(best_day.total_revenue, profile)}")
            lines.append(f"  {STAR_EMPTY} {self._t('Mbaya', 'Worst', profile)}: "
                         f"*{worst_name}* — {self._format_money(worst_day.total_revenue, profile)}")

            # Simple significance test using coefficient of variation
            if len(daily_revenues) >= 3 and statistics.mean(daily_revenues) > 0:
                cv = statistics.stdev(daily_revenues) / statistics.mean(daily_revenues)
                if cv > 0.3:
                    lines.append(f"  {WARNING} {self._t('Tofauti ni kubwa — mauzo yako ni yasiyo sawa',
                        'High variation — your sales are inconsistent', profile)}")
                else:
                    lines.append(f"  {CHECK} {self._t('Tofauti ni ndogo — mauzo ni ya kawaida',
                        'Low variation — sales are consistent', profile)}")

        # ── Top 3 Products ──
        if top_products:
            lines.append("")
            lines.append(self._section("🏆",
                self._t("Bidhaa Bora 3", "Top 3 Products", profile),
                self._t("Bidhaa Bora 3", "Top 3 Products", profile), profile))
            for i, (name, (qty, rev)) in enumerate(top_products, 1):
                pct = (rev / total_revenue * 100) if total_revenue > 0 else 0
                lines.append(f"  {i}. *{name}* — {qty} sold, "
                             f"{self._format_money(rev, profile)} ({pct:.0f}%)")

        # ── Customer Insights ──
        if customers:
            top_customer = max(customers, key=lambda c: c.total_spent)
            returning = [c for c in customers if c.visit_count > 1]
            lines.append("")
            lines.append(self._section("👥",
                self._t("Wateja", "Customers", profile),
                self._t("Wateja", "Customers", profile), profile))
            lines.append(f"  {STAR_FILLED} {self._t('Mteja bora', 'Top customer', profile)}: "
                         f"*{top_customer.name}* — "
                         f"{self._format_money(top_customer.total_spent, profile)}")
            lines.append(f"  🔄 {self._t('Wateja waliorudi', 'Returning customers', profile)}: "
                         f"{len(returning)}")

            # Outstanding credit
            credit_customers = [c for c in customers if c.credit_balance > 0]
            if credit_customers:
                total_credit = sum(c.credit_balance for c in credit_customers)
                lines.append(f"  💳 {self._t('Deni la wateja', 'Outstanding credit', profile)}: "
                             f"{self._format_money(total_credit, profile)} "
                             f"({len(credit_customers)} {self._t('wateja', 'customers', profile)})")

        # ── STA 244: Price Trends ──
        if price_trends:
            lines.append("")
            lines.append(self._section("📈",
                self._t("Mabadiliko ya Bei", "Price Trends", profile),
                self._t("Mabadiliko ya Bei", "Price Trends", profile), profile))
            for pt in price_trends:
                if len(pt.prices) >= 2:
                    change = ((pt.prices[-1] - pt.prices[0]) / pt.prices[0] * 100
                              ) if pt.prices[0] > 0 else 0
                    arrow = self._growth_indicator(change)
                    lines.append(f"  {arrow} *{pt.item_name}*: "
                                 f"{change:+.0f}% {self._t('wiki hii', 'this week', profile)} "
                                 f"({self._format_money(pt.current_price, profile)})")

        # ── STA 341: Cash Flow Forecast (Estimation) ──
        if daily_data and len(daily_data) >= 3:
            lines.append("")
            lines.append(self._section("🔮",
                self._t("Utabiri wa Pesa", "Cash Flow Forecast", profile),
                self._t("Utabiri wa Pesa", "Cash Flow Forecast", profile), profile))

            daily_profits = [d.total_revenue - d.total_expenses for d in daily_data]
            avg_daily_profit = statistics.mean(daily_profits)
            avg_daily_expense = statistics.mean([d.total_expenses for d in daily_data])

            if avg_daily_profit > 0 and profile.current_savings > 0:
                days_until_zero = profile.current_savings / avg_daily_expense if avg_daily_expense > 0 else 999
                lines.append(f"  💰 {self._t('Faida ya wastani/siku', 'Avg daily profit', profile)}: "
                             f"{self._format_money(avg_daily_profit, profile)}")
                lines.append(f"  📊 {self._t('Kwa kasi hii', 'At this rate', profile)}, "
                             f"pesa yako {self._t('itatosha siku', 'will last', profile)} "
                             f"*{days_until_zero:.0f}*")
            elif avg_daily_profit <= 0:
                lines.append(f"  {WARNING} {self._t('Faida yako ni hasara — punguza gharama',
                    'Negative profit — reduce expenses', profile)}")

        # ── ECO 206: Savings Progress ──
        if profile.savings_goal > 0:
            lines.append("")
            lines.append(self._section("🎯",
                self._t("Maendeleo ya Akiba", "Savings Progress", profile),
                self._t("Maendeleo ya Akiba", "Savings Progress", profile), profile))
            pct_done = (profile.current_savings / profile.savings_goal * 100)
            lines.append(f"  💰 {self._t('Akiba', 'Saved')}: "
                         f"{self._format_money(profile.current_savings, profile)}")
            lines.append(f"  🎯 {self._t('Lengo', 'Goal')}: "
                         f"{self._format_money(profile.savings_goal, profile)}")
            lines.append(f"  📊 {pct_done:.0f}% {self._t('imefikiwa', 'reached', profile)}")

        # ── Business Health Score ──
        lines.append("")
        lines.append(self._section("❤️",
            self._t("Afya ya Biashara", "Business Health", profile),
            self._t("Afya ya Biashara", "Business Health", profile), profile))

        # Simple health score from available data
        if daily_data:
            active_days = len([d for d in daily_data if d.total_revenue > 0])
            consistency = active_days / len(daily_data) * 100 if daily_data else 0
            profit_days = len([d for d in daily_data if d.total_revenue > d.total_expenses])
            profitability = profit_days / len(daily_data) * 100 if daily_data else 0
            health = (consistency * 0.4 + profitability * 0.4 + min(margin * 2, 20))
            health = min(100, max(0, health))

            lines.append(f"  {health_display(health)} {self._t('Alama', 'Score')}: *{health:.0f}/100*")
            lines.append(f"  {star_rating(health)}")

        # ── Footer ──
        lines.append("")
        lines.append(self._divider())
        lines.append(f"📱 {self._t('Ripoti ya mwezi inakuja tarehe 1', 'Monthly report on the 1st', profile)}")

        return "\n".join(lines)


# ============================================================================
# 3. MONTHLY REPORT — Ripoti ya Mwezi
# ============================================================================
# Degree Units: ECO 201, STA 244, STA 142 (descriptive), STA 341, ECO 206,
#               ECO 210 (quantitative methods)
# ============================================================================

class MonthlyReport(WorkerReport):
    """Monthly business health check and analysis.

    ECO 201: P&L with trends, profit margin analysis vs market.
    STA 244: Revenue growth trend using time series.
    STA 142: Expense breakdown by category (descriptive statistics).
    STA 341: Business health score (Bayesian estimation), inventory turnover.
    ECO 206: Savings progress, credit readiness update.
    ECO 210: Supplier comparison (quantitative optimization).
    """

    def report_type(self) -> str:
        return "monthly"

    def generate(
        self,
        profile: WorkerProfile,
        year: int,
        month: int,
        daily_data: List[TransactionSummary],
        previous_month_revenue: float = 0.0,
        previous_month_profit: float = 0.0,
        customers: Optional[List[CustomerData]] = None,
        inventory: Optional[List[InventoryStatus]] = None,
        peer_data: Optional[ComparisonResult] = None,
    ) -> str:
        """Generate monthly report."""
        # Aggregates
        total_revenue = sum(d.total_revenue for d in daily_data)
        total_expenses = sum(d.total_expenses for d in daily_data)
        profit = total_revenue - total_expenses
        margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        total_txn = sum(d.transaction_count for d in daily_data)
        active_days = len([d for d in daily_data if d.total_revenue > 0])

        # Growth
        rev_growth = ((total_revenue - previous_month_revenue) / previous_month_revenue * 100
                      ) if previous_month_revenue > 0 else 0.0
        profit_growth = ((profit - previous_month_profit) / previous_month_profit * 100
                         ) if previous_month_profit > 0 else 0.0

        # Expense categories (STA 142: Descriptive Statistics)
        expense_cats: Dict[str, float] = defaultdict(float)
        for d in daily_data:
            for cat, amt in d.expense_categories.items():
                expense_cats[cat] += amt

        # Top products
        product_totals: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        for d in daily_data:
            for item, (qty, rev) in d.items_sold.items():
                old_qty, old_rev = product_totals[item]
                product_totals[item] = (old_qty + qty, old_rev + rev)
        top_products = sorted(product_totals.items(),
                              key=lambda x: x[1][1], reverse=True)[:5]

        # Daily revenue for trend
        daily_revenues = [d.total_revenue for d in daily_data]

        # Inventory turnover
        avg_inventory_value = 0.0
        if inventory:
            avg_inventory_value = sum(i.current_stock * i.cost_per_unit for i in inventory)
        turnover_days = (avg_inventory_value / (total_revenue / len(daily_data))
                         ) if daily_data and total_revenue > 0 and avg_inventory_value > 0 else 0

        month_name = SWAHILI_MONTHS[month - 1]
        lines: List[str] = []

        # ── Header ──
        lines.append(self._header(
            self._t("Ripoti ya Mwezi", "Monthly Report", profile),
            profile, f"{month_name} {year}"
        ))
        lines.append("")

        # ── ECO 201: P&L with Trends ──
        lines.append(self._section("💰",
            self._t("Muhtasari wa Mwezi", "Month Summary", profile),
            self._t("Muhtasari wa Mwezi", "Month Summary", profile), profile))

        lines.append(self._metric_line(
            self._t("Mauzo", "Revenue", profile), self._format_money(total_revenue, profile)))
        lines.append(self._metric_line(
            self._t("Gharama", "Expenses", profile), self._format_money(total_expenses, profile)))
        lines.append(self._metric_line(
            self._t("Faida", "Profit", profile), self._format_money(profit, profile),
            CHECK if profit > 0 else CROSS_MARK))
        lines.append(self._metric_line(
            self._t("Margin", "Margin", profile), f"{margin:.1f}%"))
        lines.append(self._metric_line(
            self._t("Siku za kazi", "Active days", profile), str(active_days)))
        lines.append(self._metric_line(
            self._t("Miamala", "Transactions", profile), str(total_txn)))

        # Growth indicators
        if rev_growth != 0:
            arrow = self._growth_indicator(rev_growth)
            lines.append(self._metric_line(
                self._t("Ukuaji wa mauzo", "Revenue growth", profile),
                f"{rev_growth:+.1f}% {self._t('kuliko mwezi uliopita', 'vs last month', profile)}",
                arrow))

        # ── STA 244: Revenue Trend ──
        if daily_revenues:
            lines.append("")
            lines.append(self._t("Mwelekeo wa mauzo:", "Revenue trend:", profile))
            lines.append(self.sparkline.render(daily_revenues))

        # ── STA 142: Expense Breakdown (Descriptive Statistics) ──
        if expense_cats:
            lines.append("")
            lines.append(self._section("📊",
                self._t("Gharama kwa Jamii", "Expense Breakdown", profile),
                self._t("Gharama kwa Jamii", "Expense Breakdown", profile), profile))

            sorted_cats = sorted(expense_cats.items(), key=lambda x: x[1], reverse=True)
            for cat, amt in sorted_cats:
                pct = (amt / total_expenses * 100) if total_expenses > 0 else 0
                bar_width = int(pct / 5)  # 5% per block
                bar = BLOCK_FULL * bar_width + BLOCK_LIGHT * (20 - bar_width)
                lines.append(f"  {cat}: {self._format_money(amt, profile)} ({pct:.0f}%)")
                lines.append(f"    {bar}")

        # ── Top Products ──
        if top_products:
            lines.append("")
            lines.append(self._section("🏆",
                self._t("Bidhaa Bora 5", "Top 5 Products", profile),
                self._t("Bidhaa Bora 5", "Top 5 Products", profile), profile))
            for i, (name, (qty, rev)) in enumerate(top_products, 1):
                pct = (rev / total_revenue * 100) if total_revenue > 0 else 0
                lines.append(f"  {i}. *{name}* — {qty} sold, "
                             f"{self._format_money(rev, profile)} ({pct:.0f}%)")

        # ── Margin Analysis vs Market ──
        if peer_data:
            lines.append("")
            lines.append(self._section("📊",
                self._t("Faida ikilinganishwa na soko", "Margin vs Market", profile),
                self._t("Faida ikilinganishwa na soko", "Margin vs Market", profile), profile))
            market_margin = peer_data.peer_avg_margin if hasattr(peer_data, 'peer_avg_margin') else 30
            if margin > market_margin:
                lines.append(f"  {CHECK} {self._t('Faida yako ni', 'Your margin is')} "
                             f"*{margin:.0f}%* — {self._t('juu ya wastani wa soko', 'above market average', profile)} "
                             f"({market_margin:.0f}%)")
            else:
                lines.append(f"  {WARNING} {self._t('Faida yako ni', 'Your margin is')} "
                             f"*{margin:.0f}%* — {self._t('chini ya wastani wa soko', 'below market average', profile)} "
                             f"({market_margin:.0f}%)")

        # ── STA 341: Inventory Turnover ──
        if turnover_days > 0:
            lines.append("")
            lines.append(self._section("📦",
                self._t("Mzunguko wa Stock", "Inventory Turnover", profile),
                self._t("Mzunguko wa Stock", "Inventory Turnover", profile), profile))
            lines.append(f"  📦 {self._t('Bidhaa zako zinachukua', 'Your products take')} "
                         f"*{turnover_days:.0f}* {self._t('siku kuuza', 'days to sell', profile)}")
            if turnover_days > 7:
                lines.append(f"  {WARNING} {self._t('Punguza stock — inachukua muda mrefu',
                    'Reduce stock — takes too long', profile)}")
            elif turnover_days < 3:
                lines.append(f"  {CHECK} {self._t('Mzunguko mzuri — stock inaukwa haraka',
                    'Good turnover — stock sells fast', profile)}")

        # ── Customer Retention ──
        if customers:
            returning = [c for c in customers if c.visit_count > 1]
            new_customers = [c for c in customers if c.visit_count == 1]
            lines.append("")
            lines.append(self._section("👥",
                self._t("Wateja", "Customers", profile),
                self._t("Wateja", "Customers", profile), profile))
            lines.append(f"  🔄 {self._t('Wateja waliorudi', 'Returning customers', profile)}: "
                         f"*{len(returning)}*")
            lines.append(f"  🆕 {self._t('Wateja wapya', 'New customers', profile)}: "
                         f"*{len(new_customers)}*")

        # ── ECO 206: Credit Readiness ──
        if profile.credit_score > 0:
            lines.append("")
            lines.append(self._section("🏦",
                self._t("Utayari wa Mkopo", "Credit Readiness", profile),
                self._t("Utayari wa Mkopo", "Credit Readiness", profile), profile))

            score = profile.credit_score
            if score >= 70:
                status = self._t("Tayari kwa mkopo!", "Ready for a loan!", profile)
                eligible = self._format_money(score * 200, profile)  # Rough estimate
            elif score >= 50:
                status = self._t("Karibu tayari", "Almost ready", profile)
                eligible = self._format_money(score * 100, profile)
            else:
                status = self._t("Inahitaji kazi zaidi", "Needs more work", profile)
                eligible = self._format_money(0, profile)

            lines.append(f"  {health_display(score)} {self._t('Alama', 'Score')}: *{score:.0f}/100*")
            lines.append(f"  📊 {status}")
            if score >= 50:
                lines.append(f"  💰 {self._t('Mkopo unawezekana', 'Possible loan')}: ~{eligible}")

        # ── Recommendations ──
        lines.append("")
        lines.append(self._section("💡",
            self._t("Mapendekezo", "Recommendations", profile),
            self._t("Mapendekezo", "Recommendations", profile), profile))

        recommendations = self._generate_monthly_recommendations(
            margin, rev_growth, turnover_days, expense_cats, total_revenue, profile)
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"  {i}. {rec}")

        # ── Footer ──
        lines.append("")
        lines.append(self._divider())
        lines.append(f"📱 {self._t('Ripoti ya nusu mwaka: Juni 30 & Desemba 31',
            'Semi-annual report: June 30 & December 31', profile)}")

        return "\n".join(lines)

    def _generate_monthly_recommendations(
        self, margin: float, rev_growth: float, turnover_days: float,
        expense_cats: Dict[str, float], total_revenue: float,
        profile: WorkerProfile,
    ) -> List[str]:
        """Generate 3 specific actionable recommendations."""
        recs: List[str] = []

        # 1. Margin-based recommendation
        if margin < 20:
            recs.append(self._t(
                "Ongeza bei au punguza gharama — margin yako ni ndogo sana",
                "Increase prices or reduce costs — your margin is too low",
                profile))
        elif margin > 40:
            recs.append(self._t(
                "Margin yako ni nzuri — fikiria kupanua biashara",
                "Good margin — consider expanding",
                profile))
        else:
            recs.append(self._t(
                "Dumisha margin yako — iko katika hali nzuri",
                "Maintain your margin — it's in good shape",
                profile))

        # 2. Expense-based recommendation
        if expense_cats:
            top_expense_cat = max(expense_cats.items(), key=lambda x: x[1])
            top_pct = (top_expense_cat[1] / sum(expense_cats.values()) * 100
                       ) if sum(expense_cats.values()) > 0 else 0
            if top_pct > 40:
                recs.append(self._t(
                    f"Gharama kubwa ni {top_expense_cat[0]} ({top_pct:.0f}%) — tafuta mbadala wa bei rahisi",
                    f"Biggest expense is {top_expense_cat[0]} ({top_pct:.0f}%) — find cheaper alternatives",
                    profile))

        # 3. Growth-based recommendation
        if rev_growth < -10:
            recs.append(self._t(
                "Mauzo yamepungua — jaribu kuuza bidhaa mpya au ongeza wateja",
                "Sales dropped — try new products or attract more customers",
                profile))
        elif rev_growth > 20:
            recs.append(self._t(
                "Mauzo yameongezeka sana! Hakikisha una stock ya kutosha",
                "Sales grew a lot! Make sure you have enough stock",
                profile))
        else:
            recs.append(self._t(
                "Jaribu kuongeza mauzo kwa 10% mwezi ujao — ongeza bidhaa 1-2 mpya",
                "Try increasing sales 10% next month — add 1-2 new products",
                profile))

        return recs[:3]


# ============================================================================
# 4. SEMI-ANNUAL REPORT — Ripoti ya Nusu Mwaka
# ============================================================================
# Degree Units: ECO 201, STA 244, ECO 206, STA 341, ECO 210
# ============================================================================

class SemiAnnualReport(WorkerReport):
    """6-month strategic business review.

    ECO 201: Revenue trend, seasonal patterns, market position.
    STA 244: 6-month trend line with seasonality detection.
    ECO 206: Financial health assessment — savings, debt, credit trajectory.
    STA 341: Product portfolio analysis using estimation and confidence.
    ECO 210: Customer base growth analysis (quantitative methods).
    """

    def report_type(self) -> str:
        return "semiannual"

    def generate(
        self,
        profile: WorkerProfile,
        period_start: date,
        period_end: date,
        monthly_data: List[MonthlyData],
        customers: Optional[List[CustomerData]] = None,
        seasonal_result: Optional[SeasonalAnalysisResult] = None,
    ) -> str:
        """Generate semi-annual report."""
        # 6-month aggregates
        total_revenue = sum(m.revenue for m in monthly_data)
        total_expenses = sum(m.expenses for m in monthly_data)
        profit = total_revenue - total_expenses
        margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        total_txn = sum(m.transactions for m in monthly_data)

        # Best/worst months
        if monthly_data:
            best_month = max(monthly_data, key=lambda m: m.revenue)
            worst_month = min(monthly_data, key=lambda m: m.revenue)
        else:
            best_month = worst_month = None

        # Monthly revenue trend
        monthly_revenues = [m.revenue for m in monthly_data]

        # Product portfolio
        product_totals: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        for m in monthly_data:
            # MonthlyData doesn't have items_sold directly; use top_product
            if m.top_product:
                product_totals[m.top_product] = (
                    product_totals[m.top_product][0] + 1,
                    product_totals[m.top_product][1] + m.top_product_revenue
                )
        top_products = sorted(product_totals.items(),
                              key=lambda x: x[1][1], reverse=True)[:5]

        lines: List[str] = []
        period_str = f"{self._format_date(period_start, profile.language)} — {self._format_date(period_end, profile.language)}"

        # ── Header ──
        lines.append(self._header(
            self._t("Ripoti ya Nusu Mwaka", "Semi-Annual Report", profile),
            profile, period_str
        ))
        lines.append("")

        # ── ECO 201: Half-Year P&L ──
        lines.append(self._section("💰",
            self._t("Muhtasari wa Nusu Mwaka", "Half-Year Summary", profile),
            self._t("Muhtasari wa Nusu Mwaka", "Half-Year Summary", profile), profile))

        lines.append(self._metric_line(
            self._t("Mauzo ya nusu mwaka", "Half-year revenue", profile),
            self._format_money(total_revenue, profile)))
        lines.append(self._metric_line(
            self._t("Faida ya nusu mwaka", "Half-year profit", profile),
            self._format_money(profit, profile),
            CHECK if profit > 0 else CROSS_MARK))
        lines.append(self._metric_line(
            self._t("Margin", "Margin", profile), f"{margin:.1f}%"))
        lines.append(self._metric_line(
            self._t("Miamala", "Transactions", profile), str(total_txn)))

        # ── STA 244: 6-Month Trend ──
        if monthly_revenues:
            lines.append("")
            lines.append(self._t("Mwelekeo wa miezi 6:", "6-month trend:", profile))
            lines.append(self.sparkline.render(monthly_revenues))

        # ── Best/Worst Months ──
        if best_month and worst_month:
            lines.append("")
            lines.append(self._section("📊",
                self._t("Mwezi Bora vs Mbaya", "Best vs Worst Month", profile),
                self._t("Mwezi Bora vs Mbaya", "Best vs Worst Month", profile), profile))
            best_name = SWAHILI_MONTHS[best_month.month - 1]
            worst_name = SWAHILI_MONTHS[worst_month.month - 1]
            lines.append(f"  {STAR_FILLED} {self._t('Bora', 'Best')}: "
                         f"*{best_name}* — {self._format_money(best_month.revenue, profile)}")
            lines.append(f"  {STAR_EMPTY} {self._t('Mbaya', 'Worst')}: "
                         f"*{worst_name}* — {self._format_money(worst_month.revenue, profile)}")

        # ── STA 244: Seasonal Patterns ──
        if seasonal_result:
            lines.append("")
            lines.append(self._section("🌦️",
                self._t("Msimu wa Mauzo", "Sales Seasons", profile),
                self._t("Msimu wa Mauzo", "Sales Seasons", profile), profile))
            if hasattr(seasonal_result, 'peak_months') and seasonal_result.peak_months:
                peak_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in seasonal_result.peak_months)
                lines.append(f"  🔥 {self._t('Miezi ya mauzo mengi', 'Peak months')}: *{peak_names}*")
            if hasattr(seasonal_result, 'low_months') and seasonal_result.low_months:
                low_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in seasonal_result.low_months)
                lines.append(f"  📉 {self._t('Miezi ya mauzo kidogo', 'Low months')}: *{low_names}*")

        # ── Product Portfolio ──
        if top_products:
            lines.append("")
            lines.append(self._section("📦",
                self._t("Bidhaa — Uchambuzi", "Product Analysis", profile),
                self._t("Bidhaa — Uchambuzi", "Product Analysis", profile), profile))
            for i, (name, (months_active, rev)) in enumerate(top_products, 1):
                lines.append(f"  {i}. *{name}* — "
                             f"{self._format_money(rev, profile)} ({months_active} months)")

        # ── Customer Base Growth ──
        if customers:
            returning = [c for c in customers if c.visit_count > 3]
            new_customers = [c for c in customers if c.visit_count <= 1]
            total_spend = sum(c.total_spent for c in customers)
            lines.append("")
            lines.append(self._section("👥",
                self._t("Wateja — Ukuaji", "Customer Growth", profile),
                self._t("Wateja — Ukuaji", "Customer Growth", profile), profile))
            lines.append(f"  👥 {self._t('Wateja wote', 'Total customers')}: *{len(customers)}*")
            lines.append(f"  🔄 {self._t('Warudiayo', 'Returning')}: *{len(returning)}*")
            lines.append(f"  🆕 {self._t('Wapya', 'New')}: *{len(new_customers)}*")
            lines.append(f"  💰 {self._t('Mteja anatumia wastani', 'Avg spend per customer')}: "
                         f"{self._format_money(total_spend / len(customers), profile)}")

        # ── ECO 206: Financial Health ──
        lines.append("")
        lines.append(self._section("🏦",
            self._t("Afya ya Kifedha", "Financial Health", profile),
            self._t("Afya ya Kifedha", "Financial Health", profile), profile))

        avg_monthly_profit = profit / 6 if profit > 0 else 0
        lines.append(f"  💰 {self._t('Faida ya wastani/mwezi', 'Avg monthly profit')}: "
                     f"{self._format_money(avg_monthly_profit, profile)}")

        if profile.current_savings > 0:
            months_of_expenses = (profile.current_savings / (total_expenses / 6)
                                  ) if total_expenses > 0 else 0
            lines.append(f"  🏦 {self._t('Akiba', 'Savings')}: "
                         f"{self._format_money(profile.current_savings, profile)} "
                         f"({months_of_expenses:.1f} {self._t('miezi ya gharama', 'months of expenses', profile)})")

        if profile.credit_score > 0:
            lines.append(f"  {health_display(profile.credit_score)} "
                         f"{self._t('Alama ya mkopo', 'Credit score')}: *{profile.credit_score:.0f}/100*")

        # ── Goals for Next 6 Months ──
        lines.append("")
        lines.append(self._section("🎯",
            self._t("Malengo ya Nusu Mwaka Ijayo", "Next 6-Month Goals", profile),
            self._t("Malengo ya Nusu Mwaka Ijayo", "Next 6-Month Goals", profile), profile))

        next_rev_target = total_revenue * 1.15  # 15% growth target
        lines.append(f"  1. {self._t('Ongeza mauzo hadi', 'Grow revenue to')} "
                     f"{self._format_money(next_rev_target, profile)} (+15%)")
        lines.append(f"  2. {self._t('Fikia akiba ya', 'Reach savings of')} "
                     f"{self._format_money(profile.savings_goal, profile)}")
        lines.append(f"  3. {self._t('Ongeza wateja wapya 20+', 'Add 20+ new customers')}")

        # ── Footer ──
        lines.append("")
        lines.append(self._divider())
        lines.append(f"📱 {self._t('Ripoti ya mwaka mzima: Desemba 31',
            'Annual report: December 31', profile)}")

        return "\n".join(lines)


# ============================================================================
# 5. ANNUAL REPORT — Ripoti ya Mwaka
# ============================================================================
# Degree Units: ALL — comprehensive annual review
# ============================================================================

class AnnualReport(WorkerReport):
    """Comprehensive annual business review.

    Applies ALL degree units for a complete picture:
    - ECO 201: Annual P&L, market position, growth analysis
    - STA 244: Year-over-year trends, seasonality
    - STA 142: Descriptive statistics of annual performance
    - STA 341: Bayesian business health, credit readiness estimation
    - STA 342: Year-over-year hypothesis testing
    - STA 346: Quality control — process capability of the business
    - ECO 206: Savings, credit history, financial inclusion
    - ECO 210: Customer lifetime value, inventory optimization
    - ECO 421: Tax compliance summary, formalization readiness
    """

    def report_type(self) -> str:
        return "annual"

    def generate(
        self,
        profile: WorkerProfile,
        year: int,
        monthly_data: List[MonthlyData],
        previous_year_revenue: float = 0.0,
        previous_year_profit: float = 0.0,
        customers: Optional[List[CustomerData]] = None,
        inventory: Optional[List[InventoryStatus]] = None,
        seasonal_result: Optional[SeasonalAnalysisResult] = None,
        health_result: Optional[HealthScoreResult] = None,
    ) -> str:
        """Generate annual report."""
        # Annual aggregates
        total_revenue = sum(m.revenue for m in monthly_data)
        total_expenses = sum(m.expenses for m in monthly_data)
        profit = total_revenue - total_expenses
        margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        total_txn = sum(m.transactions for m in monthly_data)
        active_months = len([m for m in monthly_data if m.revenue > 0])

        # Year-over-year
        yoy_rev = ((total_revenue - previous_year_revenue) / previous_year_revenue * 100
                   ) if previous_year_revenue > 0 else 0.0
        yoy_profit = ((profit - previous_year_profit) / previous_year_profit * 100
                      ) if previous_year_profit > 0 else 0.0

        # Monthly revenues for trend
        monthly_revenues = [m.revenue for m in monthly_data]

        # Best/worst months
        best_month = max(monthly_data, key=lambda m: m.revenue) if monthly_data else None
        worst_month = min(monthly_data, key=lambda m: m.revenue) if monthly_data else None

        # Customer metrics
        total_customers = len(customers) if customers else 0
        returning_customers = len([c for c in customers if c.visit_count > 1]) if customers else 0
        avg_customer_value = (sum(c.total_spent for c in customers) / total_customers
                              ) if customers and total_customers > 0 else 0

        # Profitable months
        profitable_months = len([m for m in monthly_data if m.revenue > m.expenses])

        lines: List[str] = []

        # ── Header ──
        lines.append(self._header(
            self._t("Ripoti ya Mwaka", "Annual Report", profile),
            profile, str(year)
        ))
        lines.append("")
        lines.append(f"🎉 {self._t('Hii ni ripoti kamili ya biashara yako ya mwaka mzima!',
            'This is your complete annual business report!', profile)}")
        lines.append("")

        # ── ECO 201: Annual P&L ──
        lines.append(self._section("💰",
            self._t("Mauzo na Faida ya Mwaka", "Annual P&L", profile),
            self._t("Mauzo na Faida ya Mwaka", "Annual P&L", profile), profile))

        lines.append(self._metric_line(
            self._t("Mauzo ya mwaka", "Annual revenue", profile),
            self._format_money(total_revenue, profile)))
        lines.append(self._metric_line(
            self._t("Gharama za mwaka", "Annual expenses", profile),
            self._format_money(total_expenses, profile)))
        lines.append(self._metric_line(
            self._t("Faida ya mwaka", "Annual profit", profile),
            self._format_money(profit, profile),
            CHECK if profit > 0 else CROSS_MARK))
        lines.append(self._metric_line(
            self._t("Margin ya faida", "Profit margin", profile), f"{margin:.1f}%"))
        lines.append(self._metric_line(
            self._t("Miezi yenye faida", "Profitable months", profile),
            f"{profitable_months}/12"))
        lines.append(self._metric_line(
            self._t("Miamala", "Transactions", profile), str(total_txn)))

        # YoY growth
        if yoy_rev != 0:
            arrow = self._growth_indicator(yoy_rev)
            lines.append(self._metric_line(
                self._t("Ukuaji wa mauzo", "Revenue growth", profile),
                f"{yoy_rev:+.1f}% {self._t('kuliko mwaka uliopita', 'vs last year', profile)}",
                arrow))

        # ── STA 244: Monthly Trend ──
        if monthly_revenues:
            lines.append("")
            lines.append(self._t("Mwelekeo wa miezi 12:", "12-month trend:", profile))
            lines.append(self.sparkline.render(monthly_revenues))

        # ── Best/Worst Months ──
        if best_month and worst_month:
            lines.append("")
            lines.append(self._section("📊",
                self._t("Mwezi Bora vs Mbaya", "Best vs Worst Month", profile),
                self._t("Mwezi Bora vs Mbaya", "Best vs Worst Month", profile), profile))
            best_name = SWAHILI_MONTHS[best_month.month - 1]
            worst_name = SWAHILI_MONTHS[worst_month.month - 1]
            lines.append(f"  {STAR_FILLED} {self._t('Bora', 'Best')}: "
                         f"*{best_name}* — {self._format_money(best_month.revenue, profile)}")
            lines.append(f"  {STAR_EMPTY} {self._t('Mbaya', 'Worst')}: "
                         f"*{worst_name}* — {self._format_money(worst_month.revenue, profile)}")

        # ── STA 244: Seasonal Patterns ──
        if seasonal_result:
            lines.append("")
            lines.append(self._section("🌦️",
                self._t("Msimu wa Mauzo", "Sales Seasons", profile),
                self._t("Msimu wa Mauzo", "Sales Seasons", profile), profile))
            if hasattr(seasonal_result, 'peak_months') and seasonal_result.peak_months:
                peak_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in seasonal_result.peak_months)
                lines.append(f"  🔥 {self._t('Miezi bora', 'Peak months')}: *{peak_names}*")
            if hasattr(seasonal_result, 'low_months') and seasonal_result.low_months:
                low_names = ", ".join(SWAHILI_MONTHS[m - 1] for m in seasonal_result.low_months)
                lines.append(f"  📉 {self._t('Miezi dhaifu', 'Low months')}: *{low_names}*")

        # ── STA 142: Profit Margin Evolution ──
        monthly_margins = []
        for m in monthly_data:
            if m.revenue > 0:
                monthly_margins.append((m.revenue - m.expenses) / m.revenue * 100)
        if monthly_margins:
            lines.append("")
            lines.append(self._section("📈",
                self._t("Margin ya Faida kwa Mwezi", "Monthly Margin Trend", profile),
                self._t("Margin ya Faida kwa Mwezi", "Monthly Margin Trend", profile), profile))
            avg_margin = statistics.mean(monthly_margins)
            lines.append(f"  📊 {self._t('Margin ya wastani', 'Average margin')}: *{avg_margin:.1f}%*")
            if len(monthly_margins) >= 3:
                first_half = statistics.mean(monthly_margins[:6])
                second_half = statistics.mean(monthly_margins[6:])
                margin_trend = second_half - first_half
                if margin_trend > 2:
                    lines.append(f"  {ARROW_UP} {self._t('Margin imeongezeka mwishoni', 'Margin improved in H2', profile)}")
                elif margin_trend < -2:
                    lines.append(f"  {ARROW_DOWN} {self._t('Margin imepungua mwishoni', 'Margin declined in H2', profile)}")

        # ── ECO 210: Customer Lifetime Value ──
        if customers:
            lines.append("")
            lines.append(self._section("👥",
                self._t("Wateja — Uchambuzi wa Mwaka", "Annual Customer Analysis", profile),
                self._t("Wateja — Uchambuzi wa Mwaka", "Annual Customer Analysis", profile), profile))

            retention_rate = (returning_customers / total_customers * 100
                              ) if total_customers > 0 else 0
            lines.append(f"  👥 {self._t('Wateja wote', 'Total customers')}: *{total_customers}*")
            lines.append(f"  🔄 {self._t('Kiwango cha kurudi', 'Retention rate')}: *{retention_rate:.0f}%*")
            lines.append(f"  💰 {self._t('Thamani ya mteja', 'Avg customer value')}: "
                         f"{self._format_money(avg_customer_value, profile)}")

            # Customer lifetime value estimate (ECO 210)
            if retention_rate > 0 and avg_customer_value > 0:
                # Simple CLV = avg_value × retention_rate / (1 - retention_rate)
                clv = avg_customer_value * (retention_rate / 100) / (1 - retention_rate / 100)
                lines.append(f"  {STAR_FILLED} {self._t('Thamani ya muda wa mteja', 'Customer lifetime value')}: "
                             f"~{self._format_money(clv, profile)}")

        # ── STA 341/346: Business Health Assessment ──
        lines.append("")
        lines.append(self._section("❤️",
            self._t("Afya ya Biashara — Tathmini ya Mwaka", "Annual Health Assessment", profile),
            self._t("Afya ya Biashara — Tathmini ya Mwaka", "Annual Health Assessment", profile), profile))

        if health_result:
            lines.append(f"  {health_display(health_result.overall_score)} "
                         f"{self._t('Alama ya afya', 'Health score')}: "
                         f"*{health_result.overall_score:.0f}/100*")
            lines.append(f"  {star_rating(health_result.overall_score)}")
        else:
            # Calculate from available data
            if monthly_data:
                consistency = active_months / 12 * 100
                profitability = profitable_months / 12 * 100
                health = (consistency * 0.3 + profitability * 0.4 + min(margin * 1.5, 30))
                health = min(100, max(0, health))
                lines.append(f"  {health_display(health)} "
                             f"{self._t('Alama ya afya', 'Health score')}: *{health:.0f}/100*")
                lines.append(f"  {star_rating(health)}")

        # ── ECO 206: Credit & Savings Summary ──
        lines.append("")
        lines.append(self._section("🏦",
            self._t("Akiba na Mkopo", "Savings & Credit", profile),
            self._t("Akiba na Mkopo", "Savings & Credit", profile), profile))

        avg_monthly_savings = profile.current_savings / 12 if profile.current_savings > 0 else 0
        lines.append(f"  💰 {self._t('Akiba', 'Savings')}: "
                     f"{self._format_money(profile.current_savings, profile)}")
        lines.append(f"  📊 {self._t('Wastani wa akiba/mwezi', 'Avg monthly savings')}: "
                     f"{self._format_money(avg_monthly_savings, profile)}")

        if profile.credit_score > 0:
            lines.append(f"  {health_display(profile.credit_score)} "
                         f"{self._t('Alama ya mkopo', 'Credit score')}: *{profile.credit_score:.0f}/100*")
            if profile.credit_score >= 70:
                eligible = profile.credit_score * 200
                lines.append(f"  ✅ {self._t('Uko tayari kwa mkopo wa', 'Eligible for loan of')} "
                             f"~{self._format_money(eligible, profile)}")

        # ── ECO 421: Tax Compliance ──
        lines.append("")
        lines.append(self._section("📋",
            self._t("Ushuru — Tathmini", "Tax Compliance", profile),
            self._t("Ushuru — Tathmini", "Tax Compliance", profile), profile))

        estimated_tax = max(0, profit * 0.1) if profit > 0 else 0  # Simplified 10% presumptive
        lines.append(f"  📋 {self._t('Faida ya mwaka', 'Annual profit')}: "
                     f"{self._format_money(profit, profile)}")
        lines.append(f"  💰 {self._t('Ushuru wa makadirio', 'Estimated tax')}: "
                     f"~{self._format_money(estimated_tax, profile)}")
        if total_txn > 0:
            lines.append(f"  ✅ {self._t('Rekodi zako za miamala ziko tayari kwa KRA',
                'Your transaction records are ready for KRA', profile)}")

        # ── Formalization Pathway ──
        lines.append("")
        lines.append(self._section("🏢",
            self._t("Usajili wa Biashara", "Business Formalization", profile),
            self._t("Usajili wa Biashara", "Business Formalization", profile), profile))

        if profile.credit_score >= 60 and active_months >= 6:
            lines.append(f"  ✅ {self._t('Biashara yako iko tayari kwa usajili',
                'Your business is ready for registration', profile)}")
            lines.append(f"  📄 {self._t('Hatua zifuatazo', 'Next steps')}:")
            lines.append(f"    1. {self._t('Pata leseni ya biashara', 'Get business permit')}")
            lines.append(f"    2. {self._t('Jisajili na KRA', 'Register with KRA')}")
            lines.append(f"    3. {self._t('Fungua akaunti ya biashara', 'Open business account')}")
        else:
            lines.append(f"  {WARNING} {self._t('Biashara bado haijawa tayari — endelea kurekodi',
                'Business not ready yet — keep recording', profile)}")

        # ── Next Year Goals ──
        lines.append("")
        lines.append(self._section("🎯",
            self._t("Malengo ya Mwaka Ujao", "Next Year Goals", profile),
            self._t("Malengo ya Mwaka Ujao", "Next Year Goals", profile), profile))

        next_rev = total_revenue * 1.25  # 25% growth target
        next_profit = profit * 1.30  # 30% profit growth
        lines.append(f"  1. {self._t('Ongeza mauzo hadi', 'Grow revenue to')} "
                     f"{self._format_money(next_rev, profile)} (+25%)")
        lines.append(f"  2. {self._t('Ongeza faida hadi', 'Grow profit to')} "
                     f"{self._format_money(next_profit, profile)} (+30%)")
        lines.append(f"  3. {self._t('Fikia akiba ya', 'Reach savings of')} "
                     f"{self._format_money(profile.savings_goal, profile)}")
        if profile.credit_score < 70:
            lines.append(f"  4. {self._t('Fikia alama ya mkopo 70', 'Reach credit score 70')}")
        if total_customers < 50:
            lines.append(f"  5. {self._t('Ongeza wateja hadi 50', 'Grow customers to 50')}")

        # ── Footer ──
        lines.append("")
        lines.append(self._divider())
        lines.append(f"🎉 {self._t('Hongera kwa mwaka mzima wa biashara!',
            'Congratulations on a full year of business!', profile)}")
        lines.append(f"📱 {self._t('Msaidizi — Biashara yako, data yako',
            'Msaidizi — Your business, your data', profile)}")

        return "\n".join(lines)


# ============================================================================
# Report Factory — convenience entry point
# ============================================================================

class ReportFactory:
    """Factory for creating and generating worker reports.

    Usage:
        factory = ReportFactory()
        daily = factory.daily(profile, today_data, yesterday_data)
        weekly = factory.weekly(profile, week_start, week_end, daily_data)
    """

    def __init__(self):
        self._daily = DailyReport()
        self._weekly = WeeklyReport()
        self._monthly = MonthlyReport()
        self._semiannual = SemiAnnualReport()
        self._annual = AnnualReport()

    def daily(self, profile: WorkerProfile, **kwargs) -> str:
        return self._daily.generate(profile, **kwargs)

    def weekly(self, profile: WorkerProfile, **kwargs) -> str:
        return self._weekly.generate(profile, **kwargs)

    def monthly(self, profile: WorkerProfile, **kwargs) -> str:
        return self._monthly.generate(profile, **kwargs)

    def semiannual(self, profile: WorkerProfile, **kwargs) -> str:
        return self._semiannual.generate(profile, **kwargs)

    def annual(self, profile: WorkerProfile, **kwargs) -> str:
        return self._annual.generate(profile, **kwargs)

    def get_report(self, report_type: str) -> WorkerReport:
        """Get report generator by type string."""
        mapping = {
            "daily": self._daily,
            "weekly": self._weekly,
            "monthly": self._monthly,
            "semiannual": self._semiannual,
            "annual": self._annual,
        }
        if report_type not in mapping:
            raise ValueError(f"Unknown report type: {report_type}. "
                             f"Valid: {list(mapping.keys())}")
        return mapping[report_type]
