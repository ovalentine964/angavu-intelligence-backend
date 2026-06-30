"""
Report generation service.

Generates business reports for users in their preferred language.
Reports are structured for delivery via WhatsApp, Telegram, SMS, or app.

Report types:
- Daily: End-of-day business summary
- Weekly: Weekly trends and patterns
- Advice: AI-generated business recommendations
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.report import (
    AdviceItem,
    AdviceReport,
    DailyReport,
    TopProduct,
    TransactionSummary,
    WeeklyReport,
    WeeklyTrend,
)
from app.services.pipeline import DataPipeline

logger = structlog.get_logger(__name__)


class ReportGenerator:
    """
    Generates business intelligence reports for Msaidizi users.

    Reports are generated in the user's preferred language (Swahili,
    English, or Sheng) and formatted for their communication channel.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.pipeline = DataPipeline(db)

    # =========================================================================
    # Daily Report
    # =========================================================================

    async def generate_daily_report(
        self,
        user: User,
        report_date: Optional[date] = None,
    ) -> DailyReport:
        """
        Generate a daily business summary report.

        Shows total sales, expenses, profit, top products,
        and comparison with yesterday and last week.

        Args:
            user: The user to generate the report for
            report_date: Date to generate for (defaults to today)

        Returns:
            DailyReport with all metrics
        """
        if report_date is None:
            report_date = date.today()

        period_start = report_date
        period_end = report_date

        # Get today's metrics
        metrics = await self.pipeline.aggregate_user_metrics(
            user.id, period_start, period_end
        )

        # Get yesterday's metrics for comparison
        yesterday = report_date - timedelta(days=1)
        yesterday_metrics = await self.pipeline.aggregate_user_metrics(
            user.id, yesterday, yesterday
        )

        # Get last week's daily average
        week_ago_start = report_date - timedelta(days=7)
        week_ago_end = report_date - timedelta(days=1)
        week_metrics = await self.pipeline.aggregate_user_metrics(
            user.id, week_ago_start, week_ago_end
        )

        # Calculate comparisons
        vs_yesterday_pct = None
        if yesterday_metrics["total_sales"] > 0:
            vs_yesterday_pct = round(
                (metrics["total_sales"] - yesterday_metrics["total_sales"])
                / yesterday_metrics["total_sales"]
                * 100,
                1,
            )

        vs_week_avg_pct = None
        week_daily_avg = week_metrics["total_sales"] / 7 if week_metrics["total_sales"] > 0 else 0
        if week_daily_avg > 0:
            vs_week_avg_pct = round(
                (metrics["total_sales"] - week_daily_avg) / week_daily_avg * 100,
                1,
            )

        # Build top products
        top_products = [
            TopProduct(
                item=p["item"],
                quantity_sold=p["quantity_sold"],
                revenue=p["revenue"],
                profit=p["profit"],
                transaction_count=p["transaction_count"],
                avg_price=p["avg_price"],
            )
            for p in metrics["top_products"][:5]
        ]

        # Build hourly breakdown
        hourly = self._compute_hourly_breakdown(
            metrics.get("daily_breakdown", [])
        )

        # Find busiest hour
        busiest_hour = None
        peak_sales = None
        if hourly:
            busiest = max(hourly, key=lambda h: h.sales)
            busiest_hour = busiest.hour
            peak_sales = busiest.sales

        # Low stock alerts (placeholder — would query inventory)
        low_stock = await self._get_low_stock_items(user.id)

        # Debt summary (placeholder)
        debt_count, debt_total = await self._get_debt_summary(user.id)

        return DailyReport(
            user_id=str(user.id),
            report_date=report_date,
            summary=TransactionSummary(
                total_sales=metrics["total_sales"],
                total_purchases=metrics["total_purchases"],
                total_expenses=metrics["total_expenses"],
                gross_profit=metrics["gross_profit"],
                net_profit=metrics["net_profit"],
                transaction_count=metrics["transaction_count"],
                average_transaction_value=metrics["avg_transaction_value"],
                profit_margin_pct=metrics["profit_margin_pct"],
            ),
            top_products=top_products,
            hourly_breakdown=hourly,
            vs_yesterday_pct=vs_yesterday_pct,
            vs_last_week_avg_pct=vs_week_avg_pct,
            busiest_hour=busiest_hour,
            peak_sales_amount=peak_sales,
            low_stock_items=low_stock,
            outstanding_debts_count=debt_count,
            outstanding_debts_total=debt_total,
            language=user.language or "sw",
        )

    # =========================================================================
    # Weekly Report
    # =========================================================================

    async def generate_weekly_report(
        self,
        user: User,
        week_end: Optional[date] = None,
    ) -> WeeklyReport:
        """
        Generate a weekly business report with trends.

        Shows week-over-week trends, best/worst days,
        product performance, and payment method mix.

        Args:
            user: The user to generate for
            week_end: End of the week (defaults to today)

        Returns:
            WeeklyReport with trends and insights
        """
        if week_end is None:
            week_end = date.today()
        week_start = week_end - timedelta(days=6)

        # Current week metrics
        current = await self.pipeline.aggregate_user_metrics(
            user.id, week_start, week_end
        )

        # Previous week for comparison
        prev_end = week_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6)
        previous = await self.pipeline.aggregate_user_metrics(
            user.id, prev_start, prev_end
        )

        # Compute trends
        trends_data = await self.pipeline.compute_trends(user.id, weeks=1)
        trends = [
            WeeklyTrend(
                metric=t["metric"],
                current_value=t["current_value"],
                previous_value=t["previous_value"],
                change_pct=t["change_pct"],
                direction=t["direction"],
            )
            for t in trends_data.get("trends", [])
        ]

        # Daily summaries for the week
        daily_summaries = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_metrics = await self.pipeline.aggregate_user_metrics(
                user.id, day, day
            )
            daily_summaries.append(TransactionSummary(
                total_sales=day_metrics["total_sales"],
                total_purchases=day_metrics["total_purchases"],
                total_expenses=day_metrics["total_expenses"],
                gross_profit=day_metrics["gross_profit"],
                net_profit=day_metrics["net_profit"],
                transaction_count=day_metrics["transaction_count"],
                average_transaction_value=day_metrics["avg_transaction_value"],
                profit_margin_pct=day_metrics["profit_margin_pct"],
            ))

        # Find best/worst days
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        if daily_summaries:
            best_idx = max(
                range(len(daily_summaries)),
                key=lambda i: daily_summaries[i].total_sales,
            )
            worst_idx = min(
                range(len(daily_summaries)),
                key=lambda i: daily_summaries[i].total_sales,
            )
            best_day = day_names[best_idx]
            worst_day = day_names[worst_idx]
        else:
            best_day = None
            worst_day = None

        # Top and bottom products
        top_products = [
            TopProduct(
                item=p["item"],
                quantity_sold=p["quantity_sold"],
                revenue=p["revenue"],
                profit=p["profit"],
                transaction_count=p["transaction_count"],
                avg_price=p["avg_price"],
            )
            for p in current["top_products"][:10]
        ]

        # WoW comparisons
        wow_sales = None
        wow_profit = None
        if previous["total_sales"] > 0:
            wow_sales = round(
                (current["total_sales"] - previous["total_sales"])
                / previous["total_sales"] * 100,
                1,
            )
        if previous["net_profit"] > 0:
            wow_profit = round(
                (current["net_profit"] - previous["net_profit"])
                / previous["net_profit"] * 100,
                1,
            )

        return WeeklyReport(
            user_id=str(user.id),
            week_start=week_start,
            week_end=week_end,
            summary=TransactionSummary(
                total_sales=current["total_sales"],
                total_purchases=current["total_purchases"],
                total_expenses=current["total_expenses"],
                gross_profit=current["gross_profit"],
                net_profit=current["net_profit"],
                transaction_count=current["transaction_count"],
                average_transaction_value=current["avg_transaction_value"],
                profit_margin_pct=current["profit_margin_pct"],
            ),
            daily_summaries=daily_summaries,
            trends=trends,
            top_products=top_products,
            best_day=best_day,
            worst_day=worst_day,
            wow_sales_change_pct=wow_sales,
            wow_profit_change_pct=wow_profit,
            language=user.language or "sw",
        )

    # =========================================================================
    # Advice Report
    # =========================================================================

    async def generate_advice_report(
        self,
        user: User,
    ) -> AdviceReport:
        """
        Generate AI-powered business advice.

        Analyzes the user's transaction patterns and generates
        actionable recommendations for improving their business.

        Args:
            user: The user to generate advice for

        Returns:
            AdviceReport with prioritized recommendations
        """
        # Get 7-day and 30-day metrics
        end_date = date.today()
        metrics_7d = await self.pipeline.aggregate_user_metrics(
            user.id, end_date - timedelta(days=7), end_date
        )
        metrics_30d = await self.pipeline.aggregate_user_metrics(
            user.id, end_date - timedelta(days=30), end_date
        )

        # Detect anomalies
        anomalies = await self.pipeline.detect_anomalies(user.id, lookback_days=30)

        # Compute trends
        trends = await self.pipeline.compute_trends(user.id, weeks=4)

        # Calculate health score (0-100)
        health_score = self._calculate_health_score(
            metrics_7d, metrics_30d, trends
        )
        health_label = self._health_label(health_score)

        # Generate advice items based on analysis
        advice_items = self._generate_advice_items(
            metrics_7d, metrics_30d, trends, anomalies, user.language or "sw"
        )

        # Determine revenue trend
        revenue_trend = "stable"
        for t in trends.get("trends", []):
            if t["metric"] == "revenue":
                revenue_trend = t["direction"]
                break

        # Top growing/declining categories
        top_growing = None
        top_declining = None
        if metrics_7d["top_products"] and metrics_30d["top_products"]:
            # Simple comparison of top products
            recent_items = {p["item"]: p["revenue"] for p in metrics_7d["top_products"]}
            older_items = {p["item"]: p["revenue"] for p in metrics_30d["top_products"]}
            changes = {}
            for item in recent_items:
                if item in older_items and older_items[item] > 0:
                    changes[item] = (recent_items[item] - older_items[item]) / older_items[item]
            if changes:
                top_growing = max(changes, key=changes.get)
                top_declining = min(changes, key=changes.get)

        return AdviceReport(
            user_id=str(user.id),
            health_score=health_score,
            health_label=health_label,
            advice=advice_items,
            avg_daily_revenue_7d=round(
                metrics_7d["total_sales"] / 7, 2
            ),
            avg_daily_profit_7d=round(
                metrics_7d["net_profit"] / 7, 2
            ),
            revenue_trend=revenue_trend,
            top_growing_category=top_growing,
            top_declining_category=top_declining,
            language=user.language or "sw",
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _calculate_health_score(
        self,
        metrics_7d: Dict,
        metrics_30d: Dict,
        trends: Dict,
    ) -> int:
        """
        Calculate business health score (0-100).

        Factors:
        - Revenue consistency (30%)
        - Profit margin (25%)
        - Transaction volume trend (20%)
        - Operating days (15%)
        - Data quality (10%)
        """
        score = 0

        # Revenue consistency — based on profit margin
        margin = metrics_7d.get("profit_margin_pct", 0)
        if margin > 30:
            score += 30
        elif margin > 20:
            score += 25
        elif margin > 10:
            score += 15
        elif margin > 0:
            score += 5

        # Profit
        if metrics_7d.get("net_profit", 0) > 0:
            score += 25
        elif metrics_7d.get("gross_profit", 0) > 0:
            score += 10

        # Transaction volume trend
        for t in trends.get("trends", []):
            if t["metric"] == "transaction_count":
                if t["direction"] == "up":
                    score += 20
                elif t["direction"] == "stable":
                    score += 12
                else:
                    score += 3
                break

        # Operating days (7-day period)
        daily = metrics_7d.get("daily_breakdown", [])
        active_days = len([d for d in daily if d.get("sales", 0) > 0])
        score += int(active_days / 7 * 15)

        # Data quality — having data is good
        if metrics_7d.get("transaction_count", 0) > 20:
            score += 10
        elif metrics_7d.get("transaction_count", 0) > 10:
            score += 5

        return min(100, max(0, score))

    @staticmethod
    def _health_label(score: int) -> str:
        """Convert health score to human-readable label."""
        if score >= 80:
            return "excellent"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "fair"
        elif score >= 20:
            return "needs_attention"
        else:
            return "critical"

    def _generate_advice_items(
        self,
        metrics_7d: Dict,
        metrics_30d: Dict,
        trends: Dict,
        anomalies: List,
        language: str,
    ) -> List[AdviceItem]:
        """Generate prioritized advice items based on analysis."""
        items = []

        # Check profit margin
        margin = metrics_7d.get("profit_margin_pct", 0)
        if margin < 10 and metrics_7d.get("total_sales", 0) > 0:
            items.append(AdviceItem(
                category="pricing",
                priority="high",
                title="Increase your profit margins",
                title_sw="Ongeza faida yako",
                detail=(
                    f"Your profit margin is {margin:.0f}%. "
                    "Consider raising prices or finding cheaper suppliers."
                ),
                detail_sw=(
                    f"Faida yako ni {margin:.0f}%. "
                    "Fikiria kupandisha bei au kupata wasambazaji wazuri."
                ),
                expected_impact="10-20% profit increase",
                action_items=[
                    "Review prices for your top 5 products",
                    "Compare supplier prices at different markets",
                    "Consider buying in bulk for better prices",
                ],
            ))

        # Check transaction volume trend
        for t in trends.get("trends", []):
            if t["metric"] == "transaction_count" and t["direction"] == "down":
                items.append(AdviceItem(
                    category="operations",
                    priority="high",
                    title="Fewer customers this week",
                    title_sw="Wateja wachache wiki hii",
                    detail=(
                        f"Sales dropped {abs(t['change_pct']):.0f}% "
                        "compared to last week."
                    ),
                    detail_sw=(
                        f"Mauzo yameshuka {abs(t['change_pct']):.0f}% "
                        "ikilinganishwa na wiki iliyopita."
                    ),
                    action_items=[
                        "Check if nearby competitors changed prices",
                        "Consider promotions on slow-moving items",
                        "Extend operating hours if possible",
                    ],
                ))

        # Check for low margin on top products
        top = metrics_7d.get("top_products", [])
        for p in top[:3]:
            if p.get("profit", 0) > 0 and p.get("revenue", 0) > 0:
                item_margin = p["profit"] / p["revenue"] * 100
                if item_margin < 15:
                    items.append(AdviceItem(
                        category="pricing",
                        priority="medium",
                        title=f"Low margin on {p['item']}",
                        title_sw=f"Faida ndogo ya {p['item']}",
                        detail=(
                            f"{p['item']} has a {item_margin:.0f}% margin. "
                            "This is your top product but profit is thin."
                        ),
                        expected_impact="5-10% profit increase on this item",
                        action_items=[
                            f"Try increasing {p['item']} price by KES 5-10",
                            "Look for a cheaper supplier",
                        ],
                    ))

        # Anomaly-based advice
        for anomaly in anomalies[:2]:
            if anomaly["type"] == "low_volume_day":
                items.append(AdviceItem(
                    category="operations",
                    priority="low",
                    title="Some days had very few sales",
                    title_sw="Siku zilizo na mauzo machache",
                    detail=anomaly["description"],
                    detail_sw=anomaly["description"],
                    action_items=[
                        "Track which days are consistently slow",
                        "Consider different products on slow days",
                    ],
                ))

        # If no issues found, give positive feedback
        if not items:
            items.append(AdviceItem(
                category="general",
                priority="low",
                title="Your business is doing well!",
                title_sw="Biashara yako inaenda vizuri!",
                detail=(
                    "Keep recording your transactions daily. "
                    "Consistency helps you see patterns and make better decisions."
                ),
                detail_sw=(
                    "Endelea kurekodi mauzo yako kila siku. "
                    "Kuwa na uvumilivu kunakusaidia kuona mazuri na kufanya maamuzi bora."
                ),
            ))

        # Sort by priority and return top 5
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda x: priority_order.get(x.priority, 99))
        return items[:5]

    def _compute_hourly_breakdown(self, daily_breakdown):
        """Compute hourly sales breakdown (placeholder — needs hourly data)."""
        # In production, this would aggregate from timestamp.hour
        # For now, return empty list
        return []

    async def _get_low_stock_items(self, user_id) -> List[str]:
        """Get items below restock threshold."""
        from app.models.transaction import Inventory
        from sqlalchemy import and_, select

        result = await self.db.execute(
            select(Inventory.item).where(
                and_(
                    Inventory.user_id == user_id,
                    Inventory.current_stock <= Inventory.restock_threshold,
                    Inventory.restock_threshold > 0,
                )
            )
        )
        return [row[0] for row in result.all()]

    async def _get_debt_summary(self, user_id) -> tuple:
        """Get outstanding debt count and total. Returns (count, total)."""
        # Placeholder — would query debts table if implemented
        return 0, 0.0
