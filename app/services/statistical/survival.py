"""
Survival Analysis — Cox Proportional Hazards for Angavu Intelligence.

Predicts time-to-event outcomes for informal economy participants:
- Time-to-default for loans
- Time-to-churn for workers
- Time-to-business-closure

Academic Foundation:
- Cox, D.R. (1972). Regression models and life-tables. JRSS-B, 34(2), 187-220.
- Kaplan-Meier estimator for non-parametric survival curves
- ECO 206 (Microfinance): Default timing, dynamic incentive models
- STA 341 (Estimation): Partial likelihood MLE for hazard ratios
- STA 342 (Inference): Likelihood ratio tests for covariate significance

Implementation uses lifelines if available, otherwise provides a
self-contained Cox PH implementation using scipy.

Buyers: Microfinance banks, M-Shwari, Fuliza, Tala, Branch
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import structlog
from scipy import stats as sp_stats

logger = structlog.get_logger(__name__)

# Try importing lifelines for full survival analysis
try:
    from lifelines import CoxPHFitter, KaplanMeierFitter
    from lifelines.statistics import logrank_test

    LIFELINES_AVAILABLE = True
except ImportError:
    LIFELINES_AVAILABLE = False
    logger.info(
        "lifelines_not_installed",
        msg="pip install lifelines for full survival analysis; using built-in Cox PH",
    )


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class SurvivalPrediction:
    """Prediction from a survival model.

    Attributes:
        entity_id: ID of the entity (worker/loan)
        entity_type: 'worker' or 'loan'
        event_type: 'default' or 'churn' or 'closure'
        survival_probability: P(survive beyond time t) for various t
        median_survival_time: Expected time until event (days)
        hazard_ratio: Relative hazard compared to baseline
        risk_score: Normalized risk score (0-1, higher = riskier)
        risk_factors: Contributing risk factors
        confidence: Model confidence
        explanation_sw: Swahili explanation
    """
    entity_id: str
    entity_type: str  # "worker" | "loan"
    event_type: str  # "default" | "churn" | "closure"
    survival_curve: dict[int, float]  # time_days -> survival_prob
    median_survival_time: float  # days
    hazard_ratio: float
    risk_score: float
    risk_factors: list[str]
    confidence: float
    explanation_sw: str
    feature_importance: dict[str, float]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "event_type": self.event_type,
            "survival_curve": {str(k): round(v, 4) for k, v in self.survival_curve.items()},
            "median_survival_time_days": round(self.median_survival_time, 1),
            "hazard_ratio": round(self.hazard_ratio, 4),
            "risk_score": round(self.risk_score, 4),
            "risk_factors": self.risk_factors,
            "confidence": round(self.confidence, 3),
            "explanation_sw": self.explanation_sw,
            "feature_importance": {k: round(v, 4) for k, v in self.feature_importance.items()},
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class CoxModelResult:
    """Result from fitting a Cox PH model.

    Attributes:
        coefficients: Feature coefficients (log hazard ratios)
        hazard_ratios: exp(coefficients) — multiplicative effect on hazard
        standard_errors: SE of coefficients
        p_values: p-values for each coefficient
        confidence_intervals: 95% CI for hazard ratios
        concordance_index: Model discrimination (C-index)
        log_likelihood: Model log-likelihood
        n_observations: Number of observations used
        n_events: Number of events observed
    """
    coefficients: dict[str, float]
    hazard_ratios: dict[str, float]
    standard_errors: dict[str, float]
    p_values: dict[str, float]
    confidence_intervals: dict[str, tuple[float, float]]
    concordance_index: float
    log_likelihood: float
    n_observations: int
    n_events: int

    def to_dict(self) -> dict[str, Any]:
        features = {}
        for feat in self.coefficients:
            features[feat] = {
                "coefficient": round(self.coefficients[feat], 4),
                "hazard_ratio": round(self.hazard_ratios[feat], 4),
                "std_error": round(self.standard_errors[feat], 4),
                "p_value": round(self.p_values[feat], 6),
                "ci_lower": round(self.confidence_intervals[feat][0], 4),
                "ci_upper": round(self.confidence_intervals[feat][1], 4),
                "significant": self.p_values[feat] < 0.05,
            }
        return {
            "features": features,
            "concordance_index": round(self.concordance_index, 4),
            "log_likelihood": round(self.log_likelihood, 2),
            "n_observations": self.n_observations,
            "n_events": self.n_events,
        }


# ---------------------------------------------------------------------------
# Built-in Cox PH Implementation
# ---------------------------------------------------------------------------

class _BuiltinCoxPH:
    """
    Self-contained Cox Proportional Hazards model.

    Uses partial likelihood maximization via Newton-Raphson.
    Implements Breslow's method for tie handling.

    Reference: Cox (1972), Kalbfleisch & Prentice (2002)
    """

    def __init__(self):
        self.coefficients: np.ndarray | None = None
        self.feature_names: list[str] = []
        self._fitted = False

    def fit(
        self,
        X: np.ndarray,
        durations: np.ndarray,
        events: np.ndarray,
        feature_names: list[str],
    ) -> CoxModelResult:
        """
        Fit the Cox PH model.

        Maximizes the partial likelihood:
            L(β) = Πᵢ [exp(xᵢ'β) / Σⱼ∈Rᵢ exp(xⱼ'β)]

        where Rᵢ is the risk set at time tᵢ (all subjects still at risk).

        Args:
            X: Covariate matrix (n × p)
            durations: Time to event or censoring (n,)
            events: Event indicator (1=event, 0=censored) (n,)
            feature_names: Feature names

        Returns:
            CoxModelResult with fitted parameters
        """
        self.feature_names = feature_names
        n, p = X.shape

        # Initialize coefficients
        beta = np.zeros(p)

        # Newton-Raphson to maximize partial log-likelihood
        for iteration in range(50):
            ll, grad, hess = self._partial_likelihood(X, durations, events, beta)

            try:
                delta = np.linalg.solve(-hess, grad)
            except np.linalg.LinAlgError:
                break

            beta = beta - delta
            if np.max(np.abs(delta)) < 1e-6:
                break

        self.coefficients = beta
        self._fitted = True

        # Compute standard errors from observed information
        _, _, hess = self._partial_likelihood(X, durations, events, beta)
        try:
            cov_matrix = np.linalg.inv(-hess)
            se = np.sqrt(np.diag(cov_matrix))
        except np.linalg.LinAlgError:
            se = np.full(p, np.nan)

        # Hazard ratios and CIs
        hr = np.exp(beta)
        ci_lower = np.exp(beta - 1.96 * se)
        ci_upper = np.exp(beta + 1.96 * se)

        # Wald p-values
        z_scores = beta / np.maximum(se, 1e-10)
        p_values = 2 * (1 - sp_stats.norm.cdf(np.abs(z_scores)))

        # Concordance index
        c_index = self._concordance_index(X, durations, events, beta)

        # Final log-likelihood
        ll_final, _, _ = self._partial_likelihood(X, durations, events, beta)

        return CoxModelResult(
            coefficients={name: float(beta[i]) for i, name in enumerate(feature_names)},
            hazard_ratios={name: float(hr[i]) for i, name in enumerate(feature_names)},
            standard_errors={name: float(se[i]) for i, name in enumerate(feature_names)},
            p_values={name: float(p_values[i]) for i, name in enumerate(feature_names)},
            confidence_intervals={
                name: (float(ci_lower[i]), float(ci_upper[i]))
                for i, name in enumerate(feature_names)
            },
            concordance_index=float(c_index),
            log_likelihood=float(ll_final),
            n_observations=n,
            n_events=int(np.sum(events)),
        )

    def predict_survival_curve(
        self,
        x_new: np.ndarray,
        durations_train: np.ndarray,
        events_train: np.ndarray,
        X_train: np.ndarray,
        time_points: np.ndarray | None = None,
    ) -> dict[int, float]:
        """
        Predict survival function S(t|x) for a new observation.

        S(t|x) = S₀(t)^exp(x'β)

        where S₀(t) is the baseline survival function (Breslow estimator).

        Args:
            x_new: Feature vector for new observation
            durations_train: Training durations
            events_train: Training events
            X_train: Training features
            time_points: Time points at which to evaluate

        Returns:
            Dict mapping time_days -> survival_probability
        """
        if not self._fitted or self.coefficients is None:
            return {}

        # Linear predictor for new observation
        lp_new = float(x_new @ self.coefficients)

        # Baseline survival (Breslow estimator)
        S0 = self._baseline_survival(
            durations_train, events_train, X_train
        )

        # S(t|x) = S₀(t)^exp(lp)
        survival = {}
        for t, s0 in sorted(S0.items()):
            s_t = s0 ** np.exp(lp_new)
            survival[int(t)] = float(np.clip(s_t, 0, 1))

        return survival

    def predict_median_survival(
        self,
        survival_curve: dict[int, float],
    ) -> float:
        """Find median survival time from survival curve."""
        for t, s in sorted(survival_curve.items()):
            if s <= 0.5:
                return float(t)
        # If survival never drops below 0.5, return max observed time
        return float(max(survival_curve.keys())) if survival_curve else 365.0

    def predict_risk_score(
        self,
        x_new: np.ndarray,
    ) -> float:
        """Predict risk score (linear predictor, higher = riskier)."""
        if not self._fitted or self.coefficients is None:
            return 0.0
        lp = float(x_new @ self.coefficients)
        # Normalize to 0-1 using logistic transform
        return float(1 / (1 + np.exp(-lp)))

    def _partial_likelihood(
        self,
        X: np.ndarray,
        durations: np.ndarray,
        events: np.ndarray,
        beta: np.ndarray,
    ) -> tuple[float, np.ndarray, np.ndarray]:
        """Compute partial log-likelihood, gradient, and Hessian.

        Uses Breslow's method for ties.
        """
        n, p = X.shape
        lp = X @ beta
        exp_lp = np.exp(np.clip(lp, -20, 20))

        # Sort by duration (descending for risk sets)
        order = np.argsort(-durations)
        durations_sorted = durations[order]
        events_sorted = events[order]
        X_sorted = X[order]
        exp_lp_sorted = exp_lp[order]
        lp_sorted = lp[order]

        ll = 0.0
        grad = np.zeros(p)
        hess = np.zeros((p, p))

        # Risk set cumulative sum (from end)
        risk_sum = 0.0
        risk_sum_x = np.zeros(p)
        risk_sum_xx = np.zeros((p, p))

        # Build risk sets from longest duration to shortest
        j = 0
        for i in range(n):
            # Add all subjects with duration >= current duration to risk set
            while j < n and durations_sorted[j] >= durations_sorted[i]:
                risk_sum += exp_lp_sorted[j]
                risk_sum_x += exp_lp_sorted[j] * X_sorted[j]
                risk_sum_xx += exp_lp_sorted[j] * np.outer(X_sorted[j], X_sorted[j])
                j += 1

            if events_sorted[i] == 1:
                # Partial log-likelihood contribution
                ll += lp_sorted[i] - np.log(risk_sum + 1e-10)

                # Gradient
                expected_x = risk_sum_x / risk_sum
                grad += X_sorted[i] - expected_x

                # Hessian
                expected_xx = risk_sum_xx / risk_sum
                hess -= expected_xx - np.outer(expected_x, expected_x)

        return ll, grad, hess

    def _baseline_survival(
        self,
        durations: np.ndarray,
        events: np.ndarray,
        X: np.ndarray,
    ) -> dict[int, float]:
        """Estimate baseline survival S₀(t) using Breslow's estimator."""
        if not self._fitted or self.coefficients is None:
            return {}

        lp = X @ self.coefficients
        exp_lp = np.exp(np.clip(lp, -20, 20))

        # Get unique event times
        event_mask = events == 1
        event_times = np.sort(np.unique(durations[event_mask]))

        S0 = {}
        baseline_surv = 1.0

        for t in event_times:
            # Number of events at time t
            d_t = np.sum((durations == t) & event_mask)

            # Risk set at time t
            risk_set = durations >= t
            risk_sum = np.sum(exp_lp[risk_set])

            # Breslow estimator
            if risk_sum > 0:
                baseline_surv *= np.exp(-d_t / risk_sum)

            S0[int(t)] = float(baseline_surv)

        return S0

    def _concordance_index(
        self,
        X: np.ndarray,
        durations: np.ndarray,
        events: np.ndarray,
        beta: np.ndarray,
    ) -> float:
        """Compute Harrell's C-index (concordance).

        C = P(risk_i > risk_j | t_i < t_j and event_i = 1)
        """
        lp = X @ beta
        n = len(durations)
        concordant = 0
        total = 0

        for i in range(n):
            for j in range(i + 1, n):
                if events[i] == 1 and durations[i] < durations[j]:
                    total += 1
                    if lp[i] > lp[j]:
                        concordant += 1
                elif events[j] == 1 and durations[j] < durations[i]:
                    total += 1
                    if lp[j] > lp[i]:
                        concordant += 1

        return concordant / max(total, 1)


# ---------------------------------------------------------------------------
# Kaplan-Meier Estimator (non-parametric)
# ---------------------------------------------------------------------------

class KaplanMeierEstimator:
    """
    Kaplan-Meier survival estimator.

    Non-parametric estimator of the survival function:
        S(t) = Π_{t_i ≤ t} (1 - d_i / n_i)

    where d_i = deaths at t_i, n_i = at risk just before t_i.

    Reference: Kaplan & Meier (1958), JASA 53(282), 457-481.
    """

    @staticmethod
    def fit(
        durations: np.ndarray,
        events: np.ndarray,
    ) -> dict[int, float]:
        """
        Estimate the Kaplan-Meier survival curve.

        Args:
            durations: Time to event or censoring
            events: Event indicator (1=event, 0=censored)

        Returns:
            Dict mapping time -> survival probability
        """
        if LIFELINES_AVAILABLE:
            kmf = KaplanMeierFitter()
            kmf.fit(durations, event_observed=events)
            survival = {}
            for t, s in zip(kmf.survival_function_.index, kmf.survival_function_["KM_estimate"]):
                survival[int(t)] = float(s)
            return survival

        # Built-in implementation
        order = np.argsort(durations)
        durations_sorted = durations[order]
        events_sorted = events[order]

        n = len(durations)
        at_risk = n
        survival = {}
        surv_prob = 1.0

        i = 0
        while i < n:
            t = durations_sorted[i]
            d = 0  # events at this time
            c = 0  # censored at this time

            while i < n and durations_sorted[i] == t:
                if events_sorted[i] == 1:
                    d += 1
                else:
                    c += 1
                i += 1

            if d > 0:
                surv_prob *= (1 - d / at_risk)
            survival[int(t)] = float(surv_prob)
            at_risk -= (d + c)

        return survival

    @staticmethod
    def median_survival(survival_curve: dict[int, float]) -> float | None:
        """Find median survival time from KM curve."""
        for t, s in sorted(survival_curve.items()):
            if s <= 0.5:
                return float(t)
        return None


# ---------------------------------------------------------------------------
# Main Survival Analysis Service
# ---------------------------------------------------------------------------

class SurvivalAnalysisService:
    """
    Survival analysis service for Angavu Intelligence.

    Predicts time-to-default for loans and time-to-churn for workers
    using Cox Proportional Hazards models. Integrates with Alama Score
    and Loan Intelligence products.

    Features:
    - Fit Cox PH model on historical data
    - Predict individual survival curves
    - Compute risk scores for new observations
    - Explain predictions in Swahili
    - Integrate with loan approval decisions

    Usage:
        service = SurvivalAnalysisService()

        # Fit on historical data
        result = service.fit_model(
            X=feature_matrix,
            durations=days_to_event,
            events=event_indicators,
            feature_names=["activity", "stability", ...],
        )

        # Predict for new worker
        prediction = service.predict_time_to_default(
            entity_id="worker_123",
            features=np.array([85, 70, ...]),
        )
    """

    def __init__(self):
        self._cox_model = _BuiltinCoxPH()
        self._kaplan_meier = KaplanMeierEstimator()
        self._is_fitted = False
        self._feature_names: list[str] = []
        self._train_durations: np.ndarray | None = None
        self._train_events: np.ndarray | None = None
        self._train_X: np.ndarray | None = None
        self._model_result: CoxModelResult | None = None

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def model_result(self) -> CoxModelResult | None:
        return self._model_result

    def fit_model(
        self,
        X: np.ndarray,
        durations: np.ndarray,
        events: np.ndarray,
        feature_names: list[str],
    ) -> CoxModelResult:
        """
        Fit Cox PH model on historical data.

        Args:
            X: Feature matrix (n × p)
            durations: Time to event or censoring in days
            events: Event indicator (1=event occurred, 0=censored)
            feature_names: Names of features

        Returns:
            CoxModelResult with model diagnostics
        """
        logger.info(
            "survival_model_fitting",
            n_observations=len(durations),
            n_events=int(np.sum(events)),
            n_features=len(feature_names),
        )

        result = self._cox_model.fit(X, durations, events, feature_names)

        self._is_fitted = True
        self._feature_names = feature_names
        self._train_durations = durations
        self._train_events = events
        self._train_X = X
        self._model_result = result

        logger.info(
            "survival_model_fitted",
            concordance=round(result.concordance_index, 4),
            n_significant=sum(1 for p in result.p_values.values() if p < 0.05),
        )

        return result

    def predict_time_to_default(
        self,
        entity_id: str,
        features: np.ndarray,
    ) -> SurvivalPrediction:
        """
        Predict time-to-default for a loan or worker.

        Args:
            entity_id: Entity identifier
            features: Feature vector for prediction

        Returns:
            SurvivalPrediction with survival curve and risk assessment
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit_model() first.")

        features = np.atleast_1d(features)

        # Predict survival curve
        survival_curve = self._cox_model.predict_survival_curve(
            features, self._train_durations, self._train_events, self._train_X
        )

        # Median survival time
        median_time = self._cox_model.predict_median_survival(survival_curve)

        # Risk score
        risk_score = self._cox_model.predict_risk_score(features)

        # Hazard ratio for this individual
        lp = float(features @ self._cox_model.coefficients)
        hazard_ratio = float(np.exp(lp))

        # Feature importance (absolute coefficient × feature value)
        feature_imp = {}
        if self._cox_model.coefficients is not None:
            for i, name in enumerate(self._feature_names):
                feature_imp[name] = float(
                    abs(self._cox_model.coefficients[i]) * abs(features[i])
                )

        # Risk factors
        risk_factors = self._identify_risk_factors(features)

        # Swahili explanation
        explanation_sw = self._explain_default_prediction(
            entity_id, median_time, risk_score, risk_factors
        )

        # Confidence based on C-index
        confidence = self._model_result.concordance_index if self._model_result else 0.5

        return SurvivalPrediction(
            entity_id=entity_id,
            entity_type="loan",
            event_type="default",
            survival_curve=survival_curve,
            median_survival_time=median_time,
            hazard_ratio=hazard_ratio,
            risk_score=risk_score,
            risk_factors=risk_factors,
            confidence=confidence,
            explanation_sw=explanation_sw,
            feature_importance=feature_imp,
        )

    def predict_time_to_churn(
        self,
        entity_id: str,
        features: np.ndarray,
    ) -> SurvivalPrediction:
        """
        Predict time-to-churn for a worker.

        Args:
            entity_id: Worker identifier
            features: Feature vector

        Returns:
            SurvivalPrediction with churn risk assessment
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit_model() first.")

        features = np.atleast_1d(features)

        survival_curve = self._cox_model.predict_survival_curve(
            features, self._train_durations, self._train_events, self._train_X
        )

        median_time = self._cox_model.predict_median_survival(survival_curve)
        risk_score = self._cox_model.predict_risk_score(features)

        lp = float(features @ self._cox_model.coefficients)
        hazard_ratio = float(np.exp(lp))

        feature_imp = {}
        if self._cox_model.coefficients is not None:
            for i, name in enumerate(self._feature_names):
                feature_imp[name] = float(
                    abs(self._cox_model.coefficients[i]) * abs(features[i])
                )

        risk_factors = self._identify_risk_factors(features)
        explanation_sw = self._explain_churn_prediction(
            entity_id, median_time, risk_score, risk_factors
        )

        confidence = self._model_result.concordance_index if self._model_result else 0.5

        return SurvivalPrediction(
            entity_id=entity_id,
            entity_type="worker",
            event_type="churn",
            survival_curve=survival_curve,
            median_survival_time=median_time,
            hazard_ratio=hazard_ratio,
            risk_score=risk_score,
            risk_factors=risk_factors,
            confidence=confidence,
            explanation_sw=explanation_sw,
            feature_importance=feature_imp,
        )

    def get_kaplan_meier_curve(
        self,
        durations: np.ndarray | None = None,
        events: np.ndarray | None = None,
    ) -> dict[int, float]:
        """
        Get Kaplan-Meier survival curve (non-parametric).

        Args:
            durations: Override training durations
            events: Override training events

        Returns:
            Survival curve as Dict[time, probability]
        """
        d = durations if durations is not None else self._train_durations
        e = events if events is not None else self._train_events
        if d is None or e is None:
            return {}
        return self._kaplan_meier.fit(d, e)

    def compare_groups(
        self,
        group1_durations: np.ndarray,
        group1_events: np.ndarray,
        group2_durations: np.ndarray,
        group2_events: np.ndarray,
        group1_name: str = "Group A",
        group2_name: str = "Group B",
    ) -> dict[str, Any]:
        """
        Compare survival between two groups (log-rank test).

        Args:
            group1_durations, group1_events: Group 1 data
            group2_durations, group2_events: Group 2 data
            group1_name, group2_name: Group labels

        Returns:
            Dict with test results and survival curves
        """
        # KM curves for each group
        km1 = self._kaplan_meier.fit(group1_durations, group1_events)
        km2 = self._kaplan_meier.fit(group2_durations, group2_events)

        # Log-rank test
        if LIFELINES_AVAILABLE:
            result = logrank_test(
                group1_durations, group2_durations,
                group1_events, group2_events,
            )
            test_stat = result.test_statistic
            p_value = result.p_value
        else:
            # Simplified log-rank test
            test_stat, p_value = self._simple_logrank(
                group1_durations, group1_events,
                group2_durations, group2_events,
            )

        return {
            "group1": {
                "name": group1_name,
                "n": len(group1_durations),
                "events": int(np.sum(group1_events)),
                "median_survival": self._kaplan_meier.median_survival(km1),
                "survival_curve": {str(k): round(v, 4) for k, v in km1.items()},
            },
            "group2": {
                "name": group2_name,
                "n": len(group2_durations),
                "events": int(np.sum(group2_events)),
                "median_survival": self._kaplan_meier.median_survival(km2),
                "survival_curve": {str(k): round(v, 4) for k, v in km2.items()},
            },
            "log_rank_test": {
                "test_statistic": round(float(test_stat), 4),
                "p_value": round(float(p_value), 6),
                "significant": p_value < 0.05,
                "interpretation": (
                    f"{'Significant' if p_value < 0.05 else 'No significant'} "
                    f"difference in survival between {group1_name} and {group2_name}"
                ),
            },
        }

    # -------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------

    def _identify_risk_factors(self, features: np.ndarray) -> list[str]:
        """Identify risk factors from feature values."""
        factors = []
        if self._cox_model.coefficients is None:
            return factors

        for i, name in enumerate(self._feature_names):
            coef = self._cox_model.coefficients[i]
            val = features[i]

            # Positive coefficient = higher risk
            if coef > 0.1 and val > 0.5:
                factors.append(f"High {name} increases risk (HR={np.exp(coef):.2f})")
            elif coef < -0.1 and val < 0.3:
                factors.append(f"Low {name} increases risk (protective factor missing)")

        return factors[:5] or ["No significant risk factors identified"]

    def _explain_default_prediction(
        self,
        entity_id: str,
        median_days: float,
        risk_score: float,
        risk_factors: list[str],
    ) -> str:
        """Generate Swahili explanation for default prediction."""
        if risk_score < 0.2:
            level = "chini"
            advice = "Mkopo huu ni salama. Endelea kulipa kwa wakati."
        elif risk_score < 0.4:
            level = "ya kati"
            advice = "Kuna hatari kidogo. Hakikisha unalipa kwa wakati."
        elif risk_score < 0.6:
            level = "ya juu"
            advice = "Hatari ni kubwa. Fikiria kupunguza mkopo au kuongeza muda wa kulipa."
        else:
            level = "kubwa sana"
            advice = "Hatari ni kubwa sana. Mkopo huu unaweza kusababisha matatizo."

        return (
            f"Muda wa kukamilisha mkopo: siku {median_days:.0f}. "
            f"Hatari ya kutolipa: {level} ({risk_score*100:.0f}%). "
            f"{advice}"
        )

    def _explain_churn_prediction(
        self,
        entity_id: str,
        median_days: float,
        risk_score: float,
        risk_factors: list[str],
    ) -> str:
        """Generate Swahili explanation for churn prediction."""
        if risk_score < 0.2:
            return "Mfanyakari huyu ataendelea kutumia mfumo. Hatari ya kuondoka ni ndogo."
        elif risk_score < 0.5:
            return (
                f"Mfanyakari huyu anaweza kuondoka baada ya siku {median_days:.0f}. "
                f"Ongeza thamani ya huduma ili kumshikilia."
            )
        else:
            return (
                f"Onyo! Mfanyakari huyu ana hatari kubwa ya kuondoka "
                f"(siku {median_days:.0f}). Fanya haraka kumfikia na kumpa motisha."
            )

    def _simple_logrank(
        self,
        d1: np.ndarray, e1: np.ndarray,
        d2: np.ndarray, e2: np.ndarray,
    ) -> tuple[float, float]:
        """Simplified log-rank test statistic."""
        all_times = np.unique(np.concatenate([d1, d2]))
        O1, E1, V1 = 0.0, 0.0, 0.0

        for t in all_times:
            # At risk in each group
            n1 = np.sum(d1 >= t)
            n2 = np.sum(d2 >= t)
            n = n1 + n2

            # Events at t
            d1_t = np.sum((d1 == t) & (e1 == 1))
            d2_t = np.sum((d2 == t) & (e2 == 1))
            d_t = d1_t + d2_t

            if n > 0:
                e1_t = n1 * d_t / n
                E1 += e1_t
                O1 += d1_t
                if n > 1:
                    V1 += n1 * n2 * d_t * (n - d_t) / (n ** 2 * (n - 1))

        if V1 > 0:
            chi2 = (O1 - E1) ** 2 / V1
            p = 1 - sp_stats.chi2.cdf(chi2, 1)
        else:
            chi2 = 0.0
            p = 1.0

        return float(chi2), float(p)
