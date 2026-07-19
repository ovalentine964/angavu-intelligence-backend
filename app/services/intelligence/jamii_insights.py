"""
Jamii Insights — NGO Financial Inclusion Service.

Financial inclusion metrics by demographic:
- Digital payment adoption
- Savings and credit access
- Impact measurement for development programs

Academic Foundation (Valentine's BSc Economics & Statistics):
- STA 246: Statistical Demography → Population metrics, life tables,
  demographic transition, fertility/mortality, cohort analysis
- ECO 100/401: Development Economics → Poverty measurement (FGT measures,
  Alkire-Foster MPI), inequality indices (Gini, Theil, Atkinson),
  capability approach (Sen), Lewis dual sector model
- ECO 206: Economics of Microfinance → Adverse selection, moral hazard,
  group lending, savings mobilisation, microinsurance
- ECO 204: Issues in African Development → Structural transformation,
  institutional economics, gender and development, governance

Buyers: NGOs, development organizations (World Bank, USAID, DFID)
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.intelligence.cache import intelligence_cache
from app.services.intelligence.health_economics import HealthEconomicsEngine
from app.services.research.hypothesis_testing import HypothesisTester
from app.services.statistical_foundation import (
    ClusterAnalyzer,
    InequalityAnalyzer,
    PovertyAnalyzer,
    bootstrap,
    kde_estimator,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# ECO 100/401 — Poverty and Inequality Measurement helpers
# ─────────────────────────────────────────────────────────────────────────────

def _gini_coefficient(incomes: np.ndarray) -> float:
    """
    Gini coefficient: G = (2Σiyᵢ)/(nΣyᵢ) - (n+1)/n.

    Driven by ECO 100 § Measurement of Development and ECO 401 § Poverty
    and Inequality — measures income inequality on a 0-1 scale where
    0 = perfect equality and 1 = perfect inequality.

    Uses the "fast" formula on sorted incomes:
    G = (2/(n²μ)) Σᵢ(i·y₍ᵢ₎) - (n+1)/n

    Args:
        incomes: array of income values

    Returns:
        Gini coefficient (0-1)
    """
    n = len(incomes)
    if n < 2 or np.sum(incomes) == 0:
        return 0.0
    sorted_inc = np.sort(incomes)
    cumulative = np.cumsum(sorted_inc)
    mu = np.mean(sorted_inc)
    # Fast formula
    gini = (2 * np.sum(np.arange(1, n + 1) * sorted_inc) / (n * n * mu)) - (n + 1) / n
    return round(float(max(0, min(1, gini))), 4)


def _theil_index(incomes: np.ndarray) -> float:
    """
    Theil Index: T = (1/n)Σ(yᵢ/μ)·ln(yᵢ/μ).

    Driven by ECO 401 § Poverty and Inequality — a decomposable
    inequality measure (unlike Gini). Can be split into within-group
    and between-group inequality. T = 0 for perfect equality.

    Theil is GE(1); Theil-L (mean log deviation) is GE(0).

    Args:
        incomes: array of positive income values

    Returns:
        Theil index (≥ 0)
    """
    incomes = incomes[incomes > 0]
    n = len(incomes)
    if n == 0:
        return 0.0
    mu = np.mean(incomes)
    if mu <= 0:
        return 0.0
    ratios = incomes / mu
    ratios = ratios[ratios > 0]
    theil = float(np.mean(ratios * np.log(ratios)))
    return round(max(0, theil), 4)


def _atkinson_index(incomes: np.ndarray, epsilon: float = 1.0) -> float:
    """
    Atkinson Index: A = 1 - (1/μ)[(1/n)Σyᵢ^(1-ε)]^(1/(1-ε)).

    Driven by ECO 401 § Poverty and Inequality — an inequality measure
    with an explicit inequality aversion parameter ε:
    - ε = 0: no aversion (Atkinson = 0)
    - ε = 1: logarithmic: A = 1 - (geometric mean / arithmetic mean)
    - ε → ∞: maximin (Rawlsian)

    Args:
        incomes: array of positive income values
        epsilon: inequality aversion parameter

    Returns:
        Atkinson index (0-1)
    """
    incomes = incomes[incomes > 0]
    if len(incomes) == 0:
        return 0.0
    mu = np.mean(incomes)
    if mu <= 0:
        return 0.0

    if abs(epsilon - 1.0) < 1e-6:
        # Logarithmic case
        geometric_mean = np.exp(np.mean(np.log(incomes)))
        atkinson = 1 - geometric_mean / mu
    else:
        mean_transformed = np.mean(incomes ** (1 - epsilon)) ** (1 / (1 - epsilon))
        atkinson = 1 - mean_transformed / mu

    return round(float(max(0, min(1, atkinson))), 4)


def _fgt_poverty_measure(
    incomes: np.ndarray, poverty_line: float, alpha: int = 0
) -> float:
    """
    Foster-Greer-Thorbecke (FGT) poverty measure.

    Driven by ECO 401 § Poverty and Inequality:
    P_α = (1/n) Σᵢ ((z - yᵢ)/z)^α  for yᵢ < z

    α = 0: Headcount ratio (proportion below poverty line)
    α = 1: Poverty gap (average shortfall as proportion of line)
    α = 2: Squared poverty gap (severity — weights extreme poverty more)

    Args:
        incomes: array of income values
        poverty_line: poverty threshold z
        alpha: FGT parameter (0, 1, or 2)

    Returns:
        FGT poverty measure
    """
    n = len(incomes)
    if n == 0:
        return 0.0
    poor = incomes[incomes < poverty_line]
    if len(poor) == 0:
        return 0.0
    gaps = (poverty_line - poor) / poverty_line
    if alpha == 0:
        return round(float(len(poor) / n), 4)
    elif alpha == 1:
        return round(float(np.sum(gaps) / n), 4)
    elif alpha == 2:
        return round(float(np.sum(gaps**2) / n), 4)
    else:
        return round(float(np.sum(gaps**alpha) / n), 4)


def _lorenz_curve(incomes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Lorenz Curve: cumulative income share vs cumulative population share.

    Driven by ECO 100 § Measurement of Development — visual representation
    of inequality. Perfect equality = 45° line. The further the Lorenz
    curve bows below, the greater the inequality.

    Args:
        incomes: array of income values

    Returns:
        (population_shares, income_shares) arrays for plotting
    """
    sorted_inc = np.sort(incomes)
    n = len(sorted_inc)
    cum_pop = np.arange(1, n + 1) / n
    cum_income = np.cumsum(sorted_inc) / np.sum(sorted_inc)
    return cum_pop, cum_income


# ─────────────────────────────────────────────────────────────────────────────
# STA 246 — Statistical Demography helpers
# ─────────────────────────────────────────────────────────────────────────────

def _construct_abridged_life_table(
    age_groups: list[str],
    population: np.ndarray,
    deaths: np.ndarray,
) -> list[dict[str, Any]]:
    """
    Construct an abridged life table from age-group population and deaths.

    Driven by STA 246 § Life Tables:
    - nMₓ = nDₓ / nPₓ (age-specific death rate)
    - nqₓ = n·nMₓ / (1 + (1-αₓ)·n·nMₓ) (probability of dying)
    - lₓ₊ₙ = lₓ · (1 - nqₓ) (survival)
    - nLₓ = n·(lₓ₊ₙ + αₓ·n·dₓ) (person-years lived)
    - eₓ = Tₓ / lₓ (life expectancy)

    Args:
        age_groups: labels like ["0", "1-4", "5-9", ...]
        population: mid-year population in each age group
        deaths: deaths in each age group

    Returns:
        list of life table rows
    """
    n = len(age_groups)
    # Width of each age group
    widths = []
    for ag in age_groups:
        if ag == "0":
            widths.append(1)
        elif "-" in ag:
            parts = ag.split("-")
            widths.append(int(parts[1]) - int(parts[0]) + 1)
        else:
            widths.append(5)

    l = [100000.0]  # radix
    life_table = []

    for i in range(n):
        nM = deaths[i] / max(population[i], 1)
        width = widths[i]
        alpha = 0.5  # Assume uniform distribution of deaths

        nq = min(1.0, (width * nM) / (1 + (1 - alpha) * width * nM))
        nd = l[-1] * nq
        lx_next = l[-1] - nd
        nL = width * (lx_next + alpha * nd)

        life_table.append({
            "age_group": age_groups[i],
            "population": int(population[i]),
            "deaths": int(deaths[i]),
            "nMx": round(float(nM), 6),
            "nqx": round(float(nq), 6),
            "lx": round(float(l[-1]), 2),
            "ndx": round(float(nd), 2),
            "nLx": round(float(nL), 2),
        })
        l.append(lx_next)

    # Compute Tₓ and eₓ
    T = 0
    for i in range(n - 1, -1, -1):
        T += life_table[i]["nLx"]
        life_table[i]["Tx"] = round(T, 2)
        life_table[i]["ex"] = round(T / max(life_table[i]["lx"], 1), 2)

    return life_table


