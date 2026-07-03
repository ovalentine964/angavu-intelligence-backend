"""
Causal Inference Engine — IV/2SLS, DiD, RDD (ECO 424 — Advanced Econometrics).

Theoretical Foundations:
- Angrist & Pischke (2009). *Mostly Harmless Econometrics*. Princeton.
- Angrist & Pischke (2014). *Mastering 'Metrics*. Princeton.
- Imbens & Lemieux (2008). "Regression Discontinuity Designs: A Guide to Practice."
  Journal of Econometrics, 142(2), 615–635.
- Lee & Lemieux (2010). "Regression Discontinuity Designs in Economics."
  Journal of Economic Literature, 48(2), 281–355.
- Wooldridge (2010). *Econometric Analysis of Cross Section and Panel Data*. MIT Press.
- Stock & Yogo (2005). "Testing for Weak Instruments in Linear IV Regression."
  In *Identification and Inference for Econometric Models*. Cambridge.

This module implements three core causal identification strategies used
throughout Angavu Intelligence to make credible causal claims:

1. **Instrumental Variables / 2SLS** — For endogenous regressors
2. **Difference-in-Differences** — For policy/treatment evaluation
3. **Regression Discontinuity** — For threshold-based treatment effects
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from scipy import stats
from scipy.optimize import minimize_scalar

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: OLS with robust (White / HC1) standard errors
# ---------------------------------------------------------------------------

def _ols(
    X: np.ndarray,
    y: np.ndarray,
    robust: bool = True,
    cluster: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    OLS regression returning coefficients, SEs, residuals, fitted values.

    Uses np.linalg.lstsq for numerically stable coefficient estimation
    (avoids explicit inversion of X'X which is ill-conditioned when
    columns are near-collinear). When *cluster* is provided, computes
    cluster-robust (CR1) standard errors. Otherwise, if *robust*, uses
    HC1 (White) standard errors.
    """
    n, k = X.shape
    # Flatten y to 1D if single-column
    if y.ndim > 1:
        y = y.ravel()
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    fitted = X @ beta
    mse = np.sum(resid ** 2) / (n - k)
    # Compute (X'X)^{-1} for standard error estimation only
    XtX_inv = np.linalg.inv(X.T @ X)

    if cluster is not None:
        # Cluster-robust (CR1) variance estimator
        # Var(β̂) = (X'X)⁻¹ (Σ_g X_g' ε_g ε_g' X_g) (X'X)⁻¹
        unique_clusters = np.unique(cluster)
        G = len(unique_clusters)
        meat = np.zeros((k, k))
        for g in unique_clusters:
            idx = cluster == g
            Xg = X[idx]
            eg = resid[idx]
            meat += (Xg.T @ eg) @ (eg.T @ Xg)
        # CR1 finite-sample correction: G/(G-1) * (n-1)/(n-k)
        correction = (G / (G - 1)) * ((n - 1) / (n - k)) if G > 1 else 1.0
        sandwich = XtX_inv @ (correction * meat) @ XtX_inv
        se = np.sqrt(np.diag(sandwich))
    elif robust:
        Omega = np.diag(resid ** 2)
        sandwich = XtX_inv @ (X.T @ Omega @ X) @ XtX_inv
        se = np.sqrt(np.diag(sandwich))
    else:
        se = np.sqrt(np.diag(mse * XtX_inv))

    t_stats = beta / se
    p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n - k))
    t_crit = stats.t.ppf(0.975, df=n - k)
    ci = np.column_stack([beta - t_crit * se, beta + t_crit * se])

    ss_tot = np.sum((y - np.mean(y)) ** 2)
    ss_res = np.sum(resid ** 2)
    r2 = 1 - ss_res / ss_tot
    r2_adj = 1 - (1 - r2) * (n - 1) / (n - k)

    return {
        "coefficients": beta,
        "standard_errors": se,
        "t_statistics": t_stats,
        "p_values": p_values,
        "confidence_intervals_95": ci,
        "r_squared": r2,
        "adj_r_squared": r2_adj,
        "residuals": resid,
        "fitted_values": fitted,
        "n": n,
        "k": k,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. Instrumental Variables / Two-Stage Least Squares (2SLS)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class TwoSLSResult:
    """Container for 2SLS estimation results."""
    first_stage_coefficients: np.ndarray
    first_stage_standard_errors: np.ndarray
    first_stage_f_statistic: float
    first_stage_r_squared: float
    second_stage_coefficients: np.ndarray
    second_stage_standard_errors: np.ndarray
    second_stage_t_statistics: np.ndarray
    second_stage_p_values: np.ndarray
    second_stage_confidence_intervals: np.ndarray
    second_stage_r_squared: float
    hausman_statistic: Optional[float] = None
    hausman_p_value: Optional[float] = None
    endogeneity_detected: Optional[bool] = None
    weak_instrument: bool = True
    n_observations: int = 0
    n_instruments: int = 0
    n_endogenous: int = 0

    def summary(self) -> Dict[str, Any]:
        return {
            "first_stage": {
                "f_statistic": round(self.first_stage_f_statistic, 4),
                "r_squared": round(self.first_stage_r_squared, 4),
                "weak_instrument": self.weak_instrument,
            },
            "second_stage": {
                "coefficients": self.second_stage_coefficients.tolist(),
                "standard_errors": self.second_stage_standard_errors.tolist(),
                "t_statistics": self.second_stage_t_statistics.tolist(),
                "p_values": self.second_stage_p_values.tolist(),
                "confidence_intervals_95": self.second_stage_confidence_intervals.tolist(),
                "r_squared": round(self.second_stage_r_squared, 4),
            },
            "hausman_test": {
                "statistic": round(self.hausman_statistic, 4) if self.hausman_statistic is not None else None,
                "p_value": round(self.hausman_p_value, 6) if self.hausman_p_value is not None else None,
                "endogeneity_detected": self.endogeneity_detected,
            },
            "diagnostics": {
                "n_observations": self.n_observations,
                "n_instruments": self.n_instruments,
                "n_endogenous": self.n_endogenous,
            },
        }


class InstrumentalVariables2SLS:
    """
    Two-Stage Least Squares estimation for endogenous regressors.

    **Problem**: When E[ε|X] ≠ 0, OLS is biased and inconsistent.
    This arises from omitted variables, measurement error, or simultaneity.

    **Solution**: Use an instrument Z that satisfies:
    1. Relevance:   Cov(Z, X) ≠ 0  (Z predicts X)
    2. Exclusion:   Cov(Z, ε) = 0   (Z affects Y only through X)

    **2SLS Estimator**:
      Stage 1:  X = Zπ + v        →  X̂ = Z(Z'Z)⁻¹Z'X = P_Z X
      Stage 2:  Y = X̂β + ε*       →  β̂_2SLS = (X̂'X̂)⁻¹X̂'Y

    **Weak Instrument Test** (Stock & Yogo, 2005):
      F-statistic from Stage 1. Rule of thumb: F > 10.

    **Hausman Test** (Hausman, 1978):
      H₀: OLS is consistent (no endogeneity).
      H₁: OLS is inconsistent → use 2SLS.
      Under H₀: H = (β̂_OLS − β̂_2SLS)' [Var(β̂_OLS) − Var(β̂_2SLS)]⁻¹ (β̂_OLS − β̂_2SLS) ~ χ²

    **Angavu Use Case**:
      Does credit access CAUSE income growth?
        Y = income_growth
        X = credit_access (endogenous — banks select on income)
        Z = distance_to_bank (instrument — affects access, not income directly)

    References:
        Angrist & Pischke (2009), Ch. 4.
        Wooldridge (2010), Ch. 5.
        Stock & Yogo (2005).
    """

    @staticmethod
    def fit(
        Y: np.ndarray,
        X_endogenous: np.ndarray,
        Z_instruments: np.ndarray,
        X_exogenous: Optional[np.ndarray] = None,
        robust: bool = True,
    ) -> TwoSLSResult:
        """
        Estimate 2SLS model.

        Args:
            Y: Outcome vector (n,)
            X_endogenous: Endogenous regressor(s) (n, k_endog)
            Z_instruments: External instruments (n, n_instr)
            X_exogenous: Exogenous controls (n, k_exog), optional
            robust: Use robust standard errors

        Returns:
            TwoSLSResult with all estimates and diagnostics
        """
        n = len(Y)
        if X_endogenous.ndim == 1:
            X_endogenous = X_endogenous.reshape(-1, 1)
        if Z_instruments.ndim == 1:
            Z_instruments = Z_instruments.reshape(-1, 1)

        k_endog = X_endogenous.shape[1]
        n_instr = Z_instruments.shape[1]

        # Build exogenous part
        if X_exogenous is not None:
            if X_exogenous.ndim == 1:
                X_exogenous = X_exogenous.reshape(-1, 1)
            W = np.column_stack([np.ones(n), X_exogenous])
        else:
            W = np.ones((n, 1))

        k_exog = W.shape[1]

        # ── Stage 1: Regress X_endogenous on [W, Z] ──
        S1_X = np.column_stack([W, Z_instruments])
        stage1_result = _ols(S1_X, X_endogenous, robust=robust)

        # Predicted values X̂
        X_hat = S1_X @ stage1_result["coefficients"] if X_endogenous.shape[1] == 1 else S1_X @ stage1_result["coefficients"]
        if X_hat.ndim == 1:
            X_hat = X_hat.reshape(-1, 1)

        # First-stage F-statistic (joint significance of instruments)
        # Restricted model: X on W only
        if W.shape[1] > 0:
            r1 = _ols(W, X_endogenous[:, 0], robust=False)
            ss_res_r = np.sum(r1["residuals"] ** 2)
        else:
            ss_res_r = np.sum((X_endogenous[:, 0] - np.mean(X_endogenous[:, 0])) ** 2)

        ss_res_u = np.sum((X_endogenous[:, 0] - S1_X @ stage1_result["coefficients"]) ** 2) if X_endogenous.shape[1] == 1 else np.sum((X_endogenous - S1_X @ stage1_result["coefficients"]) ** 2)
        df_diff = n_instr
        df_resid = n - S1_X.shape[1]

        if df_resid > 0 and ss_res_u > 0:
            first_stage_f = ((ss_res_r - ss_res_u) / df_diff) / (ss_res_u / df_resid)
        else:
            first_stage_f = 0.0

        # First-stage R²
        ss_tot = np.sum((X_endogenous[:, 0] - np.mean(X_endogenous[:, 0])) ** 2)
        first_stage_r2 = 1 - ss_res_u / ss_tot if ss_tot > 0 else 0.0

        weak_instrument = first_stage_f < 10.0  # Stock-Yogo rule of thumb

        # ── Stage 2: Regress Y on [W, X̂] ──
        S2_X = np.column_stack([W, X_hat])
        stage2_result = _ols(S2_X, Y, robust=robust)

        # ── Hausman Test ──
        # Compare OLS and 2SLS estimates of endogenous coefficients
        ols_X = np.column_stack([W, X_endogenous])
        ols_result = _ols(ols_X, Y, robust=False)

        # Extract endogenous coefficients only
        beta_ols_endog = ols_result["coefficients"][k_exog:k_exog + k_endog]
        beta_2sls_endog = stage2_result["coefficients"][k_exog:k_exog + k_endog]

        # Var-cov matrices for endogenous block
        mse_ols = np.sum(ols_result["residuals"] ** 2) / (n - ols_X.shape[1])
        V_ols = mse_ols * np.linalg.inv(ols_X.T @ ols_X)
        V_ols_endog = V_ols[k_exog:k_exog + k_endog, k_exog:k_exog + k_endog]

        mse_2sls = np.sum((Y - S2_X @ stage2_result["coefficients"]) ** 2) / (n - S2_X.shape[1])
        V_2sls = mse_2sls * np.linalg.inv(S2_X.T @ S2_X)
        V_2sls_endog = V_2sls[k_exog:k_exog + k_endog, k_exog:k_exog + k_endog]

        try:
            diff = beta_ols_endog - beta_2sls_endog
            V_diff = V_ols_endog - V_2sls_endog
            # Ensure positive-definite
            if np.all(np.linalg.eigvalsh(V_diff) > 0):
                hausman_stat = float(diff @ np.linalg.inv(V_diff) @ diff)
                hausman_p = 1 - stats.chi2.cdf(hausman_stat, df=k_endog)
                endogeneity = hausman_p < 0.05
            else:
                hausman_stat = None
                hausman_p = None
                endogeneity = None
        except Exception:
            hausman_stat = None
            hausman_p = None
            endogeneity = None

        return TwoSLSResult(
            first_stage_coefficients=stage1_result["coefficients"],
            first_stage_standard_errors=stage1_result["standard_errors"],
            first_stage_f_statistic=float(first_stage_f),
            first_stage_r_squared=float(first_stage_r2),
            second_stage_coefficients=stage2_result["coefficients"],
            second_stage_standard_errors=stage2_result["standard_errors"],
            second_stage_t_statistics=stage2_result["t_statistics"],
            second_stage_p_values=stage2_result["p_values"],
            second_stage_confidence_intervals=stage2_result["confidence_intervals_95"],
            second_stage_r_squared=float(stage2_result["r_squared"]),
            hausman_statistic=hausman_stat,
            hausman_p_value=hausman_p,
            endogeneity_detected=endogeneity,
            weak_instrument=weak_instrument,
            n_observations=n,
            n_instruments=n_instr,
            n_endogenous=k_endog,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Difference-in-Differences (DiD)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DiDResult:
    """Container for Difference-in-Differences estimation results."""
    coefficients: np.ndarray
    standard_errors: np.ndarray
    t_statistics: np.ndarray
    p_values: np.ndarray
    confidence_intervals: np.ndarray
    r_squared: float
    ate: float  # Average Treatment Effect (β₃)
    ate_se: float
    ate_ci: Tuple[float, float]
    parallel_trends_f_stat: Optional[float] = None
    parallel_trends_p_value: Optional[float] = None
    parallel_trends_satisfied: Optional[bool] = None
    n_treated: int = 0
    n_control: int = 0
    n_periods: int = 0

    def summary(self) -> Dict[str, Any]:
        return {
            "treatment_effect": {
                "ate": round(self.ate, 6),
                "standard_error": round(self.ate_se, 6),
                "t_statistic": round(float(self.ate / self.ate_se), 4) if self.ate_se > 0 else None,
                "p_value": round(float(2 * (1 - stats.t.cdf(abs(self.ate / self.ate_se), df=self.n_treated + self.n_control - 4))), 6) if self.ate_se > 0 else None,
                "confidence_interval_95": [round(self.ate_ci[0], 6), round(self.ate_ci[1], 6)],
            },
            "model": {
                "coefficients": self.coefficients.tolist(),
                "standard_errors": self.standard_errors.tolist(),
                "r_squared": round(self.r_squared, 4),
            },
            "parallel_trends_test": {
                "f_statistic": round(self.parallel_trends_f_stat, 4) if self.parallel_trends_f_stat is not None else None,
                "p_value": round(self.parallel_trends_p_value, 6) if self.parallel_trends_p_value is not None else None,
                "assumption_satisfied": self.parallel_trends_satisfied,
            },
            "sample": {
                "n_treated": self.n_treated,
                "n_control": self.n_control,
                "n_periods": self.n_periods,
            },
        }


class DifferenceInDifferences:
    """
    Difference-in-Differences estimation for policy evaluation.

    **Classic 2×2 DiD** (Angrist & Pischke, 2009, Ch. 5):

        Y_it = β₀ + β₁·Treat_i + β₂·Post_t + β₃·(Treat_i × Post_t) + ε_it

    Where:
        β₁ = group fixed effect (treated vs control baseline difference)
        β₂ = time fixed effect (pre vs post common shock)
        β₃ = **causal treatment effect** (the DiD estimator)

    **Key Assumption — Parallel Trends**:
        E[Y₀ᵢₜ | Treat=1] − E[Y₀ᵢₜ | Treat=0] = constant for all t
        Without treatment, treated and control would have followed
        the same trend. Testable in pre-treatment periods.

    **Clustered Standard Errors** (Bertrand, Duflo & Mullainathan, 2004):
        Must cluster at the unit level to avoid severe size distortion.
        Inference is invalid without clustering when treatment varies
        at a group level.

    **Angavu Use Case**:
        Did the Msaidizi credit rollout CAUSE business growth?
          Y = business_revenue
          Treat = 1 if market received Msaidizi (treatment group)
          Post = 1 if period after rollout
          β₃ = causal effect of Msaidizi on revenue

    References:
        Angrist & Pischke (2009), Ch. 5.
        Bertrand, Duflo & Mullainathan (2004). QJE.
        Cunningham (2021). *Causal Inference: The Mixtape*. Yale.
    """

    @staticmethod
    def fit(
        Y: np.ndarray,
        treat: np.ndarray,
        post: np.ndarray,
        cluster: Optional[np.ndarray] = None,
        controls: Optional[np.ndarray] = None,
        check_parallel_trends: bool = True,
        pre_treat_interaction: Optional[np.ndarray] = None,
    ) -> DiDResult:
        """
        Estimate DiD model.

        Args:
            Y: Outcome vector (n,)
            post: Post-treatment indicator (n,)
            treat: Treatment group indicator (n,)
            cluster: Cluster variable for clustered SEs (n,)
            controls: Additional controls (n, k)
            check_parallel_trends: Test parallel trends assumption
            pre_treat_interaction: Pre-period × treat for parallel trends test

        Returns:
            DiDResult with treatment effect and diagnostics
        """
        n = len(Y)
        did_interaction = treat * post

        # Design matrix: [1, treat, post, treat×post, controls...]
        X_list = [np.ones(n), treat, post, did_interaction]
        if controls is not None:
            if controls.ndim == 1:
                controls = controls.reshape(-1, 1)
            X_list.append(controls)
        X = np.column_stack(X_list)

        # OLS with clustered SEs
        result = _ols(X, Y, robust=True, cluster=cluster)

        # ATE is the coefficient on treat×post (index 3)
        ate = float(result["coefficients"][3])
        ate_se = float(result["standard_errors"][3])
        ate_ci = (
            float(result["confidence_intervals_95"][3, 0]),
            float(result["confidence_intervals_95"][3, 1]),
        )

        # Parallel trends test: interact treat with pre-period indicators
        pt_f = None
        pt_p = None
        pt_satisfied = None

        if check_parallel_trends and pre_treat_interaction is not None:
            # Pre-treat interaction: columns are treat × pre_period_dummies
            if pre_treat_interaction.ndim == 1:
                pre_treat_interaction = pre_treat_interaction.reshape(-1, 1)

            X_pt = np.column_stack([X, pre_treat_interaction])
            try:
                result_pt = _ols(X_pt, Y, robust=True, cluster=cluster)

                # F-test: joint significance of pre-treat interactions
                k_pre = pre_treat_interaction.shape[1]
                n_params = X_pt.shape[1]

                # Use F-test from restricted vs unrestricted R²
                r2_u = result_pt["r_squared"]
                r2_r = result["r_squared"]
                df1 = k_pre
                df2 = n - n_params
                if df2 > 0 and (1 - r2_u) > 0:
                    pt_f = ((r2_u - r2_r) / df1) / ((1 - r2_u) / df2)
                    pt_p = 1 - stats.f.cdf(pt_f, df1, df2)
                    pt_satisfied = pt_p > 0.05  # Fail to reject = parallel trends OK
            except np.linalg.LinAlgError:
                logger.warning("Parallel trends test: singular matrix, skipping")

        n_treated = int(np.sum(treat == 1))
        n_control = int(np.sum(treat == 0))

        return DiDResult(
            coefficients=result["coefficients"],
            standard_errors=result["standard_errors"],
            t_statistics=result["t_statistics"],
            p_values=result["p_values"],
            confidence_intervals=result["confidence_intervals_95"],
            r_squared=float(result["r_squared"]),
            ate=ate,
            ate_se=ate_se,
            ate_ci=ate_ci,
            parallel_trends_f_stat=pt_f,
            parallel_trends_p_value=pt_p,
            parallel_trends_satisfied=pt_satisfied,
            n_treated=n_treated,
            n_control=n_control,
            n_periods=len(np.unique(post)),
        )

    @staticmethod
    def event_study(
        Y: np.ndarray,
        treat: np.ndarray,
        time_period: np.ndarray,
        treatment_time: int,
        cluster: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Event study design — dynamic treatment effects over time.

        Estimates period-by-period treatment effects relative to
        the treatment date, allowing visual inspection of:
        1. Pre-trends (should be zero under parallel trends)
        2. Dynamic treatment effects post-intervention

        Model:
            Y_it = α_i + γ_t + Σ_k δ_k · (Treat_i × 1[t=k]) + ε_it

        where k ranges over time periods, and δ_k is normalized to 0
        at k = treatment_time − 1 (base period).

        Args:
            Y: Outcome vector
            treat: Treatment group indicator
            time_period: Time period variable
            treatment_time: Period when treatment begins
            cluster: Cluster variable

        Returns:
            Dict with period-specific coefficients and pre-trend test
        """
        n = len(Y)
        periods = np.sort(np.unique(time_period))
        base_period = treatment_time - 1

        # Create period dummies and interact with treat
        period_effects = {}
        X_list = [np.ones(n), treat]

        for t in periods:
            if t == base_period:
                continue  # Omitted base period
            dummy = (time_period == t).astype(float)
            X_list.append(dummy)  # Time FE
            X_list.append(treat * dummy)  # Event study interaction
            period_effects[t] = len(X_list) - 1  # Index of interaction coeff

        X = np.column_stack(X_list)
        result = _ols(X, Y, robust=True, cluster=cluster)

        # Extract event study coefficients
        event_coefs = {}
        event_ses = {}
        for t, idx in period_effects.items():
            event_coefs[int(t)] = round(float(result["coefficients"][idx]), 6)
            event_ses[int(t)] = round(float(result["standard_errors"][idx]), 6)

        # Pre-trend test: joint significance of pre-treatment interactions
        pre_periods = [t for t in periods if t < treatment_time and t != base_period]
        if pre_periods:
            pre_indices = [period_effects[t] for t in pre_periods]
            # Simplified: use absolute values — if all pre-period CIs include 0, trends OK
            pre_coefs = np.array([result["coefficients"][i] for i in pre_indices])
            pre_ses = np.array([result["standard_errors"][i] for i in pre_indices])
            pre_t = pre_coefs / pre_ses
            # Joint F via Wald
            k_pre = len(pre_indices)
            if k_pre > 0:
                V = np.zeros((k_pre, k_pre))
                for i_idx, i in enumerate(pre_indices):
                    for j_idx, j in enumerate(pre_indices):
                        # Approximate from the full VCV
                        V[i_idx, j_idx] = result["standard_errors"][i] * result["standard_errors"][j] * (1.0 if i == j else 0.0)
                try:
                    wald = pre_coefs @ np.linalg.solve(V, pre_coefs)
                    pre_f_p = 1 - stats.chi2.cdf(wald, df=k_pre)
                except Exception:
                    pre_f_p = None
        else:
            pre_f_p = None

        return {
            "event_coefficients": event_coefs,
            "event_standard_errors": event_ses,
            "base_period": int(base_period),
            "pre_trend_p_value": round(pre_f_p, 4) if pre_f_p is not None else None,
            "parallel_trends_ok": pre_f_p > 0.05 if pre_f_p is not None else None,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. Regression Discontinuity Design (RDD)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RDDResult:
    """Container for RDD estimation results."""
    treatment_effect: float
    treatment_effect_se: float
    treatment_effect_ci: Tuple[float, float]
    t_statistic: float
    p_value: float
    bandwidth: float
    n_left: int
    n_right: int
    n_total: int
    r_squared: float
    coefficients: np.ndarray
    standard_errors: np.ndarray
    mccrary_p_value: Optional[float] = None
    mccrary_manipulation_detected: Optional[bool] = None
    optimal_bandwidth: Optional[float] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "treatment_effect": {
                "estimate": round(self.treatment_effect, 6),
                "standard_error": round(self.treatment_effect_se, 6),
                "t_statistic": round(self.t_statistic, 4),
                "p_value": round(self.p_value, 6),
                "confidence_interval_95": [round(self.treatment_effect_ci[0], 6), round(self.treatment_effect_ci[1], 6)],
            },
            "estimation": {
                "bandwidth": round(self.bandwidth, 4),
                "optimal_bandwidth": round(self.optimal_bandwidth, 4) if self.optimal_bandwidth else None,
                "n_left": self.n_left,
                "n_right": self.n_right,
                "n_total": self.n_total,
                "r_squared": round(self.r_squared, 4),
            },
            "mccrary_test": {
                "p_value": round(self.mccrary_p_value, 4) if self.mccrary_p_value is not None else None,
                "manipulation_detected": self.mccrary_manipulation_detected,
            },
        }


class RegressionDiscontinuity:
    """
    Regression Discontinuity Design for threshold-based causal inference.

    **Sharp RDD** (Imbens & Lemieux, 2008; Lee & Lemieux, 2010):

    When treatment D is a deterministic function of a running variable X:
        D_i = 1[X_i ≥ c]

    The causal effect at the cutoff c is:
        τ = lim_{x↓c} E[Y|X=x] − lim_{x↑c} E[Y|X=x]

    **Local Linear Regression** at the cutoff:
        Y_i = α + τ·D_i + β₁·(X_i − c) + β₂·D_i·(X_i − c) + ε_i

    estimated on observations within bandwidth h of the cutoff.

    **Bandwidth Selection** (Imbens & Kalyanaraman, 2012):
        Optimal bandwidth minimizes asymptotic MSE. The IK bandwidth
        balances bias (wider → more bias from misspecification) and
        variance (wider → more precision).

    **McCrary Density Test** (McCrary, 2008):
        Tests for manipulation of the running variable at the cutoff.
        If agents can precisely manipulate X around c, the design is
        invalid. Estimates density on each side and tests for a jump.

    **Angavu Use Case**:
        Do businesses just above the Alama Score credit threshold benefit?
          Y = business_revenue_growth
          X = Alama_score (running variable)
          c = credit_approval_threshold
          τ = causal effect of credit access at the margin

    References:
        Imbens & Lemieux (2008). Journal of Econometrics, 142(2).
        Lee & Lemieux (2010). JEL, 48(2).
        Imbens & Kalyanaraman (2012). REStud, 79(3).
        McCrary (2008). Journal of Econometrics, 142(2).
        Cattaneo, Idrobo & Titiunik (2020). *A Practical Guide to RDD*. Cambridge.
    """

    @staticmethod
    def _ik_bandwidth(X: np.ndarray, cutoff: float) -> float:
        """
        Imbens-Kalyanaraman optimal bandwidth.

        Implements a simplified version of the IK (2012) plug-in
        bandwidth selector for local linear regression RDD.

        h_IK = C · (σ² / (f(c) · [μ₂² − μ₁²]²))^{1/5} · n^{−1/5}

        where:
            f(c) = density at cutoff (estimated via histogram)
            σ²   = conditional variance near cutoff
            μ_j  = j-th moment of X near cutoff
            C    = constant depending on kernel

        Simplified implementation using Silverman rule-of-thumb as
        initial pilot bandwidth, then plug-in refinement.
        """
        n = len(X)
        X_centered = X - cutoff

        # Pilot bandwidth (Silverman)
        h_pilot = 1.06 * np.std(X_centered) * n ** (-1 / 5)

        # Estimate density at cutoff using Gaussian kernel
        kernel_vals = stats.norm.pdf(X_centered / h_pilot) / h_pilot
        f_c = np.mean(kernel_vals)

        # Conditional variance near cutoff
        in_band = np.abs(X_centered) <= h_pilot
        if np.sum(in_band) < 5:
            in_band = np.abs(X_centered) <= 2 * h_pilot
        sigma2 = np.var(X_centered[in_band]) if np.sum(in_band) > 1 else np.var(X_centered)

        # Optimal bandwidth (simplified IK formula)
        # C ≈ 3.4375 for triangular kernel (IK 2012, Table 1)
        C = 3.4375
        if f_c > 0:
            h_opt = C * (sigma2 / (f_c * n)) ** 0.2
        else:
            h_opt = h_pilot

        # Clamp to reasonable range
        x_range = np.max(np.abs(X_centered))
        h_opt = max(h_opt, x_range * 0.01)
        h_opt = min(h_opt, x_range * 0.5)

        return float(h_opt)

    @staticmethod
    def _mccrary_test(X: np.ndarray, cutoff: float, bin_width: Optional[float] = None) -> Tuple[float, bool]:
        """
        McCrary (2008) density test for manipulation at the cutoff.

        Bins observations on each side of the cutoff, estimates
        log density, and tests for a discontinuity using local
        linear regression on the binned data.

        H₀: Density is continuous at cutoff (no manipulation)
        H₁: Density jumps at cutoff (manipulation)

        Returns:
            (p_value, manipulation_detected)
        """
        n = len(X)
        X_centered = X - cutoff

        # Bin width via Silverman rule
        if bin_width is None:
            bin_width = 2 * np.std(X_centered) * n ** (-1 / 3)

        # Create bins on each side
        max_dist = np.max(np.abs(X_centered))
        n_bins = int(np.ceil(max_dist / bin_width))

        left_bins = []
        right_bins = []
        for i in range(n_bins):
            lo = -(i + 1) * bin_width
            hi = -i * bin_width
            count = np.sum((X_centered >= lo) & (X_centered < hi))
            mid = (lo + hi) / 2
            left_bins.append((mid, max(count, 1)))

            lo_r = i * bin_width
            hi_r = (i + 1) * bin_width
            count_r = np.sum((X_centered >= lo_r) & (X_centered < hi_r))
            mid_r = (lo_r + hi_r) / 2
            right_bins.append((mid_r, max(count_r, 1)))

        left_bins.sort(key=lambda x: x[0])
        right_bins.sort(key=lambda x: x[0])

        # Log density: ln(count / (n * bin_width))
        def log_density(bins):
            mids = np.array([b[0] for b in bins])
            counts = np.array([b[1] for b in bins])
            ld = np.log(counts / (n * bin_width))
            return mids, ld

        mids_l, ld_l = log_density(left_bins)
        mids_r, ld_r = log_density(right_bins)

        # Local linear regression on each side near cutoff
        # Use only bins within 2*bandwidth of cutoff
        h_mc = 2 * bin_width * len(left_bins) ** 0.2

        mask_l = np.abs(mids_l) <= h_mc
        mask_r = mids_r <= h_mc

        if np.sum(mask_l) < 3 or np.sum(mask_r) < 3:
            return 0.5, False  # Not enough data

        # Extrapolate to cutoff from each side
        def local_linear(mids, ld, side):
            # Triangular kernel
            if side == "left":
                dist = np.abs(mids)
            else:
                dist = mids

            weights = np.maximum(1 - dist / h_mc, 0)
            X_design = np.column_stack([np.ones(len(mids)), mids])
            W = np.diag(weights)
            try:
                beta = np.linalg.solve(X_design.T @ W @ X_design, X_design.T @ W @ ld)
                limit = beta[0]  # Value at cutoff
            except np.linalg.LinAlgError:
                limit = np.mean(ld)
            return limit

        limit_left = local_linear(mids_l[mask_l], ld_l[mask_l], "left")
        limit_right = local_linear(mids_r[mask_r], ld_r[mask_r], "right")

        # Test statistic: difference in log density
        theta = limit_right - limit_left

        # Standard error (simplified)
        se_theta = np.sqrt(2 / (n * bin_width * stats.norm.pdf(0)))
        if se_theta > 0:
            z = theta / se_theta
            p_value = 2 * (1 - stats.norm.cdf(abs(z)))
        else:
            p_value = 1.0

        return float(p_value), bool(p_value < 0.05)

    @classmethod
    def fit(
        cls,
        Y: np.ndarray,
        X: np.ndarray,
        cutoff: float,
        bandwidth: Optional[float] = None,
        kernel: str = "triangular",
        optimal_bw: bool = True,
        run_mccrary: bool = True,
    ) -> RDDResult:
        """
        Estimate sharp RDD using local linear regression.

        Model within bandwidth h of cutoff c:
            Y_i = α + τ·D_i + β₁·(X_i − c) + β₂·D_i·(X_i − c) + ε_i

        where D_i = 1[X_i ≥ c] and τ is the treatment effect.

        Args:
            Y: Outcome vector (n,)
            X: Running variable (n,)
            cutoff: Threshold value c
            bandwidth: Fixed bandwidth h (if None, uses IK optimal)
            kernel: Kernel weighting ("triangular", "uniform", "epanechnikov")
            optimal_bw: Compute IK optimal bandwidth
            run_mccrary: Run McCrary density test

        Returns:
            RDDResult with treatment effect and diagnostics
        """
        n = len(Y)
        X_centered = X - cutoff
        D = (X >= cutoff).astype(float)

        # Optimal bandwidth
        opt_bw = cls._ik_bandwidth(X, cutoff) if optimal_bw else None
        h = bandwidth if bandwidth is not None else opt_bw
        if h is None:
            h = cls._ik_bandwidth(X, cutoff)

        # Subset to observations within bandwidth
        in_bw = np.abs(X_centered) <= h
        Y_h = Y[in_bw]
        X_h = X_centered[in_bw]
        D_h = D[in_bw]
        n_h = len(Y_h)

        if n_h < 10:
            raise ValueError(
                f"Too few observations ({n_h}) within bandwidth {h:.4f}. "
                "Increase bandwidth or check data near cutoff."
            )

        # Kernel weights
        u = np.abs(X_h) / h
        if kernel == "triangular":
            w = np.maximum(1 - u, 0)
        elif kernel == "epanechnikov":
            w = np.maximum(0.75 * (1 - u ** 2), 0)
        else:  # uniform
            w = np.ones_like(u)

        # Design matrix: [1, D, X-c, D*(X-c)]
        X_design = np.column_stack([np.ones(n_h), D_h, X_h, D_h * X_h])

        # Weighted least squares
        W = np.diag(w)
        try:
            XtWX_inv = np.linalg.inv(X_design.T @ W @ X_design)
            beta = XtWX_inv @ (X_design.T @ W @ Y_h)
        except np.linalg.LinAlgError:
            raise ValueError("Singular design matrix — check bandwidth and data.")

        # Residuals and variance
        resid = Y_h - X_design @ beta
        sigma2 = np.sum(w * resid ** 2) / (n_h - 4)

        # Robust (HC1) variance for WLS
        W_half = np.diag(np.sqrt(w))
        X_w = W_half @ X_design
        Y_w = W_half @ Y_h
        resid_w = Y_w - X_w @ beta
        Omega = np.diag(resid_w ** 2)
        try:
            V_robust = XtWX_inv @ (X_design.T @ Omega @ X_design) @ XtWX_inv
            se = np.sqrt(np.diag(V_robust))
        except Exception:
            se = np.sqrt(np.diag(sigma2 * XtWX_inv))

        # Treatment effect is β[1] (coefficient on D)
        tau = float(beta[1])
        tau_se = float(se[1])
        t_stat = tau / tau_se if tau_se > 0 else 0.0
        p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=n_h - 4))
        t_crit = stats.t.ppf(0.975, df=n_h - 4)
        tau_ci = (tau - t_crit * tau_se, tau + t_crit * tau_se)

        # R²
        ss_tot = np.sum(w * (Y_h - np.average(Y_h, weights=w)) ** 2)
        ss_res = np.sum(w * resid ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        n_left = int(np.sum((X < cutoff) & in_bw))
        n_right = int(np.sum((X >= cutoff) & in_bw))

        # McCrary test
        mc_p, mc_manip = (None, None)
        if run_mccrary:
            try:
                mc_p, mc_manip = cls._mccrary_test(X, cutoff)
            except Exception:
                logger.warning("McCrary test failed", exc_info=True)

        return RDDResult(
            treatment_effect=tau,
            treatment_effect_se=tau_se,
            treatment_effect_ci=tau_ci,
            t_statistic=float(t_stat),
            p_value=float(p_val),
            bandwidth=float(h),
            n_left=n_left,
            n_right=n_right,
            n_total=n_h,
            r_squared=float(r2),
            coefficients=beta,
            standard_errors=se,
            mccrary_p_value=mc_p,
            mccrary_manipulation_detected=mc_manip,
            optimal_bandwidth=opt_bw,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Convenience singletons
# ═══════════════════════════════════════════════════════════════════════════

iv_2sls = InstrumentalVariables2SLS()
did = DifferenceInDifferences()
rdd = RegressionDiscontinuity()
