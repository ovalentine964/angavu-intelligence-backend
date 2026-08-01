"""
Macroeconomic Models for Angavu Intelligence Backend (ECO 311/414)

Implements core macroeconomic models and relationships used for
economic analysis and policy evaluation in Kenya's context:

1. Phillips Curve — inflation-unemployment relationship
2. IS-LM Model — goods market + money market equilibrium
3. Solow Growth Model — capital accumulation and steady state
4. Demographic Models — life tables, population projections
5. Taylor Rule — monetary policy rule
6. Okun's Law — GDP-unemployment relationship
7. Fisher Equation — nominal vs real interest rates
8. Money Multiplier — money supply creation process

Mathematical Foundations:
- Phillips Curve: π = πᵉ - β(u - uⁿ) + ε  (expectations-augmented)
- IS Curve: Y = C(Y-T) + I(r) + G + NX
- LM Curve: M/P = L(Y, r)  (money market equilibrium)
- Solow: Δk = sf(k) - (n+δ)k  (capital accumulation)
- Taylor: r = r* + π + 0.5(π - π*) + 0.5(y - y*)
- Okun: ΔY/Y = k - c(u - u₋₁)
- Fisher: (1 + i) = (1 + r)(1 + π)
- Money Multiplier: m = (1 + c)/(r + c)

Reference:
- Mankiw, N.G. (2019). Macroeconomics (10th ed.).
- Blanchard, O. (2017). Macroeconomics (7th ed.).
- Romer, D. (2019). Advanced Macroeconomics (5th ed.).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import optimize as sp_opt
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. Phillips Curve
# ════════════════════════════════════════════════════════════════


class PhillipsCurve:
    """
    Expectations-Augmented Phillips Curve.

    Short-run: π = πᵉ - β(u - uⁿ) + ε
    Long-run: π = πᵉ (vertical Phillips curve at NAIRU)

    Adaptive expectations: πᵉ = π₋₁
    Forward-looking: πᵉ = E[πₜ₊₁]

    For Kenya:
    - NAIRU estimated at ~5-7% (varies by estimation)
    - Inflation expectations partially anchored by CBK targeting
    - Food supply shocks create supply-side inflation

    Estimation:
    - OLS: πₜ = α + βuₜ + γπₜ₋₁ + εₜ
    - GMM: instrument for expectations
    """

    @staticmethod
    def estimate(
        inflation: np.ndarray,
        unemployment: np.ndarray,
        expected_inflation: Optional[np.ndarray] = None,
        method: str = "adaptive",
    ) -> Dict[str, Any]:
        """
        Estimate Phillips Curve parameters.

        Args:
            inflation: time series of inflation rates
            unemployment: time series of unemployment rates
            expected_inflation: expected inflation (if None, uses adaptive)
            method: "adaptive" (πᵉ = π₋₁) or "naive" (πᵉ = 0)

        Returns:
            Dict with estimated parameters, NAIRU, diagnostics
        """
        pi = np.asarray(inflation, dtype=float).ravel()
        u = np.asarray(unemployment, dtype=float).ravel()
        n = min(len(pi), len(u))

        if n < 10:
            return {"error": "Need ≥10 observations"}

        # Align
        pi = pi[:n]
        u = u[:n]

        if expected_inflation is not None:
            pi_e = np.asarray(expected_inflation, dtype=float).ravel()[:n]
        elif method == "adaptive":
            pi_e = np.roll(pi, 1)
            pi_e[0] = pi[0]
        else:
            pi_e = np.zeros(n)

        # Regression: π - πᵉ = α + β(u - u*) + ε
        # Or: π = α + β*u + γ*πᵉ + ε
        y = pi[1:]  # exclude first for lag
        X = np.column_stack([
            np.ones(n - 1),
            u[1:],
            pi_e[1:],
        ])

        # OLS
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in estimation"}

        intercept, beta_u, gamma_e = beta
        residuals = y - X @ beta
        sigma2 = np.sum(residuals ** 2) / (n - 4)

        # NAIRU: solve for u where π = πᵉ
        # π = α + β*u + γ*πᵉ → if π = πᵉ: πᵉ = α + β*u + γ*πᵉ
        # (1 - γ)πᵉ = α + β*u → u* = ((1-γ)πᵉ - α) / β
        pi_e_mean = np.mean(pi_e)
        if abs(beta_u) > 1e-10:
            nairu = ((1 - gamma_e) * pi_e_mean - intercept) / beta_u
        else:
            nairu = float('nan')

        # Standard errors
        try:
            var_beta = sigma2 * np.linalg.inv(X.T @ X)
            se = np.sqrt(np.diag(var_beta))
        except np.linalg.LinAlgError:
            se = np.full(3, float('nan'))

        t_stats = beta / se
        p_values = 2 * (1 - sp_stats.t.cdf(np.abs(t_stats), df=n - 4))

        return {
            "method": "Expectations-Augmented Phillips Curve",
            "intercept": float(intercept),
            "beta_unemployment": float(beta_u),
            "gamma_expectations": float(gamma_e),
            "std_errors": se.tolist(),
            "t_statistics": t_stats.tolist(),
            "p_values": p_values.tolist(),
            "nairu": float(nairu),
            "n_obs": n,
            "residual_std": float(np.sqrt(sigma2)),
            "interpretation": f"1% rise in unemployment → {abs(beta_u):.2f}pp change in inflation" if beta_u != 0 else "No relationship detected",
        }

    @staticmethod
    def simulate(
        nairu: float,
        beta: float,
        expected_inflation: float,
        unemployment_path: np.ndarray,
        initial_inflation: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Simulate inflation path given unemployment trajectory.

        Args:
            nairu: Non-Accelerating Inflation Rate of Unemployment
            beta: Phillips curve slope
            expected_inflation: baseline expected inflation
            unemployment_path: future unemployment rates
            initial_inflation: starting inflation rate

        Returns:
            Dict with simulated inflation path
        """
        u = np.asarray(unemployment_path, dtype=float).ravel()
        n = len(u)

        pi = np.zeros(n)
        pi[0] = initial_inflation

        for t in range(1, n):
            # Adaptive expectations: πᵉ = π₋₁
            pi_e = pi[t - 1]
            # Phillips curve: π = πᵉ - β(u - uⁿ)
            pi[t] = pi_e - beta * (u[t] - nairu)

        return {
            "inflation_path": pi.tolist(),
            "unemployment_path": u.tolist(),
            "nairu": nairu,
            "final_inflation": float(pi[-1]),
        }


