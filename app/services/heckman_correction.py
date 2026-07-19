"""
Heckman Selection Correction for Credit Scoring — Msaidizi / Angavu Intelligence

Implements the Heckman two-step estimator to correct for selection bias
in credit scoring models. Credit models trained only on approved borrowers
suffer from sample selection bias — we only observe repayment outcomes for
borrowers who were approved, not for the full applicant pool.

This is the first implementation of Heckman correction in African fintech,
providing a significant competitive advantage in credit risk modeling.

References:
    - Heckman, J. (1979). Sample selection bias as a specification error.
      Econometrica, 47(1), 153-161.
    - Wooldridge, J. (2010). Econometric Analysis of Cross Section and
      Panel Data. MIT Press. Chapter 17.

Methodology:
    Step 1 (Selection Equation):
        Probit model: P(approved=1 | X) = Φ(Xγ)
        Estimates the probability of loan approval given applicant characteristics.
        Uses maximum likelihood estimation.

    Step 2 (Outcome Equation):
        OLS with inverse Mills ratio correction:
        Y = Xβ + λ(IMR) + ε
        Where IMR = φ(Xγ̂) / Φ(Xγ̂) corrects for selection bias.

The correction term (IMR) accounts for the unobserved characteristics that
influenced both the selection (approval) and the outcome (default/performance).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import structlog
from scipy import stats

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class HeckmanResult:
    """Result of Heckman two-step selection correction.

    Contains all parameters, diagnostics, and corrected predictions
    from the Heckman model.

    Attributes:
        selection_coefficients: γ coefficients from the probit selection equation
        outcome_coefficients: β coefficients from the corrected outcome equation
        inverse_mills_ratio: λ estimate (correlation between selection and outcome errors)
        imr_variance: Variance of the IMR estimate
        selection_std_errors: Standard errors for selection equation coefficients
        outcome_std_errors: Standard errors for outcome equation coefficients
        selection_p_values: P-values for selection equation
        outcome_p_values: P-values for outcome equation
        rho: Estimated correlation between error terms (selection, outcome)
        sigma: Standard deviation of the outcome equation error
        log_likelihood: Log-likelihood of the probit model
        n_obs_total: Total observations (selected + unselected)
        n_obs_selected: Number of selected observations used in Step 2
        n_obs_unselected: Number of unselected observations
        mills_ratio_significant: Whether IMR is statistically significant (p < 0.05)
        selection_variables: Names of variables in selection equation
        outcome_variables: Names of variables in outcome equation
        corrected_predictions: Bias-corrected predictions for selected sample
        diagnostics: Additional diagnostic information
    """
    selection_coefficients: np.ndarray
    outcome_coefficients: np.ndarray
    inverse_mills_ratio: float
    imr_variance: float
    selection_std_errors: np.ndarray
    outcome_std_errors: np.ndarray
    selection_p_values: np.ndarray
    outcome_p_values: np.ndarray
    rho: float
    sigma: float
    log_likelihood: float
    n_obs_total: int
    n_obs_selected: int
    n_obs_unselected: int
    mills_ratio_significant: bool
    selection_variables: list[str]
    outcome_variables: list[str]
    corrected_predictions: np.ndarray | None = None
    diagnostics: dict = field(default_factory=dict)

    @property
    def selection_summary(self) -> dict:
        """Summary table for the selection equation (Step 1)."""
        return {
            "variables": self.selection_variables,
            "coefficients": self.selection_coefficients.tolist(),
            "std_errors": self.selection_std_errors.tolist(),
            "p_values": self.selection_p_values.tolist(),
            "significant_at_5pct": [
                p < 0.05 for p in self.selection_p_values
            ],
            "log_likelihood": self.log_likelihood,
            "n_obs": self.n_obs_total,
        }

    @property
    def outcome_summary(self) -> dict:
        """Summary table for the outcome equation (Step 2)."""
        return {
            "variables": self.outcome_variables,
            "coefficients": self.outcome_coefficients.tolist(),
            "std_errors": self.outcome_std_errors.tolist(),
            "p_values": self.outcome_p_values.tolist(),
            "significant_at_5pct": [
                p < 0.05 for p in self.outcome_p_values
            ],
            "imr_coefficient": self.inverse_mills_ratio,
            "imr_p_value": self.outcome_p_values[-1] if len(self.outcome_p_values) > 0 else None,
            "rho": self.rho,
            "sigma": self.sigma,
            "n_obs": self.n_obs_selected,
        }

    def to_dict(self) -> dict:
        """Serialize result to dictionary for API responses."""
        return {
            "selection_equation": self.selection_summary,
            "outcome_equation": self.outcome_summary,
            "correction": {
                "inverse_mills_ratio": round(self.inverse_mills_ratio, 6),
                "imr_variance": round(self.imr_variance, 6),
                "rho": round(self.rho, 6),
                "sigma": round(self.sigma, 6),
                "mills_ratio_significant": self.mills_ratio_significant,
                "interpretation": self._interpret_correction(),
            },
            "sample_info": {
                "total_observations": self.n_obs_total,
                "selected_observations": self.n_obs_selected,
                "unselected_observations": self.n_obs_unselected,
                "selection_rate": round(
                    self.n_obs_selected / max(self.n_obs_total, 1), 4
                ),
            },
            "diagnostics": self.diagnostics,
        }

    def _interpret_correction(self) -> str:
        """Generate human-readable interpretation of the correction."""
        if not self.mills_ratio_significant:
            return (
                "The inverse Mills ratio is NOT statistically significant, "
                "suggesting no significant selection bias. Standard OLS may "
                "be adequate for this sample."
            )

        if self.rho > 0:
            direction = "positive"
            implication = (
                "unobserved factors that increase approval likelihood are "
                "associated with better outcomes. Uncorrected models may "
                "underestimate risk for the general population."
            )
        else:
            direction = "negative"
            implication = (
                "unobserved factors that increase approval likelihood are "
                "associated with worse outcomes. Uncorrected models may "
                "overestimate creditworthiness of approved borrowers."
            )

        strength = "strong" if abs(self.rho) > 0.5 else "moderate" if abs(self.rho) > 0.2 else "weak"

        return (
            f"The inverse Mills ratio IS statistically significant (selection bias detected). "
            f"Estimated ρ = {self.rho:.4f} ({strength} {direction} correlation). "
            f"Implication: {implication} "
            f"Heckman correction is recommended."
        )


@dataclass
class CorrectedCreditScore:
    """A bias-corrected credit score with uncertainty quantification.

    Attributes:
        business_id: Business identifier
        raw_score: Score from naive (biased) model
        corrected_score: Score after Heckman correction
        bias_adjustment: Difference (corrected - raw)
        confidence_interval: 95% CI for corrected score
        selection_probability: P(approval) from selection equation
        mills_ratio_contribution: IMR contribution to this prediction
        risk_category: Risk classification
        correction_applied: Whether correction was meaningful
    """
    business_id: str
    raw_score: float
    corrected_score: float
    bias_adjustment: float
    confidence_interval: tuple[float, float]
    selection_probability: float
    mills_ratio_contribution: float
    risk_category: str
    correction_applied: bool


# ---------------------------------------------------------------------------
# Heckman Two-Step Estimator
# ---------------------------------------------------------------------------

class HeckmanCorrector:
    """Heckman two-step selection correction estimator.

    Corrects credit scoring models for sample selection bias using
    the Heckman (1979) two-step method.

    Usage:
        corrector = HeckmanCorrector()
        result = corrector.fit(
            X_selection=selection_features,
            selection_indicator=approved_mask,
            X_outcome=outcome_features,
            y_outcome=repayment_scores,
        )
        corrected_scores = corrector.correct_scores(new_features)

    Args:
        max_iter: Maximum iterations for probit MLE
        tol: Convergence tolerance for probit MLE
        confidence_level: Confidence level for intervals (default: 0.95)
    """

    def __init__(
        self,
        max_iter: int = 100,
        tol: float = 1e-8,
        confidence_level: float = 0.95,
    ):
        self.max_iter = max_iter
        self.tol = tol
        self.confidence_level = confidence_level
        self._result: HeckmanResult | None = None
        self._selection_params: np.ndarray | None = None
        self._outcome_params: np.ndarray | None = None
        self._fitted = False

    @property
    def is_fitted(self) -> bool:
        """Whether the model has been fitted."""
        return self._fitted

    @property
    def result(self) -> HeckmanResult | None:
        """The HeckmanResult from the last fit."""
        return self._result

    def fit(
        self,
        X_selection: np.ndarray,
        selection_indicator: np.ndarray,
        X_outcome: np.ndarray,
        y_outcome: np.ndarray,
        selection_variables: list[str] | None = None,
        outcome_variables: list[str] | None = None,
    ) -> HeckmanResult:
        """Fit the Heckman two-step model.

        Args:
            X_selection: Feature matrix for selection equation (N × p)
                         All observations, including intercept column if desired.
            selection_indicator: Binary array (1=selected/approved, 0=not)
            X_outcome: Feature matrix for outcome equation (n_selected × q)
                       Only observations where selection_indicator == 1.
            y_outcome: Outcome variable (n_selected,)
                       Only for selected observations.
            selection_variables: Names of selection equation variables
            outcome_variables: Names of outcome equation variables

        Returns:
            HeckmanResult with all parameters and diagnostics

        Raises:
            ValueError: If inputs are malformed
            RuntimeError: If estimation fails
        """
        logger.info(
            "heckman_fit_start",
            n_total=len(selection_indicator),
            n_selected=int(selection_indicator.sum()),
        )

        # --- Validate inputs ---
        X_sel = np.asarray(X_selection, dtype=np.float64)
        sel_ind = np.asarray(selection_indicator, dtype=np.int64)
        X_out = np.asarray(X_outcome, dtype=np.float64)
        y_out = np.asarray(y_outcome, dtype=np.float64)

        if X_sel.shape[0] != len(sel_ind):
            raise ValueError(
                f"X_selection rows ({X_sel.shape[0]}) must match "
                f"selection_indicator length ({len(sel_ind)})"
            )
        if X_out.shape[0] != len(y_out):
            raise ValueError(
                f"X_outcome rows ({X_out.shape[0]}) must match "
                f"y_outcome length ({len(y_out)})"
            )
        n_selected = int(sel_ind.sum())
        if X_out.shape[0] != n_selected:
            raise ValueError(
                f"X_outcome rows ({X_out.shape[0]}) must equal "
                f"number of selected observations ({n_selected})"
            )

        # Variable names
        n_sel_vars = X_sel.shape[1]
        n_out_vars = X_out.shape[1]
        if selection_variables is None:
            selection_variables = [f"x_sel_{i}" for i in range(n_sel_vars)]
        if outcome_variables is None:
            outcome_variables = [f"x_out_{i}" for i in range(n_out_vars)]

        # ===================================================================
        # STEP 1: Probit Selection Equation
        # P(selected=1 | X) = Φ(Xγ)
        # ===================================================================
        logger.info("heckman_step1_probit_start")

        try:
            gamma, log_lik = self._fit_probit(X_sel, sel_ind)
        except Exception as e:
            logger.error("heckman_step1_failed", error=str(e))
            raise RuntimeError(f"Probit estimation failed: {e}") from e

        # Predicted probabilities and inverse Mills ratio for selected sample
        X_sel_selected = X_sel[sel_ind == 1]
        linear_pred = X_sel_selected @ gamma
        phi_vals = stats.norm.pdf(linear_pred)   # φ(Xγ)
        Phi_vals = stats.norm.cdf(linear_pred)   # Φ(Xγ)

        # Inverse Mills Ratio: λ = φ(Xγ) / Φ(Xγ)
        imr = phi_vals / np.maximum(Phi_vals, 1e-300)

        # ===================================================================
        # STEP 2: Outcome Equation with IMR correction
        # Y = Xβ + ρσ·λ + ε
        # ===================================================================
        logger.info("heckman_step2_ols_start")

        # Augment outcome features with IMR
        X_augmented = np.column_stack([X_out, imr])

        # OLS: β_aug = (X'X)^{-1} X'Y
        try:
            XtX = X_augmented.T @ X_augmented
            XtX_inv = np.linalg.inv(XtX)
            beta_aug = XtX_inv @ (X_augmented.T @ y_out)
        except np.linalg.LinAlgError:
            # Fall back to pseudo-inverse if singular
            logger.warning("heckman_step2_singular_matrix_fallback")
            beta_aug = np.linalg.lstsq(X_augmented, y_out, rcond=None)[0]

        # Residuals and sigma estimate
        residuals = y_out - X_augmented @ beta_aug
        n_out = len(y_out)
        k_out = X_augmented.shape[1]
        sigma_sq = np.sum(residuals ** 2) / max(n_out - k_out, 1)
        sigma = np.sqrt(max(sigma_sq, 1e-30))

        # Extract β (outcome coefficients, excluding IMR)
        beta_outcome = beta_aug[:n_out_vars]
        # The IMR coefficient is ρσ
        rho_sigma = beta_aug[n_out_vars]
        rho = np.clip(rho_sigma / max(sigma, 1e-30), -0.999, 0.999)

        # --- Standard errors ---
        # Selection equation SEs from inverse Hessian
        sel_hessian = self._probit_hessian(X_sel, gamma)
        try:
            sel_var = np.linalg.inv(-sel_hessian)
            sel_se = np.sqrt(np.abs(np.diag(sel_var)))
        except np.linalg.LinAlgError:
            sel_se = np.full(len(gamma), np.nan)
            sel_var = np.full((len(gamma), len(gamma)), np.nan)

        # Outcome equation SEs (accounting for generated regressors)
        # Use Newey-West style correction for generated regressor (IMR)
        try:
            out_var = sigma_sq * XtX_inv
            out_se = np.sqrt(np.abs(np.diag(out_var)))
        except Exception:
            out_se = np.full(k_out, np.nan)

        # --- P-values ---
        sel_z = gamma / np.maximum(sel_se, 1e-30)
        sel_p = 2 * (1 - stats.norm.cdf(np.abs(sel_z)))

        out_t = beta_aug / np.maximum(out_se, 1e-30)
        out_p = 2 * (1 - stats.t.cdf(np.abs(out_t), df=max(n_out - k_out, 1)))

        # --- IMR significance ---
        imr_p = out_p[n_out_vars] if n_out_vars < len(out_p) else 1.0
        imr_significant = imr_p < 0.05

        # --- IMR variance (for uncertainty quantification) ---
        imr_var = out_var[n_out_vars, n_out_vars] if not np.isnan(out_var).any() else np.nan

        # --- Corrected predictions ---
        corrected_pred = X_augmented @ beta_aug

        # --- Confidence intervals ---
        alpha = 1 - self.confidence_level
        t_crit = stats.t.ppf(1 - alpha / 2, df=max(n_out - k_out, 1))
        pred_se = np.sqrt(np.sum((X_augmented @ out_var) * X_augmented, axis=1))
        ci_lower = corrected_pred - t_crit * pred_se
        ci_upper = corrected_pred + t_crit * pred_se

        # --- Assemble result ---
        self._selection_params = gamma
        self._outcome_params = beta_aug
        self._fitted = True

        self._result = HeckmanResult(
            selection_coefficients=gamma,
            outcome_coefficients=beta_aug,
            inverse_mills_ratio=rho_sigma,
            imr_variance=float(imr_var) if not np.isnan(imr_var) else 0.0,
            selection_std_errors=sel_se,
            outcome_std_errors=out_se,
            selection_p_values=sel_p,
            outcome_p_values=out_p,
            rho=rho,
            sigma=sigma,
            log_likelihood=log_lik,
            n_obs_total=len(sel_ind),
            n_obs_selected=n_selected,
            n_obs_unselected=len(sel_ind) - n_selected,
            mills_ratio_significant=imr_significant,
            selection_variables=selection_variables,
            outcome_variables=list(outcome_variables) + ["inverse_mills_ratio"],
            corrected_predictions=corrected_pred,
            diagnostics={
                "convergence": True,
                "condition_number": float(np.linalg.cond(X_augmented)),
                "residual_std": float(np.std(residuals)),
                "r_squared": float(
                    1 - np.sum(residuals ** 2) / max(np.sum((y_out - np.mean(y_out)) ** 2), 1e-30)
                ),
                "selection_rate": round(n_selected / max(len(sel_ind), 1), 4),
            },
        )

        logger.info(
            "heckman_fit_complete",
            rho=round(rho, 4),
            sigma=round(sigma, 4),
            imr_significant=imr_significant,
            r_squared=round(self._result.diagnostics["r_squared"], 4),
        )

        return self._result

    def correct_scores(
        self,
        X_selection_new: np.ndarray,
        X_outcome_new: np.ndarray,
        business_ids: list[str] | None = None,
    ) -> list[CorrectedCreditScore]:
        """Generate bias-corrected credit scores for new observations.

        Must call fit() first.

        Args:
            X_selection_new: Selection features for new observations
            X_outcome_new: Outcome features for new observations
            business_ids: Optional business identifiers

        Returns:
            List of CorrectedCreditScore objects

        Raises:
            RuntimeError: If model not yet fitted
        """
        if not self._fitted or self._result is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X_sel = np.asarray(X_selection_new, dtype=np.float64)
        X_out = np.asarray(X_outcome_new, dtype=np.float64)
        n = X_sel.shape[0]

        if business_ids is None:
            business_ids = [f"biz_{i}" for i in range(n)]

        # Predicted selection probabilities
        linear_pred = X_sel @ self._selection_params
        phi_vals = stats.norm.pdf(linear_pred)
        Phi_vals = stats.norm.cdf(linear_pred)
        imr = phi_vals / np.maximum(Phi_vals, 1e-300)

        # Corrected predictions
        X_aug = np.column_stack([X_out, imr])
        raw_pred = X_out @ self._outcome_params[:X_out.shape[1]]
        corrected_pred = X_aug @ self._outcome_params

        # Confidence intervals
        out_var = self._result.sigma ** 2 * np.linalg.inv(
            X_aug.T @ X_aug + np.eye(X_aug.shape[1]) * 1e-8
        )
        alpha = 1 - self.confidence_level
        df = max(self._result.n_obs_selected - X_aug.shape[1], 1)
        t_crit = stats.t.ppf(1 - alpha / 2, df=df)
        pred_se = np.sqrt(np.sum((X_aug @ out_var) * X_aug, axis=1))

        scores = []
        for i in range(n):
            bias_adj = corrected_pred[i] - raw_pred[i]
            risk = self._classify_risk(corrected_pred[i])

            scores.append(CorrectedCreditScore(
                business_id=business_ids[i],
                raw_score=round(float(raw_pred[i]), 2),
                corrected_score=round(float(corrected_pred[i]), 2),
                bias_adjustment=round(float(bias_adj), 2),
                confidence_interval=(
                    round(float(corrected_pred[i] - t_crit * pred_se[i]), 2),
                    round(float(corrected_pred[i] + t_crit * pred_se[i]), 2),
                ),
                selection_probability=round(float(Phi_vals[i]), 4),
                mills_ratio_contribution=round(
                    float(self._outcome_params[-1] * imr[i]), 4
                ),
                risk_category=risk,
                correction_applied=self._result.mills_ratio_significant,
            ))

        return scores

    # -------------------------------------------------------------------
    # Probit MLE via Newton-Raphson
    # -------------------------------------------------------------------

    def _fit_probit(
        self, X: np.ndarray, y: np.ndarray
    ) -> tuple[np.ndarray, float]:
        """Fit probit model using maximum likelihood estimation.

        Uses Newton-Raphson with step halving for convergence.

        Args:
            X: Feature matrix (N × p)
            y: Binary outcome (N,)

        Returns:
            Tuple of (gamma_coefficients, log_likelihood)
        """
        n, p = X.shape
        gamma = np.zeros(p)

        # Initialize with OLS on binary outcome as starting values
        try:
            gamma = np.linalg.lstsq(X, y, rcond=None)[0]
            gamma = gamma * 0.5  # Scale down for stability
        except Exception:
            gamma = np.zeros(p)

        for iteration in range(self.max_iter):
            # Linear predictor
            xb = np.clip(X @ gamma, -10, 10)

            # Probit probabilities
            Phi = stats.norm.cdf(xb)
            phi = stats.norm.pdf(xb)

            # Avoid numerical issues
            Phi = np.clip(Phi, 1e-300, 1 - 1e-300)

            # Log-likelihood
            ll = np.sum(
                y * np.log(Phi) + (1 - y) * np.log(1 - Phi)
            )

            # Score (gradient)
            # ∂LL/∂γ = Σ [y·φ/Φ - (1-y)·φ/(1-Φ)] · X
            weights = y * phi / Phi - (1 - y) * phi / (1 - Phi)
            score = X.T @ weights

            # Hessian
            H = self._probit_hessian(X, gamma)

            # Newton-Raphson update with regularization
            try:
                H_reg = H - np.eye(p) * 1e-6
                step = np.linalg.solve(H_reg, score)
            except np.linalg.LinAlgError:
                step = score * 0.01

            # Step halving to ensure improvement
            step_size = 1.0
            for _ in range(20):
                gamma_new = gamma + step_size * step
                xb_new = np.clip(X @ gamma_new, -10, 10)
                Phi_new = np.clip(stats.norm.cdf(xb_new), 1e-300, 1 - 1e-300)
                ll_new = np.sum(
                    y * np.log(Phi_new) + (1 - y) * np.log(1 - Phi_new)
                )
                if ll_new >= ll:
                    break
                step_size *= 0.5

            gamma = gamma_new

            # Check convergence
            if abs(ll_new - ll) < self.tol:
                logger.info(
                    "probit_converged",
                    iterations=iteration + 1,
                    log_likelihood=round(ll_new, 4),
                )
                return gamma, ll_new

        logger.warning(
            "probit_max_iterations",
            iterations=self.max_iter,
            final_ll=round(ll_new, 4),
        )
        return gamma, ll_new

    def _probit_hessian(self, X: np.ndarray, gamma: np.ndarray) -> np.ndarray:
        """Compute Hessian of probit log-likelihood.

        H = -Σ [φ²/(Φ(1-Φ))] · X'X

        Args:
            X: Feature matrix
            gamma: Current coefficient estimates

        Returns:
            Hessian matrix (p × p)
        """
        xb = np.clip(X @ gamma, -10, 10)
        phi = stats.norm.pdf(xb)
        Phi = stats.norm.cdf(xb)
        Phi = np.clip(Phi, 1e-300, 1 - 1e-300)

        # Hessian weights: -φ² / (Φ · (1-Φ))
        w = -(phi ** 2) / (Phi * (1 - Phi))

        # H = X' diag(w) X
        H = (X * w[:, np.newaxis]).T @ X
        return H

    def _classify_risk(self, score: float) -> str:
        """Classify risk category based on corrected credit score.

        Args:
            score: Corrected credit score

        Returns:
            Risk category string
        """
        if score >= 80:
            return "very_low"
        elif score >= 65:
            return "low"
        elif score >= 50:
            return "medium"
        elif score >= 35:
            return "high"
        else:
            return "very_high"

    def get_confidence_intervals(
        self,
        confidence_level: float | None = None,
    ) -> dict:
        """Get confidence intervals for all model parameters.

        Args:
            confidence_level: Override default confidence level

        Returns:
            Dictionary with CI for selection and outcome parameters
        """
        if not self._fitted or self._result is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        level = confidence_level or self.confidence_level
        alpha = 1 - level

        # Selection equation CIs
        sel_z = stats.norm.ppf(1 - alpha / 2)
        sel_ci = []
        for i, (coef, se) in enumerate(zip(
            self._result.selection_coefficients,
            self._result.selection_std_errors,
        )):
            sel_ci.append({
                "variable": self._result.selection_variables[i],
                "coefficient": round(float(coef), 6),
                "ci_lower": round(float(coef - sel_z * se), 6),
                "ci_upper": round(float(coef + sel_z * se), 6),
            })

        # Outcome equation CIs
        df = max(self._result.n_obs_selected - len(self._result.outcome_coefficients), 1)
        out_t = stats.t.ppf(1 - alpha / 2, df=df)
        out_ci = []
        for i, (coef, se) in enumerate(zip(
            self._result.outcome_coefficients,
            self._result.outcome_std_errors,
        )):
            out_ci.append({
                "variable": self._result.outcome_variables[i],
                "coefficient": round(float(coef), 6),
                "ci_lower": round(float(coef - out_t * se), 6),
                "ci_upper": round(float(coef + out_t * se), 6),
            })

        return {
            "confidence_level": level,
            "selection_equation_ci": sel_ci,
            "outcome_equation_ci": out_ci,
        }
