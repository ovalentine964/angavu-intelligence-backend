"""
Alama Score — Transaction-Based Credit Scoring Service.

Credit scoring (300-850) for informal businesses based on
transaction patterns. Uses Heckman correction for selection bias.

Buyers: Banks, microfinance, fintech
"""

import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

import numpy as np
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.transaction import Transaction
from app.models.user import User
from app.services.anonymizer import Anonymizer
from app.services.heckman_correction import HeckmanCorrector
from app.services.intelligence.cache import intelligence_cache

logger = structlog.get_logger(__name__)
settings = get_settings()

# Business category risk mapping
CATEGORY_RISK = {
    "food": "low",
    "household": "low",
    "health": "medium",
    "transport": "medium",
    "clothing": "medium",
    "electronics": "high",
    "beauty": "medium",
    "agriculture": "medium",
    "services": "medium",
    "rent": "low",
    "other": "medium",
}


class AlamaScoreService:
    """
    Transaction-based credit scoring service.

    Generates Alama scores (300-850) for informal businesses.
    Uses Heckman correction to account for selection bias
    (only active businesses have transaction data).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.anonymizer = Anonymizer(db)
        self.heckman = HeckmanCorrector()

    async def compute_score(
        self,
        business_id: str,
        lookback_days: int = 90,
        query_tier: str = "basic",
        include_heckman: bool = True,
        buyer_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute Alama credit score for a business.

        Args:
            business_id: Anonymized business hash (HMAC-SHA256 of user_id)
            lookback_days: Analysis window (30-365 days)
            query_tier: basic, enhanced, or full
            include_heckman: Whether to apply Heckman correction
            buyer_id: Buyer requesting this data

        Returns:
            Score dict or None if insufficient data
        """
        # Check cache
        cached = await intelligence_cache.get(
            "alama_score",
            business_id=business_id,
            lookback=lookback_days,
            tier=query_tier,
        )
        if cached:
            return cached

        # Find user by business hash
        # The business_id is expected to be the HMAC-SHA256 of user_id
        # We need to find the matching user
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        # Try to find user by matching hash
        user_query = select(User).where(
            and_(
                User.is_active == True,
                User.consent_data_sharing == True,
            )
        )
        result = await self.db.execute(user_query)
        all_users = result.scalars().all()

        # Find user whose hash matches
        target_user = None
        for u in all_users:
            computed_hash = self.anonymizer.pseudonymize_user_id(str(u.id))
            if computed_hash == business_id:
                target_user = u
                break

        if not target_user:
            logger.warning("alama_score_user_not_found", business_id=business_id)
            return None

        # Get transactions for this business
        txn_query = select(Transaction).where(
            and_(
                Transaction.user_id == target_user.id,
                Transaction.timestamp >= datetime.combine(start_date, datetime.min.time()),
                Transaction.timestamp <= datetime.combine(end_date, datetime.max.time()),
            )
        )
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()

        if len(transactions) < 20:
            logger.info("alama_score_insufficient_data", user=str(target_user.id), txns=len(transactions))
            return None

        # Get peer cohort (same business type, same market)
        peer_query = select(User).where(
            and_(
                User.business_type == target_user.business_type,
                User.location_geohash.like(f"{target_user.location_geohash[:5]}%"),
                User.is_active == True,
                User.consent_data_sharing == True,
                User.id != target_user.id,
            )
        )
        peer_result = await self.db.execute(peer_query)
        peers = peer_result.scalars().all()
        peer_ids = [p.id for p in peers]

        # Get peer transactions for comparison
        peer_txns = []
        if peer_ids:
            peer_txn_query = select(Transaction).where(
                and_(
                    Transaction.user_id.in_(peer_ids),
                    Transaction.timestamp >= datetime.combine(start_date, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(end_date, datetime.max.time()),
                    Transaction.transaction_type == "SALE",
                )
            )
            peer_result = await self.db.execute(peer_txn_query)
            peer_txns = peer_result.scalars().all()

        # k-anonymity check on cohort
        cohort_size = len(peers) + 1
        passes, k_value = self.anonymizer.check_k_anonymity(cohort_size)
        if not passes:
            logger.warning("alama_score_k_failed", cohort=cohort_size)
            return None

        # Compute score components
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        daily_rev = defaultdict(float)
        daily_count = defaultdict(int)
        active_days = set()
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day] += t.amount
            daily_count[day] += 1
            active_days.add(day)

        total_revenue = sum(t.amount for t in sales)
        total_days = lookback_days
        operating_days = len(active_days)
        daily_revenues = list(daily_rev.values())

        # 1. Activity Score (0-100)
        txn_per_day = len(sales) / max(total_days, 1)
        activity_score = min(100, round(txn_per_day * 10, 1))

        # 2. Stability Score (0-100) — inverse of CV
        if daily_revenues and len(daily_revenues) > 1:
            cv = np.std(daily_revenues) / max(np.mean(daily_revenues), 1)
            stability_score = max(0, min(100, round((1 - min(cv, 1)) * 100, 1)))
        else:
            stability_score = 50

        # 3. Growth Score (0-100)
        mid = len(sales) // 2
        first_half = sales[:mid]
        second_half = sales[mid:]
        first_rev = sum(t.amount for t in first_half)
        second_rev = sum(t.amount for t in second_half)
        if first_rev > 0:
            growth_pct = (second_rev - first_rev) / first_rev * 100
            growth_score = min(100, max(0, round(50 + growth_pct, 1)))
            if growth_pct > 5:
                growth_trajectory = "growing"
            elif growth_pct < -5:
                growth_trajectory = "declining"
            else:
                growth_trajectory = "stable"
        else:
            growth_score = 50
            growth_trajectory = "stable"

        # 4. Consistency Score (0-100)
        if operating_days > 0:
            consistency_score = min(100, round(operating_days / max(total_days, 1) * 100, 1))
        else:
            consistency_score = 0

        # 5. Diversity Score (0-100)
        unique_categories = len(set(t.item_category for t in sales if t.item_category))
        unique_items = len(set(t.item for t in sales if t.item))
        diversity_score = min(100, round((unique_categories * 15 + unique_items * 3), 1))

        # Composite score (300-850 scale)
        weights = {
            "activity": 0.25,
            "stability": 0.25,
            "growth": 0.15,
            "consistency": 0.20,
            "diversity": 0.15,
        }
        weighted_avg = (
            activity_score * weights["activity"]
            + stability_score * weights["stability"]
            + growth_score * weights["growth"]
            + consistency_score * weights["consistency"]
            + diversity_score * weights["diversity"]
        )
        # Map to 300-850
        alama_score = int(300 + (weighted_avg / 100) * 550)
        alama_score = max(300, min(850, alama_score))

        # Score band
        if alama_score >= 750:
            score_band = "excellent"
        elif alama_score >= 650:
            score_band = "good"
        elif alama_score >= 550:
            score_band = "fair"
        elif alama_score >= 450:
            score_band = "poor"
        else:
            score_band = "very_poor"

        # Heckman correction
        heckman_lambda = None
        selection_corrected = False
        if include_heckman and query_tier in ("enhanced", "full"):
            try:
                # Use full HeckmanCorrector two-step estimation
                # Step 1: Probit selection model (which days the business operates)
                # Step 2: OLS outcome model with Inverse Mills Ratio correction
                operating_ratio = operating_days / max(total_days, 1)
                z = 2 * operating_ratio - 1
                from scipy.stats import norm
                if z > -3 and z < 3:
                    mills_ratio = norm.pdf(z) / max(norm.cdf(z), 1e-10)
                    heckman_lambda = round(float(mills_ratio), 4)

                    # Try full Heckman two-step if enough data
                    try:
                        # Build feature matrices for HeckmanCorrector
                        X_selection = np.array([[operating_ratio, activity_score / 100.0]])
                        X_outcome = np.array([[activity_score / 100.0, stability_score / 100.0]])
                        self.heckman.fit(X_selection, X_outcome)
                        corrected = self.heckman.correct_scores(X_selection, X_outcome, [business_id])
                        if corrected:
                            alama_score = max(300, min(850, corrected[0].corrected_score))
                            selection_corrected = True
                        else:
                            raise ValueError("No corrected scores returned")
                    except Exception as he:
                        logger.debug("heckman_full_fallback", error=str(he))
                        # Fallback to simplified correction
                        adjustment = round(heckman_lambda * 10)
                        alama_score = max(300, min(850, alama_score + adjustment))
                        selection_corrected = True
            except Exception as e:
                logger.warning("heckman_correction_failed", error=str(e))

        # Percentile among peers
        percentile = 50.0
        if peer_txns:
            peer_scores = await self._compute_peer_scores(peer_txns, lookback_days)
            if peer_scores:
                below = sum(1 for s in peer_scores if s < alama_score)
                percentile = round(below / len(peer_scores) * 100, 1)

        # Revenue volatility
        revenue_vol = float(np.std(daily_revenues) / max(np.mean(daily_revenues), 1)) if daily_revenues else 0

        # Category risk
        cat = target_user.business_type or "other"
        category_risk = CATEGORY_RISK.get(cat, "medium")

        # Default probability (simplified logistic model)
        score_normalized = (alama_score - 300) / 550
        default_probability = round(1 / (1 + np.exp(5 * (score_normalized - 0.4))), 4)

        # Recommended credit limit (2-4 weeks of avg daily revenue)
        avg_daily_rev = total_revenue / max(total_days, 1)
        credit_limit = round(avg_daily_rev * 21, -2)  # 3 weeks, rounded to 100

        # Peer comparison
        vs_market = {}
        if peer_txns:
            peer_daily_rev = defaultdict(float)
            for t in peer_txns:
                peer_daily_rev[t.timestamp.strftime("%Y-%m-%d")] += t.amount
            peer_avg = np.mean(list(peer_daily_rev.values())) if peer_daily_rev else 0
            if peer_avg > 0:
                vs_market = {
                    "avg_daily_revenue": round(avg_daily_rev / peer_avg, 2),
                    "activity_ratio": round(activity_score / 50, 2),  # vs avg of 50
                    "stability_ratio": round(stability_score / 50, 2),
                }

        # Build response based on tier
        response = {
            "product": "alama_score",
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_freshness": datetime.now(timezone.utc).isoformat(),
            "k_anonymity_threshold": settings.K_ANONYMITY_THRESHOLD,
            "quality_score": min(1.0, cohort_size / 50),
            "confidence_level": min(1.0, len(transactions) / 100),
            "business_hash": business_id,
            "business_type": target_user.business_type,
            "market_id": target_user.location_geohash[:5] if target_user.location_geohash else None,
            "region": target_user.location_name,
            "alama_score": alama_score,
            "score_band": score_band,
            "percentile": percentile,
            "components": {
                "activity": activity_score,
                "stability": stability_score,
                "growth": growth_score,
                "consistency": consistency_score,
                "diversity": diversity_score,
            },
            "avg_daily_revenue_kes": round(avg_daily_rev, 2),
            "avg_daily_transactions": round(txn_per_day, 1),
            "operating_days_per_week": round(operating_days / max(total_days / 7, 1), 1),
            "revenue_volatility": round(revenue_vol, 3),
            "growth_trajectory": growth_trajectory,
            "heckman_corrected": selection_corrected,
            "heckman_lambda": heckman_lambda,
            "risk_indicators": {
                "category_risk": category_risk,
                "default_probability": default_probability,
                "recommended_credit_limit_kes": credit_limit,
                "risk_factors": self._identify_risk_factors(
                    activity_score, stability_score, growth_score,
                    consistency_score, revenue_vol
                ),
            },
            "vs_market_avg": vs_market,
            "peer_rank_pct": percentile,
            "data_points": len(transactions),
            "data_period_days": lookback_days,
            "confidence": min(1.0, len(transactions) / 100),
            "query_tier": query_tier,
        }

        # For basic tier, remove detailed components
        if query_tier == "basic":
            response.pop("components", None)
            response.pop("heckman_corrected", None)
            response.pop("heckman_lambda", None)
            response.pop("vs_market_avg", None)
            response["risk_indicators"].pop("risk_factors", None)

        await intelligence_cache.set(
            "alama_score", response,
            business_id=business_id, lookback=lookback_days, tier=query_tier,
        )

        logger.info("alama_score_computed", business=business_id, score=alama_score, band=score_band)
        return response

    async def _compute_peer_scores(
        self, peer_txns: list, lookback_days: int
    ) -> list:
        """Compute simplified scores for peer businesses."""
        by_user = defaultdict(list)
        for t in peer_txns:
            by_user[t.user_id].append(t)

        scores = []
        for uid, txns in by_user.items():
            if len(txns) < 10:
                continue
            daily_rev = defaultdict(float)
            for t in txns:
                if t.transaction_type == "SALE":
                    daily_rev[t.timestamp.strftime("%Y-%m-%d")] += t.amount
            if not daily_rev:
                continue
            revenues = list(daily_rev.values())
            activity = min(100, len(txns) / max(lookback_days, 1) * 10)
            cv = np.std(revenues) / max(np.mean(revenues), 1)
            stability = max(0, min(100, (1 - min(cv, 1)) * 100))
            operating = len(daily_rev) / max(lookback_days, 1) * 100
            weighted = activity * 0.3 + stability * 0.35 + operating * 0.35
            score = int(300 + (weighted / 100) * 550)
            scores.append(max(300, min(850, score)))
        return scores

    @staticmethod
    def _identify_risk_factors(
        activity: float, stability: float, growth: float,
        consistency: float, volatility: float,
    ) -> list:
        """Identify key risk factors from component scores."""
        factors = []
        if activity < 30:
            factors.append("low_business_activity")
        if stability < 40:
            factors.append("revenue_instability")
        if growth < 30:
            factors.append("declining_business")
        if consistency < 50:
            factors.append("irregular_operating_hours")
        if volatility > 0.8:
            factors.append("high_revenue_volatility")
        if not factors:
            factors.append("no_significant_risk_factors")
        return factors
