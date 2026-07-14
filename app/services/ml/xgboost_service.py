"""
XGBoost Service — ML Prediction Layer for Angavu Intelligence.

Provides four core prediction capabilities powered by XGBoost:
1. Demand Forecasting — predict next week's sales volume
2. Credit Scoring — enhanced Alama Score with XGBoost
3. Churn Prediction — will a worker stop using Msaidizi?
4. Anomaly Detection — unusual transactions flagged in real-time

Each model:
- Uses SHAP for explainable predictions
- Falls back gracefully to classical stats when insufficient data
- Integrates with the existing intelligence pipeline
- Stores model artifacts for versioning and reproducibility

Design Principle: ML models AMPLIFY classical statistics, not replace them.
When ML confidence is low, the system falls back to Holt-Winters, ARIMA,
or other classical methods already validated at A-.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Model storage directory
MODEL_DIR = Path(os.environ.get("ML_MODEL_DIR", "models/xgboost"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Feature names used across all models (consistent ordering)
FEATURE_NAMES = [
    # RFM
    "rfm_recency_days", "rfm_frequency", "rfm_monetary_total",
    "rfm_monetary_avg", "rfm_monetary_std", "rfm_tenure_days", "rfm_txn_per_day",
    # Temporal
    "temporal_dow_entropy", "temporal_peak_dow", "temporal_weekend_ratio",
    "temporal_morning_ratio", "temporal_afternoon_ratio", "temporal_evening_ratio",
    "temporal_hour_entropy", "temporal_days_since_last_active",
    "temporal_active_days_ratio", "temporal_max_gap_days", "temporal_avg_gap_days",
    # Product mix
    "pmix_unique_categories", "pmix_unique_items", "pmix_hhi",
    "pmix_top_category_share", "pmix_avg_item_price", "pmix_price_range",
    "pmix_qty_per_txn", "pmix_profit_margin",
    # Location
    "loc_unique_locations", "loc_primary_location_share",
    "loc_location_entropy", "loc_has_geohash",
    # Derived (7d, 14d, 30d windows)
    "derived_rev_7d", "derived_count_7d", "derived_avg_txn_7d", "derived_volatility_7d",
    "derived_rev_14d", "derived_count_14d", "derived_avg_txn_14d", "derived_volatility_14d",
    "derived_rev_30d", "derived_count_30d", "derived_avg_txn_30d", "derived_volatility_30d",
    "derived_momentum_7_30", "derived_trend_slope",
    # Churn
    "churn_days_since_last_txn", "churn_txn_decline_rate", "churn_rev_decline_rate",
    "churn_short_session_ratio", "churn_record_method_diversity",
    "churn_voice_usage_ratio", "churn_avg_confidence",
]


def _import_xgboost():
    """Lazy import of xgboost with graceful fallback."""
    try:
        import xgboost as xgb
        return xgb
    except ImportError:
        logger.warning("xgboost_not_installed", msg="pip install xgboost")
        return None


def _import_shap():
    """Lazy import of shap with graceful fallback."""
    try:
        import shap
        return shap
    except ImportError:
        logger.warning("shap_not_installed", msg="pip install shap")
        return None


def _import_sklearn():
    """Lazy import of sklearn."""
    try:
        from sklearn.model_selection import cross_val_score, TimeSeriesSplit
        from sklearn.metrics import (
            mean_absolute_error, mean_squared_error, r2_score,
            accuracy_score, precision_score, recall_score, f1_score,
            roc_auc_score, classification_report,
        )
        return {
            "cross_val_score": cross_val_score,
            "TimeSeriesSplit": TimeSeriesSplit,
            "mean_absolute_error": mean_absolute_error,
            "mean_squared_error": mean_squared_error,
            "r2_score": r2_score,
            "accuracy_score": accuracy_score,
            "precision_score": precision_score,
            "recall_score": recall_score,
            "f1_score": f1_score,
            "roc_auc_score": roc_auc_score,
            "classification_report": classification_report,
        }
    except ImportError:
        logger.warning("sklearn_not_installed")
        return None


class XGBoostService:
    """
    ML prediction service powered by XGBoost.

    Provides demand forecasting, credit scoring, churn prediction,
    and anomaly detection — all with SHAP explainability.

    Usage:
        service = XGBoostService()

        # Demand forecast
        forecast = service.predict_demand(features, model_version="latest")

        # Credit score enhancement
        credit = service.predict_credit_score(features, classical_score=650)

        # Churn prediction
        churn = service.predict_churn(features)

        # Anomaly detection
        anomaly = service.detect_anomaly(txn_features, user_id="abc")
    """

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = Path(model_dir) if model_dir else MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._models: Dict[str, Any] = {}  # In-memory model cache

    # ─────────────────────────────────────────────────────────────────────
    # Model Loading
    # ─────────────────────────────────────────────────────────────────────

    def _load_model(self, model_type: str, version: str = "latest") -> Optional[Any]:
        """
        Load a trained XGBoost model from disk.

        Args:
            model_type: One of 'demand', 'credit', 'churn', 'anomaly'
            version: Model version string or 'latest'

        Returns:
            XGBoost Booster or None if not found
        """
        cache_key = f"{model_type}_{version}"
        if cache_key in self._models:
            return self._models[cache_key]

        xgb = _import_xgboost()
        if xgb is None:
            return None

        if version == "latest":
            # Find latest model file
            pattern = f"{model_type}_*.ubj"
            model_files = sorted(self.model_dir.glob(pattern), reverse=True)
            if not model_files:
                logger.info("no_model_found", model_type=model_type)
                return None
            model_path = model_files[0]
        else:
            model_path = self.model_dir / f"{model_type}_{version}.ubj"

        if not model_path.exists():
            logger.info("model_not_found", path=str(model_path))
            return None

        try:
            model = xgb.Booster()
            model.load_model(str(model_path))
            self._models[cache_key] = model
            logger.info("model_loaded", model_type=model_type, version=version, path=str(model_path))
            return model
        except Exception as e:
            logger.error("model_load_failed", model_type=model_type, error=str(e))
            return None

    def _save_model(self, model: Any, model_type: str, version: str, metadata: Dict[str, Any]) -> Path:
        """Save a trained model with metadata."""
        model_path = self.model_dir / f"{model_type}_{version}.ubj"
        model.save_model(str(model_path))

        # Save metadata
        import json
        meta_path = self.model_dir / f"{model_type}_{version}_meta.json"
        meta = {
            "model_type": model_type,
            "version": version,
            "model_file": str(model_path),
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "feature_names": FEATURE_NAMES,
            **metadata,
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        # Update cache
        self._models[f"{model_type}_{version}"] = model

        return model_path

    # ─────────────────────────────────────────────────────────────────────
    # SHAP Explainability
    # ─────────────────────────────────────────────────────────────────────

    def explain_prediction(
        self,
        model: Any,
        features: np.ndarray,
        feature_names: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Generate SHAP explanations for a model prediction.

        Args:
            model: Trained XGBoost model
            features: Feature array (1D for single prediction)
            feature_names: Names for each feature
            top_k: Number of top features to include

        Returns:
            Dict with SHAP values, feature importance, and human-readable explanation
        """
        shap = _import_shap()
        if shap is None:
            return {"available": False, "reason": "shap_not_installed"}

        if feature_names is None:
            feature_names = FEATURE_NAMES

        try:
            xgb = _import_xgboost()
            if xgb is None:
                return {"available": False, "reason": "xgboost_not_installed"}

            # Create DMatrix
            if features.ndim == 1:
                features = features.reshape(1, -1)

            dmatrix = xgb.DMatrix(features, feature_names=feature_names[:features.shape[1]])

            # SHAP TreeExplainer
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(features)

            # Get base value (expected value)
            base_value = float(explainer.expected_value)
            if isinstance(base_value, (list, np.ndarray)):
                base_value = float(base_value[0])

            # Feature contributions
            sv = shap_values[0] if isinstance(shap_values, np.ndarray) else shap_values
            if isinstance(sv, list):
                sv = sv[0]
            sv = np.array(sv).flatten()

            # Top-k features by absolute SHAP value
            abs_sv = np.abs(sv)
            top_indices = np.argsort(abs_sv)[::-1][:top_k]

            contributions = []
            for idx in top_indices:
                if idx < len(feature_names):
                    contributions.append({
                        "feature": feature_names[idx],
                        "shap_value": round(float(sv[idx]), 4),
                        "feature_value": round(float(features[0, idx]), 4) if features.ndim > 1 else round(float(features[idx]), 4),
                        "direction": "increases" if sv[idx] > 0 else "decreases",
                    })

            return {
                "available": True,
                "base_value": round(base_value, 4),
                "prediction_contribution": round(float(np.sum(sv)), 4),
                "top_contributors": contributions,
                "method": "SHAP TreeExplainer (Lundberg & Lee, 2017)",
            }

        except Exception as e:
            logger.warning("shap_explanation_failed", error=str(e))
            return {"available": False, "reason": str(e)}

    # ─────────────────────────────────────────────────────────────────────
    # 1. Demand Forecasting
    # ─────────────────────────────────────────────────────────────────────

    def predict_demand(
        self,
        features: Dict[str, float],
        model_version: str = "latest",
    ) -> Dict[str, Any]:
        """
        Predict next week's sales volume using XGBoost.

        Complements Holt-Winters and ARIMA forecasts from Soko Pulse.
        XGBoost captures non-linear feature interactions that linear
        models miss (e.g., weekend × category × location effects).

        Args:
            features: Feature dict from FeatureEngineer
            model_version: Model version to use

        Returns:
            Dict with prediction, confidence, and SHAP explanation
        """
        model = self._load_model("demand", model_version)

        if model is None:
            return {
                "available": False,
                "method": "xgboost_demand",
                "fallback": "classical_stats",
                "reason": "model_not_trained",
            }

        xgb = _import_xgboost()
        try:
            feature_array, feature_names = self._features_to_array(features)
            dmatrix = xgb.DMatrix(feature_array.reshape(1, -1), feature_names=feature_names)
            prediction = float(model.predict(dmatrix)[0])
            prediction = max(0, prediction)

            # SHAP explanation
            explanation = self.explain_prediction(model, feature_array, feature_names)

            return {
                "available": True,
                "method": "xgboost_demand",
                "predicted_volume": round(prediction, 2),
                "confidence": self._estimate_confidence(features, "demand"),
                "shap_explanation": explanation,
                "model_version": model_version,
            }

        except Exception as e:
            logger.error("demand_prediction_failed", error=str(e))
            return {"available": False, "method": "xgboost_demand", "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────
    # 2. Credit Scoring (Alama Score Enhancement)
    # ─────────────────────────────────────────────────────────────────────

    def predict_credit_score(
        self,
        features: Dict[str, float],
        classical_score: Optional[int] = None,
        model_version: str = "latest",
    ) -> Dict[str, Any]:
        """
        Predict credit risk using XGBoost, enhanced with classical Alama Score.

        XGBoost captures non-linear interactions between behavioral features
        that logistic regression (classical Alama) may miss. The final score
        is a weighted ensemble of classical and ML scores.

        Args:
            features: Feature dict from FeatureEngineer
            classical_score: Existing Alama Score (300-850) for ensemble
            model_version: Model version to use

        Returns:
            Dict with ML credit assessment, default probability, and explanation
        """
        model = self._load_model("credit", model_version)

        if model is None:
            return {
                "available": False,
                "method": "xgboost_credit",
                "fallback": "classical_alama",
                "reason": "model_not_trained",
            }

        xgb = _import_xgboost()
        try:
            feature_array, feature_names = self._features_to_array(features)
            dmatrix = xgb.DMatrix(feature_array.reshape(1, -1), feature_names=feature_names)
            raw_prediction = float(model.predict(dmatrix)[0])

            # XGBoost predicts default probability (0-1)
            default_prob = float(np.clip(raw_prediction, 0, 1))

            # Convert to Alama-style score (300-850)
            ml_score = int(300 + (1 - default_prob) * 550)
            ml_score = max(300, min(850, ml_score))

            # Ensemble with classical score
            if classical_score is not None:
                # Weighted ensemble: 60% ML, 40% classical (ML has more features)
                ensemble_score = int(0.6 * ml_score + 0.4 * classical_score)
                ensemble_score = max(300, min(850, ensemble_score))
            else:
                ensemble_score = ml_score

            # Score band
            if ensemble_score >= 750:
                band = "excellent"
            elif ensemble_score >= 650:
                band = "good"
            elif ensemble_score >= 550:
                band = "fair"
            elif ensemble_score >= 450:
                band = "poor"
            else:
                band = "very_poor"

            # SHAP explanation
            explanation = self.explain_prediction(model, feature_array, feature_names)

            return {
                "available": True,
                "method": "xgboost_credit",
                "ml_score": ml_score,
                "ensemble_score": ensemble_score,
                "classical_score": classical_score,
                "score_band": band,
                "default_probability": round(default_prob, 4),
                "confidence": self._estimate_confidence(features, "credit"),
                "shap_explanation": explanation,
                "model_version": model_version,
                "ensemble_weights": {"ml": 0.6, "classical": 0.4} if classical_score else None,
            }

        except Exception as e:
            logger.error("credit_prediction_failed", error=str(e))
            return {"available": False, "method": "xgboost_credit", "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────
    # 3. Churn Prediction
    # ─────────────────────────────────────────────────────────────────────

    def predict_churn(
        self,
        features: Dict[str, float],
        model_version: str = "latest",
    ) -> Dict[str, Any]:
        """
        Predict whether a worker will stop using Msaidizi.

        XGBoost captures complex behavioral patterns:
        - Declining transaction frequency + voice-only usage = high churn risk
        - Weekend-only activity + short sessions = moderate risk
        - Consistent multi-channel usage = low risk

        Args:
            features: Feature dict from FeatureEngineer
            model_version: Model version to use

        Returns:
            Dict with churn probability, risk level, and key drivers
        """
        model = self._load_model("churn", model_version)

        if model is None:
            return {
                "available": False,
                "method": "xgboost_churn",
                "fallback": "rule_based",
                "reason": "model_not_trained",
            }

        xgb = _import_xgboost()
        try:
            feature_array, feature_names = self._features_to_array(features)
            dmatrix = xgb.DMatrix(feature_array.reshape(1, -1), feature_names=feature_names)
            raw_prediction = float(model.predict(dmatrix)[0])
            churn_prob = float(np.clip(raw_prediction, 0, 1))

            # Risk level
            if churn_prob >= 0.7:
                risk_level = "critical"
            elif churn_prob >= 0.5:
                risk_level = "high"
            elif churn_prob >= 0.3:
                risk_level = "medium"
            else:
                risk_level = "low"

            # SHAP explanation
            explanation = self.explain_prediction(model, feature_array, feature_names)

            # Identify top churn drivers
            drivers = []
            if explanation.get("available"):
                for contrib in explanation.get("top_contributors", [])[:5]:
                    if contrib["shap_value"] > 0:  # Positive SHAP = increases churn
                        drivers.append({
                            "factor": contrib["feature"],
                            "impact": contrib["shap_value"],
                            "value": contrib["feature_value"],
                        })

            return {
                "available": True,
                "method": "xgboost_churn",
                "churn_probability": round(churn_prob, 4),
                "risk_level": risk_level,
                "confidence": self._estimate_confidence(features, "churn"),
                "top_drivers": drivers,
                "shap_explanation": explanation,
                "model_version": model_version,
            }

        except Exception as e:
            logger.error("churn_prediction_failed", error=str(e))
            return {"available": False, "method": "xgboost_churn", "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────
    # 4. Anomaly Detection
    # ─────────────────────────────────────────────────────────────────────

    def detect_anomaly(
        self,
        transaction_features: Dict[str, float],
        model_version: str = "latest",
    ) -> Dict[str, Any]:
        """
        Detect if a transaction is anomalous using XGBoost.

        XGBoost learns complex decision boundaries for "normal" vs
        "anomalous" transactions. Outperforms simple z-score detection
        by capturing feature interactions.

        Args:
            transaction_features: Features for this specific transaction
            model_version: Model version to use

        Returns:
            Dict with anomaly score, classification, and explanation
        """
        model = self._load_model("anomaly", model_version)

        if model is None:
            # Fallback: z-score based detection
            return self._zscore_anomaly_fallback(transaction_features)

        xgb = _import_xgboost()
        try:
            # Anomaly features have different structure
            feature_names = sorted(transaction_features.keys())
            feature_array = np.array(
                [transaction_features.get(k, 0.0) for k in feature_names],
                dtype=np.float32,
            )
            dmatrix = xgb.DMatrix(feature_array.reshape(1, -1), feature_names=feature_names)
            raw_score = float(model.predict(dmatrix)[0])
            anomaly_prob = float(np.clip(raw_score, 0, 1))

            is_anomalous = anomaly_prob > 0.5

            # SHAP explanation
            explanation = self.explain_prediction(model, feature_array, feature_names, top_k=5)

            return {
                "available": True,
                "method": "xgboost_anomaly",
                "anomaly_probability": round(anomaly_prob, 4),
                "is_anomalous": is_anomalous,
                "severity": "high" if anomaly_prob > 0.8 else "medium" if anomaly_prob > 0.5 else "low",
                "confidence": 0.85,
                "shap_explanation": explanation,
                "model_version": model_version,
            }

        except Exception as e:
            logger.error("anomaly_detection_failed", error=str(e))
            return self._zscore_anomaly_fallback(transaction_features)

    def _zscore_anomaly_fallback(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Z-score fallback when XGBoost model is not available."""
        amount = features.get("txn_amount", 0)
        mean = features.get("anomaly_hist_mean_amount", 0)
        std = features.get("anomaly_hist_std_amount", 0)

        if std > 0:
            zscore = abs((amount - mean) / std)
        else:
            zscore = 0.0

        is_anomalous = zscore > 3.0

        return {
            "available": True,
            "method": "zscore_fallback",
            "anomaly_probability": round(min(1.0, zscore / 5.0), 4),
            "is_anomalous": is_anomalous,
            "severity": "high" if zscore > 4 else "medium" if zscore > 3 else "low",
            "zscore": round(zscore, 2),
            "confidence": 0.6,
            "note": "Fallback to z-score — train XGBoost model for better accuracy",
        }

    # ─────────────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────────────

    def _features_to_array(
        self, features: Dict[str, float]
    ) -> Tuple[np.ndarray, List[str]]:
        """Convert features dict to ordered numpy array."""
        values = [features.get(k, 0.0) for k in FEATURE_NAMES]
        return np.array(values, dtype=np.float32), FEATURE_NAMES

    @staticmethod
    def _estimate_confidence(features: Dict[str, float], model_type: str) -> float:
        """
        Estimate prediction confidence based on data completeness.

        More data = higher confidence. Sparse data = lower confidence
        (signals fallback to classical stats may be needed).
        """
        # Count non-zero features as proxy for data quality
        non_zero = sum(1 for v in features.values() if v != 0.0)
        total = max(len(features), 1)

        completeness = non_zero / total

        # Data volume signal
        txn_count = features.get("rfm_frequency", 0)
        if txn_count >= 100:
            volume_score = 1.0
        elif txn_count >= 30:
            volume_score = 0.8
        elif txn_count >= 10:
            volume_score = 0.5
        else:
            volume_score = 0.2

        confidence = 0.5 * completeness + 0.5 * volume_score
        return round(min(0.95, max(0.1, confidence)), 2)

    def get_model_info(self, model_type: str) -> Dict[str, Any]:
        """Get information about a stored model."""
        import json

        pattern = f"{model_type}_*_meta.json"
        meta_files = sorted(self.model_dir.glob(pattern), reverse=True)

        if not meta_files:
            return {"model_type": model_type, "status": "not_trained"}

        with open(meta_files[0]) as f:
            meta = json.load(f)

        return {
            "model_type": model_type,
            "status": "available",
            **meta,
        }

    def list_models(self) -> Dict[str, Any]:
        """List all available models."""
        model_types = ["demand", "credit", "churn", "anomaly"]
        return {mt: self.get_model_info(mt) for mt in model_types}