# ════════════════════════════════════════════════════════════════
# 2. IS-LM Model
# ════════════════════════════════════════════════════════════════


class ISLMModel:
    """
    IS-LM Model — simultaneous equilibrium in goods and money markets.

    IS curve (goods market): Y = C₀ + c(Y-T) + I₀ - br + G
        → Y = (C₀ + I₀ + G - cT - br) / (1-c)

    LM curve (money market): M/P = kY - hr
        → r = (kY - M/P) / h

    Equilibrium: Solve simultaneously for Y* and r*.

    For Kenya:
    - IS: Government spending G is major component, investment sensitive to interest
    - LM: CBK controls money supply, M-Pesa affects money demand
    - Fiscal multiplier: 1/(1-c+bt) where t = tax rate
    """

    @staticmethod
    def solve(
        consumption_intercept: float = 100,
        mpc: float = 0.75,
        tax_rate: float = 0.15,
        investment_intercept: float = 200,
        investment_sensitivity: float = 50,
        government_spending: float = 150,
        money_supply: float = 500,
        price_level: float = 1.0,
        money_income_sensitivity: float = 0.5,
        money_rate_sensitivity: float = 100,
    ) -> Dict[str, Any]:
        """
        Solve IS-LM model for equilibrium output and interest rate.

        Args:
            consumption_intercept: C₀ (autonomous consumption)
            mpc: c (marginal propensity to consume)
            tax_rate: t (proportional income tax)
            investment_intercept: I₀ (autonomous investment)
            investment_sensitivity: b (investment sensitivity to interest rate)
            government_spending: G
            money_supply: M (nominal)
            price_level: P
            money_income_sensitivity: k (money demand income sensitivity)
            money_rate_sensitivity: h (money demand interest rate sensitivity)

        Returns:
            Dict with equilibrium Y*, r*, slopes, fiscal/monetary multipliers
        """
        # IS curve: Y = (C₀ + I₀ + G - br) / (1 - c(1-t))
        # Slope of IS in (Y, r) space: dr/dY = -(1-c(1-t))/b
        c = mpc
        t = tax_rate
        b = investment_sensitivity
        k = money_income_sensitivity
        h = money_rate_sensitivity
        M_P = money_supply / price_level

        # IS: Y(1 - c(1-t)) = C₀ + I₀ + G - br
        # LM: r = (kY - M/P) / h

        # Substitute LM into IS:
        # Y(1-c(1-t)) = C₀ + I₀ + G - b(kY - M/P)/h
        # Y(1-c(1-t)) + bkY/h = C₀ + I₀ + G + bM/(Ph)
        # Y(1-c(1-t) + bk/h) = C₀ + I₀ + G + bM/(Ph)

        A = consumption_intercept + investment_intercept + government_spending
        denominator = (1 - c * (1 - t)) + b * k / h

        if abs(denominator) < 1e-10:
            return {"error": "Model has no unique solution (degenerate)"}

        Y_star = (A + b * M_P / h) / denominator
        r_star = (k * Y_star - M_P) / h

        # Multipliers
        fiscal_multiplier = 1 / (1 - c * (1 - t) + b * k / h)
        monetary_multiplier = (b / h) / (1 - c * (1 - t) + b * k / h)

        # IS slope: dr/dY = -(1-c(1-t))/b
        is_slope = -(1 - c * (1 - t)) / b if b != 0 else float('-inf')
        # LM slope: dr/dY = k/h
        lm_slope = k / h if h != 0 else float('inf')

        return {
            "method": "IS-LM Model",
            "equilibrium_output": float(Y_star),
            "equilibrium_interest_rate": float(r_star),
            "fiscal_multiplier": float(fiscal_multiplier),
            "monetary_multiplier": float(monetary_multiplier),
            "is_slope": float(is_slope),
            "lm_slope": float(lm_slope),
            "parameters": {
                "mpc": mpc, "tax_rate": tax_rate, "investment_sensitivity": b,
                "money_income_sensitivity": k, "money_rate_sensitivity": h,
                "government_spending": government_spending, "money_supply": money_supply,
            },
        }

    @staticmethod
    def fiscal_shock(
        base_params: Dict[str, float],
        delta_g: float,
    ) -> Dict[str, Any]:
        """
        Compute effect of fiscal policy change (ΔG).

        ΔY = fiscal_multiplier × ΔG
        Δr = LM slope × ΔY
        """
        base = ISLMModel.solve(**base_params)
        new_params = base_params.copy()
        new_params["government_spending"] = new_params.get("government_spending", 150) + delta_g
        new = ISLMModel.solve(**new_params)

        return {
            "delta_output": new["equilibrium_output"] - base["equilibrium_output"],
            "delta_interest_rate": new["equilibrium_interest_rate"] - base["equilibrium_interest_rate"],
            "fiscal_multiplier": base["fiscal_multiplier"],
            "base_equilibrium": base,
            "new_equilibrium": new,
        }

    @staticmethod
    def monetary_shock(
        base_params: Dict[str, float],
        delta_m: float,
    ) -> Dict[str, Any]:
        """
        Compute effect of monetary policy change (ΔM).
        """
        base = ISLMModel.solve(**base_params)
        new_params = base_params.copy()
        new_params["money_supply"] = new_params.get("money_supply", 500) + delta_m
        new = ISLMModel.solve(**new_params)

        return {
            "delta_output": new["equilibrium_output"] - base["equilibrium_output"],
            "delta_interest_rate": new["equilibrium_interest_rate"] - base["equilibrium_interest_rate"],
            "monetary_multiplier": base["monetary_multiplier"],
            "base_equilibrium": base,
            "new_equilibrium": new,
        }


