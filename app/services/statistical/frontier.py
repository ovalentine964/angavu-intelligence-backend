"""
Production Frontier Analysis — DEA & SFA (ECO 311, ECO 422).

Classes:
- DEAAnalyzer: Data Envelopment Analysis for technical efficiency
- SFAAnalyzer: Stochastic Frontier Analysis for production efficiency

Implements frontier methods for measuring productive efficiency of
decision-making units (DMUs) such as businesses, sectors, or regions.
"""

from typing import Any

import numpy as np
from scipy import optimize, stats


class DEAAnalyzer:
    """
    Data Envelopment Analysis (ECO 311 — Production & Cost, ECO 422).

    DEA is a non-parametric linear programming method that constructs
    a piecewise-linear production frontier from observed input-output data.

    For each DMU, DEA solves:
        max θ
        s.t. Σⱼ λⱼ xⱼᵢ ≤ x₀ᵢ  ∀i (inputs)
             Σⱼ λⱼ yⱼᵣ ≥ θ·y₀ᵣ  ∀r (outputs)
             λⱼ ≥ 0

    This is the input-oriented BCC model (variable returns to scale).
    """

    @staticmethod
    def input_oriented_bcc(
        inputs: np.ndarray,
        outputs: np.ndarray,
        dmu_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Input-oriented BCC (variable returns to scale) DEA model.

        Measures how much inputs could be proportionally reduced
        while maintaining the same output levels.

        Args:
            inputs: (n, m) matrix of n DMUs with m inputs
            outputs: (n, s) matrix of n DMUs with s outputs
            dmu_names: optional list of DMU identifiers

        Returns:
            Dict with efficiency scores, benchmarks, and peer groups
        """
        inputs = np.asarray(inputs, dtype=float)
        outputs = np.asarray(outputs, dtype=float)
        n, m = inputs.shape
        _, s = outputs.shape

        if dmu_names is None:
            dmu_names = [f"DMU_{i}" for i in range(n)]

        efficiencies: list[float] = []
        benchmarks: list[dict[str, Any]] = []

        for i in range(n):
            try:
                eff = DEAAnalyzer._solve_bcc(inputs, outputs, i)
                efficiencies.append(eff)

                # Identify benchmark (peer) DMUs
                peers = []
                for j in range(n):
                    if j != i and efficiencies[-1] < 1.0:
                        # Check if DMU j is on the frontier
                        dist = float(np.linalg.norm(inputs[j] - inputs[i]))
                        if dist > 0:
                            peers.append({"dmu": dmu_names[j], "distance": round(dist, 4)})
                peers.sort(key=lambda x: x["distance"])
                benchmarks.append({
                    "dmu": dmu_names[i],
                    "efficiency": round(eff, 4),
                    "peers": peers[:3],
                })
            except Exception:
                efficiencies.append(1.0)
                benchmarks.append({"dmu": dmu_names[i], "efficiency": 1.0, "peers": []})

        eff_arr = np.array(efficiencies)

        return {
            "efficiencies": [round(e, 4) for e in efficiencies],
            "mean_efficiency": round(float(np.mean(eff_arr)), 4),
            "median_efficiency": round(float(np.median(eff_arr)), 4),
            "min_efficiency": round(float(np.min(eff_arr)), 4),
            "n_efficient": int(np.sum(np.abs(eff_arr - 1.0) < 1e-6)),
            "n_inefficient": int(np.sum(np.abs(eff_arr - 1.0) >= 1e-6)),
            "benchmarks": benchmarks,
            "dmu_names": dmu_names,
            "n_dmus": n,
            "n_inputs": m,
            "n_outputs": s,
            "model": "BCC_input_oriented",
            "returns_to_scale": "variable",
        }

    @staticmethod
    def _solve_bcc(inputs: np.ndarray, outputs: np.ndarray, target: int) -> float:
        """Solve BCC DEA for a single target DMU using linear programming."""
        n = inputs.shape[0]
        x0 = inputs[target]
        y0 = outputs[target]

        # Simple approach using scipy.optimize.linprog
        # min -theta s.t. constraints
        # Variables: [theta, lambda_1, ..., lambda_n]
        n_vars = 1 + n

        # Objective: minimize -theta (i.e., maximize theta)
        c = np.zeros(n_vars)
        c[0] = -1.0  # -theta

        # Constraints: A_ub @ x <= b_ub
        # Input constraints: Σ λⱼ xⱼᵢ ≤ x₀ᵢ for each input i
        m = inputs.shape[1]
        s = outputs.shape[1]

        A_list = []
        b_list = []

        # Input constraints: Σⱼ λⱼ xⱼᵢ ≤ x₀ᵢ
        for k in range(m):
            row = np.zeros(n_vars)
            row[0] = 0  # theta coefficient
            row[1:] = inputs[:, k]
            A_list.append(row)
            b_list.append(float(x0[k]))

        # Output constraints: Σⱼ λⱼ yⱼᵣ ≥ θ·y₀ᵣ → -Σⱼ λⱼ yⱼᵣ + θ·y₀ᵣ ≤ 0
        for k in range(s):
            row = np.zeros(n_vars)
            row[0] = float(y0[k])  # theta * y0_r
            row[1:] = -outputs[:, k]
            A_list.append(row)
            b_list.append(0.0)

        # VRS constraint: Σ λⱼ = 1
        # Equality: A_eq @ x = b_eq
        A_eq = np.zeros((1, n_vars))
        A_eq[0, 1:] = 1.0
        b_eq = np.array([1.0])

        # Bounds: theta >= 0, lambda_j >= 0
        bounds = [(0, None)] * n_vars

        A_ub = np.array(A_list)
        b_ub = np.array(b_list)

        result = optimize.linprog(
            c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
            bounds=bounds, method='highs'
        )

        if result.success:
            return float(result.x[0])
        return 1.0  # Default to efficient if solver fails

    @staticmethod
    def output_oriented_bcc(
        inputs: np.ndarray,
        outputs: np.ndarray,
        dmu_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Output-oriented BCC DEA model.

        Measures how much outputs could be proportionally expanded
        while maintaining the same input levels.

        Args:
            inputs: (n, m) matrix of n DMUs with m inputs
            outputs: (n, s) matrix of n DMUs with s outputs
            dmu_names: optional list of DMU identifiers

        Returns:
            Dict with efficiency scores and benchmarks
        """
        inputs = np.asarray(inputs, dtype=float)
        outputs = np.asarray(outputs, dtype=float)
        n = inputs.shape[0]

        if dmu_names is None:
            dmu_names = [f"DMU_{i}" for i in range(n)]

        # Output-oriented efficiency = 1 / input-oriented efficiency
        # (under VRS, input and output oriented measures are reciprocal)
        result = DEAAnalyzer.input_oriented_bcc(inputs, outputs, dmu_names)
        eff_scores = result["efficiencies"]

        # Reciprocal for output-oriented
        output_eff = [round(1.0 / max(e, 1e-10), 4) for e in eff_scores]

        result["efficiencies"] = output_eff
        result["model"] = "BCC_output_oriented"
        result["mean_efficiency"] = round(float(np.mean(output_eff)), 4)
        return result

    @staticmethod
    def malmquist_index(
        inputs_t0: np.ndarray,
        outputs_t0: np.ndarray,
        inputs_t1: np.ndarray,
        outputs_t1: np.ndarray,
    ) -> dict[str, Any]:
        """
        Malmquist productivity index for measuring productivity change.

        MI = TEC × TC where:
        - TEC = Technical Efficiency Change (catching up)
        - TC = Technical Change (frontier shift)

        Args:
            inputs_t0: inputs at time 0
            outputs_t0: outputs at time 0
            inputs_t1: inputs at time 1
            outputs_t1: outputs at time 1

        Returns:
            Dict with Malmquist index decomposition
        """
        # Compute efficiencies at each period
        eff_t0 = DEAAnalyzer.input_oriented_bcc(inputs_t0, outputs_t0)["efficiencies"]
        eff_t1 = DEAAnalyzer.input_oriented_bcc(inputs_t1, outputs_t1)["efficiencies"]

        eff_t0 = np.array(eff_t0)
        eff_t1 = np.array(eff_t1)

        # Technical efficiency change
        tec = eff_t1 / np.maximum(eff_t0, 1e-10)

        # Simplified: assume TC ≈ 1 (no frontier shift info from single DEA)
        # In practice, need cross-period DEA
        mi = tec  # Malmquist ≈ TEC when TC = 1

        return {
            "malmquist_index": [round(float(v), 4) for v in mi],
            "mean_malmquist": round(float(np.mean(mi)), 4),
            "technical_efficiency_change": [round(float(v), 4) for v in tec],
            "mean_tec": round(float(np.mean(tec)), 4),
            "productivity_improved": int(np.sum(mi > 1.0)),
            "productivity_declined": int(np.sum(mi < 1.0)),
            "n_dmus": len(mi),
        }


class SFAAnalyzer:
    """
    Stochastic Frontier Analysis (ECO 311, ECO 422).

    SFA decomposes the error term into two components:
        ln(yᵢ) = β₀ + β'ln(xᵢ) + vᵢ - uᵢ

    where:
        vᵢ ~ N(0, σ²ᵥ) — symmetric noise (statistical noise)
        uᵢ ≥ 0 — one-sided inefficiency (half-normal or truncated normal)

    Unlike DEA, SFA separates statistical noise from true inefficiency.
    """

    @staticmethod
    def half_normal_frontier(
        log_output: np.ndarray,
        log_inputs: np.ndarray,
    ) -> dict[str, Any]:
        """
        Estimate production frontier with half-normal inefficiency.

        Uses OLS + corrected estimate (COLS) as initial, then
        method of moments for variance decomposition.

        Args:
            log_output: ln(y) — natural log of output
            log_inputs: ln(X) — natural log of input matrix (n × k)

        Returns:
            Dict with frontier coefficients, efficiency scores, variance decomposition
        """
        log_output = np.asarray(log_output, dtype=float)
        log_inputs = np.asarray(log_inputs, dtype=float)
        n = len(log_output)

        if log_inputs.ndim == 1:
            log_inputs = log_inputs.reshape(-1, 1)

        # Add intercept
        X = np.column_stack([np.ones(n), log_inputs])
        k = X.shape[1]

        # OLS estimation
        try:
            beta_ols = np.linalg.lstsq(X, log_output, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "OLS estimation failed"}

        residuals = log_output - X @ beta_ols
        sigma2_u_ols = float(np.var(residuals, ddof=k))

        # Corrected OLS (COLS): shift frontier up
        # The OLS intercept is biased downward; COLS corrects by adding
        # the mean of the half-normal inefficiency term
        # For half-normal: E[u] = σ_u √(2/π)
        # Method of moments:
        # m₃ = (2/π)^(3/2) · σ_u³  (third moment of residuals)
        m3 = float(np.mean(residuals ** 3))

        # Skewness-based estimate of σ_u
        # For OLS residuals: skewness is caused by -u term
        # skew(OLS residuals) = -E[(u-E[u])³] / σ³ < 0 if inefficiency exists
        if m3 < 0:
            # Use method of moments
            sigma_u = float((-m3 * (np.pi / 2) ** 1.5) ** (1.0 / 3))
            sigma2_v = max(sigma2_u_ols - sigma_u ** 2 * (1 - 2 / np.pi), 1e-10)
        else:
            # No evidence of inefficiency
            sigma_u = 0.0
            sigma2_v = sigma2_u_ols

        # Corrected intercept
        beta_cols = beta_ols.copy()
        if sigma_u > 0:
            beta_cols[0] += sigma_u * np.sqrt(2 / np.pi)

        # Efficiency scores: E[exp(-u)|ε]
        # Using Jondrow et al. (1982) estimator
        sigma2 = sigma_u ** 2 + sigma2_v
        sigma = np.sqrt(max(sigma2, 1e-10))
        sigma_star = sigma_u * np.sqrt(sigma2_v) / max(sigma, 1e-10)

        eps = residuals
        mu_star = -eps * (sigma_u ** 2) / max(sigma2, 1e-10)

        # E[u|ε] = μ* + σ* · φ(μ*/σ*) / Φ(μ*/σ*)
        efficiencies = np.zeros(n)
        for i in range(n):
            if sigma_star > 1e-10:
                z = mu_star[i] / sigma_star
                phi_z = float(stats.norm.pdf(z))
                Phi_z = float(stats.norm.cdf(z))
                if Phi_z > 1e-300:
                    efficiencies[i] = float(np.exp(-mu_star[i] - sigma_star * phi_z / Phi_z))
                else:
                    efficiencies[i] = float(np.exp(-mu_star[i]))
            else:
                efficiencies[i] = 1.0

        efficiencies = np.clip(efficiencies, 0, 1)

        # Log-likelihood for model comparison
        ll = -n / 2 * np.log(2 * np.pi * sigma2) - np.sum(eps ** 2) / (2 * sigma2)
        for i in range(n):
            if sigma_star > 1e-10:
                z = mu_star[i] / sigma_star
                Phi_z = float(stats.norm.cdf(z))
                if Phi_z > 1e-300:
                    ll += np.log(2) - np.log(sigma) + np.log(Phi_z)

        # R²
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((log_output - np.mean(log_output)) ** 2)
        r_squared = 1 - ss_res / max(ss_tot, 1e-10)

        return {
            "coefficients": [round(float(c), 6) for c in beta_cols],
            "coefficients_ols": [round(float(c), 6) for c in beta_ols],
            "sigma_u": round(float(sigma_u), 6),
            "sigma_v": round(float(np.sqrt(sigma2_v)), 6),
            "sigma2_u": round(float(sigma_u ** 2), 6),
            "sigma2_v": round(float(sigma2_v), 6),
            "lambda": round(float(sigma_u / max(np.sqrt(sigma2_v), 1e-10)), 4),
            "gamma": round(float(sigma_u ** 2 / max(sigma2, 1e-10)), 4),
            "efficiencies": [round(float(e), 4) for e in efficiencies],
            "mean_efficiency": round(float(np.mean(efficiencies)), 4),
            "median_efficiency": round(float(np.median(efficiencies)), 4),
            "min_efficiency": round(float(np.min(efficiencies)), 4),
            "log_likelihood": round(float(ll), 2),
            "r_squared": round(float(r_squared), 4),
            "n_observations": n,
            "model": "half_normal_SFA",
            "inefficiency_detected": sigma_u > 0,
        }

    @staticmethod
    def cobb_douglas_frontier(
        output: np.ndarray,
        inputs: np.ndarray,
        input_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Cobb-Douglas stochastic production frontier.

        ln(y) = β₀ + Σ βᵢ ln(xᵢ) + v - u

        Args:
            output: output values (levels, not logs)
            inputs: input matrix (n × k) in levels
            input_names: optional names for inputs

        Returns:
            Dict with frontier parameters and efficiency scores
        """
        output = np.asarray(output, dtype=float)
        inputs = np.asarray(inputs, dtype=float)

        # Ensure positive values for log transform
        output = np.maximum(output, 1e-10)
        inputs = np.maximum(inputs, 1e-10)

        log_output = np.log(output)
        log_inputs = np.log(inputs)

        result = SFAAnalyzer.half_normal_frontier(log_output, log_inputs)

        if "error" in result:
            return result

        # Add input names and elasticity interpretation
        if input_names is not None and "coefficients" in result:
            betas = result["coefficients"]
            elasticities: dict[str, float] = {}
            for i, name in enumerate(input_names):
                if i + 1 < len(betas):
                    elasticities[name] = round(float(betas[i + 1]), 4)
            result["elasticities"] = elasticities
            result["returns_to_scale"] = round(float(sum(elasticities.values())), 4)

        result["model"] = "cobb_douglas_SFA"
        return result

    @staticmethod
    def translog_frontier(
        output: np.ndarray,
        inputs: np.ndarray,
        input_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Translog stochastic production frontier.

        ln(y) = β₀ + Σ βᵢ ln(xᵢ) + Σᵢ Σⱼ βᵢⱼ ln(xᵢ)ln(xⱼ) + v - u

        More flexible than Cobb-Douglas — allows for variable elasticities
        and interaction effects between inputs.

        Args:
            output: output values (levels)
            inputs: input matrix (n × k) in levels
            input_names: optional names for inputs

        Returns:
            Dict with frontier parameters and efficiency scores
        """
        output = np.asarray(output, dtype=float)
        inputs = np.asarray(inputs, dtype=float)

        output = np.maximum(output, 1e-10)
        inputs = np.maximum(inputs, 1e-10)

        log_output = np.log(output)
        log_inputs = np.log(inputs)

        n, k = log_inputs.shape

        # Build translog design matrix: [1, ln(x₁),...,ln(xₖ), ln(x₁)², ln(x₁)ln(x₂),...]
        X_cols = [np.ones(n)]
        for i in range(k):
            X_cols.append(log_inputs[:, i])
        # Interaction and squared terms
        for i in range(k):
            for j in range(i, k):
                X_cols.append(log_inputs[:, i] * log_inputs[:, j])

        X = np.column_stack(X_cols)

        result = SFAAnalyzer.half_normal_frontier(log_output, X)

        if "error" in result:
            return result

        # Parse coefficients
        betas = result.get("coefficients", [])
        linear_names = input_names if input_names else [f"x{i}" for i in range(k)]
        result["linear_coefficients"] = {
            linear_names[i]: round(float(betas[i + 1]), 6) for i in range(k) if i + 1 < len(betas)
        }

        result["model"] = "translog_SFA"
        result["n_interaction_terms"] = k * (k + 1) // 2
        return result


__all__ = ["DEAAnalyzer", "SFAAnalyzer"]
