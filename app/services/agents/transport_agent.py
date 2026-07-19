"""
TransportAgent — Domain intelligence for boda boda, matatu, tuk-tuk, taxi drivers.

Capabilities:
    - Trip tracking and fare analysis
    - Fuel cost analysis (KSh/km, km/litre)
    - Earnings per hour calculation
    - Peak hours analysis (when are fares highest?)
    - Route profitability analysis
    - Maintenance schedule (based on distance/time)
    - Daily/weekly earnings reports
    - Revenue pattern detection

Tier: 2 (Domain) — activated when worker type is TRANSPORT
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TransportAgent:
    """
    Specialized intelligence for transport workers.

    Analyzes trip data to provide fuel efficiency, earnings optimization,
    peak hours, and route profitability insights.
    """

    name = "TransportAgent"
    role = "Transport business intelligence specialist"
    tier = 2
    worker_types = ["boda_boda", "matatu", "tuk_tuk", "taxi"]

    def __init__(self):
        self._logger = logger.bind(agent=self.name)

    # ── Trip Analysis ───────────────────────────────────────────────

    def analyze_trips(
        self,
        transactions: list[dict[str, Any]],
        period_days: int = 30,
    ) -> dict[str, Any]:
        """
        Analyze trip transactions to extract transport-specific metrics.

        Args:
            transactions: List of transaction dicts with at minimum:
                - amount (float): fare earned
                - timestamp (str/datetime): when the trip happened
                - item (str, optional): route description
                - quantity (float, optional): distance in km
                - profit (float, optional): net profit after fuel
            period_days: Analysis window in days

        Returns:
            Dict with transport-specific analytics
        """
        if not transactions:
            return self._empty_analysis()

        # Filter to sales (trips are revenue)
        trips = [
            t for t in transactions
            if t.get("transaction_type") == "SALE"
        ]

        if not trips:
            return self._empty_analysis()

        fares = [t["amount"] for t in trips if t.get("amount", 0) > 0]
        profits = [t.get("profit", 0) or 0 for t in trips]
        distances = [t.get("quantity", 0) or 0 for t in trips]

        # Earnings summary
        total_earnings = sum(fares)
        total_profit = sum(profits)
        trip_count = len(trips)
        avg_fare = total_earnings / trip_count if trip_count else 0

        # Fuel efficiency
        fuel_costs = [f - p for f, p in zip(fares, profits) if f > 0]
        total_fuel = sum(fuel_costs)
        fuel_pct = (total_fuel / total_earnings * 100) if total_earnings > 0 else 0

        # Per-km metrics
        total_km = sum(d for d in distances if d > 0)
        cost_per_km = total_fuel / total_km if total_km > 0 else None
        earnings_per_km = total_earnings / total_km if total_km > 0 else None

        # Hourly earnings (estimate from timestamps)
        hourly_earnings = self._calc_hourly_earnings(trips)
        peak_hours = self._find_peak_hours(trips)

        # Daily earnings
        daily_earnings = self._calc_daily_earnings(trips)

        # Route analysis
        route_analysis = self._analyze_routes(trips)

        return {
            "period_days": period_days,
            "trip_count": trip_count,
            "total_earnings": round(total_earnings, 2),
            "total_profit": round(total_profit, 2),
            "avg_fare": round(avg_fare, 2),
            "fuel_cost_total": round(total_fuel, 2),
            "fuel_cost_pct": round(fuel_pct, 1),
            "total_km": round(total_km, 1),
            "cost_per_km": round(cost_per_km, 2) if cost_per_km else None,
            "earnings_per_km": round(earnings_per_km, 2) if earnings_per_km else None,
            "hourly_earnings": hourly_earnings,
            "peak_hours": peak_hours,
            "daily_earnings": daily_earnings,
            "route_analysis": route_analysis,
        }

    def _calc_hourly_earnings(
        self, trips: list[dict[str, Any]]
    ) -> dict[str, float]:
        """Calculate average earnings per hour of the day."""
        hour_totals: dict[int, list[float]] = defaultdict(list)
        for trip in trips:
            ts = trip.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                hour_totals[ts.hour].append(trip.get("amount", 0))

        return {
            f"{h:02d}:00": round(statistics.mean(amounts), 2)
            for h, amounts in sorted(hour_totals.items())
            if amounts
        }

    def _find_peak_hours(
        self, trips: list[dict[str, Any]], top_n: int = 3
    ) -> list[dict[str, Any]]:
        """Find the top N most profitable hours."""
        hour_data: dict[int, dict[str, float]] = defaultdict(
            lambda: {"total": 0.0, "count": 0}
        )
        for trip in trips:
            ts = trip.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                h = ts.hour
                hour_data[h]["total"] += trip.get("amount", 0)
                hour_data[h]["count"] += 1

        ranked = sorted(
            hour_data.items(),
            key=lambda x: x[1]["total"],
            reverse=True,
        )
        return [
            {
                "hour": f"{h:02d}:00",
                "total_earnings": round(d["total"], 2),
                "trip_count": int(d["count"]),
                "avg_fare": round(d["total"] / d["count"], 2) if d["count"] else 0,
            }
            for h, d in ranked[:top_n]
        ]

    def _calc_daily_earnings(
        self, trips: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Calculate daily earnings statistics."""
        day_totals: dict[str, float] = defaultdict(float)
        for trip in trips:
            ts = trip.get("timestamp")
            if ts:
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                day_key = ts.strftime("%Y-%m-%d")
                day_totals[day_key] += trip.get("amount", 0)

        if not day_totals:
            return {"avg": 0, "best": 0, "worst": 0, "days": 0}

        values = list(day_totals.values())
        return {
            "avg": round(statistics.mean(values), 2),
            "best": round(max(values), 2),
            "worst": round(min(values), 2),
            "std_dev": round(statistics.stdev(values), 2) if len(values) > 1 else 0,
            "days": len(values),
        }

    def _analyze_routes(
        self, trips: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Analyze profitability by route."""
        route_data: dict[str, dict[str, float]] = defaultdict(
            lambda: {"total": 0.0, "count": 0, "profit": 0.0}
        )
        for trip in trips:
            route = trip.get("item", "Unknown Route")
            route_data[route]["total"] += trip.get("amount", 0)
            route_data[route]["count"] += 1
            route_data[route]["profit"] += trip.get("profit", 0) or 0

        ranked = sorted(
            route_data.items(),
            key=lambda x: x[1]["total"],
            reverse=True,
        )
        return [
            {
                "route": route,
                "total_earnings": round(d["total"], 2),
                "trip_count": int(d["count"]),
                "avg_fare": round(d["total"] / d["count"], 2) if d["count"] else 0,
                "total_profit": round(d["profit"], 2),
            }
            for route, d in ranked[:10]
        ]

    # ── Recommendations ─────────────────────────────────────────────

    def get_recommendations(
        self,
        analysis: dict[str, Any],
        language: str = "en",
    ) -> list[dict[str, str]]:
        """
        Generate transport-specific recommendations based on analysis.

        Returns list of {category, title, message, priority}.
        """
        recs = []

        # Fuel efficiency
        fuel_pct = analysis.get("fuel_cost_pct", 0)
        if fuel_pct > 40:
            recs.append({
                "category": "fuel",
                "title": "Fuel costs too high" if language == "en" else "Gharama za mafuta ni kubwa sana",
                "message": (
                    f"Fuel is {fuel_pct:.0f}% of your earnings. Target below 35%. "
                    "Consider grouping trips by area to reduce dead mileage."
                    if language == "en" else
                    f"Mafuta ni {fuel_pct:.0f}% ya mapato yako. Lenga chini ya 35%. "
                    "Fikiria kugawanya safari kwa eneo kupunguza kilometa tupu."
                ),
                "priority": "high",
            })

        # Peak hours
        peak_hours = analysis.get("peak_hours", [])
        if peak_hours:
            best_hours = ", ".join(h["hour"] for h in peak_hours[:2])
            recs.append({
                "category": "timing",
                "title": "Best hours for earnings" if language == "en" else "Masaa bora ya mapato",
                "message": (
                    f"Your best earning hours are {best_hours}. "
                    "Focus your work during these peak times."
                    if language == "en" else
                    f"Masaa yako bora ya mapato ni {best_hours}. "
                    "Zingatia kazi yako wakati huu wa kilele."
                ),
                "priority": "medium",
            })

        # Daily target
        daily = analysis.get("daily_earnings", {})
        avg_daily = daily.get("avg", 0)
        if avg_daily > 0:
            target = round(avg_daily * 1.1, 0)  # 10% improvement
            recs.append({
                "category": "target",
                "title": "Daily earnings target" if language == "en" else "Lengo la mapato ya kila siku",
                "message": (
                    f"Your average is KSh {avg_daily:,.0f}/day. "
                    f"Try targeting KSh {target:,.0f} — just 10% more."
                    if language == "en" else
                    f"Wako wa kawaida ni KSh {avg_daily:,.0f}/siku. "
                    f"Jaribu kulenga KSh {target:,.0f} — ongezeko la 10% tu."
                ),
                "priority": "medium",
            })

        # Route optimization
        routes = analysis.get("route_analysis", [])
        if len(routes) >= 2:
            best_route = routes[0]
            worst_route = routes[-1]
            if best_route["avg_fare"] > worst_route["avg_fare"] * 1.5:
                recs.append({
                    "category": "route",
                    "title": "Focus on profitable routes" if language == "en" else "Zingatia njia zenye faida",
                    "message": (
                        f"'{best_route['route']}' pays KSh {best_route['avg_fare']:,.0f} avg. "
                        f"'{worst_route['route']}' pays KSh {worst_route['avg_fare']:,.0f}. "
                        "Shift more time to higher-paying routes."
                        if language == "en" else
                        f"'{best_route['route']}' inalipa KSh {best_route['avg_fare']:,.0f} wastani. "
                        f"'{worst_route['route']}' inalipa KSh {worst_route['avg_fare']:,.0f}. "
                        "Hamisha muda zaidi kwa njia zenye malipo bora."
                    ),
                    "priority": "high",
                })

        # Earnings trend
        if avg_daily > 0 and daily.get("std_dev", 0) > avg_daily * 0.5:
            recs.append({
                "category": "stability",
                "title": "Earnings are inconsistent" if language == "en" else "Mapato si thabiti",
                "message": (
                    "Your daily earnings vary a lot. Try to maintain consistent "
                    "working hours and routes for more predictable income."
                    if language == "en" else
                    "Mapato yako ya kila siku yanatofauti sana. Jaribu kudumisha "
                    "masaa na njia za kazi thabiti kwa mapato yanayoweza kutabiriwa."
                ),
                "priority": "medium",
            })

        return recs

    def _empty_analysis(self) -> dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "period_days": 0,
            "trip_count": 0,
            "total_earnings": 0,
            "total_profit": 0,
            "avg_fare": 0,
            "fuel_cost_total": 0,
            "fuel_cost_pct": 0,
            "total_km": 0,
            "cost_per_km": None,
            "earnings_per_km": None,
            "hourly_earnings": {},
            "peak_hours": [],
            "daily_earnings": {"avg": 0, "best": 0, "worst": 0, "days": 0},
            "route_analysis": [],
        }
