"""
Tests for the ML Layer — XGBoost integration.

Tests cover:
- Feature engineering (RFM, temporal, product mix, location, derived, churn)
- XGBoost service (demand, credit, churn, anomaly — with and without models)
- Model trainer (data preparation, label generation)
- ProactiveAlertEngine (alert generation)
- SHAP explainability
- Integration with classical stats (fallback behavior)
"""

import sys
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Set required env vars before any app imports
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-32chars"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-unit-tests-32b!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-unit-tests-32chars"
os.environ["APP_ENV"] = "development"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — Mock Transaction Data
# ─────────────────────────────────────────────────────────────────────────────


def _make_transaction(
    amount: float = 1000.0,
    txn_type: str = "SALE",
    item: str = "sugar",
    category: str = "food",
    quantity: float = 5.0,
    unit_price: float = 200.0,
    hours_ago: int = 0,
    user_id: str = None,
    location: str = "ke0v1",
    recorded_via: str = "text",
    confidence: float = 1.0,
    mpesa: bool = False,
    profit: float = None,
):
    """Create a mock transaction object."""
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        transaction_type=txn_type,
        item=item,
        item_category=category,
        quantity=quantity,
        unit="pieces",
        unit_price=unit_price,
        amount=amount,
        profit=profit,
        payment_method="mpesa" if mpesa else "cash",
        mpesa_receipt="QKH123ABC" if mpesa else None,
        recorded_via=recorded_via,
        confidence_score=confidence,
        timestamp=ts,
        location_geohash=location,
    )


def _make_transactions(n: int = 50, user_id: str = None) -> list:
    """Create a list of realistic mock transactions."""
    uid = user_id or str(uuid.uuid4())
    txns = []
    categories = ["food", "household", "health", "beauty"]
    items = {"food": ["sugar", "flour", "cooking_oil"], "household": ["soap", "detergent"],
             "health": ["paracetamol"], "beauty": ["lotion"]}

    for i in range(n):
        cat = categories[i % len(categories)]
        item_list = items.get(cat, ["generic"])
        item = item_list[i % len(item_list)]
        amount = 500 + np.random.normal(0, 100)
        amount = max(50, amount)

        txns.append(_make_transaction(
            amount=amount,
            txn_type="SALE" if i % 5 != 0 else "PURCHASE",
            item=item,
            category=cat,
            quantity=float(1 + i % 10),
            unit_price=amount / max(1 + i % 10, 1),
            hours_ago=i * 6,  # Every 6 hours
            user_id=uid,
            recorded_via="voice" if i % 3 == 0 else "text",
            mpesa=i % 4 == 0,
            profit=amount * 0.2 if i % 5 != 0 else None,
        ))

    return txns


# ─────────────────────────────────────────────────────────────────────────────
# Test Feature Engineering
# ─────────────────────────────────────────────────────────────────────────────


