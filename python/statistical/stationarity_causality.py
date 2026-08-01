"""
Stationarity Tests and Granger Causality for Angavu Intelligence Backend

Implements:
1. KPSS Test — null hypothesis: series is stationary
2. Granger Causality Test — does X Granger-cause Y?
3. Confidence Interval computation for all predictions
4. Bootstrap confidence intervals (non-parametric)

Academic Reference:
- Kwiatkowski et al. (1992). "Testing the null hypothesis of stationarity"
- Granger (1969). "Investigating causal relations by econometric models"
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. KPSS Stationarity Test
# ════════════════════════════════════════════════════════════════


class KPSS_test:
    """
    KPSS test for stationarity (Kwiatkowski et al. 1992).

    H₀: Series is stationary (trend-stationary or level-stationary)
    H₁: Series has a unit root (non-stationary)

    This is the COMPLEMENT of the ADF test:
    - ADF H₀: unit root exists (non-stationary)
    - KPSS H₀: series is stationary

    Using both tests together provides strong evidence:
    - ADF rejects + KPSS non-reject → stationary (strong evidence)
    - ADF non-reject + KPSS rejects → non-stationary (strong evidence)
    - Both reject → inconclusive
    - Neither rejects → inconclusive

    Test statistic: η = (1/T²) Σ Sₜ² / σ̂²
    where Sₜ = Σᵢ₌₁ᵗ eᵢ (cumulative residuals from regression)
    σ̂² = Newey-West HAC estimator of long-run variance
    """

    @staticmethod
    def test(
        data: np.ndarray,
        regression: str = "c",  # "c" for constant, "ct" for constant+trend
        lags: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Perform KPSS test.

        Args:
            data: Time series data
            regression: "c" for level stationarity, "ct" for trend stationarity
            lags: Bandwidth for Newey-West (None = auto)

        Returns:
            Dictionary with test statistic, critical values, conclusion
        """
        y = np.array(data, dtype=float)
        T = len(y)

        if T < 20:
            return {"error": "Need ≥20 observations for KPSS test"}

        # Step 1: Detrend the series
        if regression == "ct":
            # Regress on constant + trend
            X = np.column_stack([np.ones(T), np.arange(1, T + 1)])
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            residuals = y - X @ beta
        else:
            # Regress on constant only (demean)
            residuals = y - np.mean(y)

        # Step 2: Cumulative sum of residuals
        S = np.cumsum(residuals)

        # Step 3: Newey-West long-run variance estimate
        if lags is None:
            lags = int(np.floor(4 * (T / 100) ** 0.25))
        lags = max(1, min(lags, T // 4))

        # Compute gamma_0 and gamma_j with Bartlett kernel
        gamma_0 = np.sum(residuals ** 2) / T
        lrv = gamma_0
        for j in range(1, lags + 1):
            weight = 1 - j / (lags + 1)
            gamma_j = np.sum(residuals[j:] * residuals[:-j]) / T
            lrv += 2 * weight * gamma_j

        # Step 4: KPSS statistic
        kpss_stat = np.sum(S ** 2) / (T ** 2 * max(lrv, 1e-10))

        # Critical values (Kwiatkowski et al. 1992 Table 1)
        if regression == "ct":
            # Trend stationarity critical values
            crit = {"10%": 0.119, "5%": 0.146, "2.5%": 0.176, "1%": 0.216}
        else:
            # Level stationarity critical values
            crit = {"10%": 0.347, "5%": 0.463, "2.5%": 0.574, "1%": 0.739}

        # Conclusion
        is_stationary = kpss_stat < crit["5%"]

        return {
            "kpss_statistic": float(kpss_stat),
            "critical_values": crit,
            "is_stationary": is_stationary,
            "regression": regression,
            "lags": lags,
            "n": T,
            "conclusion": "fail to reject H₀ (stationary)" if is_stationary else "reject H₀ (non-stationary)",
        }


# ════════════════════════════════════════════════════════════════
# 2. Granger Causality Test
# ════════════════════════════════════════════════════════════════


class GrangerCausalityTest:
    """
    Granger causality test for economic variable relationships.

    X Granger-causes Y if past values of X help predict Y
    beyond what past values of Y alone can predict.

    Restricted model: Yₜ = α₀ + Σ αᵢ Yₜ₋ᵢ + εₜ
    Unrestricted model: Yₜ = α₀ + Σ αᵢ Yₜ₋ᵢ + Σ βⱼ Xₜ₋ⱼ + εₜ

    F-test: F = [(RSS_R - RSS_U) / p] / [RSS_U / (T - 2p - 1)]
    where p = number of lags

    Application: Does M-Pesa transaction volume Granger-cause revenue?
    """

    @staticmethod
    def test(
        x: np.ndarray,
        y: np.ndarray,
        max_lag: int = 4,
        significance: float = 0.05
    ) -> Dict[str, Any]:
        """
        Test if x Granger-causes y.

        Args:
            x: Potential cause variable
            y: Effect variable
            max_lag: Maximum number of lags to test
            significance: Significance level

        Returns:
            Dictionary with F-statistic, p-value, and conclusion
        """
        x = np.array(x, dtype=float)
        y = np.array(y, dtype=float)
        T = len(y)

        if len(x) != T:
            return {"error": "x and y must have same length"}
        if T < 2 * max_lag + 5:
            return {"error": f"Need ≥{2 * max_lag + 5} observations"}

        # Create lagged matrices
        n = T - max_lag

        # Dependent variable: y[t] for t = max_lag, ..., T-1
        y_dep = y[max_lag:]

        # Restricted model: Y on own lags
        X_restricted = np.column_stack([
            y[max_lag - i - 1:T - i - 1] for i in range(max_lag)
        ])
        # Add constant
        X_restricted = np.column_stack([np.ones(n), X_restricted])

        # Unrestricted model: Y on own lags + X lags
        X_unrestricted = np.column_stack([
            y[max_lag - i - 1:T - i - 1] for i in range(max_lag)
        ] + [
            x[max_lag - i - 1:T - i - 1] for i in range(max_lag)
        ])
        X_unrestricted = np.column_stack([np.ones(n), X_unrestricted])

        # Fit both models
        try:
            beta_r = np.linalg.lstsq(X_restricted, y_dep, rcond=None)[0]
            beta_u = np.linalg.lstsq(X_unrestricted, y_dep, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix — try fewer lags"}

        # Residual sum of squares
        rss_r = np.sum((y_dep - X_restricted @ beta_r) ** 2)
        rss_u = np.sum((y_dep - X_unrestricted @ beta_u) ** 2)

        # F-test
        p = max_lag  # number of restrictions
        df1 = p
        df2 = n - 2 * max_lag - 1

        if df2 <= 0 or rss_u <= 0:
            return {"error": "Insufficient degrees of freedom"}

        f_stat = ((rss_r - rss_u) / df1) / (rss_u / df2)
        p_value = 1 - sp_stats.f.cdf(f_stat, df1, df2)

        # Also compute AIC and BIC for both models
        aic_r = n * np.log(rss_r / n) + 2 * (max_lag + 1)
        aic_u = n * np.log(rss_u / n) + 2 * (2 * max_lag + 1)
        bic_r = n * np.log(rss_r / n) + np.log(n) * (max_lag + 1)
        bic_u = n * np.log(rss_u / n) + np.log(n) * (2 * max_lag + 1)

        granger_causes = p_value < significance

        return {
            "f_statistic": float(f_stat),
            "p_value": float(p_value),
            "df1": int(df1),
            "df2": int(df2),
            "granger_causes": granger_causes,
            "lag": max_lag,
            "rss_restricted": float(rss_r),
            "rss_unrestricted": float(rss_u),
            "aic_restricted": float(aic_r),
            "aic_unrestricted": float(aic_u),
            "conclusion": (
                f"X Granger-causes Y at {significance*100}% level"
                if granger_causes
                else f"X does NOT Granger-cause Y at {significance*100}% level"
            ),
        }

    @staticmethod
    def pairwise_causality_matrix(
        variables: Dict[str, np.ndarray],
        max_lag: int = 4,
        significance: float = 0.05
    ) -> Dict[str, Any]:
        """
        Test pairwise Granger causality among multiple variables.

        Returns a matrix of p-values and a directed graph of causal relationships.
        """
        names = list(variables.keys())
        n_vars = len(names)
        p_values = {}
        edges = []

        for i, name_i in enumerate(names):
            for j, name_j in enumerate(names):
                if i == j:
                    continue
                result = GrangerCausalityTest.test(
                    variables[name_i], variables[name_j], max_lag, significance
                )
                if "error" not in result:
                    p_val = result["p_value"]
                    key = f"{name_i} -> {name_j}"
                    p_values[key] = p_val
                    if result["granger_causes"]:
                        edges.append({"from": name_i, "to": name_j, "p_value": p_val, "f_stat": result["f_statistic"]})

        return {
            "p_values": p_values,
            "causal_edges": edges,
            "significance": significance,
            "n_variables": n_vars,
            "lag": max_lag,
        }


# ════════════════════════════════════════════════════════════════
# 3. Comprehensive Confidence Intervals
# ════════════════════════════════════════════════════════════════


class ConfidenceIntervals:
    """
    Comprehensive confidence interval computation for all predictions.
    """

    @staticmethod
    def mean_ci(
        data: np.ndarray,
        confidence: float = 0.95,
        method: str = "t"
    ) -> Dict[str, float]:
        """CI for population mean."""
        d = np.array(data, dtype=float)
        n = len(d)
        x_bar = np.mean(d)
        alpha = 1 - confidence

        if method == "t":
            se = np.std(d, ddof=1) / np.sqrt(n)
            crit = sp_stats.t.ppf(1 - alpha / 2, df=n - 1)
        elif method == "z":
            se = np.std(d, ddof=1) / np.sqrt(n)
            crit = sp_stats.norm.ppf(1 - alpha / 2)
        elif method == "bootstrap":
            return ConfidenceIntervals._bootstrap_ci(d, np.mean, confidence)
        else:
            raise ValueError(f"Unknown method: {method}")

        margin = crit * se
        return {
            "mean": float(x_bar),
            "ci_lower": float(x_bar - margin),
            "ci_upper": float(x_bar + margin),
            "margin_of_error": float(margin),
            "se": float(se),
            "method": method,
            "n": n,
        }

    @staticmethod
    def proportion_ci(
        successes: int,
        total: int,
        confidence: float = 0.95
    ) -> Dict[str, float]:
        """CI for population proportion (Wilson score interval)."""
        p_hat = successes / total
        alpha = 1 - confidence
        z = sp_stats.norm.ppf(1 - alpha / 2)

        # Wilson score interval (better than Wald for small n or extreme p)
        denom = 1 + z**2 / total
        center = (p_hat + z**2 / (2 * total)) / denom
        margin = z * np.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) / denom

        return {
            "proportion": float(p_hat),
            "ci_lower": float(max(0, center - margin)),
            "ci_upper": float(min(1, center + margin)),
            "margin_of_error": float(margin),
            "method": "wilson_score",
            "n": total,
        }

    @staticmethod
    def variance_ci(
        data: np.ndarray,
        confidence: float = 0.95
    ) -> Dict[str, float]:
        """CI for population variance using chi-squared distribution."""
        d = np.array(data, dtype=float)
        n = len(d)
        s2 = np.var(d, ddof=1)
        alpha = 1 - confidence

        chi2_lower = sp_stats.chi2.ppf(alpha / 2, df=n - 1)
        chi2_upper = sp_stats.chi2.ppf(1 - alpha / 2, df=n - 1)

        return {
            "variance": float(s2),
            "ci_lower": float((n - 1) * s2 / chi2_upper),
            "ci_upper": float((n - 1) * s2 / chi2_lower),
            "std_ci_lower": float(np.sqrt((n - 1) * s2 / chi2_upper)),
            "std_ci_upper": float(np.sqrt((n - 1) * s2 / chi2_lower)),
            "method": "chi_squared",
            "n": n,
        }

    @staticmethod
    def _bootstrap_ci(
        data: np.ndarray,
        statistic_fn: callable,
        confidence: float = 0.95,
        n_bootstrap: int = 10000
    ) -> Dict[str, float]:
        """Non-parametric bootstrap CI (Efron's percentile method)."""
        rng = np.random.default_rng(42)
        n = len(data)
        boot_stats = np.array([
            statistic_fn(rng.choice(data, size=n, replace=True))
            for _ in range(n_bootstrap)
        ])
        alpha = 1 - confidence
        ci_lower = np.percentile(boot_stats, 100 * alpha / 2)
        ci_upper = np.percentile(boot_stats, 100 * (1 - alpha / 2))

        return {
            "estimate": float(statistic_fn(data)),
            "ci_lower": float(ci_lower),
            "ci_upper": float(ci_upper),
            "bootstrap_se": float(np.std(boot_stats)),
            "method": "bootstrap_percentile",
            "n_bootstrap": n_bootstrap,
            "n": n,
        }


# ════════════════════════════════════════════════════════════════
# 4. Bootstrap Confidence Intervals (BCa)
# ════════════════════════════════════════════════════════════════


class BootstrapBCa:
    """
    Bias-Corrected and Accelerated (BCa) bootstrap confidence intervals.
    More accurate than percentile bootstrap, corrects for bias and skewness.
    """

    @staticmethod
    def bca_ci(
        data: np.ndarray,
        statistic_fn: callable,
        confidence: float = 0.95,
        n_bootstrap: int = 10000
    ) -> Dict[str, float]:
        """
        BCa bootstrap CI.

        Corrects the percentile CI for:
        1. Bias: statistic may not be median-unbiased
        2. Acceleration: rate of change of SE with respect to true parameter
        """
        d = np.array(data, dtype=float)
        n = len(d)
        rng = np.random.default_rng(42)

        # Bootstrap samples
        boot_stats = np.array([
            statistic_fn(rng.choice(d, size=n, replace=True))
            for _ in range(n_bootstrap)
        ])

        # Original estimate
        theta_hat = statistic_fn(d)

        # Bias correction: z₀ = Φ⁻¹(#{θ* < θ̂} / B)
        z0 = sp_stats.norm.ppf(np.mean(boot_stats < theta_hat))

        # Acceleration: using jackknife
        jackknife_stats = np.array([
            statistic_fn(np.delete(d, i))
            for i in range(n)
        ])
        jack_mean = np.mean(jackknife_stats)
        a = np.sum((jack_mean - jackknife_stats) ** 3) / (
            6 * (np.sum((jack_mean - jackknife_stats) ** 2)) ** 1.5
        )

        # Adjusted percentiles
        alpha = 1 - confidence
        z_alpha = sp_stats.norm.ppf(alpha / 2)
        z_1alpha = sp_stats.norm.ppf(1 - alpha / 2)

        p_lower = sp_stats.norm.cdf(z0 + (z0 + z_alpha) / (1 - a * (z0 + z_alpha)))
        p_upper = sp_stats.norm.cdf(z0 + (z0 + z_1alpha) / (1 - a * (z0 + z_1alpha)))

        ci_lower = np.percentile(boot_stats, 100 * p_lower)
        ci_upper = np.percentile(boot_stats, 100 * p_upper)

        return {
            "estimate": float(theta_hat),
            "ci_lower": float(ci_lower),
            "ci_upper": float(ci_upper),
            "confidence": confidence,
            "bias_correction": float(z0),
            "acceleration": float(a),
            "bootstrap_se": float(np.std(boot_stats)),
            "method": "BCa",
            "n_bootstrap": n_bootstrap,
            "n": n,
        }


# ════════════════════════════════════════════════════════════════
# Runner Interface
# ════════════════════════════════════════════════════════════════


def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the Rust bridge."""
    try:
        if method == "kpss":
            data = np.array(args["data"], dtype=float)
            return KPSS_test.test(
                data,
                regression=args.get("regression", "c"),
                lags=args.get("lags"),
            )

        elif method == "granger_causality":
            x = np.array(args["x"], dtype=float)
            y = np.array(args["y"], dtype=float)
            return GrangerCausalityTest.test(
                x, y,
                max_lag=args.get("max_lag", 4),
                significance=args.get("significance", 0.05),
            )

        elif method == "granger_matrix":
            variables = {k: np.array(v, dtype=float) for k, v in args["variables"].items()}
            return GrangerCausalityTest.pairwise_causality_matrix(
                variables,
                max_lag=args.get("max_lag", 4),
                significance=args.get("significance", 0.05),
            )

        elif method == "ci_mean":
            data = np.array(args["data"], dtype=float)
            return ConfidenceIntervals.mean_ci(
                data,
                confidence=args.get("confidence", 0.95),
                method=args.get("ci_method", "t"),
            )

        elif method == "ci_proportion":
            return ConfidenceIntervals.proportion_ci(
                args["successes"], args["total"],
                confidence=args.get("confidence", 0.95),
            )

        elif method == "ci_variance":
            data = np.array(args["data"], dtype=float)
            return ConfidenceIntervals.variance_ci(
                data, confidence=args.get("confidence", 0.95),
            )

        elif method == "bootstrap_bca":
            data = np.array(args["data"], dtype=float)
            stat_name = args.get("statistic", "mean")
            stat_fn = {"mean": np.mean, "median": np.median, "std": np.std}.get(stat_name, np.mean)
            return BootstrapBCa.bca_ci(
                data, stat_fn,
                confidence=args.get("confidence", 0.95),
                n_bootstrap=args.get("n_bootstrap", 10000),
            )

        else:
            return {"error": f"Unknown method: {method}"}

    except Exception as e:
        return {"error": str(e), "method": method}


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1:
        input_data = json.loads(sys.argv[1])
        result = run_method(input_data["method"], input_data.get("args", {}))
        print(json.dumps(result))
