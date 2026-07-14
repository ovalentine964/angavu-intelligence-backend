"""
Proactive Alert Engine — ML-Powered Business Alerts.

Uses XGBoost predictions to generate proactive alerts for workers
and businesses. Combines demand forecasting, credit scoring, churn
prediction, and anomaly detection into actionable alerts.

Alert Types:
- DEMAND_SPIKE: ML predicts significant demand increase
- DEMAND_DROP: ML predicts demand decline
- CREDIT_RISK: Credit score declining (ML + classical ensemble)
- CHURN_RISK: Worker showing disengagement patterns
- ANOMALY_DETECTED: Unusual transaction flagged
- REVENUE_OPPORTUNITY: ML identifies untapped revenue patterns
- STOCKOUT_RISK: Demand forecast exceeds current inventory

Design: Alerts are non-blocking and fire-and-forget. Workers
receive them via WhatsApp with actionable recommendations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class AlertType(str, Enum):
    """Types of proactive alerts."""
    DEMAND_SPIKE = "demand_spike"
    DEMAND_DROP = "demand_drop"
    CREDIT_RISK = "credit_risk"
    CHURN_RISK = "churn_risk"
    ANOMALY_DETECTED = "anomaly_detected"
    REVENUE_OPPORTUNITY = "revenue_opportunity"
    STOCKOUT_RISK = "stockout_risk"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ProactiveAlert:
    """A single proactive alert."""

    def __init__(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        worker_id: Optional[str] = None,
        confidence: float = 0.0,
        ml_explanation: Optional[Dict[str, Any]] = None,
        recommended_action: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.alert_type = alert_type
        self.severity = severity
        self.title = title
        self.message = message
        self.worker_id = worker_id
        self.confidence = confidence
        self.ml_explanation = ml_explanation
        self.recommended_action = recommended_action
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "worker_id": self.worker_id,
            "confidence": self.confidence,
            "ml_explanation": self.ml_explanation,
            "recommended_action": self.recommended_action,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class ProactiveAlertEngine:
    """
    Generates proactive business alerts using ML predictions.

    Combines XGBoost predictions with classical statistics to
    generate actionable alerts for informal economy workers.

    Usage:
        engine = ProactiveAlertEngine()

        # Check for alerts for a specific worker
        alerts = await engine.generate_alerts(worker_id, transactions)

        # Check demand alerts for a product category
        demand_alerts = await engine.check_demand_alerts(
            product_category="food", region="Nairobi"
        )
    """

    def __init__(self):
        # Lazy-load ML services
        self._ml_service = None
        self._feature_engineer = None

    def _get_ml_service(self):
        """Lazy-load XGBoost service."""
        if self._ml_service is None:
            try:
                from app.services.ml.xgboost_service import XGBoostService
                self._ml_service = XGBoostService()
            except ImportError:
                pass
        return self._ml_service

    def _get_feature_engineer(self):
        """Lazy-load feature engineer."""
        if self._feature_engineer is None:
            try:
                from app.services.ml.feature_engineering import FeatureEngineer
                self._feature_engineer = FeatureEngineer()
            except ImportError:
                pass
        return self._feature_engineer

    async def generate_alerts(
        self,
        worker_id: str,
        transactions: List[Any],
        inventory: Optional[List[Any]] = None,
    ) -> List[ProactiveAlert]:
        """
        Generate all applicable alerts for a worker.

        Runs all ML models and classical checks, returning
        only alerts that meet confidence thresholds.

        Args:
            worker_id: Worker/user ID
            transactions: Recent transactions
            inventory: Optional inventory data for stockout alerts

        Returns:
            List of ProactiveAlert objects
        """
        alerts = []

        ml = self._get_ml_service()
        fe = self._get_feature_engineer()

        if ml is None or fe is None:
            logger.debug("ml_not_available_for_alerts")
            return alerts

        if len(transactions) < 10:
            return alerts

        try:
            features = fe.extract_all_features(transactions)

            # 1. Churn risk
            churn_result = ml.predict_churn(features)
            if churn_result.get("available") and churn_result.get("churn_probability", 0) >= 0.5:
                alerts.append(ProactiveAlert(
                    alert_type=AlertType.CHURN_RISK,
                    severity=AlertSeverity.CRITICAL if churn_result["churn_probability"] >= 0.7 else AlertSeverity.WARNING,
                    title="⚠️ Business Activity Declining",
                    message=(
                        f"Your business activity has been declining. "
                        f"Risk of inactivity: {churn_result['churn_probability']:.0%}. "
                        f"Keep recording transactions to maintain your credit score."
                    ),
                    worker_id=worker_id,
                    confidence=churn_result.get("confidence", 0),
                    ml_explanation=churn_result.get("shap_explanation"),
                    recommended_action="Record at least one transaction daily to maintain your business profile.",
                ))

            # 2. Demand drop
            trend_slope = features.get("derived_trend_slope", 0)
            momentum = features.get("derived_momentum_7_30", 0)
            if trend_slope < -100 and momentum < 0.7:
                alerts.append(ProactiveAlert(
                    alert_type=AlertType.DEMAND_DROP,
                    severity=AlertSeverity.WARNING,
                    title="📉 Sales Declining",
                    message=(
                        f"Your sales have been declining over the past month. "
                        f"Recent week is {momentum:.0%} of your monthly average."
                    ),
                    worker_id=worker_id,
                    confidence=0.75,
                    recommended_action="Consider promotions, new products, or adjusting prices to boost sales.",
                ))

            # 3. Revenue opportunity (strong positive momentum)
            if momentum > 1.3 and trend_slope > 100:
                alerts.append(ProactiveAlert(
                    alert_type=AlertType.REVENUE_OPPORTUNITY,
                    severity=AlertSeverity.INFO,
                    title="📈 Sales Momentum Strong",
                    message=(
                        f"Your sales are growing! Recent week is {momentum:.0%} "
                        f"of your monthly average. Consider stocking more inventory."
                    ),
                    worker_id=worker_id,
                    confidence=0.8,
                    recommended_action="Increase inventory for your top-selling products to capitalize on demand.",
                ))

            # 4. Anomaly detection on recent transactions
            if len(transactions) >= 5:
                recent_txns = sorted(transactions, key=lambda t: t.timestamp)[-5:]
                for txn in recent_txns:
                    txn_features = fe.extract_transaction_features(txn, transactions)
                    anomaly_result = ml.detect_anomaly(txn_features)
                    if anomaly_result.get("available") and anomaly_result.get("is_anomalous"):
                        alerts.append(ProactiveAlert(
                            alert_type=AlertType.ANOMALY_DETECTED,
                            severity=AlertSeverity.WARNING if anomaly_result["severity"] == "high" else AlertSeverity.INFO,
                            title="🔍 Unusual Transaction Detected",
                            message=(
                                f"A transaction of KES {txn.amount:,.0f} on "
                                f"{txn.timestamp.strftime('%Y-%m-%d')} looks unusual for your business."
                            ),
                            worker_id=worker_id,
                            confidence=anomaly_result.get("confidence", 0),
                            ml_explanation=anomaly_result.get("shap_explanation"),
                            recommended_action="Verify this transaction is correct. If not, you can edit or delete it.",
                            metadata={"transaction_id": str(txn.id), "amount": txn.amount},
                        ))
                        break  # Only report first anomaly

            # 5. Credit risk (if we can compute features)
            credit_result = ml.predict_credit_score(features)
            if credit_result.get("available"):
                default_prob = credit_result.get("default_probability", 0)
                if default_prob >= 0.4:
                    alerts.append(ProactiveAlert(
                        alert_type=AlertType.CREDIT_RISK,
                        severity=AlertSeverity.WARNING,
                        title="💳 Credit Score at Risk",
                        message=(
                            f"Your business patterns suggest credit risk. "
                            f"Keep consistent sales to maintain your Alama Score."
                        ),
                        worker_id=worker_id,
                        confidence=credit_result.get("confidence", 0),
                        ml_explanation=credit_result.get("shap_explanation"),
                        recommended_action="Maintain daily transactions and diversify your product mix.",
                    ))

        except Exception as e:
            logger.error("alert_generation_failed", worker_id=worker_id, error=str(e))

        return alerts

    async def check_demand_alerts(
        self,
        product_category: str,
        region: Optional[str] = None,
    ) -> List[ProactiveAlert]:
        """
        Check for demand-related alerts for a product category/region.

        Used by Soko Pulse buyers (FMCG companies) to get proactive
        demand intelligence.

        Args:
            product_category: Product category to check
            region: Geographic region

        Returns:
            List of demand alerts
        """
        # This would integrate with SokoPulseService for real data
        # For now, return empty — alerts are generated per-worker
        return []

    async def check_stockout_risk(
        self,
        worker_id: str,
        transactions: List[Any],
        inventory: List[Any],
    ) -> List[ProactiveAlert]:
        """
        Check for stockout risk based on demand forecast vs inventory.

        Args:
            worker_id: Worker ID
            transactions: Recent transactions
            inventory: Current inventory levels

        Returns:
            List of stockout risk alerts
        """
        alerts = []
        ml = self._get_ml_service()
        fe = self._get_feature_engineer()

        if ml is None or fe is None or not inventory:
            return alerts

        try:
            features = fe.extract_all_features(transactions)
            demand = ml.predict_demand(features)

            if not demand.get("available"):
                return alerts

            predicted_volume = demand.get("predicted_volume", 0)

            for item in inventory:
                if hasattr(item, "current_stock") and hasattr(item, "sell_price"):
                    if item.current_stock > 0 and item.sell_price and item.sell_price > 0:
                        days_of_stock = item.current_stock / max(predicted_volume / 7, 1)
                        if days_of_stock < 3:
                            alerts.append(ProactiveAlert(
                                alert_type=AlertType.STOCKOUT_RISK,
                                severity=AlertSeverity.WARNING,
                                title=f"📦 Low Stock: {item.item}",
                                message=(
                                    f"You have ~{days_of_stock:.0f} days of stock remaining "
                                    f"for {item.item} based on current demand."
                                ),
                                worker_id=worker_id,
                                confidence=demand.get("confidence", 0),
                                recommended_action=f"Restock {item.item} soon to avoid missing sales.",
                            ))

        except Exception as e:
            logger.error("stockout_check_failed", worker_id=worker_id, error=str(e))

        return alerts
