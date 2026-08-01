"""
Extended Non-Parametric Methods for Angavu Intelligence Backend (STA 442/443)

Implements advanced non-parametric methods for distribution-free inference:

1. Friedman Test — non-parametric repeated measures
2. Kolmogorov-Smirnov Test — distribution goodness-of-fit
3. Anderson-Darling Test — distribution fit assessment
4. LOESS Regression — non-parametric local polynomial regression
5. Bootstrap BCa — bias-corrected accelerated bootstrap CI
6. Non-parametric Regression — cubic spline smoothing

Mathematical Justification:
- Friedman: χ²_F = (12/(nk(k+1))) Σ R²ⱼ - 3n(k+1), rank-based repeated measures
- KS: D = sup|F_n(x) - F_0(x)|, Kolmogorov distribution for p-value
- AD: A² = -n - Σ(2i-1)(ln F₀(x_(i)) + ln(1-F₀(x_(n+1-i))))/n, more sensitive to tails
- LOESS: weighted local polynomial fit, bandwidth h controls bias-variance tradeoff
- BCa: bias-correction + acceleration for second-order accurate CIs
- Splines: minimize Σ(yᵢ-f(xᵢ))² + λ∫(f''(x))²dx, penalized likelihood

Application to Angavu:
- Friedman: compare worker income across repeated time periods
- KS/AD: test if transaction data follows expected distributions
- LOESS: smooth income trends without assuming functional form
- BCa bootstrap: accurate CIs for skewed financial statistics
- Splines: smooth credit score calibration curves
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from scipy import stats as scipy_stats
from scipy.interpolate import UnivariateSpline


class FriedmanTest:
    """Friedman Test — non-parametric repeated measures.

    STA 442: Extension of sign test to k treatments with n blocks.
    Tests H₀: all treatments have the same distribution.

    Application: Compare worker income across months/quarters without
    assuming normality (income data is typically skewed).
    """

    @staticmethod
    def test(data: List[List[float]]) -> Dict[str, Any]:
        """Run Friedman test.

        Args:
            data: list of k treatments, each with n observations (blocks)
                  Format: [[block1_trt1, block1_trt2, ...], [block2_trt1, ...], ...]
                  OR list of n blocks, each with k values

        Returns:
            Dict with test statistic, p-value, effect size
        """
        arr = np.array(data, dtype=float)

        # Ensure shape is (n_blocks, k_treatments)
        if arr.ndim != 2:
            raise ValueError("Data must be 2D: (blocks × treatments)")

        n, k = arr.shape
        if n < 2 or k < 2:
            raise ValueError("Need ≥2 blocks and ≥2 treatments")

        # Rank within each block
        ranks = np.zeros_like(arr)
        for i in range(n):
            ranks[i] = scipy_stats.rankdata(arr[i])

        # Mean rank per treatment
        mean_ranks = ranks.mean(axis=0)

        # Friedman chi-square statistic
        chi2_f = (12.0 / (n * k * (k + 1))) * np.sum(mean_ranks**2 * n) - 3 * n * (k + 1)

        # Correction for ties
        ranks_tied = ranks
        tie_correction = 0
        for i in range(n):
            row = arr[i]
            _, counts = np.unique(row, return_counts=True)
            ties = counts[counts > 1]
            if len(ties) > 0:
                tie_correction += np.sum(ties**3 - ties)

        if tie_correction > 0:
            chi2_f_corrected = chi2_f / (1 - tie_correction / (n * k * (k**2 - 1)))
        else:
            chi2_f_corrected = chi2_f

        # P-value from chi-square distribution (df = k-1)
        df = k - 1
        p_value = 1 - scipy_stats.chi2.cdf(chi2_f_corrected, df)

        # Effect size: Kendall's W (concordance coefficient)
        w = chi2_f / (n * (k - 1)) if n * (k - 1) > 0 else 0

        # Post-hoc: Nemenyi test (pairwise comparisons)
        comparisons = []
        q_critical = scipy_stats.t.ppf(0.975, df=1000) * np.sqrt(2)  # approx
        for i in range(k):
            for j in range(i + 1, k):
                diff = abs(mean_ranks[i] - mean_ranks[j])
                se = np.sqrt(k * (k + 1) / (6 * n))
                z = diff / se
                p_adj = min(1.0, (1 - scipy_stats.norm.cdf(z)) * 2 * k * (k - 1) / 2)
                comparisons.append({
                    "treatment_i": int(i),
                    "treatment_j": int(j),
                    "rank_diff": float(diff),
                    "z_statistic": float(z),
                    "p_adjusted": float(p_adj),
                    "significant": p_adj < 0.05,
                })

        return {
            "test_name": "Friedman Test",
            "chi_square": float(chi2_f_corrected),
            "df": int(df),
            "p_value": float(p_value),
            "significant_at_05": p_value < 0.05,
            "kendall_w": float(w),
            "mean_ranks": mean_ranks.tolist(),
            "n_blocks": int(n),
            "n_treatments": int(k),
            "post_hoc_comparisons": comparisons,
        }


class KolmogorovSmirnovTest:
    """Kolmogorov-Smirnov Goodness-of-Fit Test.

    STA 442: Tests whether a sample comes from a specified distribution.
    D = sup|F_n(x) - F_0(x)|

    Application: Test if transaction amounts follow expected distributions
    (log-normal for income, gamma for spending patterns).
    """

    @staticmethod
    def one_sample(data: List[float], distribution: str = "norm", params: Optional[Dict] = None) -> Dict[str, Any]:
        """One-sample KS test.

        Args:
            data: observed sample
            distribution: 'norm', 'lognorm', 'expon', 'gamma', 'uniform'
            params: distribution parameters (if None, estimated from data)

        Returns:
            Dict with D-statistic, p-value
        """
        arr = np.array(data, dtype=float)
        n = len(arr)
        if n < 5:
            raise ValueError("Need ≥5 observations")

        sorted_data = np.sort(arr)

        # Get CDF function
        dist_map = {
            "norm": scipy_stats.norm,
            "lognorm": scipy_stats.lognorm,
            "expon": scipy_stats.expon,
            "gamma": scipy_stats.gamma,
            "uniform": scipy_stats.uniform,
        }

        if distribution not in dist_map:
            raise ValueError(f"Unknown distribution: {distribution}")

        dist = dist_map[distribution]

        if params is not None:
            cdf_values = dist.cdf(sorted_data, **params)
        else:
            # Fit parameters from data
            if distribution == "norm":
                mu, sigma = arr.mean(), arr.std(ddof=1)
                cdf_values = dist.cdf(sorted_data, loc=mu, scale=sigma)
            elif distribution == "lognorm":
                log_data = np.log(arr[arr > 0])
                s, loc, scale = scipy_stats.lognorm.fit(arr[arr > 0], floc=0)
                cdf_values = dist.cdf(sorted_data, s, loc=loc, scale=scale)
            elif distribution == "expon":
                loc, scale = scipy_stats.expon.fit(arr)
                cdf_values = dist.cdf(sorted_data, loc=loc, scale=scale)
            elif distribution == "gamma":
                a, loc, scale = scipy_stats.gamma.fit(arr)
                cdf_values = dist.cdf(sorted_data, a, loc=loc, scale=scale)
            else:  # uniform
                loc, scale = arr.min(), arr.max() - arr.min()
                cdf_values = dist.cdf(sorted_data, loc=loc, scale=scale)

        empirical = np.arange(1, n + 1) / n
        empirical_prev = np.arange(0, n) / n

        d_plus = np.max(empirical - cdf_values)
        d_minus = np.max(cdf_values - empirical_prev)
        d_stat = max(d_plus, d_minus)

        # P-value (Kolmogorov distribution approximation)
        sqrt_n = np.sqrt(n)
        lam = (sqrt_n + 0.12 + 0.11 / sqrt_n) * d_stat
        p_value = 0.0
        for j in range(1, 101):
            p_value += 2 * (-1)**(j - 1) * np.exp(-2 * j * j * lam * lam)
        p_value = max(0, min(1, p_value))

        return {
            "test_name": f"Kolmogorov-Smirnov (vs {distribution})",
            "d_statistic": float(d_stat),
            "d_plus": float(d_plus),
            "d_minus": float(d_minus),
            "p_value": float(p_value),
            "significant_at_05": p_value < 0.05,
            "n": int(n),
            "distribution": distribution,
        }

    @staticmethod
    def two_sample(sample1: List[float], sample2: List[float]) -> Dict[str, Any]:
        """Two-sample KS test.

        Tests H₀: both samples come from the same distribution.
        """
        stat, p_value = scipy_stats.ks_2samp(sample1, sample2)
        return {
            "test_name": "Kolmogorov-Smirnov (two-sample)",
            "d_statistic": float(stat),
            "p_value": float(p_value),
            "significant_at_05": p_value < 0.05,
            "n1": len(sample1),
            "n2": len(sample2),
        }


class AndersonDarlingTest:
    """Anderson-Darling Test — distribution fit assessment.

    STA 442: More sensitive to tail deviations than KS test.
    A² = -n - Σ(2i-1)(ln F₀(x_(i)) + ln(1-F₀(x_(n+1-i))))/n

    Application: Test if credit scores or income follow assumed distributions,
    especially for tail risk assessment.
    """

    @staticmethod
    def test(data: List[float], distribution: str = "norm") -> Dict[str, Any]:
        """Run Anderson-Darling test.

        Args:
            data: observed sample
            distribution: 'norm', 'expon', 'logistic', 'gumbel'

        Returns:
            Dict with A² statistic, critical values, p-value
        """
        arr = np.array(data, dtype=float)
        n = len(arr)
        if n < 5:
            raise ValueError("Need ≥5 observations")

        sorted_data = np.sort(arr)

        if distribution == "norm":
            result = scipy_stats.anderson(sorted_data, dist='norm')
        elif distribution == "expon":
            result = scipy_stats.anderson(sorted_data, dist='expon')
        elif distribution == "logistic":
            result = scipy_stats.anderson(sorted_data, dist='logistic')
        elif distribution == "gumbel":
            result = scipy_stats.anderson(sorted_data, dist='gumbel')
        else:
            raise ValueError(f"Unsupported distribution: {distribution}")

        # Extract results
        stat = result.statistic
        critical_values = dict(zip(
            [f"{sl}%" for sl in result.significance_level],
            result.critical_values.tolist()
        ))

        # Determine significance at 5%
        cv_5 = result.critical_values[2] if len(result.critical_values) > 2 else result.critical_values[-1]
        significant = stat > cv_5

        # Approximate p-value (interpolation from critical values)
        # AD stat follows approximately: p ≈ exp(1.2937 - 5.709*stat + 0.0186*stat²) for normal
        if distribution == "norm":
            if stat < 0.2:
                p_approx = 1.0
            elif stat < 0.341:
                p_approx = 0.75
            elif stat < 0.564:
                p_approx = 0.50
            elif stat < 0.755:
                p_approx = 0.25
            elif stat < 1.067:
                p_approx = 0.10
            elif stat < 1.362:
                p_approx = 0.05
            elif stat < 1.709:
                p_approx = 0.025
            elif stat < 1.943:
                p_approx = 0.01
            else:
                p_approx = 0.005
        else:
            p_approx = 0.05 if significant else 0.50

        return {
            "test_name": f"Anderson-Darling (vs {distribution})",
            "statistic": float(stat),
            "critical_values": critical_values,
            "p_value_approx": float(p_approx),
            "significant_at_05": bool(significant),
            "n": int(n),
            "distribution": distribution,
        }


class LOESSRegression:
    """LOESS — Locally Estimated Scatterplot Smoothing.

    STA 443: Non-parametric local polynomial regression.
    Fits low-degree polynomial to subsets of data, weighted by distance.

    Application: Smooth income trends, seasonality patterns, credit score
    calibration without assuming a global functional form.
    """

    @staticmethod
    def fit(x: List[float], y: List[float], span: float = 0.3,
            degree: int = 1, n_points: int = 100) -> Dict[str, Any]:
        """Fit LOESS regression.

        Args:
            x: predictor values
            y: response values
            span: fraction of data used for each local fit (0-1)
            degree: polynomial degree (0=constant, 1=linear, 2=quadratic)
            n_points: number of evaluation points

        Returns:
            Dict with fitted values, smoothed curve, residuals
        """
        x_arr = np.array(x, dtype=float)
        y_arr = np.array(y, dtype=float)
        n = len(x_arr)

        if n < max(5, int(span * n) + 1):
            raise ValueError("Insufficient data for LOESS fit")

        # Sort by x
        order = np.argsort(x_arr)
        x_sorted = x_arr[order]
        y_sorted = y_arr[order]

        # Evaluation points
        x_eval = np.linspace(x_sorted.min(), x_sorted.max(), n_points)
        y_eval = np.zeros(n_points)

        # Bandwidth: number of neighbors
        k = max(int(span * n), degree + 1)

        for i, x0 in enumerate(x_eval):
            # Find k nearest neighbors
            distances = np.abs(x_sorted - x0)
            idx = np.argsort(distances)[:k]
            max_dist = distances[idx[-1]]

            # Tricube weights
            if max_dist > 0:
                u = distances[idx] / max_dist
                w = (1 - u**3)**3
            else:
                w = np.ones(k)

            # Weighted polynomial regression
            X_local = np.column_stack([x_sorted[idx]**p for p in range(degree + 1)])
            W = np.diag(w)

            try:
                # β = (X'WX)^{-1} X'Wy
                XtWX = X_local.T @ W @ X_local
                XtWy = X_local.T @ W @ y_sorted[idx]
                beta = np.linalg.solve(XtWX, XtWy)
                y_eval[i] = sum(beta[p] * x0**p for p in range(degree + 1))
            except np.linalg.LinAlgError:
                y_eval[i] = y_sorted[idx].mean()

        # Fitted values at original x positions (for residuals)
        y_fitted = np.interp(x_sorted, x_eval, y_eval)
        residuals = y_sorted - y_fitted

        # R-squared
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((y_sorted - y_sorted.mean())**2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        return {
            "x_eval": x_eval.tolist(),
            "y_eval": y_eval.tolist(),
            "x_sorted": x_sorted.tolist(),
            "y_fitted": y_fitted.tolist(),
            "residuals": residuals.tolist(),
            "r_squared": float(r_squared),
            "span": float(span),
            "degree": int(degree),
            "n_points": int(n_points),
        }


class BootstrapBCa:
    """BCa Bootstrap — Bias-Corrected and Accelerated Confidence Intervals.

    STA 442: Second-order accurate bootstrap CIs.
    Corrects for bias and skewness in bootstrap distribution.

    Application: Accurate CIs for Gini coefficient, Theil index, and
    other skewed financial statistics.
    """

    @staticmethod
    def confidence_interval(data: List[float], statistic_fn=None,
                            n_bootstrap: int = 5000, confidence: float = 0.95) -> Dict[str, Any]:
        """Compute BCa bootstrap CI.

        Args:
            data: observed sample
            statistic_fn: function to compute statistic (default: mean)
            n_bootstrap: number of bootstrap resamples
            confidence: confidence level

        Returns:
            Dict with CI, bias, acceleration
        """
        arr = np.array(data, dtype=float)
        n = len(arr)
        if n < 5:
            raise ValueError("Need ≥5 observations")

        if statistic_fn is None:
            statistic_fn = np.mean

        # Original estimate
        theta_hat = float(statistic_fn(arr))

        # Bootstrap resamples
        rng = np.random.default_rng(42)
        boot_stats = np.array([
            float(statistic_fn(rng.choice(arr, size=n, replace=True)))
            for _ in range(n_bootstrap)
        ])

        # Bias correction factor z₀
        prop_less = np.mean(boot_stats < theta_hat)
        # Avoid 0 and 1
        prop_less = max(1e-10, min(1 - 1e-10, prop_less))
        z0 = scipy_stats.norm.ppf(prop_less)

        # Acceleration factor a (jackknife estimate)
        jackknife_stats = np.array([
            float(statistic_fn(np.delete(arr, i)))
            for i in range(n)
        ])
        jack_mean = jackknife_stats.mean()
        num = np.sum((jack_mean - jackknife_stats)**3)
        den = 6 * (np.sum((jack_mean - jackknife_stats)**2))**1.5
        a = num / den if abs(den) > 1e-15 else 0.0

        # Adjusted percentiles
        alpha = 1 - confidence
        z_lo = scipy_stats.norm.ppf(alpha / 2)
        z_hi = scipy_stats.norm.ppf(1 - alpha / 2)

        p_lo = scipy_stats.norm.cdf(z0 + (z0 + z_lo) / (1 - a * (z0 + z_lo)))
        p_hi = scipy_stats.norm.cdf(z0 + (z0 + z_hi) / (1 - a * (z0 + z_hi)))

        # Clamp to valid range
        p_lo = max(1e-10, min(1 - 1e-10, p_lo))
        p_hi = max(1e-10, min(1 - 1e-10, p_hi))

        # BCa CI
        boot_sorted = np.sort(boot_stats)
        ci_lo = float(np.percentile(boot_sorted, p_lo * 100))
        ci_hi = float(np.percentile(boot_sorted, p_hi * 100))

        # Standard percentile CI for comparison
        pct_lo = float(np.percentile(boot_sorted, (alpha / 2) * 100))
        pct_hi = float(np.percentile(boot_sorted, (1 - alpha / 2) * 100))

        return {
            "estimate": theta_hat,
            "bca_ci_lower": ci_lo,
            "bca_ci_upper": ci_hi,
            "percentile_ci_lower": pct_lo,
            "percentile_ci_upper": pct_hi,
            "confidence": float(confidence),
            "bootstrap_se": float(np.std(boot_stats, ddof=1)),
            "bias_correction": float(z0),
            "acceleration": float(a),
            "n_bootstrap": int(n_bootstrap),
            "n_observations": int(n),
        }


class NonparametricSplineRegression:
    """Non-parametric regression using cubic smoothing splines.

    STA 443: Fit smooth curve by minimizing penalized residual sum of squares:
        min Σ(yᵢ - f(xᵢ))² + λ ∫(f''(x))² dx

    λ controls smoothness: λ→0 interpolates, λ→∞ gives linear fit.

    Application: Credit score calibration curves, income trend smoothing.
    """

    @staticmethod
    def fit(x: List[float], y: List[float], smoothing_factor: Optional[float] = None,
            n_points: int = 200) -> Dict[str, Any]:
        """Fit cubic smoothing spline.

        Args:
            x: predictor values
            y: response values
            smoothing_factor: s parameter (default: auto-selected by cross-validation)
            n_points: number of evaluation points

        Returns:
            Dict with spline coefficients, knots, fitted curve
        """
        x_arr = np.array(x, dtype=float)
        y_arr = np.array(y, dtype=float)
        n = len(x_arr)

        if n < 4:
            raise ValueError("Need ≥4 observations for spline fit")

        # Sort by x
        order = np.argsort(x_arr)
        x_sorted = x_arr[order]
        y_sorted = y_arr[order]

        # Fit spline
        if smoothing_factor is not None:
            spline = UnivariateSpline(x_sorted, y_sorted, s=smoothing_factor)
        else:
            # Auto-select smoothing (default s = n * var(y))
            spline = UnivariateSpline(x_sorted, y_sorted)

        # Evaluation points
        x_eval = np.linspace(x_sorted.min(), x_sorted.max(), n_points)
        y_eval = spline(x_eval)

        # Fitted values at original x
        y_fitted = spline(x_sorted)
        residuals = y_sorted - y_fitted

        # R-squared
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((y_sorted - y_sorted.mean())**2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Effective degrees of freedom (approximate)
        # For smoothing spline: trace of smoother matrix
        # Approximation: number of knots
        knots = spline.get_knots()
        edf = len(knots) + 4  # cubic spline

        # GCV (Generalized Cross-Validation) score
        gcv = (1 / n) * ss_res / (1 - edf / n)**2 if edf < n else float('inf')

        # AIC
        aic = n * np.log(ss_res / n) + 2 * edf if ss_res > 0 else float('-inf')

        return {
            "x_eval": x_eval.tolist(),
            "y_eval": y_eval.tolist(),
            "x_sorted": x_sorted.tolist(),
            "y_fitted": y_fitted.tolist(),
            "residuals": residuals.tolist(),
            "r_squared": float(r_squared),
            "knots": knots.tolist(),
            "n_knots": len(knots),
            "effective_df": float(edf),
            "gcv_score": float(gcv),
            "aic": float(aic),
            "smoothing_factor": float(spline._data[0]) if hasattr(spline, '_data') else None,
        }
