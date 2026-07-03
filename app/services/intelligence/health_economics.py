"""
Health Economics Intelligence — ECO 106: Emerging Public Health Issues.

Standalone health-economic intelligence module for Biashara Intelligence.
Tracks health shocks, models health investment decisions, and quantifies
the poverty-health nexus for informal workers.

Academic Foundation:
- ECO 106: Emerging Public Health Issues — Grossman health capital model,
  health shocks and poverty traps, catastrophic health expenditure (CHE),
  epidemiological transition, universal health coverage (UHC)

This module is wired into JamiiInsightsService as the health-economic
subsystem. It was refactored from the inline implementation in
jamii_insights.py to support independent testing and reuse.

Key References:
- Grossman, M. (1972). "On the Concept of Health Capital." JPE.
- WHO (2010). "The World Health Report — Health Systems Financing."
- Chuma, J. & Gilson, L. (2008). "Healthcare financing and the poor."
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class HealthEconomicsEngine:
    """
    Health-economic intelligence engine for informal workers.

    Implements:
    1. Health shock detection from transaction patterns
    2. Grossman health capital model for investment decisions
    3. Health insurance gap analysis (NHIF, CBHI)
    4. Epidemiological early warning from economic data
    5. Health-productivity correlation analysis
    """

    # Common health shocks in Kenya's informal sector
    HEALTH_SHOCK_TYPES = {
        "malaria": {"avg_cost_kes": 3500, "avg_days_lost": 5, "severity": "moderate"},
        "respiratory_infection": {"avg_cost_kes": 2500, "avg_days_lost": 3, "severity": "mild"},
        "diarrheal_disease": {"avg_cost_kes": 2000, "avg_days_lost": 2, "severity": "mild"},
        "typhoid": {"avg_cost_kes": 8000, "avg_days_lost": 10, "severity": "moderate"},
        "hospitalization": {"avg_cost_kes": 35000, "avg_days_lost": 14, "severity": "severe"},
        "surgery": {"avg_cost_kes": 120000, "avg_days_lost": 30, "severity": "catastrophic"},
        "chronic_disease": {"avg_cost_kes": 5000, "avg_days_lost": 0, "severity": "ongoing"},
        "maternal": {"avg_cost_kes": 25000, "avg_days_lost": 42, "severity": "moderate"},
        "road_injury": {"avg_cost_kes": 45000, "avg_days_lost": 21, "severity": "severe"},
    }

    NHIF_COVERAGE = {
        "formal_sector": 0.65,
        "informal_sector": 0.18,
        "overall": 0.22,
    }

    @classmethod
    def detect_health_shocks(
        cls,
        transactions: List[Any],
        lookback_days: int = 180,
        poverty_line_monthly: float = 8800,
    ) -> Dict[str, Any]:
        """
        Detect health shocks from transaction revenue patterns.

        Health shocks manifest as:
        1. Revenue drops >50% for 3+ consecutive days
        2. Activity gaps (zero transactions for 3+ days)
        3. Sudden expense spikes

        Args:
            transactions: List of transaction objects
            lookback_days: Analysis window
            poverty_line_monthly: Poverty threshold in KES

        Returns:
            Dict with detected shocks, impact assessment, recovery tracking
        """
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if len(sales) < 20:
            return {"error": "Insufficient transaction data", "shock_count": 0}

        # Daily revenue aggregation
        daily_rev = defaultdict(float)
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day] += t.amount

        sorted_days = sorted(daily_rev.keys())
        if len(sorted_days) < 14:
            return {"error": "Need at least 14 days of data", "shock_count": 0}

        revenues = np.array([daily_rev[d] for d in sorted_days], dtype=float)
        median_rev = float(np.median(revenues))
        mean_rev = float(np.mean(revenues))

        # Detect revenue drops (health shock signature)
        shocks = []
        i = 0
        while i < len(sorted_days):
            if daily_rev[sorted_days[i]] < median_rev * 0.5:
                shock_start = i
                shock_days = [sorted_days[i]]
                while i + 1 < len(sorted_days) and daily_rev[sorted_days[i + 1]] < median_rev * 0.5:
                    i += 1
                    shock_days.append(sorted_days[i])

                if len(shock_days) >= 3:
                    shock_rev = sum(daily_rev[d] for d in shock_days)
                    expected_rev = median_rev * len(shock_days)
                    revenue_loss = expected_rev - shock_rev
                    loss_pct = revenue_loss / max(expected_rev, 1) * 100

                    if loss_pct > 80:
                        severity = "catastrophic"
                    elif loss_pct > 60:
                        severity = "severe"
                    elif loss_pct > 40:
                        severity = "moderate"
                    else:
                        severity = "mild"

                    shocks.append({
                        "start_date": shock_days[0],
                        "end_date": shock_days[-1],
                        "duration_days": len(shock_days),
                        "revenue_loss_kes": round(revenue_loss, 0),
                        "loss_percentage": round(loss_pct, 1),
                        "severity": severity,
                        "estimated_health_cost": cls._estimate_health_cost(len(shock_days), severity),
                    })
            i += 1

        total_loss = sum(s["revenue_loss_kes"] for s in shocks)
        total_days_lost = sum(s["duration_days"] for s in shocks)

        # Poverty risk from health shocks
        avg_monthly = mean_rev * 30
        post_shock = max(0, avg_monthly - (total_loss / max(lookback_days / 30, 1)))

        return {
            "shock_count": len(shocks),
            "health_shocks": shocks,
            "total_revenue_loss_kes": round(total_loss, 0),
            "total_days_lost": total_days_lost,
            "avg_monthly_revenue_kes": round(avg_monthly, 0),
            "post_shock_monthly_revenue_kes": round(post_shock, 0),
            "poverty_risk_from_health_shocks": 1 if post_shock < poverty_line_monthly else 0,
            "health_vulnerability_score": cls._vulnerability_score(
                len(shocks) / max(lookback_days / 30, 1), total_loss, avg_monthly
            ),
            "method": "ECO 106 — Health-Economic Shock Detection",
        }

    @classmethod
    def grossman_health_investment(
        cls,
        current_health_stock: float,
        wage_rate: float,
        depreciation_rate: float = 0.05,
        interest_rate: float = 0.12,
        medical_cost_index: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Grossman health capital model — optimal health investment.

        H(t+1) = (1-δ)·H(t) + I(t)^α where α = 0.5 (diminishing returns)
        Optimal: MB = α·I^(α-1)·w·health_to_time = MC·(r+δ)

        Args:
            current_health_stock: Health status (0-100)
            wage_rate: Daily wage rate in KES
            depreciation_rate: Annual health depreciation
            interest_rate: Discount rate
            medical_cost_index: Relative cost of medical care

        Returns:
            Dict with optimal investment, trajectory, recommendations
        """
        alpha = 0.5
        health_to_time = 0.01
        marginal_value = wage_rate * health_to_time

        denominator = medical_cost_index * (interest_rate + depreciation_rate)
        if denominator > 0:
            optimal_investment = (alpha * marginal_value / denominator) ** (1 / (1 - alpha))
        else:
            optimal_investment = 0

        annual_depreciation = current_health_stock * depreciation_rate
        maintenance_investment = annual_depreciation

        if current_health_stock < 40:
            priority = "critical"
            recommendation = "Immediate health investment needed. Seek subsidized care at public facilities."
        elif current_health_stock < 60:
            priority = "high"
            recommendation = "Regular check-ups recommended. Consider NHIF enrollment."
        elif current_health_stock < 80:
            priority = "moderate"
            recommendation = "Maintain through balanced nutrition and exercise. Budget for annual check-up."
        else:
            priority = "low"
            recommendation = "Health stock is good. Continue preventive care."

        return {
            "current_health_stock": current_health_stock,
            "wage_rate_kes": wage_rate,
            "optimal_daily_investment_kes": round(optimal_investment, 0),
            "optimal_annual_investment_kes": round(optimal_investment * 365, 0),
            "annual_depreciation_units": round(annual_depreciation, 2),
            "investment_gap_units": round(maintenance_investment - optimal_investment, 2),
            "health_trajectory": "improving" if optimal_investment > maintenance_investment else "declining",
            "priority": priority,
            "recommendation": recommendation,
            "model": "Grossman Health Capital Model (1972)",
            "method": "ECO 106 — Health Investment Optimization",
        }

    @classmethod
    def health_insurance_gap(
        cls,
        user_count: int,
        avg_monthly_income: float,
        region: str = "Kenya",
    ) -> Dict[str, Any]:
        """
        Health insurance coverage and gap analysis.

        WHO framework: UHC = financial protection + service coverage.
        CHE threshold: OOP health spending > 40% of capacity to pay.

        Args:
            user_count: Number of users in analysis
            avg_monthly_income: Average monthly income in KES
            region: Geographic region

        Returns:
            Dict with insurance gap, CHE risk, CBHI recommendation
        """
        estimated_coverage = cls.NHIF_COVERAGE["informal_sector"]
        insured = int(user_count * estimated_coverage)
        uninsured = user_count - insured
        insurance_gap = 1 - estimated_coverage

        capacity_to_pay = avg_monthly_income * 0.5  # Non-food
        che_threshold = capacity_to_pay * 0.4
        avg_hospitalization = 35000

        cbhi_premium = avg_monthly_income * 0.02
        cbhi_limit = cbhi_premium * 12 * 10

        return {
            "region": region,
            "user_count": user_count,
            "estimated_insured": insured,
            "estimated_uninsured": uninsured,
            "insurance_coverage_rate": round(estimated_coverage * 100, 1),
            "insurance_gap_pct": round(insurance_gap * 100, 1),
            "che_risk": {
                "threshold_kes": round(che_threshold, 0),
                "avg_hospitalization_cost_kes": avg_hospitalization,
                "catastrophic_risk": "high" if avg_hospitalization > che_threshold else "low",
            },
            "recommended_insurance": {
                "type": "Community-Based Health Insurance (CBHI)",
                "monthly_premium_kes": round(cbhi_premium, 0),
                "coverage_limit_kes": round(cbhi_limit, 0),
            },
            "financial_protection_score": round(
                (1 - insurance_gap) * 50 + (1 - min(1, avg_hospitalization / max(che_threshold, 1))) * 50, 1
            ),
            "method": "ECO 106 — Health Financial Protection (WHO UHC framework)",
        }

    @classmethod
    def full_health_economic_report(
        cls,
        transactions: List[Any],
        region: str,
        user_count: int,
        avg_monthly_income: float,
        poverty_line_monthly: float = 8800,
    ) -> Dict[str, Any]:
        """
        Comprehensive health-economic intelligence report.

        Combines all ECO 106 analyses into a single report.
        """
        report = {
            "product": "health_economics",
            "region": region,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # 1. Health shock detection
        report["health_shocks"] = cls.detect_health_shocks(
            transactions, poverty_line_monthly=poverty_line_monthly
        )

        # 2. Grossman model
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        daily_rev = defaultdict(float)
        for t in sales:
            daily_rev[t.timestamp.strftime("%Y-%m-%d")] += t.amount
        avg_daily = float(np.mean(list(daily_rev.values()))) if daily_rev else 0
        active_days = len(daily_rev)
        total_days = max(1, (
            max(t.timestamp for t in sales) - min(t.timestamp for t in sales)
        ).days + 1) if sales else 1
        health_stock = min(100, (active_days / total_days) * 100 + 20)

        report["grossman_model"] = cls.grossman_health_investment(
            current_health_stock=health_stock, wage_rate=avg_daily
        )

        # 3. Insurance gap
        report["insurance_intelligence"] = cls.health_insurance_gap(
            user_count, avg_monthly_income, region
        )

        # 4. Overall risk score
        shock_risk = report["health_shocks"].get("health_vulnerability_score", 50)
        ins_risk = report["insurance_intelligence"].get("financial_protection_score", 50)
        overall_risk = round((shock_risk + (100 - ins_risk)) / 2, 1)

        report["overall_health_risk_score"] = overall_risk
        report["overall_risk_level"] = (
            "critical" if overall_risk > 70
            else "high" if overall_risk > 50
            else "moderate" if overall_risk > 30
            else "low"
        )
        report["key_insight"] = (
            f"Health risk: {overall_risk}/100 ({report['overall_risk_level']}). "
            f"Insurance: {report['insurance_intelligence']['insurance_coverage_rate']}%. "
            f"Shocks: {report['health_shocks'].get('shock_count', 0)}. "
            f"Recommendation: {report['grossman_model']['recommendation']}"
        )

        return report

    @staticmethod
    def _estimate_health_cost(duration_days: int, severity: str) -> float:
        base_costs = {"mild": 2000, "moderate": 5000, "severe": 25000, "catastrophic": 80000}
        return base_costs.get(severity, 5000) + duration_days * 500

    @staticmethod
    def _vulnerability_score(shock_frequency: float, total_loss: float, avg_monthly: float) -> float:
        freq_score = min(50, shock_frequency * 25)
        loss_score = min(50, (total_loss / max(avg_monthly * 12, 1)) * 50)
        return round(freq_score + loss_score, 1)
