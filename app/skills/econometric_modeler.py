"""
Econometric Modeler — ECO 424: Econometrics (Advanced)

Maps ECO 424 (Advanced Econometrics) course unit into executable
causal inference and regression modeling capabilities.

Capabilities:
- OLS regression with robust standard errors
- Instrumental variables / 2SLS for endogeneity
- Panel data models (fixed effects, random effects)
- Time series models (ARIMA, VAR)
- Cointegration testing and ECM
- Heckman selection correction

Theoretical Foundations:
- Gauss-Markov theorem (OLS is BLUE)
- Instrumental variables (exclusion restriction, relevance)
- Hausman test (FE vs RE)
- Engle-Granger cointegration
- Johansen procedure

Wired into: IntelligenceGenerator, AnalysisAgent
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from scipy import stats

from app.skills.base import BaseSkill, SkillResult

logger = structlog.get_logger(__name__)


class EconometricModeler(BaseSkill):
    """
    ECO 424 — Advanced Econometrics

    Provides causal inference, regression modeling, and econometric
    analysis for Angavu Intelligence intelligence products.
    """

    def __init__(self):
        super().__init__(
            name="econometric_modeler",
            course_unit="ECO 424 — Econometrics",
            description=(
                "OLS, IV, 2SLS regression, panel data models, "
                "and time series models (ARIMA, VAR) for causal inference."
            ),
            version="1.0.0",
            agent_bindings=["IntelligenceGenerator"],
        )

    async def execute(self, action: str, **kwargs) -> SkillResult:
        actions = {
            "ols_regression": self._ols_regression,
            "iv_regression": self._iv_regression,
            "panel_fixed_effects": self._panel_fixed_effects,
            "panel_random_effects": self._panel_random_effects,
            "hausman_test": self._hausman_test,
            "arima_model": self._arima_model,
            "var_model": self._var_model,
            "cointegration_test": self._cointegration_test,
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
                confidence=data.get("_confidence", 0.85),
            )
        except Exception as exc:
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=str(exc),
            )

    async def _ols_regression(
        self,
        X: List[List[float]],
        y: List[float],
        robust: bool = True,
        variable_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        OLS regression with optional robust (White) standard errors.

        Model: Y = Xβ + ε
        Estimator: β̂ = (X'X)⁻¹X'Y

        Args:
            X: Design matrix (list of lists)
            y: Dependent variable
            robust: Use White robust SEs
            variable_names: Names for regressors

        Returns:
            Dict with coefficients, SEs, R², diagnostics
        """
        X_arr = np.column_stack([np.ones(len(y)), np.array(X, dtype=float)])
        y_arr = np.array(y, dtype=float)
        n, k = X_arr.shape

        # β̂ = (X'X)⁻¹X'Y
        try:
            XtX_inv = np.linalg.inv(X_arr.T @ X_arr)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix — perfect multicollinearity"}

        beta = XtX_inv @ (X_arr.T @ y_arr)
        residuals = y_arr - X_arr @ beta
        mse = np.sum(residuals ** 2) / (n - k)

        if robust:
            Omega = np.diag(residuals ** 2)
            sandwich = XtX_inv @ (X_arr.T @ Omega @ X_arr) @ XtX_inv
            se = np.sqrt(np.diag(sandwich))
        else:
            se = np.sqrt(np.diag(mse * XtX_inv))

        t_stats = beta / se
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n - k))

        ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
        ss_res = np.sum(residuals ** 2)
        r2 = 1 - ss_res / ss_tot
        adj_r2 = 1 - (1 - r2) * (n - 1) / (n - k)

        # F-test
        ss_reg = np.sum((X_arr @ beta - np.mean(y_arr)) ** 2)
        f_stat = (ss_reg / (k - 1)) / (ss_res / (n - k)) if k > 1 else None
        f_p = 1 - stats.f.cdf(f_stat, k - 1, n - k) if f_stat else None

        # Confidence intervals
        t_crit = stats.t.ppf(0.975, df=n - k)

        if variable_names is None:
            variable_names = ["const"] + [f"x{i+1}" for i in range(k - 1)]

        coefficients = []
        for i in range(k):
            coefficients.append({
                "name": variable_names[i] if i < len(variable_names) else f"beta_{i}",
                "estimate": round(float(beta[i]), 6),
                "std_error": round(float(se[i]), 6),
                "t_statistic": round(float(t_stats[i]), 4),
                "p_value": round(float(p_values[i]), 6),
                "ci_lower": round(float(beta[i] - t_crit * se[i]), 6),
                "ci_upper": round(float(beta[i] + t_crit * se[i]), 6),
                "significant": bool(p_values[i] < 0.05),
            })

        return {
            "coefficients": coefficients,
            "r_squared": round(float(r2), 4),
            "adj_r_squared": round(float(adj_r2), 4),
            "f_statistic": round(float(f_stat), 4) if f_stat else None,
            "f_p_value": round(float(f_p), 6) if f_p else None,
            "residual_std_error": round(float(np.sqrt(mse)), 4),
            "n_observations": n,
            "n_parameters": k,
            "robust_se": robust,
            "_confidence": 0.9,
        }

    async def _iv_regression(
        self,
        X: List[List[float]],
        y: List[float],
        Z: List[List[float]],
        endogenous_indices: List[int],
        variable_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Two-Stage Least Squares (2SLS) instrumental variable regression.

        For endogenous regressors X₂ with instruments Z:
        Stage 1: X₂ = Zγ + v  (first stage)
        Stage 2: Y = X₁β₁ + X̂₂β₂ + ε  (second stage)

        Args:
            X: Exogenous + endogenous regressors
            y: Dependent variable
            Z: Instruments (must include all exogenous regressors)
            endogenous_indices: Which columns of X are endogenous
            variable_names: Names for regressors

        Returns:
            Dict with 2SLS coefficients, first-stage F-stat, diagnostics
        """
        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=float)
        Z_arr = np.array(Z, dtype=float)
        n = len(y_arr)

        # Add constant
        X_full = np.column_stack([np.ones(n), X_arr])
        Z_full = np.column_stack([np.ones(n), Z_arr])
        k = X_full.shape[1]

        # Stage 1: Regress each endogenous variable on instruments
        # X̂ = Z(Z'Z)⁻¹Z'X = P_Z X
        try:
            ZtZ_inv = np.linalg.inv(Z_full.T @ Z_full)
        except np.linalg.LinAlgError:
            return {"error": "Singular instrument matrix"}

        P_Z = Z_full @ ZtZ_inv @ Z_full.T  # Projection matrix
        X_hat = P_Z @ X_full

        # Stage 2: OLS of Y on X̂
        try:
            XtX_inv = np.linalg.inv(X_hat.T @ X_hat)
        except np.linalg.LinAlgError:
            return {"error": "Singular fitted regressor matrix"}

        beta_2sls = XtX_inv @ (X_hat.T @ y_arr)
        residuals = y_arr - X_full @ beta_2sls

        # Robust SEs for 2Slass
        Omega = np.diag(residuals ** 2)
        try:
            bread = np.linalg.inv(X_full.T @ Z_full @ ZtZ_inv @ Z_full.T @ X_full)
        except np.linalg.LinAlgError:
            bread = XtX_inv
        sandwich = bread @ (X_full.T @ Z_full @ ZtZ_inv @ Z_full.T @ Omega @ Z_full @ ZtZ_inv @ Z_full.T @ X_full) @ bread
        se = np.sqrt(np.diag(sandwich))

        t_stats = beta_2sls / np.maximum(se, 1e-10)
        p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n - k))

        # First-stage F-stat (for weak instruments test)
        first_stage_F = None
        for idx in endogenous_indices:
            x_endog = X_full[:, idx + 1]  # +1 for constant
            try:
                beta_fs = ZtZ_inv @ (Z_full.T @ x_endog)
                resid_fs = x_endog - Z_full @ beta_fs
                ss_res_fs = np.sum(resid_fs ** 2)
                ss_tot_fs = np.sum((x_endog - np.mean(x_endog)) ** 2)
                r2_fs = 1 - ss_res_fs / max(ss_tot_fs, 1e-10)
                n_instruments = Z_full.shape[1]
                first_stage_F = float((r2_fs / n_instruments) / ((1 - r2_fs) / max(n - n_instruments - 1, 1)))
            except Exception:
                first_stage_F = None

        if variable_names is None:
            variable_names = ["const"] + [f"x{i+1}" for i in range(k - 1)]

        coefficients = []
        for i in range(k):
            coefficients.append({
                "name": variable_names[i] if i < len(variable_names) else f"beta_{i}",
                "estimate": round(float(beta_2sls[i]), 6),
                "std_error": round(float(se[i]), 6),
                "t_statistic": round(float(t_stats[i]), 4),
                "p_value": round(float(p_values[i]), 6),
            })

        weak_instruments = first_stage_F is not None and first_stage_F < 10

        return {
            "method": "2SLS",
            "coefficients": coefficients,
            "n_observations": n,
            "first_stage_F": round(first_stage_F, 4) if first_stage_F else None,
            "weak_instruments_warning": weak_instruments,
            "endogenous_variables": [variable_names[i + 1] for i in endogenous_indices if i + 1 < len(variable_names)],
            "_confidence": 0.8,
        }

    async def _panel_fixed_effects(
        self,
        X: List[List[float]],
        y: List[float],
        groups: List[int],
        variable_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Panel data fixed effects estimator.

        Within-group transformation: ỹ_it = y_it - ȳ_i
        Removes time-invariant unobserved heterogeneity.

        Args:
            X: Regressors
            y: Dependent variable
            groups: Group/individual identifiers
            variable_names: Variable names

        Returns:
            Dict with FE coefficients, within R², diagnostics
        """
        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=float)
        groups_arr = np.array(groups)
        n = len(y_arr)

        unique_groups = np.unique(groups_arr)
        n_groups = len(unique_groups)

        # Within-group demeaning
        y_within = y_arr.copy()
        X_within = X_arr.copy()

        for g in unique_groups:
            mask = groups_arr == g
            y_within[mask] -= np.mean(y_arr[mask])
            for j in range(X_arr.shape[1]):
                X_within[mask, j] -= np.mean(X_arr[mask, j])

        # OLS on demeaned data
        result = await self._ols_regression(
            X_within.tolist(),
            y_within.tolist(),
            robust=True,
            variable_names=variable_names,
        )

        if "error" in result:
            return result

        result["method"] = "Fixed Effects (Within)"
        result["n_groups"] = n_groups
        result["group_dummies_removed"] = n_groups
        result["df_adjusted"] = n - n_groups - X_arr.shape[1]
        result["_confidence"] = 0.85
        return result

    async def _panel_random_effects(
        self,
        X: List[List[float]],
        y: List[float],
        groups: List[int],
        variable_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Panel data random effects estimator (GLS).

        Assumes individual effects are uncorrelated with regressors.
        More efficient than FE if assumption holds.

        Args:
            X: Regressors
            y: Dependent variable
            groups: Group identifiers
            variable_names: Variable names

        Returns:
            Dict with RE coefficients, diagnostics
        """
        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=float)
        groups_arr = np.array(groups)
        n = len(y_arr)

        unique_groups = np.unique(groups_arr)
        n_groups = len(unique_groups)
        n_per_group = n / n_groups

        # Estimate variance components
        # Step 1: Pooled OLS
        pooled_result = await self._ols_regression(
            X_arr.tolist(), y_arr.tolist(), robust=False, variable_names=variable_names,
        )
        if "error" in pooled_result:
            return pooled_result

        beta_pooled = np.array([c["estimate"] for c in pooled_result["coefficients"]])
        residuals = y_arr - np.column_stack([np.ones(n), X_arr]) @ beta_pooled

        # Step 2: Estimate σ²_u (between-group variance)
        group_means = np.zeros(n)
        for g in unique_groups:
            mask = groups_arr == g
            group_means[mask] = np.mean(residuals[mask])

        sigma2_u = float(np.var(group_means, ddof=1))
        sigma2_e = float(np.var(residuals - group_means, ddof=n_groups))

        # Step 3: GLS transformation
        theta = 1 - np.sqrt(max(sigma2_e, 1e-10) / max(sigma2_e + n_per_group * sigma2_u, 1e-10))

        y_gls = y_arr.copy()
        X_gls = np.column_stack([np.ones(n), X_arr]).copy()

        for g in unique_groups:
            mask = groups_arr == g
            y_gls[mask] -= theta * np.mean(y_arr[mask])
            for j in range(X_gls.shape[1]):
                X_gls[mask, j] -= theta * np.mean(X_gls[mask, j])

        # GLS estimation
        try:
            beta_re = np.linalg.inv(X_gls.T @ X_gls) @ (X_gls.T @ y_gls)
        except np.linalg.LinAlgError:
            return {"error": "Singular matrix in RE estimation"}

        residuals_re = y_arr - np.column_stack([np.ones(n), X_arr]) @ beta_re

        return {
            "method": "Random Effects (GLS)",
            "coefficients": [round(float(b), 6) for b in beta_re],
            "variance_components": {
                "sigma2_within": round(sigma2_e, 6),
                "sigma2_between": round(sigma2_u, 6),
                "theta": round(float(theta), 6),
            },
            "n_groups": n_groups,
            "n_observations": n,
            "_confidence": 0.8,
        }

    async def _hausman_test(
        self,
        fe_coefficients: List[float],
        re_coefficients: List[float],
        fe_covariance: List[List[float]],
        re_covariance: List[List[float]],
    ) -> Dict[str, Any]:
        """
        Hausman test: Fixed Effects vs Random Effects.

        H₀: RE is consistent and efficient (no correlation between
            individual effects and regressors)
        H₁: FE is consistent (correlation exists)

        H = (β_FE - β_RE)' [Var(β_FE) - Var(β_RE)]⁻¹ (β_FE - β_RE)
        Under H₀: H ~ χ²(k)
        """
        beta_diff = np.array(fe_coefficients) - np.array(re_coefficients)
        var_diff = np.array(fe_covariance) - np.array(re_covariance)

        try:
            var_diff_inv = np.linalg.inv(var_diff)
        except np.linalg.LinAlgError:
            return {"error": "Singular variance difference matrix"}

        H = float(beta_diff @ var_diff_inv @ beta_diff)
        df = len(fe_coefficients)
        p_value = 1 - stats.chi2.cdf(H, df)

        use_fixed = p_value < 0.05

        return {
            "hausman_statistic": round(H, 4),
            "df": df,
            "p_value": round(p_value, 6),
            "significant_at_05": use_fixed,
            "recommendation": (
                "Use Fixed Effects (individual effects correlate with regressors)"
                if use_fixed
                else "Use Random Effects (more efficient, no correlation detected)"
            ),
            "_confidence": 0.85,
        }

    async def _arima_model(
        self,
        data: List[float],
        p: int = 1,
        d: int = 0,
        q: int = 0,
        steps: int = 7,
    ) -> Dict[str, Any]:
        """
        Fit ARIMA(p,d,q) and forecast.

        Args:
            data: Time series
            p: AR order
            d: Differencing order
            q: MA order
            steps: Forecast horizon
        """
        from app.services.econometric_engine import ARIMAModel

        model = ARIMAModel(p=p, d=d, q=q)
        fit_result = model.fit(np.array(data, dtype=float))

        if "error" in fit_result:
            return fit_result

        forecast_result = model.forecast(steps=steps)

        return {
            "fit": fit_result,
            "forecast": forecast_result,
            "_confidence": 0.8,
        }

    async def _var_model(
        self,
        data: List[List[float]],
        variable_names: Optional[List[str]] = None,
        p: int = 1,
        periods: int = 20,
    ) -> Dict[str, Any]:
        """
        Fit VAR(p) model.

        Args:
            data: (T × k) matrix of endogenous variables
            variable_names: Variable names
            p: VAR order
            periods: IRF/FEVD horizon
        """
        from app.services.econometric_engine import VARModel

        model = VARModel(p=p)
        fit_result = model.fit(np.array(data, dtype=float), variable_names=variable_names)

        if "error" in fit_result:
            return fit_result

        irf = model.impulse_response(periods=periods)
        fevd = model.variance_decomposition(periods=periods)

        return {
            "fit": fit_result,
            "impulse_response": irf,
            "variance_decomposition": fevd,
            "_confidence": 0.75,
        }

    async def _cointegration_test(
        self,
        y: List[float],
        x: List[float],
    ) -> Dict[str, Any]:
        """
        Engle-Granger cointegration test.

        Tests if two non-stationary series share a long-run equilibrium.
        If cointegrated, estimates Error Correction Model (ECM).
        """
        from app.services.econometric_engine import CointegrationTester

        result = CointegrationTester.engle_granger(
            np.array(y, dtype=float),
            np.array(x, dtype=float),
        )
        result["_confidence"] = 0.8
        return result
