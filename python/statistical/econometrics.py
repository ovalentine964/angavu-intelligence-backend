"""
Econometrics Module for Angavu Intelligence Backend (ECO 414/424)

Implements core econometric methods used in credit scoring, impact evaluation,
and economic analysis for Kenya's informal sector:

1. OLS Regression — basic linear regression with diagnostics
2. Instrumental Variables (IV) / 2SLS — endogeneity correction
3. GMM Estimation — Generalized Method of Moments
4. Panel Data Methods — fixed/random effects for worker tracking
5. Heteroskedasticity Tests — Breusch-Pagan, White
6. Probit/Logit — limited dependent variable models
7. VAR/VECM — vector autoregression for macro forecasting
8. Cointegration — Engle-Granger test for long-run relationships

Mathematical Foundations:
- OLS: β̂ = (X'X)⁻¹X'y, with Gauss-Markov optimality under homoskedasticity
- IV: β̂_IV = (Z'X)⁻¹'Z'y, where Z are instruments
- 2SLS: First stage X = Zπ + v, Second stage y = Xβ + ε
- GMM: β̂ = argmin g(β)'W g(β) where g(β) = (1/n)ΣZᵢ(yᵢ - Xᵢβ)
- Panel FE: (yᵢ - ȳᵢ) = (Xᵢ - X̄ᵢ)β + (εᵢ - ε̄ᵢ)
- Probit: P(Y=1|X) = Φ(Xβ), estimated by MLE

Reference:
- Wooldridge, J. (2010). Econometric Analysis of Cross Section and Panel Data.
- Greene, W. (2018). Econometric Analysis.
- Cameron & Trivedi (2005). Microeconometrics.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy import stats as sp_stats


# ════════════════════════════════════════════════════════════════
# 1. OLS Regression
# ════════════════════════════════════════════════════════════════


@dataclass
class OLSResult:
    """Result container for OLS regression."""
    coefficients: np.ndarray       # β̂
    intercept: float               # β₀
    std_errors: np.ndarray         # SE(β̂)
    t_statistics: np.ndarray       # t = β̂/SE
    p_values: np.ndarray           # p-values
    r_squared: float               # R²
    adj_r_squared: float           # Adjusted R²
    f_statistic: float             # F-test for overall significance
    f_p_value: float               # p-value for F-test
    residual_std: float            # σ̂ = √(RSS/(n-k-1))
    n_obs: int                     # number of observations
    n_vars: int                    # number of predictors
    residuals: np.ndarray          # ê = y - Xβ̂
    predictions: np.ndarray        # ŷ = Xβ̂
    feature_names: List[str]       # variable names
    log_likelihood: float          # for model comparison
    aic: float                     # AIC
    bic: float                     # BIC


class OLSRegression:
    """
    Ordinary Least Squares regression.

    β̂ = (X'X)⁻¹X'y

    Under Gauss-Markov assumptions, OLS is BLUE (Best Linear Unbiased Estimator).

    Used for:
    - Revenue prediction from historical sales
    - Demand estimation (price elasticity)
    - Impact evaluation (difference-in-differences)
    """

    @staticmethod
    def fit(
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
        add_constant: bool = True,
    ) -> OLSResult:
        """
        Fit OLS regression.

        Args:
            X: n×p design matrix
            y: n-vector of outcomes
            feature_names: names for each predictor
            add_constant: add intercept column

        Returns:
            OLSResult with all diagnostics
        """
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        n, p_orig = X.shape

        if add_constant:
            X_design = np.column_stack([np.ones(n), X])
        else:
            X_design = X.copy()

        n_vars = X_design.shape[1]  # includes intercept if added

        if n <= n_vars:
            raise ValueError(f"Need n > k. Got n={n}, k={n_vars}")

        # β̂ = (X'X)⁻¹X'y
        XtX = X_design.T @ X_design
        Xty = X_design.T @ y

        try:
            XtX_inv = np.linalg.inv(XtX)
        except np.linalg.LinAlgError:
            XtX_inv = np.linalg.pinv(XtX)  # pseudoinverse if singular

        beta_hat = XtX_inv @ Xty

        # Predictions and residuals
        predictions = X_design @ beta_hat
        residuals = y - predictions

        # Variance estimate: σ̂² = RSS / (n - k)
        rss = np.sum(residuals ** 2)
        k = n_vars
        dof = n - k
        sigma2_hat = rss / dof
        residual_std = math.sqrt(sigma2_hat)

        # Covariance matrix of β̂: Var(β̂) = σ̂²(X'X)⁻¹
        var_beta = sigma2_hat * XtX_inv
        std_errors = np.sqrt(np.diag(var_beta))

        # t-statistics and p-values
        t_stats = beta_hat / std_errors
        p_values = 2 * (1 - sp_stats.t.cdf(np.abs(t_stats), df=dof))

        # R² and adjusted R²
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - rss / ss_tot if ss_tot > 0 else 0.0
        adj_r_squared = 1 - (1 - r_squared) * (n - 1) / dof if dof > 0 else 0.0

        # F-test: H₀: all slope coefficients = 0
        ss_reg = ss_tot - rss
        df_reg = k - 1 if add_constant else k
        df_resid = dof
        if df_reg > 0 and sigma2_hat > 0:
            f_stat = (ss_reg / df_reg) / sigma2_hat
            f_p_value = 1 - sp_stats.f.cdf(f_stat, df_reg, df_resid)
        else:
            f_stat = 0.0
            f_p_value = 1.0

        # Log-likelihood, AIC, BIC
        ll = -n / 2 * (math.log(2 * math.pi * sigma2_hat) + 1)
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * math.log(n)

        # Feature names
        if feature_names is None:
            feature_names = [f"x{i+1}" for i in range(p_orig)]
        if add_constant:
            feature_names = ["const"] + list(feature_names)

        return OLSResult(
            coefficients=beta_hat,
            intercept=float(beta_hat[0]) if add_constant else 0.0,
            std_errors=std_errors,
            t_statistics=t_stats,
            p_values=p_values,
            r_squared=r_squared,
            adj_r_squared=adj_r_squared,
            f_statistic=f_stat,
            f_p_value=f_p_value,
            residual_std=residual_std,
            n_obs=n,
            n_vars=k,
            residuals=residuals,
            predictions=predictions,
            feature_names=feature_names,
            log_likelihood=ll,
            aic=aic,
            bic=bic,
        )


# ════════════════════════════════════════════════════════════════
# 2. Heteroskedasticity Tests
# ════════════════════════════════════════════════════════════════


class HeteroskedasticityTests:
    """
    Tests for heteroskedasticity in regression residuals.

    Heteroskedasticity invalidates OLS standard errors.
    If detected, use robust (White) standard errors or GLS.

    For informal sector data: income variance typically increases
    with income level → heteroskedasticity is expected.
    """

    @staticmethod
    def breusch_pagan(
        residuals: np.ndarray,
        X: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Breusch-Pagan test for heteroskedasticity.

        H₀: Var(εᵢ) = σ² (homoskedasticity)
        H₁: Var(εᵢ) = σ² exp(Zᵢγ)

        Test: nR² from regressing ê² on X ~ χ²(p-1)

        Args:
            residuals: OLS residuals
            X: original design matrix (without constant)

        Returns:
            Dict with LM statistic, p-value, conclusion
        """
        residuals = np.asarray(residuals, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        n = len(residuals)

        # Squared residuals standardized
        e2 = residuals ** 2
        sigma2 = np.mean(e2)
        if sigma2 == 0:
            return {"error": "Zero residual variance"}

        # Regress e²/σ̂² on X
        g = e2 / sigma2
        X_design = np.column_stack([np.ones(n), X])
        try:
            beta = np.linalg.lstsq(X_design, g, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in BP test"}

        g_hat = X_design @ beta
        ss_res = np.sum((g - g_hat) ** 2)
        ss_tot = np.sum((g - np.mean(g)) ** 2)
        r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # LM = nR² ~ χ²(p-1)
        lm = n * r_sq
        df = X.shape[1]  # number of regressors (excluding constant)
        p_value = 1 - sp_stats.chi2.cdf(lm, df)

        return {
            "test": "Breusch-Pagan",
            "lm_statistic": float(lm),
            "df": df,
            "p_value": float(p_value),
            "heteroskedastic": p_value < 0.05,
            "interpretation": "Heteroskedasticity detected — use robust SE" if p_value < 0.05
                else "No heteroskedasticity detected",
        }

    @staticmethod
    def white_test(
        residuals: np.ndarray,
        X: np.ndarray,
    ) -> Dict[str, Any]:
        """
        White's general test for heteroskedasticity.

        More general than BP — tests for any form of heteroskedasticity
        by including squares and cross-products of regressors.

        H₀: Homoskedasticity
        LM = nR² from regressing ê² on X, X², XᵢXⱼ ~ χ²(q)

        Args:
            residuals: OLS residuals
            X: design matrix (without constant)

        Returns:
            Dict with test results
        """
        residuals = np.asarray(residuals, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        n, p = X.shape

        e2 = residuals ** 2

        # Build White regressors: X, X², cross-products
        white_vars = [np.ones(n)]
        for j in range(p):
            white_vars.append(X[:, j])
        for j in range(p):
            white_vars.append(X[:, j] ** 2)
        for j in range(p):
            for k in range(j + 1, p):
                white_vars.append(X[:, j] * X[:, k])

        Z = np.column_stack(white_vars)
        q = Z.shape[1] - 1  # degrees of freedom

        try:
            beta = np.linalg.lstsq(Z, e2, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in White test"}

        e2_hat = Z @ beta
        ss_res = np.sum((e2 - e2_hat) ** 2)
        ss_tot = np.sum((e2 - np.mean(e2)) ** 2)
        r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        lm = n * r_sq
        p_value = 1 - sp_stats.chi2.cdf(lm, q)

        return {
            "test": "White",
            "lm_statistic": float(lm),
            "df": q,
            "p_value": float(p_value),
            "heteroskedastic": p_value < 0.05,
            "interpretation": "Heteroskedasticity detected — use robust SE" if p_value < 0.05
                else "No heteroskedasticity detected",
        }

    @staticmethod
    def robust_standard_errors(
        X: np.ndarray,
        y: np.ndarray,
        residuals: np.ndarray,
    ) -> Dict[str, Any]:
        """
        White's heteroskedasticity-consistent (HC) standard errors.

        Var_HC(β̂) = (X'X)⁻¹ X'Ω X (X'X)⁻¹
        where Ω = diag(ê₁², ê₂², ..., êₙ²)

        Args:
            X: design matrix (with constant)
            y: outcome vector
            residuals: OLS residuals

        Returns:
            Dict with robust SE, t-stats, p-values
        """
        X = np.asarray(X, dtype=float)
        residuals = np.asarray(residuals, dtype=float).ravel()
        n = X.shape[0]

        XtX_inv = np.linalg.pinv(X.T @ X)
        Omega = np.diag(residuals ** 2)
        # Var_HC = (X'X)⁻¹ X'Ω X (X'X)⁻¹
        var_robust = XtX_inv @ (X.T @ Omega @ X) @ XtX_inv
        robust_se = np.sqrt(np.diag(var_robust))

        beta = XtX_inv @ (X.T @ y)
        t_robust = beta / robust_se
        p_robust = 2 * (1 - sp_stats.t.cdf(np.abs(t_robust), df=n - X.shape[1]))

        return {
            "robust_se": robust_se,
            "t_statistics": t_robust,
            "p_values": p_robust,
            "note": "HC0 (White) robust standard errors",
        }


# ════════════════════════════════════════════════════════════════
# 3. Instrumental Variables / 2SLS
# ════════════════════════════════════════════════════════════════


class IV2SLS:
    """
    Instrumental Variables and Two-Stage Least Squares (2SLS).

    Solves endogeneity: when E[X'ε] ≠ 0 (e.g., simultaneity, omitted variables).

    For informal economy:
    - Credit access → income (endogenous: high-income workers self-select into credit)
    - Instrument: geographic distance to nearest MFI branch
    - Education → earnings (endogenous: ability bias)
    - Instrument: birth quarter (natural experiment)

    Mathematical basis:
        2SLS First stage:  X = Zπ + v
        2SLS Second stage: y = Xβ̂ + ε
        where X̂ = Z(Z'Z)⁻¹Z'X = P_Z X

        β̂_2SLS = (X'P_Z X)⁻¹ X'P_Z y = (X̂'X̂)⁻¹ X̂'y
    """

    @staticmethod
    def two_stage_least_squares(
        y: np.ndarray,
        X_endog: np.ndarray,
        Z_instruments: np.ndarray,
        X_exog: Optional[np.ndarray] = None,
        feature_names: Optional[List[str]] = None,
        instrument_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        2SLS estimation.

        Args:
            y: outcome vector (n,)
            X_endog: endogenous regressors (n×k₁)
            Z_instruments: instruments (n×m)
            X_exog: exogenous regressors (n×k₀), optional
            feature_names: names for regressors
            instrument_names: names for instruments

        Returns:
            Dict with coefficients, SE, diagnostics
        """
        y = np.asarray(y, dtype=float).ravel()
        X_endog = np.asarray(X_endog, dtype=float)
        Z_instr = np.asarray(Z_instruments, dtype=float)
        n = len(y)

        if X_endog.ndim == 1:
            X_endog = X_endog.reshape(-1, 1)
        if Z_instr.ndim == 1:
            Z_instr = Z_instr.reshape(-1, 1)

        # Build full instrument matrix [Z, X_exog]
        if X_exog is not None:
            X_exog = np.asarray(X_exog, dtype=float)
            if X_exog.ndim == 1:
                X_exog = X_exog.reshape(-1, 1)
            Z_full = np.column_stack([Z_instr, X_exog])
        else:
            Z_full = Z_instr

        # Build full regressor matrix [X_endog, X_exog]
        if X_exog is not None:
            X_full = np.column_stack([X_endog, X_exog])
        else:
            X_full = X_endog

        # Add constant
        ones = np.ones((n, 1))
        Z_aug = np.column_stack([ones, Z_full])
        X_aug = np.column_stack([ones, X_full])

        k = X_aug.shape[1]
        m = Z_aug.shape[1]

        if n < m:
            return {"error": f"Need n ≥ instruments. Got n={n}, m={m}"}

        # First stage: X̂ = P_Z X where P_Z = Z(Z'Z)⁻¹Z'
        try:
            ZtZ_inv = np.linalg.inv(Z_aug.T @ Z_aug)
        except np.linalg.LinAlgError:
            return {"error": "Singular instrument matrix — weak instruments?"}

        P_Z = Z_aug @ ZtZ_inv @ Z_aug.T  # Projection matrix
        X_hat = P_Z @ X_aug

        # Second stage: β̂ = (X̂'X̂)⁻¹ X̂'y
        try:
            XtX_hat_inv = np.linalg.inv(X_hat.T @ X_hat)
        except np.linalg.LinAlgError:
            return {"error": "Singular fitted regressor matrix"}

        beta_2sls = XtX_hat_inv @ (X_hat.T @ y)

        # Residuals
        residuals = y - X_aug @ beta_2sls

        # Standard errors: σ̂² = ê'ê/(n-k), Var = σ̂²(X̂'X̂)⁻¹
        sigma2 = np.sum(residuals ** 2) / (n - k)
        var_beta = sigma2 * XtX_hat_inv
        se = np.sqrt(np.diag(var_beta))

        # Identification test: need m ≥ k (order condition)
        order = m - k
        identified = order >= 0

        # Weak instrument test: first-stage F-statistic
        first_stage_f = None
        first_stage_p = None
        if X_endog.shape[1] > 0:
            # Partial F-test for excluded instruments
            y_first = X_endog[:, 0]  # test first endogenous variable
            # Restricted model: y_first on X_exog only
            if X_exog is not None:
                X_rest = np.column_stack([ones, X_exog])
            else:
                X_rest = ones
            beta_rest = np.linalg.lstsq(X_rest, y_first, rcond=None)[0]
            rss_rest = np.sum((y_first - X_rest @ beta_rest) ** 2)
            # Unrestricted: y_first on Z_full
            beta_unrest = np.linalg.lstsq(Z_aug, y_first, rcond=None)[0]
            rss_unrest = np.sum((y_first - Z_aug @ beta_unrest) ** 2)
            df1 = Z_aug.shape[1] - X_rest.shape[1]
            df2 = n - Z_aug.shape[1]
            if df1 > 0 and rss_unrest > 0:
                first_stage_f = ((rss_rest - rss_unrest) / df1) / (rss_unrest / df2)
                first_stage_p = 1 - sp_stats.f.cdf(first_stage_f, df1, df2)

        # t-stats and p-values
        t_stats = beta_2sls / se
        p_values = 2 * (1 - sp_stats.t.cdf(np.abs(t_stats), df=n - k))

        # Feature names
        if feature_names is None:
            feature_names = [f"x{i}" for i in range(X_endog.shape[1])]
            if X_exog is not None:
                feature_names += [f"exog{i}" for i in range(X_exog.shape[1])]

        return {
            "method": "2SLS",
            "coefficients": beta_2sls.tolist(),
            "std_errors": se.tolist(),
            "t_statistics": t_stats.tolist(),
            "p_values": p_values.tolist(),
            "n_obs": n,
            "n_regressors": k,
            "n_instruments": m,
            "order_condition": order,
            "identified": identified,
            "first_stage_f": first_stage_f,
            "first_stage_p": first_stage_p,
            "weak_instruments": first_stage_f is not None and first_stage_f < 10,
            "feature_names": ["const"] + list(feature_names),
            "residual_std": math.sqrt(sigma2),
            "note": "Weak instrument F < 10 suggests instruments may be invalid",
        }


# ════════════════════════════════════════════════════════════════
# 4. GMM Estimation
# ════════════════════════════════════════════════════════════════


class GMMEstimator:
    """
    Generalized Method of Moments (GMM) estimation.

    More efficient than 2SLS when heteroskedasticity is present.
    Uses optimal weighting matrix W = S⁻¹ where S = E[gᵢgᵢ'].

    Mathematical basis:
        Moment conditions: E[gᵢ(β)] = 0
        where gᵢ(β) = Zᵢ(yᵢ - Xᵢβ)

        GMM objective: J(β) = g(β)'W g(β)
        Optimal W: W = (1/n)Σ gᵢgᵢ' = Ŝ⁻¹

        Two-step GMM:
        Step 1: W = I (identity) → β̂₁
        Step 2: W = Ŝ(β̂₁)⁻¹ → β̂₂ (efficient)

        J-test: J = n × g(β̂₂)'Ŝ⁻¹g(β̂₂) ~ χ²(m-k) under H₀
    """

    @staticmethod
    def two_step_gmm(
        y: np.ndarray,
        X: np.ndarray,
        Z: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Two-step GMM estimation.

        Args:
            y: outcome vector (n,)
            X: regressor matrix (n×k)
            Z: instrument matrix (n×m)

        Returns:
            Dict with GMM estimates, J-test, diagnostics
        """
        y = np.asarray(y, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        Z = np.asarray(Z, dtype=float)

        if X.ndim == 1:
            X = X.reshape(-1, 1)
        if Z.ndim == 1:
            Z = Z.reshape(-1, 1)

        n = len(y)
        k = X.shape[1]
        m = Z.shape[1]

        # Add constant
        ones = np.ones((n, 1))
        X_aug = np.column_stack([ones, X])
        Z_aug = np.column_stack([ones, Z])  # instruments include constant
        k_aug = k + 1

        # Moment function: g(β) = (1/n) Σ Zᵢ(yᵢ - Xᵢβ)
        def moment_conditions(beta):
            residuals = y - X_aug @ beta
            return (Z_aug.T * residuals).T  # n×m matrix

        # Step 1: W = I (identity)
        # Initial estimate: 2SLS with identity weight
        # β̂₁ = (X'Z(Z'Z)⁻¹Z'X)⁻¹ X'Z(Z'Z)⁻¹Z'y
        try:
            ZtZ_inv = np.linalg.inv(Z_aug.T @ Z_aug / n)
        except np.linalg.LinAlgError:
            return {"error": "Singular instrument matrix"}

        # Project X onto Z: X̂ = Z(Z'Z)⁻¹Z'X
        P_Z = Z_aug @ ZtZ_inv @ Z_aug.T / n  # Approx projection
        X_hat = P_Z @ X_aug
        try:
            beta_1 = np.linalg.lstsq(X_hat, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Failed initial GMM estimate"}

        # Compute moment covariance at β̂₁
        g1 = moment_conditions(beta_1)  # n×m
        S1 = g1.T @ g1 / n  # m×m

        # Step 2: W = Ŝ⁻¹
        try:
            W2 = np.linalg.inv(S1)
        except np.linalg.LinAlgError:
            W2 = np.eye(m)

        # GMM: β̂₂ = (X'Z W Z'X)⁻¹ X'Z W Z'y
        # X_aug: n×k, Z_aug: n×m, W2: m×m
        XtZ = X_aug.T @ Z_aug        # k×m
        ZtX = Z_aug.T @ X_aug        # m×k
        Zty = Z_aug.T @ y            # m-vector
        XtZ_W = XtZ @ W2             # k×m
        A = XtZ_W @ ZtX              # k×k
        b = XtZ_W @ Zty              # k-vector

        try:
            beta_2 = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            return {"error": "Singular GMM system"}

        XZWZX = A  # reuse for variance

        # Residuals and J-statistic
        residuals = y - X_aug @ beta_2
        g2 = moment_conditions(beta_2)
        g_bar = g2.mean(axis=0)  # m-vector
        S2 = g2.T @ g2 / n

        try:
            S2_inv = np.linalg.inv(S2)
        except np.linalg.LinAlgError:
            S2_inv = np.eye(m)

        J = n * g_bar @ S2_inv @ g_bar  # J-statistic
        df_overid = m - k_aug
        j_p_value = 1 - sp_stats.chi2.cdf(J, max(0, df_overid)) if df_overid > 0 else None

        # Asymptotic variance: Var(β̂₂) = (1/n)(X'ZWZ'X)⁻¹
        try:
            var_beta = np.linalg.inv(XZWZX) / n
            se = np.sqrt(np.diag(var_beta))
        except np.linalg.LinAlgError:
            se = np.full(k_aug, float('nan'))

        t_stats = beta_2 / se
        p_values = 2 * (1 - sp_stats.norm.cdf(np.abs(t_stats)))

        names = ["const"]
        if feature_names:
            names += list(feature_names)
        else:
            names += [f"x{i+1}" for i in range(k)]

        return {
            "method": "Two-step GMM",
            "coefficients": beta_2.tolist(),
            "std_errors": se.tolist(),
            "t_statistics": t_stats.tolist(),
            "p_values": p_values.tolist(),
            "j_statistic": float(J),
            "j_df": df_overid,
            "j_p_value": float(j_p_value) if j_p_value is not None else None,
            "overidentified": df_overid > 0,
            "n_obs": n,
            "n_instruments": m,
            "n_regressors": k_aug,
            "feature_names": names,
        }


# ════════════════════════════════════════════════════════════════
# 5. Panel Data Methods
# ════════════════════════════════════════════════════════════════


class PanelDataEstimator:
    """
    Panel data estimation for tracking workers over time.

    Fixed Effects (FE): removes time-invariant unobserved heterogeneity.
    Random Effects (RE): more efficient if unobserved effects are uncorrelated with X.

    For informal workers:
    - Panel = repeated observations of same worker over time
    - FE controls for worker-specific ability/motivation (unobserved)
    - RE when worker effects are random (e.g., random sample of workers)

    Mathematical basis:
        yᵢₜ = αᵢ + Xᵢₜβ + εᵢₜ

        FE: αᵢ removed by within-transformation
            ȳᵢ = αᵢ + X̄ᵢβ + ε̄ᵢ
            (yᵢₜ - ȳᵢ) = (Xᵢₜ - X̄ᵢ)β + (εᵢₜ - ε̄ᵢ)

        RE: GLS transformation using θ = 1 - √(σ²_ε / (σ²_ε + Tσ²_α))
    """

    @staticmethod
    def fixed_effects(
        y: np.ndarray,
        X: np.ndarray,
        groups: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fixed Effects (within) estimator.

        Args:
            y: outcome vector (n_obs,)
            X: regressor matrix (n_obs × k)
            groups: group/individual identifier (n_obs,)

        Returns:
            Dict with FE estimates, within R², diagnostics
        """
        y = np.asarray(y, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        groups = np.asarray(groups)
        n_obs = len(y)
        k = X.shape[1]

        if X.ndim == 1:
            X = X.reshape(-1, 1)

        # Get unique groups
        unique_groups = np.unique(groups)
        n_groups = len(unique_groups)

        if n_groups >= n_obs:
            return {"error": "More groups than observations — no within variation"}

        # Within transformation: demean by group
        y_within = np.zeros(n_obs)
        X_within = np.zeros_like(X)

        group_indices = {}
        for g in unique_groups:
            idx = np.where(groups == g)[0]
            group_indices[g] = idx
            y_mean = np.mean(y[idx])
            X_mean = np.mean(X[idx], axis=0)
            y_within[idx] = y[idx] - y_mean
            X_within[idx] = X[idx] - X_mean

        # OLS on demeaned data
        result = OLSRegression.fit(X_within, y_within, feature_names=feature_names, add_constant=False)

        # Group-level statistics
        group_sizes = [len(group_indices[g]) for g in unique_groups]

        # F-test for fixed effects (H₀: all αᵢ equal)
        # Compare FE model with pooled OLS
        pooled = OLSRegression.fit(X, y, feature_names=feature_names, add_constant=True)
        f_fe = ((pooled.r_squared - result.r_squared) / (n_groups - 1)) / \
               ((1 - result.r_squared) / (n_obs - n_groups - k))
        f_fe_p = 1 - sp_stats.f.cdf(f_fe, n_groups - 1, n_obs - n_groups - k)

        return {
            "method": "Fixed Effects (Within)",
            "coefficients": result.coefficients.tolist(),
            "std_errors": result.std_errors.tolist(),
            "p_values": result.p_values.tolist(),
            "within_r_squared": result.r_squared,
            "n_obs": n_obs,
            "n_groups": n_groups,
            "avg_group_size": float(np.mean(group_sizes)),
            "min_group_size": int(np.min(group_sizes)),
            "max_group_size": int(np.max(group_sizes)),
            "fe_f_test": float(f_fe),
            "fe_f_p_value": float(f_fe_p),
            "fe_significant": f_fe_p < 0.05,
            "feature_names": result.feature_names,
            "note": "FE removes time-invariant unobserved heterogeneity",
        }

    @staticmethod
    def random_effects(
        y: np.ndarray,
        X: np.ndarray,
        groups: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Random Effects (GLS) estimator.

        Uses θ = 1 - √(σ²_ε / (σ²_ε + Tσ²_α)) to GLS-transform.

        Args:
            y: outcome vector
            X: regressor matrix
            groups: group identifiers

        Returns:
            Dict with RE estimates
        """
        y = np.asarray(y, dtype=float).ravel()
        X = np.asarray(X, dtype=float)
        groups = np.asarray(groups)
        n_obs = len(y)

        if X.ndim == 1:
            X = X.reshape(-1, 1)

        unique_groups = np.unique(groups)
        n_groups = len(unique_groups)

        # Step 1: Get FE residuals to estimate σ²_ε
        fe_result = PanelDataEstimator.fixed_effects(y, X, groups, feature_names)
        if "error" in fe_result:
            return fe_result

        # Estimate σ²_ε from FE residuals
        # Use within residuals
        y_within = np.zeros(n_obs)
        X_within = np.zeros_like(X)
        group_sizes = {}

        for g in unique_groups:
            idx = np.where(groups == g)[0]
            group_sizes[g] = len(idx)
            y_within[idx] = y[idx] - np.mean(y[idx])
            X_within[idx] = X[idx] - np.mean(X[idx], axis=0)

        fe_coefs = np.array(fe_result["coefficients"])
        residuals_fe = y_within - X_within @ fe_coefs
        sigma2_e = np.sum(residuals_fe ** 2) / (n_obs - n_groups - X.shape[1])

        # Estimate σ²_α from between-group variation
        y_means = np.array([np.mean(y[groups == g]) for g in unique_groups])
        T_bar = np.mean(list(group_sizes.values()))
        # σ̂²_α = (MS_between - σ̂²_ε) / T̄
        ss_between = sum(group_sizes[g] * (y_means[i] - np.mean(y)) ** 2
                        for i, g in enumerate(unique_groups))
        ms_between = ss_between / (n_groups - 1)
        sigma2_alpha = max(0, (ms_between - sigma2_e) / T_bar)

        # θ transformation
        T = T_bar  # average T
        theta = 1 - math.sqrt(sigma2_e / (sigma2_e + T * sigma2_alpha)) if (sigma2_e + T * sigma2_alpha) > 0 else 0

        # GLS transformation: quasi-demean
        y_gls = np.zeros(n_obs)
        X_gls = np.zeros_like(X)

        for g in unique_groups:
            idx = np.where(groups == g)[0]
            T_g = len(idx)
            y_mean_g = np.mean(y[idx])
            X_mean_g = np.mean(X[idx], axis=0)
            y_gls[idx] = y[idx] - theta * y_mean_g
            X_gls[idx] = X[idx] - theta * X_mean_g

        # OLS on quasi-demeaned data
        re_result = OLSRegression.fit(X_gls, y_gls, feature_names=feature_names, add_constant=True)

        return {
            "method": "Random Effects (GLS)",
            "coefficients": re_result.coefficients.tolist(),
            "std_errors": re_result.std_errors.tolist(),
            "p_values": re_result.p_values.tolist(),
            "r_squared": re_result.r_squared,
            "theta": float(theta),
            "sigma2_epsilon": float(sigma2_e),
            "sigma2_alpha": float(sigma2_alpha),
            "n_obs": n_obs,
            "n_groups": n_groups,
            "feature_names": re_result.feature_names,
        }

    @staticmethod
    def hausman_test(
            fe_result: Dict[str, Any],
            re_result: Dict[str, Any],
        ) -> Dict[str, Any]:
        """
        Hausman test: FE vs RE.

        H₀: RE is consistent (E[αᵢ|X] = 0)
        H₁: FE needed (correlation between αᵢ and X)

        H = (β̂_FE - β̂_RE)' [Var(β̂_FE) - Var(β̂_RE)]⁻¹ (β̂_FE - β̂_RE) ~ χ²(k)

        Args:
            fe_result: output from fixed_effects
            re_result: output from random_effects

        Returns:
            Dict with Hausman statistic and recommendation
        """
        fe_betas = np.array(fe_result["coefficients"])
        re_betas = np.array(re_result["coefficients"])

        # Align dimensions (FE has no intercept)
        k = min(len(fe_betas), len(re_betas) - 1)  # exclude RE intercept
        fe_b = fe_betas[:k]
        re_b = re_betas[1:k+1]  # skip RE intercept

        diff = fe_b - re_b

        fe_se = np.array(fe_result["std_errors"])[:k]
        re_se = np.array(re_result["std_errors"])[1:k+1]

        # Var(diff) = Var(FE) - Var(RE)
        var_diff = np.diag(fe_se ** 2) - np.diag(re_se ** 2)

        try:
            var_diff_inv = np.linalg.inv(var_diff)
        except np.linalg.LinAlgError:
            return {"error": "Singular variance difference — Hausman test not applicable"}

        H = diff @ var_diff_inv @ diff
        p_value = 1 - sp_stats.chi2.cdf(H, k)

        return {
            "test": "Hausman",
            "statistic": float(H),
            "df": k,
            "p_value": float(p_value),
            "use_fixed_effects": p_value < 0.05,
            "recommendation": "Use Fixed Effects (RE inconsistent)" if p_value < 0.05
                else "Random Effects is consistent and more efficient",
        }


# ════════════════════════════════════════════════════════════════
# 6. Probit/Logit (Limited Dependent Variables)
# ════════════════════════════════════════════════════════════════


class LimitedDependentVariable:
    """
    Probit and Logit models for binary outcomes.

    Used for:
    - Credit default prediction (P(default|features))
    - Binary treatment effects (participated or not)
    - Market entry decisions

    Mathematical basis:
        Logit: P(Y=1|X) = Λ(Xβ) = exp(Xβ)/(1+exp(Xβ))
        Probit: P(Y=1|X) = Φ(Xβ) = ∫_{-∞}^{Xβ} φ(z)dz

        Both estimated by MLE:
        ℓ(β) = Σ[yᵢ log F(Xᵢβ) + (1-yᵢ) log(1-F(Xᵢβ))]

        where F = Λ (logit) or Φ (probit)
    """

    @staticmethod
    def logit(
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
        max_iter: int = 50,
        tol: float = 1e-8,
    ) -> Dict[str, Any]:
        """
        Logit (logistic regression) via IRLS.

        Args:
            X: design matrix (n×p)
            y: binary outcome (0/1)
            feature_names: variable names
            max_iter: maximum IRLS iterations
            tol: convergence tolerance

        Returns:
            Dict with coefficients, marginal effects, diagnostics
        """
        return LimitedDependentVariable._fit_glm(X, y, "logit", feature_names, max_iter, tol)

    @staticmethod
    def probit(
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
        max_iter: int = 50,
        tol: float = 1e-8,
    ) -> Dict[str, Any]:
        """
        Probit model via IRLS.

        Args:
            X: design matrix
            y: binary outcome
            feature_names: variable names

        Returns:
            Dict with coefficients, marginal effects, diagnostics
        """
        return LimitedDependentVariable._fit_glm(X, y, "probit", feature_names, max_iter, tol)

    @staticmethod
    def _fit_glm(
        X: np.ndarray,
        y: np.ndarray,
        link: str,
        feature_names: Optional[List[str]],
        max_iter: int,
        tol: float,
    ) -> Dict[str, Any]:
        """IRLS estimation for GLM with logit/probit link."""
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        n, p = X.shape

        # Add constant
        X_aug = np.column_stack([np.ones(n), X])
        k = p + 1

        if feature_names is None:
            feature_names = [f"x{i+1}" for i in range(p)]

        # Initialize β = 0
        beta = np.zeros(k)

        # Link functions
        if link == "logit":
            def F(z): return 1 / (1 + np.exp(-np.clip(z, -500, 500)))
            def f(z): p = F(z); return p * (1 - p)
        else:  # probit
            def F(z): return sp_stats.norm.cdf(z)
            def f(z): return sp_stats.norm.pdf(z)

        # IRLS iterations
        converged = False
        ll_old = -np.inf

        for iteration in range(max_iter):
            eta = X_aug @ beta
            mu = F(eta)
            mu = np.clip(mu, 1e-10, 1 - 1e-10)

            # Working weights: W = diag(f(η)² / (μ(1-μ)))
            f_eta = f(eta)
            w = f_eta ** 2 / (mu * (1 - mu))
            w = np.clip(w, 1e-10, 1e10)

            # Working response: z = η + (y - μ)/f(η)
            z = eta + (y - mu) / np.clip(f_eta, 1e-10, 1e10)

            # Weighted least squares
            W = np.diag(w)
            XtWX = X_aug.T @ W @ X_aug
            XtWz = X_aug.T @ W @ z

            try:
                beta_new = np.linalg.solve(XtWX, XtWz)
            except np.linalg.LinAlgError:
                return {"error": "Singular matrix in IRLS"}

            # Log-likelihood
            ll = np.sum(y * np.log(mu) + (1 - y) * np.log(1 - mu))

            # Check convergence
            if abs(ll - ll_old) < tol:
                converged = True
                beta = beta_new
                break

            beta = beta_new
            ll_old = ll

        # Final estimates
        eta = X_aug @ beta
        mu = F(eta)
        mu = np.clip(mu, 1e-10, 1 - 1e-10)

        # Variance-covariance: (X'WX)⁻¹
        f_eta = f(eta)
        w = f_eta ** 2 / (mu * (1 - mu))
        W = np.diag(w)
        XtWX = X_aug.T @ W @ X_aug
        try:
            var_beta = np.linalg.inv(XtWX)
        except np.linalg.LinAlgError:
            var_beta = np.linalg.pinv(XtWX)

        se = np.sqrt(np.diag(var_beta))
        z_stats = beta / se
        p_values = 2 * (1 - sp_stats.norm.cdf(np.abs(z_stats)))

        # Pseudo R² (McFadden)
        ll_null = np.sum(y * np.log(np.mean(y)) + (1 - y) * np.log(1 - np.mean(y)))
        pseudo_r2 = 1 - ll / ll_null if ll_null != 0 else 0

        # AIC, BIC
        aic = -2 * ll + 2 * k
        bic = -2 * ll + k * math.log(n)

        # Predictions and classification
        predictions = (mu >= 0.5).astype(int)
        accuracy = np.mean(predictions == y)

        # Marginal effects at means
        X_mean = X_aug.mean(axis=0)
        eta_mean = X_mean @ beta
        if link == "logit":
            me = F(eta_mean) * (1 - F(eta_mean)) * beta
        else:
            me = sp_stats.norm.pdf(eta_mean) * beta

        return {
            "method": link.capitalize(),
            "coefficients": beta.tolist(),
            "std_errors": se.tolist(),
            "z_statistics": z_stats.tolist(),
            "p_values": p_values.tolist(),
            "log_likelihood": float(ll),
            "pseudo_r_squared": float(pseudo_r2),
            "aic": float(aic),
            "bic": float(bic),
            "accuracy": float(accuracy),
            "n_obs": n,
            "converged": converged,
            "marginal_effects_at_means": me.tolist(),
            "feature_names": ["const"] + list(feature_names),
        }


# ════════════════════════════════════════════════════════════════
# 7. VAR/VECM (Vector Autoregression)
# ════════════════════════════════════════════════════════════════


class VARModel:
    """
    Vector Autoregression (VAR) for multivariate time series.

    Used for:
    - Macro forecasting: inflation, exchange rates, GDP together
    - Impulse response functions
    - Granger causality tests

    Mathematical basis:
        Yₜ = c + A₁Yₜ₋₁ + A₂Yₜ₋₂ + ... + AₚYₜ₋ₚ + εₜ

        where Yₜ is a k×1 vector, Aᵢ are k×k coefficient matrices
    """

    @staticmethod
    def fit(
        data: np.ndarray,
        max_lags: int = 4,
        variable_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fit VAR model with automatic lag selection (AIC).

        Args:
            data: T×k matrix (T observations, k variables)
            max_lags: maximum lags to consider
            variable_names: names for variables

        Returns:
            Dict with VAR coefficients, lag order, diagnostics
        """
        data = np.asarray(data, dtype=float)
        T, k = data.shape

        if variable_names is None:
            variable_names = [f"y{i+1}" for i in range(k)]

        # Lag selection by AIC
        best_aic = np.inf
        best_p = 1
        best_result = None

        for p in range(1, max_lags + 1):
            if T - p <= k * p + 1:
                break

            # Build lagged data matrix
            Y = data[p:]  # (T-p)×k
            X = np.ones((T - p, 1))  # constant
            for lag in range(1, p + 1):
                X = np.column_stack([X, data[p - lag:T - lag]])  # lagged values

            # OLS for each equation
            n = T - p
            n_vars = k * p + 1

            try:
                B = np.linalg.lstsq(X, Y, rcond=None)[0]  # (n_vars × k)
            except np.linalg.LinAlgError:
                continue

            residuals = Y - X @ B
            sigma = residuals.T @ residuals / n

            # AIC for VAR: ln|Σ̂| + (2/n) × k × (k×p + 1)
            sign, logdet = np.linalg.slogdet(sigma)
            aic = logdet + (2.0 / n) * k * n_vars

            if aic < best_aic:
                best_aic = aic
                best_p = p
                best_result = {
                    "coefficients": B,
                    "residuals": residuals,
                    "sigma": sigma,
                    "n": n,
                }

        if best_result is None:
            return {"error": "Could not fit VAR model"}

        # Extract results
        B = best_result["coefficients"]
        sigma = best_result["sigma"]
        n = best_result["n"]
        p = best_p

        # Granger causality tests
        granger_tests = {}
        for i in range(k):
            for j in range(k):
                if i != j:
                    # Test if variable j Granger-causes variable i
                    # Restricted: Yᵢ on own lags only
                    # Unrestricted: Yᵢ on own lags + lags of Yⱼ
                    Y_dep = data[p:, i]
                    # Unrestricted
                    X_unr = np.ones((n, 1))
                    for lag in range(1, p + 1):
                        X_unr = np.column_stack([X_unr, data[p-lag:T-lag]])
                    beta_unr = np.linalg.lstsq(X_unr, Y_dep, rcond=None)[0]
                    rss_unr = np.sum((Y_dep - X_unr @ beta_unr) ** 2)

                    # Restricted: only own lags
                    X_res = np.ones((n, 1))
                    for lag in range(1, p + 1):
                        X_res = np.column_stack([X_res, data[p-lag:T-lag, i:i+1]])
                    beta_res = np.linalg.lstsq(X_res, Y_dep, rcond=None)[0]
                    rss_res = np.sum((Y_dep - X_res @ beta_res) ** 2)

                    df1 = p * (k - 1)
                    df2 = n - (k * p + 1)
                    if df1 > 0 and df2 > 0 and rss_unr > 0:
                        f_gc = ((rss_res - rss_unr) / df1) / (rss_unr / df2)
                        p_gc = 1 - sp_stats.f.cdf(f_gc, df1, df2)
                        granger_tests[f"{variable_names[j]}_causes_{variable_names[i]}"] = {
                            "f_statistic": float(f_gc),
                            "p_value": float(p_gc),
                            "causes": p_gc < 0.05,
                        }

        # Coefficient matrix organized by lag
        lag_matrices = []
        for lag in range(1, p + 1):
            start = 1 + (lag - 1) * k
            end = start + k
            lag_matrices.append(B[start:end, :].tolist())

        return {
            "method": f"VAR({p})",
            "lag_order": p,
            "n_obs": n,
            "n_variables": k,
            "variable_names": variable_names,
            "lag_coefficients": lag_matrices,
            "intercept": B[0, :].tolist(),
            "residual_covariance": sigma.tolist(),
            "aic": float(best_aic),
            "granger_causality": granger_tests,
        }


# ════════════════════════════════════════════════════════════════
# 8. Cointegration (Engle-Granger)
# ════════════════════════════════════════════════════════════════


class CointegrationTest:
    """
    Engle-Granger cointegration test.

    Tests for long-run equilibrium relationships between non-stationary series.
    If two I(1) series are cointegrated, a linear combination is I(0).

    For informal economy:
    - Price and cost of goods (should move together long-run)
    - Income and consumption
    - Exchange rates and import prices

    Mathematical basis:
        Step 1: yₜ = α + βxₜ + εₜ (long-run OLS)
        Step 2: Test êₜ for stationarity (ADF test)
        If êₜ ~ I(0), then y and x are cointegrated
    """

    @staticmethod
    def engle_granger(
        y: np.ndarray,
        x: np.ndarray,
        max_lags: int = 4,
    ) -> Dict[str, Any]:
        """
        Engle-Granger two-step cointegration test.

        Args:
            y: first time series
            x: second time series
            max_lags: max lags for ADF test

        Returns:
            Dict with cointegrating relationship, ADF test, conclusion
        """
        y = np.asarray(y, dtype=float).ravel()
        x = np.asarray(x, dtype=float).ravel()
        n = len(y)

        if len(x) != n:
            return {"error": "y and x must have same length"}

        # Step 1: OLS regression (long-run relationship)
        X_design = np.column_stack([np.ones(n), x])
        beta = np.linalg.lstsq(X_design, y, rcond=None)[0]
        alpha, beta_hat = beta[0], beta[1]
        residuals = y - (alpha + beta_hat * x)

        # Step 2: ADF test on residuals
        adf_result = CointegrationTest._adf_test(residuals, max_lags)

        # Critical values for Engle-Granger (approximate)
        # These are more negative than standard ADF critical values
        eg_critical = {
            "1%": -3.90,
            "5%": -3.34,
            "10%": -3.04,
        }

        adf_stat = adf_result["adf_statistic"]
        cointegrated = adf_stat < eg_critical["5%"]

        return {
            "test": "Engle-Granger cointegration",
            "cointegrating_vector": {"alpha": float(alpha), "beta": float(beta_hat)},
            "adf_statistic": float(adf_stat),
            "adf_p_value": float(adf_result.get("p_value", 0)),
            "critical_values": eg_critical,
            "cointegrated": cointegrated,
            "conclusion": "Long-run equilibrium exists" if cointegrated
                else "No cointegration — series drift apart",
            "n_obs": n,
        }

    @staticmethod
    def _adf_test(series: np.ndarray, max_lags: int) -> Dict[str, Any]:
        """Augmented Dickey-Fuller test for unit root."""
        series = np.asarray(series, dtype=float).ravel()
        n = len(series)

        # Δyₜ = α + γyₜ₋₁ + ΣδᵢΔyₜ₋ᵢ + εₜ
        dy = np.diff(series)
        y_lag = series[:-1]
        n_eff = len(dy) - max_lags

        if n_eff < 10:
            return {"error": "Too few observations for ADF"}

        # Build regressor matrix
        # Δyₜ = α + γyₜ₋₁ + ΣδᵢΔyₜ₋ᵢ + εₜ
        # Y = dy[max_lags:] has length n_eff
        # y_lag[max_lags:] has length n_eff (aligned lagged levels)
        # For lagged differences: dy[max_lags - lag : max_lags - lag + n_eff]
        Y = dy[max_lags:]
        X = np.column_stack([
            np.ones(n_eff),
            y_lag[max_lags:max_lags + n_eff],
        ])
        for lag in range(1, max_lags + 1):
            lagged_dy = dy[max_lags - lag : max_lags - lag + n_eff]
            X = np.column_stack([X, lagged_dy])

        beta = np.linalg.lstsq(X, Y, rcond=None)[0]
        residuals = Y - X @ beta

        # γ coefficient (on y_{t-1})
        gamma = beta[1]
        sigma2 = np.sum(residuals ** 2) / (n_eff - X.shape[1])
        var_gamma = sigma2 * np.linalg.inv(X.T @ X)[1, 1]
        se_gamma = math.sqrt(abs(var_gamma))

        adf_stat = gamma / se_gamma

        # Approximate p-value (MacKinnon)
        if adf_stat < -3.9:
            p_value = 0.01
        elif adf_stat < -3.34:
            p_value = 0.05
        elif adf_stat < -3.04:
            p_value = 0.10
        elif adf_stat < -2.57:
            p_value = 0.25
        else:
            p_value = 0.50

        return {
            "adf_statistic": float(adf_stat),
            "p_value": float(p_value),
            "gamma": float(gamma),
            "n_lags": max_lags,
        }


# ════════════════════════════════════════════════════════════════
# 9. VECM (Vector Error Correction Model)
# ════════════════════════════════════════════════════════════════


class VECMModel:
    """
    Vector Error Correction Model (VECM).

    If VAR variables are I(1) and cointegrated, VECM captures both
    short-run dynamics and long-run equilibrium adjustment.

    Mathematical basis:
        ΔYₜ = ΠYₜ₋₁ + Γ₁ΔYₜ₋₁ + ... + Γₖ₋₁ΔYₜ₋(ₖ₋₁) + εₜ

        where Π = αβ' is the error correction matrix
        α = adjustment speed (how fast return to equilibrium)
        β = cointegrating vectors (long-run relationships)
    """

    @staticmethod
    def fit(
        data: np.ndarray,
        cointegrating_rank: int = 1,
        max_lags: int = 3,
        variable_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fit VECM model.

        Args:
            data: T×k matrix
            cointegrating_rank: number of cointegrating relationships
            max_lags: lag order of underlying VAR
            variable_names: names for variables

        Returns:
            Dict with VECM parameters, adjustment speeds, cointegrating vectors
        """
        data = np.asarray(data, dtype=float)
        T, k = data.shape

        if variable_names is None:
            variable_names = [f"y{i+1}" for i in range(k)]

        # Differences
        dY = np.diff(data, axis=0)  # (T-1)×k

        # Lagged levels for error correction
        Y_lag = data[:-1]  # (T-1)×k

        # Build lagged differences
        p = max_lags
        n = T - p - 1

        # Dependent: ΔY from p+1 to T-1
        Y_dep = dY[p:]  # n×k

        # Regressors: Y_{t-1} (levels), ΔY_{t-1}, ..., ΔY_{t-p}
        X = np.column_stack([np.ones(n), Y_lag[p:]])  # constant + levels
        for lag in range(1, p + 1):
            X = np.column_stack([X, dY[p - lag:T - 1 - lag]])

        # OLS
        try:
            B = np.linalg.lstsq(X, Y_dep, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in VECM"}

        residuals = Y_dep - X @ B

        # Extract Π (error correction matrix)
        # B structure: [const | Π columns | Γ₁ columns | ... | Γₚ₋₁ columns]
        Pi = B[1:1+k, :]  # k×k

        # Johansen-style: decompose Π = αβ'
        U, S, Vt = np.linalg.svd(Pi)
        r = cointegrating_rank
        alpha = U[:, :r] * S[:r]  # k×r adjustment speeds
        beta = Vt[:r, :].T  # k×r cointegrating vectors

        # Adjustment speeds (α)
        adjustment = {variable_names[i]: float(alpha[i, 0]) for i in range(k)}

        # Cointegrating relationships
        coint_vectors = []
        for j in range(r):
            vec = {variable_names[i]: float(beta[i, j]) for i in range(k)}
            coint_vectors.append(vec)

        return {
            "method": f"VECM(rank={r}, lag={p})",
            "n_obs": n,
            "n_variables": k,
            "cointegrating_rank": r,
            "adjustment_speeds": adjustment,
            "cointegrating_vectors": coint_vectors,
            "error_correction_matrix": Pi.tolist(),
            "variable_names": variable_names,
            "note": "Negative adjustment speed indicates convergence to equilibrium",
        }


# ════════════════════════════════════════════════════════════════
# 10. Bootstrap Hypothesis Testing
# ════════════════════════════════════════════════════════════════


class BootstrapHypothesisTest:
    """
    Bootstrap-based hypothesis tests for regression coefficients.

    Useful when:
    - Sample size is small (CLT doesn't apply well)
    - Distribution of test statistic is unknown
    - Heteroskedasticity invalidates standard errors

    Methods:
    - Bootstrap-t: resample residuals, recompute t-statistic
    - Pairs bootstrap: resample (yᵢ, Xᵢ) pairs
    """

    @staticmethod
    def bootstrap_t_test(
        X: np.ndarray,
        y: np.ndarray,
        coef_index: int = 1,
        n_bootstrap: int = 2000,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Bootstrap-t test for regression coefficient.

        H₀: βⱼ = 0

        Args:
            X: design matrix (with constant)
            y: outcome vector
            coef_index: index of coefficient to test (0=const, 1=first slope)
            n_bootstrap: number of bootstrap replications
            seed: random seed

        Returns:
            Dict with bootstrap CI, p-value
        """
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        n = len(y)
        rng = np.random.RandomState(seed)

        # Original estimate
        beta_hat = np.linalg.lstsq(X, y, rcond=None)[0]
        residuals = y - X @ beta_hat
        sigma2 = np.sum(residuals ** 2) / (n - X.shape[1])
        se_orig = math.sqrt(sigma2 * np.linalg.inv(X.T @ X)[coef_index, coef_index])
        t_orig = beta_hat[coef_index] / se_orig if se_orig > 0 else 0

        # Bootstrap
        t_boot = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            # Resample residuals
            e_boot = rng.choice(residuals, size=n, replace=True)
            y_boot = X @ beta_hat + e_boot
            beta_boot = np.linalg.lstsq(X, y_boot, rcond=None)[0]
            resid_boot = y_boot - X @ beta_boot
            s2_boot = np.sum(resid_boot ** 2) / (n - X.shape[1])
            se_boot = math.sqrt(abs(s2_boot * np.linalg.inv(X.T @ X)[coef_index, coef_index]))
            t_boot[b] = (beta_boot[coef_index] - beta_hat[coef_index]) / se_boot if se_boot > 0 else 0

        # Bootstrap p-value: proportion of |t_boot| ≥ |t_orig|
        p_boot = np.mean(np.abs(t_boot) >= np.abs(t_orig))

        # Bootstrap CI for coefficient
        beta_boot_all = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            idx = rng.choice(n, size=n, replace=True)
            beta_boot_all[b] = np.linalg.lstsq(X[idx], y[idx], rcond=None)[0][coef_index]

        ci_lower = float(np.percentile(beta_boot_all, 2.5))
        ci_upper = float(np.percentile(beta_boot_all, 97.5))

        return {
            "test": "Bootstrap-t",
            "coefficient": float(beta_hat[coef_index]),
            "original_t": float(t_orig),
            "bootstrap_p_value": float(p_boot),
            "significant_at_05": p_boot < 0.05,
            "bootstrap_ci_95": {"lower": ci_lower, "upper": ci_upper},
            "n_bootstrap": n_bootstrap,
        }
