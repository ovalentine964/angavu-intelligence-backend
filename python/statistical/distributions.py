"""
Probability Distributions and Fitting for Angavu Intelligence Backend (STA 241/341)

Implements:
1. Distribution fitting via MLE (Maximum Likelihood Estimation)
2. Moment Generating Functions (MGF) for distribution characterization
3. Central Limit Theorem demonstration and sampling distributions
4. Goodness-of-fit tests (Chi-squared, KS)
5. Parametric bootstrap for confidence intervals

Mathematical foundations:
- MLE: θ̂ = argmax L(θ|x) = argmax Σ log f(xᵢ|θ)
- MGF: M(t) = E[e^(tX)], uniquely determines distribution
- CLT: X̄ₙ → N(μ, σ²/n) as n → ∞
- Chi-squared GOF: χ² = Σ (Oᵢ - Eᵢ)² / Eᵢ
- KS test: D = sup|Fₙ(x) - F₀(x)|

Reference:
- Casella & Berger (2002). Statistical Inference.
- Wasserman (2004). All of Statistics.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. Distribution Fitting via MLE
# ════════════════════════════════════════════════════════════════


@dataclass
class FitResult:
    """Result of distribution fitting."""
    distribution: str
    parameters: Dict[str, float]
    log_likelihood: float
    aic: float
    bic: float
    n: int
    ks_statistic: float
    ks_p_value: float
    chi_sq_statistic: Optional[float] = None
    chi_sq_p_value: Optional[float] = None
    goodness_of_fit: str = ""


class DistributionFitter:
    """
    Fit parametric distributions to data via Maximum Likelihood Estimation.

    Supported distributions:
    - Normal: N(μ, σ²)
    - Exponential: Exp(λ)
    - Poisson: Poisson(λ)
    - Gamma: Gamma(α, β)
    - Beta: Beta(α, β)
    - Lognormal: LogN(μ, σ²)
    - Weibull: Weibull(k, λ)
    """

    @staticmethod
    def fit_normal(data: np.ndarray) -> FitResult:
        """MLE for Normal: μ̂ = x̄, σ̂² = (1/n)Σ(xᵢ - x̄)²"""
        n = len(data)
        mu_hat = np.mean(data)
        sigma_hat = np.std(data, ddof=0)
        ll = np.sum(sp_stats.norm.logpdf(data, mu_hat, sigma_hat))
        k = 2
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * np.log(n)
        ks_stat, ks_p = sp_stats.kstest(data, 'norm', args=(mu_hat, sigma_hat))
        return FitResult(
            distribution="normal",
            parameters={"mu": float(mu_hat), "sigma": float(sigma_hat)},
            log_likelihood=float(ll), aic=float(aic), bic=float(bic),
            n=n, ks_statistic=float(ks_stat), ks_p_value=float(ks_p),
            goodness_of_fit="good" if ks_p > 0.05 else "poor"
        )

    @staticmethod
    def fit_exponential(data: np.ndarray) -> FitResult:
        """MLE for Exponential: λ̂ = 1/x̄"""
        if np.any(data < 0):
            raise ValueError("Exponential data must be non-negative")
        n = len(data)
        lambda_hat = 1.0 / np.mean(data) if np.mean(data) > 0 else 0.0
        ll = np.sum(sp_stats.expon.logpdf(data, scale=1.0/lambda_hat)) if lambda_hat > 0 else -np.inf
        k = 1
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * np.log(n)
        ks_stat, ks_p = sp_stats.kstest(data, 'expon', args=(0, 1.0/lambda_hat)) if lambda_hat > 0 else (1.0, 0.0)
        return FitResult(
            distribution="exponential",
            parameters={"lambda": float(lambda_hat)},
            log_likelihood=float(ll), aic=float(aic), bic=float(bic),
            n=n, ks_statistic=float(ks_stat), ks_p_value=float(ks_p),
            goodness_of_fit="good" if ks_p > 0.05 else "poor"
        )

    @staticmethod
    def fit_gamma(data: np.ndarray) -> FitResult:
        """MLE for Gamma via scipy."""
        if np.any(data <= 0):
            raise ValueError("Gamma data must be positive")
        n = len(data)
        a_hat, loc, scale = sp_stats.gamma.fit(data, floc=0)
        b_hat = 1.0 / scale  # rate parameter
        ll = np.sum(sp_stats.gamma.logpdf(data, a_hat, loc=0, scale=scale))
        k = 2
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * np.log(n)
        ks_stat, ks_p = sp_stats.kstest(data, 'gamma', args=(a_hat, 0, scale))
        return FitResult(
            distribution="gamma",
            parameters={"alpha": float(a_hat), "beta": float(b_hat)},
            log_likelihood=float(ll), aic=float(aic), bic=float(bic),
            n=n, ks_statistic=float(ks_stat), ks_p_value=float(ks_p),
            goodness_of_fit="good" if ks_p > 0.05 else "poor"
        )

    @staticmethod
    def fit_beta(data: np.ndarray) -> FitResult:
        """MLE for Beta via scipy."""
        if np.any(data <= 0) or np.any(data >= 1):
            raise ValueError("Beta data must be in (0, 1)")
        n = len(data)
        a_hat, b_hat, loc, scale = sp_stats.beta.fit(data, floc=0, fscale=1)
        ll = np.sum(sp_stats.beta.logpdf(data, a_hat, b_hat, loc=0, scale=1))
        k = 2
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * np.log(n)
        ks_stat, ks_p = sp_stats.kstest(data, 'beta', args=(a_hat, b_hat, 0, 1))
        return FitResult(
            distribution="beta",
            parameters={"alpha": float(a_hat), "beta": float(b_hat)},
            log_likelihood=float(ll), aic=float(aic), bic=float(bic),
            n=n, ks_statistic=float(ks_stat), ks_p_value=float(ks_p),
            goodness_of_fit="good" if ks_p > 0.05 else "poor"
        )

    @staticmethod
    def fit_lognormal(data: np.ndarray) -> FitResult:
        """MLE for Lognormal."""
        if np.any(data <= 0):
            raise ValueError("Lognormal data must be positive")
        n = len(data)
        log_data = np.log(data)
        mu_hat = np.mean(log_data)
        sigma_hat = np.std(log_data, ddof=0)
        ll = np.sum(sp_stats.lognorm.logpdf(data, sigma_hat, scale=np.exp(mu_hat)))
        k = 2
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * np.log(n)
        ks_stat, ks_p = sp_stats.kstest(data, 'lognorm', args=(sigma_hat, 0, np.exp(mu_hat)))
        return FitResult(
            distribution="lognormal",
            parameters={"mu": float(mu_hat), "sigma": float(sigma_hat)},
            log_likelihood=float(ll), aic=float(aic), bic=float(bic),
            n=n, ks_statistic=float(ks_stat), ks_p_value=float(ks_p),
            goodness_of_fit="good" if ks_p > 0.05 else "poor"
        )

    @staticmethod
    def fit_weibull(data: np.ndarray) -> FitResult:
        """MLE for Weibull via scipy."""
        if np.any(data <= 0):
            raise ValueError("Weibull data must be positive")
        n = len(data)
        k_hat, loc, lam_hat = sp_stats.weibull_min.fit(data, floc=0)
        ll = np.sum(sp_stats.weibull_min.logpdf(data, k_hat, loc=0, scale=lam_hat))
        k = 2
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * np.log(n)
        ks_stat, ks_p = sp_stats.kstest(data, 'weibull_min', args=(k_hat, 0, lam_hat))
        return FitResult(
            distribution="weibull",
            parameters={"k": float(k_hat), "lambda": float(lam_hat)},
            log_likelihood=float(ll), aic=float(aic), bic=float(bic),
            n=n, ks_statistic=float(ks_stat), ks_p_value=float(ks_p),
            goodness_of_fit="good" if ks_p > 0.05 else "poor"
        )

    @staticmethod
    def fit_best(data: np.ndarray) -> FitResult:
        """Fit all supported distributions and return the best (lowest AIC)."""
        data = np.array(data, dtype=float)
        results = []
        for name, fitter in [
            ("normal", DistributionFitter.fit_normal),
            ("exponential", DistributionFitter.fit_exponential),
            ("gamma", DistributionFitter.fit_gamma),
            ("lognormal", DistributionFitter.fit_lognormal),
            ("weibull", DistributionFitter.fit_weibull),
        ]:
            try:
                r = fitter(data)
                results.append(r)
            except Exception:
                continue
        if not results:
            raise ValueError("No distribution could be fitted")
        best = min(results, key=lambda r: r.aic)
        return best


# ════════════════════════════════════════════════════════════════
# 2. Moment Generating Functions
# ════════════════════════════════════════════════════════════════


class MomentGeneratingFunction:
    """
    MGF computation for common distributions.

    M(t) = E[e^(tX)] uniquely determines the distribution.
    Moments: E[X^n] = M^(n)(0) (n-th derivative at t=0)

    Key MGFs:
    - Normal: M(t) = exp(μt + σ²t²/2)
    - Exponential: M(t) = λ/(λ-t), t < λ
    - Poisson: M(t) = exp(λ(e^t - 1))
    - Gamma: M(t) = (β/(β-t))^α, t < β
    - Binomial: M(t) = (1-p+pe^t)^n
    """

    @staticmethod
    def normal_mgf(t: float, mu: float, sigma: float) -> float:
        """MGF of N(μ, σ²): exp(μt + σ²t²/2)"""
        return math.exp(mu * t + sigma**2 * t**2 / 2)

    @staticmethod
    def normal_moments(mu: float, sigma: float, order: int = 4) -> List[float]:
        """Compute moments of Normal from MGF derivatives."""
        moments = [mu]  # E[X] = μ
        if order >= 2:
            moments.append(sigma**2 + mu**2)  # E[X²] = σ² + μ²
        if order >= 3:
            moments.append(mu**3 + 3*mu*sigma**2)  # E[X³]
        if order >= 4:
            moments.append(mu**4 + 6*mu**2*sigma**2 + 3*sigma**4)  # E[X⁴]
        return moments

    @staticmethod
    def exponential_mgf(t: float, lam: float) -> Optional[float]:
        """MGF of Exp(λ): λ/(λ-t), t < λ"""
        if t >= lam:
            return None  # MGF undefined
        return lam / (lam - t)

    @staticmethod
    def poisson_mgf(t: float, lam: float) -> float:
        """MGF of Poisson(λ): exp(λ(e^t - 1))"""
        return math.exp(lam * (math.exp(t) - 1))

    @staticmethod
    def gamma_mgf(t: float, alpha: float, beta: float) -> Optional[float]:
        """MGF of Gamma(α, β): (β/(β-t))^α, t < β"""
        if t >= beta:
            return None
        return (beta / (beta - t)) ** alpha

    @staticmethod
    def binomial_mgf(t: float, n: int, p: float) -> float:
        """MGF of Binomial(n, p): (1-p+pe^t)^n"""
        return (1 - p + p * math.exp(t)) ** n

    @staticmethod
    def sample_mgf(data: np.ndarray, t_values: np.ndarray) -> np.ndarray:
        """Compute empirical MGF: M̂(t) = (1/n)Σ e^(txᵢ)"""
        return np.array([np.mean(np.exp(t * data)) for t in t_values])


# ════════════════════════════════════════════════════════════════
# 3. Central Limit Theorem
# ════════════════════════════════════════════════════════════════


class CentralLimitTheorem:
    """
    CLT demonstration and sampling distribution computation.

    Theorem: If X₁, ..., Xₙ are iid with mean μ and variance σ²,
    then √n(X̄ₙ - μ)/σ → N(0, 1) as n → ∞.

    Practical implications:
    - Sample means are approximately normal for n ≥ 30
    - Justifies z-tests and t-tests
    - Confidence intervals: X̄ ± z_{α/2} × σ/√n
    """

    @staticmethod
    def sampling_distribution(
        population: np.ndarray,
        sample_size: int,
        n_samples: int = 10000,
        statistic: str = "mean"
    ) -> Dict[str, Any]:
        """
        Demonstrate CLT by sampling from a population and computing
        the distribution of the sample statistic.

        Args:
            population: Full population data
            sample_size: Size of each sample
            n_samples: Number of samples to draw
            statistic: "mean", "median", or "variance"

        Returns:
            Dictionary with sampling distribution properties
        """
        pop = np.array(population, dtype=float)
        pop_mean = np.mean(pop)
        pop_var = np.var(pop, ddof=0)
        pop_std = np.std(pop, ddof=0)

        rng = np.random.default_rng(42)
        samples = rng.choice(pop, size=(n_samples, sample_size), replace=True)

        if statistic == "mean":
            sample_stats = np.mean(samples, axis=1)
            theoretical_se = pop_std / np.sqrt(sample_size)
        elif statistic == "median":
            sample_stats = np.median(samples, axis=1)
            theoretical_se = pop_std / np.sqrt(sample_size) * 1.253  # asymptotic SE of median
        elif statistic == "variance":
            sample_stats = np.var(samples, axis=1, ddof=1)
            theoretical_se = pop_var * np.sqrt(2.0 / (sample_size - 1))
        else:
            raise ValueError(f"Unknown statistic: {statistic}")

        sample_mean = np.mean(sample_stats)
        sample_se = np.std(sample_stats, ddof=1)

        # Normality check on sampling distribution
        if len(sample_stats) >= 20:
            _, shapiro_p = sp_stats.shapiro(sample_stats[:5000])
        else:
            shapiro_p = 0.0

        return {
            "statistic": statistic,
            "sample_size": sample_size,
            "n_samples": n_samples,
            "population_mean": float(pop_mean),
            "population_std": float(pop_std),
            "sampling_mean": float(sample_mean),
            "sampling_se": float(sample_se),
            "theoretical_se": float(theoretical_se),
            "se_ratio": float(sample_se / theoretical_se) if theoretical_se > 0 else 0,
            "is_normal": shapiro_p > 0.05,
            "shapiro_p_value": float(shapiro_p),
            "clt_holds": abs(sample_se - theoretical_se) / theoretical_se < 0.2 if theoretical_se > 0 else False,
        }

    @staticmethod
    def clt_confidence_interval(
        sample: np.ndarray,
        confidence: float = 0.95,
        population_std: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Compute CLT-based confidence interval for the population mean.

        If population σ is known: use z-interval
        If unknown: use t-interval (Welch's)
        """
        data = np.array(sample, dtype=float)
        n = len(data)
        x_bar = np.mean(data)
        alpha = 1 - confidence

        if population_std is not None:
            # z-interval
            se = population_std / np.sqrt(n)
            z_crit = sp_stats.norm.ppf(1 - alpha / 2)
            margin = z_crit * se
            method = "z-interval (σ known)"
        else:
            # t-interval
            s = np.std(data, ddof=1)
            se = s / np.sqrt(n)
            t_crit = sp_stats.t.ppf(1 - alpha / 2, df=n - 1)
            margin = t_crit * se
            method = "t-interval (σ unknown)"

        return {
            "mean": float(x_bar),
            "ci_lower": float(x_bar - margin),
            "ci_upper": float(x_bar + margin),
            "margin_of_error": float(margin),
            "se": float(se),
            "n": n,
            "confidence": confidence,
            "method": method,
        }


