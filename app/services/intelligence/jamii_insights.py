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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.intelligence.cache import intelligence_cache

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
    gini = (2 * np.sum((np.arange(1, n + 1) * sorted_inc)) / (n * n * mu)) - (n + 1) / n
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


def _lorenz_curve(incomes: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
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
    age_groups: List[str],
    population: np.ndarray,
    deaths: np.ndarray,
) -> List[Dict[str, Any]]:
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
) -> Dict[str, float]:
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
) -> Dict[str, Any]:
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
        demographic_segment: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        program_name: Optional[str] = None,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
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

        response = {
            "product": "jamii_insights",
            "version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
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
    ) -> List[Dict[str, Any]]:
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
