"""
DigitalAgent — Domain intelligence for M-Pesa agents, social media sellers, gig workers.

Capabilities:
    - Commission tracking by platform
    - Client management
    - Gig economy patterns (irregular income smoothing)
    - Income forecasting
    - Platform fee tracking
    - ROI on digital marketing
    - Float management (for M-Pesa agents)

Tier: 2 (Domain) — activated when worker type is DIGITAL
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DigitalAgent:
    """
    Specialized intelligence for digital/gig workers.

    Analyzes commission income, platform fees, and irregular income
    patterns to provide earnings optimization and forecasting.
    """

    name = "DigitalAgent"
    role = "Digital/gig economy intelligence specialist"
    tier = 2
    worker_types = ["mpesa_agent", "social_media_seller", "gig_worker", "freelancer", "content_creator"]

    def __init__(self):
        self._logger = logger.bind(agent=self.name)

    # ── Digital Income Analysis ─────────────────────────────────────

    def analyze_income(
        self,
        transactions: list[dict[str, Any]],
        period_days: int = 30,
    ) -> dict[str, Any]:
        """
        Analyze digital/gig income patterns.

        Args:
            transactions: Transaction dicts
            period_days: Analysis window

        Returns:
            Dict with digital-specific analytics
        """
        if not transactions:
            return self._empty_analysis()

        income = [
            t for t in transactions
            if t.get("transaction_type") == "SALE"
        ]
        expenses = [
            t for t in transactions
            if t.get("transaction_type") in ("PURCHASE", "EXPENSE")
        ]

        # Commission tracking
        commission_analysis = self._analyze_commissions(income)

        # Platform analysis
        platform_analysis = self._analyze_platforms(income)

        # Income smoothing
        income_smoothing = self._analyze_income_stability(income)

        # Fee tracking
        fee_analysis = self._analyze_fees(expenses)

        # Client analysis
        client_analysis = self._analyze_clients(income)

        total_income = sum(t.get("amount", 0) for t in income)
        total_expenses = sum(t.get("amount", 0) for t in expenses)
        net_income = total_income - total_expenses

        return {
            "period_days": period_days,
            "income_count": len(income),
            "expense_count": len(expenses),
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_income": round(net_income, 2),
            "avg_transaction": round(
                total_income / len(income), 2
            ) if income else 0,
            "commission_analysis": commission_analysis,
            "platform_analysis": platform_analysis,
            "income_smoothing": income_smoothing,
            "fee_analysis": fee_analysis,
            "client_analysis": client_analysis,
        }

    def _analyze_commissions(
        self, income: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze commission-based income."""
        # Group by service type (M-Pesa commission, ad sales, etc.)
        service_data: dict[str, dict[str, float]] = defaultdict(
            lambda: {"total": 0, "count": 0, "profit": 0}
        )
        for t in income:
            item = t.get("item", "Unknown")
            service_data[item]["total"] += t.get("amount", 0)
            service_data[item]["count"] += 1
            service_data[item]["profit"] += t.get("profit", 0) or 0

        ranked = sorted(
            service_data.items(), key=lambda x: x[1]["total"], reverse=True
        )
        return {
            "by_service": [
                {
                    "service": name,
                    "total": round(d["total"], 2),
                    "count": int(d["count"]),
                    "avg_per_transaction": round(
                        d["total"] / d["count"], 2
                    ) if d["count"] else 0,
                    "profit": round(d["profit"], 2),
                }
                for name, d in ranked[:10]
            ],
        }

    def _analyze_platforms(
        self, income: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze income by platform/channel."""
        channel_data: dict[str, float] = defaultdict(float)
        for t in income:
            channel = t.get("recorded_via", "unknown")
            channel_data[channel] += t.get("amount", 0)

        total = sum(channel_data.values())
        return {
            "by_channel": {
                ch: {
                    "revenue": round(v, 2),
                    "pct": round(v / total * 100, 1) if total > 0 else 0,
                }
                for ch, v in sorted(
                    channel_data.items(), key=lambda x: x[1], reverse=True
                )
            },
        }

    def _analyze_income_stability(
        self, income: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze income stability (important for gig workers)."""
        daily_totals: dict[str, float] = defaultdict(float)
        for t in income:
            ts = t.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                day_key = ts.strftime("%Y-%m-%d")
                daily_totals[day_key] += t.get("amount", 0)

        if not daily_totals:
            return {"avg_daily": 0, "std_dev": 0, "stability_score": 0, "zero_income_days": 0}

        values = list(daily_totals.values())
        avg = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0

        # Stability score: 100 = perfectly stable, 0 = highly variable
        cv = (std / avg) if avg > 0 else 0  # Coefficient of variation
        stability_score = max(0, min(100, 100 - (cv * 100)))

        # Count zero-income days
        period = max(daily_totals.keys()) > min(daily_totals.keys()) if len(daily_totals) > 1 else False
        all_days = set()
        if period:
            start = datetime.strptime(min(daily_totals.keys()), "%Y-%m-%d")
            end = datetime.strptime(max(daily_totals.keys()), "%Y-%m-%d")
            current = start
            while current <= end:
                all_days.add(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
        zero_days = len(all_days - set(daily_totals.keys()))

        return {
            "avg_daily": round(avg, 2),
            "std_dev": round(std, 2),
            "stability_score": round(stability_score, 1),
            "zero_income_days": zero_days,
            "coefficient_of_variation": round(cv, 2),
        }

    def _analyze_fees(
        self, expenses: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze platform/transaction fees."""
        fee_categories: dict[str, float] = defaultdict(float)
        for t in expenses:
            item = (t.get("item") or "").lower()
            if any(kw in item for kw in ["fee", "charge", "commission", "transaction cost"]):
                fee_categories[t.get("item", "fees")] += t.get("amount", 0)
            else:
                fee_categories["operational"] += t.get("amount", 0)

        total_fees = sum(fee_categories.values())
        return {
            "breakdown": {k: round(v, 2) for k, v in fee_categories.items()},
            "total": round(total_fees, 2),
        }

    def _analyze_clients(
        self, income: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze client patterns."""
        client_data: dict[str, dict[str, float]] = defaultdict(
            lambda: {"transactions": 0, "total": 0}
        )
        for t in income:
            client_key = t.get("customer_phone_hash") or t.get("item", "unknown")
            client_data[client_key]["transactions"] += 1
            client_data[client_key]["total"] += t.get("amount", 0)

        total_clients = len(client_data)
        repeat = sum(1 for d in client_data.values() if d["transactions"] > 1)

        return {
            "total_clients": total_clients,
            "repeat_clients": repeat,
            "retention_rate_pct": round(
                repeat / total_clients * 100, 1
            ) if total_clients > 0 else 0,
        }

    # ── Recommendations ─────────────────────────────────────────────

    def get_recommendations(
        self,
        analysis: dict[str, Any],
        language: str = "en",
    ) -> list[dict[str, str]]:
        """Generate digital/gig-specific recommendations."""
        recs = []

        # Income stability
        smoothing = analysis.get("income_smoothing", {})
        stability = smoothing.get("stability_score", 0)
        if stability < 50:
            recs.append({
                "category": "stability",
                "title": "Income is irregular" if language == "en" else "Mapato si thabiti",
                "message": (
                    "Your income varies a lot day-to-day. "
                    "Build a buffer: save 20% on good days to cover slow days. "
                    "Try to diversify income sources."
                    if language == "en" else
                    "Mapato yako yanatofauti sana siku hadi siku. "
                    "Jenga akiba: weka 20% siku nzuri kufunika siku mbaya. "
                    "Jaribu kutoa vyanzo tofauti vya mapato."
                ),
                "priority": "high",
            })

        # Zero income days
        zero_days = smoothing.get("zero_income_days", 0)
        if zero_days > 5:
            recs.append({
                "category": "consistency",
                "title": "Too many zero-income days" if language == "en" else "Siku nyingi bila mapato",
                "message": (
                    f"You had {zero_days} days with no income. "
                    "Set a daily minimum target and try to work consistently."
                    if language == "en" else
                    f"Ulikuwa na siku {zero_days} bila mapato. "
                    "Weka lengo la chini la kila siku na jaribu kufanya kazi kwa uthabiti."
                ),
                "priority": "medium",
            })

        # Fee optimization
        fees = analysis.get("fee_analysis", {})
        total_fees = fees.get("total", 0)
        total_income = analysis.get("total_income", 0)
        if total_income > 0 and total_fees > total_income * 0.15:
            recs.append({
                "category": "fees",
                "title": "High platform fees" if language == "en" else "Gharama za juu za jukwaa",
                "message": (
                    f"Fees are KSh {total_fees:,.0f} ({total_fees/total_income*100:.0f}% of income). "
                    "Review if there are cheaper transaction methods."
                    if language == "en" else
                    f"Gharama ni KSh {total_fees:,.0f} ({total_fees/total_income*100:.0f}% ya mapato). "
                    "Kagua kama kuna njia za muamala bei nafuu."
                ),
                "priority": "medium",
            })

        # Client retention
        clients = analysis.get("client_analysis", {})
        retention = clients.get("retention_rate_pct", 0)
        if retention < 40:
            recs.append({
                "category": "clients",
                "title": "Grow repeat clients" if language == "en" else "Kuza wateja wa kudumu",
                "message": (
                    f"Only {retention:.0f}% of clients return. "
                    "Follow up after transactions. Offer referral bonuses."
                    if language == "en" else
                    f"Wateja {retention:.0f}% tu wanarudi. "
                    "Fuata baada ya miamala. Toa bonasi za rufani."
                ),
                "priority": "medium",
            })

        # Top service
        commissions = analysis.get("commission_analysis", {})
        services = commissions.get("by_service", [])
        if services:
            top = services[0]
            recs.append({
                "category": "focus",
                "title": "Focus on top earner" if language == "en" else "Zingatia kipato kikuu",
                "message": (
                    f"'{top['service']}' earns you KSh {top['total']:,.0f}. "
                    "This is your best earner — maximize this service."
                    if language == "en" else
                    f"'{top['service']}' inakuletea KSh {top['total']:,.0f}. "
                    "Hii ndiyo kipato chako kikuu — ongeza huduma hii."
                ),
                "priority": "medium",
            })

        return recs

    def _empty_analysis(self) -> dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "period_days": 0,
            "income_count": 0,
            "expense_count": 0,
            "total_income": 0,
            "total_expenses": 0,
            "net_income": 0,
            "avg_transaction": 0,
            "commission_analysis": {"by_service": []},
            "platform_analysis": {"by_channel": {}},
            "income_smoothing": {
                "avg_daily": 0, "std_dev": 0, "stability_score": 0,
                "zero_income_days": 0, "coefficient_of_variation": 0,
            },
            "fee_analysis": {"breakdown": {}, "total": 0},
            "client_analysis": {
                "total_clients": 0, "repeat_clients": 0, "retention_rate_pct": 0,
            },
        }