class TestFeatureEngineer:
    """Tests for FeatureEngineer."""

    def test_rfm_features_with_data(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(30)
        features = FeatureEngineer.rfm_features(txns)

        assert "rfm_recency_days" in features
        assert "rfm_frequency" in features
        assert "rfm_monetary_total" in features
        assert "rfm_monetary_avg" in features
        assert features["rfm_frequency"] > 0
        assert features["rfm_monetary_total"] > 0

    def test_rfm_features_empty(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        features = FeatureEngineer.rfm_features([])
        assert features["rfm_recency_days"] == 999.0
        assert features["rfm_frequency"] == 0.0

    def test_temporal_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(30)
        features = FeatureEngineer.temporal_features(txns)

        assert "temporal_dow_entropy" in features
        assert "temporal_weekend_ratio" in features
        assert "temporal_active_days_ratio" in features
        assert 0 <= features["temporal_weekend_ratio"] <= 1

    def test_product_mix_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(30)
        features = FeatureEngineer.product_mix_features(txns)

        assert "pmix_unique_categories" in features
        assert "pmix_hhi" in features
        assert features["pmix_unique_categories"] > 0
        assert 0 < features["pmix_hhi"] <= 1

    def test_location_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(30)
        features = FeatureEngineer.location_features(txns)

        assert "loc_unique_locations" in features
        assert "loc_has_geohash" in features

    def test_derived_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(30)
        features = FeatureEngineer.derived_features(txns)

        assert "derived_rev_7d" in features
        assert "derived_rev_30d" in features
        assert "derived_momentum_7_30" in features
        assert "derived_trend_slope" in features

    def test_churn_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(30)
        features = FeatureEngineer.churn_features(txns)

        assert "churn_days_since_last_txn" in features
        assert "churn_txn_decline_rate" in features
        assert "churn_voice_usage_ratio" in features

    def test_anomaly_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(30)
        features = FeatureEngineer.anomaly_features(txns)

        assert "anomaly_hist_mean_amount" in features
        assert "anomaly_hist_std_amount" in features

    def test_extract_all_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(50)
        features = FeatureEngineer.extract_all_features(txns)

        assert len(features) >= 40  # Should have 50+ features
        assert "rfm_recency_days" in features
        assert "temporal_dow_entropy" in features
        assert "pmix_hhi" in features
        assert "derived_trend_slope" in features

    def test_extract_transaction_features(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(20)
        target_txn = txns[0]
        features = FeatureEngineer.extract_transaction_features(target_txn, txns)

        assert "txn_amount" in features
        assert "txn_hour" in features
        assert "txn_dow" in features
        assert "txn_amount_zscore" in features
        assert "anomaly_hist_mean_amount" in features

    def test_features_to_array(self):
        from app.services.ml.feature_engineering import FeatureEngineer

        features = {"a": 1.0, "b": 2.0, "c": 3.0}
        arr, names = FeatureEngineer.features_to_array(features)

        assert isinstance(arr, np.ndarray)
        assert len(arr) == 3
        assert names == ["a", "b", "c"]


# ─────────────────────────────────────────────────────────────────────────────
# Test XGBoost Service
# ─────────────────────────────────────────────────────────────────────────────


class TestXGBoostService:
    """Tests for XGBoostService."""

    def test_service_initialization(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        assert service.model_dir.exists()

    def test_demand_prediction_no_model(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        result = service.predict_demand({"rfm_frequency": 10})

        assert result["available"] is False
        assert result["fallback"] == "classical_stats"

    def test_credit_prediction_no_model(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        result = service.predict_credit_score(
            {"rfm_frequency": 10}, classical_score=650
        )

        assert result["available"] is False
        assert result["fallback"] == "classical_alama"

    def test_churn_prediction_no_model(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        result = service.predict_churn({"churn_days_since_last_txn": 5})

        assert result["available"] is False
        assert result["fallback"] == "rule_based"

    def test_anomaly_zscore_fallback(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        result = service.detect_anomaly({
            "txn_amount": 5000,
            "anomaly_hist_mean_amount": 1000,
            "anomaly_hist_std_amount": 200,
        })

        assert result["available"] is True
        assert result["method"] == "zscore_fallback"
        assert result["is_anomalous"] is True  # z-score = 20, well above 3

    def test_anomaly_zscore_normal(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        result = service.detect_anomaly({
            "txn_amount": 1100,
            "anomaly_hist_mean_amount": 1000,
            "anomaly_hist_std_amount": 200,
        })

        assert result["available"] is True
        assert result["is_anomalous"] is False  # z-score = 0.5

    def test_confidence_estimation(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)

        # High data → high confidence
        features_high = {f"feat_{i}": float(i) for i in range(50)}
        features_high["rfm_frequency"] = 100
        conf_high = service._estimate_confidence(features_high, "demand")

        # Low data → low confidence
        features_low = {f"feat_{i}": 0.0 for i in range(50)}
        features_low["rfm_frequency"] = 2
        conf_low = service._estimate_confidence(features_low, "demand")

        assert conf_high > conf_low

    def test_list_models_empty(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        models = service.list_models()

        assert models["demand"]["status"] == "not_trained"
        assert models["credit"]["status"] == "not_trained"

    def test_model_info_no_model(self, tmp_path):
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)
        info = service.get_model_info("demand")

        assert info["status"] == "not_trained"


# ─────────────────────────────────────────────────────────────────────────────
# Test Model Trainer
# ─────────────────────────────────────────────────────────────────────────────


class TestModelTrainer:
    """Tests for ModelTrainer data preparation."""

    def test_prepare_features(self, tmp_path):
        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)
        uid = str(uuid.uuid4())
        txns_by_user = {uid: _make_transactions(30, user_id=uid)}

        X, names, user_ids = trainer.prepare_features(txns_by_user)

        assert len(X) == 1
        assert len(names) > 40
        assert user_ids == [uid]

    def test_prepare_features_insufficient(self, tmp_path):
        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)
        uid = str(uuid.uuid4())
        txns_by_user = {uid: _make_transactions(3, user_id=uid)}  # Too few

        X, names, user_ids = trainer.prepare_features(txns_by_user)
        assert len(X) == 0  # Filtered out

    def test_prepare_demand_targets(self, tmp_path):
        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)
        uid = str(uuid.uuid4())
        txns_by_user = {uid: _make_transactions(30, user_id=uid)}

        y = trainer.prepare_demand_targets(txns_by_user)
        assert len(y) == 1
        assert y[0] >= 0

    def test_prepare_churn_targets(self, tmp_path):
        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)
        uid = str(uuid.uuid4())
        txns_by_user = {uid: _make_transactions(30, user_id=uid)}

        y = trainer.prepare_churn_targets(txns_by_user, inactive_days=30)
        assert len(y) == 1
        assert y[0] in [0, 1]

    def test_generate_credit_labels(self, tmp_path):
        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)
        uid = str(uuid.uuid4())
        txns_by_user = {uid: _make_transactions(30, user_id=uid)}

        y = trainer._generate_credit_labels(txns_by_user, [uid])
        assert len(y) == 1
        assert y[0] in [0, 1]

    def test_next_version(self, tmp_path):
        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)
        v = trainer._next_version("demand")
        assert v == "v1"


# ─────────────────────────────────────────────────────────────────────────────
# Test Proactive Alert Engine
# ─────────────────────────────────────────────────────────────────────────────


class TestProactiveAlertEngine:
    """Tests for ProactiveAlertEngine."""

    @pytest.mark.asyncio
    async def test_generate_alerts_no_ml(self, tmp_path):
        """Alerts gracefully degrade when ML models aren't trained."""
        from app.services.intelligence.proactive_alerts import ProactiveAlertEngine

        engine = ProactiveAlertEngine()
        txns = _make_transactions(30)

        # Should not crash even without trained models
        alerts = await engine.generate_alerts("worker-1", txns)
        assert isinstance(alerts, list)

    @pytest.mark.asyncio
    async def test_generate_alerts_insufficient_data(self):
        """No alerts when insufficient transaction data."""
        from app.services.intelligence.proactive_alerts import ProactiveAlertEngine

        engine = ProactiveAlertEngine()
        alerts = await engine.generate_alerts("worker-1", _make_transactions(3))
        assert alerts == []

    @pytest.mark.asyncio
    async def test_check_demand_alerts(self):
        """Demand alerts return a list."""
        from app.services.intelligence.proactive_alerts import ProactiveAlertEngine

        engine = ProactiveAlertEngine()
        alerts = await engine.check_demand_alerts("food", "Nairobi")
        assert isinstance(alerts, list)

    def test_alert_to_dict(self):
        from app.services.intelligence.proactive_alerts import (
            ProactiveAlert, AlertType, AlertSeverity,
        )

        alert = ProactiveAlert(
            alert_type=AlertType.DEMAND_SPIKE,
            severity=AlertSeverity.INFO,
            title="Test",
            message="Test message",
            confidence=0.8,
        )
        d = alert.to_dict()

        assert d["alert_type"] == "demand_spike"
        assert d["severity"] == "info"
        assert d["confidence"] == 0.8
        assert "created_at" in d


# ─────────────────────────────────────────────────────────────────────────────
# Test Integration — XGBoost with Classical Stats
# ─────────────────────────────────────────────────────────────────────────────


class TestMLClassicalIntegration:
    """Tests that ML and classical stats coexist."""

    def test_ml_features_compatible_with_classical(self):
        """ML features are derived from the same transaction data as classical stats."""
        from app.services.ml.feature_engineering import FeatureEngineer

        txns = _make_transactions(50)
        features = FeatureEngineer.extract_all_features(txns)

        # RFM features should be consistent with classical statistics
        assert features["rfm_monetary_avg"] > 0
        assert features["rfm_frequency"] > 0

        # Temporal features should reflect actual transaction patterns
        assert 0 <= features["temporal_active_days_ratio"] <= 1

    def test_ml_fallback_when_no_model(self, tmp_path):
        """When no ML model exists, service returns fallback signal."""
        from app.services.ml.xgboost_service import XGBoostService
        from app.services.ml.feature_engineering import FeatureEngineer

        service = XGBoostService(model_dir=tmp_path)
        features = FeatureEngineer.extract_all_features(_make_transactions(30))

        demand = service.predict_demand(features)
        assert demand["available"] is False
        assert demand["fallback"] == "classical_stats"

        credit = service.predict_credit_score(features)
        assert credit["available"] is False
        assert credit["fallback"] == "classical_alama"

    def test_zscore_anomaly_fallback_works(self, tmp_path):
        """Z-score fallback works when XGBoost anomaly model isn't trained."""
        from app.services.ml.xgboost_service import XGBoostService

        service = XGBoostService(model_dir=tmp_path)

        # Normal transaction
        normal = service.detect_anomaly({
            "txn_amount": 1050,
            "anomaly_hist_mean_amount": 1000,
            "anomaly_hist_std_amount": 100,
        })
        assert normal["is_anomalous"] is False

        # Anomalous transaction (z-score = 10)
        anomaly = service.detect_anomaly({
            "txn_amount": 2000,
            "anomaly_hist_mean_amount": 1000,
            "anomaly_hist_std_amount": 100,
        })
        assert anomaly["is_anomalous"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test XGBoost Training (requires xgboost installed)
# ─────────────────────────────────────────────────────────────────────────────


class TestXGBoostTraining:
    """Integration tests for XGBoost model training. Skipped if xgboost not installed."""

    def _check_xgboost(self):
        try:
            import xgboost
            return True
        except ImportError:
            return False

    def test_train_demand_model(self, tmp_path):
        if not self._check_xgboost():
            pytest.skip("xgboost not installed")

        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)

        # Create enough data for training
        txns_by_user = {}
        for i in range(30):
            uid = str(uuid.uuid4())
            txns_by_user[uid] = _make_transactions(40, user_id=uid)

        result = trainer.train_demand_model(txns_by_user)

        assert result["status"] == "success"
        assert result["model_type"] == "demand"
        assert "metrics" in result
        assert "mae" in result["metrics"]
        assert "r2" in result["metrics"]
        assert "feature_importance" in result
        assert len(result["feature_importance"]) > 0

    def test_train_credit_model(self, tmp_path):
        if not self._check_xgboost():
            pytest.skip("xgboost not installed")

        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)

        txns_by_user = {}
        for i in range(30):
            uid = str(uuid.uuid4())
            txns_by_user[uid] = _make_transactions(40, user_id=uid)

        result = trainer.train_credit_model(txns_by_user)

        assert result["status"] == "success"
        assert result["model_type"] == "credit"
        assert "metrics" in result
        assert "auc" in result["metrics"]
        assert "f1" in result["metrics"]

    def test_train_churn_model(self, tmp_path):
        if not self._check_xgboost():
            pytest.skip("xgboost not installed")

        from app.services.ml.model_trainer import ModelTrainer

        trainer = ModelTrainer(model_dir=tmp_path)

        txns_by_user = {}
        for i in range(30):
            uid = str(uuid.uuid4())
            txns_by_user[uid] = _make_transactions(40, user_id=uid)

        result = trainer.train_churn_model(txns_by_user)

        assert result["status"] == "success"
        assert result["model_type"] == "churn"

    def test_trained_model_can_predict(self, tmp_path):
        if not self._check_xgboost():
            pytest.skip("xgboost not installed")

        from app.services.ml.model_trainer import ModelTrainer
        from app.services.ml.xgboost_service import XGBoostService
        from app.services.ml.feature_engineering import FeatureEngineer

        trainer = ModelTrainer(model_dir=tmp_path)

        txns_by_user = {}
        for i in range(30):
            uid = str(uuid.uuid4())
            txns_by_user[uid] = _make_transactions(40, user_id=uid)

        # Train
        train_result = trainer.train_demand_model(txns_by_user)
        assert train_result["status"] == "success"

        # Predict
        service = XGBoostService(model_dir=tmp_path)
        features = FeatureEngineer.extract_all_features(_make_transactions(30))
        prediction = service.predict_demand(features)

        assert prediction["available"] is True
        assert prediction["predicted_volume"] >= 0
        assert prediction["confidence"] > 0
        assert prediction["shap_explanation"]["available"] is True

    def test_shap_explainability(self, tmp_path):
        if not self._check_xgboost():
            pytest.skip("xgboost not installed")

        from app.services.ml.model_trainer import ModelTrainer
        from app.services.ml.xgboost_service import XGBoostService
        from app.services.ml.feature_engineering import FeatureEngineer

        trainer = ModelTrainer(model_dir=tmp_path)

        txns_by_user = {}
        for i in range(30):
            uid = str(uuid.uuid4())
            txns_by_user[uid] = _make_transactions(40, user_id=uid)

        trainer.train_demand_model(txns_by_user)

        service = XGBoostService(model_dir=tmp_path)
        features = FeatureEngineer.extract_all_features(_make_transactions(30))
        prediction = service.predict_demand(features)

        shap = prediction.get("shap_explanation", {})
        assert shap.get("available") is True
        assert "top_contributors" in shap
        assert len(shap["top_contributors"]) > 0
        assert "base_value" in shap
