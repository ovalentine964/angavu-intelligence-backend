"""
Monte Carlo Simulation & MCMC Sampling (STA 347 — Stochastic Processes).

Classes:
- MonteCarloEngine: Crude MC integration, importance sampling, bootstrap testing,
  revenue distribution simulation
- MCMCSampler: Metropolis-Hastings sampling with convergence diagnostics

Decomposed from statistical_foundation.py for maintainability.
"""

from typing import Any, Callable, Dict, List, Optional

import numpy as np
from scipy import stats


class MonteCarloEngine:
    """
    Monte Carlo simulation methods (STA 347 — Stochastic Processes).

    Simulation-based inference when analytical solutions are intractable.
    """

    @staticmethod
    def crude_integration(
        func: Callable,
        lower: float,
        upper: float,
        n_samples: int = 100000,
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Crude Monte Carlo integration.

        Estimates ∫_a^b f(x) dx ≈ (b-a)/n Σᵢ f(Xᵢ)
        where Xᵢ ~ Uniform(a, b).
        """
        rng = np.random.RandomState(seed)
        samples = rng.uniform(lower, upper, size=n_samples)
        func_values = np.array([func(x) for x in samples])

        interval_length: float = upper - lower
        estimate: float = interval_length * float(np.mean(func_values))
        se: float = interval_length * float(np.std(func_values)) / np.sqrt(n_samples)

        return {
            "estimate": round(estimate, 6),
            "standard_error": round(se, 6),
            "ci_lower": round(estimate - 1.96 * se, 6),
            "ci_upper": round(estimate + 1.96 * se, 6),
            "n_samples": n_samples,
            "method": "crude_monte_carlo",
        }

    @staticmethod
    def importance_sampling(
        func: Callable,
        proposal_sampler: Callable,
        proposal_pdf: Callable,
        target_pdf: Optional[Callable] = None,
        n_samples: int = 100000,
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Importance sampling for variance reduction.

        Estimates E_p[f(X)] ≈ (1/n) Σᵢ f(Xᵢ)·w(Xᵢ)
        where w(x) = p(x)/q(x).
        """
        rng = np.random.RandomState(seed)
        samples = proposal_sampler(n_samples, rng)

        func_values = np.array([func(x) for x in samples])
        proposal_vals = np.maximum(np.array([proposal_pdf(x) for x in samples]), 1e-300)

        if target_pdf is not None:
            target_vals = np.array([target_pdf(x) for x in samples])
            weights = target_vals / proposal_vals
        else:
            weights = 1.0 / proposal_vals

        weights_normalized = weights / weights.sum()
        estimate: float = float(np.sum(weights_normalized * func_values))
        ess: float = 1.0 / float(np.sum(weights_normalized ** 2))
        weighted_var: float = float(np.sum(weights_normalized * (func_values - estimate) ** 2))
        se: float = float(np.sqrt(weighted_var / ess))

        return {
            "estimate": round(estimate, 6),
            "standard_error": round(se, 6),
            "ci_lower": round(estimate - 1.96 * se, 6),
            "ci_upper": round(estimate + 1.96 * se, 6),
            "effective_sample_size": round(ess, 1),
            "efficiency": round(ess / n_samples, 4),
            "n_samples": n_samples,
            "method": "importance_sampling",
        }

    @staticmethod
    def bootstrap_hypothesis_test(
        sample1: np.ndarray,
        sample2: np.ndarray,
        statistic_func: Callable,
        n_bootstrap: int = 10000,
        alternative: str = "two-sided",
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Bootstrap/permutation hypothesis test.

        Tests H₀: θ₁ = θ₂ without distributional assumptions.
        """
        sample1 = np.asarray(sample1, dtype=float)
        sample2 = np.asarray(sample2, dtype=float)
        rng = np.random.RandomState(seed)

        n1: int = len(sample1)
        n2: int = len(sample2)
        observed_diff: float = float(statistic_func(sample1) - statistic_func(sample2))

        pooled = np.concatenate([sample1, sample2])
        n_total: int = n1 + n2

        perm_stats = np.zeros(n_bootstrap)
        for i in range(n_bootstrap):
            perm = rng.permutation(n_total)
            s1_perm = pooled[perm[:n1]]
            s2_perm = pooled[perm[n1:]]
            perm_stats[i] = statistic_func(s1_perm) - statistic_func(s2_perm)

        if alternative == "two-sided":
            p_value: float = float(np.mean(np.abs(perm_stats) >= np.abs(observed_diff)))
        elif alternative == "greater":
            p_value = float(np.mean(perm_stats >= observed_diff))
        elif alternative == "less":
            p_value = float(np.mean(perm_stats <= observed_diff))
        else:
            raise ValueError(f"Unknown alternative: {alternative}")

        return {
            "observed_statistic": round(observed_diff, 4),
            "p_value": round(p_value, 6),
            "significant_at_05": p_value < 0.05,
            "significant_at_01": p_value < 0.01,
            "n_bootstrap": n_bootstrap,
            "alternative": alternative,
            "permutation_mean": round(float(np.mean(perm_stats)), 4),
            "permutation_std": round(float(np.std(perm_stats)), 4),
            "test_name": "Permutation/bootstrap hypothesis test",
            "interpretation": (
                f"{'Reject' if p_value < 0.05 else 'Fail to reject'} null hypothesis "
                f"at 5% significance (p={p_value:.4f})"
            ),
        }

    @staticmethod
    def simulation_confidence_interval(
        data: np.ndarray,
        statistic_func: Callable,
        n_simulations: int = 10000,
        confidence: float = 0.95,
        method: str = "percentile",
        seed: int = 42,
    ) -> Dict[str, float]:
        """
        Simulation-based confidence intervals.

        Supports: 'percentile', 'bc' (bias-corrected), 'bca' (BCa).
        """
        data = np.asarray(data, dtype=float)
        rng = np.random.RandomState(seed)
        n: int = len(data)
        alpha: float = 1 - confidence

        original_stat: float = float(statistic_func(data))
        boot_stats = np.zeros(n_simulations)

        for i in range(n_simulations):
            sample = rng.choice(data, size=n, replace=True)
            boot_stats[i] = statistic_func(sample)

        if method == "percentile":
            ci_lower: float = float(np.percentile(boot_stats, 100 * alpha / 2))
            ci_upper: float = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))
        elif method == "bc":
            z0: float = float(stats.norm.ppf(np.mean(boot_stats < original_stat)))
            z_alpha = stats.norm.ppf([alpha / 2, 1 - alpha / 2])
            p_vals = stats.norm.cdf(2 * z0 + z_alpha)
            ci_lower = float(np.percentile(boot_stats, 100 * p_vals[0]))
            ci_upper = float(np.percentile(boot_stats, 100 * p_vals[1]))
        elif method == "bca":
            z0 = float(stats.norm.ppf(np.mean(boot_stats < original_stat)))
            jackknife_stats = np.zeros(n)
            for i in range(n):
                jack_sample = np.delete(data, i)
                jackknife_stats[i] = statistic_func(jack_sample)
            jack_mean: float = float(np.mean(jackknife_stats))
            numer: float = float(np.sum((jack_mean - jackknife_stats) ** 3))
            denom: float = float(6 * (np.sum((jack_mean - jackknife_stats) ** 2) ** 1.5))
            a_hat: float = numer / denom if abs(denom) > 1e-12 else 0.0

            z_alpha = stats.norm.ppf([alpha / 2, 1 - alpha / 2])
            p_vals = stats.norm.cdf(z0 + (z0 + z_alpha) / (1 - a_hat * (z0 + z_alpha)))
            ci_lower = float(np.percentile(boot_stats, 100 * p_vals[0]))
            ci_upper = float(np.percentile(boot_stats, 100 * p_vals[1]))
        else:
            raise ValueError(f"Unknown CI method: {method}")

        return {
            "estimate": round(original_stat, 4),
            "ci_lower": round(ci_lower, 4),
            "ci_upper": round(ci_upper, 4),
            "bootstrap_se": round(float(np.std(boot_stats)), 4),
            "confidence": confidence,
            "method": method,
            "n_simulations": n_simulations,
        }

    @staticmethod
    def revenue_distribution_simulation(
        base_revenue: float,
        growth_mean: float,
        growth_std: float,
        n_periods: int = 12,
        n_simulations: int = 10000,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Simulate revenue distribution via geometric Brownian motion.

        R(t+1) = R(t) · exp((μ - σ²/2)·dt + σ·√dt·Z)
        """
        rng = np.random.RandomState(seed)

        dt: float = 1.0 / 12
        paths = np.zeros((n_simulations, n_periods + 1))
        paths[:, 0] = base_revenue

        for t in range(n_periods):
            z = rng.randn(n_simulations)
            paths[:, t + 1] = paths[:, t] * np.exp(
                (growth_mean - 0.5 * growth_std ** 2) * dt + growth_std * np.sqrt(dt) * z
            )

        terminal = paths[:, -1]

        return {
            "base_revenue": base_revenue,
            "terminal_mean": round(float(np.mean(terminal)), 2),
            "terminal_median": round(float(np.median(terminal)), 2),
            "terminal_std": round(float(np.std(terminal)), 2),
            "percentile_5": round(float(np.percentile(terminal, 5)), 2),
            "percentile_25": round(float(np.percentile(terminal, 25)), 2),
            "percentile_75": round(float(np.percentile(terminal, 75)), 2),
            "percentile_95": round(float(np.percentile(terminal, 95)), 2),
            "prob_decline": round(float(np.mean(terminal < base_revenue)), 4),
            "prob_growth_10pct": round(float(np.mean(terminal > base_revenue * 1.1)), 4),
            "n_periods": n_periods,
            "n_simulations": n_simulations,
            "growth_mean": growth_mean,
            "growth_std": growth_std,
        }


class MCMCSampler:
    """
    Markov Chain Monte Carlo sampling (STA 347).

    Metropolis-Hastings algorithm for drawing samples from
    arbitrary (unnormalised) posterior distributions.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.RandomState(seed)

    def metropolis_hastings(
        self,
        log_target: Callable,
        initial_state: np.ndarray,
        n_samples: int = 10000,
        proposal_std: Optional[np.ndarray] = None,
        burn_in: int = 1000,
        thin: int = 1,
    ) -> Dict[str, Any]:
        """
        Metropolis-Hastings sampler with random walk proposal.

        Proposal: θ* = θₜ + ε, where ε ~ N(0, Σ)
        Acceptance: α = min(1, π(θ*) / π(θₜ))
        """
        initial_state = np.asarray(initial_state, dtype=float)
        dim: int = len(initial_state)

        if proposal_std is None:
            proposal_std = np.maximum(0.1 * np.abs(initial_state), 0.1)
        else:
            proposal_std = np.asarray(proposal_std, dtype=float)

        all_samples = np.zeros((n_samples, dim))
        current = initial_state.copy()
        current_log_prob: float = float(log_target(current))
        n_accepted: int = 0

        for i in range(n_samples):
            proposal = current + self.rng.randn(dim) * proposal_std
            proposal_log_prob: float = float(log_target(proposal))
            log_alpha: float = proposal_log_prob - current_log_prob

            if np.log(self.rng.rand()) < log_alpha:
                current = proposal
                current_log_prob = proposal_log_prob
                n_accepted += 1

            all_samples[i] = current

        post_burnin = all_samples[burn_in:]
        thinned = post_burnin[::thin]
        acceptance_rate: float = n_accepted / n_samples

        summary: List[Dict[str, Any]] = []
        for d in range(dim):
            chain = thinned[:, d]
            summary.append({
                "mean": round(float(np.mean(chain)), 4),
                "std": round(float(np.std(chain)), 4),
                "median": round(float(np.median(chain)), 4),
                "ci_95": (
                    round(float(np.percentile(chain, 2.5)), 4),
                    round(float(np.percentile(chain, 97.5)), 4),
                ),
            })

        return {
            "samples": thinned,
            "n_samples_effective": len(thinned),
            "acceptance_rate": round(acceptance_rate, 4),
            "burn_in": burn_in,
            "thin": thin,
            "n_total_iterations": n_samples,
            "summary": summary,
            "convergence": self._check_convergence_single(thinned),
        }

    @staticmethod
    def gelman_rubin_rhat(chains: List[np.ndarray]) -> Dict[str, Any]:
        """
        Gelman-Rubin R-hat convergence diagnostic.

        R-hat < 1.1 generally indicates convergence.
        """
        if len(chains) < 2:
            raise ValueError("Need at least 2 chains for R-hat diagnostic")

        chains = [np.asarray(c) for c in chains]
        n_chains: int = len(chains)
        n_samples: int = chains[0].shape[0]
        dim: int = chains[0].shape[1] if chains[0].ndim > 1 else 1

        rhat_values: List[float] = []

        for d in range(dim):
            if dim > 1:
                chain_data = [c[:, d] for c in chains]
            else:
                chain_data = [c.ravel() for c in chains]

            chain_means = [float(np.mean(c)) for c in chain_data]
            chain_vars = [float(np.var(c, ddof=1)) for c in chain_data]

            W: float = float(np.mean(chain_vars))
            B: float = n_samples * float(np.var(chain_means, ddof=1))
            var_hat: float = ((n_samples - 1) / n_samples) * W + B / n_samples

            rhat: float = float(np.sqrt(var_hat / W)) if W > 0 else float("inf")
            rhat_values.append(round(rhat, 4))

        max_rhat: float = max(rhat_values)
        converged: bool = max_rhat < 1.1

        return {
            "rhat_per_dimension": rhat_values,
            "rhat_max": round(max_rhat, 4),
            "converged": converged,
            "threshold": 1.1,
            "n_chains": n_chains,
            "n_samples_per_chain": n_samples,
            "diagnostic": "Gelman-Rubin (1992)",
            "interpretation": (
                f"{'Converged' if converged else 'NOT converged'}: "
                f"max R-hat = {max_rhat:.4f} ({'< 1.1 ✓' if converged else '≥ 1.1 ✗'})"
            ),
        }

    @staticmethod
    def _check_convergence_single(samples: np.ndarray) -> Dict[str, Any]:
        """Basic convergence diagnostics for a single chain."""
        if samples.ndim == 1:
            samples = samples.reshape(-1, 1)

        n, dim = samples.shape

        diagnostics: List[Dict[str, Any]] = []
        for d in range(dim):
            chain = samples[:, d]
            n_chain: int = len(chain)

            max_lag: int = min(n_chain // 2, 200)
            acf_vals: List[float] = []
            mean: float = float(np.mean(chain))
            var: float = float(np.var(chain, ddof=1))
            if var > 0:
                for lag in range(max_lag):
                    acf: float = float(np.mean((chain[:n_chain - lag] - mean) * (chain[lag:] - mean)) / var)
                    acf_vals.append(acf)
                    if acf < 0:
                        break
                tau: float = 1 + 2 * sum(acf_vals[1:]) if len(acf_vals) > 1 else 1.0
                ess: float = n_chain / max(tau, 1.0)
            else:
                ess = float(n_chain)

            n1: int = max(int(0.1 * n_chain), 10)
            n2: int = max(int(0.5 * n_chain), 10)
            first_part = chain[:n1]
            last_part = chain[-n2:]
            mean_diff: float = float(np.mean(first_part) - np.mean(last_part))
            se_diff: float = float(np.sqrt(
                np.var(first_part, ddof=1) / n1 + np.var(last_part, ddof=1) / n2
            ))
            geweke_z: float = mean_diff / se_diff if se_diff > 0 else 0.0
            geweke_p: float = 2 * (1 - float(stats.norm.cdf(abs(geweke_z))))

            diagnostics.append({
                "dimension": d,
                "effective_sample_size": round(ess, 1),
                "ess_ratio": round(ess / n_chain, 4),
                "geweke_z": round(geweke_z, 4),
                "geweke_p_value": round(geweke_p, 4),
                "geweke_converged": geweke_p > 0.05,
            })

        return {
            "per_dimension": diagnostics,
            "all_converged": all(d["geweke_converged"] for d in diagnostics),
        }


__all__ = ["MonteCarloEngine", "MCMCSampler"]
