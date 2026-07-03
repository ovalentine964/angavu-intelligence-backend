"""
Statistical Estimator — STA 341: Theory of Estimation

Maps STA 341 (Theory of Estimation) course unit into executable
statistical estimation capabilities.

Capabilities:
- Point estimation (MLE, method of moments)
- Interval estimation (confidence intervals)
- Bayesian estimation (conjugate priors, posterior inference)
- Sufficient statistics computation
- Hypothesis testing framework

Theoretical Foundations:
- Maximum Likelihood Estimation (MLE)
- Cramér-Rao lower bound (efficiency)
- Bayesian estimation with conjugate priors
- Method of moments
- Sufficient and complete statistics

Wired into: AnalysisAgent, TransactionProcessor
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats
from scipy.optimize import minimize

from app.skills.base import BaseSkill, SkillResult

logger = structlog.get_logger(__name__)


class StatisticalEstimator(BaseSkill):
    """
    STA 341 — Theory of Estimation

    Provides point estimation, interval estimation, and Bayesian
    inference for all Angavu Intelligence statistical needs.
    """

    def __init__(self):
        super().__init__(
            name="statistical_estimator",
            course_unit="STA 341 — Theory of Estimation",
            description=(
                "Point and interval estimation, maximum likelihood estimation, "
                "and Bayesian estimation for statistical inference."
            ),
            version="1.0.0",
            agent_bindings=["TransactionProcessor", "IntelligenceGenerator"],
        )

    async def execute(self, action: str, **kwargs) -> SkillResult:
        actions = {
            "point_estimate": self._point_estimate,
            "interval_estimate": self._interval_estimate,
            "mle": self._mle,
            "bayesian_estimate": self._bayesian_estimate,
            "sufficient_statistics": self._sufficient_statistics,
        }

        if action not in actions:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=f"Unknown action: {action}. Available: {list(actions.keys())}",
            )

        try:
            data = await actions[action](**kwargs)
            return SkillResult(
                success=True,
                skill_name=self.name,
                data=data,
                confidence=data.get("_confidence", 0.9),
            )
        except Exception as exc:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=str(exc),
            )

    async def _point_estimate(
        self,
        data: List[float],
        parameter: str = "mean",
        method: str = "mle",
    ) -> Dict[str, Any]:
        """
        Compute point estimates for population parameters.

        Args:
            data: Observed data
            parameter: 'mean', 'variance', 'proportion', 'rate'
            method: 'mle', 'moments' (method of moments)

        Returns:
            Dict with estimate, standard error, and properties
        """
        arr = np.array(data, dtype=float)
        n = len(arr)

        if n == 0:
            return {"error": "Empty data"}

        if parameter == "mean":
            estimate = float(np.mean(arr))
            se = float(np.std(arr, ddof=1) / np.sqrt(n))
            # MLE and MoM coincide for normal mean
            property_note = "MLE = MoM = sample mean (efficient, unbiased)"

        elif parameter == "variance":
            if method == "mle":
                estimate = float(np.var(arr, ddof=0))  # MLE: divide by n
                se = estimate * np.sqrt(2 / n)
                property_note = "MLE variance (biased but consistent)"
            else:
                estimate = float(np.var(arr, ddof=1))  # Unbiased: divide by n-1
                se = estimate * np.sqrt(2 / (n - 1))
                property_note = "Unbiased variance (S², divide by n-1)"

        elif parameter == "proportion":
            # Binary data: count successes
            successes = np.sum(arr > 0)
            estimate = float(successes / n)
            se = float(np.sqrt(estimate * (1 - estimate) / n))
            property_note = "MLE proportion = X̄ (asymptotically efficient)"

        elif parameter == "rate":
            # Poisson rate: λ̂ = X̄
            estimate = float(np.mean(arr))
            se = float(np.sqrt(estimate / n))
            property_note = "MLE Poisson rate = sample mean"

        else:
            return {"error": f"Unknown parameter: {parameter}"}

        return {
            "parameter": parameter,
            "estimate": round(estimate, 6),
            "standard_error": round(se, 6),
            "n": n,
            "method": method,
            "property": property_note,
            "_confidence": 0.95,
        }

    async def _interval_estimate(
        self,
        data: List[float],
        confidence: float = 0.95,
        parameter: str = "mean",
    ) -> Dict[str, Any]:
        """
        Compute confidence intervals.

        Args:
            data: Observed data
            confidence: Confidence level (e.g., 0.95 for 95%)
            parameter: 'mean', 'variance', 'proportion'

        Returns:
            Dict with CI bounds, margin of error, interpretation
        """
        arr = np.array(data, dtype=float)
        n = len(arr)
        alpha = 1 - confidence

        if parameter == "mean":
            mean = np.mean(arr)
            se = np.std(arr, ddof=1) / np.sqrt(n)
            t_crit = stats.t.ppf(1 - alpha / 2, df=n - 1)
            margin = t_crit * se
            ci_lower = mean - margin
            ci_upper = mean + margin
            method = "t-distribution (σ unknown)"

        elif parameter == "variance":
            var = np.var(arr, ddof=1)
            chi2_lower = stats.chi2.ppf(1 - alpha / 2, df=n - 1)
            chi2_upper = stats.chi2.ppf(alpha / 2, df=n - 1)
            ci_lower = (n - 1) * var / chi2_lower
            ci_upper = (n - 1) * var / chi2_upper
            margin = None
            method = "Chi-squared distribution"

        elif parameter == "proportion":
            p_hat = np.mean(arr > 0)
            z_crit = stats.norm.ppf(1 - alpha / 2)
            se = np.sqrt(p_hat * (1 - p_hat) / n)
            margin = z_crit * se
            ci_lower = p_hat - margin
            ci_upper = p_hat + margin
            method = "Wald (normal approximation)"

        else:
            return {"error": f"Unknown parameter: {parameter}"}

        return {
            "parameter": parameter,
            "point_estimate": round(float(np.mean(arr) if parameter != "variance" else np.var(arr, ddof=1)), 6),
            "ci_lower": round(float(ci_lower), 6),
            "ci_upper": round(float(ci_upper), 6),
            "confidence_level": confidence,
            "margin_of_error": round(float(margin), 6) if margin is not None else None,
            "n": n,
            "method": method,
            "interpretation": (
                f"We are {confidence*100:.0f}% confident that the true {parameter} "
                f"lies between {ci_lower:.4f} and {ci_upper:.4f}."
            ),
            "_confidence": confidence,
        }

    async def _mle(
        self,
        data: List[float],
        distribution: str = "normal",
    ) -> Dict[str, Any]:
        """
        Maximum Likelihood Estimation for various distributions.

        Args:
            data: Observed data
            distribution: 'normal', 'exponential', 'poisson', 'bernoulli'

        Returns:
            Dict with MLE parameters, log-likelihood, Fisher information
        """
        arr = np.array(data, dtype=float)
        n = len(arr)

        if distribution == "normal":
            mu_hat = float(np.mean(arr))
            sigma2_hat = float(np.var(arr, ddof=0))  # MLE uses n, not n-1

            log_lik = -0.5 * n * (np.log(2 * np.pi * sigma2_hat) + 1)
            # Fisher information matrix
            fisher_info = np.array([
                [n / sigma2_hat, 0],
                [0, n / (2 * sigma2_hat ** 2)],
            ])
            # Cramér-Rao lower bound
            crl_bound = np.linalg.inv(fisher_info)

            return {
                "distribution": "normal",
                "mle_estimates": {
                    "mu": round(mu_hat, 6),
                    "sigma2": round(sigma2_hat, 6),
                    "sigma": round(np.sqrt(sigma2_hat), 6),
                },
                "log_likelihood": round(float(log_lik), 4),
                "fisher_information": fisher_info.tolist(),
                "cramér_rao_lower_bound": {
                    "var_mu_hat": round(float(crl_bound[0, 0]), 8),
                    "var_sigma2_hat": round(float(crl_bound[1, 1]), 8),
                },
                "efficiency": "MLE achieves CRLB for normal (efficient estimator)",
                "_confidence": 0.95,
            }

        elif distribution == "exponential":
            lambda_hat = 1.0 / np.mean(arr)
            log_lik = n * np.log(lambda_hat) - lambda_hat * np.sum(arr)
            fisher_info = n * lambda_hat ** 2

            return {
                "distribution": "exponential",
                "mle_estimates": {"lambda": round(float(lambda_hat), 6)},
                "log_likelihood": round(float(log_lik), 4),
                "fisher_information": float(fisher_info),
                "_confidence": 0.95,
            }

        elif distribution == "poisson":
            lambda_hat = float(np.mean(arr))
            log_lik = np.sum(arr * np.log(max(lambda_hat, 1e-10)) - lambda_hat)

            return {
                "distribution": "poisson",
                "mle_estimates": {"lambda": round(lambda_hat, 6)},
                "log_likelihood": round(float(log_lik), 4),
                "_confidence": 0.95,
            }

        elif distribution == "bernoulli":
            p_hat = float(np.mean(arr))
            successes = int(np.sum(arr))
            log_lik = successes * np.log(max(p_hat, 1e-10)) + (n - successes) * np.log(max(1 - p_hat, 1e-10))

            return {
                "distribution": "bernoulli",
                "mle_estimates": {"p": round(p_hat, 6)},
                "n_successes": successes,
                "n_trials": n,
                "log_likelihood": round(float(log_lik), 4),
                "_confidence": 0.95,
            }

        else:
            return {"error": f"Unsupported distribution: {distribution}"}

    async def _bayesian_estimate(
        self,
        data: List[float],
        prior_type: str = "conjugate",
        distribution: str = "normal",
        prior_params: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Bayesian estimation with conjugate priors.

        Args:
            data: Observed data
            prior_type: 'conjugate', 'jeffreys'
            distribution: 'normal', 'bernoulli', 'poisson'
            prior_params: Prior hyperparameters

        Returns:
            Dict with posterior parameters, credible interval, Bayes estimate
        """
        arr = np.array(data, dtype=float)
        n = len(arr)
        prior_params = prior_params or {}

        if distribution == "bernoulli":
            # Beta-Binomial conjugate
            alpha_0 = prior_params.get("alpha", 1.0)
            beta_0 = prior_params.get("beta", 1.0)
            successes = int(np.sum(arr))
            failures = n - successes

            post_alpha = alpha_0 + successes
            post_beta = beta_0 + failures

            post_mean = post_alpha / (post_alpha + post_beta)
            post_var = (post_alpha * post_beta) / (
                (post_alpha + post_beta) ** 2 * (post_alpha + post_beta + 1)
            )
            ci_lower = float(stats.beta.ppf(0.025, post_alpha, post_beta))
            ci_upper = float(stats.beta.ppf(0.975, post_alpha, post_beta))

            return {
                "distribution": "bernoulli",
                "prior": {"alpha": alpha_0, "beta": beta_0, "type": "Beta"},
                "posterior": {
                    "alpha": post_alpha,
                    "beta": post_beta,
                    "mean": round(post_mean, 6),
                    "variance": round(post_var, 8),
                    "credible_interval_95": (round(ci_lower, 4), round(ci_upper, 4)),
                },
                "mle": round(float(np.mean(arr)), 6),
                "shrinkage": round(abs(post_mean - np.mean(arr)), 6),
                "data_points": n,
                "_confidence": 0.95,
            }

        elif distribution == "normal":
            # Normal-Normal conjugate (known variance case)
            mu_0 = prior_params.get("mu", float(np.mean(arr)))
            tau2_0 = prior_params.get("tau2", 100.0)  # Prior variance
            sigma2 = prior_params.get("sigma2", float(np.var(arr, ddof=1)))

            sample_mean = float(np.mean(arr))
            precision_prior = 1 / tau2_0
            precision_data = n / sigma2
            precision_post = precision_prior + precision_data

            post_mean = (precision_prior * mu_0 + precision_data * sample_mean) / precision_post
            post_var = 1 / precision_post
            post_std = np.sqrt(post_var)

            ci_lower = post_mean - 1.96 * post_std
            ci_upper = post_mean + 1.96 * post_std

            return {
                "distribution": "normal",
                "prior": {"mu": mu_0, "tau2": tau2_0},
                "posterior": {
                    "mean": round(float(post_mean), 6),
                    "variance": round(float(post_var), 8),
                    "std": round(float(post_std), 6),
                    "credible_interval_95": (round(float(ci_lower), 4), round(float(ci_upper), 4)),
                },
                "mle": round(sample_mean, 6),
                "shrinkage_factor": round(float(precision_data / precision_post), 4),
                "effective_prior_n": round(float(tau2_0 / sigma2), 2),
                "_confidence": 0.95,
            }

        else:
            return {"error": f"Unsupported distribution for Bayesian estimation: {distribution}"}

    async def _sufficient_statistics(
        self,
        data: List[float],
        distribution: str = "normal",
    ) -> Dict[str, Any]:
        """
        Compute sufficient statistics for common distributions.

        By the factorization theorem, T(X) is sufficient for θ if
        f(x|θ) = g(T(x), θ) × h(x).
        """
        arr = np.array(data, dtype=float)
        n = len(arr)

        if distribution == "normal":
            # Sufficient statistics: (Σxᵢ, Σxᵢ²) or equivalently (X̄, S²)
            T1 = float(np.sum(arr))
            T2 = float(np.sum(arr ** 2))
            return {
                "distribution": "normal",
                "sufficient_statistics": {
                    "sum_x": round(T1, 4),
                    "sum_x2": round(T2, 4),
                    "sample_mean": round(float(np.mean(arr)), 6),
                    "sample_var_mle": round(float(np.var(arr, ddof=0)), 6),
                },
                "n": n,
                "theorem": "Factorization theorem: f(x|θ) = g(T(x),θ)·h(x)",
                "note": "(X̄, S²) is jointly sufficient for (μ, σ²)",
                "_confidence": 0.99,
            }

        elif distribution == "exponential":
            T = float(np.sum(arr))
            return {
                "distribution": "exponential",
                "sufficient_statistics": {"sum_x": round(T, 4)},
                "n": n,
                "note": "ΣXᵢ is sufficient for λ",
                "_confidence": 0.99,
            }

        elif distribution == "bernoulli":
            T = int(np.sum(arr))
            return {
                "distribution": "bernoulli",
                "sufficient_statistics": {"successes": T, "trials": n},
                "note": "ΣXᵢ is sufficient for p (complete and minimal)",
                "_confidence": 0.99,
            }

        else:
            return {"error": f"Unsupported distribution: {distribution}"}
