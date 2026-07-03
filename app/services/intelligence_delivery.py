"""
Intelligence Delivery Service — Msaidizi ↔ Angavu Intelligence Pipeline

Delivers processed intelligence back to Msaidizi devices. Formats
intelligence for display in the worker's local language (Swahili, English,
or Sheng).

Data Flow (Angavu Intelligence → Msaidizi):
    Backend processes data → generates intelligence
    → Push notification to device
    → Device pulls intelligence (when online)
    → Displayed to worker in local language

Intelligence priorities:
    1. Urgent alerts (restock, price drop, credit opportunity)
    2. Daily insights (profit, top items, trends)
    3. Weekly reports (market comparison, growth)

All text is translated to the worker's preferred language. Translations
are human-readable, not machine-translated — they use the vocabulary
and patterns familiar to Kenyan informal workers.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Inventory, Transaction
from app.models.user import User
from app.schemas.sync import AlertItem, DailyBriefing, IntelligenceUpdate

logger = structlog.get_logger(__name__)


# =========================================================================
# Local Language Translations
# =========================================================================

# Translation dictionaries for UI strings used in intelligence delivery.
# These are NOT machine translations — they use the vocabulary and patterns
# familiar to Kenyan informal workers (dukawallahs, mama mbogas, boda boda).

TRANSLATIONS = {
    "sw": {
        "profit_today": "Faida ya leo",
        "revenue_today": "Mapato ya leo",
        "transactions_today": "Mauzo ya leo",
        "top_item": "Bidhaa inayouzwa zaidi",
        "restock_alert": "Bidhaa imepungua — nunua zaidi",
        "price_drop": "Bei ya soko imepungua",
        "credit_opportunity": "Fursa ya mkopo ipo",
        "demand_spike": "Mahitaji yameongezeka",
        "seasonal_tip": "Kidokezo cha msimu",
        "daily_summary": "Muhtasari wa biashara ya leo",
        "weekly_summary": "Muhtasari wa wiki hii",
        "market_trend": "Mwelekeo wa soko",
        "restock_now": "Nunua sasa",
        "check_prices": "Angalia bei",
        "apply_credit": "Omba mkopo",
        "your_score": "Alama yako ya biashara",
        "growing": "Biashara inakua",
        "stable": "Biashara imara",
        "declining": "Biashara inapungua",
        "no_data": "Hakuna data ya kutosha bado",
        "sync_needed": "Tuma data yako ili upate taarifa",
        "good_morning": "Habari za asubuhi",
        "good_afternoon": "Habari za mchana",
        "good_evening": "Habari za jioni",
        "kes": "KSh",
    },
    "en": {
        "profit_today": "Today's profit",
        "revenue_today": "Today's revenue",
        "transactions_today": "Today's transactions",
        "top_item": "Best-selling item",
        "restock_alert": "Low stock — restock needed",
        "price_drop": "Market price has dropped",
        "credit_opportunity": "Credit opportunity available",
        "demand_spike": "Demand has increased",
        "seasonal_tip": "Seasonal tip",
        "daily_summary": "Today's business summary",
        "weekly_summary": "This week's summary",
        "market_trend": "Market trend",
        "restock_now": "Restock now",
        "check_prices": "Check prices",
        "apply_credit": "Apply for credit",
        "your_score": "Your business score",
        "growing": "Business growing",
        "stable": "Business stable",
        "declining": "Business declining",
        "no_data": "Not enough data yet",
        "sync_needed": "Sync your data to get insights",
        "good_morning": "Good morning",
        "good_afternoon": "Good afternoon",
        "good_evening": "Good evening",
        "kes": "KES",
    },
    "sh": {
        "profit_today": "Profit ya leo",
        "revenue_today": "Cash ya leo",
        "transactions_today": "Deals za leo",
        "top_item": "Item yenye sales mob",
        "restock_alert": "Stock imepungua — ingiza zaidi",
        "price_drop": "Bei imeanguka",
        "credit_opportunity": "Kuna loan poa",
        "demand_spike": "Demand imepanda",
        "seasonal_tip": "Tip ya season",
        "daily_summary": "Summary ya biz leo",
        "weekly_summary": "Summary ya week",
        "market_trend": "Market trend",
        "restock_now": "Ingiza sasa",
        "check_prices": "Check bei",
        "apply_credit": "Apply loan",
        "your_score": "Score yako",
        "growing": "Biz inakua",
        "stable": "Biz iko poa",
        "declining": "Biz inadrop",
        "no_data": "Hakuna data bado",
        "sync_needed": "Sync data yako upate info",
        "good_morning": "Safi sana asubuhi",
        "good_afternoon": "Safi sana mchana",
        "good_evening": "Safi sana jioni",
        "kes": "KSh",
    },
}


def t(key: str, language: str = "sw") -> str:
    """Get a translated string for the given key and language."""
    lang = language if language in TRANSLATIONS else "sw"
    return TRANSLATIONS.get(lang, TRANSLATIONS["sw"]).get(key, key)


def format_currency_kes(amount: float, language: str = "sw") -> str:
    """Format a KES amount for display."""
    if amount >= 1_000_000:
        return f"{t('kes', language)} {amount / 1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"{t('kes', language)} {amount / 1_000:.1f}K"
    else:
        return f"{t('kes', language)} {amount:,.0f}"


def get_greeting(language: str = "sw") -> str:
    """Get time-appropriate greeting in local language."""
    hour = datetime.now(timezone.utc).hour  # Would adjust for EAT in production
    if hour < 12:
        return t("good_morning", language)
    elif hour < 17:
        return t("good_afternoon", language)
    else:
        return t("good_evening", language)


# =========================================================================
# Intelligence Delivery Service
# =========================================================================


class IntelligenceDelivery:
    """
    Delivers intelligence to Msaidizi devices.

    Formats intelligence for display in the worker's language.
    Priority: urgent alerts > daily insights > weekly reports.

    This service bridges the gap between complex backend analytics
    and the simple, actionable insights that informal workers need.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_intelligence_for_worker(
        self,
        worker_id_hash: str,
        language: str = "sw",
        since: Optional[datetime] = None,
    ) -> Dict:
        """
        Get complete intelligence update for a worker.

        This is the main entry point called by the sync API when a device
        pulls intelligence. It assembles all intelligence components into
        a single response formatted for device display.

        Args:
            worker_id_hash: HMAC-SHA256 hashed worker ID
            language: Preferred language (sw, en, sh)
            since: Only return updates since this timestamp

        Returns:
            IntelligenceUpdate dictionary for device display
        """
        logger.info(
            "intelligence_delivery_started",
            worker_id_hash=worker_id_hash[:12] + "...",
            language=language,
            since=since,
        )

        # Generate daily briefing
        briefing = await self.get_daily_briefing(worker_id_hash, language)

        # Get urgent alerts
        alerts = await self.get_alerts(worker_id_hash, language)

        # Get market insights for worker's area/product
        market_insights = await self._get_market_insights(
            worker_id_hash, language
        )

        result = {
            "worker_id_hash": worker_id_hash,
            "language": language,
            "briefing": briefing,
            "alerts": [a if isinstance(a, dict) else a.model_dump() for a in alerts],
            "alama_score": None,  # Would come from Alama Score service
            "alama_score_band": None,
            "market_insights": market_insights,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "intelligence_delivery_completed",
            worker_id_hash=worker_id_hash[:12] + "...",
            alerts_count=len(alerts),
            has_briefing=briefing is not None,
        )

        return result

    async def get_daily_briefing(
        self,
        worker_id_hash: str,
        language: str = "sw",
    ) -> Optional[Dict]:
        """
        Generate daily briefing: profit, alerts, recommendations.

        Aggregates today's transactions into a simple summary that
        the worker can understand at a glance.

        Args:
            worker_id_hash: Hashed worker ID
            language: Preferred language

        Returns:
            DailyBriefing dictionary or None if no data
        """
        today = datetime.now(timezone.utc).date()
        today_start = datetime.combine(today, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        today_end = datetime.combine(today, datetime.max.time()).replace(
            tzinfo=timezone.utc
        )

        # Query today's transactions for this worker
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == worker_id_hash[:32],  # Approximate match
                    Transaction.timestamp >= today_start,
                    Transaction.timestamp <= today_end,
                )
            )
        )
        transactions = result.scalars().all()

        if not transactions:
            # No data today — return a helpful nudge
            return {
                "worker_id_hash": worker_id_hash,
                "date": today.isoformat(),
                "language": language,
                "summary": f"{get_greeting(language)}. {t('sync_needed', language)}.",
                "profit_today": None,
                "revenue_today": None,
                "transactions_today": 0,
                "top_item": None,
                "alerts": [],
                "recommendations": [t("sync_needed", language)],
                "market_trend": None,
            }

        # Calculate daily metrics
        sales = [tx for tx in transactions if tx.transaction_type == "SALE"]
        purchases = [tx for tx in transactions if tx.transaction_type == "PURCHASE"]
        expenses = [tx for tx in transactions if tx.transaction_type == "EXPENSE"]

        revenue = sum(tx.amount for tx in sales)
        cost = sum(tx.amount for tx in purchases)
        expense_total = sum(tx.amount for tx in expenses)
        profit = sum(tx.profit for tx in sales if tx.profit is not None)
        if profit == 0 and revenue > 0:
            profit = revenue - cost - expense_total

        # Find top item
        item_sales = {}
        for tx in sales:
            if tx.item:
                item_sales[tx.item] = item_sales.get(tx.item, 0) + tx.amount
        top_item = max(item_sales, key=item_sales.get) if item_sales else None

        # Build summary
        greeting = get_greeting(language)
        if profit > 0:
            summary = (
                f"{greeting}! {t('profit_today', language)}: "
                f"{format_currency_kes(profit, language)}. "
                f"{len(transactions)} {t('transactions_today', language).lower()}."
            )
        else:
            summary = (
                f"{greeting}. {t('transactions_today', language)}: {len(transactions)}."
            )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            sales=sales,
            purchases=purchases,
            profit=profit,
            revenue=revenue,
            language=language,
        )

        return {
            "worker_id_hash": worker_id_hash,
            "date": today.isoformat(),
            "language": language,
            "summary": summary,
            "profit_today": round(profit, 2),
            "revenue_today": round(revenue, 2),
            "transactions_today": len(transactions),
            "top_item": top_item,
            "alerts": [],
            "recommendations": recommendations,
            "market_trend": None,
        }

    async def get_alerts(
        self,
        worker_id_hash: str,
        language: str = "sw",
    ) -> List[Dict]:
        """
        Get urgent alerts for a worker.

        Alert types:
        - restock: Item below restock threshold
        - price_drop: Market price dropped for worker's products
        - credit_opportunity: Worker qualifies for credit
        - demand_spike: Unusual demand for a product
        - seasonal_tip: Seasonal business advice

        Args:
            worker_id_hash: Hashed worker ID
            language: Preferred language

        Returns:
            List of AlertItem dictionaries
        """
        alerts = []

        # Check inventory for restock alerts
        restock_alerts = await self._check_restock_alerts(
            worker_id_hash, language
        )
        alerts.extend(restock_alerts)

        # Check for demand spikes (unusual transaction volume)
        demand_alerts = await self._check_demand_spikes(
            worker_id_hash, language
        )
        alerts.extend(demand_alerts)

        # Add seasonal tips
        seasonal = self._get_seasonal_tip(language)
        if seasonal:
            alerts.append(seasonal)

        # Sort by severity: critical > warning > info
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: severity_order.get(a.get("severity", "info"), 2))

        return alerts

    async def get_intelligence_freshness(
        self,
        worker_id_hash: str,
    ) -> Optional[datetime]:
        """
        Get the timestamp of the most recent intelligence update.

        Args:
            worker_id_hash: Hashed worker ID

        Returns:
            Datetime of last intelligence update, or None
        """
        result = await self.db.execute(
            select(func.max(Transaction.synced_at)).where(
                Transaction.user_id == worker_id_hash[:32]
            )
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _check_restock_alerts(
        self,
        worker_id_hash: str,
        language: str,
    ) -> List[Dict]:
        """Check inventory levels and generate restock alerts."""
        alerts = []

        result = await self.db.execute(
            select(Inventory).where(
                and_(
                    Inventory.user_id == worker_id_hash[:32],
                    Inventory.restock_threshold > 0,
                    Inventory.current_stock <= Inventory.restock_threshold,
                )
            )
        )
        low_stock_items = result.scalars().all()

        for item in low_stock_items:
            severity = "critical" if item.current_stock == 0 else "warning"
            alerts.append({
                "alert_type": "restock",
                "severity": severity,
                "title": t("restock_alert", language),
                "message": (
                    f"{item.item}: {item.current_stock} {item.unit or ''} "
                    f"({t('restock_now', language).lower()})"
                ),
                "action_label": t("restock_now", language),
                "action_payload": {
                    "item": item.item,
                    "current_stock": item.current_stock,
                    "restock_threshold": item.restock_threshold,
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(hours=24)
                ).isoformat(),
            })

        return alerts

    async def _check_demand_spikes(
        self,
        worker_id_hash: str,
        language: str,
    ) -> List[Dict]:
        """
        Detect unusual demand spikes by comparing today's volume
        to the 7-day average.
        """
        alerts = []
        now = datetime.now(timezone.utc)
        today = now.date()
        today_start = datetime.combine(today, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        week_ago = today_start - timedelta(days=7)

        # Get recent transactions
        result = await self.db.execute(
            select(
                Transaction.item,
                func.date(Transaction.timestamp).label("day"),
                func.count(Transaction.id).label("count"),
            ).where(
                and_(
                    Transaction.user_id == worker_id_hash[:32],
                    Transaction.transaction_type == "SALE",
                    Transaction.timestamp >= week_ago,
                    Transaction.item.isnot(None),
                )
            ).group_by(Transaction.item, func.date(Transaction.timestamp))
        )
        rows = result.all()

        # Calculate daily averages per item
        item_days = {}
        for row in rows:
            item = row.item
            if item not in item_days:
                item_days[item] = []
            item_days[item].append(row.count)

        # Today's counts
        today_result = await self.db.execute(
            select(
                Transaction.item,
                func.count(Transaction.id).label("count"),
            ).where(
                and_(
                    Transaction.user_id == worker_id_hash[:32],
                    Transaction.transaction_type == "SALE",
                    Transaction.timestamp >= today_start,
                    Transaction.item.isnot(None),
                )
            ).group_by(Transaction.item)
        )
        today_counts = {row.item: row.count for row in today_result.all()}

        # Compare
        for item, counts in item_days.items():
            if len(counts) < 3:
                continue
            avg = sum(counts) / len(counts)
            today_count = today_counts.get(item, 0)
            if today_count > avg * 2 and today_count >= 3:
                alerts.append({
                    "alert_type": "demand_spike",
                    "severity": "info",
                    "title": t("demand_spike", language),
                    "message": (
                        f"{item}: {today_count} sold today "
                        f"(avg: {avg:.0f}/day)"
                    ),
                    "action_label": t("check_prices", language),
                    "action_payload": {"item": item, "today": today_count, "avg": round(avg, 1)},
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(hours=12)
                    ).isoformat(),
                })

        return alerts

    def _generate_recommendations(
        self,
        sales: list,
        purchases: list,
        profit: float,
        revenue: float,
        language: str,
    ) -> List[str]:
        """Generate actionable recommendations based on today's data."""
        recommendations = []

        # Profit margin check
        if revenue > 0:
            margin = profit / revenue
            if margin < 0.1:
                recommendations.append(
                    "Margin yako ni ndogo. Angalia bei za kununua."  # TODO: proper translations
                    if language == "sw"
                    else "Your margin is low. Check your purchase prices."
                )
            elif margin > 0.5:
                recommendations.append(
                    "Margin yako ni nzuri! Fikiria kuongeza stock."
                    if language == "sw"
                    else "Great margin! Consider increasing stock."
                )

        # Transaction volume
        if len(sales) < 3:
            recommendations.append(
                "Mauzo ni machache leo. Jaribu kupanga bidhaa vizuri."
                if language == "sw"
                else "Low sales today. Try rearranging your products."
            )

        # Payment method mix
        mpesa_count = sum(1 for tx in sales if tx.payment_method == "mpesa")
        cash_count = sum(1 for tx in sales if tx.payment_method == "cash")
        if cash_count > 0 and mpesa_count == 0:
            recommendations.append(
                "Jaribu M-Pesa — ni salama zaidi na rahisi."
                if language == "sw"
                else "Try M-Pesa — it's safer and easier to track."
            )

        return recommendations[:3]  # Max 3 recommendations

    async def _get_market_insights(
        self,
        worker_id_hash: str,
        language: str,
    ) -> Optional[Dict]:
        """
        Get relevant market insights for the worker's area and products.

        This provides context about the broader market that the worker
        operates in — helping them make informed decisions.
        """
        # Get worker's recent items
        result = await self.db.execute(
            select(
                Transaction.item,
                func.count(Transaction.id).label("count"),
                func.avg(Transaction.amount).label("avg_amount"),
            ).where(
                and_(
                    Transaction.user_id == worker_id_hash[:32],
                    Transaction.transaction_type == "SALE",
                    Transaction.timestamp >= datetime.now(timezone.utc) - timedelta(days=30),
                    Transaction.item.isnot(None),
                )
            ).group_by(Transaction.item).order_by(
                func.count(Transaction.id).desc()
            ).limit(5)
        )
        top_items = result.all()

        if not top_items:
            return None

        return {
            "top_products": [
                {
                    "item": row.item,
                    "transaction_count": row.count,
                    "avg_price": round(row.avg_amount, 2),
                }
                for row in top_items
            ],
            "language": language,
            "period": "last_30_days",
        }

    def _get_seasonal_tip(self, language: str) -> Optional[Dict]:
        """
        Generate seasonal business tips based on the current month.

        Kenya's informal economy has strong seasonal patterns:
        - Jan-Feb: Back to school (stationery, uniforms)
        - Mar-Apr: Long rains begin (umbrellas, waterproof goods)
        - May-Jun: Cold season (warm clothing, hot beverages)
        - Jul-Aug: Mid-year (general)
        - Sep-Oct: Short rains (rain gear)
        - Nov-Dec: Holiday season (gifts, food, decorations)
        """
        month = datetime.now(timezone.utc).month

        seasonal_tips = {
            1: ("Bidhaa za shule zinahitajika sasa", "School supplies are in demand"),
            2: ("Mavazi ya shule bado yanauzwa", "School uniforms still selling well"),
            3: ("Mvua zinakuja — jenga stock ya mwavuli", "Rains coming — stock umbrellas"),
            4: ("Msimu wa mvua — bidhaa za kujikinga zinauzwa", "Rainy season — waterproof goods selling"),
            5: ("Baridi inakuja — chai na nguo za joto", "Cold weather — hot drinks and warm clothing"),
            6: ("Msimu wa baridi — ongeza bidhaa za joto", "Cold season — add warm products"),
            7: ("Biashara imara — angalia bei za soko", "Business steady — watch market prices"),
            8: ("Mwezi mzuri wa kuweka akiba", "Good month to save"),
            9: ("Mvua za mfupi zinakuja", "Short rains approaching"),
            10: ("Msimu wa mwisho wa mwaka unakaribia", "Year-end season approaching"),
            11: ("Bei za zawadi zinaanza kupanda", "Gift prices starting to rise"),
            12: ("Msimu wa likizo — ongeza stock!", "Holiday season — increase stock!"),
        }

        tip = seasonal_tips.get(month)
        if not tip:
            return None

        sw_tip, en_tip = tip
        message = sw_tip if language == "sw" else en_tip

        return {
            "alert_type": "seasonal_tip",
            "severity": "info",
            "title": t("seasonal_tip", language),
            "message": message,
            "action_label": None,
            "action_payload": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
        }