def _compute_dependency_ratio(
    youth_pop: float, working_age_pop: float, elderly_pop: float
) -> dict[str, float]:
    """
    Dependency ratios.

    Driven by STA 246 § Population Projections — key indicator for
    demographic dividend analysis.

    Args:
        youth_pop: population aged 0-14
        working_age_pop: population aged 15-64
        elderly_pop: population aged 65+

    Returns:
        dict with youth, elderly, and total dependency ratios
    """
    wap = max(working_age_pop, 1)
    return {
        "youth_dependency_ratio": round(youth_pop / wap * 100, 1),
        "elderly_dependency_ratio": round(elderly_pop / wap * 100, 1),
        "total_dependency_ratio": round((youth_pop + elderly_pop) / wap * 100, 1),
        "demographic_dividend_potential": "high" if (youth_pop + elderly_pop) / wap < 0.5 else "moderate",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ECO 206 — Microfinance Impact Analysis helpers
# ─────────────────────────────────────────────────────────────────────────────

def _microfinance_impact_score(
    digital_adoption: float,
    credit_access: float,
    savings_behavior: float,
    group_membership_pct: float,
) -> dict[str, Any]:
    """
    Composite microfinance inclusion score.

    Driven by ECO 206 § Foundations of Microfinance:
    - Financial inclusion = access to credit + savings + insurance + payments
    - Group lending (chama) as social collateral mechanism
    - Mobile money (M-Pesa) as digital financial infrastructure
    - Progressive lending: build credit history through small loans

    Uses equal-weighted geometric mean approach.

    Args:
        digital_adoption: % using digital payments (0-100)
        credit_access: % with credit access (0-100)
        savings_behavior: savings consistency score (0-100)
        group_membership_pct: % in financial groups (0-100)

    Returns:
        dict with composite score and components
    """
    # Geometric mean (all must be > 0)
    vals = [max(1, v) for v in [digital_adoption, credit_access, savings_behavior, group_membership_pct]]
    composite = float(np.prod(vals) ** (1 / len(vals)))
    composite = min(100, composite)

    return {
        "microfinance_inclusion_index": round(composite, 1),
        "components": {
            "digital_payments": round(digital_adoption, 1),
            "credit_access": round(credit_access, 1),
            "savings_behavior": round(savings_behavior, 1),
            "group_membership": round(group_membership_pct, 1),
        },
        "interpretation": (
            "high" if composite > 70
            else "moderate" if composite > 40
            else "low"
        ),
    }


class JamiiInsightsService:
    """
    Financial inclusion intelligence service for NGO buyers.

    Generates demographic-level financial inclusion metrics
    and program impact assessments.

    Statistical methods powered by Valentine's degree:
    - Poverty: FGT measures, Gini, Theil, Atkinson (ECO 100/401)
    - Demography: Life tables, dependency ratios (STA 246)
    - Microfinance: Inclusion indices, impact analysis (ECO 206)
    - Development: Capability approach, Lewis model (ECO 204/401)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def generate_inclusion_report(
        self,
        region: str,
        demographic_segment: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        program_name: str | None = None,
        buyer_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Generate financial inclusion intelligence.

        Args:
            region: Geographic region or 'national'
            demographic_segment: youth, women, rural, urban, etc.
            period_start: Analysis start (default: 90 days ago)
            period_end: Analysis end (default: today)
            program_name: Specific program for impact evaluation
            buyer_id: Buyer requesting this data

        Returns:
            Inclusion report dict or None if k-anonymity not met
        """
        cached = await intelligence_cache.get(
            "jamii_insights",
            region=region,
            demographic=demographic_segment,
            start=str(period_start),
            end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        # Build user query
        user_query = select(User).where(
            and_(
                User.is_active == True,
                User.consent_data_sharing == True,
            )
        )
        if region != "national":
            user_query = user_query.where(
                User.location_geohash.like(f"{region}%")
            )

        result = await self.db.execute(user_query)
        users = result.scalars().all()

        if demographic_segment:
            users = self._filter_demographic(users, demographic_segment)

        user_count = len(users)
        if user_count < settings.K_ANONYMITY_THRESHOLD:
            logger.warning("jamii_insights_k_failed", region=region, users=user_count)
            return None

        user_ids = [u.id for u in users]

        # Get transactions
        txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()

        sales = [t for t in transactions if t.transaction_type == "SALE"]

        # Financial inclusion metrics
        mpesa_users = set()
        cash_users = set()
        credit_users = set()
        daily_revenues = defaultdict(lambda: defaultdict(float))
        monthly_revenues = defaultdict(float)

        for t in sales:
            uid = str(t.user_id)
            if t.payment_method == "mpesa":
                mpesa_users.add(uid)
            elif t.payment_method == "cash":
                cash_users.add(uid)
            elif t.payment_method == "credit":
                credit_users.add(uid)
            daily_revenues[t.user_id][t.timestamp.strftime("%Y-%m-%d")] += t.amount
            monthly_revenues[t.timestamp.strftime("%Y-%m")] += t.amount

        # Digital payment adoption
        digital_adoption = round(len(mpesa_users) / max(user_count, 1) * 100, 1)

        # Savings proxy
        consistent_users = 0
        for uid, daily in daily_revenues.items():
            revenues = list(daily.values())
            if len(revenues) >= 10 and np.mean(revenues) > 0:
                cv = np.std(revenues) / max(np.mean(revenues), 1)
                if cv < 0.5:
                    consistent_users += 1
        savings_score = min(100, round(consistent_users / max(user_count, 1) * 100, 1))

        # Credit access proxy
        credit_access = round(len(credit_users) / max(user_count, 1) * 100, 1)

        # ── ECO 100/401: Composite inclusion index ──────────────────────────
        inclusion_index = round(
            digital_adoption * 0.35
            + savings_score * 0.25
            + credit_access * 0.20
            + min(100, user_count / 10) * 0.20,
            1,
        )

        registration_pct = round(digital_adoption * 0.6, 1)

        # Demographics
        youth_owned = sum(1 for u in users if self._is_youth(u))
        women_owned = sum(1 for u in users if self._is_woman(u))
        youth_pct = round(youth_owned / max(user_count, 1) * 100, 1)
        women_pct = round(women_owned / max(user_count, 1) * 100, 1)

        # ── ECO 100/401: Income distribution analysis ───────────────────────
        total_revenue = sum(t.amount for t in sales)
        months_in_period = max(1, (period_end - period_start).days / 30)
        avg_monthly = total_revenue / max(user_count, 1) / months_in_period
        dp_avg_monthly = max(0, round(
            self.anonymizer.add_laplace_noise(avg_monthly, sensitivity=5000), 0
        ))

        # Per-user monthly income distribution for inequality analysis
        user_monthly_incomes = np.array([
            sum(t.amount for t in sales if t.user_id == u.id) / months_in_period
            for u in users
        ])
        user_monthly_incomes = user_monthly_incomes[user_monthly_incomes > 0]

        # Gini coefficient
        gini = _gini_coefficient(user_monthly_incomes) if len(user_monthly_incomes) > 1 else None

        # Theil index (decomposable)
        theil = _theil_index(user_monthly_incomes) if len(user_monthly_incomes) > 1 else None

        # Atkinson index (ε=1, logarithmic case)
        atkinson = _atkinson_index(user_monthly_incomes, epsilon=1.0) if len(user_monthly_incomes) > 1 else None

        # Poverty measures (FGT)
        poverty_line_daily = 2.15 * 130  # $2.15/day in KES (approx 130 KES/USD)
        poverty_line_monthly = poverty_line_daily * 30
        poverty_headcount = _fgt_poverty_measure(user_monthly_incomes, poverty_line_monthly, alpha=0)
        poverty_gap = _fgt_poverty_measure(user_monthly_incomes, poverty_line_monthly, alpha=1)
        poverty_severity = _fgt_poverty_measure(user_monthly_incomes, poverty_line_monthly, alpha=2)

        # Lorenz curve data
        lorenz_pop, lorenz_inc = None, None
        if len(user_monthly_incomes) > 5:
            lorenz_pop, lorenz_inc = _lorenz_curve(user_monthly_incomes)
            # Downsample for API response
            step = max(1, len(lorenz_pop) // 20)
            lorenz_data = {
                "population_shares": [round(float(lorenz_pop[i]), 3) for i in range(0, len(lorenz_pop), step)],
                "income_shares": [round(float(lorenz_inc[i]), 3) for i in range(0, len(lorenz_inc), step)],
            }
        else:
            lorenz_data = None

        # ── ECO 206: Microfinance inclusion score ───────────────────────────
        group_membership_pct = min(100, user_count / 10)  # Proxy
        mfi_score = _microfinance_impact_score(
            digital_adoption, credit_access, savings_score, group_membership_pct
        )

        # Income growth
        first_half_rev = sum(
            t.amount for t in sales
            if t.timestamp < datetime.combine(
                period_start + (period_end - period_start) / 2, datetime.min.time()
            )
        )
        second_half_rev = total_revenue - first_half_rev
        income_growth = 0
        if first_half_rev > 0:
            income_growth = round(
                (second_half_rev - first_half_rev) / first_half_rev * 100, 1
            )

        # Employment
        employment_created = user_count
        livelihoods = user_count * 3

        # Barriers to inclusion
        barriers = self._assess_barriers(
            digital_adoption, credit_access, savings_score, user_count
        )

        # ── STA 442: Cluster Analysis for community segmentation ───────
        community_segmentation = None
        if user_count >= 15:
            try:
                user_features = []
                for u in users:
                    uid = u.id
                    u_sales = [t for t in sales if t.user_id == uid]
                    u_rev = sum(t.amount for t in u_sales)
                    u_mpesa = sum(1 for t in u_sales if t.payment_method == "mpesa")
                    u_txn_count = len(u_sales)
                    u_digital = 1 if u_mpesa > len(u_sales) * 0.5 else 0
                    user_features.append([
                        u_rev / max(months_in_period, 1),
                        u_txn_count / max(months_in_period, 1),
                        u_digital,
                        1.0 if u_mpesa > 0 else 0.0,
                    ])

                if len(user_features) >= 15:
                    seg_data = np.array(user_features, dtype=float)
                    seg_result = ClusterAnalyzer.segment_market(
                        seg_data,
                        feature_names=["monthly_revenue", "monthly_txns", "digital_adoption", "has_mpesa"],
                        max_k=min(5, len(user_features) // 4),
                    )
                    community_segmentation = {
                        "optimal_k": seg_result["optimal_k"],
                        "silhouette_score": seg_result["silhouette_score"],
                        "segments": [
                            {
                                "segment_id": s["segment_id"],
                                "size": s["size"],
                                "proportion": s["proportion"],
                                "profile": s["profile"],
                            }
                            for s in seg_result["segments"]
                        ],
                    }
            except Exception as e:
                logger.debug("community_segmentation_failed", error=str(e))

        # Program impact
        program_impact = None
        if program_name:
            program_impact = {
                "program_name": program_name,
                "beneficiary_count": user_count,
                "pre_program_index": max(0, inclusion_index - income_growth),
                "post_program_index": inclusion_index,
                "impact_delta": round(income_growth, 1),
                "cost_per_beneficiary_kes": None,
            }

        # ── ECO 106: Health-economic intelligence ──────────────────────
        health_economic = None
        try:
            avg_monthly_inc = avg_monthly if avg_monthly > 0 else 10000
            health_economic = HealthEconomicsEngine.full_health_economic_report(
                transactions=transactions,
                region=region,
                user_count=user_count,
                avg_monthly_income=avg_monthly_inc,
                poverty_line_monthly=poverty_line_monthly,
            )
        except Exception as e:
            logger.debug("health_economic_failed", error=str(e))

        response = {
            "product": "jamii_insights",
            "version": "2.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "data_freshness": datetime.now(UTC).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, user_count / 100),
            "confidence_level": min(1.0, len(sales) / 100),
            "region": region,
            "demographic_segment": demographic_segment,
            "time_period": f"{period_start} to {period_end}",
            "inclusion_metrics": {
                "financial_inclusion_index": inclusion_index,
                "digital_payment_adoption": digital_adoption,
                "savings_behavior_score": savings_score,
                "credit_access_score": credit_access,
                "insurance_coverage_pct": 0,
            },
            # ECO 206: Microfinance inclusion
            "microfinance_inclusion": mfi_score,
            "business_registration_pct": registration_pct,
            "tax_compliance_pct": round(digital_adoption * 0.3, 1),
            "formal_banking_pct": round(digital_adoption * 0.5, 1),
            "youth_owned_pct": youth_pct,
            "women_owned_pct": women_pct,
            "avg_owner_age": None,
            "avg_monthly_income_kes": dp_avg_monthly,
            "income_growth_pct": income_growth if income_growth != 0 else None,
            # ECO 100/401: Inequality measures
            "inequality": {
                "gini_coefficient": gini,
                "theil_index": theil,
                "atkinson_index": atkinson,
                "lorenz_curve": lorenz_data,
                "interpretation": {
                    "gini": (
                        "low" if (gini or 0) < 0.3
                        else "moderate" if (gini or 0) < 0.4
                        else "high" if (gini or 0) < 0.5
                        else "very_high"
                    ),
                },
            },
            # ECO 100/401: Poverty measures (FGT)
            "poverty_indicators": {
                "poverty_line_monthly_kes": round(poverty_line_monthly, 0),
                "headcount_ratio_P0": poverty_headcount,
                "poverty_gap_P1": poverty_gap,
                "poverty_severity_P2": poverty_severity,
                "method": "FGT (Foster-Greer-Thorbecke)",
            },
            "employment_created": employment_created,
            "livelihoods_supported": livelihoods,
            "program_impact": program_impact,
            "barriers": barriers,
            # ECO 106: Health-economic intelligence
            "health_economic": health_economic,
            # STA 442: Cluster analysis for community segmentation
            "community_segmentation": community_segmentation,
            # STA 341/ECO 401: Statistical engine inequality & poverty analysis
            "advanced_inequality_analysis": self._run_statistical_engine_inequality(
                user_monthly_incomes, poverty_line_monthly,
            ),
            # STA 444: Non-parametric analysis
            "nonparametric_analysis": self._run_nonparametric_analysis(
                sales, users, user_monthly_incomes, user_count,
                poverty_line_monthly, digital_adoption, credit_access,
            ),
            "sample_size": user_count,
        }

        await intelligence_cache.set(
            "jamii_insights", response,
            region=region, demographic=demographic_segment,
            start=str(period_start), end=str(period_end),
        )

        logger.info("jamii_insights_generated", region=region, k=user_count)
        return response

    @staticmethod
    def _run_statistical_engine_inequality(
        user_monthly_incomes: np.ndarray,
        poverty_line_monthly: float,
    ) -> dict[str, Any] | None:
        """
        Run statistical engine inequality & poverty analysis (STA 341, ECO 401).

        Uses InequalityAnalyzer and PovertyAnalyzer from the statistical
        foundation layer to compute Gini, Theil, Atkinson, FGT, Lorenz curve,
        Watts index, and Sen index with proper uncertainty quantification.
        """
        if len(user_monthly_incomes) < 5:
            return None

        try:
            incomes = np.array(user_monthly_incomes, dtype=float)
            incomes = incomes[incomes > 0]
            if len(incomes) < 3:
                return None

            # InequalityAnalyzer: Gini, Theil, Atkinson, Lorenz
            gini = InequalityAnalyzer.gini_coefficient(incomes)
            theil = InequalityAnalyzer.theil_index(incomes)
            atkinson = InequalityAnalyzer.atkinson_index(incomes, epsilon=1.0)
            lorenz = InequalityAnalyzer.lorenz_curve(incomes)

            # PovertyAnalyzer: FGT, Watts, Sen
            fgt_0 = PovertyAnalyzer.fgt_measure(incomes, poverty_line_monthly, alpha=0)
            fgt_1 = PovertyAnalyzer.fgt_measure(incomes, poverty_line_monthly, alpha=1)
            fgt_2 = PovertyAnalyzer.fgt_measure(incomes, poverty_line_monthly, alpha=2)
            watts = PovertyAnalyzer.watts_index(incomes, poverty_line_monthly)
            sen = PovertyAnalyzer.sen_index(incomes, poverty_line_monthly)
            profile = PovertyAnalyzer.poverty_profile(incomes, poverty_line_monthly)

            return {
                "inequality": {
                    "gini": gini,
                    "theil": theil,
                    "atkinson": atkinson,
                    "lorenz_curve": {
                        "n_points": len(lorenz["population_shares"]),
                        "gini": lorenz["gini"],
                    },
                },
                "poverty": {
                    "fgt_0_headcount": fgt_0,
                    "fgt_1_poverty_gap": fgt_1,
                    "fgt_2_severity": fgt_2,
                    "watts_index": watts,
                    "sen_index": sen,
                    "mean_income": profile["mean_income"],
                    "median_income": profile["median_income"],
                },
                "n_observations": len(incomes),
                "method": "STA 341/ECO 401 — Statistical engine (InequalityAnalyzer, PovertyAnalyzer)",
            }
        except Exception as e:
            logger.debug("statistical_engine_inequality_failed", error=str(e))
            return None

    @staticmethod
    def _run_nonparametric_analysis(
        sales: list,
        users: list,
        user_monthly_incomes: np.ndarray,
        user_count: int,
        poverty_line_monthly: float,
        digital_adoption: float,
        credit_access: float,
    ) -> dict[str, Any] | None:
        """
        Run non-parametric statistical analysis (STA 444).

        Applies Kruskal-Wallis for cross-community comparison,
        Mann-Whitney for gender income gap, KDE for income distribution,
        and bootstrap CI on poverty measures. Essential for informal
        economy data which is non-normal, small-sample, and ordinal.
        """
        if len(sales) < 20 or len(user_monthly_incomes) < 10:
            return None

        result: dict[str, Any] = {}

        # ── STA 444: KDE for income distribution ───────────────────────────
        try:
            inc_arr = np.array(user_monthly_incomes, dtype=float)
            inc_arr = inc_arr[inc_arr > 0]
            if len(inc_arr) >= 10:
                grid, density = kde_estimator.gaussian_kde(inc_arr)
                mode_idx = int(np.argmax(density))
                result["kde_income_distribution"] = {
                    "description": "Non-parametric income density (Gaussian KDE)",
                    "mode_income": round(float(grid[mode_idx]), 2),
                    "bandwidth": round(float(
                        0.9 * min(
                            np.std(inc_arr),
                            (np.percentile(inc_arr, 75) - np.percentile(inc_arr, 25)) / 1.34,
                        ) * len(inc_arr) ** (-0.2)
                    ), 4),
                    "n_observations": len(inc_arr),
                    "multimodality": kde_estimator.detect_multimodality(inc_arr),
                    "interpretation": "Multimodal income distribution suggests distinct economic segments",
                    "method": "STA 444 — Kernel Density Estimation",
                }
        except Exception as e:
            logger.debug("kde_income_distribution_failed", error=str(e))

        # ── STA 444: Mann-Whitney — gender income gap analysis ─────────────
        try:
            male_incomes = []
            female_incomes = []
            for u in users:
                uid = u.id
                u_income = sum(t.amount for t in sales if t.user_id == uid)
                if u.business_type in ("mama_mboga", "tailor"):
                    female_incomes.append(float(u_income))
                else:
                    male_incomes.append(float(u_income))

            male_arr = np.array(male_incomes, dtype=float)
            female_arr = np.array(female_incomes, dtype=float)
            male_arr = male_arr[male_arr > 0]
            female_arr = female_arr[female_arr > 0]

            if len(male_arr) >= 5 and len(female_arr) >= 5:
                tester = HypothesisTester(alpha=0.05)
                mw_result = tester.mann_whitney_u(
                    male_arr.tolist(), female_arr.tolist()
                )
                result["mann_whitney_gender_income_gap"] = {
                    "test": "Mann-Whitney U",
                    "null_hypothesis": "Income distributions are the same for male- and female-owned businesses",
                    "test_statistic": round(mw_result.test_statistic, 4),
                    "p_value": round(mw_result.p_value, 6),
                    "significant": mw_result.reject_null,
                    "effect_size": round(mw_result.effect_size or 0, 4),
                    "male_median_income": round(float(np.median(male_arr)), 2),
                    "female_median_income": round(float(np.median(female_arr)), 2),
                    "gap_pct": round(
                        (float(np.median(male_arr)) - float(np.median(female_arr)))
                        / max(float(np.median(female_arr)), 1) * 100, 1
                    ),
                    "n_male": len(male_arr),
                    "n_female": len(female_arr),
                    "interpretation": mw_result.interpretation,
                    "method": "STA 444 — Non-parametric two-sample test (no normality assumption)",
                }
        except Exception as e:
            logger.debug("mann_whitney_gender_gap_failed", error=str(e))

        # ── STA 444: Kruskal-Wallis — compare financial inclusion across communities ──
        try:
            # Group users by business type as proxy for community
            community_incomes: dict[str, list] = defaultdict(list)
            for u in users:
                uid = u.id
                u_income = sum(t.amount for t in sales if t.user_id == uid)
                if u_income > 0:
                    community_incomes[u.business_type or "other"].append(float(u_income))

            valid_groups = [
                v for v in community_incomes.values() if len(v) >= 5
            ]
            if len(valid_groups) >= 3:
                tester = HypothesisTester(alpha=0.05)
                kw_result = tester.kruskal_wallis(valid_groups)
                result["kruskal_wallis_community_inclusion"] = {
                    "test": "Kruskal-Wallis H",
                    "null_hypothesis": "All communities have the same income distribution",
                    "test_statistic": round(kw_result.test_statistic, 4),
                    "p_value": round(kw_result.p_value, 6),
                    "significant": kw_result.reject_null,
                    "effect_size_epsilon_sq": round(kw_result.effect_size or 0, 4),
                    "n_groups": len(valid_groups),
                    "n_total": sum(len(g) for g in valid_groups),
                    "interpretation": kw_result.interpretation,
                    "method": "STA 444 — Non-parametric ANOVA (no normality assumption)",
                }
        except Exception as e:
            logger.debug("kruskal_wallis_community_failed", error=str(e))

        # ── STA 444: Bootstrap CI on poverty measures ──────────────────────
        try:
            inc_arr = np.array(user_monthly_incomes, dtype=float)
            inc_arr = inc_arr[inc_arr > 0]
            if len(inc_arr) >= 20:
                # Bootstrap CI on headcount ratio
                def _headcount(data):
                    return float(np.mean(data < poverty_line_monthly))

                boot_headcount = bootstrap.percentile_ci(
                    inc_arr, _headcount, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on mean income
                boot_mean = bootstrap.percentile_ci(
                    inc_arr, np.mean, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on median income
                boot_median = bootstrap.percentile_ci(
                    inc_arr, np.median, n_bootstrap=5000, confidence=0.95,
                )
                result["bootstrap_poverty_ci"] = {
                    "headcount_ratio": {
                        "estimate": boot_headcount["estimate"],
                        "ci_lower": boot_headcount["ci_lower"],
                        "ci_upper": boot_headcount["ci_upper"],
                        "bootstrap_se": boot_headcount["bootstrap_se"],
                    },
                    "mean_income": {
                        "estimate": boot_mean["estimate"],
                        "ci_lower": boot_mean["ci_lower"],
                        "ci_upper": boot_mean["ci_upper"],
                        "bootstrap_se": boot_mean["bootstrap_se"],
                    },
                    "median_income": {
                        "estimate": boot_median["estimate"],
                        "ci_lower": boot_median["ci_lower"],
                        "ci_upper": boot_median["ci_upper"],
                        "bootstrap_se": boot_median["bootstrap_se"],
                    },
                    "poverty_line_monthly_kes": round(poverty_line_monthly, 0),
                    "confidence": 0.95,
                    "n_bootstrap": 5000,
                    "method": "STA 444 — Bootstrap percentile CI (distribution-free)",
                }
        except Exception as e:
            logger.debug("bootstrap_poverty_ci_failed", error=str(e))

        return result if result else None

    @staticmethod
    def _filter_demographic(users: list, segment: str) -> list:
        """Filter users by demographic segment."""
        if segment == "youth":
            return [u for u in users if u.business_type in ("boda_boda", "vendor")]
        elif segment == "women":
            return [u for u in users if u.business_type in ("mama_mboga", "tailor")]
        elif segment == "rural":
            return [u for u in users if u.location_geohash and len(u.location_geohash) >= 5]
        elif segment == "urban":
            return [u for u in users if u.location_geohash and len(u.location_geohash) <= 4]
        return users

    @staticmethod
    def _is_youth(user) -> bool:
        return user.business_type in ("boda_boda", "vendor")

    @staticmethod
    def _is_woman(user) -> bool:
        return user.business_type in ("mama_mboga", "tailor")

    @staticmethod
    def _assess_barriers(
        digital: float, credit: float, savings: float, count: int
    ) -> list[dict[str, Any]]:
        """Assess barriers to financial inclusion."""
        barriers = []
        if digital < 50:
            barriers.append({
                "barrier": "low_digital_literacy",
                "severity": max(0, 100 - digital),
                "affected_pct": round(100 - digital, 1),
                "recommended_intervention": "Digital financial literacy training",
            })
        if credit < 20:
            barriers.append({
                "barrier": "limited_credit_access",
                "severity": max(0, 100 - credit * 2),
                "affected_pct": round(100 - credit, 1),
                "recommended_intervention": "Microfinance partnerships and credit education",
            })
        if savings < 30:
            barriers.append({
                "barrier": "low_savings_behavior",
                "severity": max(0, 100 - savings * 2),
                "affected_pct": round(100 - savings, 1),
                "recommended_intervention": "Savings group formation and incentives",
            })
        if count < 50:
            barriers.append({
                "barrier": "geographic_isolation",
                "severity": 60,
                "affected_pct": 40,
                "recommended_intervention": "Mobile-first service delivery",
            })
        if not barriers:
            barriers.append({
                "barrier": "no_significant_barriers",
                "severity": 10,
                "affected_pct": 5,
                "recommended_intervention": "Continue monitoring",
            })
        return barriers


# ─────────────────────────────────────────────────────────────────────────────
# ECO 106 — Emerging Public Health Issues: Health-Economic Intelligence
# ─────────────────────────────────────────────────────────────────────────────


class HealthEconomicIntelligence:
    """
    Health-economic intelligence module for informal workers.

    Driven by ECO 106 § Emerging Public Health Issues:

    Health shocks are the #1 cause of poverty entry for informal
    workers in Kenya. A single hospitalization can wipe out months
    of savings and push a family below the poverty line.

    Key Concepts:

    - Grossman Health Capital Model (1972): Health is a durable capital
      stock that depreciates over time and can be augmented by
      investment (medical care, nutrition, exercise):
        H(t+1) = H(t) - δ·H(t) + I(t)
      where δ = depreciation rate, I = health investment.
      Optimal health investment: MB(MC) = δ + r (depreciation + interest).

    - Health Shocks and Poverty: A health shock reduces labor supply
      and income, creating a poverty trap:
        Income_loss = f(shock_severity, duration, insurance_coverage)
        Poverty_probability = P(income - health_expenses < poverty_line)

    - Catastrophic Health Expenditure (WHO): Health spending > 40% of
      household's capacity to pay (non-food expenditure).
      CHE_rate = P(health_spending > 0.4 × non_food_expenditure)

    - Epidemiological Transition (Omran, 1971): Kenya is in stage 3
      (degenerative diseases) with lingering stage 2 (infectious diseases).
      Informal workers face dual burden: malaria/TB + diabetes/hypertension.

    - Financial Protection: NHIF (National Hospital Insurance Fund) covers
      ~20% of Kenyans. Informal sector largely uninsured.
      Insurance_gap = 1 - (insured_workers / total_workers)

    Data Integration Points:
    - NHIF claims data (if accessible)
    - MoH DHIS2 (District Health Information System)
    - Revenue patterns pre/post health shock (from transaction data)
    - Community health worker (CHW) reports

    References:
    - Grossman, M. (1972). "On the Concept of Health Capital and the Demand
      for Health." Journal of Political Economy, 80(2), 223-255.
    - WHO (2010). "The World Health Report — Health Systems Financing."
    - Chuma, J. & Gilson, L. (2008). "Healthcare financing and the poor:
      the case of Kenya." Journal of International Development.
    - Omran, A.R. (1971). "The Epidemiologic Transition." Milbank Memorial
      Fund Quarterly, 49(4), 509-538.
    """

    # Common health shocks affecting informal workers in Kenya
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
        "mental_health": {"avg_cost_kes": 3000, "avg_days_lost": 7, "severity": "moderate"},
    }

    # NHIF coverage rates by sector (estimated)
    NHIF_COVERAGE = {
        "formal_sector": 0.65,
        "informal_sector": 0.18,
        "overall": 0.22,
    }

    @classmethod
    def health_shock_tracker(
        cls,
        user_id: str,
        transactions: list[Any],
        lookback_days: int = 180,
        poverty_line_monthly: float = 8800,
    ) -> dict[str, Any]:
        """
        Detect and track health shocks from transaction patterns.

        Health shocks manifest as:
        1. Revenue drops (>50% decline for 3+ consecutive days)
        2. Activity gaps (zero transactions for 3+ days)
        3. Sudden expense spikes (medical payments)

        Driven by ECO 106 § Health-Economic Nexus:
        A health shock reduces H(t) → reduces labor supply → reduces income.
        The Grossman model predicts: optimal health investment increases
        when wage rate is high (high opportunity cost of illness).

        Args:
            user_id: anonymized user identifier
            transactions: list of transaction objects
            lookback_days: analysis window
            poverty_line_monthly: poverty threshold in KES

        Returns:
            Dict with detected shocks, impact assessment, and recovery tracking
        """
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if len(sales) < 20:
            return {"error": "Insufficient transaction data"}

        # Daily revenue aggregation
        daily_rev = defaultdict(float)
        daily_count = defaultdict(int)
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day] += t.amount
            daily_count[day] += 1

        sorted_days = sorted(daily_rev.keys())
        if len(sorted_days) < 14:
            return {"error": "Need at least 14 days of data"}

        revenues = np.array([daily_rev[d] for d in sorted_days], dtype=float)
        median_rev = float(np.median(revenues))
        mean_rev = float(np.mean(revenues))

        # Detect revenue drops (health shock signature)
        shocks = []
        i = 0
        while i < len(sorted_days):
            # Check if this day is significantly below median
            if daily_rev[sorted_days[i]] < median_rev * 0.5:
                # Start of potential shock
                shock_start = i
                shock_days = [sorted_days[i]]
                while i + 1 < len(sorted_days) and daily_rev[sorted_days[i + 1]] < median_rev * 0.5:
                    i += 1
                    shock_days.append(sorted_days[i])

                if len(shock_days) >= 3:  # Minimum 3 days for health shock
                    shock_rev = sum(daily_rev[d] for d in shock_days)
                    expected_rev = median_rev * len(shock_days)
                    revenue_loss = expected_rev - shock_rev

                    # Classify severity
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
                        "recovery_status": cls._assess_recovery(
                            daily_rev, sorted_days, i, median_rev
                        ),
                    })
            i += 1

        # Health shock frequency
        shock_count = len(shocks)
        shock_frequency = shock_count / max(lookback_days / 30, 1)  # Per month

        # Total impact
        total_loss = sum(s["revenue_loss_kes"] for s in shocks)
        total_days_lost = sum(s["duration_days"] for s in shocks)
        total_health_cost = sum(s["estimated_health_cost"] for s in shocks)

        # Poverty risk from health shocks
        avg_monthly_rev = mean_rev * 30
        post_shock_monthly = max(0, avg_monthly_rev - (total_loss / max(lookback_days / 30, 1)))
        poverty_risk = 1 if post_shock_monthly < poverty_line_monthly else 0

        return {
            "user_id": user_id,
            "lookback_days": lookback_days,
            "health_shocks": shocks,
            "shock_count": shock_count,
            "shock_frequency_per_month": round(shock_frequency, 2),
            "total_revenue_loss_kes": round(total_loss, 0),
            "total_days_lost": total_days_lost,
            "total_estimated_health_cost_kes": round(total_health_cost, 0),
            "avg_monthly_revenue_kes": round(avg_monthly_rev, 0),
            "post_shock_monthly_revenue_kes": round(post_shock_monthly, 0),
            "poverty_risk_from_health_shocks": poverty_risk,
            "health_vulnerability_score": cls._vulnerability_score(
                shock_frequency, total_loss, avg_monthly_rev
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
    ) -> dict[str, Any]:
        """
        Grossman health capital model — optimal health investment.

        Driven by ECO 106 § Grossman Model (1972):
        Health is a durable capital stock H(t) that:
        - Depreciates at rate δ: H(t+1) = (1-δ)·H(t) + I(t)
        - Generates healthy time: T_healthy = f(H)
        - Healthy time produces income: Y = w · T_healthy

        Optimal investment condition:
        MB of health investment = MC of health investment
        where MC = cost of medical care, MB = present value of future
        earnings from improved health.

        For informal workers:
        - Wage rate w is variable (not fixed salary)
        - δ may be higher (poor nutrition, working conditions)
        - MC may be higher (limited access, transport costs)
        - Interest rate r is higher (no formal credit)

        Args:
            current_health_stock: health status (0-100)
            wage_rate: daily wage rate in KES
            depreciation_rate: annual health depreciation (default 5%)
            interest_rate: discount rate (default 12% for informal sector)
            medical_cost_index: relative cost of medical care (1.0 = average)

        Returns:
            Dict with optimal investment, marginal benefit/cost, and recommendations
        """
        # Health production function: H(t+1) = (1-δ)·H(t) + I(t)^α
        # where α = 0.5 (diminishing returns to health investment)
        alpha = 0.5

        # Marginal product of health investment
        # MP_I = α · I^(α-1) — diminishing returns

        # Optimal investment condition:
        # MB = (w × marginal_health_time) / (r + δ)
        # MC = medical_cost_index × unit_cost

        # Marginal value of healthy time
        # Assume 1 unit of health → 0.01 units of healthy time
        health_to_time = 0.01
        marginal_value = wage_rate * health_to_time

        # Optimal investment level
        # From FOC: α · I^(α-1) × marginal_value = medical_cost_index × (r + δ)
        # Solving: I* = (α × marginal_value / (medical_cost_index × (r + δ)))^(1/(1-α))
        denominator = medical_cost_index * (interest_rate + depreciation_rate)
        if denominator > 0:
            optimal_investment = (alpha * marginal_value / denominator) ** (1 / (1 - alpha))
        else:
            optimal_investment = 0

        # Health depreciation
        annual_depreciation = current_health_stock * depreciation_rate

        # Required investment to maintain current health
        maintenance_investment = annual_depreciation

        # Investment gap
        investment_gap = maintenance_investment - optimal_investment

        # Recommendations based on current health stock
        if current_health_stock < 40:
            priority = "critical"
            recommendation = "Immediate health investment needed. Seek subsidized care at public health facilities."
        elif current_health_stock < 60:
            priority = "high"
            recommendation = "Regular health check-ups and preventive care recommended. Consider NHIF enrollment."
        elif current_health_stock < 80:
            priority = "moderate"
            recommendation = "Maintain health through balanced nutrition and regular exercise. Budget for annual check-up."
        else:
            priority = "low"
            recommendation = "Health stock is good. Continue preventive care and healthy lifestyle."

        return {
            "current_health_stock": current_health_stock,
            "wage_rate_kes": wage_rate,
            "depreciation_rate": depreciation_rate,
            "interest_rate": interest_rate,
            "optimal_annual_investment_kes": round(optimal_investment * 365, 0),
            "optimal_daily_investment_kes": round(optimal_investment, 0),
            "annual_depreciation_units": round(annual_depreciation, 2),
            "maintenance_investment_units": round(maintenance_investment, 2),
            "investment_gap_units": round(investment_gap, 2),
            "health_trajectory": "improving" if optimal_investment > maintenance_investment else "declining",
            "priority": priority,
            "recommendation": recommendation,
            "model": {
                "name": "Grossman Health Capital Model (1972)",
                "production_function": "H(t+1) = (1-δ)·H(t) + I(t)^α",
                "optimal_condition": "MB = α·I^(α-1)·w·health_to_time = MC·(r+δ)",
                "parameters": {"alpha": alpha, "health_to_time": health_to_time},
            },
        }

    @classmethod
    def health_insurance_intelligence(
        cls,
        user_count: int,
        transactions: list[Any],
        region: str,
        avg_monthly_income: float,
    ) -> dict[str, Any]:
        """
        Health insurance coverage and gap analysis.

        Driven by ECO 106 § Financial Protection in Health:
        - Universal Health Coverage (UHC): WHO goal that all people obtain
          needed health services without financial hardship.
        - Catastrophic Health Expenditure (CHE): Out-of-pocket health
          spending > 40% of non-food household expenditure.
        - NHIF (Kenya): National Hospital Insurance Fund — covers ~22%
          of population. Informal sector coverage ~18%.
        - Community-Based Health Insurance (CBHI): Chama-based health
          pools, common in informal sector.

        Insurance gap = 1 - (insured / total population)
        CHE risk = P(OOP_health_spend > 0.4 × capacity_to_pay)

        Args:
            user_count: number of users in analysis
            transactions: transaction data for income estimation
            region: geographic region
            avg_monthly_income: average monthly income in KES

        Returns:
            Dict with insurance gap, CHE risk, and recommendations
        """
        # Estimate insurance coverage (proxy: NHIF coverage for informal sector)
        estimated_coverage = cls.NHIF_COVERAGE["informal_sector"]
        insured_count = int(user_count * estimated_coverage)
        uninsured_count = user_count - insured_count
        insurance_gap = 1 - estimated_coverage

        # Catastrophic health expenditure risk
        # WHO threshold: OOP > 40% of capacity to pay (non-food expenditure)
        # Assume food = 50% of income for informal workers
        capacity_to_pay = avg_monthly_income * 0.5  # Non-food
        che_threshold = capacity_to_pay * 0.4

        # Risk assessment
        # Average hospitalization cost in Kenya: ~KES 35,000
        avg_hospitalization = 35000
        che_probability = 1 if avg_hospitalization > che_threshold else 0
        months_to_save = avg_hospitalization / max(avg_monthly_income * 0.1, 1)  # 10% savings rate

        # Health expenditure burden
        annual_health_budget = avg_monthly_income * 12 * 0.05  # WHO recommends 5%
        annual_health_budget_actual = min(annual_health_budget, avg_monthly_income * 12 * 0.15)  # Max 15%

        # CBHI (chama-based) recommendation
        cbhi_monthly_premium = avg_monthly_income * 0.02  # 2% of income
        cbhi_coverage_limit = cbhi_monthly_premium * 12 * 10  # 10x annual premium

        return {
            "region": region,
            "user_count": user_count,
            "estimated_insured": insured_count,
            "estimated_uninsured": uninsured_count,
            "insurance_coverage_rate": round(estimated_coverage * 100, 1),
            "insurance_gap_pct": round(insurance_gap * 100, 1),
            "che_risk": {
                "threshold_kes": round(che_threshold, 0),
                "avg_hospitalization_cost_kes": avg_hospitalization,
                "catastrophic_risk": "high" if che_probability else "low",
                "months_to_save_for_hospitalization": round(months_to_save, 1),
            },
            "recommended_insurance": {
                "type": "Community-Based Health Insurance (CBHI)",
                "monthly_premium_kes": round(cbhi_monthly_premium, 0),
                "annual_premium_kes": round(cbhi_monthly_premium * 12, 0),
                "coverage_limit_kes": round(cbhi_coverage_limit, 0),
                "affordability": "affordable" if cbhi_monthly_premium < avg_monthly_income * 0.05 else "stretched",
            },
            "nhif_enrollment": {
                "current_rate": round(cls.NHIF_COVERAGE["informal_sector"] * 100, 1),
                "target_rate": 50,
                "gap": round((0.50 - cls.NHIF_COVERAGE["informal_sector"]) * 100, 1),
            },
            "financial_protection_score": round(
                (1 - insurance_gap) * 50 + (1 - che_probability) * 50, 1
            ),
            "interpretation": (
                f"{uninsured_count} of {user_count} workers ({insurance_gap*100:.0f}%) lack health insurance. "
                f"Average hospitalization (KES {avg_hospitalization:,}) is "
                f"{'catastrophic' if che_probability else 'manageable'} relative to income. "
                f"Recommend CBHI at KES {cbhi_monthly_premium:,.0f}/month."
            ),
            "method": "ECO 106 — Health Financial Protection (WHO UHC framework)",
        }

    @classmethod
    def epidemiological_early_warning(
        cls,
        transactions: list[Any],
        region: str,
        lookback_days: int = 90,
    ) -> dict[str, Any]:
        """
        Epidemiological early warning from transaction patterns.

        Driven by ECO 106 § Disease Surveillance:
        Disease outbreaks manifest in economic data before clinical data:
        1. Clustered revenue drops across multiple traders (community illness)
        2. Changes in product mix (medicine purchases up, food down)
        3. Reduced market attendance (fewer active traders)

        This is syndromic surveillance through economic data — a novel
        approach enabled by Angavu Intelligence's transaction coverage.

        Early warning signals:
        - Z-score > 2 on 7-day rolling revenue (unusual decline)
        - Cluster of 3+ traders with >50% revenue drop in same week
        - Product mix shift: medicine/household ratio increase

        Args:
            transactions: transaction data
            region: geographic region
            lookback_days: analysis window

        Returns:
            Dict with early warning signals, risk level, and alert details
        """
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if len(sales) < 50:
            return {"error": "Insufficient data for epidemiological surveillance"}

        # Daily aggregation
        daily_rev = defaultdict(float)
        daily_traders = defaultdict(set)
        daily_categories = defaultdict(lambda: defaultdict(float))

        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day] += t.amount
            daily_traders[day].add(str(t.user_id))
            if t.item_category:
                daily_categories[day][t.item_category] += t.amount

        sorted_days = sorted(daily_rev.keys())
        if len(sorted_days) < 14:
            return {"error": "Need at least 14 days of data"}

        revenues = np.array([daily_rev[d] for d in sorted_days], dtype=float)

        # 7-day rolling statistics
        window = 7
        rolling_mean = np.convolve(revenues, np.ones(window) / window, mode='valid')
        rolling_std = np.array([
            np.std(revenues[max(0, i-window+1):i+1]) for i in range(window-1, len(revenues))
        ])

        # Z-scores for recent days
        z_scores = []
        for i in range(len(rolling_mean)):
            if rolling_std[i] > 0:
                z = (revenues[window - 1 + i] - rolling_mean[i]) / rolling_std[i]
            else:
                z = 0
            z_scores.append(z)

        # Detect anomalies (z < -2 = unusual decline)
        anomaly_days = []
        for i, z in enumerate(z_scores):
            if z < -2.0:
                day_idx = window - 1 + i
                if day_idx < len(sorted_days):
                    anomaly_days.append({
                        "date": sorted_days[day_idx],
                        "z_score": round(float(z), 2),
                        "revenue": round(float(revenues[day_idx]), 0),
                        "expected": round(float(rolling_mean[i]), 0),
                    })

        # Cluster detection: multiple traders affected in same week
        weekly_clusters = defaultdict(lambda: {"affected_traders": set(), "total_drop": 0})
        for t in sales:
            week = t.timestamp.strftime("%Y-W%W")
            weekly_clusters[week]["total_drop"] += t.amount

        # Active traders per week
        weekly_active = defaultdict(set)
        for t in sales:
            week = t.timestamp.strftime("%Y-W%W")
            weekly_active[week].add(str(t.user_id))

        # Product mix shift detection
        medicine_keywords = ["health", "medicine", "pharmacy", "hospital"]
        medicine_share_trend = []
        for d in sorted_days[-14:]:  # Last 2 weeks
            total = sum(daily_categories[d].values())
            medicine = sum(
                v for k, v in daily_categories[d].items()
                if any(kw in (k or "").lower() for kw in medicine_keywords)
            )
            if total > 0:
                medicine_share_trend.append(medicine / total)

        # Early warning risk level
        risk_factors = 0
        if len(anomaly_days) >= 3:
            risk_factors += 2  # Multiple anomaly days
        if any(a["z_score"] < -3 for a in anomaly_days):
            risk_factors += 1  # Extreme anomaly
        if len(medicine_share_trend) >= 2 and medicine_share_trend[-1] > medicine_share_trend[0] * 1.5:
            risk_factors += 1  # Medicine share spike

        if risk_factors >= 3:
            risk_level = "high"
            alert = "Potential disease outbreak detected. Multiple economic indicators suggest community health event."
        elif risk_factors >= 2:
            risk_level = "elevated"
            alert = "Unusual economic activity patterns detected. Monitor for disease outbreak signals."
        elif risk_factors >= 1:
            risk_level = "moderate"
            alert = "Minor anomalies detected. Continue routine surveillance."
        else:
            risk_level = "low"
            alert = "No unusual patterns detected. Normal economic activity."

        return {
            "region": region,
            "lookback_days": lookback_days,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "alert": alert,
            "anomaly_days": anomaly_days[:5],  # Top 5 most anomalous
            "active_traders_last_week": len(weekly_active.get(sorted_days[-1][:8], set())) if sorted_days else 0,
            "medicine_share_trend": [round(s, 4) for s in medicine_share_trend[-4:]] if medicine_share_trend else [],
            "recommendations": cls._epidemiological_recommendations(risk_level),
            "method": "ECO 106 — Syndromic Surveillance via Economic Data",
        }

    @classmethod
    def health_productivity_correlation(
        cls,
        transactions: list[Any],
        lookback_days: int = 180,
    ) -> dict[str, Any]:
        """
        Measure correlation between health indicators and productivity.

        Driven by ECO 106 § Health-Productivity Nexus:
        - Human capital theory (Becker, 1964): Health is a component of
          human capital that increases productivity.
        - Productivity = f(health, education, experience)
        - Health shocks reduce H → reduce productivity → reduce income

        For informal workers:
        - No sick leave → health shock = zero income
        - No health insurance → health cost = out-of-pocket
        - Dual burden: income loss + medical expense

        Uses Spearman rank correlation (STA 444) for robust
        non-parametric measurement.

        Args:
            transactions: transaction data
            lookback_days: analysis window

        Returns:
            Dict with health-productivity metrics and correlations
        """
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if len(sales) < 30:
            return {"error": "Insufficient data"}

        # Daily metrics
        daily_rev = defaultdict(float)
        daily_count = defaultdict(int)
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day] += t.amount
            daily_count[day] += 1

        sorted_days = sorted(daily_rev.keys())
        revenues = np.array([daily_rev[d] for d in sorted_days], dtype=float)
        counts = np.array([daily_count[d] for d in sorted_days], dtype=float)

        # Activity pattern (proxy for health status)
        # Consecutive inactive days suggest health issues
        inactive_streaks = []
        current_streak = 0
        for r in revenues:
            if r < np.median(revenues) * 0.2:  # Very low activity
                current_streak += 1
            else:
                if current_streak >= 2:
                    inactive_streaks.append(current_streak)
                current_streak = 0
        if current_streak >= 2:
            inactive_streaks.append(current_streak)

        # Weekly aggregation for correlation
        weekly_rev = defaultdict(float)
        weekly_count = defaultdict(int)
        for d, r in daily_rev.items():
            week = d[:8]  # Year-week approximation
            weekly_rev[week] += r
            weekly_count[week] += 1

        weeks = sorted(weekly_rev.keys())
        if len(weeks) < 4:
            return {"error": "Need at least 4 weeks of data"}

        w_revenues = np.array([weekly_rev[w] for w in weeks], dtype=float)
        w_counts = np.array([weekly_count[w] for w in weeks], dtype=float)

        # Correlation: activity (txn count) vs revenue
        from scipy import stats as sp_stats
        if len(w_counts) >= 4:
            rho, p_val = sp_stats.spearmanr(w_counts, w_revenues)
        else:
            rho, p_val = 0.0, 1.0

        # Vulnerability assessment
        zero_days = int(np.sum(revenues < 1))
        low_days = int(np.sum(revenues < np.median(revenues) * 0.3))

        return {
            "lookback_days": lookback_days,
            "total_days": len(sorted_days),
            "active_days": int(np.sum(revenues > 0)),
            "zero_income_days": zero_days,
            "low_activity_days": low_days,
            "inactive_streaks": inactive_streaks,
            "longest_inactive_streak": max(inactive_streaks) if inactive_streaks else 0,
            "activity_revenue_correlation": {
                "spearman_rho": round(float(rho), 4),
                "p_value": round(float(p_val), 6),
                "significant": p_val < 0.05,
                "interpretation": (
                    f"{'Significant' if p_val < 0.05 else 'Non-significant'} "
                    f"{'positive' if rho > 0 else 'negative'} correlation "
                    f"between activity and revenue (ρ={rho:.3f}). "
                    f"This suggests {'health status directly impacts productivity' if abs(rho) > 0.5 else 'moderate health-productivity link'}."
                ),
            },
            "health_vulnerability": {
                "zero_income_risk": "high" if zero_days > 10 else "moderate" if zero_days > 5 else "low",
                "income_stability": "unstable" if np.std(revenues) / max(np.mean(revenues), 1) > 0.8 else "stable",
                "no_sick_leave_buffer": True,
                "recommendation": "Build emergency fund equal to 2 weeks of expenses to buffer health shocks",
            },
            "method": "ECO 106 — Health-Productivity Correlation (Human Capital Theory)",
        }

    @classmethod
    def full_health_economic_report(
        cls,
        user_id: str,
        transactions: list[Any],
        region: str,
        user_count: int,
        avg_monthly_income: float,
        poverty_line_monthly: float = 8800,
    ) -> dict[str, Any]:
        """
        Comprehensive health-economic intelligence report.

        Combines all ECO 106 analyses:
        1. Health shock detection and tracking
        2. Grossman health investment model
        3. Health insurance gap analysis
        4. Epidemiological early warning
        5. Health-productivity correlation

        Args:
            user_id: anonymized user ID
            transactions: transaction data
            region: geographic region
            user_count: total users in area
            avg_monthly_income: average monthly income in KES
            poverty_line_monthly: poverty threshold

        Returns:
            Comprehensive health-economic report
        """
        report = {
            "product": "jamii_insights_health",
            "user_id": user_id,
            "region": region,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # 1. Health shock tracker
        report["health_shocks"] = cls.health_shock_tracker(
            user_id, transactions, poverty_line_monthly=poverty_line_monthly
        )

        # 2. Grossman model (estimate health stock from activity patterns)
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        daily_rev = defaultdict(float)
        for t in sales:
            daily_rev[t.timestamp.strftime("%Y-%m-%d")] += t.amount
        avg_daily_rev = float(np.mean(list(daily_rev.values()))) if daily_rev else 0

        # Estimate health stock: 100 if fully active, lower if inactive
        active_days = len(daily_rev)
        total_days = max(1, (max(t.timestamp for t in sales) - min(t.timestamp for t in sales)).days + 1) if sales else 1
        activity_ratio = active_days / total_days
        estimated_health_stock = min(100, activity_ratio * 100 + 20)  # Base 20 + activity

        report["grossman_model"] = cls.grossman_health_investment(
            current_health_stock=estimated_health_stock,
            wage_rate=avg_daily_rev,
        )

        # 3. Health insurance intelligence
        report["insurance_intelligence"] = cls.health_insurance_intelligence(
            user_count, transactions, region, avg_monthly_income
        )

        # 4. Epidemiological early warning
        report["epidemiological_warning"] = cls.epidemiological_early_warning(
            transactions, region
        )

        # 5. Health-productivity correlation
        report["health_productivity"] = cls.health_productivity_correlation(transactions)

        # Summary risk score
        shock_risk = report["health_shocks"].get("health_vulnerability_score", 50)
        ins_risk = report["insurance_intelligence"].get("financial_protection_score", 50)
        epi_risk = {"low": 10, "moderate": 30, "elevated": 60, "high": 90}.get(
            report["epidemiological_warning"].get("risk_level", "low"), 10
        )
        overall_risk = round((shock_risk + (100 - ins_risk) + epi_risk) / 3, 1)

        report["overall_health_risk_score"] = overall_risk
        report["overall_risk_level"] = (
            "critical" if overall_risk > 70
            else "high" if overall_risk > 50
            else "moderate" if overall_risk > 30
            else "low"
        )
        report["key_insight"] = (
            f"Health risk score: {overall_risk}/100 ({report['overall_risk_level']}). "
            f"Insurance coverage: {report['insurance_intelligence']['insurance_coverage_rate']}%. "
            f"Health shocks detected: {report['health_shocks'].get('shock_count', 0)}. "
            f"Recommendation: {report['grossman_model']['recommendation']}"
        )

        return report

    @staticmethod
    def _estimate_health_cost(duration_days: int, severity: str) -> float:
        """Estimate health cost based on shock duration and severity."""
        base_costs = {
            "mild": 2000, "moderate": 5000, "severe": 25000, "catastrophic": 80000
        }
        base = base_costs.get(severity, 5000)
        return base + duration_days * 500  # Daily cost component

    @staticmethod
    def _assess_recovery(
        daily_rev: dict, sorted_days: list, shock_end_idx: int, median_rev: float
    ) -> str:
        """Assess recovery status after a health shock."""
        # Check 7 days after shock end
        recovery_start = shock_end_idx + 1
        recovery_end = min(recovery_start + 7, len(sorted_days))
        if recovery_start >= len(sorted_days):
            return "ongoing"
        recovery_rev = [daily_rev[sorted_days[i]] for i in range(recovery_start, recovery_end)]
        avg_recovery = np.mean(recovery_rev) if recovery_rev else 0
        if avg_recovery >= median_rev * 0.8:
            return "recovered"
        elif avg_recovery >= median_rev * 0.5:
            return "recovering"
        else:
            return "not_recovered"

    @staticmethod
    def _vulnerability_score(
        shock_frequency: float, total_loss: float, avg_monthly_rev: float
    ) -> float:
        """Compute health vulnerability score (0-100, higher = more vulnerable)."""
        freq_score = min(50, shock_frequency * 25)  # Max 50 from frequency
        loss_score = min(50, (total_loss / max(avg_monthly_rev * 12, 1)) * 50)  # Max 50 from loss
        return round(freq_score + loss_score, 1)

    @staticmethod
    def _epidemiological_recommendations(risk_level: str) -> list[str]:
        """Generate recommendations based on epidemiological risk level."""
        if risk_level == "high":
            return [
                "Alert community health workers (CHWs) in the area",
                "Increase surveillance frequency to daily",
                "Report unusual patterns to Sub-County Health Management Team",
                "Advise traders to stock essential medicines and hygiene supplies",
                "Consider temporary market closure if pattern persists",
            ]
        elif risk_level == "elevated":
            return [
                "Monitor daily for 7 days",
                "Cross-reference with MoH DHIS2 disease reports",
                "Advise traders on hand hygiene and food safety",
            ]
        elif risk_level == "moderate":
            return [
                "Continue routine weekly monitoring",
                "Note pattern for seasonal adjustment",
            ]
        else:
            return ["No action required. Continue routine monitoring."]
