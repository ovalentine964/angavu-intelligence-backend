"""
ServiceAgent — Domain intelligence for hairdressers, barbers, mechanics, tailors, laundry.

Capabilities:
    - Job tracking and client management
    - Material cost tracking
    - Pricing recommendations (labour vs materials)
    - Client retention tracking (repeat customer rate)
    - Peak hours/days analysis
    - Service expansion recommendations

Tier: 2 (Domain) — activated when worker type is SERVICE
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class ServiceAgent:
    """
    Specialized intelligence for service workers.

    Analyzes job records, client data, and material costs to optimize
    pricing, client retention, and service offerings.
    """

    name = "ServiceAgent"
    role = "Service business intelligence specialist"
    tier = 2
    worker_types = ["hairdresser", "barber", "mechanic", "tailor", "laundry", "plumber", "electrician"]

    def __init__(self):
        self._logger = logger.bind(agent=self.name)

    # ── Service Analysis ────────────────────────────────────────────

    def analyze_services(
        self,
        transactions: List[Dict[str, Any]],
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Analyze service transactions for service-specific insights.

        Args:
            transactions: Transaction dicts
            period_days: Analysis window

        Returns:
            Dict with service-specific analytics
        """
        if not transactions:
            return self._empty_analysis()

        sales = [
            t for t in transactions
            if t.get("transaction_type") == "SALE"
        ]
        expenses = [
            t for t in transactions
            if t.get("transaction_type") in ("PURCHASE", "EXPENSE")
        ]

        # Service performance
        service_analysis = self._analyze_services(sales)

        # Client analysis
        client_analysis = self._analyze_clients(sales)

        # Labour vs materials
        labour_materials = self._labour_vs_materials(sales, expenses)

        # Daily/hourly patterns
        daily_patterns = self._analyze_patterns(sales)

        # Pricing analysis
        pricing = self._analyze_pricing(sales)

        total_revenue = sum(t.get("amount", 0) for t in sales)
        total_expenses = sum(t.get("amount", 0) for t in expenses)

        return {
            "period_days": period_days,
            "job_count": len(sales),
            "expense_count": len(expenses),
            "total_revenue": round(total_revenue, 2),
            "total_expenses": round(total_expenses, 2),
            "total_profit": round(total_revenue - total_expenses, 2),
            "avg_job_value": round(
                total_revenue / len(sales), 2
            ) if sales else 0,
            "service_analysis": service_analysis,
            "client_analysis": client_analysis,
            "labour_vs_materials": labour_materials,
            "daily_patterns": daily_patterns,
            "pricing_analysis": pricing,
        }

    def _analyze_services(
        self, sales: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze performance per service type."""
        service_data: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"revenue": 0, "profit": 0, "count": 0}
        )
        for t in sales:
            service = t.get("item", "Unknown Service")
            service_data[service]["revenue"] += t.get("amount", 0)
            service_data[service]["profit"] += t.get("profit", 0) or 0
            service_data[service]["count"] += 1

        ranked = sorted(
            service_data.items(), key=lambda x: x[1]["revenue"], reverse=True
        )
        return [
            {
                "service": name,
                "revenue": round(d["revenue"], 2),
                "profit": round(d["profit"], 2),
                "job_count": int(d["count"]),
                "avg_price": round(d["revenue"] / d["count"], 2) if d["count"] else 0,
                "margin_pct": round(
                    d["profit"] / d["revenue"] * 100, 1
                ) if d["revenue"] > 0 else 0,
            }
            for name, d in ranked[:15]
        ]

    def _analyze_clients(
        self, sales: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze client patterns from transactions."""
        # Use customer_phone_hash or source_text to identify repeat clients
        client_visits: Dict[str, int] = defaultdict(int)
        client_spend: Dict[str, float] = defaultdict(float)

        for t in sales:
            # Use phone hash if available, else use source text fingerprint
            client_key = t.get("customer_phone_hash") or t.get("item", "unknown")
            client_visits[client_key] += 1
            client_spend[client_key] += t.get("amount", 0)

        total_clients = len(client_visits)
        repeat_clients = sum(1 for v in client_visits.values() if v > 1)
        retention_rate = (repeat_clients / total_clients * 100) if total_clients > 0 else 0

        avg_visits = statistics.mean(client_visits.values()) if client_visits else 0
        avg_spend = statistics.mean(client_spend.values()) if client_spend else 0

        return {
            "total_clients": total_clients,
            "repeat_clients": repeat_clients,
            "retention_rate_pct": round(retention_rate, 1),
            "avg_visits_per_client": round(avg_visits, 1),
            "avg_spend_per_client": round(avg_spend, 2),
            "top_clients": [
                {"client": k, "visits": v, "total_spend": round(client_spend[k], 2)}
                for k, v in sorted(
                    client_visits.items(), key=lambda x: x[1], reverse=True
                )[:5]
            ],
        }

    def _labour_vs_materials(
        self,
        sales: List[Dict[str, Any]],
        expenses: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Break down revenue into labour vs material components."""
        total_revenue = sum(t.get("amount", 0) for t in sales)
        total_materials = sum(t.get("amount", 0) for t in expenses)

        labour_value = total_revenue - total_materials
        labour_pct = (labour_value / total_revenue * 100) if total_revenue > 0 else 0

        return {
            "total_revenue": round(total_revenue, 2),
            "material_costs": round(total_materials, 2),
            "labour_value": round(labour_value, 2),
            "labour_pct": round(labour_pct, 1),
            "material_pct": round(100 - labour_pct, 1),
        }

    def _analyze_patterns(
        self, sales: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze service demand patterns by day and hour."""
        day_names = [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ]
        day_data: Dict[int, Dict[str, float]] = defaultdict(
            lambda: {"revenue": 0, "count": 0}
        )
        hour_data: Dict[int, float] = defaultdict(float)

        for t in sales:
            ts = t.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                dow = ts.weekday()
                day_data[dow]["revenue"] += t.get("amount", 0)
                day_data[dow]["count"] += 1
                hour_data[ts.hour] += t.get("amount", 0)

        by_day = {}
        for dow in range(7):
            d = day_data[dow]
            if d["count"] > 0:
                by_day[day_names[dow]] = {
                    "revenue": round(d["revenue"], 2),
                    "jobs": int(d["count"]),
                }

        best_day = max(by_day.items(), key=lambda x: x[1]["revenue"]) if by_day else None
        peak_hours = sorted(hour_data.items(), key=lambda x: x[1], reverse=True)[:3]

        return {
            "by_day": by_day,
            "best_day": best_day[0] if best_day else None,
            "peak_hours": [
                {"hour": f"{h:02d}:00", "revenue": round(v, 2)}
                for h, v in peak_hours
            ],
        }

    def _analyze_pricing(
        self, sales: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze pricing per service."""
        service_prices: Dict[str, List[float]] = defaultdict(list)
        for t in sales:
            service = t.get("item", "Unknown")
            service_prices[service].append(t.get("amount", 0))

        pricing = {}
        for service, prices in service_prices.items():
            if len(prices) >= 2:
                pricing[service] = {
                    "avg": round(statistics.mean(prices), 2),
                    "min": round(min(prices), 2),
                    "max": round(max(prices), 2),
                    "std_dev": round(statistics.stdev(prices), 2),
                    "count": len(prices),
                }

        return pricing

    # ── Recommendations ─────────────────────────────────────────────

    def get_recommendations(
        self,
        analysis: Dict[str, Any],
        language: str = "en",
    ) -> List[Dict[str, str]]:
        """Generate service-specific recommendations."""
        recs = []

        # Client retention
        clients = analysis.get("client_analysis", {})
        retention = clients.get("retention_rate_pct", 0)
        if retention < 30:
            recs.append({
                "category": "clients",
                "title": "Low client retention" if language == "en" else "Wateja wanarudi kidogo",
                "message": (
                    f"Only {retention:.0f}% of clients return. "
                    "Follow up with past clients via SMS/WhatsApp. "
                    "Offer loyalty discounts for repeat visits."
                    if language == "en" else
                    f"Wateja {retention:.0f}% tu wanarudi. "
                    "Fuata wateja wa zamani kupitia SMS/WhatsApp. "
                    "Toa punguzo la uaminifu kwa ziara za mara kwa mara."
                ),
                "priority": "high",
            })

        # Pricing consistency
        pricing = analysis.get("pricing_analysis", {})
        inconsistent = [
            (s, p) for s, p in pricing.items()
            if p.get("std_dev", 0) > p.get("avg", 0) * 0.3
        ]
        if inconsistent:
            services = ", ".join(s for s, _ in inconsistent[:3])
            recs.append({
                "category": "pricing",
                "title": "Inconsistent pricing" if language == "en" else "Bei si thabiti",
                "message": (
                    f"Prices vary a lot for: {services}. "
                    "Set standard prices — consistency builds trust."
                    if language == "en" else
                    f"Bei zinatofauti sana kwa: {services}. "
                    "Weka bei za kawaida — uthabiti unajenga uaminifu."
                ),
                "priority": "medium",
            })

        # Best day
        patterns = analysis.get("daily_patterns", {})
        best_day = patterns.get("best_day")
        if best_day:
            recs.append({
                "category": "timing",
                "title": "Best day for business" if language == "en" else "Siku bora ya biashara",
                "message": (
                    f"{best_day} is your busiest day. "
                    "Make sure you're available and fully stocked."
                    if language == "en" else
                    f"{best_day} ni siku yako yenye shughuli nyingi. "
                    "Hakikisha unapatikana na una vifaa vyote."
                ),
                "priority": "medium",
            })

        # Service mix
        services = analysis.get("service_analysis", [])
        if services:
            top = services[0]
            if top.get("margin_pct", 0) > 50:
                recs.append({
                    "category": "services",
                    "title": "Promote high-margin service" if language == "en" else "Tangaza huduma yenye faida kubwa",
                    "message": (
                        f"'{top['service']}' has {top['margin_pct']:.0f}% margin. "
                        "Promote this service to more clients."
                        if language == "en" else
                        f"'{top['service']}' ina faida ya {top['margin_pct']:.0f}%. "
                        "Tangaza huduma hii kwa wateja zaidi."
                    ),
                    "priority": "medium",
                })

        # Labour value
        labour = analysis.get("labour_vs_materials", {})
        if labour.get("labour_pct", 0) < 40:
            recs.append({
                "category": "pricing",
                "title": "Your labour is undervalued" if language == "en" else "Kazi yako inathaminiwa kidogo",
                "message": (
                    f"Only {labour['labour_pct']:.0f}% of your revenue is labour. "
                    "Your skills are valuable — consider raising service charges."
                    if language == "en" else
                    f"Kazi ni {labour['labour_pct']:.0f}% tu ya mapato yako. "
                    "Ujuzi wako ni wa thamani — fikiria kupongeza ada za huduma."
                ),
                "priority": "high",
            })

        return recs

    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "period_days": 0,
            "job_count": 0,
            "expense_count": 0,
            "total_revenue": 0,
            "total_expenses": 0,
            "total_profit": 0,
            "avg_job_value": 0,
            "service_analysis": [],
            "client_analysis": {
                "total_clients": 0, "repeat_clients": 0,
                "retention_rate_pct": 0, "avg_visits_per_client": 0,
                "avg_spend_per_client": 0, "top_clients": [],
            },
            "labour_vs_materials": {
                "total_revenue": 0, "material_costs": 0,
                "labour_value": 0, "labour_pct": 0, "material_pct": 0,
            },
            "daily_patterns": {"by_day": {}, "best_day": None, "peak_hours": []},
            "pricing_analysis": {},
        }
