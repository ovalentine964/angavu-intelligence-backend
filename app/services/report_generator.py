"""
Report Generator — Msaidizi / Angavu Intelligence

The core engine that generates all 5 report types for WhatsApp delivery.
This is the module that turns raw business data into beautiful, actionable
reports that show informal workers their business for the first time.

Report Types:
1. Ripoti ya Leo (Daily) — End-of-day snapshot
2. Ripoti ya Wiki (Weekly) — Weekly trends and patterns
3. Ripoti ya Mwezi (Monthly) — Monthly business health check
4. Ripoti ya Nusu Mwaka (Semi-annual) — Strategic review
5. Ripoti ya Mwaka (Yearly) — Complete annual picture

Design Principles:
- Every report starts with the worker's name — this is PERSONAL
- Swahili first, with English/Sheng support
- Visual charts using Unicode blocks (no images needed)
- Actionable insights, not just numbers
- Show growth and progress — make workers feel proud
- WhatsApp-native formatting (bold with asterisks, no markdown tables)
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .whatsapp_charts import (
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
from .health_score import BusinessHealthScorer, BusinessMetrics, HealthScoreResult
from .seasonal_analyzer import SeasonalAnalyzer, MonthlyData, SeasonalAnalysisResult
from .comparison_engine import ComparisonEngine, PeerBusiness, ComparisonResult


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    """User profile for report personalization."""
    user_id: str
    name: str                       # First name, used in greeting
    business_name: str = "Biashara" # Business name/nickname
    business_type: str = "food_vendor"
    location: str = ""              # Market/area name
    language: str = "sw"            # "sw" (Swahili), "en" (English), "sh" (Sheng)
    preferred_report_time: str = "19:00"  # HH:MM format
    currency: str = "KSh"
    phone: str = ""
    join_date: Optional[date] = None


@dataclass
class TransactionData:
    """A single transaction record."""
    transaction_id: str
    user_id: str
    transaction_type: str           # "sale" or "purchase"
    amount: float
    item_name: str = ""
    item_category: str = ""
    quantity: int = 1
    timestamp: Optional[datetime] = None
    payment_method: str = "cash"    # "cash", "mpesa", "credit"


@dataclass
class InventoryItem:
    """Inventory item with stock level."""
    item_name: str
    current_stock: float
    unit: str = "pieces"
    daily_usage_rate: float = 0.0   # Average units used per day
    restock_threshold: float = 0.0  # Alert when below this
    last_restock_date: Optional[date] = None
    cost_per_unit: float = 0.0


@dataclass
class DailyData:
    """Aggregated data for a single day."""
    date: date
    total_sales: float = 0.0
    total_purchases: float = 0.0
    profit: float = 0.0
    sales_count: int = 0
    purchase_count: int = 0
    items_sold: Dict[str, Tuple[int, float]] = field(default_factory=dict)  # item → (qty, revenue)
    best_item: str = ""
    best_item_revenue: float = 0.0
    best_item_qty: int = 0


@dataclass
class WeeklyData:
    """Aggregated data for a week."""
    week_start: date
    week_end: date
    daily_data: List[DailyData] = field(default_factory=list)
    total_sales: float = 0.0
    total_purchases: float = 0.0
    profit: float = 0.0
    total_transactions: int = 0
    best_day: str = ""
    best_day_sales: float = 0.0
    worst_day: str = ""
    worst_day_sales: float = 0.0
    top_items: List[Tuple[str, int, float]] = field(default_factory=list)  # (name, qty, revenue)
    inventory_alerts: List[InventoryItem] = field(default_factory=list)


@dataclass
class MonthlyDataAgg:
    """Aggregated data for a month."""
    year: int
    month: int
    total_sales: float = 0.0
    total_purchases: float = 0.0
    profit: float = 0.0
    total_transactions: int = 0
    active_days: int = 0
    daily_data: List[DailyData] = field(default_factory=list)
    top_items: List[Tuple[str, int, float]] = field(default_factory=list)
    expense_categories: Dict[str, float] = field(default_factory=dict)
    previous_month_sales: float = 0.0
    previous_month_profit: float = 0.0


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Generates all 5 report types for WhatsApp delivery.

    Usage:
        generator = ReportGenerator()
        daily_msg = generator.generate_daily(profile, daily_data, previous_day)
        weekly_msg = generator.generate_weekly(profile, weekly_data, previous_week)
        monthly_msg = generator.generate_monthly(profile, monthly_data, previous_months)
        semi_msg = generator.generate_semiannual(profile, monthly_data_list)
        annual_msg = generator.generate_annual(profile, monthly_data_list)
    """

    def __init__(self):
        self.bar_chart = BarChart()
        self.progress_bar = ProgressBar()
        self.sparkline = Sparkline()
        self.heatmap = Heatmap()
        self.cashflow = CashFlowDiagram()
        self.trend = TrendLine()
        self.table = TableBuilder()
        self.health_scorer = BusinessHealthScorer()
        self.seasonal_analyzer = SeasonalAnalyzer()
        self.comparison_engine = ComparisonEngine()

    # ===================================================================
    # 1. DAILY REPORT — Ripoti ya Leo
    # ===================================================================

    def generate_daily(
        self,
        profile: UserProfile,
        today: DailyData,
        yesterday: Optional[DailyData] = None,
        avg_daily_sales: float = 0.0,
        inventory_alerts: Optional[List[InventoryItem]] = None,
    ) -> str:
        """Generate the daily report (Ripoti ya Leo).

        End-of-day snapshot showing what happened today.
        Includes sales, purchases, profit, best item, comparison with
        yesterday, mood indicator, and one actionable tip.

        Args:
            profile: User profile.
            today: Today's aggregated data.
            yesterday: Yesterday's data for comparison (optional).
            avg_daily_sales: Average daily sales for mood calculation.
            inventory_alerts: Items running low (optional).

        Returns:
            Formatted WhatsApp message string.
        """
        lang = profile.language
        cfg = self._chart_config(profile)

        # Calculate key metrics
        profit = today.total_sales - today.total_purchases
        if avg_daily_sales == 0:
            avg_daily_sales = today.total_sales  # No baseline yet

        # Day name in Swahili
        day_name = self._swahili_day(today.date)

        # Date string
        date_str = self._format_date(today.date, lang)

        # Mood
        mood = mood_label(today.total_sales, avg_daily_sales, lang)

        # Yesterday comparison
        if yesterday and yesterday.total_sales > 0:
            sales_change = ((today.total_sales - yesterday.total_sales) / yesterday.total_sales) * 100
            profit_yesterday = yesterday.total_sales - yesterday.total_purchases
            if profit_yesterday > 0:
                profit_change = ((profit - profit_yesterday) / profit_yesterday) * 100
            else:
                profit_change = 0
            has_comparison = True
        else:
            sales_change = 0
            profit_change = 0
            has_comparison = False

        # Generate tip
        tip = self._generate_daily_tip(today, yesterday, avg_daily_sales, lang)

        # Build message
        lines = []

        # Header
        lines.append(f"📊 *Ripoti ya Leo — {profile.business_name}*")
        lines.append(f"📅 {day_name}, {date_str}")
        lines.append("")

        # Greeting
        if lang == "sw":
            lines.append(f"👤 {profile.name}, hii leo:")
        elif lang == "sh":
            lines.append(f"👤 {profile.name}, leo ni:")
        else:
            lines.append(f"👤 {profile.name}, today's report:")
        lines.append("")

        # Key metrics
        lines.append(f"💰 *{'Mauzo' if lang == 'sw' else 'Sales'}:* {format_currency(today.total_sales, cfg)} ({today.sales_count} {'mauzo' if lang == 'sw' else 'sales'})")
        lines.append(f"🛒 *{'Manunuzi' if lang == 'sw' else 'Purchases'}:* {format_currency(today.total_purchases, cfg)} ({today.purchase_count} {'manunuzi' if lang == 'sw' else 'purchases'})")
        lines.append(f"📈 *{'Faida' if lang == 'sw' else 'Profit'}:* {format_currency(profit, cfg)}")
        lines.append("")

        # Best selling item
        if today.best_item:
            lines.append(f"🏆 *{'Bidhaa bora' if lang == 'sw' else 'Best item'}:* {today.best_item} ({today.best_item_qty} {'mauzo' if lang == 'sw' else 'sold'}, {format_currency(today.best_item_revenue, cfg)})")
            lines.append("")

        # Yesterday comparison
        if has_comparison:
            if lang == "sw":
                lines.append("📊 *Ikilinganishwa na jana:*")
            else:
                lines.append("📊 *Compared to yesterday:*")

            sales_arrow = ARROW_UP if sales_change >= 0 else ARROW_DOWN
            profit_arrow = ARROW_UP if profit_change >= 0 else ARROW_DOWN
            lines.append(f"   {'Mauzo' if lang == 'sw' else 'Sales'}: {sales_arrow} {abs(sales_change):.0f}% (jana {format_currency(yesterday.total_sales, cfg)})")
            lines.append(f"   {'Faida' if lang == 'sw' else 'Profit'}: {profit_arrow} {abs(profit_change):.0f}% (jana {format_currency(profit_yesterday, cfg)})")
            lines.append("")

        # Mood
        lines.append(mood)
        lines.append("")

        # Inventory alerts
        if inventory_alerts:
            if lang == "sw":
                lines.append("⚠️ *Hifadhi ya chini:*")
            else:
                lines.append("⚠️ *Low stock alerts:*")
            for item in inventory_alerts[:3]:
                days_left = self._days_of_stock(item)
                if lang == "sw":
                    lines.append(f"   • {item.item_name}: imesalia siku {days_left:.0f}")
                else:
                    lines.append(f"   • {item.item_name}: {days_left:.0f} days left")
            lines.append("")

        # Tip
        lines.append(f"💡 *{'Kidokezo' if lang == 'sw' else 'Tip'}:* {tip}")

        return "\n".join(lines)

    # ===================================================================
    # 2. WEEKLY REPORT — Ripoti ya Wiki
    # ===================================================================

    def generate_weekly(
        self,
        profile: UserProfile,
        week: WeeklyData,
        previous_week: Optional[WeeklyData] = None,
    ) -> str:
        """Generate the weekly report (Ripoti ya Wiki).

        Weekly trends and patterns. Shows daily breakdown with bar charts,
        top items, inventory alerts, week-over-week comparison, and
        2-3 actionable insights.

        Args:
            profile: User profile.
            week: This week's aggregated data.
            previous_week: Previous week's data for comparison (optional).

        Returns:
            Formatted WhatsApp message string.
        """
        lang = profile.language
        cfg = self._chart_config(profile)

        profit = week.total_sales - week.total_purchases

        # Week-over-week comparison
        if previous_week and previous_week.total_sales > 0:
            sales_change = ((week.total_sales - previous_week.total_sales) / previous_week.total_sales) * 100
            prev_profit = previous_week.total_sales - previous_week.total_purchases
            profit_change = ((profit - prev_profit) / prev_profit * 100) if prev_profit > 0 else 0
            has_comparison = True
        else:
            sales_change = 0
            profit_change = 0
            has_comparison = False

        # Generate insights
        insights = self._generate_weekly_insights(week, previous_week, lang)

        # Build message
        lines = []

        # Header
        lines.append(f"📊 *Ripoti ya Wiki — {profile.business_name}*")
        week_start_str = self._format_date(week.week_start, lang)
        week_end_str = self._format_date(week.week_end, lang)
        lines.append(f"📅 Wiki ya {week_start_str} - {week_end_str}")
        lines.append("")

        # Greeting
        if lang == "sw":
            lines.append(f"👤 {profile.name}, muhtasari wa wiki hii:")
        else:
            lines.append(f"👤 {profile.name}, this week's summary:")
        lines.append("")

        # Key metrics
        lines.append(f"💰 *{'Mauzo jumla' if lang == 'sw' else 'Total sales'}:* {format_currency(week.total_sales, cfg)} ({week.total_transactions} {'mauzo' if lang == 'sw' else 'transactions'})")
        lines.append(f"🛒 *{'Manunuzi jumla' if lang == 'sw' else 'Total purchases'}:* {format_currency(week.total_purchases, cfg)}")
        lines.append(f"📈 *{'Faida jumla' if lang == 'sw' else 'Total profit'}:* {format_currency(profit, cfg)}")

        if has_comparison:
            sales_arrow = ARROW_UP if sales_change >= 0 else ARROW_DOWN
            profit_arrow = ARROW_UP if profit_change >= 0 else ARROW_DOWN
            lines.append(f"   {sales_arrow} {'Mauzo' if lang == 'sw' else 'Sales'}: {format_percentage(sales_change)} {'wiki iliyopita' if lang == 'sw' else 'vs last week'}")
        lines.append("")

        # Daily breakdown bar chart
        if week.daily_data:
            if lang == "sw":
                lines.append("📊 *Mauzo ya kila siku:*")
            else:
                lines.append("📊 *Daily sales:*")

            daily_sales = {}
            for d in week.daily_data:
                day_label = self._swahili_day_short(d.date)
                daily_sales[day_label] = d.total_sales

            # Highlight best day
            best_day_label = self._swahili_day_short(
                max(week.daily_data, key=lambda d: d.total_sales).date
            )
            chart = self.bar_chart.render(
                daily_sales,
                max_label_width=8,
                highlight_max=True,
                currency=True,
            )
            lines.append(chart)

        # Best and worst days
        if week.daily_data:
            best = max(week.daily_data, key=lambda d: d.total_sales)
            worst = min(week.daily_data, key=lambda d: d.total_sales)
            if lang == "sw":
                lines.append(f"🏆 *Siku bora:* {self._swahili_day(best.date)} ({format_currency(best.total_sales, cfg)})")
                lines.append(f"📉 *Siku dhaifu:* {self._swahili_day(worst.date)} ({format_currency(worst.total_sales, cfg)})")
            else:
                lines.append(f"🏆 *Best day:* {self._swahili_day(best.date)} ({format_currency(best.total_sales, cfg)})")
                lines.append(f"📉 *Weakest day:* {self._swahili_day(worst.date)} ({format_currency(worst.total_sales, cfg)})")
            lines.append("")

        # Top items
        if week.top_items:
            if lang == "sw":
                lines.append("🥇 *Bidhaa bora wiki hii:*")
            else:
                lines.append("🥇 *Top items this week:*")
            for i, (name, qty, revenue) in enumerate(week.top_items[:5], 1):
                lines.append(f"{i}. {name} — {qty} {'mauzo' if lang == 'sw' else 'sold'}, {format_currency(revenue, cfg)}")
            lines.append("")

        # Inventory alerts
        if week.inventory_alerts:
            if lang == "sw":
                lines.append("⚠️ *Hifadhi ya chini:*")
            else:
                lines.append("⚠️ *Low stock alerts:*")
            for item in week.inventory_alerts[:4]:
                days_left = self._days_of_stock(item)
                if lang == "sw":
                    lines.append(f"   • {item.item_name}: imesalia siku {days_left:.0f}")
                else:
                    lines.append(f"   • {item.item_name}: {days_left:.0f} days left")
            lines.append("")

        # Cash flow visualization
        if week.daily_data:
            if lang == "sw":
                lines.append("💰 *Mtiririko wa pesa:*")
            else:
                lines.append("💰 *Cash flow:*")
            lines.append(self.cashflow.render(
                week.total_sales, week.total_purchases, locale=lang
            ))
            lines.append("")

        # Insights
        if insights:
            if lang == "sw":
                lines.append("💡 *Vidokezo:*")
            else:
                lines.append("💡 *Insights:*")
            for i, insight in enumerate(insights, 1):
                lines.append(f"{i}. {insight}")

        return "\n".join(lines)

    # ===================================================================
    # 3. MONTHLY REPORT — Ripoti ya Mwezi
    # ===================================================================

    def generate_monthly(
        self,
        profile: UserProfile,
        month_data: MonthlyDataAgg,
        previous_months: Optional[List[MonthlyDataAgg]] = None,
        inventory: Optional[List[InventoryItem]] = None,
        peer_data: Optional[List[PeerBusiness]] = None,
    ) -> str:
        """Generate the monthly report (Ripoti ya Mwezi).

        Monthly business health check with profit margin, trend analysis,
        item performance, expense breakdown, health score, and
        recommendations for next month.

        Args:
            profile: User profile.
            month_data: This month's aggregated data.
            previous_months: List of previous months for trend (optional).
            inventory: Current inventory state (optional).
            peer_data: Peer businesses for comparison (optional).

        Returns:
            Formatted WhatsApp message string.
        """
        lang = profile.language
        cfg = self._chart_config(profile)

        profit = month_data.total_sales - month_data.total_purchases
        profit_margin = (profit / month_data.total_sales * 100) if month_data.total_sales > 0 else 0

        # Month-over-month growth
        if month_data.previous_month_sales > 0:
            sales_growth = ((month_data.total_sales - month_data.previous_month_sales) / month_data.previous_month_sales) * 100
        else:
            sales_growth = 0

        # Build message
        lines = []

        # Header
        month_name = SWAHILI_MONTHS[month_data.month - 1]
        lines.append(f"📊 *Ripoti ya Mwezi — {profile.business_name}*")
        lines.append(f"📅 {month_name} {month_data.year}")
        lines.append("")

        # Greeting
        if lang == "sw":
            lines.append(f"👤 {profile.name}, muhtasari wa mwezi huu:")
        else:
            lines.append(f"👤 {profile.name}, this month's summary:")
        lines.append("")

        # Key metrics
        lines.append(f"💰 *{'Mauzo jumla' if lang == 'sw' else 'Total sales'}:* {format_currency(month_data.total_sales, cfg)} ({month_data.total_transactions} {'mauzo' if lang == 'sw' else 'transactions'})")
        lines.append(f"🛒 *{'Manunuzi jumla' if lang == 'sw' else 'Total purchases'}:* {format_currency(month_data.total_purchases, cfg)}")
        lines.append(f"📈 *{'Faida jumla' if lang == 'sw' else 'Total profit'}:* {format_currency(profit, cfg)}")
        lines.append(f"📊 *{'Kiwango cha faida' if lang == 'sw' else 'Profit margin'}:* {profit_margin:.1f}%")
        lines.append("")

        # Monthly trend (last 3 months)
        if previous_months and len(previous_months) >= 2:
            if lang == "sw":
                lines.append("📈 *Mwezi kwa mwezi:*")
            else:
                lines.append("📈 *Month by month:*")

            trend_data = {}
            for m in previous_months[-3:]:
                m_label = SWAHILI_MONTHS_SHORT[m.month - 1]
                trend_data[m_label] = m.total_sales
            # Add current month
            current_label = SWAHILI_MONTHS_SHORT[month_data.month - 1]
            trend_data[current_label] = month_data.total_sales

            chart = self.bar_chart.render(
                trend_data,
                max_label_width=3,
                highlight_max=True,
                currency=True,
            )
            lines.append(chart)

            growth_arrow = ARROW_UP if sales_growth >= 0 else ARROW_DOWN
            lines.append(f"{growth_arrow} *{'Ukuaji' if lang == 'sw' else 'Growth'}:* {format_percentage(sales_growth)} {'mwezi huu' if lang == 'sw' else 'this month'}")
            lines.append("")

        # Top items
        if month_data.top_items:
            if lang == "sw":
                lines.append("🏆 *Bidhaa bora:*")
            else:
                lines.append("🏆 *Top items:*")
            for i, (name, qty, revenue) in enumerate(month_data.top_items[:5], 1):
                pct = (revenue / month_data.total_sales * 100) if month_data.total_sales > 0 else 0
                lines.append(f"{i}. {name} — {format_currency(revenue, cfg)} ({pct:.0f}%)")
            lines.append("")

        # Expense breakdown
        if month_data.expense_categories:
            if lang == "sw":
                lines.append("💸 *Matumizi:*")
            else:
                lines.append("💸 *Expenses:*")
            total_expenses = sum(month_data.expense_categories.values())
            for category, amount in sorted(
                month_data.expense_categories.items(), key=lambda x: x[1], reverse=True
            )[:5]:
                pct = (amount / total_expenses * 100) if total_expenses > 0 else 0
                category_sw = self._translate_category(category, lang)
                lines.append(f"   • {category_sw}: {format_currency(amount, cfg)} ({pct:.0f}%)")
            lines.append("")

        # Health score
        health_metrics = self._build_health_metrics(month_data, previous_months, profile)
        health_result = self.health_scorer.calculate_health_score(health_metrics)
        lines.append(self.health_scorer.render_health_report(health_result, lang))
        lines.append("")

        # Comparison with similar businesses
        if peer_data:
            comparison = self.comparison_engine.compare(
                user_revenue=month_data.total_sales,
                user_margin=profit_margin / 100,
                user_growth=sales_growth,
                user_transactions=month_data.total_transactions,
                user_diversity=len(month_data.top_items),
                user_savings_rate=health_metrics.savings_rate,
                peer_data=peer_data,
                business_type=profile.business_type,
                market=profile.location,
                locale=lang,
            )
            lines.append(self.comparison_engine.render_for_whatsapp(comparison, lang))
            lines.append("")

        # Recommendations
        recommendations = self._generate_monthly_recommendations(
            month_data, previous_months, health_result, lang
        )
        if recommendations:
            if lang == "sw":
                lines.append("💡 *Mapendekezo ya mwezi ujao:*")
            else:
                lines.append("💡 *Recommendations for next month:*")
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec}")

        return "\n".join(lines)

    # ===================================================================
    # 4. SEMI-ANNUAL REPORT — Ripoti ya Nusu Mwaka
    # ===================================================================

    def generate_semiannual(
        self,
        profile: UserProfile,
        monthly_data_list: List[MonthlyDataAgg],
        peer_data: Optional[List[PeerBusiness]] = None,
    ) -> str:
        """Generate the semi-annual report (Ripoti ya Nusu Mwaka).

        6-month strategic review with trend analysis, seasonal patterns,
        product portfolio evolution, cash reserve analysis, goal setting,
        and business narrative.

        Args:
            profile: User profile.
            monthly_data_list: List of 6 monthly data points.
            peer_data: Peer businesses for comparison (optional).

        Returns:
            Formatted WhatsApp message string.
        """
        lang = profile.language
        cfg = self._chart_config(profile)

        if not monthly_data_list:
            return self._no_data_message(lang)

        # Calculate totals
        total_sales = sum(m.total_sales for m in monthly_data_list)
        total_purchases = sum(m.total_purchases for m in monthly_data_list)
        total_profit = total_sales - total_purchases
        profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0

        # Determine period
        first_month = monthly_data_list[0]
        last_month = monthly_data_list[-1]
        period_start = f"{SWAHILI_MONTHS_SHORT[first_month.month - 1]} {first_month.year}"
        period_end = f"{SWAHILI_MONTHS_SHORT[last_month.month - 1]} {last_month.year}"

        # Build message
        lines = []

        # Header
        lines.append(f"📊 *Ripoti ya Nusu Mwaka — {profile.business_name}*")
        lines.append(f"📅 {period_start} - {period_end}")
        lines.append("")

        # Greeting
        if lang == "sw":
            lines.append(f"👤 {profile.name}, huu ni muhtasari wa miezi 6:")
        else:
            lines.append(f"👤 {profile.name}, here's your 6-month summary:")
        lines.append("")

        # Key metrics
        lines.append(f"💰 *{'Mauzo jumla' if lang == 'sw' else 'Total sales'}:* {format_currency(total_sales, cfg)}")
        lines.append(f"📈 *{'Faida jumla' if lang == 'sw' else 'Total profit'}:* {format_currency(total_profit, cfg)}")
        lines.append(f"📊 *{'Kiwango cha faida' if lang == 'sw' else 'Profit margin'}:* {profit_margin:.1f}%")
        lines.append("")

        # Monthly trend
        if lang == "sw":
            lines.append("📈 *Mwezi kwa mwezi:*")
        else:
            lines.append("📈 *Month by month:*")

        trend_data = {}
        for m in monthly_data_list:
            label = SWAHILI_MONTHS_SHORT[m.month - 1]
            trend_data[label] = m.total_sales

        chart = self.bar_chart.render(
            trend_data,
            max_label_width=3,
            highlight_max=True,
            currency=True,
        )
        lines.append(chart)
        lines.append("")

        # Overall growth
        if len(monthly_data_list) >= 2:
            first_sales = monthly_data_list[0].total_sales
            last_sales = monthly_data_list[-1].total_sales
            if first_sales > 0:
                total_growth = ((last_sales - first_sales) / first_sales) * 100
                growth_arrow = ARROW_UP if total_growth >= 0 else ARROW_DOWN
                lines.append(f"{growth_arrow} *{'Ukuaji wa miezi 6' if lang == 'sw' else '6-month growth'}:* {format_percentage(total_growth)}")
                lines.append("")

        # Seasonal analysis
        seasonal_monthly = [
            MonthlyData(year=m.year, month=m.month, revenue=m.total_sales, profit=m.profit)
            for m in monthly_data_list
        ]
        seasonal_result = self.seasonal_analyzer.analyze(seasonal_monthly, lang)
        lines.append(self.seasonal_analyzer.render_for_whatsapp(seasonal_result, lang))
        lines.append("")

        # Product portfolio evolution
        if monthly_data_list:
            self._render_product_evolution(monthly_data_list, lines, lang, cfg)
            lines.append("")

        # Health score
        health_metrics = self._build_health_metrics_semiannual(monthly_data_list, profile)
        health_result = self.health_scorer.calculate_health_score(health_metrics)
        lines.append(self.health_scorer.render_health_report(health_result, lang))
        lines.append("")

        # Investment readiness
        invest_result = self.health_scorer.calculate_investment_readiness(health_metrics)
        if lang == "sw":
            lines.append(f"📊 *Uwekezaji tayari:* {invest_result.score:.0f}/100")
            if invest_result.ready:
                lines.append(f"   ✅ {invest_result.recommendation_sw}")
            else:
                lines.append(f"   ⏳ {invest_result.recommendation_sw}")
        else:
            lines.append(f"📊 *Investment readiness:* {invest_result.score:.0f}/100")
            if invest_result.ready:
                lines.append(f"   ✅ {invest_result.recommendation_en}")
            else:
                lines.append(f"   ⏳ {invest_result.recommendation_en}")
        lines.append("")

        # Goals for next 6 months
        goals = self._generate_semiannual_goals(monthly_data_list, health_result, lang)
        if goals:
            if lang == "sw":
                lines.append("💡 *Malengo ya miezi 6 ijayo:*")
            else:
                lines.append("💡 *Goals for next 6 months:*")
            for i, goal in enumerate(goals, 1):
                lines.append(f"{i}. {goal}")

        return "\n".join(lines)

    # ===================================================================
    # 5. ANNUAL REPORT — Ripoti ya Mwaka
    # ===================================================================

    def generate_annual(
        self,
        profile: UserProfile,
        monthly_data_list: List[MonthlyDataAgg],
        previous_year_sales: float = 0.0,
        peer_data: Optional[List[PeerBusiness]] = None,
    ) -> str:
        """Generate the annual report (Ripoti ya Mwaka).

        The complete picture — the report that changes everything.
        For the first time, an informal worker sees their ENTIRE YEAR
        in data. Includes full financials, monthly heatmap, product
        portfolio, business maturity, tax estimation, credit readiness,
        business narrative, and next year planning.

        Args:
            profile: User profile.
            monthly_data_list: List of 12 monthly data points.
            previous_year_sales: Previous year's total sales for YoY comparison.
            peer_data: Peer businesses for comparison (optional).

        Returns:
            Formatted WhatsApp message string.
        """
        lang = profile.language
        cfg = self._chart_config(profile)

        if not monthly_data_list:
            return self._no_data_message(lang)

        year = monthly_data_list[0].year

        # Calculate totals
        total_sales = sum(m.total_sales for m in monthly_data_list)
        total_purchases = sum(m.total_purchases for m in monthly_data_list)
        total_profit = total_sales - total_purchases
        profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
        total_transactions = sum(m.total_transactions for m in monthly_data_list)

        # Year-over-year growth
        if previous_year_sales > 0:
            yoy_growth = ((total_sales - previous_year_sales) / previous_year_sales) * 100
        else:
            yoy_growth = None

        # Best and worst months
        best_month = max(monthly_data_list, key=lambda m: m.total_sales)
        worst_month = min(monthly_data_list, key=lambda m: m.total_sales)

        # Aggregate top items across all months
        all_items: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        for m in monthly_data_list:
            for name, qty, revenue in m.top_items:
                existing_qty, existing_rev = all_items[name]
                all_items[name] = (existing_qty + qty, existing_rev + revenue)
        top_items = sorted(all_items.items(), key=lambda x: x[1][1], reverse=True)

        # Health score
        health_metrics = self._build_health_metrics_annual(monthly_data_list, profile)
        health_result = self.health_scorer.calculate_health_score(health_metrics)

        # Credit readiness
        credit_result = self.health_scorer.calculate_credit_readiness(health_metrics)

        # Build message
        lines = []

        # Header with double divider
        lines.append(f"📊 *Ripoti ya Mwaka — {profile.business_name}*")
        lines.append(f"📅 {year}")
        lines.append("")
        lines.append(f"👤 {profile.name}, huu ni mwaka wako wa biashara:")
        lines.append("")

        # Grand totals with visual separator
        lines.append(divider("═", 23))
        lines.append(f"💰 *{'MAUZO JUMLA' if lang == 'sw' else 'TOTAL SALES'}:* {format_currency(total_sales, cfg)}")
        lines.append(f"📈 *{'FAIDA JUMLA' if lang == 'sw' else 'TOTAL PROFIT'}:* {format_currency(total_profit, cfg)}")
        lines.append(f"📊 *{'Kiwango cha faida' if lang == 'sw' else 'Profit margin'}:* {profit_margin:.1f}%")
        lines.append(divider("═", 23))
        lines.append("")

        # Monthly heatmap (full year)
        if lang == "sw":
            lines.append("📅 *Mwezi kwa mwezi:*")
        else:
            lines.append("📅 *Month by month:*")

        monthly_sales = {m.month: m.total_sales for m in monthly_data_list}
        heatmap_chart = self.heatmap.render(monthly_sales, locale=lang)
        lines.append(heatmap_chart)

        # Best/worst month
        lines.append("")
        lines.append(f"🏆 *{'Mwezi bora' if lang == 'sw' else 'Best month'}:* {SWAHILI_MONTHS[best_month.month - 1]} ({format_currency(best_month.total_sales, cfg)})")
        lines.append(f"📉 *{'Mwezi dhaifu' if lang == 'sw' else 'Weakest month'}:* {SWAHILI_MONTHS[worst_month.month - 1]} ({format_currency(worst_month.total_sales, cfg)})")
        lines.append("")

        # Top products
        if top_items:
            if lang == "sw":
                lines.append("🥇 *Bidhaa bora za mwaka:*")
            else:
                lines.append("🥇 *Top products of the year:*")
            for i, (name, (qty, revenue)) in enumerate(top_items[:5], 1):
                pct = (revenue / total_sales * 100) if total_sales > 0 else 0
                lines.append(f"{i}. {name} — {format_currency(revenue, cfg)} ({pct:.0f}%)")
            lines.append("")

        # Year-over-year growth
        if yoy_growth is not None:
            growth_arrow = ARROW_UP if yoy_growth >= 0 else ARROW_DOWN
            lines.append(f"💰 *{'Ukuaji' if lang == 'sw' else 'Growth'}:* {growth_arrow} {format_percentage(yoy_growth)} {'kuliko mwaka jana' if lang == 'sw' else 'vs last year'}")
            lines.append("")

        # Health score
        lines.append(self.health_scorer.render_health_report(health_result, lang))
        lines.append("")

        # Credit readiness
        lines.append(self.health_scorer.render_credit_report(credit_result, lang))
        lines.append("")

        # Tax estimation
        if total_profit > 0:
            estimated_tax = total_profit * 0.15  # Simplified Kenya tax rate
            if lang == "sw":
                lines.append("📋 *Ushuru (makadirio):*")
                lines.append(f"   {format_currency(total_profit, cfg)} faida × 15% = {format_currency(estimated_tax, cfg)}")
                lines.append("   (Hii ni makadirio tu — si lazima kulipa bado)")
            else:
                lines.append("📋 *Tax (estimate):*")
                lines.append(f"   {format_currency(total_profit, cfg)} profit × 15% = {format_currency(estimated_tax, cfg)}")
                lines.append("   (This is just an estimate — not required to pay yet)")
            lines.append("")

        # Business narrative ("My Business Year" story)
        narrative = self._generate_business_narrative(
            profile, monthly_data_list, total_sales, total_profit, yoy_growth, lang
        )
        if narrative:
            if lang == "sw":
                lines.append("📖 *Hadithi ya mwaka wako:*")
            else:
                lines.append("📖 *Your business story:*")
            lines.append(f'"{narrative}"')
            lines.append("")

        # Goals for next year
        goals = self._generate_annual_goals(
            monthly_data_list, health_result, credit_result, lang
        )
        if goals:
            if lang == "sw":
                lines.append(f"💡 *Malengo ya {year + 1}:*")
            else:
                lines.append(f"💡 *Goals for {year + 1}:*")
            for i, goal in enumerate(goals, 1):
                lines.append(f"{i}. {goal}")

        return "\n".join(lines)

    # ===================================================================
    # Helper Methods
    # ===================================================================

    def _chart_config(self, profile: UserProfile):
        """Create a ChartConfig from user profile."""
        from .whatsapp_charts import ChartConfig
        return ChartConfig(currency_prefix=profile.currency, locale=profile.language)

    def _swahili_day(self, d: date) -> str:
        """Get Swahili day name for a date."""
        return SWAHILI_DAYS_SHORT[d.weekday()]

    def _swahili_day_short(self, d: date) -> str:
        """Get short Swahili day name for a date."""
        names = ["Jp", "Jt", "Jn", "Al", "Ij", "Js", "Jp"]
        return names[d.weekday()]

    def _format_date(self, d: date, lang: str = "sw") -> str:
        """Format a date in Swahili style."""
        month_name = SWAHILI_MONTHS[d.month - 1]
        return f"{d.day} {month_name} {d.year}"

    def _days_of_stock(self, item: InventoryItem) -> float:
        """Calculate days of stock remaining."""
        if item.daily_usage_rate > 0:
            return item.current_stock / item.daily_usage_rate
        return 999  # Unknown

    def _translate_category(self, category: str, lang: str) -> str:
        """Translate expense category to requested language."""
        translations = {
            "sw": {
                "raw_materials": "Unnga & bidhaa za msingi",
                "transport": "Usafiri",
                "rent": "Kodi & gharama",
                "utilities": "Umeme & maji",
                "packaging": "Ufungaji",
                "labor": "Mishahara",
                "other": "Mengine",
            },
            "en": {
                "raw_materials": "Raw materials",
                "transport": "Transport",
                "rent": "Rent & costs",
                "utilities": "Utilities",
                "packaging": "Packaging",
                "labor": "Labor",
                "other": "Other",
            },
        }
        lang_map = translations.get(lang, translations["sw"])
        return lang_map.get(category, category)

    def _no_data_message(self, lang: str) -> str:
        """Generate a message when there's no data."""
        if lang == "sw":
            return "📊 *Ripoti*\n\nHakuna data ya kutosha kutengeneza ripoti. Anza kurekodi mauzo yako!"
        return "📊 *Report*\n\nNot enough data to generate a report. Start recording your sales!"

    # -------------------------------------------------------------------
    # Daily Tip Generation
    # -------------------------------------------------------------------

    def _generate_daily_tip(
        self,
        today: DailyData,
        yesterday: Optional[DailyData],
        avg_sales: float,
        lang: str,
    ) -> str:
        """Generate one actionable tip based on today's data.

        Args:
            today: Today's data.
            yesterday: Yesterday's data.
            avg_sales: Average daily sales.
            lang: Language.

        Returns:
            Tip string.
        """
        tips = []

        # Best item tip
        if today.best_item and today.best_item_qty >= 3:
            if lang == "sw":
                tips.append(f"{today.best_item} yanaongezeka soko leo. Ongeza stock ya kesho!")
            else:
                tips.append(f"{today.best_item} is selling well today. Increase stock for tomorrow!")

        # Sales comparison tip
        if yesterday and today.total_sales > yesterday.total_sales * 1.2:
            if lang == "sw":
                tips.append("Mauzo yameongezeka sana! Weka bei nzuri kwa bidhaa zinazouzwa vizuri.")
            else:
                tips.append("Sales jumped! Keep pricing optimized for your best sellers.")
        elif yesterday and today.total_sales < yesterday.total_sales * 0.7:
            if lang == "sw":
                tips.append("Mauzo yamepungua — jaribu kuongeza matangazo au kubadilisha bidhaa.")
            else:
                tips.append("Sales dropped — try promoting or adjusting your product mix.")

        # Low profit tip
        profit = today.total_sales - today.total_purchases
        if today.total_sales > 0 and profit / today.total_sales < 0.15:
            if lang == "sw":
                tips.append("Faida ni ndogo — angalia bei za manunuzi na uongeze bei kidogo.")
            else:
                tips.append("Profit is low — check purchase prices and consider raising prices.")

        # Default tip
        if not tips:
            if lang == "sw":
                tips.append("Endelea kurekodi mauzo yako kila siku — data inasaidia!")
            else:
                tips.append("Keep recording your sales daily — data helps!")

        return tips[0]

    # -------------------------------------------------------------------
    # Weekly Insights
    # -------------------------------------------------------------------

    def _generate_weekly_insights(
        self,
        week: WeeklyData,
        previous_week: Optional[WeeklyData],
        lang: str,
    ) -> List[str]:
        """Generate 2-3 insights for the weekly report.

        Args:
            week: This week's data.
            previous_week: Previous week's data.
            lang: Language.

        Returns:
            List of insight strings.
        """
        insights = []

        # Best day pattern
        if week.daily_data:
            best = max(week.daily_data, key=lambda d: d.total_sales)
            best_day_name = self._swahili_day(best.date)
            if lang == "sw":
                insights.append(
                    f"{best_day_name} ndio soko yako bora — hakikisha stock ya kutosha siku hiyo"
                )
            else:
                insights.append(
                    f"{best_day_name} is your best day — make sure you have enough stock"
                )

        # Weak day pattern
        if week.daily_data and len(week.daily_data) >= 5:
            worst = min(week.daily_data, key=lambda d: d.total_sales)
            worst_day_name = self._swahili_day(worst.date)
            if lang == "sw":
                insights.append(
                    f"{worst_day_name} ni siku dhaifu — fikiria kupunguza manunuzi siku hiyo"
                )
            else:
                insights.append(
                    f"{worst_day_name} is your weakest day — consider reducing purchases"
                )

        # Top item trend
        if week.top_items:
            top = week.top_items[0]
            if lang == "sw":
                insights.append(
                    f"{top[0]} yanaongezeka — ongeza uzalishaji wiki ijayo"
                )
            else:
                insights.append(
                    f"{top[0]} is trending up — increase production next week"
                )

        return insights[:3]

    # -------------------------------------------------------------------
    # Monthly Recommendations
    # -------------------------------------------------------------------

    def _generate_monthly_recommendations(
        self,
        month: MonthlyDataAgg,
        previous_months: Optional[List[MonthlyDataAgg]],
        health: HealthScoreResult,
        lang: str,
    ) -> List[str]:
        """Generate recommendations for next month.

        Args:
            month: This month's data.
            previous_months: Previous months' data.
            health: Health score result.
            lang: Language.

        Returns:
            List of recommendation strings.
        """
        recs = []

        # Top item recommendation
        if month.top_items:
            top = month.top_items[0]
            if lang == "sw":
                recs.append(f"Ongeza uzalishaji wa {top[0]} — ndio bidhaa yako bora")
            else:
                recs.append(f"Increase production of {top[0]} — it's your best product")

        # Savings recommendation
        profit = month.total_sales - month.total_purchases
        if profit > 0:
            savings_target = profit * 0.10
            if lang == "sw":
                recs.append(f"Weka akiba ya {format_currency(savings_target)} kwa matumizi ya dharura")
            else:
                recs.append(f"Save {format_currency(savings_target)} for emergencies")

        # Product diversification
        if len(month.top_items) <= 2:
            if lang == "sw":
                recs.append("Fikiria kuongeza bidhaa mpya — bidhaa mbalimbali huleta wateja wapya")
            else:
                recs.append("Consider adding new products — diversity attracts new customers")

        return recs[:3]

    # -------------------------------------------------------------------
    # Product Evolution (Semi-annual)
    # -------------------------------------------------------------------

    def _render_product_evolution(
        self,
        monthly_data_list: List[MonthlyDataAgg],
        lines: List[str],
        lang: str,
        cfg: Any,
    ) -> None:
        """Render product portfolio evolution over 6 months.

        Args:
            monthly_data_list: List of monthly data.
            lines: Output lines (mutated).
            lang: Language.
            cfg: Chart config.
        """
        # Track products across months
        product_trend: Dict[str, List[float]] = defaultdict(list)
        for m in monthly_data_list:
            items_dict = {name: revenue for name, _, revenue in m.top_items}
            all_products = set()
            for prev_m in monthly_data_list:
                for name, _, _ in prev_m.top_items:
                    all_products.add(name)

            for product in all_products:
                product_trend[product].append(items_dict.get(product, 0))

        if not product_trend:
            return

        # Find gaining and declining products
        gaining = []
        declining = []

        for product, values in product_trend.items():
            if len(values) >= 2 and values[0] > 0:
                change = ((values[-1] - values[0]) / values[0]) * 100
                if change > 20:
                    gaining.append((product, change, values[-1]))
                elif change < -10:
                    declining.append((product, change, values[-1]))

        if gaining:
            if lang == "sw":
                lines.append("🏆 *Bidhaa zilizoongezeka:*")
            else:
                lines.append("🏆 *Growing products:*")
            for product, change, latest in sorted(gaining, key=lambda x: x[1], reverse=True)[:3]:
                lines.append(f"📈 {product}: {format_percentage(change)} ({format_currency(latest, cfg)})")

        if declining:
            lines.append("")
            if lang == "sw":
                lines.append("📉 *Bidhaa zilizopungua:*")
            else:
                lines.append("📉 *Declining products:*")
            for product, change, latest in sorted(declining, key=lambda x: x[1])[:3]:
                lines.append(f"📉 {product}: {format_percentage(change)} ({format_currency(latest, cfg)})")

    # -------------------------------------------------------------------
    # Goal Generation
    # -------------------------------------------------------------------

    def _generate_semiannual_goals(
        self,
        monthly_data_list: List[MonthlyDataAgg],
        health: HealthScoreResult,
        lang: str,
    ) -> List[str]:
        """Generate goals for next 6 months.

        Args:
            monthly_data_list: Current 6 months data.
            health: Health score result.
            lang: Language.

        Returns:
            List of goal strings.
        """
        goals = []
        avg_monthly = statistics.mean(m.total_sales for m in monthly_data_list) if monthly_data_list else 0

        # Revenue goal
        target_revenue = avg_monthly * 1.25  # 25% growth target
        if lang == "sw":
            goals.append(f"Fikisha mauzo ya {format_currency(target_revenue)}/mwezi")
        else:
            goals.append(f"Reach {format_currency(target_revenue)}/month in sales")

        # Savings goal
        total_profit = sum(m.total_sales - m.total_purchases for m in monthly_data_list)
        savings_target = total_profit * 0.15
        if lang == "sw":
            goals.append(f"Fikia akiba ya {format_currency(savings_target)}")
        else:
            goals.append(f"Build savings to {format_currency(savings_target)}")

        # Product goal
        if lang == "sw":
            goals.append("Ongeza bidhaa mpya 2")
        else:
            goals.append("Add 2 new products")

        return goals

    def _generate_annual_goals(
        self,
        monthly_data_list: List[MonthlyDataAgg],
        health: HealthScoreResult,
        credit: Any,
        lang: str,
    ) -> List[str]:
        """Generate goals for next year.

        Args:
            monthly_data_list: Current year data.
            health: Health score result.
            credit: Credit readiness result.
            lang: Language.

        Returns:
            List of goal strings.
        """
        goals = []
        avg_monthly = statistics.mean(m.total_sales for m in monthly_data_list) if monthly_data_list else 0

        # Revenue goal
        target = avg_monthly * 1.30  # 30% annual growth
        if lang == "sw":
            goals.append(f"Fikisha mauzo ya {format_currency(target)}/mwezi")
        else:
            goals.append(f"Reach {format_currency(target)}/month in sales")

        # Business formalization
        if lang == "sw":
            goals.append("Fungua duka la kudumu")
            goals.append("Ajiri mtu mmoja")
        else:
            goals.append("Open a permanent shop")
            goals.append("Hire one employee")

        # Tax/formalization
        if health.overall_score >= 60:
            if lang == "sw":
                goals.append("Anza kulipa ushuru (formalize)")
            else:
                goals.append("Start paying taxes (formalize)")

        return goals

    # -------------------------------------------------------------------
    # Business Narrative
    # -------------------------------------------------------------------

    def _generate_business_narrative(
        self,
        profile: UserProfile,
        monthly_data: List[MonthlyDataAgg],
        total_sales: float,
        total_profit: float,
        yoy_growth: Optional[float],
        lang: str,
    ) -> str:
        """Generate a narrative summary of the business year.

        This is the "story" that makes the data human and meaningful.

        Args:
            profile: User profile.
            monthly_data: Monthly data for the year.
            total_sales: Total annual sales.
            total_profit: Total annual profit.
            yoy_growth: Year-over-year growth.
            lang: Language.

        Returns:
            Narrative string.
        """
        if not monthly_data:
            return ""

        first_month = monthly_data[0]
        last_month = monthly_data[-1]
        best_month = max(monthly_data, key=lambda m: m.total_sales)
        top_items = []
        for m in monthly_data:
            for name, _, _ in m.top_items:
                if name not in top_items:
                    top_items.append(name)

        if lang == "sw":
            narrative = (
                f"{profile.name}, mwaka {first_month.year} ulianza na biashara "
                f"ya {format_currency(first_month.total_sales)}/mwezi. "
            )

            if yoy_growth and yoy_growth > 0:
                narrative += (
                    f"Leo, biashara yako imefikia {format_currency(last_month.total_sales)}/mwezi "
                    f"— ukuaji wa {yoy_growth:.0f}%! "
                )

            if top_items:
                narrative += f"{top_items[0]} yako ndio bidhaa maarufu {profile.location}. "

            narrative += (
                f"{SWAHILI_MONTHS[best_month.month - 1]} ulikuwa na mwezi bora zaidi. "
                f"Sasa unayo data ya kutosha kuomba mkopo na kuanzisha duka la kudumu."
            )
        else:
            narrative = (
                f"{profile.name}, {first_month.year} started with "
                f"{format_currency(first_month.total_sales)}/month in sales. "
            )

            if yoy_growth and yoy_growth > 0:
                narrative += (
                    f"Today, your business reached {format_currency(last_month.total_sales)}/month "
                    f"— {yoy_growth:.0f}% growth! "
                )

            if top_items:
                narrative += f"Your {top_items[0]} is the most popular in {profile.location}. "

            narrative += (
                f"{SWAHILI_MONTHS[best_month.month - 1]} was your best month. "
                f"You now have enough data to apply for a loan and start a permanent shop."
            )

        return narrative

    # -------------------------------------------------------------------
    # Health Metrics Builders
    # -------------------------------------------------------------------

    def _build_health_metrics(
        self,
        month: MonthlyDataAgg,
        previous_months: Optional[List[MonthlyDataAgg]],
        profile: UserProfile,
    ) -> BusinessMetrics:
        """Build BusinessMetrics for monthly health score.

        Args:
            month: Current month data.
            previous_months: Previous months data.
            profile: User profile.

        Returns:
            BusinessMetrics instance.
        """
        profit = month.total_sales - month.total_purchases
        margin = profit / month.total_sales if month.total_sales > 0 else 0

        # Calculate growth
        growth = 0
        if month.previous_month_sales > 0:
            growth = ((month.total_sales - month.previous_month_sales) / month.previous_month_sales) * 100

        # Calculate consistency from daily data
        daily_revenues = [d.total_sales for d in month.daily_data if d.total_sales > 0]
        if len(daily_revenues) >= 2:
            cv = statistics.stdev(daily_revenues) / statistics.mean(daily_revenues) if statistics.mean(daily_revenues) > 0 else 0
        else:
            cv = 0

        # Product concentration
        top_product_concentration = 0
        if month.top_items and month.total_sales > 0:
            top_product_concentration = month.top_items[0][2] / month.total_sales

        return BusinessMetrics(
            total_revenue=month.total_sales,
            total_expenses=month.total_purchases,
            total_profit=profit,
            total_transactions=month.total_transactions,
            days_active=month.active_days,
            days_in_period=30,
            current_period_revenue=month.total_sales,
            previous_period_revenue=month.previous_month_sales,
            revenue_growth_pct=growth,
            daily_revenues=daily_revenues,
            coefficient_of_variation=cv,
            unique_products=len(month.top_items),
            top_product_concentration=top_product_concentration,
            savings_rate=0,  # Would need savings data
            expense_categories=month.expense_categories,
            months_of_data=len(previous_months) + 1 if previous_months else 1,
            business_type=profile.business_type,
            location=profile.location,
        )

    def _build_health_metrics_semiannual(
        self,
        monthly_data_list: List[MonthlyDataAgg],
        profile: UserProfile,
    ) -> BusinessMetrics:
        """Build BusinessMetrics for semi-annual health score."""
        total_sales = sum(m.total_sales for m in monthly_data_list)
        total_purchases = sum(m.total_purchases for m in monthly_data_list)
        total_profit = total_sales - total_purchases
        total_transactions = sum(m.total_transactions for m in monthly_data_list)

        # Growth from first to last month
        if len(monthly_data_list) >= 2 and monthly_data_list[0].total_sales > 0:
            growth = ((monthly_data_list[-1].total_sales - monthly_data_list[0].total_sales) / monthly_data_list[0].total_sales) * 100
        else:
            growth = 0

        # Aggregate daily revenues
        all_daily = []
        for m in monthly_data_list:
            all_daily.extend(d.total_sales for d in m.daily_data if d.total_sales > 0)

        cv = statistics.stdev(all_daily) / statistics.mean(all_daily) if len(all_daily) >= 2 and statistics.mean(all_daily) > 0 else 0

        # Aggregate products
        all_items: Dict[str, float] = defaultdict(float)
        for m in monthly_data_list:
            for name, _, revenue in m.top_items:
                all_items[name] += revenue

        top_product_concentration = max(all_items.values()) / total_sales if all_items and total_sales > 0 else 0

        return BusinessMetrics(
            total_revenue=total_sales,
            total_expenses=total_purchases,
            total_profit=total_profit,
            total_transactions=total_transactions,
            days_active=sum(m.active_days for m in monthly_data_list),
            days_in_period=len(monthly_data_list) * 30,
            revenue_growth_pct=growth,
            daily_revenues=all_daily,
            coefficient_of_variation=cv,
            unique_products=len(all_items),
            top_product_concentration=top_product_concentration,
            months_of_data=len(monthly_data_list),
            business_type=profile.business_type,
            location=profile.location,
        )

    def _build_health_metrics_annual(
        self,
        monthly_data_list: List[MonthlyDataAgg],
        profile: UserProfile,
    ) -> BusinessMetrics:
        """Build BusinessMetrics for annual health score."""
        return self._build_health_metrics_semiannual(monthly_data_list, profile)