# ════════════════════════════════════════════════════════════════
# 4. Goodness-of-Fit Tests
# ════════════════════════════════════════════════════════════════


class GoodnessOfFit:
    """Goodness-of-fit tests for distribution validation."""

    @staticmethod
    def chi_squared_test(
        observed: np.ndarray,
        expected: np.ndarray,
        n_params_estimated: int = 0
    ) -> Dict[str, float]:
        """
        Chi-squared goodness-of-fit test.

        χ² = Σ (Oᵢ - Eᵢ)² / Eᵢ
        df = k - 1 - p (where p = number of estimated parameters)
        """
        obs = np.array(observed, dtype=float)
        exp = np.array(expected, dtype=float)
        mask = exp > 0
        chi_sq = np.sum((obs[mask] - exp[mask])**2 / exp[mask])
        k = np.sum(mask)
        df = max(k - 1 - n_params_estimated, 1)
        p_value = 1 - sp_stats.chi2.cdf(chi_sq, df)
        return {
            "chi_squared": float(chi_sq),
            "df": int(df),
            "p_value": float(p_value),
            "good_fit": p_value > 0.05,
        }

    @staticmethod
    def kolmogorov_smirnov_test(
        data: np.ndarray,
        distribution: str = "norm",
        params: Optional[Tuple] = None
    ) -> Dict[str, float]:
        """
        Kolmogorov-Smirnov test comparing empirical CDF to theoretical.
        """
        d = np.array(data, dtype=float)
        if params:
            stat, p = sp_stats.kstest(d, distribution, args=params)
        else:
            stat, p = sp_stats.kstest(d, distribution)
        return {
            "ks_statistic": float(stat),
            "p_value": float(p),
            "good_fit": p > 0.05,
        }

    @staticmethod
    def anderson_darling_test(data: np.ndarray) -> Dict[str, Any]:
        """
        Anderson-Darling test for normality.
        More sensitive to tail deviations than KS test.
        """
        result = sp_stats.anderson(data, dist='norm')
        return {
            "statistic": float(result.statistic),
            "critical_values": {str(s): float(c) for s, c in zip(result.significance_level, result.critical_values)},
            "is_normal_5pct": float(result.statistic) < float(result.critical_values[2]),  # 5% level
        }


