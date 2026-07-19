"""
Tax Base Estimation — Government Revenue Service.

Estimated tax liability for informal businesses:
- VAT collection potential by sector/region
- Tax gap analysis
- Formalization tracking

Academic Foundation (Valentine's BSc Economics & Statistics):
- ECO 421: Public Finance and Fiscal Policy → Tax theory (Ramsey rule,
  optimal taxation), Laffer curve, tax incidence analysis, deadweight
  loss, fiscal decentralization, Mirrlees optimal income tax
- ECO 210: Introduction to Quantitative Methods → Estimation techniques,
  matrix algebra for tax models, optimisation under constraints
- STA 245: Social & Economic Statistics for National Planning → Official
  statistics methodology, revenue forecasting, fiscal indicators

Buyers: KRA, county governments
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
from app.services.research.hypothesis_testing import HypothesisTester
from app.services.statistical_foundation import (
    bootstrap,
    kde_estimator,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Kenya VAT rate
VAT_RATE = 0.16  # 16% standard VAT
VAT_THRESHOLD_KES = 5_000_000  # KES 5M annual turnover threshold

# Sector-specific tax assumptions
SECTOR_TAX_PROFILES = {
    "food": {"vat_applicable": 0.7, "income_tax_rate": 0.25, "compliance_rate": 0.15},
    "household": {"vat_applicable": 0.9, "income_tax_rate": 0.25, "compliance_rate": 0.20},
    "health": {"vat_applicable": 0.5, "income_tax_rate": 0.30, "compliance_rate": 0.25},
    "transport": {"vat_applicable": 0.8, "income_tax_rate": 0.25, "compliance_rate": 0.18},
    "clothing": {"vat_applicable": 0.9, "income_tax_rate": 0.25, "compliance_rate": 0.15},
    "electronics": {"vat_applicable": 0.95, "income_tax_rate": 0.30, "compliance_rate": 0.22},
    "beauty": {"vat_applicable": 0.8, "income_tax_rate": 0.25, "compliance_rate": 0.12},
    "agriculture": {"vat_applicable": 0.3, "income_tax_rate": 0.15, "compliance_rate": 0.10},
    "services": {"vat_applicable": 0.7, "income_tax_rate": 0.30, "compliance_rate": 0.20},
    "other": {"vat_applicable": 0.7, "income_tax_rate": 0.25, "compliance_rate": 0.15},
}


# ─────────────────────────────────────────────────────────────────────────────
# ECO 421 — Public Finance helpers
# ─────────────────────────────────────────────────────────────────────────────

def _laffer_curve_revenue(
    tax_rate: float, base_revenue: float, elasticity: float = 1.5
) -> float:
    """
    Laffer curve: revenue as a function of tax rate.

    Driven by ECO 421 § Taxation Theory — the Laffer curve shows that
    tax revenue is zero at both t=0% (no tax) and t=100% (no incentive
    to produce), with a maximum in between. The symmetric Laffer model:

    Revenue(t) = Base × t × (1 - t)^ε

    where ε captures the elasticity of the tax base to the tax rate.

    Args:
        tax_rate: tax rate in [0, 1]
        base_revenue: maximum possible revenue (at optimal rate)
        elasticity: elasticity of taxable income

    Returns:
        estimated revenue at this tax rate
    """
    if tax_rate <= 0 or tax_rate >= 1:
        return 0.0
    return round(float(base_revenue * tax_rate * (1 - tax_rate) ** elasticity), 0)


def _optimal_tax_rate(elasticity: float = 1.5) -> float:
    """
    Revenue-maximising tax rate from the Laffer curve.

    Driven by ECO 421 § Optimal Taxation — from the symmetric Laffer
    model R(t) = B·t·(1-t)^ε, the revenue-maximising rate is:

    t* = 1 / (1 + ε)

    For ε = 1.5, t* = 0.40 (40%).

    Args:
        elasticity: elasticity of taxable income

    Returns:
        optimal tax rate (0-1)
    """
    return round(1.0 / (1.0 + elasticity), 4)


def _ramsey_tax_rate(
    demand_elasticity: float, base_rate: float = 0.16
) -> float:
    """
    Ramsey (inverse elasticity) rule for optimal commodity taxation.

    Driven by ECO 421 § Taxation Theory — the Ramsey rule states that
    optimal tax rates should be inversely proportional to demand
    elasticities to minimise deadweight loss:

    tᵢ / tⱼ = εⱼ / εᵢ

    Inelastic goods (staples) get higher rates; elastic goods (luxuries)
    get lower rates. This is efficiency-optimal but regressive.

    Args:
        demand_elasticity: price elasticity of demand for the good
        base_rate: reference tax rate for unit-elastic good

    Returns:
        optimal tax rate for this good
    """
    if demand_elasticity <= 0:
        return base_rate
    # Inverse elasticity rule: t ∝ 1/ε
    return round(float(base_rate / max(demand_elasticity, 0.1)), 4)


def _deadweight_loss(
    tax_rate: float, elasticity: float, quantity: float, price: float
) -> float:
    """
    Deadweight loss from taxation.

    Driven by ECO 421 § Tax Incidence and Deadweight Loss:
    DWL ≈ ½ · t² · ε · Q₀ / P₀

    This is the Harberger triangle approximation.

    Args:
        tax_rate: ad valorem tax rate
        elasticity: price elasticity of demand
        quantity: pre-tax equilibrium quantity
        price: pre-tax equilibrium price

    Returns:
        estimated deadweight loss
    """
    return round(0.5 * tax_rate**2 * abs(elasticity) * quantity / max(price, 1), 0)


def _tax_incidence(
    supply_elasticity: float, demand_elasticity: float
) -> dict[str, float]:
    """
    Tax incidence: who bears the burden?

    Driven by ECO 421 § Tax Incidence:
    Consumer share = εˢ / (εˢ + |εᵈ|)
    Producer share = |εᵈ| / (εˢ + |εᵈ|)

    The more inelastic side bears more of the burden.

    Args:
        supply_elasticity: price elasticity of supply
        demand_elasticity: price elasticity of demand (negative)

    Returns:
        dict with consumer and producer shares
    """
    es = abs(supply_elasticity)
    ed = abs(demand_elasticity)
    total = es + ed
    if total == 0:
        return {"consumer_share": 0.5, "producer_share": 0.5}
    return {
        "consumer_share": round(es / total, 4),
        "producer_share": round(ed / total, 4),
        "interpretation": (
            "consumers_bear_more" if es > ed
            else "producers_bear_more" if ed > es
            else "equal_burden"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# STA 341 — Bootstrap Confidence Intervals
# ─────────────────────────────────────────────────────────────────────────────

def _bootstrap_ci(
    data: np.ndarray,
    statistic_fn,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Bootstrap confidence interval for any statistic.

    Driven by STA 341 § Interval Estimation — non-parametric bootstrap
    (Efron, 1979) for confidence intervals without distributional
    assumptions.

    Args:
        data: 1-D observations
        statistic_fn: function computing the statistic
        n_bootstrap: replicates
        confidence: CI level

    Returns:
        (point_estimate, ci_lower, ci_upper)
    """
    rng = np.random.default_rng(seed)
    point = float(statistic_fn(data))
    boot = np.empty(n_bootstrap)
    n = len(data)
    for i in range(n_bootstrap):
        boot[i] = statistic_fn(rng.choice(data, size=n, replace=True))
    alpha = 1 - confidence
    return (
        round(point, 2),
        round(float(np.percentile(boot, 100 * alpha / 2)), 2),
        round(float(np.percentile(boot, 100 * (1 - alpha / 2))), 2),
    )


