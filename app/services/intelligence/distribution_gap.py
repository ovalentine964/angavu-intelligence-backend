"""
Distribution Gap Analysis — FMCG Market Coverage Service.

Identifies where products are NOT reaching:
- Underserved market identification
- Coverage and penetration analysis
- Expansion recommendations with ROI

Academic Foundation (Valentine's BSc Economics & Statistics):
- ECO 422: Economics of Industry → Market structure analysis (HHI,
  concentration ratios), barriers to entry (structural, strategic,
  legal), contestable markets (Baumol), two-sided markets
- ECO 210: Introduction to Quantitative Methods → Gap analysis methods,
  linear programming for resource allocation, optimisation under
  constraints, matrix operations for market modelling
- STA 346: Statistical Quality Control → Process control charts
  (Shewhart, CUSUM), acceptance sampling, capability indices (Cp, Cpk),
  control limits for monitoring distribution performance

Buyers: FMCG distribution companies
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
from app.services.research.confidence_intervals import BootstrapCI
from app.services.research.hypothesis_testing import HypothesisTester
from app.services.statistical_foundation import (
    BootstrapInference,
    KernelDensityEstimator,
    bootstrap,
    kde_estimator,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# ECO 422 — Market Structure Analysis helpers
# ─────────────────────────────────────────────────────────────────────────────

def _herfindahl_hirschman_index(market_shares: np.ndarray) -> float:
    """
    Herfindahl-Hirschman Index: HHI = Σsᵢ².

    Driven by ECO 422 § Market Structure — HHI measures market
    concentration:
    - HHI < 0.01: highly competitive (atomistic)
    - HHI 0.01-0.15: unconcentrated
    - HHI 0.15-0.25: moderately concentrated
    - HHI > 0.25: highly concentrated

    Shares must be fractions (0-1), not percentages.

    Args:
        market_shares: array of market share fractions

    Returns:
        HHI value (0-1, or 0-10000 if shares are percentages)
    """
    return round(float(np.sum(market_shares ** 2)), 4)


def _concentration_ratio(market_shares: np.ndarray, n: int = 4) -> float:
    """
    Concentration ratio: CRₙ = Σ(top n firms' shares).

    Driven by ECO 422 § Market Structure — simple measure of how
    much of the market is controlled by the largest n firms.
    CR₄ > 0.8 suggests oligopoly.

    Args:
        market_shares: sorted descending array of market share fractions
        n: number of top firms to include

    Returns:
        concentration ratio (0-1)
    """
    sorted_shares = np.sort(market_shares)[::-1]
    return round(float(np.sum(sorted_shares[:n])), 4)


def _identify_barriers_to_entry(
    vendor_count: int,
    avg_startup_cost: float,
    network_effect_strength: float,
    regulatory_complexity: float,
) -> Dict[str, Any]:
    """
    Identify and classify barriers to entry.

    Driven by ECO 422 § Barriers to Entry:
    1. Structural: economies of scale, network effects, capital requirements
    2. Strategic: limit pricing, predatory pricing, excess capacity
    3. Legal: patents, licenses, regulations

    Each barrier scored 0-100 (100 = insurmountable).

    Args:
        vendor_count: number of vendors in the market
        avg_startup_cost: average capital needed to enter
        network_effect_strength: 0-100 (how much value increases with users)
        regulatory_complexity: 0-100 (license/permit difficulty)

    Returns:
        dict with barrier scores and overall entry difficulty
    """
    # Capital barrier
    capital_barrier = min(100, avg_startup_cost / 1000)  # Normalise

    # Scale economies barrier
    if vendor_count > 100:
        scale_barrier = 10  # Many small firms → easy entry
    elif vendor_count > 20:
        scale_barrier = 40
    elif vendor_count > 5:
        scale_barrier = 70
    else:
        scale_barrier = 90  # Few firms → hard to enter

    # Competition barrier (inverse of market friendliness)
    competition_barrier = min(100, max(0, 100 - vendor_count))

    overall = np.mean([
        capital_barrier, scale_barrier,
        network_effect_strength, regulatory_complexity,
        competition_barrier,
    ])

    return {
        "capital_requirement": round(capital_barrier, 1),
        "economies_of_scale": round(scale_barrier, 1),
        "network_effects": round(network_effect_strength, 1),
        "regulatory": round(regulatory_complexity, 1),
        "competition_intensity": round(competition_barrier, 1),
        "overall_entry_difficulty": round(float(overall), 1),
        "classification": (
            "low" if overall < 30
            else "moderate" if overall < 60
            else "high"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# STA 346 — Statistical Quality Control helpers
# ─────────────────────────────────────────────────────────────────────────────

def _control_chart_limits(
    data: np.ndarray, sigma: float = 3.0
) -> Dict[str, float]:
    """
    Shewhart control chart: compute UCL, CL, LCL.

    Driven by STA 346 § Statistical Quality Control — X-bar chart
    for monitoring distribution performance over time:
    - Centre Line (CL) = μ (process mean)
    - Upper Control Limit (UCL) = μ + 3σ
    - Lower Control Limit (LCL) = μ - 3σ
    - Points outside limits signal "out of control"

    Applied to distribution coverage: monitor each market's
    penetration over time and flag when coverage drops below
    expected levels.

    Args:
        data: time series of the metric being monitored
        sigma: number of standard deviations for control limits

    Returns:
        dict with UCL, CL, LCL, and whether latest observation is in control
    """
    if len(data) < 3:
        return {"ucl": None, "cl": None, "lcl": None, "in_control": True}

    mu = float(np.mean(data))
    std = float(np.std(data))

    ucl = mu + sigma * std
    lcl = mu - sigma * std
    latest = float(data[-1])

    return {
        "ucl": round(ucl, 2),
        "cl": round(mu, 2),
        "lcl": round(max(0, lcl), 2),
        "latest_value": round(latest, 2),
        "in_control": lcl <= latest <= ucl,
        "signal": "out_of_control_low" if latest < lcl else "out_of_control_high" if latest > ucl else "in_control",
    }


def _cusum_detect_shift(
    data: np.ndarray, target: float, threshold: float = 5.0, drift: float = 0.5
) -> Dict[str, Any]:
    """
    CUSUM (Cumulative Sum) control chart for detecting sustained shifts.

    Driven by STA 346 § Statistical Quality Control — CUSUM detects
    small, persistent shifts in the process mean that Shewhart charts
    miss. Accumulates deviations from target:
    Sₕ = max(0, Sₕ₋₁ + (xᵢ - target) - k)
    where k = allowance (drift parameter).

    Args:
        data: time series of the metric
        target: target value
        threshold: decision interval (detects shift when CUSUM exceeds this)
        drift: allowance parameter (typically 0.5σ)

    Returns:
        dict with CUSUM analysis
    """
    n = len(data)
    if n < 3:
        return {"shift_detected": False, "shift_magnitude": 0}

    s_pos = 0.0
    s_neg = 0.0
    shift_detected = False
    shift_point = None

    for i, x in enumerate(data):
        s_pos = max(0, s_pos + (x - target) - drift)
        s_neg = max(0, s_neg - (x - target) - drift)
        if s_pos > threshold or s_neg > threshold:
            shift_detected = True
            shift_point = i
            break

    return {
        "shift_detected": shift_detected,
        "shift_point": shift_point,
        "cusum_positive": round(float(s_pos), 2),
        "cusum_negative": round(float(s_neg), 2),
        "target": round(target, 2),
        "threshold": threshold,
    }


def _process_capability_index(
    data: np.ndarray, lsl: float, usl: float
) -> Dict[str, float]:
    """
    Process capability indices Cp and Cpk.

    Driven by STA 346 § Statistical Quality Control — measures how
    well a process fits within specification limits:
    - Cp = (USL - LSL) / 6σ — potential capability (centred)
    - Cpk = min((USL - μ)/3σ, (μ - LSL)/3σ) — actual capability

    For distribution: USL = maximum target penetration, LSL = minimum
    acceptable penetration. Cp/Cpk > 1.33 = capable process.

    Args:
        data: observed values
        lsl: lower specification limit
        usl: upper specification limit

    Returns:
        dict with Cp, Cpk, and interpretation
    """
    mu = float(np.mean(data))
    sigma = float(np.std(data))
    if sigma == 0:
        return {"cp": float("inf"), "cpk": float("inf"), "capable": True}

    cp = (usl - lsl) / (6 * sigma)
    cpk = min((usl - mu) / (3 * sigma), (mu - lsl) / (3 * sigma))

    return {
        "cp": round(float(cp), 3),
        "cpk": round(float(cpk), 3),
        "process_mean": round(mu, 2),
        "process_std": round(sigma, 2),
        "capable": cpk >= 1.33,
        "interpretation": (
            "highly_capable" if cpk >= 2.0
            else "capable" if cpk >= 1.33
            else "marginally_capable" if cpk >= 1.0
            else "not_capable"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ECO 210 — Linear Programming helpers
# ─────────────────────────────────────────────────────────────────────────────

def _optimise_expansion_allocation(
    market_potentials: np.ndarray,
    budget: float,
    cost_per_market: float,
) -> Dict[str, Any]:
    """
    Optimally allocate expansion budget across gap markets.

    Driven by ECO 210 § Linear Programming — a simple knapsack/
    allocation problem:
    Maximise Σ potential[i] · x[i]
    subject to Σ cost[i] · x[i] ≤ budget, 0 ≤ x[i] ≤ 1

    Greedy heuristic: rank markets by ROI (potential / cost)
    and allocate until budget exhausted.

    Args:
        market_potentials: array of revenue potential per market
        budget: total expansion budget
        cost_per_market: cost to enter each market

    Returns:
        dict with recommended allocation
    """
    n = len(market_potentials)
    if n == 0 or cost_per_market <= 0:
        return {"markets_to_enter": [], "total_investment": 0, "expected_return": 0}

    # ROI per market
    roi = market_potentials / cost_per_market
    ranked = np.argsort(roi)[::-1]

    allocated = []
    remaining = budget
    total_return = 0

    for idx in ranked:
        if remaining >= cost_per_market:
            allocated.append(int(idx))
            remaining -= cost_per_market
            total_return += market_potentials[idx]

    return {
        "markets_to_enter": allocated,
        "n_markets": len(allocated),
        "total_investment": round(float(len(allocated) * cost_per_market), 0),
        "expected_return": round(float(total_return), 0),
        "roi_pct": round(float((total_return - len(allocated) * cost_per_market) / max(len(allocated) * cost_per_market, 1) * 100), 1),
        "remaining_budget": round(float(remaining), 0),
    }


class DistributionGapService:
    """
    Distribution gap analysis service for FMCG buyers.

    Identifies markets where products are not reaching
    and estimates revenue potential of gap markets.

    Statistical methods powered by Valentine's degree:
    - HHI and concentration ratios (ECO 422)
    - Barriers to entry analysis (ECO 422)
    - Control charts and CUSUM (STA 346)
    - Process capability indices (STA 346)
    - Optimisation for expansion allocation (ECO 210)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)

    async def analyze_gaps(
        self,
        product_category: str,
        product_name: Optional[str] = None,
        region: Optional[str] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze distribution gaps for a product category.

        Args:
            product_category: Category to analyze
            product_name: Specific product or None for category
            region: Geographic region or None for national
            period_start: Analysis start (default: 90 days ago)
            period_end: Analysis end (default: today)
            buyer_id: Buyer requesting this data

        Returns:
            Gap analysis dict or None if insufficient data
        """
        cached = await intelligence_cache.get(
            "distribution_gap",
            category=product_category,
            product=product_name,
            region=region,
            start=str(period_start),
            end=str(period_end),
        )
        if cached:
            return cached

        if not period_end:
            period_end = date.today()
        if not period_start:
            period_start = period_end - timedelta(days=90)

        # Get all markets
        market_query = (
            select(
                User.location_geohash,
                func.count(User.id).label("user_count"),
            )
            .where(
                and_(
                    User.is_active == True,
                    User.consent_data_sharing == True,
                    User.location_geohash.isnot(None),
                )
            )
            .group_by(User.location_geohash)
        )
        if region:
            market_query = market_query.where(
                User.location_geohash.like(f"{region}%")
            )

        result = await self.db.execute(market_query)
        all_markets = result.all()

        if not all_markets:
            return None

        # Get markets that have the product
        product_query = select(Transaction).where(
            and_(
                Transaction.transaction_type == "SALE",
                Transaction.item_category == product_category,
                Transaction.timestamp >= datetime.combine(period_start, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        if product_name:
            product_query = product_query.where(Transaction.item == product_name)

        result = await self.db.execute(product_query)
        product_txns = result.scalars().all()

        # Group by market
        markets_with_product = set()
        market_data = defaultdict(lambda: {
            "volume": 0, "revenue": 0, "vendors": set(), "txns": 0
        })
        for t in product_txns:
            user_query = select(User.location_geohash).where(User.id == t.user_id)
            user_result = await self.db.execute(user_query)
            loc = user_result.scalar()
            if loc:
                market = loc[:5]
                markets_with_product.add(market)
                market_data[market]["volume"] += t.quantity or 0
                market_data[market]["revenue"] += t.amount
                market_data[market]["vendors"].add(t.user_id)
                market_data[market]["txns"] += 1

        # Identify gap markets
        all_market_codes = set(m[0][:5] for m in all_markets if m[0])
        gap_markets = all_market_codes - markets_with_product

        market_user_counts = {}
        for m in all_markets:
            code = m[0][:5]
            market_user_counts[code] = market_user_counts.get(code, 0) + m[1]

        valid_gap_markets = [
            m for m in gap_markets
            if market_user_counts.get(m, 0) >= settings.K_ANONYMITY_THRESHOLD
        ]

        total_markets = len(all_market_codes)
        covered_markets = len(markets_with_product)
        coverage_pct = round(covered_markets / max(total_markets, 1) * 100, 1)

        # ── ECO 422: Market Structure Analysis ──────────────────────────────
        # Compute market shares within covered markets
        market_shares = []
        total_covered_revenue = sum(d["revenue"] for d in market_data.values())
        if total_covered_revenue > 0:
            market_shares = np.array([
                d["revenue"] / total_covered_revenue
                for d in market_data.values()
            ])
        else:
            market_shares = np.array([1.0 / max(len(market_data), 1)] * len(market_data))

        hhi = _herfindahl_hirschman_index(market_shares) if len(market_shares) > 0 else 0
        cr4 = _concentration_ratio(market_shares, n=4) if len(market_shares) >= 4 else 0

        market_structure = {
            "hhi": hhi,
            "concentration_ratio_cr4": cr4,
            "n_active_markets": covered_markets,
            "structure": (
                "highly_competitive" if hhi < 0.01
                else "competitive" if hhi < 0.15
                else "moderately_concentrated" if hhi < 0.25
                else "concentrated"
            ),
        }

        # Barriers to entry
        barriers = _identify_barriers_to_entry(
            vendor_count=covered_markets,
            avg_startup_cost=500_000,  # KES
            network_effect_strength=20,  # Low for physical goods
            regulatory_complexity=30,
        )

        # Estimate revenue potential for gap markets
        avg_revenue_per_market = 0
        if market_data:
            avg_revenue_per_market = np.mean([
                d["revenue"] for d in market_data.values()
            ])

        gap_revenue_potential = round(avg_revenue_per_market * len(valid_gap_markets), 0)

        # Demand index for gap markets
        gap_demand = {}
        for m in valid_gap_markets[:20]:
            user_count = market_user_counts.get(m, 0)
            demand_index = min(100, round(user_count / 10, 1))
            gap_demand[m] = {
                "market_id": m,
                "user_count": user_count,
                "demand_index": demand_index,
                "revenue_potential_kes": round(avg_revenue_per_market * (demand_index / 50), 0),
            }

        sorted_gaps = sorted(
            gap_demand.values(),
            key=lambda x: x["demand_index"],
            reverse=True,
        )

        priority_gaps = [
            {
                "market_id": g["market_id"],
                "market_name": f"Market {g['market_id']}",
                "region": region or "national",
                "population_estimate": g["user_count"] * 50,
                "demand_index": g["demand_index"],
                "revenue_potential_kes": g["revenue_potential_kes"],
                "competitor_presence": "unknown",
                "priority_rank": i + 1,
                "recommended_action": "high_potential" if g["demand_index"] > 60 else "monitor",
            }
            for i, g in enumerate(sorted_gaps[:10])
        ]

        # Underserved regions
        underserved = []
        for m, d in market_data.items():
            if d["txns"] > 0 and len(d["vendors"]) < 3:
                underserved.append({
                    "market_id": m,
                    "vendor_count": len(d["vendors"]),
                    "transaction_count": d["txns"],
                    "issue": "low_vendor_density",
                })

        # Distribution density
        if market_data:
            densities = [
                d["volume"] / max(len(d["vendors"]), 1)
                for d in market_data.values()
            ]
            avg_density = round(float(np.mean(densities)), 2)
        else:
            avg_density = 0

        total_vendors = sum(
            len(d["vendors"]) for d in market_data.values()
        )
        potential_vendors = total_markets * 5
        penetration = round(total_vendors / max(potential_vendors, 1) * 100, 1)

        # ── STA 346: Control chart for coverage ─────────────────────────────
        # Simulate time series of coverage (in production, would track over time)
        # For now, use monthly coverage data if available
        monthly_coverage = []
        for m_str in sorted(monthly.keys()) if 'monthly' in dir() else []:
            pass
        # Use transaction density as proxy
        if market_data and len(market_data) >= 3:
            density_values = np.array([
                d["txns"] for d in market_data.values()
            ], dtype=float)
            coverage_control = _control_chart_limits(density_values)
        else:
            coverage_control = None

        # ── ECO 210: Optimise expansion allocation ──────────────────────────
        investment = len(valid_gap_markets) * 500_000
        if sorted_gaps:
            potentials = np.array([g["revenue_potential_kes"] for g in sorted_gaps], dtype=float)
            allocation = _optimise_expansion_allocation(
                potentials, budget=investment, cost_per_market=500_000
            )
        else:
            allocation = {
                "markets_to_enter": [], "n_markets": 0,
                "total_investment": 0, "expected_return": 0,
                "roi_pct": 0, "remaining_budget": 0,
            }

        annual_return = gap_revenue_potential
        roi = round((annual_return - investment) / max(investment, 1) * 100, 1)

        competitor_presence = {
            "total_markets": total_markets,
            "markets_with_competitors": covered_markets,
            "our_coverage_pct": coverage_pct,
        }

        dp_gap_revenue = max(0, round(
            self.anonymizer.add_laplace_noise(gap_revenue_potential, sensitivity=100000), 0
        ))

        response = {
            "product": "distribution_gap",
            "version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, total_vendors / 50),
            "confidence_level": min(1.0, len(product_txns) / 100),
            "product_category": product_category,
            "product_name": product_name or "all",
            "region": region or "national",
            "time_period": f"{period_start} to {period_end}",
            "coverage": {
                "total_markets_surveyed": total_markets,
                "markets_with_product": covered_markets,
                "markets_without_product": len(valid_gap_markets),
                "coverage_pct": coverage_pct,
                "penetration_rate": penetration,
            },
            # ECO 422: Market structure analysis
            "market_structure": market_structure,
            "barriers_to_entry": barriers,
            # STA 346: Quality control
            "coverage_control_chart": coverage_control,
            "gap_markets": priority_gaps,
            "gap_market_population": sum(
                g.get("population_estimate", 0) for g in priority_gaps
            ),
            "gap_revenue_potential_kes": dp_gap_revenue,
            "demand_without_supply": round(
                np.mean([g["demand_index"] for g in sorted_gaps]) if sorted_gaps else 0, 1
            ),
            "underserved_regions": underserved[:10],
            "underserved_demographics": [],
            "competitor_presence": competitor_presence,
            "competitive_gap_pct": round(100 - coverage_pct, 1),
            "market_share_estimate": None,
            "avg_distribution_cost_per_unit": None,
            "distribution_density": avg_density,
            # STA 444: Non-parametric analysis
            "nonparametric_analysis": self._run_nonparametric_analysis(
                market_data, valid_gap_markets, product_txns, gap_revenue_potential,
            ),
            # ECO 210: Optimised expansion allocation
            "expansion_optimisation": allocation,
            "recommended_expansion_markets": [
                {"market_id": g["market_id"], "priority": g["priority_rank"]}
                for g in priority_gaps[:5]
            ],
            "estimated_roi_pct": roi,
            "investment_required_kes": investment,
            "users_included": total_vendors,
            "report_type": "one_time",
        }

        await intelligence_cache.set(
            "distribution_gap", response,
            category=product_category, product=product_name,
            region=region, start=str(period_start), end=str(period_end),
        )

        logger.info(
            "distribution_gap_analyzed",
            category=product_category,
            coverage=coverage_pct,
            gaps=len(valid_gap_markets),
        )
        return response

    @staticmethod
    def _run_nonparametric_analysis(
        market_data: dict,
        valid_gap_markets: list,
        product_txns: list,
        gap_revenue_potential: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Run non-parametric statistical analysis (STA 444).

        Applies KDE for market coverage distribution, Mann-Whitney for
        served vs underserved markets, and bootstrap CI on gap estimates.
        Essential for informal economy data which is skewed and
        heteroscedastic.
        """
        if not market_data or len(market_data) < 5:
            return None

        result: Dict[str, Any] = {}

        # ── STA 444: KDE for market coverage distribution ──────────────────
        try:
            densities = np.array([
                d["txns"] for d in market_data.values()
            ], dtype=float)
            densities = densities[densities > 0]
            if len(densities) >= 5:
                grid, density = kde_estimator.gaussian_kde(densities)
                mode_idx = int(np.argmax(density))
                result["kde_market_coverage"] = {
                    "description": "Non-parametric market transaction density",
                    "mode_transactions": round(float(grid[mode_idx]), 2),
                    "bandwidth": round(float(
                        0.9 * min(
                            np.std(densities),
                            (np.percentile(densities, 75) - np.percentile(densities, 25)) / 1.34,
                        ) * len(densities) ** (-0.2)
                    ), 4),
                    "n_markets": len(densities),
                    "multimodality": kde_estimator.detect_multimodality(densities),
                    "method": "STA 444 — Kernel Density Estimation",
                }
        except Exception as e:
            logger.debug("kde_market_coverage_failed", error=str(e))

        # ── STA 444: Mann-Whitney — served vs underserved markets ───────────
        try:
            served_volumes = []
            underserved_volumes = []
            for m, d in market_data.items():
                vol = float(d["revenue"])
                if len(d["vendors"]) >= 3:
                    served_volumes.append(vol)
                else:
                    underserved_volumes.append(vol)

            served_arr = np.array(served_volumes, dtype=float)
            underserved_arr = np.array(underserved_volumes, dtype=float)

            if len(served_arr) >= 5 and len(underserved_arr) >= 5:
                tester = HypothesisTester(alpha=0.05)
                mw_result = tester.mann_whitney_u(
                    served_arr.tolist(), underserved_arr.tolist()
                )
                result["mann_whitney_served_vs_underserved"] = {
                    "test": "Mann-Whitney U",
                    "null_hypothesis": "Revenue distributions are the same for served and underserved markets",
                    "test_statistic": round(mw_result.test_statistic, 4),
                    "p_value": round(mw_result.p_value, 6),
                    "significant": mw_result.reject_null,
                    "effect_size": round(mw_result.effect_size or 0, 4),
                    "served_median_revenue": round(float(np.median(served_arr)), 2),
                    "underserved_median_revenue": round(float(np.median(underserved_arr)), 2),
                    "n_served": len(served_arr),
                    "n_underserved": len(underserved_arr),
                    "interpretation": mw_result.interpretation,
                    "method": "STA 444 — Non-parametric two-sample test (no normality assumption)",
                }
        except Exception as e:
            logger.debug("mann_whitney_served_vs_underserved_failed", error=str(e))

        # ── STA 444: Bootstrap CI on gap estimates ─────────────────────────
        try:
            rev_values = np.array([
                d["revenue"] for d in market_data.values()
            ], dtype=float)
            rev_values = rev_values[rev_values > 0]
            if len(rev_values) >= 10:
                # Bootstrap CI on mean market revenue
                boot_mean = bootstrap.percentile_ci(
                    rev_values, np.mean, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on total gap revenue potential
                def _gap_estimate(data):
                    avg = float(np.mean(data))
                    return avg * len(valid_gap_markets)

                boot_gap = bootstrap.percentile_ci(
                    rev_values, _gap_estimate, n_bootstrap=5000, confidence=0.95,
                )
                # Bootstrap CI on median market revenue
                boot_median = bootstrap.percentile_ci(
                    rev_values, np.median, n_bootstrap=5000, confidence=0.95,
                )
                result["bootstrap_gap_ci"] = {
                    "mean_market_revenue": {
                        "estimate": boot_mean["estimate"],
                        "ci_lower": boot_mean["ci_lower"],
                        "ci_upper": boot_mean["ci_upper"],
                        "bootstrap_se": boot_mean["bootstrap_se"],
                    },
                    "total_gap_revenue": {
                        "estimate": boot_gap["estimate"],
                        "ci_lower": boot_gap["ci_lower"],
                        "ci_upper": boot_gap["ci_upper"],
                        "bootstrap_se": boot_gap["bootstrap_se"],
                    },
                    "median_market_revenue": {
                        "estimate": boot_median["estimate"],
                        "ci_lower": boot_median["ci_lower"],
                        "ci_upper": boot_median["ci_upper"],
                        "bootstrap_se": boot_median["bootstrap_se"],
                    },
                    "n_gap_markets": len(valid_gap_markets),
                    "confidence": 0.95,
                    "n_bootstrap": 5000,
                    "method": "STA 444 — Bootstrap percentile CI (distribution-free)",
                }
        except Exception as e:
            logger.debug("bootstrap_gap_ci_failed", error=str(e))

        return result if result else None