# ════════════════════════════════════════════════════════════════
# 5. Parametric Bootstrap
# ════════════════════════════════════════════════════════════════


class ParametricBootstrap:
    """
    Parametric bootstrap: fit distribution, sample from fitted distribution,
    compute CI for any statistic.
    """

    @staticmethod
    def bootstrap_ci(
        data: np.ndarray,
        statistic_fn: callable,
        distribution: str = "normal",
        n_bootstrap: int = 10000,
        confidence: float = 0.95
    ) -> Dict[str, float]:
        """
        Parametric bootstrap CI.

        1. Fit distribution to data
        2. Sample from fitted distribution
        3. Compute statistic on each sample
        4. Take percentile CI
        """
        d = np.array(data, dtype=float)
        n = len(d)
        rng = np.random.default_rng(42)

        # Fit distribution
        if distribution == "normal":
            mu, sigma = np.mean(d), np.std(d, ddof=0)
            samples = rng.normal(mu, sigma, size=(n_bootstrap, n))
        elif distribution == "exponential":
            lam = 1.0 / np.mean(d)
            samples = rng.exponential(1.0/lam, size=(n_bootstrap, n))
        elif distribution == "gamma":
            a, loc, scale = sp_stats.gamma.fit(d, floc=0)
            samples = rng.gamma(a, scale=scale, size=(n_bootstrap, n))
        else:
            raise ValueError(f"Unsupported distribution: {distribution}")

        boot_stats = np.array([statistic_fn(s) for s in samples])
        alpha = 1 - confidence
        ci_lower = np.percentile(boot_stats, 100 * alpha / 2)
        ci_upper = np.percentile(boot_stats, 100 * (1 - alpha / 2))

        return {
            "estimate": float(statistic_fn(d)),
            "ci_lower": float(ci_lower),
            "ci_upper": float(ci_upper),
            "confidence": confidence,
            "bootstrap_se": float(np.std(boot_stats)),
            "n_bootstrap": n_bootstrap,
            "distribution": distribution,
        }


