"""
Econometric Methods Module — Monte Carlo & MCMC Simulation.

Extracted from statistical_foundation.py for modularity.

Provides simulation-based inference for financial risk assessment,
revenue forecasting, and Bayesian posterior sampling.

Classes:
- MonteCarloEngine: Monte Carlo simulation for revenue/credit risk
- MCMCSampler: Markov Chain Monte Carlo for Bayesian posterior sampling

Academic Foundation:
- STA 347: Stochastic Processes → Monte Carlo methods, GBM simulation
- STA 341: Theory of Estimation → MCMC for posterior inference
- ECO 424: Econometrics → Simulation-based estimation
"""

from typing import Any, Dict, List, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class MonteCarloEngine:
    """
    Monte Carlo simulation methods (STA 347 — Stochastic Processes).

    Provides simulation-based inference when analytical solutions are
    intractable or when full distributional characterisation is needed.
    """

    @staticmethod
    def crude_integration(
        func: callable,
        bounds: List[tuple],
        n_samples: int = 100000,
        seed: int = 42,
    ) -> Dict[str, float]:
        """Crude Monte Carlo integration."""
        rng = np.random.RandomState(seed)
        dim = len(bounds)
        samples = np.zeros((n_samples, dim))
        for d, (lo, hi) in enumerate(bounds):
            samples[:, d] = rng.uniform(lo, hi, n_samples)

        func_vals = np.array([func(s) for s in samples])
        volume = np.prod([hi - lo for lo, hi in bounds])
        estimate = volume * np.mean(func_vals)
        std_error = volume * np.std(func_vals) / np.sqrt(n_samples)

        return {
            "estimate": round(float(estimate), 6),
            "std_error": round(float(std_error), 6),
            "ci_95": (
                round(float(estimate - 1.96 * std_error), 6),
                round(float(estimate + 1.96 * std_error), 6),
            ),
            "n_samples": n_samples,
        }

    @staticmethod
    def importance_sampling(
        target_log_prob: callable,
        proposal_sampler: callable,
        proposal_log_prob: callable,
        statistic_func: callable,
        n_samples: int = 10000,
        seed: int = 42,
    ) -> Dict[str, float]:
        """Importance sampling estimator."""
        rng = np.random.RandomState(seed)
        samples = proposal_sampler(n_samples)
        log_weights = np.array([
            target_log_prob(x) - proposal_log_prob(x) for x in samples
        ])
        log_weights -= np.max(log_weights)
        weights = np.exp(log_weights)
        weights /= np.sum(weights)

        func_vals = np.array([statistic_func(s) for s in samples])
        estimate = np.sum(weights * func_vals)

        return {
            "estimate": round(float(estimate), 6),
            "effective_sample_size": round(float(1.0 / np.sum(weights ** 2)), 0),
            "n_samples": n_samples,
        }

    @staticmethod
    def bootstrap_hypothesis_test(
        sample1: np.ndarray,
        sample2: np.ndarray,
        statistic_func: callable = None,
        n_bootstrap: int = 10000,
        alternative: str = "two-sided",
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Bootstrap permutation hypothesis test."""
        if statistic_func is None:
            statistic_func = lambda x: np.mean(x)

        rng = np.random.RandomState(seed)
        observed = float(statistic_func(sample1) - statistic_func(sample2))
        combined = np.concatenate([sample1, sample2])
        n1 = len(sample1)

        count = 0
        boot_stats = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            perm = rng.permutation(combined)
            perm_s1 = perm[:n1]
            perm_s2 = perm[n1:]
            diff = float(statistic_func(perm_s1) - statistic_func(perm_s2))
            boot_stats[i] = diff
            if alternative == "two-sided":
                if abs(diff) >= abs(observed):
                    count += 1
            elif alternative == "greater":
                if diff >= observed:
                    count += 1
            elif alternative == "less":
                if diff <= observed:
                    count += 1

        p_value = count / n_bootstrap

        return {
            "observed_statistic": round(observed, 6),
            "p_value": round(p_value, 6),
            "significant_at_05": p_value < 0.05,
            "n_bootstrap": n_bootstrap,
            "alternative": alternative,
            "interpretation": (
                f"{'Reject' if p_value < 0.05 else 'Fail to reject'} null hypothesis "
                f"(p={p_value:.4f}, {n_bootstrap} permutations)"
            ),
        }

    @staticmethod
    def simulation_confidence_interval(
        simulate_func: callable,
        n_simulations: int = 10000,
        confidence: float = 0.95,
        seed: int = 42,
    ) -> Dict[str, float]:
        """Simulation-based confidence interval."""
        rng = np.random.RandomState(seed)
        results = np.array([simulate_func(rng) for _ in range(n_simulations)])
        alpha = 1 - confidence
        ci_lower = np.percentile(results, 100 * alpha / 2)
        ci_upper = np.percentile(results, 100 * (1 - alpha / 2))

        return {
            "mean": round(float(np.mean(results)), 4),
            "std": round(float(np.std(results)), 4),
            "ci_lower": round(float(ci_lower), 4),
            "ci_upper": round(float(ci_upper), 4),
            "median": round(float(np.median(results)), 4),
            "n_simulations": n_simulations,
            "confidence": confidence,
        }

    @staticmethod
    def revenue_distribution_simulation(
        base_revenue: float,
        growth_mean: float = 0.02,
        growth_std: float = 0.1,
        n_periods: int = 12,
        n_simulations: int = 10000,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Revenue distribution simulation using Geometric Brownian Motion.

        dR = μ·R·dt + σ·R·dW

        Used by Alama Score for probabilistic credit risk assessment.
        """
        rng = np.random.RandomState(seed)
        dt = 1.0
        paths = np.zeros((n_simulations, n_periods + 1))
        paths[:, 0] = base_revenue

        for t in range(1, n_periods + 1):
            z = rng.standard_normal(n_simulations)
            paths[:, t] = paths[:, t - 1] * np.exp(
                (growth_mean - 0.5 * growth_std ** 2) * dt + growth_std * np.sqrt(dt) * z
            )

        terminal = paths[:, -1]
        returns = (terminal - base_revenue) / base_revenue

        return {
            "base_revenue": base_revenue,
            "terminal_mean": round(float(np.mean(terminal)), 2),
            "terminal_median": round(float(np.median(terminal)), 2),
            "terminal_std": round(float(np.std(terminal)), 2),
            "percentile_5": round(float(np.percentile(terminal, 5)), 2),
            "percentile_95": round(float(np.percentile(terminal, 95)), 2),
            "prob_decline": round(float(np.mean(returns < 0)), 4),
            "prob_growth_10pct": round(float(np.mean(returns > 0.1)), 4),
            "n_simulations": n_simulations,
            "n_periods": n_periods,
        }


class MCMCSampler:
    """
    Markov Chain Monte Carlo sampler (STA 341 — Theory of Estimation).

    Metropolis-Hastings algorithm for sampling from arbitrary
    posterior distributions when conjugate priors aren't available.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.RandomState(seed)

    def metropolis_hastings(
        self,
        log_target: callable,
        initial_state: np.ndarray,
        proposal_std: float = 0.1,
        n_samples: int = 10000,
        burn_in: int = 1000,
        thin: int = 1,
    ) -> Dict[str, Any]:
        """Metropolis-Hastings MCMC sampler."""
        dim = len(initial_state)
        samples = np.zeros((n_samples, dim))
        current = initial_state.copy()
        current_log_prob = log_target(current)
        n_accepted = 0

        for i in range(n_samples):
            proposal = current + self.rng.normal(0, proposal_std, dim)
            proposal_log_prob = log_target(proposal)
            log_alpha = proposal_log_prob - current_log_prob

            if np.log(self.rng.uniform()) < log_alpha:
                current = proposal
                current_log_prob = proposal_log_prob
                n_accepted += 1

            samples[i] = current

        # Apply burn-in and thinning
        samples = samples[burn_in::thin]
        acceptance_rate = n_accepted / n_samples

        return {
            "samples": samples,
            "acceptance_rate": round(acceptance_rate, 4),
            "n_samples": len(samples),
            "burn_in": burn_in,
            "thin": thin,
            "means": [round(float(np.mean(samples[:, d])), 4) for d in range(dim)],
            "stds": [round(float(np.std(samples[:, d])), 4) for d in range(dim)],
        }

    @staticmethod
    def gelman_rubin_rhat(chains: List[np.ndarray]) -> Dict[str, Any]:
        """Gelman-Rubin R-hat convergence diagnostic."""
        m = len(chains)
        if m < 2:
            return {"error": "Need at least 2 chains"}

        n = min(len(c) for c in chains)
        chains = [c[:n] for c in chains]
        dim = chains[0].shape[1] if chains[0].ndim > 1 else 1

        rhat_values = []
        for d in range(dim):
            if dim > 1:
                chain_means = [np.mean(c[:, d]) for c in chains]
                chain_vars = [np.var(c[:, d], ddof=1) for c in chains]
                grand_mean = np.mean(chain_means)
            else:
                chain_means = [np.mean(c) for c in chains]
                chain_vars = [np.var(c, ddof=1) for c in chains]
                grand_mean = np.mean(chain_means)

            B = n * np.var(chain_means, ddof=1)
            W = np.mean(chain_vars)
            var_hat = (1 - 1 / n) * W + B / n
            rhat = np.sqrt(var_hat / max(W, 1e-10))
            rhat_values.append(round(float(rhat), 4))

        return {
            "rhat": rhat_values[0] if len(rhat_values) == 1 else rhat_values,
            "converged": all(r < 1.1 for r in rhat_values),
            "n_chains": m,
            "n_samples_per_chain": n,
        }
