"""
Business Health Score Calculator — Msaidizi / Angavu Intelligence

Calculates three key scores for informal business owners:
1. Business Health Score (0-100) — overall business wellbeing
2. Credit Readiness Score (0-100) — readiness for bank loans
3. Investment Readiness Score (0-100) — readiness to expand/invest

These scores translate complex financial data into simple numbers
that a dukawallah or mama mboga can understand at a glance.

Scoring is calibrated against real data from Kenya's informal economy:
- Average food vendor margin: 25-35%
- Average daily transactions: 8-15
- Average monthly revenue: KSh 30,000-80,000
- Typical savings rate: 5-15%
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .whatsapp_charts import (
    BLOCK_FULL,
    BLOCK_LIGHT,
    BLOCK_SOLID,
    CHECK,
    CROSS_MARK,
    format_currency,
)

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class BusinessMetrics:
    """Input metrics for health score calculation.

    All monetary values in KSh (Kenya Shillings).
    """
    # Revenue & Profit
    total_revenue: float = 0.0          # Total sales in period
    total_expenses: float = 0.0         # Total purchases/expenses in period
    total_profit: float = 0.0           # Net profit (revenue - expenses)

    # Transaction Data
    total_transactions: int = 0         # Number of sales transactions
    days_active: int = 30               # Number of days with at least 1 transaction
    days_in_period: int = 30            # Total days in measurement period

    # Growth
    current_period_revenue: float = 0.0
    previous_period_revenue: float = 0.0
    revenue_growth_pct: float = 0.0     # Month-over-month growth

    # Consistency
    daily_revenues: list[float] = field(default_factory=list)  # Revenue per day
    coefficient_of_variation: float = 0.0  # StdDev / Mean of daily revenue

    # Product Diversity
    unique_products: int = 0            # Number of distinct products sold
    top_product_concentration: float = 0.0  # % of revenue from top product

    # Savings & Cash
    total_savings: float = 0.0          # Accumulated savings
    savings_rate: float = 0.0           # Savings / Revenue
    cash_on_hand: float = 0.0           # Current cash available
    months_of_data: int = 0             # How many months of transaction history

    # Expenses
    expense_categories: dict[str, float] = field(default_factory=dict)

    # Inventory
    stockout_days: int = 0              # Days where key items were out of stock
    inventory_turnover: float = 0.0     # How quickly inventory sells

    # Business Profile
    business_age_months: int = 0        # How old the business is
    business_type: str = "food_vendor"  # Type of business
    location: str = ""                  # Market/location name


@dataclass
class HealthScoreResult:
    """Result of business health score calculation."""
    overall_score: float                # 0-100
    components: dict[str, float]        # Component scores
    strengths: list[str]                # What's going well
    weaknesses: list[str]               # What needs improvement
    recommendations: list[str]          # Actionable advice
    grade: str                          # A/B/C/D/F
    emoji: str                          # Visual indicator
    summary_sw: str                     # Swahili summary
    summary_en: str                     # English summary


@dataclass
class CreditReadinessResult:
    """Result of credit readiness assessment."""
    score: float                        # 0-100
    ready: bool                         # True if ready for credit
    estimated_loan_range: tuple[float, float]  # Min/max recommended loan
    requirements_met: dict[str, bool]   # Checklist of requirements
    missing_requirements: list[str]     # What's still needed
    recommendation_sw: str              # Swahili recommendation
    recommendation_en: str              # English recommendation


@dataclass
class InvestmentReadinessResult:
    """Result of investment readiness assessment."""
    score: float                        # 0-100
    ready: bool                         # True if ready to invest
    recommended_investment_types: list[str]  # What kind of investment
    risk_level: str                     # Low/Medium/High
    recommendation_sw: str
    recommendation_en: str


# ---------------------------------------------------------------------------
# Business Health Scorer
# ---------------------------------------------------------------------------

class BusinessHealthScorer:
    """Calculates business health, credit readiness, and investment readiness.

    Scoring methodology is calibrated for Kenya's informal economy:

    Component Weights:
        - Growth (25%): Is the business growing?
        - Profitability (25%): Are margins healthy?
        - Consistency (20%): Is revenue stable?
        - Diversity (15%): Are products diversified?
        - Savings (15%): Is the owner saving?

    Benchmarks (food vendors, Gikomba/Nairobi):
        - Healthy margin: 25-40%
        - Good growth: >5% month-over-month
        - Good consistency: CV < 0.5
        - Good diversity: 3+ products, top product <60%
        - Good savings rate: >10%
    """

    # Component weights for overall health score
    WEIGHTS = {
        "growth": 0.25,
        "profitability": 0.25,
        "consistency": 0.20,
        "diversity": 0.15,
        "savings": 0.15,
    }

    # Credit readiness thresholds
    CREDIT_MIN_MONTHS = 6
    CREDIT_MIN_MARGIN = 0.15
    CREDIT_MIN_CONSISTENCY = 0.6  # 1 - CV, so higher = more consistent
    CREDIT_MIN_TRANSACTIONS_PER_DAY = 3

    # Investment readiness thresholds
    INVEST_MIN_SAVINGS_RATE = 0.10
    INVEST_MIN_HEALTH_SCORE = 65
    INVEST_MIN_MARGIN = 0.20

    # -------------------------------------------------------------------
    # Main Health Score
    # -------------------------------------------------------------------

    def calculate_health_score(self, metrics: BusinessMetrics) -> HealthScoreResult:
        """Calculate overall business health score.

        Args:
            metrics: Business metrics data.

        Returns:
            HealthScoreResult with score, components, strengths, weaknesses, and advice.
        """
        components = {}

        # 1. Growth Score (0-100)
        components["growth"] = self._score_growth(metrics)

        # 2. Profitability Score (0-100)
        components["profitability"] = self._score_profitability(metrics)

        # 3. Consistency Score (0-100)
        components["consistency"] = self._score_consistency(metrics)

        # 4. Diversity Score (0-100)
        components["diversity"] = self._score_diversity(metrics)

        # 5. Savings Score (0-100)
        components["savings"] = self._score_savings(metrics)

        # Weighted average
        overall = sum(
            components[k] * self.WEIGHTS[k] for k in self.WEIGHTS
        )
        overall = min(max(overall, 0), 100)

        # Determine grade
        grade, emoji = self._grade(overall)

        # Identify strengths and weaknesses
        strengths, weaknesses = self._analyze_components(components)

        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, components)

        # Generate summaries
        summary_sw = self._summary_sw(overall, grade, strengths, weaknesses)
        summary_en = self._summary_en(overall, grade, strengths, weaknesses)

        return HealthScoreResult(
            overall_score=round(overall, 1),
            components=components,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            grade=grade,
            emoji=emoji,
            summary_sw=summary_sw,
            summary_en=summary_en,
        )

    def _score_growth(self, m: BusinessMetrics) -> float:
        """Score business growth (0-100).

        Positive growth is good. Very high growth (>50%) gets slight discount
        as it may be unsustainable or from a single large order.

        Benchmarks:
            >20% MoM growth  → 90-100
            10-20% growth    → 70-90
            0-10% growth     → 50-70
            -10-0% decline   → 30-50
            <-10% decline    → 10-30
        """
        g = m.revenue_growth_pct

        if g >= 50:
            return 95  # Cap — very high growth is suspicious
        elif g >= 20:
            return 70 + (g - 20) * (25 / 30)
        elif g >= 10:
            return 50 + (g - 10) * (20 / 10)
        elif g >= 0:
            return 30 + g * (20 / 10)
        elif g >= -10:
            return 15 + (g + 10) * (15 / 10)
        else:
            return max(5, 15 + g * 1.0)

    def _score_profitability(self, m: BusinessMetrics) -> float:
        """Score profitability (0-100).

        Based on profit margin (profit / revenue).

        Benchmarks (informal economy):
            >40% margin → 95     (exceptional)
            30-40%      → 80-95  (excellent)
            20-30%      → 60-80  (good)
            10-20%      → 40-60  (acceptable)
            0-10%       → 10-40  (concerning)
            <0%         → 0-10   (loss)
        """
        if m.total_revenue == 0:
            return 0

        margin = m.total_profit / m.total_revenue

        if margin >= 0.40:
            return 95
        elif margin >= 0.30:
            return 80 + (margin - 0.30) * (15 / 0.10)
        elif margin >= 0.20:
            return 60 + (margin - 0.20) * (20 / 0.10)
        elif margin >= 0.10:
            return 40 + (margin - 0.10) * (20 / 0.10)
        elif margin >= 0:
            return 10 + margin * (30 / 0.10)
        else:
            return max(0, 10 + margin * 100)

    def _score_consistency(self, m: BusinessMetrics) -> float:
        """Score revenue consistency (0-100).

        Based on coefficient of variation (CV) of daily revenue.
        Lower CV = more consistent = better.

        Also factors in active days ratio.

        Benchmarks:
            CV < 0.3  → 90-100  (very consistent)
            CV 0.3-0.5 → 70-90  (consistent)
            CV 0.5-0.8 → 50-70  (moderate)
            CV 0.8-1.2 → 30-50  (volatile)
            CV > 1.2   → 10-30  (very volatile)
        """
        cv = m.coefficient_of_variation

        # CV score
        if cv <= 0.3:
            cv_score = 90 + (0.3 - cv) * (10 / 0.3)
        elif cv <= 0.5:
            cv_score = 70 + (0.5 - cv) * (20 / 0.2)
        elif cv <= 0.8:
            cv_score = 50 + (0.8 - cv) * (20 / 0.3)
        elif cv <= 1.2:
            cv_score = 30 + (1.2 - cv) * (20 / 0.4)
        else:
            cv_score = max(5, 30 - (cv - 1.2) * 20)

        # Active days ratio (how many days did the business operate?)
        if m.days_in_period > 0:
            active_ratio = m.days_active / m.days_in_period
            if active_ratio >= 0.9:
                active_score = 100
            elif active_ratio >= 0.7:
                active_score = 70 + (active_ratio - 0.7) * (30 / 0.2)
            elif active_ratio >= 0.5:
                active_score = 50 + (active_ratio - 0.5) * (20 / 0.2)
            else:
                active_score = active_ratio * 100
        else:
            active_score = 50

        # Weighted: 70% CV, 30% active days
        return cv_score * 0.7 + active_score * 0.3

    def _score_diversity(self, m: BusinessMetrics) -> float:
        """Score product diversity (0-100).

        Based on:
        - Number of unique products (more = better, up to a point)
        - Revenue concentration (less concentration = better)

        Benchmarks:
            5+ products, top <40% → 90-100
            3-4 products, top <50% → 70-90
            2 products, top <60%   → 50-70
            1 product              → 20-40
        """
        # Product count score
        if m.unique_products >= 5:
            count_score = 90 + min((m.unique_products - 5) * 2, 10)
        elif m.unique_products >= 3:
            count_score = 70 + (m.unique_products - 3) * 10
        elif m.unique_products >= 2:
            count_score = 50 + (m.unique_products - 2) * 20
        elif m.unique_products >= 1:
            count_score = 20 + (m.unique_products - 1) * 30
        else:
            count_score = 0

        # Concentration score (lower concentration = higher score)
        conc = m.top_product_concentration
        if conc <= 0.40:
            conc_score = 90 + (0.40 - conc) * (10 / 0.40)
        elif conc <= 0.50:
            conc_score = 70 + (0.50 - conc) * (20 / 0.10)
        elif conc <= 0.60:
            conc_score = 50 + (0.60 - conc) * (20 / 0.10)
        elif conc <= 0.80:
            conc_score = 30 + (0.80 - conc) * (20 / 0.20)
        else:
            conc_score = max(5, 30 - (conc - 0.80) * 100)

        return count_score * 0.5 + conc_score * 0.5

    def _score_savings(self, m: BusinessMetrics) -> float:
        """Score savings behavior (0-100).

        Based on:
        - Savings rate (savings / revenue)
        - Absolute savings amount
        - Months of data (trust in the number)

        Benchmarks:
            >15% savings rate → 90-100
            10-15%            → 70-90
            5-10%             → 50-70
            0-5%              → 20-50
            0%                → 10
        """
        rate = m.savings_rate

        if rate >= 0.15:
            rate_score = 90 + min((rate - 0.15) * (10 / 0.15), 10)
        elif rate >= 0.10:
            rate_score = 70 + (rate - 0.10) * (20 / 0.05)
        elif rate >= 0.05:
            rate_score = 50 + (rate - 0.05) * (20 / 0.05)
        elif rate > 0:
            rate_score = 20 + rate * (30 / 0.05)
        else:
            rate_score = 10

        # Bonus for having absolute savings
        if m.total_savings > 0:
            savings_bonus = min(m.total_savings / 10000 * 5, 10)  # Up to 10 bonus points
        else:
            savings_bonus = 0

        return min(rate_score + savings_bonus, 100)

    # -------------------------------------------------------------------
    # Credit Readiness
    # -------------------------------------------------------------------

    def calculate_credit_readiness(self, metrics: BusinessMetrics) -> CreditReadinessResult:
        """Assess readiness for a business loan.

        Checks:
        1. Sufficient data history (>=6 months)
        2. Positive profit margin (>=15%)
        3. Consistent transactions (>=3/day average)
        4. Revenue consistency (CV < 0.6)
        5. Active days ratio (>=60%)
        6. Savings history (at least some savings)

        Args:
            metrics: Business metrics data.

        Returns:
            CreditReadinessResult with score, readiness status, and details.
        """
        requirements = {}
        missing = []

        # 1. Data history
        has_history = metrics.months_of_data >= self.CREDIT_MIN_MONTHS
        requirements["data_history"] = has_history
        if not has_history:
            missing.append(f"Hifadhi data kwa miezi {self.CREDIT_MIN_MONTHS} (sasa: {metrics.months_of_data})")

        # 2. Profit margin
        margin = metrics.total_profit / max(metrics.total_revenue, 1)
        has_margin = margin >= self.CREDIT_MIN_MARGIN
        requirements["profit_margin"] = has_margin
        if not has_margin:
            missing.append(f"Ongeza margin hadi {self.CREDIT_MIN_MARGIN * 100:.0f}% (sasa: {margin * 100:.1f}%)")

        # 3. Transaction frequency
        avg_daily_tx = metrics.total_transactions / max(metrics.days_active, 1)
        has_tx = avg_daily_tx >= self.CREDIT_MIN_TRANSACTIONS_PER_DAY
        requirements["transaction_frequency"] = has_tx
        if not has_tx:
            missing.append(f"Ongeza mauzo hadi {self.CREDIT_MIN_TRANSACTIONS_PER_DAY}/siku (sasa: {avg_daily_tx:.1f})")

        # 4. Consistency
        consistency = 1 - metrics.coefficient_of_variation if metrics.coefficient_of_variation < 1 else 0
        has_consistency = consistency >= self.CREDIT_MIN_CONSISTENCY
        requirements["consistency"] = has_consistency
        if not has_consistency:
            missing.append("Biashara yako haijakaa sawa — fanya kazi kwa utaratibu")

        # 5. Active days
        active_ratio = metrics.days_active / max(metrics.days_in_period, 1)
        has_active = active_ratio >= 0.6
        requirements["active_days"] = has_active
        if not has_active:
            missing.append(f"Fungua biashara siku zaidi (sasa: {active_ratio * 100:.0f}%)")

        # 6. Savings
        has_savings = metrics.total_savings > 0 or metrics.savings_rate > 0
        requirements["savings"] = has_savings
        if not has_savings:
            missing.append("Anza kuweka akiba — hata KSh 100 kwa siku")

        # Calculate score
        met_count = sum(1 for v in requirements.values() if v)
        total_count = len(requirements)
        base_score = (met_count / total_count) * 100

        # Bonus for margin quality
        if margin > 0.25:
            base_score = min(base_score + 5, 100)
        if metrics.months_of_data >= 12:
            base_score = min(base_score + 5, 100)

        score = round(base_score, 1)
        ready = score >= 70

        # Estimate loan range
        if ready:
            monthly_profit = metrics.total_profit / max(metrics.months_of_data, 1)
            min_loan = monthly_profit * 3
            max_loan = monthly_profit * 10
            loan_range = (round(min_loan, -3), round(max_loan, -3))
        else:
            loan_range = (0, 0)

        # Generate recommendation
        if ready:
            rec_sw = f"Biashara yako iko tayari kwa mkopo! Unaweza kuomba mkopo wa {format_currency(loan_range[0])} - {format_currency(loan_range[1])}."
            rec_en = f"Your business is ready for a loan! You can apply for {format_currency(loan_range[0])} - {format_currency(loan_range[1])}."
        else:
            rec_sw = "Biashara yako bado haijafikia kiwango cha mkopo. Fanya kazi kwenye vidokezo vya chini."
            rec_en = "Your business is not yet ready for a loan. Work on the items below."

        return CreditReadinessResult(
            score=score,
            ready=ready,
            estimated_loan_range=loan_range,
            requirements_met=requirements,
            missing_requirements=missing,
            recommendation_sw=rec_sw,
            recommendation_en=rec_en,
        )

    # -------------------------------------------------------------------
    # Investment Readiness
    # -------------------------------------------------------------------

    def calculate_investment_readiness(self, metrics: BusinessMetrics) -> InvestmentReadinessResult:
        """Assess readiness to invest in business expansion.

        Checks:
        1. Health score >= 65
        2. Savings rate >= 10%
        3. Profit margin >= 20%
        4. Consistent growth
        5. At least 6 months of data

        Args:
            metrics: Business metrics data.

        Returns:
            InvestmentReadinessResult with score, readiness, and recommendations.
        """
        score = 0
        factors = []

        # Health score factor (30%)
        health = self.calculate_health_score(metrics)
        health_factor = min(health.overall_score / 100, 1.0) * 30
        score += health_factor
        if health.overall_score >= 65:
            factors.append("Afya ya biashara ni nzuri")

        # Savings factor (25%)
        if metrics.savings_rate >= self.INVEST_MIN_SAVINGS_RATE:
            savings_factor = 25
            factors.append("Akiba ya kutosha")
        elif metrics.savings_rate > 0:
            savings_factor = (metrics.savings_rate / self.INVEST_MIN_SAVINGS_RATE) * 25
        else:
            savings_factor = 0
        score += savings_factor

        # Margin factor (20%)
        margin = metrics.total_profit / max(metrics.total_revenue, 1)
        if margin >= self.INVEST_MIN_MARGIN:
            margin_factor = 20
            factors.append("Margin ya faida nzuri")
        elif margin > 0:
            margin_factor = (margin / self.INVEST_MIN_MARGIN) * 20
        else:
            margin_factor = 0
        score += margin_factor

        # Growth factor (15%)
        if metrics.revenue_growth_pct > 0:
            growth_factor = min(metrics.revenue_growth_pct / 20, 1.0) * 15
            if metrics.revenue_growth_pct >= 10:
                factors.append("Ukuaji mzuri")
        else:
            growth_factor = 0
        score += growth_factor

        # Data history factor (10%)
        if metrics.months_of_data >= 6:
            history_factor = 10
            factors.append("Data ya kutosha")
        else:
            history_factor = (metrics.months_of_data / 6) * 10
        score += min(history_factor, 10)

        score = round(min(score, 100), 1)
        ready = score >= 60

        # Determine investment types
        investment_types = []
        if ready:
            if margin >= 0.25:
                investment_types.append("Kuongeza stock / bidhaa mpya")
            if metrics.unique_products < 5:
                investment_types.append("Kuongeza aina za bidhaa")
            if metrics.total_savings >= 20000:
                investment_types.append("Kufungua duka la kudumu")
            if health.overall_score >= 75:
                investment_types.append("Kupanua biashara")
            if not investment_types:
                investment_types.append("Kuongeza stock ya bidhaa zako bora")

        # Risk level
        if score >= 80:
            risk = "Chini"
        elif score >= 60:
            risk = "Wastani"
        else:
            risk = "Juu"

        # Recommendations
        if ready:
            rec_sw = f"Uko tayari kuwekeza! {', '.join(investment_types[:2])}. Hatari: {risk}."
            rec_en = f"You're ready to invest! {', '.join(investment_types[:2])}. Risk: {risk}."
        else:
            rec_sw = f"Bado hujaandaa kuwekeza. Ongeza akiba na faida kwanza. Alama: {score}/100."
            rec_en = f"Not yet ready to invest. Build savings and profit first. Score: {score}/100."

        return InvestmentReadinessResult(
            score=score,
            ready=ready,
            recommended_investment_types=investment_types,
            risk_level=risk,
            recommendation_sw=rec_sw,
            recommendation_en=rec_en,
        )

    # -------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------

    def _grade(self, score: float) -> tuple[str, str]:
        """Convert score to letter grade and emoji.

        Args:
            score: Numeric score (0-100).

        Returns:
            Tuple of (grade_letter, emoji).
        """
        if score >= 90:
            return "A+", "🏆"
        elif score >= 80:
            return "A", "🌟"
        elif score >= 70:
            return "B+", "✅"
        elif score >= 60:
            return "B", "👍"
        elif score >= 50:
            return "C+", "📊"
        elif score >= 40:
            return "C", "⚠️"
        elif score >= 30:
            return "D", "📉"
        else:
            return "F", "🔴"

    def _analyze_components(
        self, components: dict[str, float]
    ) -> tuple[list[str], list[str]]:
        """Identify strengths and weaknesses from component scores.

        Args:
            components: Dict of component_name → score.

        Returns:
            Tuple of (strengths, weaknesses) lists.
        """
        strengths = []
        weaknesses = []

        labels = {
            "growth": ("Ukuaji mzuri", "Ukuaji ni polepole"),
            "profitability": ("Faida nzuri", "Faida inahitaji kuboreshwa"),
            "consistency": ("Mauzo ya kudumu", "Mauzo ni ya kutofauti"),
            "diversity": ("Bidhaa mbalimbali", "Bidhaa ni chache"),
            "savings": ("Akiba nzuri", "Akiba inahitaji kuboreshwa"),
        }

        for key, score in components.items():
            good_label, bad_label = labels.get(key, (key, key))
            if score >= 70:
                strengths.append(good_label)
            elif score < 50:
                weaknesses.append(bad_label)

        return strengths, weaknesses

    def _generate_recommendations(
        self, m: BusinessMetrics, components: dict[str, float]
    ) -> list[str]:
        """Generate actionable recommendations based on scores.

        Args:
            m: Business metrics.
            components: Component scores.

        Returns:
            List of recommendation strings in Swahili.
        """
        recs = []

        # Growth recommendations
        if components["growth"] < 50:
            if m.revenue_growth_pct < 0:
                recs.append("Biashara yako inapungua — angalia bei na ubora wa bidhaa")
            else:
                recs.append("Ongeza wateja wapya — jaribu matangazo ya mdomo")

        # Profitability recommendations
        if components["profitability"] < 50:
            margin = m.total_profit / max(m.total_revenue, 1)
            if margin < 0.10:
                recs.append("Margin yako ni ndogo sana — angalia bei za manunuzi na uongeze bei kidogo")
            elif margin < 0.20:
                recs.append("Jaribu kupunguza gharama za manunuzi — nunua kwa wingi")

        # Consistency recommendations
        if components["consistency"] < 50:
            if m.days_active < m.days_in_period * 0.7:
                recs.append("Fungua biashara siku zaidi — kila siku ni nafasi ya kuuza")
            else:
                recs.append("Mauzo yako ni ya kutofauti — weka bei na bidhaa thabiti")

        # Diversity recommendations
        if components["diversity"] < 50:
            if m.unique_products <= 1:
                recs.append("Ongeza bidhaa mpya — hata bidhaa 2-3 zinaweza kuongeza mauzo")
            elif m.top_product_concentration > 0.7:
                recs.append("Biashara yako inategemea bidhaa moja — ongeza bidhaa nyingine")

        # Savings recommendations
        if components["savings"] < 50:
            if m.savings_rate == 0:
                recs.append("Anza kuweka akiba leo — hata KSh 50 kwa siku inasaidia")
            else:
                recs.append("Ongeza akiba — jaribu kuweka 10% ya mauzo kila siku")

        # Default if no recommendations
        if not recs:
            recs.append("Biashara yako iko vizuri! Endelea kufanya kazi nzuri")

        return recs[:5]  # Max 5 recommendations

    def _summary_sw(
        self, score: float, grade: str, strengths: list[str], weaknesses: list[str]
    ) -> str:
        """Generate Swahili summary.

        Args:
            score: Overall score.
            grade: Letter grade.
            strengths: List of strengths.
            weaknesses: List of weaknesses.

        Returns:
            Swahili summary paragraph.
        """
        if score >= 80:
            return (
                f"Biashara yako iko na afya nzuri! Alama: {score:.0f}/100 ({grade}). "
                f"Endelea na kazi nzuri na ongeza bidhaa mpya."
            )
        elif score >= 60:
            return (
                f"Biashara yako iko vizuri lakini inaweza kuboreshwa. Alama: {score:.0f}/100 ({grade}). "
                f"Kuna nafasi ya kuboresha — angalia vidokezo vya chini."
            )
        elif score >= 40:
            return (
                f"Biashara yako inahitaji kuboreshwa. Alama: {score:.0f}/100 ({grade}). "
                f"Fanya kazi kwenye mapendekezo haya ili kuboresha."
            )
        else:
            return (
                f"Biashara yako inahitaji msaada. Alama: {score:.0f}/100 ({grade}). "
                f"Anza na mapendekezo rahisi kwanza."
            )

    def _summary_en(
        self, score: float, grade: str, strengths: list[str], weaknesses: list[str]
    ) -> str:
        """Generate English summary.

        Args:
            score: Overall score.
            grade: Letter grade.
            strengths: List of strengths.
            weaknesses: List of weaknesses.

        Returns:
            English summary paragraph.
        """
        if score >= 80:
            return (
                f"Your business is healthy! Score: {score:.0f}/100 ({grade}). "
                f"Keep up the good work and consider adding new products."
            )
        elif score >= 60:
            return (
                f"Your business is doing well but can improve. Score: {score:.0f}/100 ({grade}). "
                f"There's room to grow — check the tips below."
            )
        elif score >= 40:
            return (
                f"Your business needs improvement. Score: {score:.0f}/100 ({grade}). "
                f"Work on the recommendations below to get better."
            )
        else:
            return (
                f"Your business needs help. Score: {score:.0f}/100 ({grade}). "
                f"Start with the simple recommendations first."
            )

    def render_health_report(self, result: HealthScoreResult, locale: str = "sw") -> str:
        """Render health score as a WhatsApp-formatted string.

        Args:
            result: Health score result.
            locale: Language.

        Returns:
            Formatted WhatsApp message string.
        """
        lines = []

        # Header
        if locale == "sw":
            lines.append(f"🏥 *Afya ya biashara:* {result.overall_score:.0f}/100 {result.emoji}")
        else:
            lines.append(f"🏥 *Business Health:* {result.overall_score:.1f}/100 {result.emoji}")

        # Visual bar
        bar_width = 15
        filled = int((result.overall_score / 100) * bar_width)
        bar = BLOCK_SOLID * filled + BLOCK_LIGHT * (bar_width - filled)
        lines.append(f"   {bar} {result.grade}")

        # Components
        if locale == "sw":
            component_labels = {
                "growth": "📈 Ukuaji",
                "profitability": "💰 Faida",
                "consistency": "📊 Utulivu",
                "diversity": "📦 Bidhaa",
                "savings": "🏦 Akiba",
            }
        else:
            component_labels = {
                "growth": "📈 Growth",
                "profitability": "💰 Profit",
                "consistency": "📊 Consistency",
                "diversity": "📦 Diversity",
                "savings": "🏦 Savings",
            }

        lines.append("")
        for key, label in component_labels.items():
            score = result.components.get(key, 0)
            mini_filled = int((score / 100) * 8)
            mini_bar = BLOCK_FULL * mini_filled + BLOCK_LIGHT * (8 - mini_filled)
            lines.append(f"   {label}: {mini_bar} {score:.0f}")

        # Strengths
        if result.strengths:
            lines.append("")
            if locale == "sw":
                lines.append("✅ *Nguvu:*")
            else:
                lines.append("✅ *Strengths:*")
            for s in result.strengths:
                lines.append(f"   • {s}")

        # Weaknesses
        if result.weaknesses:
            lines.append("")
            if locale == "sw":
                lines.append("⚠️ *Mapungufu:*")
            else:
                lines.append("⚠️ *Weaknesses:*")
            for w in result.weaknesses:
                lines.append(f"   • {w}")

        # Recommendations
        if result.recommendations:
            lines.append("")
            if locale == "sw":
                lines.append("💡 *Mapendekezo:*")
            else:
                lines.append("💡 *Recommendations:*")
            for i, r in enumerate(result.recommendations, 1):
                lines.append(f"   {i}. {r}")

        return "\n".join(lines)

    def render_credit_report(self, result: CreditReadinessResult, locale: str = "sw") -> str:
        """Render credit readiness as a WhatsApp-formatted string.

        Args:
            result: Credit readiness result.
            locale: Language.

        Returns:
            Formatted WhatsApp message string.
        """
        lines = []

        # Header
        ready_emoji = CHECK if result.ready else CROSS_MARK
        if locale == "sw":
            lines.append(f"🏦 *Uwezo wa mkopo:* {result.score:.0f}/100 {ready_emoji}")
        else:
            lines.append(f"🏦 *Credit Readiness:* {result.score:.0f}/100 {ready_emoji}")

        # Visual bar
        bar_width = 15
        filled = int((result.score / 100) * bar_width)
        bar = BLOCK_SOLID * filled + BLOCK_LIGHT * (bar_width - filled)
        lines.append(f"   {bar}")

        # Loan range if ready
        if result.ready:
            loan_min = format_currency(result.estimated_loan_range[0])
            loan_max = format_currency(result.estimated_loan_range[1])
            if locale == "sw":
                lines.append(f"   Mkopo unaoweza: {loan_min} - {loan_max}")
            else:
                lines.append(f"   Loan range: {loan_min} - {loan_max}")

        # Requirements checklist
        lines.append("")
        if locale == "sw":
            lines.append("📋 *Mahitaji:*")
            req_labels = {
                "data_history": "Data ya miezi 6+",
                "profit_margin": "Faida ≥15%",
                "transaction_frequency": "Mauzo ≥3/siku",
                "consistency": "Mauzo ya kudumu",
                "active_days": "Siku za biashara ≥60%",
                "savings": "Akiba",
            }
        else:
            lines.append("📋 *Requirements:*")
            req_labels = {
                "data_history": "6+ months of data",
                "profit_margin": "Profit margin ≥15%",
                "transaction_frequency": "≥3 transactions/day",
                "consistency": "Consistent sales",
                "active_days": "≥60% active days",
                "savings": "Savings history",
            }

        for key, label in req_labels.items():
            met = result.requirements_met.get(key, False)
            icon = CHECK if met else CROSS_MARK
            lines.append(f"   {icon} {label}")

        # Missing requirements
        if result.missing_requirements:
            lines.append("")
            if locale == "sw":
                lines.append("❌ *Unahitaji:*")
            else:
                lines.append("❌ *Still needed:*")
            for req in result.missing_requirements:
                lines.append(f"   • {req}")

        # Recommendation
        lines.append("")
        if locale == "sw":
            lines.append(f"💡 {result.recommendation_sw}")
        else:
            lines.append(f"💡 {result.recommendation_en}")

        return "\n".join(lines)