# ════════════════════════════════════════════════════════════════
# Runner Interface
# ════════════════════════════════════════════════════════════════


def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for the Rust bridge."""
    try:
        if method == "fit_distribution":
            data = np.array(args["data"], dtype=float)
            dist = args.get("distribution", "best")
            if dist == "best":
                result = DistributionFitter.fit_best(data)
            else:
                fitter = getattr(DistributionFitter, f"fit_{dist}", None)
                if fitter is None:
                    return {"error": f"Unknown distribution: {dist}"}
                result = fitter(data)
            return {
                "distribution": result.distribution,
                "parameters": result.parameters,
                "log_likelihood": result.log_likelihood,
                "aic": result.aic,
                "bic": result.bic,
                "n": result.n,
                "ks_statistic": result.ks_statistic,
                "ks_p_value": result.ks_p_value,
                "goodness_of_fit": result.goodness_of_fit,
            }

        elif method == "mgf":
            dist = args.get("distribution", "normal")
            t = args.get("t", 0.1)
            if dist == "normal":
                val = MomentGeneratingFunction.normal_mgf(t, args["mu"], args["sigma"])
            elif dist == "exponential":
                val = MomentGeneratingFunction.exponential_mgf(t, args["lambda"])
            elif dist == "poisson":
                val = MomentGeneratingFunction.poisson_mgf(t, args["lambda"])
            elif dist == "gamma":
                val = MomentGeneratingFunction.gamma_mgf(t, args["alpha"], args["beta"])
            elif dist == "binomial":
                val = MomentGeneratingFunction.binomial_mgf(t, args["n"], args["p"])
            else:
                return {"error": f"Unknown distribution: {dist}"}
            return {"mgf_value": val, "distribution": dist, "t": t}

        elif method == "clt_demo":
            data = np.array(args["data"], dtype=float)
            result = CentralLimitTheorem.sampling_distribution(
                data,
                sample_size=args.get("sample_size", 30),
                n_samples=args.get("n_samples", 10000),
                statistic=args.get("statistic", "mean"),
            )
            return result

        elif method == "clt_ci":
            data = np.array(args["data"], dtype=float)
            pop_std = args.get("population_std")
            result = CentralLimitTheorem.clt_confidence_interval(
                data,
                confidence=args.get("confidence", 0.95),
                population_std=pop_std,
            )
            return result

        elif method == "gof_chi_squared":
            obs = np.array(args["observed"], dtype=float)
            exp = np.array(args["expected"], dtype=float)
            return GoodnessOfFit.chi_squared_test(obs, exp, args.get("n_params", 0))

        elif method == "gof_ks":
            data = np.array(args["data"], dtype=float)
            return GoodnessOfFit.kolmogorov_smirnov_test(
                data, args.get("distribution", "norm"),
                tuple(args["params"]) if "params" in args else None
            )

        elif method == "gof_anderson_darling":
            data = np.array(args["data"], dtype=float)
            return GoodnessOfFit.anderson_darling_test(data)

        elif method == "parametric_bootstrap":
            data = np.array(args["data"], dtype=float)
            stat_name = args.get("statistic", "mean")
            stat_fn = {"mean": np.mean, "median": np.median, "std": np.std}.get(stat_name, np.mean)
            return ParametricBootstrap.bootstrap_ci(
                data, stat_fn,
                distribution=args.get("distribution", "normal"),
                n_bootstrap=args.get("n_bootstrap", 10000),
                confidence=args.get("confidence", 0.95),
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