# ════════════════════════════════════════════════════════════════
# 3. Solow Growth Model
# ════════════════════════════════════════════════════════════════


class SolowGrowthModel:
    """
    Solow-Swan Growth Model.

    Production: Y = K^α (AL)^(1-α)  (Cobb-Douglas)
    Capital accumulation: ΔK = sY - δK
    Effective labor: Δ(AL) = (n + g)(AL)

    In per-effective-worker terms:
    Δk̃ = sf(k̃) - (n + g + δ)k̃
    where k̃ = K/(AL), f(k̃) = k̃^α

    Steady state: k̃* = (s/(n+g+δ))^(1/(1-α))
    Output per effective worker: y* = (k̃*)^α

    For Kenya:
    - s ≈ 0.15-0.20 (savings rate)
    - n ≈ 0.02 (population growth)
    - δ ≈ 0.05 (depreciation)
    - α ≈ 0.33 (capital share)
    - g ≈ 0.02 (technology growth)
    """

    @staticmethod
    def solve_steady_state(
        savings_rate: float = 0.18,
        population_growth: float = 0.02,
        depreciation: float = 0.05,
        technology_growth: float = 0.02,
        capital_share: float = 0.33,
    ) -> Dict[str, Any]:
        """
        Compute Solow model steady state.

        Args:
            savings_rate: s (fraction of output saved)
            population_growth: n (labor force growth rate)
            depreciation: δ (capital depreciation rate)
            technology_growth: g (technology/labor productivity growth)
            capital_share: α (Cobb-Douglas capital share)

        Returns:
            Dict with steady-state values, golden rule, convergence speed
        """
        s = savings_rate
        n = population_growth
        delta = depreciation
        g = technology_growth
        alpha = capital_share

        # Steady-state capital per effective worker
        if n + g + delta <= 0 or s <= 0:
            return {"error": "Invalid parameters (need s > 0, n+g+δ > 0)"}

        k_star = (s / (n + g + delta)) ** (1 / (1 - alpha))
        y_star = k_star ** alpha
        c_star = (1 - s) * y_star

        # Investment per effective worker at steady state
        i_star = s * y_star

        # Golden rule savings rate: s_gr = α (maximizes consumption)
        s_golden = alpha
        k_golden = (s_golden / (n + g + delta)) ** (1 / (1 - alpha))
        y_golden = k_golden ** alpha
        c_golden = (1 - s_golden) * y_golden

        # Convergence speed: λ = (1-α)(n+g+δ)
        # Half-life: ln(2)/λ
        convergence_speed = (1 - alpha) * (n + g + delta)
        half_life = math.log(2) / convergence_speed if convergence_speed > 0 else float('inf')

        # Output per worker (not per effective worker)
        # In steady state, Y/L grows at rate g
        # Y/L = A × y* where A is technology level

        return {
            "method": "Solow Growth Model",
            "steady_state": {
                "capital_per_effective_worker": float(k_star),
                "output_per_effective_worker": float(y_star),
                "consumption_per_effective_worker": float(c_star),
                "investment_per_effective_worker": float(i_star),
            },
            "golden_rule": {
                "optimal_savings_rate": float(s_golden),
                "capital": float(k_golden),
                "output": float(y_golden),
                "consumption": float(c_golden),
                "current_suboptimal": abs(s - s_golden) > 0.01,
            },
            "convergence_speed": float(convergence_speed),
            "half_life_periods": float(half_life),
            "parameters": {
                "savings_rate": s, "population_growth": n,
                "depreciation": delta, "technology_growth": g,
                "capital_share": alpha,
            },
        }

    @staticmethod
    def simulate_transition(
        initial_k: float,
        savings_rate: float = 0.18,
        population_growth: float = 0.02,
        depreciation: float = 0.05,
        technology_growth: float = 0.02,
        capital_share: float = 0.33,
        n_periods: int = 100,
    ) -> Dict[str, Any]:
        """
        Simulate transition to steady state.

        Args:
            initial_k: initial capital per effective worker
            n_periods: number of periods to simulate

        Returns:
            Dict with time paths of k, y, c, i
        """
        s = savings_rate
        n = population_growth
        delta = depreciation
        g = technology_growth
        alpha = capital_share

        k = np.zeros(n_periods)
        y = np.zeros(n_periods)
        c = np.zeros(n_periods)
        inv = np.zeros(n_periods)

        k[0] = initial_k
        y[0] = k[0] ** alpha
        inv[0] = s * y[0]
        c[0] = (1 - s) * y[0]

        for t in range(1, n_periods):
            k[t] = k[t - 1] + s * y[t - 1] - (n + g + delta) * k[t - 1]
            k[t] = max(k[t], 0.001)  # prevent negative
            y[t] = k[t] ** alpha
            inv[t] = s * y[t]
            c[t] = (1 - s) * y[t]

        # Steady state
        k_star = (s / (n + g + delta)) ** (1 / (1 - alpha))

        return {
            "capital_path": k.tolist(),
            "output_path": y.tolist(),
            "consumption_path": c.tolist(),
            "investment_path": inv.tolist(),
            "steady_state_k": float(k_star),
            "periods_to_95pct": int(np.argmax(np.abs(k - k_star) / k_star < 0.05)) if np.any(np.abs(k - k_star) / k_star < 0.05) else n_periods,
        }


