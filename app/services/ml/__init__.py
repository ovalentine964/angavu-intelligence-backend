"""
ML Services — XGBoost-based prediction layer for Angavu Intelligence.

Provides machine learning models that complement the classical statistical
methods in the intelligence pipeline. XGBoost models handle:
- Demand forecasting (next week's sales prediction)
- Credit scoring enhancement (Alama Score with ML)
- Churn prediction (will worker stop using Msaidizi?)
- Anomaly detection (unusual transactions)

All models include SHAP explainability for transparent predictions.
Models work alongside existing classical stats — not replacing them.
"""

from app.services.ml.feature_engineering import FeatureEngineer
from app.services.ml.xgboost_service import XGBoostService
from app.services.ml.model_trainer import ModelTrainer

__all__ = ["FeatureEngineer", "XGBoostService", "ModelTrainer"]