class TaxBaseService:
    """
    Tax base estimation service for government buyers.

    Estimates tax liability and collection potential from
    informal economy transaction data.

    Statistical methods powered by Valentine's degree:
    - Laffer curve and optimal taxation (ECO 421)
    - Ramsey rule for commodity taxation (ECO 421)
    - Tax incidence and deadweight loss (ECO 421)
    - Bootstrap confidence intervals (STA 341)
    - Revenue forecasting (STA 245)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def estimate_tax_base(
        self,
        region: str,
        sector: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        buyer_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Estimate tax base for a region/sector.

        Args:
            region: County code or 'national'
            sector: Specific sector or None for all
            period_start: Analysis start (default: 12 months ago)
            period_end: Analysis end (default: today)
            buyer_id: Buyer requesting this data

        Returns:
            Tax base estimation dict or None if k-anonymity not met
        """
        cached = await intelligence_cache.get(
            "tax_base", region=region, sector=sector,
            start=str(period_start), end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=365)

        region_type = self._determine_region_type(region)

        # Get users in region
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
        user_count = len(users)

        if user_count < settings.K_ANONYMITY_THRESHOLD:
            logger.warning("tax_base_k_failed", region=region, users=user_count)
            return None

        user_ids = [u.id for u in users]

        # Get transactions
        txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
                Transaction.transaction_type == "SALE",
            )
        )
        if sector:
            txn_query = txn_query.where(Transaction.item_category == sector)

        result = await self.db.execute(txn_query)
        sales = result.scalars().all()

        if not sales:
            return None

        total_revenue = sum(t.amount for t in sales)
        months_in_period = max(1, (period_end - period_start).days / 30)

        # Sector breakdown
        sector_data = defaultdict(lambda: {"revenue": 0, "count": 0, "users": set()})
        for t in sales:
            cat = t.item_category or "other"
            sector_data[cat]["revenue"] += t.amount
            sector_data[cat]["count"] += 1
            sector_data[cat]["users"].add(t.user_id)

        # Estimate formalized businesses
        formalized = 0
        for u in users:
            user_sales = [t for t in sales if t.user_id == u.id]
            if user_sales:
                mpesa_pct = sum(1 for t in user_sales if t.payment_method == "mpesa") / len(user_sales)
                if mpesa_pct > 0.5:
                    formalized += 1

        annual_rev_per_business = total_revenue / max(user_count, 1) * (12 / months_in_period)

        vat_liable_count = sum(
            1 for u in users
            if sum(t.amount for t in sales if t.user_id == u.id) * (12 / months_in_period) > VAT_THRESHOLD_KES
        )

        # ── ECO 421: Sector-level tax estimates ─────────────────────────────
        sector_breakdown = []
        total_vat_base = 0
        total_vat_collectible = 0
        total_income_tax_base = 0

        for cat, data in sector_data.items():
            profile = SECTOR_TAX_PROFILES.get(cat, SECTOR_TAX_PROFILES["other"])
            annualized_rev = data["revenue"] * (12 / months_in_period)

            vat_base = annualized_rev * profile["vat_applicable"]
            vat_collectible = vat_base * VAT_RATE * profile["compliance_rate"]
            income_tax_base = annualized_rev * profile["income_tax_rate"] * profile["compliance_rate"]

            total_vat_base += vat_base
            total_vat_collectible += vat_collectible
            total_income_tax_base += income_tax_base

            # ECO 421: Ramsey-optimal tax rate for this sector
            # Use demand elasticity proxy from SECTOR_TAX_PROFILES
            demand_elasticity = 1.0 / max(profile["vat_applicable"], 0.1)
            ramsey_rate = _ramsey_tax_rate(demand_elasticity, base_rate=VAT_RATE)

            sector_breakdown.append({
                "sector": cat,
                "estimated_revenue_kes": round(annualized_rev, 2),
                "vat_base_kes": round(vat_base, 2),
                "vat_collectible_kes": round(vat_collectible, 2),
                "business_count": len(data["users"]),
                "compliance_rate": round(profile["compliance_rate"] * 100, 1),
                # ECO 421: Ramsey optimal rate
                "ramsey_optimal_rate": round(ramsey_rate * 100, 1),
            })

        sector_breakdown.sort(key=lambda x: x["estimated_revenue_kes"], reverse=True)

        # Tax gap
        total_potential_vat = total_vat_base * VAT_RATE
        tax_gap = total_potential_vat - total_vat_collectible

        overall_compliance = round(
            (total_vat_collectible + total_income_tax_base)
            / max(total_potential_vat + total_income_tax_base, 1) * 100, 1
        )

        # ── ECO 421: Laffer curve analysis ──────────────────────────────────
        annualized_total = total_revenue * (12 / months_in_period)
        optimal_rate = _optimal_tax_rate(elasticity=1.5)
        laffer_revenue_at_optimal = _laffer_curve_revenue(optimal_rate, annualized_total, elasticity=1.5)
        laffer_revenue_at_current = _laffer_curve_revenue(VAT_RATE, annualized_total, elasticity=1.5)

        laffer_analysis = {
            "current_rate_pct": round(VAT_RATE * 100, 1),
            "optimal_rate_pct": round(optimal_rate * 100, 1),
            "revenue_at_current_rate_kes": round(laffer_revenue_at_current, 0),
            "revenue_at_optimal_rate_kes": round(laffer_revenue_at_optimal, 0),
            "revenue_gain_from_optimization_kes": round(
                laffer_revenue_at_optimal - laffer_revenue_at_current, 0
            ),
            "elasticity_assumption": 1.5,
            "interpretation": (
                "current_rate_below_optimal" if optimal_rate > VAT_RATE
                else "current_rate_above_optimal"
            ),
        }

        # ── ECO 421: Tax incidence analysis ─────────────────────────────────
        # Assume: supply elasticity 0.3 (farmers/producers), demand elasticity 0.8
        incidence = _tax_incidence(supply_elasticity=0.3, demand_elasticity=0.8)

        # ── ECO 421: Deadweight loss ────────────────────────────────────────
        dwl = _deadweight_loss(
            VAT_RATE, elasticity=0.8,
            quantity=total_revenue / max(VAT_RATE * 100, 1),
            price=annualized_total / max(user_count, 1)
        )

        # ── STA 341: Bootstrap confidence intervals ─────────────────────────
        bootstrap_ci = {}
        if len(sales) >= 30:
            revenue_data = np.array([t.amount for t in sales], dtype=float)
            mean_val, mean_lo, mean_hi = _bootstrap_ci(revenue_data, np.mean, n_bootstrap=500)
            total_val, total_lo, total_hi = _bootstrap_ci(
                revenue_data, np.sum, n_bootstrap=500
            )
            bootstrap_ci = {
                "mean_transaction": {
                    "estimate": mean_val,
                    "ci_lower": mean_lo,
                    "ci_upper": mean_hi,
                    "confidence": 0.95,
                },
                "total_annualised_revenue": {
                    "estimate": round(total_val * 12 / months_in_period, 0),
                    "ci_lower": round(total_lo * 12 / months_in_period, 0),
                    "ci_upper": round(total_hi * 12 / months_in_period, 0),
                    "confidence": 0.95,
                },
                "n_bootstrap": 500,
                "method": "bootstrap_percentile",
            }

        # Growth comparison
        prev_start = period_start - timedelta(days=(period_end - period_start).days)
        prev_txn_query = select(Transaction).where(
            and_(
                Transaction.user_id.in_(user_ids),
                Transaction.timestamp >= datetime.combine(prev_start, datetime.min.time()),
                Transaction.timestamp < datetime.combine(period_start, datetime.min.time()),
                Transaction.transaction_type == "SALE",
            )
        )
        prev_result = await self.db.execute(prev_txn_query)
        prev_sales = prev_result.scalars().all()
        prev_revenue = sum(t.amount for t in prev_sales)

        revenue_growth = 0
        if prev_revenue > 0:
            annualized_current = total_revenue * (12 / months_in_period)
            annualized_prev = prev_revenue * (12 / months_in_period)
            revenue_growth = round(
                (annualized_current - annualized_prev) / annualized_prev * 100, 1
            )

        # Apply DP
        dp_total_rev = max(0, round(
            self.anonymizer.add_laplace_noise(
                total_revenue * (12 / months_in_period), sensitivity=100000
            ), 0
        ))
        dp_vat_collectible = max(0, round(
            self.anonymizer.add_laplace_noise(total_vat_collectible, sensitivity=50000), 0
        ))

        top_contributors = [
            {"sector": s["sector"], "contribution_pct": round(
                s["vat_collectible_kes"] / max(total_vat_collectible, 1) * 100, 1
            )}
            for s in sector_breakdown[:5]
        ]

        # Bootstrap-based CI (wider than fixed percentage)
        ci_lower = bootstrap_ci.get("total_annualised_revenue", {}).get(
            "ci_lower", round(dp_total_rev * 0.85, 0)
        )
        ci_upper = bootstrap_ci.get("total_annualised_revenue", {}).get(
            "ci_upper", round(dp_total_rev * 1.15, 0)
        )

        response = {
            "product": "tax_base_estimation",
            "version": "2.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "data_freshness": datetime.now(UTC).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, user_count / 100),
            "confidence_level": min(1.0, len(sales) / 100),
            "region": region,
            "region_type": region_type,
            "sector": sector,
            "time_period": f"{period_start} to {period_end}",
            "estimated_businesses": user_count,
            "active_businesses": user_count,
            "formalized_businesses": formalized,
            "formalization_gap_pct": round((1 - formalized / max(user_count, 1)) * 100, 1),
            "tax_estimates": {
                "estimated_total_revenue_kes": dp_total_rev,
                "estimated_vat_base_kes": round(total_vat_base, 0),
                "estimated_vat_collectible_kes": dp_vat_collectible,
                "estimated_income_tax_base_kes": round(total_income_tax_base, 0),
                "vat_effective_rate": round(
                    total_vat_collectible / max(total_vat_base, 1) * 100, 2
                ),
                "tax_gap_kes": round(tax_gap, 0),
                "tax_compliance_rate": overall_compliance,
            },
            # ECO 421: Public Finance analysis
            "laffer_curve_analysis": laffer_analysis,
            "tax_incidence": incidence,
            "deadweight_loss_kes": dwl,
            "sector_breakdown": sector_breakdown,
            "top_tax_contributors": top_contributors,
            "revenue_growth_pct": revenue_growth if revenue_growth != 0 else None,
            "tax_base_growth_pct": revenue_growth if revenue_growth != 0 else None,
            "new_registrations_est": None,
            "vs_previous_period_pct": revenue_growth if revenue_growth != 0 else None,
            "county_rank": None,
            # STA 341: Bootstrap confidence intervals
            "bootstrap_estimates": bootstrap_ci if bootstrap_ci else None,
            # STA 444: Non-parametric analysis
            "nonparametric_analysis": self._run_nonparametric_analysis(
                sales, sector_breakdown, user_count,
            ),
            "users_included": user_count,
            "confidence_interval": {"lower": ci_lower, "upper": ci_upper},
        }

        await intelligence_cache.set(
            "tax_base", response,
            region=region, sector=sector,
            start=str(period_start), end=str(period_end),
        )

        logger.info("tax_base_estimated", region=region, businesses=user_count, revenue=dp_total_rev)
        return response

    @staticmethod
    def _run_nonparametric_analysis(
        sales: list,
        sector_breakdown: list,
        user_count: int,
    ) -> dict[str, Any] | None:
        """
        Run non-parametric statistical analysis (STA 444).

        Applies KDE for tax compliance distribution, comprehensive
        bootstrap CIs, and Kruskal-Wallis for cross-sector comparison.
        Essential for informal economy data which is skewed and
        outlier-heavy.
        """
        if len(sales) < 20:
            return None

        result: dict[str, Any] = {}

        # ── STA 444: KDE for tax compliance distribution ───────────────────
        try:
            # Per-business revenue as compliance proxy
            business_revenues: dict[str, float] = defaultdict(float)
            for t in sales:
                business_revenues[str(t.user_id)] += t.amount
            rev_arr = np.array(list(business_revenues.values()), dtype=float)
            rev_arr = rev_arr[rev_arr > 0]
            if len(rev_arr) >= 10:
                grid, density = kde_estimator.gaussian_kde(rev_arr)
                mode_idx = int(np.argmax(density))
                result["kde_compliance_distribution"] = {
                    "description": "Non-parametric business revenue density (compliance proxy)",
                    "mode_revenue": round(float(grid[mode_idx]), 2),
                    "bandwidth": round(float(
                        0.9 * min(
                            np.std(rev_arr),
                            (np.percentile(rev_arr, 75) - np.percentile(rev_arr, 25)) / 1.34,
                        ) * len(rev_arr) ** (-0.2)
                    ), 4),
                    "n_businesses": len(rev_arr),
                    "multimodality": kde_estimator.detect_multimodality(rev_arr),
                    "interpretation": "Multimodal revenue distribution suggests distinct compliance tiers",
                    "method": "STA 444 — Kernel Density Estimation",
                }
        except Exception as e:
            logger.debug("kde_compliance_distribution_failed", error=str(e))

        # ── STA 444: Kruskal-Wallis — compare tax compliance across sectors ──
        if len(sector_breakdown) >= 3:
            try:
                sector_revenues: dict[str, list] = defaultdict(list)
                for t in sales:
                    cat = t.item_category or "other"
                    sector_revenues[cat].append(float(t.amount))

                valid_groups = [
                    v for v in sector_revenues.values() if len(v) >= 5
                ]
                if len(valid_groups) >= 3:
                    tester = HypothesisTester(alpha=0.05)
                    kw_result = tester.kruskal_wallis(valid_groups)
                    result["kruskal_wallis_sector_compliance"] = {
                        "test": "Kruskal-Wallis H",
                        "null_hypothesis": "All sectors have the same revenue distribution",
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
                logger.debug("kruskal_wallis_sector_compliance_failed", error=str(e))

        # ── STA 444: Comprehensive Bootstrap CI on tax estimates ────────────
        try:
            rev_arr = np.array([t.amount for t in sales], dtype=float)
            if len(rev_arr) >= 30:
                # Bootstrap CI on mean transaction
                boot_mean = bootstrap.percentile_ci(
                    rev_arr, np.mean, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on total revenue
                boot_total = bootstrap.percentile_ci(
                    rev_arr, np.sum, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on median transaction
                boot_median = bootstrap.percentile_ci(
                    rev_arr, np.median, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on revenue per business
                business_revs = defaultdict(float)
                for t in sales:
                    business_revs[str(t.user_id)] += t.amount
                per_biz = np.array(list(business_revs.values()), dtype=float)
                per_biz = per_biz[per_biz > 0]
                boot_per_biz = bootstrap.percentile_ci(
                    per_biz, np.mean, n_bootstrap=5000, confidence=0.95,
                ) if len(per_biz) >= 10 else None

                result["bootstrap_comprehensive_ci"] = {
                    "mean_transaction": {
                        "estimate": boot_mean["estimate"],
                        "ci_lower": boot_mean["ci_lower"],
                        "ci_upper": boot_mean["ci_upper"],
                        "bootstrap_se": boot_mean["bootstrap_se"],
                    },
                    "total_revenue": {
                        "estimate": boot_total["estimate"],
                        "ci_lower": boot_total["ci_lower"],
                        "ci_upper": boot_total["ci_upper"],
                        "bootstrap_se": boot_total["bootstrap_se"],
                    },
                    "median_transaction": {
                        "estimate": boot_median["estimate"],
                        "ci_lower": boot_median["ci_lower"],
                        "ci_upper": boot_median["ci_upper"],
                        "bootstrap_se": boot_median["bootstrap_se"],
                    },
                    "revenue_per_business": ({
                        "estimate": boot_per_biz["estimate"],
                        "ci_lower": boot_per_biz["ci_lower"],
                        "ci_upper": boot_per_biz["ci_upper"],
                        "bootstrap_se": boot_per_biz["bootstrap_se"],
                    } if boot_per_biz else None),
                    "confidence": 0.95,
                    "n_bootstrap": 5000,
                    "method": "STA 444 — Bootstrap percentile CI (distribution-free)",
                }
        except Exception as e:
            logger.debug("bootstrap_comprehensive_ci_failed", error=str(e))

        return result if result else None

    @staticmethod
    def _determine_region_type(region: str) -> str:
        if region == "national":
            return "national"
        elif len(region) <= 3:
            return "county"
        elif len(region) <= 5:
            return "sub_county"
        else:
            return "ward"