# ════════════════════════════════════════════════════════════════
# 4. Demographic Models
# ════════════════════════════════════════════════════════════════


class DemographicModels:
    """
    Demographic analysis tools for population projection and life tables.

    Methods:
    - Life table construction from age-specific mortality rates
    - Cohort-component population projection
    - Dependency ratio calculation
    - Demographic dividend estimation

    For Kenya:
    - Population ~54 million (2023)
    - TFR ~3.3 (declining from 4.7 in 2008)
    - Life expectancy ~67 years
    - Median age ~20 years (very young)
    """

    @staticmethod
    def life_table(
        age_specific_mortality: np.ndarray,
        radix: int = 100000,
    ) -> Dict[str, Any]:
        """
        Construct a life table from age-specific mortality rates (qx).

        Life table columns:
        - x: age
        - qx: probability of dying between age x and x+1
        - lx: number surviving to age x
        - dx: number dying between age x and x+1
        - Lx: person-years lived between age x and x+1
        - Tx: total person-years lived above age x
        - ex: life expectancy at age x

        Args:
            age_specific_mortality: array of qx values (probability of death at each age)
            radix: starting cohort size (usually 100,000)

        Returns:
            Dict with complete life table and summary statistics
        """
        qx = np.asarray(age_specific_mortality, dtype=float).ravel()
        n_ages = len(qx)

        lx = np.zeros(n_ages)
        dx = np.zeros(n_ages)
        Lx = np.zeros(n_ages)
        Tx = np.zeros(n_ages)
        ex = np.zeros(n_ages)

        lx[0] = radix
        for x in range(n_ages):
            qx_clipped = min(max(qx[x], 0), 1)
            dx[x] = lx[x] * qx_clipped
            if x < n_ages - 1:
                lx[x + 1] = lx[x] - dx[x]
            # Lx: assuming uniform deaths
            Lx[x] = lx[x] - 0.5 * dx[x] if x < n_ages - 1 else lx[x] / (qx_clipped + 1e-10)

        # Tx: reverse cumulative sum of Lx
        Tx = np.cumsum(Lx[::-1])[::-1]

        # ex: life expectancy
        for x in range(n_ages):
            ex[x] = Tx[x] / lx[x] if lx[x] > 0 else 0

        return {
            "method": "Life Table",
            "n_ages": n_ages,
            "qx": qx.tolist(),
            "lx": lx.tolist(),
            "dx": dx.tolist(),
            "Lx": Lx.tolist(),
            "Tx": Tx.tolist(),
            "ex": ex.tolist(),
            "life_expectancy_at_birth": float(ex[0]),
            "life_expectancy_at_60": float(ex[min(60, n_ages - 1)]) if n_ages > 60 else None,
            "infant_mortality_rate": float(qx[0]) if n_ages > 0 else None,
        }

    @staticmethod
    def population_projection(
        initial_population: np.ndarray,
        fertility_rates: np.ndarray,
        survival_rates: np.ndarray,
        n_years: int = 20,
        net_migration: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Cohort-component population projection.

        P(t+1, a+1) = P(t, a) × S(a) + M(a)

        where:
        - P(t, a) = population at time t, age a
        - S(a) = survival rate from age a to a+1
        - M(a) = net migration at age a

        New births: P(t+1, 0) = Σ P(t, a) × f(a) / 2
        (f(a) = age-specific fertility rate, divided by 2 for female fraction)

        Args:
            initial_population: population by age group
            fertility_rates: age-specific fertility rates (by age group)
            survival_rates: survival probabilities by age group
            n_years: projection horizon
            net_migration: net migration by age (default 0)

        Returns:
            Dict with projected population, growth rates, dependency ratios
        """
        pop0 = np.asarray(initial_population, dtype=float).ravel()
        fert = np.asarray(fertility_rates, dtype=float).ravel()
        surv = np.asarray(survival_rates, dtype=float).ravel()
        n_ages = len(pop0)

        if net_migration is None:
            mig = np.zeros(n_ages)
        else:
            mig = np.asarray(net_migration, dtype=float).ravel()

        # Ensure arrays match
        if len(fert) < n_ages:
            fert = np.pad(fert, (0, n_ages - len(fert)))
        if len(surv) < n_ages:
            surv = np.pad(surv, (0, n_ages - len(surv)))
        if len(mig) < n_ages:
            mig = np.pad(mig, (0, n_ages - len(mig)))

        # Project
        pop_history = np.zeros((n_years + 1, n_ages))
        pop_history[0] = pop0
        total_pop = np.zeros(n_years + 1)
        total_pop[0] = np.sum(pop0)

        for t in range(n_years):
            pop_t = pop_history[t]
            new_pop = np.zeros(n_ages)

            # New births (ages 15-49 fertile)
            fertile_pop = pop_t[15:50] if n_ages > 50 else pop_t[15:]
            fert_slice = fert[15:50] if n_ages > 50 else fert[15:]
            births = np.sum(fertile_pop * fert_slice) / 2  # female fraction
            new_pop[0] = births

            # Aging
            for a in range(1, n_ages):
                new_pop[a] = pop_t[a - 1] * surv[a - 1] + mig[a]

            pop_history[t + 1] = new_pop
            total_pop[t + 1] = np.sum(new_pop)

        # Growth rates
        growth_rates = np.diff(total_pop) / total_pop[:-1] * 100

        # Dependency ratios (using standard age groups)
        young = np.sum(pop_history[:, :15], axis=1)  # 0-14
        working = np.sum(pop_history[:, 15:65], axis=1)  # 15-64
        old = np.sum(pop_history[:, 65:], axis=1) if n_ages > 65 else np.zeros(n_years + 1)  # 65+
        youth_dependency = young / working * 100
        old_dependency = old / working * 100
        total_dependency = (young + old) / working * 100

        return {
            "method": "Cohort-Component Projection",
            "n_years": n_years,
            "total_population": total_pop.tolist(),
            "growth_rates_pct": growth_rates.tolist(),
            "youth_dependency_ratio": youth_dependency.tolist(),
            "old_dependency_ratio": old_dependency.tolist(),
            "total_dependency_ratio": total_dependency.tolist(),
            "final_age_distribution": pop_history[-1].tolist(),
            "average_growth_rate": float(np.mean(growth_rates)),
        }


# ════════════════════════════════════════════════════════════════
# 5. Taylor Rule
# ════════════════════════════════════════════════════════════════


class TaylorRule:
    """
    Taylor Rule for monetary policy.

    i = r* + π + 0.5(π - π*) + 0.5(y - y*)

    where:
    - i = nominal interest rate (CBK policy rate)
    - r* = real equilibrium interest rate (~2%)
    - π = current inflation rate
    - π* = target inflation rate (CBK: 2.5% ± 2.5%)
    - y - y* = output gap (actual - potential GDP as %)

    Extended Taylor Rule (with exchange rate):
    i = r* + π + 0.5(π - π*) + 0.5(y - y*) + 0.5(e - e*)

    For Kenya:
    - CBK targets inflation at 2.5% (±2.5% band)
    - CBR has been 10-13% in recent years
    - Output gap estimated from production function approach
    """

    @staticmethod
    def compute(
        inflation: float,
        output_gap: float,
        target_inflation: float = 2.5,
        real_rate: float = 2.0,
        inflation_weight: float = 0.5,
        output_weight: float = 0.5,
        exchange_rate_gap: Optional[float] = None,
        exchange_rate_weight: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Compute the Taylor Rule recommended interest rate.

        Args:
            inflation: current inflation rate (%)
            output_gap: output gap as % of potential GDP
            target_inflation: central bank target (%)
            real_rate: equilibrium real interest rate (%)
            inflation_weight: weight on inflation gap
            output_weight: weight on output gap
            exchange_rate_gap: (actual - equilibrium) exchange rate (optional)
            exchange_rate_weight: weight on exchange rate gap

        Returns:
            Dict with recommended rate, deviation from actual, policy stance
        """
        # Basic Taylor Rule
        taylor_rate = real_rate + inflation + inflation_weight * (inflation - target_inflation) + output_weight * output_gap

        # Extended (with exchange rate)
        if exchange_rate_gap is not None:
            taylor_extended = taylor_rate + exchange_rate_weight * exchange_rate_gap
        else:
            taylor_extended = None

        # Policy stance
        inflation_gap = inflation - target_inflation
        stance = "NEUTRAL"
        if inflation_gap > 1 and output_gap > 0:
            stance = "HAWKISH (raise rates)"
        elif inflation_gap < -1 and output_gap < 0:
            stance = "DOVISH (lower rates)"
        elif inflation_gap > 0 and output_gap < 0:
            stance = "MIXED (inflation high but economy weak)"
        elif inflation_gap < 0 and output_gap > 0:
            stance = "MIXED (inflation low but economy strong)"

        return {
            "method": "Taylor Rule",
            "recommended_rate": float(taylor_rate),
            "recommended_rate_extended": float(taylor_extended) if taylor_extended else None,
            "components": {
                "real_equilibrium_rate": real_rate,
                "current_inflation": inflation,
                "inflation_gap": float(inflation_gap),
                "output_gap": output_gap,
                "inflation_component": float(inflation_weight * inflation_gap),
                "output_component": float(output_weight * output_gap),
            },
            "policy_stance": stance,
            "target_inflation": target_inflation,
        }

    @staticmethod
    def estimate_reaction_function(
        actual_rates: np.ndarray,
        inflation: np.ndarray,
        output_gap: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Estimate central bank reaction function from data.

        iₜ = α + β₁πₜ + β₂(y-y*)ₜ + εₜ

        Compare estimated coefficients to Taylor's (β₁ = 1.5, β₂ = 0.5).

        Args:
            actual_rates: historical policy rates
            inflation: historical inflation rates
            output_gap: historical output gap

        Returns:
            Dict with estimated coefficients, Taylor principle check
        """
        r = np.asarray(actual_rates, dtype=float).ravel()
        pi = np.asarray(inflation, dtype=float).ravel()
        yg = np.asarray(output_gap, dtype=float).ravel()
        n = min(len(r), len(pi), len(yg))

        X = np.column_stack([np.ones(n), pi[:n], yg[:n]])
        y = r[:n]

        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix"}

        residuals = y - X @ beta
        sigma2 = np.sum(residuals ** 2) / (n - 3)

        try:
            se = np.sqrt(sigma2 * np.diag(np.linalg.inv(X.T @ X)))
        except np.linalg.LinAlgError:
            se = np.full(3, float('nan'))

        intercept, beta_pi, beta_yg = beta

        # Taylor principle: β₁ > 1 means central bank raises rates more than 1-for-1 with inflation
        taylor_principle_satisfied = beta_pi > 1.0

        return {
            "intercept": float(intercept),
            "inflation_response": float(beta_pi),
            "output_gap_response": float(beta_yg),
            "std_errors": se.tolist(),
            "taylor_principle_satisfied": taylor_principle_satisfied,
            "interpretation": f"1% rise in inflation → {beta_pi:.2f}% rise in policy rate",
        }


# ════════════════════════════════════════════════════════════════
# 6. Okun's Law
# ════════════════════════════════════════════════════════════════


class OkunsLaw:
    """
    Okun's Law — relationship between GDP growth and unemployment.

    Gap version: u - u* = -c(Y - Y*)/Y*
    Growth version: Δu = a + b(ΔY/Y)

    Typical values: b ≈ -0.5 (1% GDP growth → 0.5% unemployment drop)

    For Kenya:
    - Okun coefficient estimated at -0.3 to -0.5
    - Employment responds slowly to GDP changes
    - Informal sector acts as shock absorber
    """

    @staticmethod
    def estimate(
        gdp_growth: np.ndarray,
        unemployment_change: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Estimate Okun's Law coefficient.

        Δu = a + b × ΔY/Y

        Args:
            gdp_growth: GDP growth rates (%)
            unemployment_change: change in unemployment rate (pp)

        Returns:
            Dict with Okun coefficient, R², diagnostics
        """
        dy = np.asarray(gdp_growth, dtype=float).ravel()
        du = np.asarray(unemployment_change, dtype=float).ravel()
        n = min(len(dy), len(du))

        X = np.column_stack([np.ones(n), dy[:n]])
        y = du[:n]

        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix"}

        intercept, okun_coef = beta
        predictions = X @ beta
        residuals = y - predictions
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        sigma2 = ss_res / (n - 2)
        try:
            se = np.sqrt(sigma2 * np.diag(np.linalg.inv(X.T @ X)))
        except np.linalg.LinAlgError:
            se = np.full(2, float('nan'))

        # Interpretation: 1% GDP growth → okun_coef pp change in unemployment
        return {
            "method": "Okun's Law",
            "okun_coefficient": float(okun_coef),
            "intercept": float(intercept),
            "r_squared": float(r_sq),
            "std_errors": se.tolist(),
            "n_obs": n,
            "interpretation": f"1% GDP growth → {abs(okun_coef):.2f}pp drop in unemployment",
        }

    @staticmethod
    def predict_unemployment_change(
        gdp_growth: float,
        okun_coefficient: float = -0.4,
        intercept: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Predict unemployment change from GDP growth.

        Args:
            gdp_growth: expected GDP growth rate (%)
            okun_coefficient: estimated Okun coefficient
            intercept: regression intercept

        Returns:
            Dict with predicted unemployment change
        """
        du = intercept + okun_coefficient * gdp_growth
        return {
            "predicted_unemployment_change": float(du),
            "gdp_growth": gdp_growth,
            "okun_coefficient": okun_coefficient,
            "interpretation": f"{gdp_growth}% GDP growth → {du:+.2f}pp unemployment change",
        }


# ════════════════════════════════════════════════════════════════
# 7. Fisher Equation
# ════════════════════════════════════════════════════════════════


class FisherEquation:
    """
    Fisher Equation — relationship between nominal and real interest rates.

    Exact: (1 + i) = (1 + r)(1 + π)
    Approximate: i ≈ r + π

    where:
    - i = nominal interest rate
    - r = real interest rate
    - π = expected inflation rate

    Also: r ≈ i - π (Fisher effect)

    For Kenya:
    - Treasury bill rates: 7-10%
    - Inflation: 5-8%
    - Real rate: ~2-3%
    """

    @staticmethod
    def compute(
        nominal_rate: Optional[float] = None,
        real_rate: Optional[float] = None,
        inflation_rate: Optional[float] = None,
        method: str = "exact",
    ) -> Dict[str, Any]:
        """
        Fisher Equation calculator.

        Provide any two of the three values; the third will be computed.

        Args:
            nominal_rate: nominal interest rate (%)
            real_rate: real interest rate (%)
            inflation_rate: expected inflation rate (%)
            method: "exact" or "approximate"

        Returns:
            Dict with all three rates and computation details
        """
        provided = sum(x is not None for x in [nominal_rate, real_rate, inflation_rate])
        if provided < 2:
            return {"error": "Provide at least 2 of: nominal_rate, real_rate, inflation_rate"}

        if nominal_rate is not None and inflation_rate is not None:
            i = nominal_rate / 100
            pi = inflation_rate / 100
            if method == "exact":
                r = (1 + i) / (1 + pi) - 1
            else:
                r = i - pi
            real_rate = r * 100

        elif nominal_rate is not None and real_rate is not None:
            i = nominal_rate / 100
            r = real_rate / 100
            if method == "exact":
                pi = (1 + i) / (1 + r) - 1
            else:
                pi = i - r
            inflation_rate = pi * 100

        elif real_rate is not None and inflation_rate is not None:
            r = real_rate / 100
            pi = inflation_rate / 100
            if method == "exact":
                i = (1 + r) * (1 + pi) - 1
            else:
                i = r + pi
            nominal_rate = i * 100

        # Approximation error
        if method == "exact":
            approx = real_rate / 100 + inflation_rate / 100
            exact = nominal_rate / 100
            approx_error = abs(exact - approx) * 100
        else:
            approx_error = 0.0

        return {
            "method": f"Fisher Equation ({method})",
            "nominal_rate": float(nominal_rate),
            "real_rate": float(real_rate),
            "inflation_rate": float(inflation_rate),
            "approximation_error_pp": float(approx_error),
            "formula": "(1+i) = (1+r)(1+π)" if method == "exact" else "i ≈ r + π",
        }


# ════════════════════════════════════════════════════════════════
# 8. Money Multiplier
# ════════════════════════════════════════════════════════════════


class MoneyMultiplier:
    """
    Money Multiplier — money supply creation process.

    Simple model:
        m = 1 / rr  (money multiplier)
        M = m × MB  (money supply = multiplier × monetary base)

    Extended model (with excess reserves and currency drain):
        m = (1 + c) / (rr + e + c)
        where:
        - c = currency-deposit ratio (C/D)
        - rr = required reserve ratio
        - e = excess reserve ratio (ER/D)

    Money supply measures:
    - M0 (base money): currency in circulation + reserves
    - M1: currency + demand deposits
    - M2: M1 + savings + time deposits

    For Kenya:
    - CBK reserve ratio: 4.25%
    - Currency-deposit ratio: ~0.3 (significant cash economy)
    - Money multiplier: ~3-4
    """

    @staticmethod
    def compute(
        monetary_base: Optional[float] = None,
        reserve_ratio: float = 0.0425,
        currency_deposit_ratio: float = 0.30,
        excess_reserve_ratio: float = 0.02,
        required_deposit_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute money multiplier and money supply.

        Args:
            monetary_base: monetary base (M0) in currency units
            reserve_ratio: required reserve ratio (rr)
            currency_deposit_ratio: currency-deposit ratio (c = C/D)
            excess_reserve_ratio: excess reserve ratio (e = ER/D)
            required_deposit_amount: if given, compute deposits needed for this base

        Returns:
            Dict with multiplier, money supply, components
        """
        rr = reserve_ratio
        c = currency_deposit_ratio
        e = excess_reserve_ratio

        # Simple multiplier (no currency drain)
        m_simple = 1 / rr if rr > 0 else float('inf')

        # Extended multiplier
        m_extended = (1 + c) / (rr + e + c)

        # Decomposition
        # M1 = C + D where C = cD, D = MB / (rr + e + c) (for base = C + R)
        # MB = C + R = cD + (rr + e)D = (c + rr + e)D

        result = {
            "method": "Money Multiplier",
            "simple_multiplier": float(m_simple),
            "extended_multiplier": float(m_extended),
            "parameters": {
                "reserve_ratio": rr,
                "currency_deposit_ratio": c,
                "excess_reserve_ratio": e,
            },
        }

        if monetary_base is not None:
            M1 = m_extended * monetary_base
            # Decompose
            D = monetary_base / (rr + e + c)  # total deposits
            C = c * D  # currency in circulation
            R = (rr + e) * D  # total reserves

            result.update({
                "monetary_base": monetary_base,
                "money_supply_M1": float(M1),
                "deposits": float(D),
                "currency": float(C),
                "reserves": float(R),
                "required_reserves": float(rr * D),
                "excess_reserves": float(e * D),
            })

        if required_deposit_amount is not None:
            # How much base money needed for target deposits
            base_needed = required_deposit_amount * (rr + e + c)
            m1_achieved = required_deposit_amount * (1 + c)
            result.update({
                "target_deposits": required_deposit_amount,
                "base_money_needed": float(base_needed),
                "M1_achieved": float(m1_achieved),
            })

        return result

    @staticmethod
    def simulate_monetary_expansion(
        initial_base: float,
        target_m1: float,
        reserve_ratio: float = 0.0425,
        currency_deposit_ratio: float = 0.30,
        excess_reserve_ratio: float = 0.02,
    ) -> Dict[str, Any]:
        """
        Simulate money supply expansion through the banking system.

        Shows how an initial injection ripples through banks.
        """
        rr = reserve_ratio
        c = currency_deposit_ratio
        e = excess_reserve_ratio

        rounds = []
        base_remaining = initial_base
        total_deposits = 0
        total_currency = 0

        for round_num in range(20):
            # Each round: bank lends out (1 - rr - e) of deposits received
            new_deposits = base_remaining / (rr + e + c)
            new_currency = c * new_deposits
            new_reserves = (rr + e) * new_deposits
            new_lending = new_deposits - new_reserves

            total_deposits += new_deposits
            total_currency += new_currency

            rounds.append({
                "round": round_num + 1,
                "new_deposits": float(new_deposits),
                "new_reserves": float(new_reserves),
                "cumulative_deposits": float(total_deposits),
                "cumulative_M1": float(total_deposits + total_currency),
            })

            # Next round's injection = lending that becomes deposits elsewhere
            base_remaining = new_lending
            if base_remaining < 0.01:
                break

            if total_deposits + total_currency >= target_m1:
                break

        m = (1 + c) / (rr + e + c)

        return {
            "method": "Money Expansion Simulation",
            "final_M1": float(total_deposits + total_currency),
            "multiplier_achieved": float((total_deposits + total_currency) / initial_base),
            "theoretical_multiplier": float(m),
            "rounds": rounds,
            "rounds_needed": len(rounds),
        }
