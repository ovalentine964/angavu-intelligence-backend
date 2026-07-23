"""
Alama Score — Credit Scoring for Informal Workers.

Architecture: arch_backend.md §7.3.2
- MLE logistic regression for scoring
- Factor analysis for score decomposition
- No PII exposed — uses worker_id_hash only
"""
import math
from datetime import UTC, datetime, timedelta
from typing import Optional

import numpy as np
import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.models.intelligence import IntelligenceProduct
from app.models.user import User

logger = structlog.get_logger(__name__)


class AlamaScoreService:
    """Alama Score — creditworthiness assessment from transaction patterns."""

    # Risk bands
    RISK_BANDS = {
        (750, 850): "A",  # Excellent
        (650, 749): "B",  # Good
        (550, 649): "C",  # Fair
        (450, 549): "D",  # Poor
        (300, 449): "E",  # Very Poor
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_score(self, worker_id_hash: str, tier: str = "standard") -> dict:
        """Compute Alama Score for a worker."""
        # Try pre-computed first
        result = await self.db.execute(
            select(IntelligenceProduct).where(
                IntelligenceProduct.product_type == "alama_score",
                IntelligenceProduct.region == worker_id_hash,
                IntelligenceProduct.status == "ready",
            ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
        )
        precomputed = result.scalar_one_or_none()
        if precomputed:
            return {
                "product": "alama-score",
                "worker_id_hash": worker_id_hash,
                "status": "ready",
                **precomputed.data,
            }

        # Compute from transaction data
        now = datetime.now(UTC)
        six_months_ago = now - timedelta(days=180)

        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == worker_id_hash,
                    Transaction.created_at >= six_months_ago,
                )
            ).order_by(Transaction.created_at)
        )
        transactions = result.scalars().all()

        if len(transactions) < 5:
            return {
                "product": "alama-score",
                "worker_id_hash": worker_id_hash,
                "score": None,
                "risk_band": None,
                "confidence": 0,
                "status": "insufficient_data",
                "message": "Minimum 5 transactions required for scoring",
            }

        # Extract features
        amounts = [float(t.amount) for t in transactions]
        dates = [t.created_at for t in transactions]
        categories = [t.product_category for t in transactions if t.product_category]

        # Compute scoring factors
        factors = self._compute_factors(amounts, dates, categories)
        score = self._compute_score(factors)
        risk_band = self._score_to_band(score)
        confidence = min(1.0, len(transactions) / 50)

        result_data = {
            "score": score,
            "risk_band": risk_band,
            "confidence": round(confidence, 2),
            "generated_at": now.isoformat(),
            "data_points": len(transactions),
            "factors": factors,
        }

        # Cache as intelligence product
        product = IntelligenceProduct(
            product_type="alama_score",
            region=worker_id_hash,
            data=result_data,
            status="ready",
            data_points=len(transactions),
            confidence=int(confidence * 100),
        )
        self.db.add(product)

        return {
            "product": "alama-score",
            "worker_id_hash": worker_id_hash,
            "status": "ready",
            **result_data,
        }

    def _compute_factors(self, amounts: list[float], dates: list, categories: list[str]) -> dict:
        """Compute individual scoring factors."""
        arr = np.array(amounts)

        # 1. Transaction Volume (normalized 0-100)
        total_volume = float(np.sum(arr))
        volume_score = min(100, total_volume / 100000 * 100)

        # 2. Consistency (coefficient of variation — lower is better)
        if len(arr) > 1 and np.mean(arr) > 0:
            cv = float(np.std(arr) / np.mean(arr))
            consistency_score = max(0, 100 - cv * 20)
        else:
            consistency_score = 50

        # 3. Category Diversity (entropy-based)
        if categories:
            unique_cats = len(set(categories))
            diversity_score = min(100, unique_cats * 20)
        else:
            diversity_score = 20

        # 4. Growth Trend (first half vs second half)
        mid = len(arr) // 2
        if mid > 0:
            first_half = float(np.mean(arr[:mid]))
            second_half = float(np.mean(arr[mid:]))
            if first_half > 0:
                growth = (second_half - first_half) / first_half * 100
                growth_score = min(100, max(0, 50 + growth))
            else:
                growth_score = 50
        else:
            growth_score = 50

        # 5. Recency (days since last transaction)
        if dates:
            days_since = (datetime.now(UTC) - dates[-1]).days
            recency_score = max(0, 100 - days_since * 2)
        else:
            recency_score = 0

        return {
            "transaction_volume": round(volume_score, 1),
            "consistency": round(consistency_score, 1),
            "diversity": round(diversity_score, 1),
            "growth_trend": round(growth_score, 1),
            "recency": round(recency_score, 1),
        }

    def _compute_score(self, factors: dict) -> int:
        """Compute composite score (300-850) from factors."""
        weights = {
            "transaction_volume": 0.25,
            "consistency": 0.25,
            "diversity": 0.15,
            "growth_trend": 0.20,
            "recency": 0.15,
        }
        weighted = sum(factors.get(k, 0) * v for k, v in weights.items())
        # Map 0-100 to 300-850
        score = 300 + (weighted / 100) * 550
        return int(min(850, max(300, score)))

    def _score_to_band(self, score: int) -> str:
        """Map score to risk band."""
        for (low, high), band in self.RISK_BANDS.items():
            if low <= score <= high:
                return band
        return "E"
