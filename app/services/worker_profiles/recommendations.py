"""
Worker Type Recommendations — Msaidizi / Angavu Intelligence

Provides type-specific recommendations for what to track, what insights
matter most, what financial products fit, and what tips are relevant
for each of the 25 worker types.

This module consumes WorkerProfile data and generates actionable
recommendations tailored to each worker's reality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .profiles import (
    FinancialProduct,
    KeyMetric,
    RiskLevel,
    WorkerProfile,
    WorkerSector,
    get_all_profiles,
    get_profile,
    get_profiles_by_sector,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Recommendation Categories
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class RecommendationPriority(str, Enum):
    CRITICAL = "critical"   # Must address immediately
    HIGH = "high"           # Should address soon
    MEDIUM = "medium"       # Good to address when possible
    LOW = "low"             # Nice to have


class RecommendationCategory(str, Enum):
    TRACKING = "tracking"               # What data to collect
    INSIGHTS = "insights"               # What patterns to watch
    FINANCIAL = "financial"             # Financial products & savings
    OPERATIONS = "operations"           # Day-to-day business tips
    GROWTH = "growth"                   # Scaling and expansion
    RISK = "risk"                       # Risk management
    SEASONAL = "seasonal"               # Seasonal preparation


@dataclass
class Recommendation:
    """A single actionable recommendation for a worker."""
    category: RecommendationCategory
    priority: RecommendationPriority
    title: str
    description: str
    action_steps: list[str]
    impact: str                 # "high", "medium", "low"
    effort: str                 # "easy", "moderate", "hard"
    swahili_summary: str        # Summary in Swahili for the worker


@dataclass
class TrackingRecommendation:
    """What to track and why."""
    what: str
    why: str
    how: str
    frequency: str              # "daily", "weekly", "monthly"
    tool: str                   # "notebook", "phone", "mpesa", "app"
    benchmark_good: str | None
    benchmark_average: str | None


@dataclass
class InsightRule:
    """A rule for generating insights from tracked data."""
    name: str
    trigger_condition: str      # When this condition is true...
    insight_message: str        # ...show this message
    action_suggestion: str      # ...and suggest this action
    priority: RecommendationPriority


@dataclass
class FinancialFit:
    """How well a financial product fits a worker type."""
    product: FinancialProduct
    fit_score: float            # 0.0 to 1.0
    fit_reasons: list[str]
    timing: str                 # When to recommend: "now", "soon", "future"
    prerequisites: list[str]    # What the worker needs first


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Recommendation Engine
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class RecommendationEngine:
    """
    Generates personalized recommendations for workers based on
    their type profile and current business state.
    """

    def get_tracking_recommendations(
        self, type_id: str
    ) -> list[TrackingRecommendation]:
        """Get what a worker type should track and why."""
        profile = get_profile(type_id)
        if not profile:
            return []

        recs: list[TrackingRecommendation] = []

        # Universal tracking for all types
        recs.append(TrackingRecommendation(
            what="Daily revenue",
            why="Know if you're making money or losing money each day",
            how="Write down total sales at end of day, or use M-Pesa till report",
            frequency="daily",
            tool="notebook",
            benchmark_good=f"KSh {profile.income.average * 1.5:.0f}+",
            benchmark_average=f"KSh {profile.income.average:.0f}",
        ))

        recs.append(TrackingRecommendation(
            what="Daily expenses",
            why="Understand where your money goes — expenses eat profits silently",
            how="Keep receipts, write down every purchase",
            frequency="daily",
            tool="notebook",
            benchmark_good=f"Below KSh {profile.operating_costs.total * 0.8:.0f}",
            benchmark_average=f"KSh {profile.operating_costs.total:.0f}",
        ))

        # Type-specific tracking
        for metric in profile.key_metrics:
            recs.append(TrackingRecommendation(
                what=metric.name.replace("_", " ").title(),
                why=metric.description,
                how=self._tracking_how(metric, profile),
                frequency=metric.track_frequency,
                tool=self._tracking_tool(metric),
                benchmark_good=self._format_benchmark(metric, "good"),
                benchmark_average=self._format_benchmark(metric, "average"),
            ))

        # Sector-specific additions
        recs.extend(self._sector_tracking(profile))

        return recs

    def get_insight_rules(self, type_id: str) -> list[InsightRule]:
        """Get insight generation rules for a worker type."""
        profile = get_profile(type_id)
        if not profile:
            return []

        rules: list[InsightRule] = []

        # Universal insight rules
        rules.append(InsightRule(
            name="profit_decline",
            trigger_condition="3-day moving average of profit drops >20% from weekly average",
            insight_message="Your profits have been declining for 3 days. Let's figure out why.",
            action_suggestion="Check: Did expenses go up? Did sales drop? Did you change suppliers?",
            priority=RecommendationPriority.HIGH,
        ))

        rules.append(InsightRule(
            name="expense_spike",
            trigger_condition="Daily expenses exceed 2x the 7-day average",
            insight_message="Today's expenses were unusually high.",
            action_suggestion="Review what was different — was it a restock day or an emergency?",
            priority=RecommendationPriority.MEDIUM,
        ))

        rules.append(InsightRule(
            name="no_sales_day",
            trigger_condition="Zero revenue on a working day",
            insight_message="No sales recorded today. Did something happen?",
            action_suggestion="If you worked but made no sales, log it anyway — it helps track patterns.",
            priority=RecommendationPriority.HIGH,
        ))

        # Type-specific insight rules
        rules.extend(self._type_insight_rules(profile))

        # Seasonal insight rules
        rules.extend(self._seasonal_insight_rules(profile))

        return rules

    def get_financial_fits(
        self, type_id: str,
        current_income: float | None = None,
        has_savings: bool = False,
        has_outstanding_loan: bool = False,
    ) -> list[FinancialFit]:
        """
        Get financial product recommendations ranked by fit.

        Args:
            type_id: Worker type
            current_income: Average monthly income (for sizing)
            has_savings: Whether worker already has savings
            has_outstanding_loan: Whether worker has existing debt
        """
        profile = get_profile(type_id)
        if not profile:
            return []

        fits: list[FinancialFit] = []
        monthly_income = current_income or profile.income.monthly_average

        for product in profile.financial_products:
            fit_score, reasons, timing, prereqs = self._assess_financial_fit(
                product, profile, monthly_income, has_savings, has_outstanding_loan
            )
            fits.append(FinancialFit(
                product=product,
                fit_score=fit_score,
                fit_reasons=reasons,
                timing=timing,
                prerequisites=prereqs,
            ))

        # Sort by fit score descending
        fits.sort(key=lambda f: f.fit_score, reverse=True)
        return fits

    def get_operational_tips(
        self, type_id: str, context: dict[str, Any] | None = None
    ) -> list[Recommendation]:
        """Get operational recommendations based on type and context."""
        profile = get_profile(type_id)
        if not profile:
            return []

        tips: list[Recommendation] = []

        # From profile success tips
        for i, tip in enumerate(profile.success_tips[:5]):
            tips.append(Recommendation(
                category=RecommendationCategory.OPERATIONS,
                priority=RecommendationPriority.HIGH if i < 3 else RecommendationPriority.MEDIUM,
                title=tip.split("—")[0].strip() if "—" in tip else tip[:60],
                description=tip,
                action_steps=[tip],
                impact="high" if i < 3 else "medium",
                effort="easy" if i < 2 else "moderate",
                swahili_summary="",
            ))

        # Context-based tips
        if context:
            tips.extend(self._context_tips(profile, context))

        return tips

    def get_growth_recommendations(self, type_id: str) -> list[Recommendation]:
        """Get growth and scaling recommendations."""
        profile = get_profile(type_id)
        if not profile:
            return []

        recs: list[Recommendation] = []

        # Universal growth paths
        if profile.location_type == "fixed":
            recs.append(Recommendation(
                category=RecommendationCategory.GROWTH,
                priority=RecommendationPriority.MEDIUM,
                title="Consider expanding to a second location",
                description="Your fixed-location business can scale by opening a second stall or shop in a different area.",
                action_steps=[
                    "Identify underserved areas with high foot traffic",
                    "Save for 3 months of rent as startup capital",
                    "Consider hiring someone to manage the first location",
                ],
                impact="high",
                effort="hard",
                swahili_summary="Fikiria kufungua duka la pili mahali pengine",
            ))

        if profile.requires_stock:
            recs.append(Recommendation(
                category=RecommendationCategory.GROWTH,
                priority=RecommendationPriority.MEDIUM,
                title="Buy in bulk for better margins",
                description="Pooling with other vendors or buying direct from producers can cut stock costs by 15-30%.",
                action_steps=[
                    "Identify 2-3 other vendors who buy similar stock",
                    "Calculate combined weekly demand",
                    "Negotiate bulk pricing with suppliers",
                    "Split transport costs",
                ],
                impact="high",
                effort="moderate",
                swahili_summary="Nunua kwa wingi pamoja na wengine — bei itapungua",
            ))

        # Digital presence
        recs.append(Recommendation(
            category=RecommendationCategory.GROWTH,
            priority=RecommendationPriority.LOW,
            title="Build a WhatsApp customer list",
            description="A WhatsApp broadcast list lets you notify regulars about new stock, specials, or your location.",
            action_steps=[
                "Ask regular customers for their WhatsApp number",
                "Create a broadcast list (not a group — more personal)",
                "Send 1-2 messages per week: new arrivals, specials, your location",
            ],
            impact="medium",
            effort="easy",
            swahili_summary="Tuma WhatsApp kwa wateja wako kuhusu bidhaa mpya",
        ))

        # Sector-specific growth
        recs.extend(self._sector_growth(profile))

        return recs

    def get_risk_recommendations(self, type_id: str) -> list[Recommendation]:
        """Get risk management recommendations."""
        profile = get_profile(type_id)
        if not profile:
            return []

        recs: list[Recommendation] = []

        # Universal risk management
        if profile.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM):
            recs.append(Recommendation(
                category=RecommendationCategory.RISK,
                priority=RecommendationPriority.CRITICAL,
                title="Build an emergency fund",
                description=f"With {profile.risk_level.value} risk level, you need at least 2 weeks of expenses saved. That's KSh {profile.operating_costs.total * 14:,.0f}.",
                action_steps=[
                    f"Save KSh {max(50, profile.income.average * 0.1):.0f} daily",
                    "Use M-Pesa lock savings or a separate account",
                    "Don't touch it unless it's a real emergency",
                ],
                impact="high",
                effort="moderate",
                swahili_summary="Weka akiba ya dharura — angalau wiki 2 za matumizi",
            ))

        # Type-specific risks
        risk_recs = {
            "mama_mboga": Recommendation(
                category=RecommendationCategory.RISK,
                priority=RecommendationPriority.HIGH,
                title="Manage spoilage risk",
                description="Perishables can destroy your margins. Buy smaller quantities more often.",
                action_steps=[
                    "Track which items spoil most often",
                    "Buy those items in smaller quantities",
                    "Sell near-expiry items at cost rather than throwing away",
                ],
                impact="high",
                effort="easy",
                swahili_summary="Punguza hasara — nunua kidogo mara nyingi",
            ),
            "boda_boda": Recommendation(
                category=RecommendationCategory.RISK,
                priority=RecommendationPriority.CRITICAL,
                title="Get health and accident insurance",
                description="Boda boda accidents are the #1 risk. NHIF costs KSh 500/month but covers hospitalization.",
                action_steps=[
                    "Register for NHIF immediately if not registered",
                    "Consider additional personal accident cover",
                    "Always wear a helmet — it's the cheapest insurance",
                ],
                impact="high",
                effort="easy",
                swahili_summary="Pata bima ya afya — ajali za boda ni hatari sana",
            ),
            "machinga": Recommendation(
                category=RecommendationCategory.RISK,
                priority=RecommendationPriority.HIGH,
                title="Diversify selling locations",
                description="Don't rely on one spot — kanjo can confiscate your goods anytime.",
                action_steps=[
                    "Map 4-5 different selling locations",
                    "Learn kanjo patrol schedules for each area",
                    "Keep stock small and portable — less to lose",
                ],
                impact="high",
                effort="easy",
                swahili_summary="Tumia maeneo tofauti — usiwe na mahali pamoja tu",
            ),
            "mkulima": Recommendation(
                category=RecommendationCategory.RISK,
                priority=RecommendationPriority.CRITICAL,
                title="Explore crop insurance",
                description="One drought or flood season can wipe out everything. Index-based crop insurance costs KSh 500-2,000 per season.",
                action_steps=[
                    "Check Agricultural Insurance (AII) products from KCB or Equity",
                    "Register with your county's agricultural extension officer",
                    "Diversify crops to spread risk",
                ],
                impact="high",
                effort="moderate",
                swahili_summary="Fikiria bima ya mazao — ukame au mvua inaweza kuharibu kila kitu",
            ),
            "construction_fundi": Recommendation(
                category=RecommendationCategory.RISK,
                priority=RecommendationPriority.CRITICAL,
                title="Invest in safety equipment",
                description="Construction injuries are common and devastating. A hard hat (KSh 500) and boots (KSh 1,500) are cheap protection.",
                action_steps=[
                    "Buy a hard hat, safety boots, and gloves",
                    "Refuse to work at heights without proper equipment",
                    "Register for NHIF to cover medical emergencies",
                ],
                impact="high",
                effort="easy",
                swahili_summary="Nunua vifaa vya usalama — helmet, boots, glavu",
            ),
        }

        if type_id in risk_recs:
            recs.append(risk_recs[type_id])

        return recs

    def get_seasonal_prep(self, type_id: str, current_month: int) -> list[Recommendation]:
        """Get seasonal preparation recommendations."""
        profile = get_profile(type_id)
        if not profile:
            return []

        recs: list[Recommendation] = []

        # Check if peak or slow month is coming
        next_month = (current_month % 12) + 1

        if next_month in profile.peak_months:
            recs.append(Recommendation(
                category=RecommendationCategory.SEASONAL,
                priority=RecommendationPriority.HIGH,
                title="Peak season approaching — prepare!",
                description=f"Next month is a peak revenue period for {profile.name}. Stock up and position yourself.",
                action_steps=[
                    "Increase stock levels by 30-50%",
                    "Secure additional working capital if needed",
                    "Plan your schedule to maximize working hours",
                    "Build customer awareness — let regulars know you're ready",
                ],
                impact="high",
                effort="moderate",
                swahili_summary="Msimu wa biashara unakuja — jiandae! Ongeza stock",
            ))

        if next_month in profile.slow_months:
            recs.append(Recommendation(
                category=RecommendationCategory.SEASONAL,
                priority=RecommendationPriority.HIGH,
                title="Slow season approaching — prepare financially",
                description=f"Next month is typically slow for {profile.name}. Save now to bridge the gap.",
                action_steps=[
                    "Save extra this month — aim for 2 weeks of expenses",
                    "Reduce stock levels to match lower expected demand",
                    "Consider complementary income sources",
                    "Delay non-essential purchases",
                ],
                impact="high",
                effort="moderate",
                swahili_summary="Msimu mgumu unakuja — weka akiba sasa!",
            ))

        # Current seasonal insights
        for insight in profile.seasonal_insights:
            month_names = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ]
            if month_names[current_month - 1] in insight:
                recs.append(Recommendation(
                    category=RecommendationCategory.SEASONAL,
                    priority=RecommendationPriority.MEDIUM,
                    title="Seasonal context",
                    description=insight,
                    action_steps=["Review and adjust your business plan accordingly"],
                    impact="medium",
                    effort="easy",
                    swahili_summary="",
                ))

        return recs

    # ── Internal Helpers ──────────────────────────────────────────────

    def _tracking_how(self, metric: KeyMetric, profile: WorkerProfile) -> str:
        """Determine how to track a metric."""
        if metric.unit == "KSh":
            return "Record in a notebook or use M-Pesa transaction history"
        elif metric.unit == "%":
            return "Calculate from other tracked numbers"
        elif metric.unit == "count":
            return "Tally mark in a notebook"
        elif metric.unit == "text":
            return "Note down when observed"
        else:
            return "Track in a notebook or phone"

    def _tracking_tool(self, metric: KeyMetric) -> str:
        """Determine the best tracking tool for a metric."""
        if metric.unit == "KSh":
            return "mpesa"
        elif metric.track_frequency == "daily":
            return "notebook"
        else:
            return "phone"

    def _format_benchmark(self, metric: KeyMetric, level: str) -> str | None:
        """Format benchmark value for display."""
        val = getattr(metric, f"target_{level}", None)
        if val is None:
            return None
        if metric.unit == "KSh":
            return f"KSh {val:,.0f}"
        elif metric.unit == "%":
            return f"{val:.0f}%"
        elif metric.unit == "count":
            return f"{val:.0f}"
        else:
            return str(val)

    def _sector_tracking(self, profile: WorkerProfile) -> list[TrackingRecommendation]:
        """Add sector-specific tracking recommendations."""
        recs: list[TrackingRecommendation] = []

        if profile.sector == WorkerSector.FOOD:
            recs.append(TrackingRecommendation(
                what="Waste and spoilage",
                why="Food businesses lose 10-30% of stock to spoilage — tracking it saves money",
                how="At end of day, count items thrown away and estimate their cost",
                frequency="daily",
                tool="notebook",
                benchmark_good="Below 5% of stock value",
                benchmark_average="10-15% of stock value",
            ))

        if profile.sector == WorkerSector.TRANSPORT:
            recs.append(TrackingRecommendation(
                what="Fuel consumption",
                why="Fuel is your biggest cost — every shilling saved goes to profit",
                how="Record litres purchased and amount paid each time",
                frequency="daily",
                tool="notebook",
                benchmark_good="Efficient use — track km/litre",
                benchmark_average="Standard consumption for your vehicle",
            ))

        if profile.sector == WorkerSector.RETAIL:
            recs.append(TrackingRecommendation(
                what="Dead stock",
                why="Items sitting unsold for 30+ days are wasted capital",
                how="Mark dates on stock — anything unsold for a month is dead stock",
                frequency="weekly",
                tool="notebook",
                benchmark_good="Below KSh 500 in dead stock",
                benchmark_average="KSh 1,000-2,000 in dead stock",
            ))

        return recs

    def _type_insight_rules(self, profile: WorkerProfile) -> list[InsightRule]:
        """Generate type-specific insight rules."""
        rules: list[InsightRule] = []

        if profile.type_id == "mama_mboga":
            rules.append(InsightRule(
                name="spoilage_alert",
                trigger_condition="Daily spoilage exceeds 20% of stock cost",
                insight_message="You're losing too much to spoilage! Almost 1 in 5 vegetables is going to waste.",
                action_suggestion="Buy smaller quantities, focus on fast-moving items, sell near-expiry at cost.",
                priority=RecommendationPriority.HIGH,
            ))
            rules.append(InsightRule(
                name="wholesale_price_change",
                trigger_condition="Wholesale price of top 3 items changes >15% from weekly average",
                insight_message="Market prices have shifted significantly.",
                action_suggestion="Adjust your selling prices or switch to alternative vegetables.",
                priority=RecommendationPriority.MEDIUM,
            ))

        elif profile.type_id == "boda_boda":
            rules.append(InsightRule(
                name="fuel_efficiency_drop",
                trigger_condition="Daily fuel cost increases >20% without more trips",
                insight_message="Your fuel efficiency has dropped — the bike may need maintenance.",
                action_suggestion="Check tyre pressure, air filter, and chain tension.",
                priority=RecommendationPriority.HIGH,
            ))
            rules.append(InsightRule(
                name="low_earning_day",
                trigger_condition="Daily earnings below 50% of 7-day average",
                insight_message="Today was a slow day. Was it weather, traffic, or a route change?",
                action_suggestion="Note what was different — it helps predict and avoid slow days.",
                priority=RecommendationPriority.MEDIUM,
            ))

        elif profile.type_id == "dukawallah":
            rules.append(InsightRule(
                name="dead_stock_warning",
                trigger_condition="Dead stock value exceeds KSh 3,000",
                insight_message="You have too much unsold stock — that money could be working for you.",
                action_suggestion="Mark down dead stock items, bundle with fast sellers, or return to supplier.",
                priority=RecommendationPriority.HIGH,
            ))
            rules.append(InsightRule(
                name="margin_erosion",
                trigger_condition="Average profit margin drops below 15%",
                insight_message="Your margins are getting thin — you might be selling at a loss on some items.",
                action_suggestion="Review prices on every item — some may need increasing.",
                priority=RecommendationPriority.CRITICAL,
            ))

        elif profile.type_id == "mkulima":
            rules.append(InsightRule(
                name="harvest_timing",
                trigger_condition="Crop is ready but market price is at seasonal low",
                insight_message="Market prices are low right now — selling now may mean less profit.",
                action_suggestion="If you can store safely, wait 2-4 weeks for prices to recover.",
                priority=RecommendationPriority.HIGH,
            ))

        return rules

    def _seasonal_insight_rules(self, profile: WorkerProfile) -> list[InsightRule]:
        """Generate seasonal insight rules."""
        rules: list[InsightRule] = []

        # Rain impact for outdoor workers
        if profile.location_type in ("mobile", "fixed") and profile.sector in (
            WorkerSector.FOOD, WorkerSector.RETAIL
        ):
            rules.append(InsightRule(
                name="rain_impact",
                trigger_condition="Rainy day detected (weather API or manual flag)",
                insight_message="Rain reduces customer traffic. Did you prepare?",
                action_suggestion="Consider moving to a sheltered location or reducing stock for the day.",
                priority=RecommendationPriority.MEDIUM,
            ))

        return rules

    def _context_tips(
        self, profile: WorkerProfile, context: dict[str, Any]
    ) -> list[Recommendation]:
        """Generate tips based on current business context."""
        tips: list[Recommendation] = []

        # Low savings tip
        savings = context.get("savings_amount", 0)
        if savings < profile.operating_costs.total * 7:
            tips.append(Recommendation(
                category=RecommendationCategory.FINANCIAL,
                priority=RecommendationPriority.HIGH,
                title="Your savings are low",
                description=f"You have KSh {savings:,.0f} saved, but you need at least KSh {profile.operating_costs.total * 7:,.0f} (1 week of expenses) as a buffer.",
                action_steps=[
                    f"Save KSh {max(50, profile.income.average * 0.1):.0f} starting today",
                    "Use M-Pesa lock savings to prevent spending",
                ],
                impact="high",
                effort="moderate",
                swahili_summary="Akiba yako ni ndogo — anza kuweka leo",
            ))

        # High debt tip
        if context.get("has_outstanding_loan", False):
            tips.append(Recommendation(
                category=RecommendationCategory.FINANCIAL,
                priority=RecommendationPriority.HIGH,
                title="Focus on clearing existing debt",
                description="Before taking new loans, prioritize paying off current ones to avoid debt spiral.",
                action_steps=[
                    "List all debts with interest rates",
                    "Pay off highest-interest debt first",
                    "Avoid new loans until current ones are cleared",
                ],
                impact="high",
                effort="moderate",
                swahili_summary="Lipa deni zako kwanza kabla ya kukopa zaidi",
            ))

        return tips

    def _assess_financial_fit(
        self,
        product: FinancialProduct,
        profile: WorkerProfile,
        monthly_income: float,
        has_savings: bool,
        has_outstanding_loan: bool,
    ) -> tuple[float, list[str], str, list[str]]:
        """Assess how well a financial product fits a worker."""
        score = 0.5  # Base score
        reasons: list[str] = []
        timing = "soon"
        prereqs: list[str] = []

        # Savings products are always relevant
        if "savings" in product.name.lower() or "sacco" in product.name.lower():
            score += 0.2
            reasons.append("Savings products are universally beneficial")
            if not has_savings:
                timing = "now"
                reasons.append("You don't have savings yet — start immediately")

        # Loan products
        if "loan" in product.name.lower() or "financing" in product.name.lower():
            if has_outstanding_loan:
                score -= 0.3
                reasons.append("You have existing debt — reduce before taking more")
                timing = "future"
            elif monthly_income < profile.income.monthly_average * 0.5:
                score -= 0.2
                reasons.append("Income is low — build stability first")
                timing = "future"
                prereqs.append("Stabilize monthly income first")
            else:
                score += 0.1
                reasons.append("Good fit based on your income level")

        # Insurance products
        if "insurance" in product.name.lower() or "nhif" in product.name.lower():
            if profile.risk_level == RiskLevel.HIGH:
                score += 0.3
                reasons.append("High-risk occupation — insurance is critical")
                timing = "now"
            elif profile.risk_level == RiskLevel.MEDIUM:
                score += 0.15
                reasons.append("Medium risk — insurance provides peace of mind")

        # Mobile products for low-income workers
        if "mobile" in product.provider_type and monthly_income < 10000:
            score += 0.1
            reasons.append("Mobile products are accessible and convenient")

        # Chama products for community-oriented workers
        if "chama" in product.provider_type:
            score += 0.15
            reasons.append("Group savings leverage community trust and accountability")

        return min(1.0, max(0.0, score)), reasons, timing, prereqs

    def _sector_growth(self, profile: WorkerProfile) -> list[Recommendation]:
        """Generate sector-specific growth recommendations."""
        recs: list[Recommendation] = []

        if profile.sector == WorkerSector.FOOD:
            recs.append(Recommendation(
                category=RecommendationCategory.GROWTH,
                priority=RecommendationPriority.MEDIUM,
                title="Add a delivery option",
                description="Offer free delivery within 1km for orders above KSh 200. Many customers will pay more for convenience.",
                action_steps=[
                    "Offer delivery to nearby offices and homes",
                    "Use WhatsApp for ordering",
                    "Charge a small delivery fee or set a minimum order",
                ],
                impact="medium",
                effort="easy",
                swahili_summary="Toa huduma ya kuleta — wateja wengi wanapenda urahisi",
            ))

        if profile.sector == WorkerSector.SERVICES:
            recs.append(Recommendation(
                category=RecommendationCategory.GROWTH,
                priority=RecommendationPriority.MEDIUM,
                title="Upsell complementary services",
                description="A barber who also does facials, or a fundi who also paints, earns more per customer.",
                action_steps=[
                    "Identify 1-2 related services you can learn",
                    "Watch YouTube tutorials to build the skill",
                    "Offer as an add-on to existing customers",
                ],
                impact="medium",
                effort="moderate",
                swahili_summary="Ongeza huduma zinazohusiana — faida zaidi kwa mteja mmoja",
            ))

        return recs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Singleton
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_engine: RecommendationEngine | None = None


def get_recommendation_engine() -> RecommendationEngine:
    """Get or create the singleton RecommendationEngine."""
    global _engine
    if _engine is None:
        _engine = RecommendationEngine()
    return _engine
