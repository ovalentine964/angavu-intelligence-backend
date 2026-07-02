"""
Microfinance Analyzer — ECO 206: Microfinance

Maps ECO 206 (Microfinance) course unit into executable loan intelligence.

Capabilities:
- Analyze loan terms (interest rate, tenure, repayment structure)
- Predict default risk using logistic regression
- Recommend optimal repayment schedule based on cash flow patterns
- Compute effective cost of borrowing (APR, total cost)

Theoretical Foundations:
- Group lending theory (Stiglitz, 1990; Ghatak, 2000)
- Moral hazard in credit markets
- Adverse selection screening mechanisms
- Repayment capacity analysis from cash flow data

Wired into: LoanManager, AlamaScoreService
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from scipy import stats

from app.skills.base import BaseSkill, SkillResult

logger = structlog.get_logger(__name__)


class MicrofinanceAnalyzer(BaseSkill):
    """
    ECO 206 — Microfinance

    Analyzes loan products, predicts default risk, and recommends
    optimal repayment strategies for informal economy workers.
    """

    def __init__(self):
        super().__init__(
            name="microfinance_analyzer",
            course_unit="ECO 206 — Microfinance",
            description=(
                "Analyzes loan terms, predicts default risk using logistic regression, "
                "and recommends optimal repayment schedules for microfinance borrowers."
            ),
            version="1.0.0",
            agent_bindings=["TransactionProcessor", "IntelligenceGenerator"],
        )

    async def execute(self, action: str, **kwargs) -> SkillResult:
        """Execute a microfinance analysis action."""
        actions = {
            "analyze_loan_terms": self._analyze_loan_terms,
            "predict_default_risk": self._predict_default_risk,
            "recommend_repayment": self._recommend_repayment,
            "compute_effective_cost": self._compute_effective_cost,
        }

        if action not in actions:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=f"Unknown action: {action}. Available: {list(actions.keys())}",
            )

        try:
            data = await actions[action](**kwargs)
            return SkillResult(
                success=True,
                skill_name=self.name,
                data=data,
                confidence=data.get("_confidence", 0.9),
            )
        except Exception as exc:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=str(exc),
            )

    async def _analyze_loan_terms(
        self,
        principal: float,
        interest_rate: float,
        tenure_days: int,
        repayment_frequency: str = "weekly",
        fees: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Analyze loan terms and compute key metrics.

        Args:
            principal: Loan amount (KES)
            interest_rate: Periodic interest rate (decimal, e.g., 0.10 for 10%)
            tenure_days: Loan duration in days
            repayment_frequency: 'daily', 'weekly', 'biweekly', 'monthly'
            fees: Optional fee breakdown (processing, insurance, etc.)

        Returns:
            Dict with APR, total cost, payment schedule, affordability assessment
        """
        fees = fees or {}
        total_fees = sum(fees.values())
        total_interest = principal * interest_rate
        total_due = principal + total_interest + total_fees

        # Compute APR (Annualized Percentage Rate)
        if tenure_days > 0:
            periodic_rate = (total_due - principal) / principal
            periods_per_year = 365 / tenure_days
            apr = (1 + periodic_rate) ** periods_per_year - 1
        else:
            apr = 0.0

        # Payment frequency
        freq_map = {
            "daily": 1,
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
        }
        period_days = freq_map.get(repayment_frequency, 7)
        n_payments = max(1, tenure_days // period_days)
        payment_per_period = total_due / n_payments

        # Affordability heuristic (daily income estimate)
        daily_payment = total_due / max(tenure_days, 1)
        affordability_score = self._assess_affordability(daily_payment, principal)

        return {
            "principal": principal,
            "interest_rate": interest_rate,
            "interest_amount": round(total_interest, 2),
            "fees": fees,
            "total_fees": total_fees,
            "total_due": round(total_due, 2),
            "apr": round(apr * 100, 2),
            "tenure_days": tenure_days,
            "repayment_frequency": repayment_frequency,
            "n_payments": n_payments,
            "payment_per_period": round(payment_per_period, 0),
            "daily_cost": round(daily_payment, 2),
            "affordability": affordability_score,
            "_confidence": 0.95,
        }

    async def _predict_default_risk(
        self,
        repayment_history: List[Dict[str, Any]],
        loan_amount: float,
        daily_income_estimate: float,
        days_active: int,
        purpose: str = "stock",
    ) -> Dict[str, Any]:
        """
        Predict default risk using logistic regression-inspired model.

        Features:
        - Repayment consistency (coefficient of variation of payments)
        - Payment timeliness (days late on average)
        - Loan-to-income ratio
        - Repayment progress (pct repaid)
        - Purpose risk factor

        Returns:
            Dict with risk probability, risk level, feature contributions
        """
        # Extract features
        if repayment_history:
            amounts = [r.get("amount", 0) for r in repayment_history]
            total_repaid = sum(amounts)
            n_payments = len(amounts)
            avg_payment = np.mean(amounts)
            cv_payment = np.std(amounts) / max(avg_payment, 1) if len(amounts) > 1 else 0

            # Timeliness: average days late
            days_late = [r.get("days_late", 0) for r in repayment_history]
            avg_days_late = np.mean(days_late) if days_late else 0
        else:
            total_repaid = 0
            n_payments = 0
            cv_payment = 1.0  # High variability = high risk
            avg_days_late = 0

        repayment_pct = total_repaid / max(loan_amount, 1)
        loan_to_income = loan_amount / max(daily_income_estimate * 30, 1)

        # Logistic regression model
        # β = intercept + features * coefficients
        beta_0 = -1.5  # Intercept (base risk)
        beta = {
            "repayment_consistency": 0.8,   # CV of payments
            "timeliness": 0.3,               # Days late
            "loan_to_income": 1.2,           # Loan/income ratio
            "repayment_progress": -2.0,      # Pct repaid (negative = reduces risk)
            "purpose_risk": 0.5,             # Purpose risk factor
            "activity": -0.01,               # Days active (more = less risk)
        }

        # Purpose risk factors
        purpose_factors = {
            "stock": 0.1,
            "equipment": 0.1,
            "improvement": 0.2,
            "emergency": 0.6,
            "education": 0.3,
            "other": 0.5,
        }
        purpose_risk = purpose_factors.get(purpose, 0.5)

        # Compute linear predictor
        z = (
            beta_0
            + beta["repayment_consistency"] * cv_payment
            + beta["timeliness"] * avg_days_late / 7  # Normalize to weeks
            + beta["loan_to_income"] * loan_to_income
            + beta["repayment_progress"] * repayment_pct
            + beta["purpose_risk"] * purpose_risk
            + beta["activity"] * days_active
        )

        # Sigmoid: P(default) = 1 / (1 + e^(-z))
        risk_prob = 1 / (1 + np.exp(-z))
        risk_prob = float(np.clip(risk_prob, 0.01, 0.99))

        # Risk level
        if risk_prob < 0.15:
            risk_level = "very_low"
        elif risk_prob < 0.30:
            risk_level = "low"
        elif risk_prob < 0.50:
            risk_level = "medium"
        elif risk_prob < 0.70:
            risk_level = "high"
        else:
            risk_level = "critical"

        # Feature contributions (for explainability)
        contributions = {
            "repayment_consistency": round(beta["repayment_consistency"] * cv_payment, 3),
            "timeliness": round(beta["timeliness"] * avg_days_late / 7, 3),
            "loan_to_income": round(beta["loan_to_income"] * loan_to_income, 3),
            "repayment_progress": round(beta["repayment_progress"] * repayment_pct, 3),
            "purpose_risk": round(beta["purpose_risk"] * purpose_risk, 3),
            "activity": round(beta["activity"] * days_active, 3),
        }

        return {
            "risk_probability": round(risk_prob, 4),
            "risk_level": risk_level,
            "features": {
                "repayment_consistency_cv": round(cv_payment, 4),
                "avg_days_late": round(avg_days_late, 2),
                "loan_to_income_ratio": round(loan_to_income, 4),
                "repayment_pct": round(repayment_pct * 100, 1),
                "n_payments": n_payments,
                "days_active": days_active,
                "purpose": purpose,
            },
            "feature_contributions": contributions,
            "recommendation": self._risk_recommendation(risk_level, risk_prob),
            "_confidence": max(0.5, 0.9 - cv_payment * 0.3),
        }

    async def _recommend_repayment(
        self,
        total_due: float,
        amount_repaid: float,
        daily_income_avg: float,
        income_volatility: float = 0.3,
        days_to_due: int = 30,
        current_streak: int = 0,
    ) -> Dict[str, Any]:
        """
        Recommend optimal repayment strategy based on cash flow patterns.

        Considers:
        - Income stability (volatility)
        - Time remaining
        - Current repayment streak (behavioral momentum)
        - Minimum viable payment to maintain streak

        Returns:
            Dict with recommended strategy, amounts, and behavioral nudges
        """
        remaining = max(0, total_due - amount_repaid)
        if remaining <= 0:
            return {
                "status": "completed",
                "message": "Loan fully repaid!",
                "_confidence": 1.0,
            }

        days_to_due = max(1, days_to_due)
        daily_capacity = daily_income_avg * 0.3  # 30% of income for repayment
        ideal_daily = remaining / days_to_due

        # Adjust for volatility
        if income_volatility > 0.5:
            # High volatility: pay more on good days, less on bad days
            strategy = "flexible"
            good_day_amount = round(ideal_daily * 1.5, 0)
            bad_day_amount = round(ideal_daily * 0.3, 0)
            recommended_daily = round(ideal_daily, 0)
        elif income_volatility > 0.2:
            # Moderate: semi-structured
            strategy = "semi_structured"
            good_day_amount = round(ideal_daily * 1.2, 0)
            bad_day_amount = round(ideal_daily * 0.5, 0)
            recommended_daily = round(ideal_daily, 0)
        else:
            # Low volatility: fixed daily
            strategy = "fixed"
            good_day_amount = round(ideal_daily * 1.0, 0)
            bad_day_amount = round(ideal_daily * 0.8, 0)
            recommended_daily = round(ideal_daily, 0)

        # Streak maintenance: minimum payment to keep streak alive
        min_streak_payment = max(10, round(remaining * 0.01, 0))

        # Weekly target
        weekly_target = round(recommended_daily * 7, 0)

        return {
            "remaining": round(remaining, 2),
            "days_to_due": days_to_due,
            "strategy": strategy,
            "recommended_daily": recommended_daily,
            "good_day_amount": good_day_amount,
            "bad_day_amount": bad_day_amount,
            "weekly_target": weekly_target,
            "min_streak_payment": min_streak_payment,
            "current_streak": current_streak,
            "completion_date_estimate": str(date.today() + timedelta(days=days_to_due)),
            "nudges": self._generate_nudges(
                remaining, recommended_daily, current_streak, days_to_due
            ),
            "_confidence": 0.85,
        }

    async def _compute_effective_cost(
        self,
        principal: float,
        interest_amount: float,
        fees: Dict[str, float],
        tenure_days: int,
        repayment_frequency: str = "weekly",
    ) -> Dict[str, Any]:
        """
        Compute the effective cost of borrowing.

        Returns APR, total cost, and comparison with alternatives.
        """
        total_fees = sum(fees.values())
        total_cost = interest_amount + total_fees
        effective_rate = total_cost / max(principal, 1)

        # APR calculation
        if tenure_days > 0:
            apr = effective_rate * (365 / tenure_days)
        else:
            apr = 0.0

        # Cost per KES borrowed
        cost_per_kes = total_cost / max(principal, 1)

        return {
            "principal": principal,
            "interest_amount": interest_amount,
            "fees": fees,
            "total_fees": total_fees,
            "total_cost": total_cost,
            "effective_rate_pct": round(effective_rate * 100, 2),
            "apr_pct": round(apr * 100, 2),
            "cost_per_kes_borrowed": round(cost_per_kes, 4),
            "tenure_days": tenure_days,
            "assessment": (
                "excellent" if apr < 0.20
                else "good" if apr < 0.40
                else "moderate" if apr < 0.80
                else "expensive" if apr < 1.50
                else "very_expensive"
            ),
            "_confidence": 0.95,
        }

    # ── Helpers ─────────────────────────────────────────────────────

    def _assess_affordability(self, daily_payment: float, principal: float) -> Dict[str, Any]:
        """Assess loan affordability based on estimated daily payment burden."""
        # Assume minimum daily income of KES 300 for informal workers
        min_daily_income = 300
        payment_ratio = daily_payment / min_daily_income

        if payment_ratio < 0.15:
            level = "very_affordable"
            message = "Payment is well within typical income range"
        elif payment_ratio < 0.30:
            level = "affordable"
            message = "Payment is manageable for most workers"
        elif payment_ratio < 0.50:
            level = "stretched"
            message = "Payment requires disciplined budgeting"
        else:
            level = "burdensome"
            message = "Payment may be difficult to sustain"

        return {
            "level": level,
            "daily_payment": round(daily_payment, 0),
            "payment_to_income_ratio": round(payment_ratio, 3),
            "message": message,
        }

    def _risk_recommendation(self, risk_level: str, risk_prob: float) -> str:
        """Generate risk-based recommendation."""
        recommendations = {
            "very_low": "Approve. Strong repayment history and low risk indicators.",
            "low": "Approve with standard terms. Monitor repayment progress.",
            "medium": "Approve with caution. Consider smaller amount or shorter tenure.",
            "high": "Conditional approval. Require collateral or group guarantee.",
            "critical": "Decline or restructure. Significant default risk detected.",
        }
        return recommendations.get(risk_level, "Review manually.")

    def _generate_nudges(
        self,
        remaining: float,
        daily_target: float,
        streak: int,
        days_to_due: int,
    ) -> List[Dict[str, str]]:
        """Generate behavioral nudges for repayment."""
        nudges = []

        if streak >= 7:
            nudges.append({
                "type": "streak_milestone",
                "sw": f"Siku {streak} mfululizo! Usivunje rekodi!",
                "en": f"{streak} days in a row! Keep the streak alive!",
            })

        if remaining < daily_target * 5:
            nudges.append({
                "type": "almost_done",
                "sw": f"KSh {remaining:,.0f} tu! Unaweza kumaliza wiki hii!",
                "en": f"Only KSh {remaining:,.0f} left! You can finish this week!",
            })

        if days_to_due <= 7 and days_to_due > 0:
            nudges.append({
                "type": "deadline_approaching",
                "sw": f"Siku {days_to_due} zimebaki! Lipa KSh {daily_target:,.0f} kwa siku.",
                "en": f"{days_to_due} days left! Pay KSh {daily_target:,.0f} per day.",
            })

        return nudges
