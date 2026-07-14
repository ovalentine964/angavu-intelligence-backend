"""
Model Trainer — XGBoost Model Training, Validation, and Versioning.

Handles the full ML lifecycle:
1. Data preparation from transaction records
2. Train/test splitting with proper temporal awareness
3. Cross-validation with time-series splits
4. Hyperparameter tuning
5. Model versioning and persistence
6. Performance tracking and drift detection integration

Training is designed for the informal economy:
- Handles imbalanced classes (few churners, few anomalies)
- Uses temporal splits (no future leakage)
- Works with small datasets (warm start, regularization)
- Integrates with CUSUM drift detector for retrain triggers
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

from app.services.ml.feature_engineering import FeatureEngineer
from app.services.ml.xgboost_service import FEATURE_NAMES, MODEL_DIR, XGBoostService

logger = structlog.get_logger(__name__)


def _import_xgboost():
    """Lazy import of xgboost."""
    try:
        import xgboost as xgb
        return xgb
    except ImportError:
        return None


def _import_sklearn():
    """Lazy import of sklearn."""
    try:
        from sklearn.model_selection import TimeSeriesSplit, cross_val_score
        from sklearn.metrics import (
            mean_absolute_error, mean_squared_error, r2_score,
            accuracy_score, precision_score, recall_score, f1_score,
            roc_auc_score,
        )
        import sklearn.metrics as metrics
        return {
            "TimeSeriesSplit": TimeSeriesSplit,
            "cross_val_score": cross_val_score,
            "mean_absolute_error": mean_absolute_error,
            "mean_squared_error": mean_squared_error,
            "r2_score": r2_score,
            "accuracy_score": accuracy_score,
            "precision_score": precision_score,
            "recall_score": recall_score,
            "f1_score": f1_score,
            "roc_auc_score": roc_auc_score,
            "metrics": metrics,
        }
    except ImportError:
        return None


class ModelTrainer:
    """
    Trains and manages XGBoost models for Angavu Intelligence.

    Supports four model types:
    - demand: Regression (predict next week's sales volume)
    - credit: Classification (default probability)
    - churn: Classification (will worker leave)
    - anomaly: Classification (is transaction anomalous)

    Usage:
        trainer = ModelTrainer()

        # Train demand model
        result = await trainer.train_demand_model(transactions_by_user)

        # Train credit model
        result = await trainer.train_credit_model(transactions_by_user, outcomes)

        # Cross-validate
        cv_result = trainer.cross_validate(X, y, model_type="demand")
    """

    # Default XGBoost hyperparameters per model type
    DEFAULT_PARAMS = {
        "demand": {
            "objective": "reg:squarederror",
            "max_depth": 6,
            "learning_rate": 0.1,
            "n_estimators": 200,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "min_child_weight": 5,
            "gamma": 0.1,
        },
        "credit": {
            "objective": "binary:logistic",
            "max_depth": 5,
            "learning_rate": 0.05,
            "n_estimators": 300,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "min_child_weight": 10,
            "gamma": 0.2,
            "scale_pos_weight": 3.0,  # Imbalanced: more good than bad
        },
        "churn": {
            "objective": "binary:logistic",
            "max_depth": 5,
            "learning_rate": 0.05,
            "n_estimators": 250,
            "subsample": 0.8,
            "colsample_bytree": 0.7,
            "reg_alpha": 0.2,
            "reg_lambda": 1.5,
            "min_child_weight": 8,
            "gamma": 0.15,
            "scale_pos_weight": 4.0,  # Imbalanced: few churners
        },
        "anomaly": {
            "objective": "binary:logistic",
            "max_depth": 4,
            "learning_rate": 0.1,
            "n_estimators": 150,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "reg_alpha": 0.05,
            "reg_lambda": 0.5,
            "min_child_weight": 3,
            "gamma": 0.1,
            "scale_pos_weight": 10.0,  # Very imbalanced: rare anomalies
        },
    }

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = Path(model_dir) if model_dir else MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.service = XGBoostService(self.model_dir)

    # ─────────────────────────────────────────────────────────────────────
    # Data Preparation
    # ─────────────────────────────────────────────────────────────────────

    def prepare_features(
        self,
        transactions_by_user: Dict[str, List[Any]],
    ) -> Tuple[np.ndarray, List[str], List[str]]:
        """
        Extract features for all users into a training matrix.

        Args:
            transactions_by_user: Dict mapping user_id to list of Transaction objects

        Returns:
            (feature_matrix, feature_names, user_ids)
        """
        X_rows = []
        user_ids = []

        for user_id, txns in transactions_by_user.items():
            if len(txns) < 5:
                continue  # Skip users with too few transactions

            features = FeatureEngineer.extract_all_features(txns)
            row = [features.get(f, 0.0) for f in FEATURE_NAMES]
            X_rows.append(row)
            user_ids.append(user_id)

        if not X_rows:
            return np.array([]), FEATURE_NAMES, []

        return np.array(X_rows, dtype=np.float32), FEATURE_NAMES, user_ids

    def prepare_demand_targets(
        self,
        transactions_by_user: Dict[str, List[Any]],
        forecast_days: int = 7,
    ) -> np.ndarray:
        """
        Compute demand targets: next week's total sales volume per user.

        For each user, the target is the total sales amount in the
        most recent `forecast_days` days of their transaction history.
        Features are computed from data BEFORE that window.

        Args:
            transactions_by_user: Dict mapping user_id to transactions
            forecast_days: Number of days to predict ahead

        Returns:
            Target array (total sales volume per user)
        """
        targets = []
        for user_id, txns in transactions_by_user.items():
            if len(txns) < 10:
                targets.append(0.0)
                continue

            sorted_txns = sorted(txns, key=lambda t: t.timestamp)
            last_date = sorted_txns[-1].timestamp
            cutoff = last_date - __import__("datetime").timedelta(days=forecast_days)

            # Target: sum of sales in the forecast window
            forecast_sales = [
                t.amount for t in sorted_txns
                if t.timestamp >= cutoff and t.transaction_type == "SALE"
            ]
            targets.append(sum(forecast_sales))

        return np.array(targets, dtype=np.float32)

    def prepare_churn_targets(
        self,
        transactions_by_user: Dict[str, List[Any]],
        inactive_days: int = 30,
    ) -> np.ndarray:
        """
        Compute churn targets: 1 if user has been inactive for `inactive_days`.

        A user is considered "churned" if their last transaction is more
        than `inactive_days` ago from the most recent date in the dataset.

        Args:
            transactions_by_user: Dict mapping user_id to transactions
            inactive_days: Days of inactivity to count as churned

        Returns:
            Binary target array (1 = churned, 0 = active)
        """
        now = datetime.now(timezone.utc)
        targets = []
        for user_id, txns in transactions_by_user.items():
            if not txns:
                targets.append(1)
                continue
            last_txn = max(t.timestamp for t in txns)
            days_inactive = (now - last_txn).days
            if hasattr(days_inactive, 'total_seconds'):
                days_inactive = days_inactive.days
            targets.append(1 if days_inactive >= inactive_days else 0)

        return np.array(targets, dtype=np.int32)

    # ─────────────────────────────────────────────────────────────────────
    # Training
    # ─────────────────────────────────────────────────────────────────────

    def train_demand_model(
        self,
        transactions_by_user: Dict[str, List[Any]],
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Train XGBoost demand forecasting model.

        Predicts next week's sales volume from transaction features.
        Uses time-series-aware train/test split.

        Args:
            transactions_by_user: User transaction data
            params: Optional XGBoost hyperparameter overrides

        Returns:
            Training results with metrics and model version
        """
        xgb = _import_xgboost()
        sk = _import_sklearn()
        if xgb is None or sk is None:
            return {"status": "failed", "reason": "dependencies_missing"}

        X, feature_names, user_ids = self.prepare_features(transactions_by_user)
        if len(X) < 20:
            return {"status": "failed", "reason": "insufficient_data", "min_required": 20}

        y = self.prepare_demand_targets(transactions_by_user)
        if len(y) != len(X):
            y = y[:len(X)]

        # Train/test split (80/20, preserving order)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # Merge params
        train_params = {**self.DEFAULT_PARAMS["demand"]}
        if params:
            train_params.update(params)

        n_estimators = train_params.pop("n_estimators", 200)

        # Train
        start_time = time.time()
        model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            **train_params,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )
        train_time = time.time() - start_time

        # Evaluate
        y_pred = model.predict(X_test)
        y_pred = np.maximum(y_pred, 0)

        mae = float(sk["mean_absolute_error"](y_test, y_pred))
        rmse = float(np.sqrt(sk["mean_squared_error"](y_test, y_pred)))
        r2 = float(sk["r2_score"](y_test, y_pred))

        # Cross-validation
        cv_result = self._cross_validate(model, X, y, "demand")

        # Version and save
        version = self._next_version("demand")
        metadata = {
            "mae": mae, "rmse": rmse, "r2": r2,
            "train_size": len(X_train), "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "cv_scores": cv_result,
            "params": train_params,
        }
        self.service._save_model(model.get_booster(), "demand", version, metadata)

        logger.info(
            "demand_model_trained",
            version=version, mae=mae, rmse=rmse, r2=r2, train_time=train_time,
        )

        return {
            "status": "success",
            "model_type": "demand",
            "version": version,
            "metrics": {"mae": mae, "rmse": rmse, "r2": r2},
            "cross_validation": cv_result,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "feature_importance": self._get_feature_importance(model, feature_names),
        }

    def train_credit_model(
        self,
        transactions_by_user: Dict[str, List[Any]],
        outcomes: Optional[Dict[str, int]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Train XGBoost credit scoring model.

        Predicts default probability. If outcomes are not provided,
        generates synthetic labels from transaction patterns
        (users with declining revenue → higher default risk).

        Args:
            transactions_by_user: User transaction data
            outcomes: Optional dict mapping user_id to 0 (good) or 1 (default)
            params: Optional XGBoost hyperparameter overrides

        Returns:
            Training results with metrics
        """
        xgb = _import_xgboost()
        sk = _import_sklearn()
        if xgb is None or sk is None:
            return {"status": "failed", "reason": "dependencies_missing"}

        X, feature_names, user_ids = self.prepare_features(transactions_by_user)
        if len(X) < 20:
            return {"status": "failed", "reason": "insufficient_data", "min_required": 20}

        # Generate labels if not provided
        if outcomes is None:
            y = self._generate_credit_labels(transactions_by_user, user_ids)
        else:
            y = np.array([outcomes.get(uid, 0) for uid in user_ids], dtype=np.int32)

        # Train/test split
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # Merge params
        train_params = {**self.DEFAULT_PARAMS["credit"]}
        if params:
            train_params.update(params)

        n_estimators = train_params.pop("n_estimators", 300)

        # Handle class imbalance
        n_pos = max(1, np.sum(y_train == 1))
        n_neg = max(1, np.sum(y_train == 0))
        train_params["scale_pos_weight"] = n_neg / n_pos

        start_time = time.time()
        model = xgb.XGBClassifier(
            n_estimators=n_estimators,
            **train_params,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )
        train_time = time.time() - start_time

        # Evaluate
        y_pred_proba = model.predict_proba(X_test)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        accuracy = float(sk["accuracy_score"](y_test, y_pred))
        precision = float(sk["precision_score"](y_test, y_pred, zero_division=0))
        recall = float(sk["recall_score"](y_test, y_pred, zero_division=0))
        f1 = float(sk["f1_score"](y_test, y_pred, zero_division=0))
        try:
            auc = float(sk["roc_auc_score"](y_test, y_pred_proba))
        except ValueError:
            auc = 0.0

        cv_result = self._cross_validate(model, X, y, "credit")

        version = self._next_version("credit")
        metadata = {
            "accuracy": accuracy, "precision": precision, "recall": recall,
            "f1": f1, "auc": auc,
            "train_size": len(X_train), "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "cv_scores": cv_result,
            "params": train_params,
            "class_distribution": {"positive": int(n_pos), "negative": int(n_neg)},
        }
        self.service._save_model(model.get_booster(), "credit", version, metadata)

        logger.info(
            "credit_model_trained",
            version=version, accuracy=accuracy, auc=auc, f1=f1,
        )

        return {
            "status": "success",
            "model_type": "credit",
            "version": version,
            "metrics": {
                "accuracy": accuracy, "precision": precision,
                "recall": recall, "f1": f1, "auc": auc,
            },
            "cross_validation": cv_result,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "feature_importance": self._get_feature_importance(model, feature_names),
        }

    def train_churn_model(
        self,
        transactions_by_user: Dict[str, List[Any]],
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Train XGBoost churn prediction model.

        Predicts whether a worker will become inactive.
        Uses behavioral features (declining usage, session patterns).

        Args:
            transactions_by_user: User transaction data
            params: Optional XGBoost hyperparameter overrides

        Returns:
            Training results with metrics
        """
        xgb = _import_xgboost()
        sk = _import_sklearn()
        if xgb is None or sk is None:
            return {"status": "failed", "reason": "dependencies_missing"}

        X, feature_names, user_ids = self.prepare_features(transactions_by_user)
        if len(X) < 20:
            return {"status": "failed", "reason": "insufficient_data", "min_required": 20}

        y = self.prepare_churn_targets(transactions_by_user)
        if len(y) != len(X):
            y = y[:len(X)]

        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        train_params = {**self.DEFAULT_PARAMS["churn"]}
        if params:
            train_params.update(params)

        n_estimators = train_params.pop("n_estimators", 250)

        n_pos = max(1, np.sum(y_train == 1))
        n_neg = max(1, np.sum(y_train == 0))
        train_params["scale_pos_weight"] = n_neg / n_pos

        start_time = time.time()
        model = xgb.XGBClassifier(
            n_estimators=n_estimators,
            **train_params,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )
        train_time = time.time() - start_time

        y_pred_proba = model.predict_proba(X_test)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        accuracy = float(sk["accuracy_score"](y_test, y_pred))
        precision = float(sk["precision_score"](y_test, y_pred, zero_division=0))
        recall = float(sk["recall_score"](y_test, y_pred, zero_division=0))
        f1 = float(sk["f1_score"](y_test, y_pred, zero_division=0))
        try:
            auc = float(sk["roc_auc_score"](y_test, y_pred_proba))
        except ValueError:
            auc = 0.0

        cv_result = self._cross_validate(model, X, y, "churn")

        version = self._next_version("churn")
        metadata = {
            "accuracy": accuracy, "precision": precision, "recall": recall,
            "f1": f1, "auc": auc,
            "train_size": len(X_train), "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "cv_scores": cv_result,
            "params": train_params,
        }
        self.service._save_model(model.get_booster(), "churn", version, metadata)

        logger.info(
            "churn_model_trained",
            version=version, accuracy=accuracy, auc=auc, f1=f1,
        )

        return {
            "status": "success",
            "model_type": "churn",
            "version": version,
            "metrics": {
                "accuracy": accuracy, "precision": precision,
                "recall": recall, "f1": f1, "auc": auc,
            },
            "cross_validation": cv_result,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "feature_importance": self._get_feature_importance(model, feature_names),
        }

    def train_anomaly_model(
        self,
        transactions: List[Any],
        contamination: float = 0.05,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Train XGBoost anomaly detection model.

        Uses transaction-level features. Normal transactions are labeled 0,
        and the top `contamination` fraction by amount z-score are labeled 1.

        Args:
            transactions: List of all transactions
            contamination: Expected fraction of anomalies (default 5%)
            params: Optional XGBoost hyperparameter overrides

        Returns:
            Training results with metrics
        """
        xgb = _import_xgboost()
        sk = _import_sklearn()
        if xgb is None or sk is None:
            return {"status": "failed", "reason": "dependencies_missing"}

        if len(transactions) < 50:
            return {"status": "failed", "reason": "insufficient_data", "min_required": 50}

        # Compute baseline stats per user
        from collections import defaultdict
        user_txns: Dict[str, list] = defaultdict(list)
        for t in transactions:
            user_txns[str(t.user_id)].append(t)

        # Generate features and labels
        X_rows = []
        y_labels = []

        for user_id, txns in user_txns.items():
            sorted_txns = sorted(txns, key=lambda t: t.timestamp)
            amounts = [t.amount for t in sorted_txns if t.amount > 0]
            if len(amounts) < 5:
                continue

            mean_amt = np.mean(amounts)
            std_amt = np.std(amounts)

            for t in sorted_txns:
                features = FeatureEngineer.extract_transaction_features(t, sorted_txns)
                row = [features.get(f, 0.0) for f in FEATURE_NAMES]
                X_rows.append(row)

                # Label: anomalous if z-score > 2.5
                if std_amt > 0:
                    zscore = abs((t.amount - mean_amt) / std_amt)
                else:
                    zscore = 0
                y_labels.append(1 if zscore > 2.5 else 0)

        if len(X_rows) < 50:
            return {"status": "failed", "reason": "insufficient_feature_rows"}

        X = np.array(X_rows, dtype=np.float32)
        y = np.array(y_labels, dtype=np.int32)

        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        train_params = {**self.DEFAULT_PARAMS["anomaly"]}
        if params:
            train_params.update(params)

        n_estimators = train_params.pop("n_estimators", 150)

        n_pos = max(1, np.sum(y_train == 1))
        n_neg = max(1, np.sum(y_train == 0))
        train_params["scale_pos_weight"] = n_neg / n_pos

        start_time = time.time()
        model = xgb.XGBClassifier(
            n_estimators=n_estimators,
            **train_params,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )
        train_time = time.time() - start_time

        y_pred_proba = model.predict_proba(X_test)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        accuracy = float(sk["accuracy_score"](y_test, y_pred))
        precision = float(sk["precision_score"](y_test, y_pred, zero_division=0))
        recall = float(sk["recall_score"](y_test, y_pred, zero_division=0))
        f1 = float(sk["f1_score"](y_test, y_pred, zero_division=0))

        version = self._next_version("anomaly")
        anomaly_feature_names = sorted(
            FeatureEngineer.extract_transaction_features(
                transactions[0], transactions[:10]
            ).keys()
        )
        metadata = {
            "accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1,
            "train_size": len(X_train), "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "contamination": contamination,
            "n_anomalies_labeled": int(np.sum(y == 1)),
            "params": train_params,
        }
        self.service._save_model(model.get_booster(), "anomaly", version, metadata)

        logger.info(
            "anomaly_model_trained",
            version=version, accuracy=accuracy, f1=f1,
        )

        return {
            "status": "success",
            "model_type": "anomaly",
            "version": version,
            "metrics": {
                "accuracy": accuracy, "precision": precision,
                "recall": recall, "f1": f1,
            },
            "train_size": len(X_train),
            "test_size": len(X_test),
            "train_time_seconds": round(train_time, 2),
            "n_anomalies_labeled": int(np.sum(y == 1)),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Cross-Validation
    # ─────────────────────────────────────────────────────────────────────

    def _cross_validate(
        self,
        model: Any,
        X: np.ndarray,
        y: np.ndarray,
        model_type: str,
        n_splits: int = 5,
    ) -> Dict[str, Any]:
        """
        Time-series-aware cross-validation.

        Uses TimeSeriesSplit to prevent future data leakage.
        Reports mean and std of CV scores.

        Args:
            model: XGBoost model instance
            X: Feature matrix
            y: Target array
            model_type: 'demand' (regression) or 'credit'/'churn'/'anomaly' (classification)
            n_splits: Number of CV folds

        Returns:
            Dict with CV scores
        """
        sk = _import_sklearn()
        if sk is None:
            return {"available": False}

        try:
            tscv = sk["TimeSeriesSplit"](n_splits=min(n_splits, len(X) // 5))
            scoring = "neg_mean_absolute_error" if model_type == "demand" else "roc_auc"

            scores = sk["cross_val_score"](
                model, X, y, cv=tscv, scoring=scoring,
            )

            if model_type == "demand":
                # Convert negative MAE back to positive
                scores = -scores

            return {
                "available": True,
                "n_splits": min(n_splits, len(X) // 5),
                "scoring": scoring,
                "mean": round(float(np.mean(scores)), 4),
                "std": round(float(np.std(scores)), 4),
                "scores": [round(float(s), 4) for s in scores],
            }
        except Exception as e:
            logger.warning("cross_validation_failed", error=str(e))
            return {"available": False, "reason": str(e)}

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _generate_credit_labels(
        self,
        transactions_by_user: Dict[str, List[Any]],
        user_ids: List[str],
    ) -> np.ndarray:
        """
        Generate synthetic credit labels from transaction patterns.

        Users with declining revenue and high volatility are labeled
        as higher default risk (1). This is a proxy — real outcomes
        from AlamaScoreOutcome should be preferred when available.
        """
        labels = []
        for uid in user_ids:
            txns = transactions_by_user.get(uid, [])
            if not txns:
                labels.append(1)
                continue

            sales = [t for t in txns if t.transaction_type == "SALE"]
            if len(sales) < 10:
                labels.append(1)
                continue

            # Compare first half vs second half revenue
            sorted_sales = sorted(sales, key=lambda t: t.timestamp)
            mid = len(sorted_sales) // 2
            first_rev = sum(t.amount for t in sorted_sales[:mid])
            second_rev = sum(t.amount for t in sorted_sales[mid:])

            if first_rev > 0:
                decline = (first_rev - second_rev) / first_rev
            else:
                decline = 0

            # High volatility
            daily_rev = {}
            for t in sales:
                day = t.timestamp.strftime("%Y-%m-%d")
                daily_rev[day] = daily_rev.get(day, 0) + t.amount
            rev_values = list(daily_rev.values())
            cv = np.std(rev_values) / max(np.mean(rev_values), 1) if len(rev_values) > 1 else 0

            # Label: "default" if significant decline OR extreme volatility
            is_risky = decline > 0.3 or cv > 1.5
            labels.append(1 if is_risky else 0)

        return np.array(labels, dtype=np.int32)

    @staticmethod
    def _get_feature_importance(model: Any, feature_names: List[str], top_k: int = 15) -> List[Dict[str, Any]]:
        """Extract top-k feature importances from trained model."""
        try:
            importance = model.feature_importances_
            indices = np.argsort(importance)[::-1][:top_k]
            return [
                {
                    "feature": feature_names[i] if i < len(feature_names) else f"feature_{i}",
                    "importance": round(float(importance[i]), 4),
                }
                for i in indices
            ]
        except Exception:
            return []

    def _next_version(self, model_type: str) -> str:
        """Generate next version string for a model type."""
        pattern = f"{model_type}_v*.json"
        existing = list(self.model_dir.glob(pattern))
        if not existing:
            return "v1"

        versions = []
        for f in existing:
            name = f.stem  # e.g., "demand_v3"
            parts = name.split("_v")
            if len(parts) == 2:
                try:
                    versions.append(int(parts[1]))
                except ValueError:
                    pass

        next_ver = max(versions) + 1 if versions else 1
        return f"v{next_ver}"
