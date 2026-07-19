"""
Bayesian Statistics Module — STA 341 Theory of Estimation.

Extracted from statistical_foundation.py for modularity.

Implements Bayesian estimation framework used by all intelligence products:
- Beta-Binomial conjugate updating (Alama Score default probability)
- Normal-Normal conjugate updating (Soko Pulse price estimation)

Academic Foundation:
- STA 341: Theory of Estimation → Bayesian estimation, conjugate priors,
  posterior predictive distributions, credible intervals
- STA 241: Probability → Prior distributions, likelihood functions

Bayes' theorem: p(θ|x) = [f(x|θ) × p(θ)] / m(x)
"""


import numpy as np
import structlog
from scipy import stats

logger = structlog.get_logger(__name__)


class BayesianUpdater:
    """
    Bayesian estimation framework (STA 341 — Theory of Estimation).

    Implements Bayes' theorem: p(θ|x) = [f(x|θ) × p(θ)] / m(x)

    Used by:
    - Alama Score: Credit scoring with limited data (Beta-Binomial model)
    - Soko Pulse: Price estimation with prior market knowledge
    - Jamii Insights: Financial inclusion estimation with demographic priors

    The posterior mean is a weighted average of prior mean and MLE:
    θ̂_Bayes = [n/(n+n₀)] × θ̂_MLE + [n₀/(n+n₀)] × θ_prior
    where n₀ is the "prior sample size."
    """

    @staticmethod
    def beta_binomial_update(
        prior_alpha: float,
        prior_beta: float,
        successes: int,
        failures: int,
    ) -> tuple[float, float, dict[str, float]]:
        """
        Beta-Binomial conjugate update.

        Prior: θ ~ Beta(α, β)
        Likelihood: X ~ Binomial(n, θ)
        Posterior: θ|X ~ Beta(α + successes, β + failures)

        Args:
            prior_alpha: Prior Beta alpha parameter
            prior_beta: Prior Beta beta parameter
            successes: Number of observed successes
            failures: Number of observed failures

        Returns:
            Tuple of (posterior_alpha, posterior_beta, summary_dict)
        """
        post_alpha = prior_alpha + successes
        post_beta = prior_beta + failures

        post_mean = post_alpha / (post_alpha + post_beta)
        post_var = (post_alpha * post_beta) / (
            (post_alpha + post_beta) ** 2 * (post_alpha + post_beta + 1)
        )
        post_std = np.sqrt(post_var)

        ci_lower = stats.beta.ppf(0.025, post_alpha, post_beta)
        ci_upper = stats.beta.ppf(0.975, post_alpha, post_beta)

        summary = {
            "posterior_mean": round(post_mean, 4),
            "posterior_std": round(post_std, 4),
            "credible_interval_95": (round(ci_lower, 4), round(ci_upper, 4)),
            "prior_mean": round(prior_alpha / (prior_alpha + prior_beta), 4),
            "prior_sample_size": prior_alpha + prior_beta,
            "data_points": successes + failures,
            "effective_sample_size": post_alpha + post_beta,
        }

        return post_alpha, post_beta, summary

    @staticmethod
    def normal_normal_update(
        prior_mean: float,
        prior_var: float,
        data_mean: float,
        data_var: float,
        n: int,
    ) -> tuple[float, float, dict[str, float]]:
        """
        Normal-Normal conjugate update.

        Prior: θ ~ N(μ₀, σ₀²)
        Likelihood: X̄|θ ~ N(θ, σ²/n)
        Posterior: θ|X̄ ~ N(μₙ, σₙ²)

        Args:
            prior_mean: Prior mean
            prior_var: Prior variance
            data_mean: Sample mean
            data_var: Population variance
            n: Sample size

        Returns:
            Tuple of (posterior_mean, posterior_var, summary_dict)
        """
        prior_precision = 1 / prior_var
        data_precision = n / data_var

        post_precision = prior_precision + data_precision
        post_var = 1 / post_precision
        post_mean = (
            prior_precision * prior_mean + data_precision * data_mean
        ) / post_precision
        post_std = np.sqrt(post_var)

        ci_lower = post_mean - 1.96 * post_std
        ci_upper = post_mean + 1.96 * post_std

        summary = {
            "posterior_mean": round(post_mean, 4),
            "posterior_std": round(post_std, 4),
            "credible_interval_95": (round(ci_lower, 4), round(ci_upper, 4)),
            "prior_mean": prior_mean,
            "prior_std": np.sqrt(prior_var),
            "data_mean": data_mean,
            "data_points": n,
            "shrinkage_factor": round(data_precision / post_precision, 4),
        }

        return post_mean, post_var, summary
