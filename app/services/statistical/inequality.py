"""
Inequality & Poverty Measurement — Gini, Theil, Atkinson, FGT (ECO 100, ECO 401).

Classes:
- InequalityAnalyzer: Gini coefficient, Theil index, Atkinson index
- PovertyAnalyzer: Foster-Greer-Thorbecke (FGT) poverty measures, poverty gap analysis

Extracted from jamii_insights.py for reuse across intelligence products.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class InequalityAnalyzer:
    """
    Income inequality measurement (ECO 100, ECO 401).

    Implements standard inequality indices used in development economics:
    - Gini coefficient (Lorenz curve based)
    - Theil index (entropy based, decomposable)
    - Atkinson index (welfare-based with inequality aversion)
    """

    @staticmethod
    def gini_coefficient(incomes: np.ndarray) -> float:
        """
        Gini coefficient: G = (2Σiyᵢ)/(nΣyᵢ) - (n+1)/n.

        Measures income inequality on a 0-1 scale where
        0 = perfect equality and 1 = perfect inequality.

        Uses the "fast" formula on sorted incomes:
        G = (2/(n²μ)) Σᵢ(i·y₍ᵢ₎) - (n+1)/n

        Args:
            incomes: array of income values

        Returns:
            Gini coefficient (0-1)
        """
        incomes = np.asarray(incomes, dtype=float)
        n = len(incomes)
        if n < 2 or np.sum(incomes) == 0:
            return 0.0
        sorted_inc = np.sort(incomes)
        mu = np.mean(sorted_inc)
        if mu <= 0:
            return 0.0
        gini = (2 * np.sum((np.arange(1, n + 1) * sorted_inc)) / (n * n * mu)) - (n + 1) / n
        return round(float(max(0, min(1, gini))), 4)

    @staticmethod
    def theil_index(incomes: np.ndarray) -> float:
        """
        Theil Index: T = (1/n)Σ(yᵢ/μ)·ln(yᵢ/μ).

        An entropy-based decomposable inequality measure (unlike Gini).
        Can be split into within-group and between-group inequality.
        T = 0 for perfect equality.

        Theil is GE(1); Theil-L (mean log deviation) is GE(0).

        Args:
            incomes: array of positive income values

        Returns:
            Theil index (≥ 0)
        """
        incomes = np.asarray(incomes, dtype=float)
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

    @staticmethod
    def atkinson_index(incomes: np.ndarray, epsilon: float = 1.0) -> float:
        """
        Atkinson Index: A = 1 - (1/μ)[(1/n)Σyᵢ^(1-ε)]^(1/(1-ε)).

        Welfare-based inequality measure with inequality aversion parameter ε:
        - ε = 0: no aversion (Atkinson = 0)
        - ε = 1: logarithmic: A = 1 - (geometric mean / arithmetic mean)
        - ε → ∞: maximin (Rawlsian)

        Args:
            incomes: array of positive income values
            epsilon: inequality aversion parameter

        Returns:
            Atkinson index (0-1)
        """
        incomes = np.asarray(incomes, dtype=float)
        incomes = incomes[incomes > 0]
        if len(incomes) == 0:
            return 0.0
        mu = np.mean(incomes)
        if mu <= 0:
            return 0.0

        if abs(epsilon - 1.0) < 1e-6:
            geometric_mean = np.exp(np.mean(np.log(incomes)))
            atkinson = 1 - geometric_mean / mu
        else:
            mean_transformed = np.mean(incomes ** (1 - epsilon)) ** (1 / (1 - epsilon))
            atkinson = 1 - mean_transformed / mu

        return round(float(max(0, min(1, atkinson))), 4)

    @staticmethod
    def lorenz_curve(incomes: np.ndarray) -> Dict[str, Any]:
        """
        Compute the Lorenz curve for income distribution.

        The Lorenz curve plots cumulative income share against
        cumulative population share (sorted by income).

        Args:
            incomes: array of income values

        Returns:
            Dict with population shares, income shares, and Gini
        """
        incomes = np.asarray(incomes, dtype=float)
        n = len(incomes)
        if n == 0:
            return {"population_shares": [], "income_shares": [], "gini": 0.0}

        sorted_inc = np.sort(incomes)
        total = np.sum(sorted_inc)
        if total <= 0:
            return {"population_shares": [], "income_shares": [], "gini": 0.0}

        cum_income = np.cumsum(sorted_inc) / total
        pop_shares = np.arange(1, n + 1) / n

        # Prepend origin
        pop_shares = np.concatenate([[0], pop_shares])
        cum_income = np.concatenate([[0], cum_income])

        return {
            "population_shares": pop_shares.tolist(),
            "income_shares": cum_income.tolist(),
            "gini": InequalityAnalyzer.gini_coefficient(incomes),
            "n_observations": n,
        }

    @staticmethod
    def decompose_theil(
        incomes: np.ndarray, groups: np.ndarray
    ) -> Dict[str, Any]:
        """
        Decompose Theil index into within-group and between-group components.

        T = T_between + Σⱼ(sⱼ · T_within_j)

        where sⱼ = group j's income share.

        Args:
            incomes: array of income values
            groups: array of group labels (same length as incomes)

        Returns:
            Dict with total, between, within Theil and group-level breakdown
        """
        incomes = np.asarray(incomes, dtype=float)
        groups = np.asarray(groups)
        total_theil = InequalityAnalyzer.theil_index(incomes)

        unique_groups = np.unique(groups)
        mu = np.mean(incomes)
        if mu <= 0:
            return {"total_theil": 0.0, "between_theil": 0.0, "within_theil": 0.0, "groups": {}}

        total_income = np.sum(incomes)
        between_theil = 0.0
        within_contributions: Dict[str, Dict[str, float]] = {}

        for g in unique_groups:
            mask = groups == g
            g_incomes = incomes[mask]
            g_mean = np.mean(g_incomes)
            g_share = np.sum(g_incomes) / total_income
            g_n = len(g_incomes)

            # Between-group component
            between_theil += g_share * np.log(g_mean / mu) if g_mean > 0 else 0.0

            # Within-group Theil
            g_theil = InequalityAnalyzer.theil_index(g_incomes)
            within_contributions[str(g)] = {
                "theil": g_theil,
                "income_share": round(float(g_share), 4),
                "mean_income": round(float(g_mean), 2),
                "n": int(g_n),
                "contribution": round(float(g_share * g_theil), 4),
            }

        within_theil = sum(v["contribution"] for v in within_contributions.values())

        return {
            "total_theil": round(total_theil, 4),
            "between_theil": round(float(between_theil), 4),
            "within_theil": round(float(within_theil), 4),
            "between_share": round(float(between_theil / max(total_theil, 1e-10)), 4),
            "within_share": round(float(within_theil / max(total_theil, 1e-10)), 4),
            "groups": within_contributions,
        }


class PovertyAnalyzer:
    """
    Poverty measurement (ECO 401 — Poverty and Inequality).

    Implements Foster-Greer-Thorbecke (FGT) poverty measures and
    related poverty analysis tools.
    """

    @staticmethod
    def fgt_measure(
        incomes: np.ndarray, poverty_line: float, alpha: int = 0
    ) -> float:
        """
        Foster-Greer-Thorbecke (FGT) poverty measure.

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
        incomes = np.asarray(incomes, dtype=float)
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
        else:
            return round(float(np.sum(gaps ** alpha) / n), 4)

    @staticmethod
    def poverty_profile(
        incomes: np.ndarray,
        poverty_line: float,
        groups: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive poverty profile with FGT measures.

        Args:
            incomes: array of income values
            poverty_line: poverty threshold z
            groups: optional array of group labels for disaggregation

        Returns:
            Dict with FGT(0), FGT(1), FGT(2) and group breakdowns
        """
        incomes = np.asarray(incomes, dtype=float)

        result: Dict[str, Any] = {
            "fgt_0_headcount": PovertyAnalyzer.fgt_measure(incomes, poverty_line, alpha=0),
            "fgt_1_poverty_gap": PovertyAnalyzer.fgt_measure(incomes, poverty_line, alpha=1),
            "fgt_2_severity": PovertyAnalyzer.fgt_measure(incomes, poverty_line, alpha=2),
            "poverty_line": poverty_line,
            "n_observations": len(incomes),
            "mean_income": round(float(np.mean(incomes)), 2),
            "median_income": round(float(np.median(incomes)), 2),
        }

        if groups is not None:
            groups = np.asarray(groups)
            unique_groups = np.unique(groups)
            group_profiles: Dict[str, Dict[str, float]] = {}
            for g in unique_groups:
                mask = groups == g
                g_incomes = incomes[mask]
                group_profiles[str(g)] = {
                    "fgt_0": PovertyAnalyzer.fgt_measure(g_incomes, poverty_line, alpha=0),
                    "fgt_1": PovertyAnalyzer.fgt_measure(g_incomes, poverty_line, alpha=1),
                    "fgt_2": PovertyAnalyzer.fgt_measure(g_incomes, poverty_line, alpha=2),
                    "mean_income": round(float(np.mean(g_incomes)), 2),
                    "n": int(np.sum(mask)),
                }
            result["group_profiles"] = group_profiles

        return result

    @staticmethod
    def watts_index(incomes: np.ndarray, poverty_line: float) -> float:
        """
        Watts poverty index: W = (1/n) Σᵢ ln(z/yᵢ) for yᵢ < z.

        A distribution-sensitive poverty measure satisfying monotonicity
        and transfer axioms.

        Args:
            incomes: array of income values
            poverty_line: poverty threshold z

        Returns:
            Watts index (≥ 0)
        """
        incomes = np.asarray(incomes, dtype=float)
        n = len(incomes)
        if n == 0:
            return 0.0
        poor = incomes[(incomes < poverty_line) & (incomes > 0)]
        if len(poor) == 0:
            return 0.0
        watts = float(np.sum(np.log(poverty_line / poor)) / n)
        return round(max(0, watts), 4)

    @staticmethod
    def sen_index(
        incomes: np.ndarray, poverty_line: float
    ) -> float:
        """
        Sen poverty index: S = H · [G_p + (1 - G_p) · I_g]

        Combines headcount ratio (H), Gini among the poor (G_p),
        and income gap ratio (I_g).

        Args:
            incomes: array of income values
            poverty_line: poverty threshold z

        Returns:
            Sen index (≥ 0)
        """
        incomes = np.asarray(incomes, dtype=float)
        n = len(incomes)
        if n == 0:
            return 0.0

        poor = incomes[incomes < poverty_line]
        H = len(poor) / n
        if len(poor) == 0:
            return 0.0

        # Income gap ratio
        I_g = float(np.mean((poverty_line - poor) / poverty_line))

        # Gini among the poor
        G_p = InequalityAnalyzer.gini_coefficient(poor)

        sen = H * (G_p + (1 - G_p) * I_g)
        return round(float(max(0, sen)), 4)


__all__ = ["InequalityAnalyzer", "PovertyAnalyzer"]
