"""
Feature Engineering for ML Models — Angavu Intelligence.

Extracts machine learning features from transaction data for use by
XGBoost models. Features are designed for the informal economy context
where data is sparse, irregular, and noisy.

Feature Groups:
- RFM (Recency, Frequency, Monetary) — core behavioral features
- Temporal (day-of-week, time-of-day, seasonality) — cyclical patterns
- Product Mix (category diversity, concentration) — business profile
- Location (geohash-based, market density) — spatial features
- Derived (rolling stats, momentum, volatility) — engineered signals

All features handle missing data gracefully (informal traders may have
gaps in their transaction records).
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class FeatureEngineer:
    """
    Extracts ML features from transaction records.

    Designed for the informal economy: handles sparse data, irregular
    transaction patterns, and missing values gracefully.
    """

    # ─────────────────────────────────────────────────────────────────────
    # RFM Features (Recency, Frequency, Monetary)
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def rfm_features(
        transactions: list[Any],
        reference_date: datetime | None = None,
    ) -> dict[str, float]:
        """
        Compute RFM (Recency, Frequency, Monetary) features.

        Core behavioral features for any transaction-based ML model.
        Based on marketing science (Hughes, 1996) adapted for informal economy.

        Args:
            transactions: List of Transaction objects (must have .timestamp, .amount, .transaction_type)
            reference_date: Reference date for recency calculation (default: now)

        Returns:
            Dict of RFM features
        """
        if not transactions:
            return {
                "rfm_recency_days": 999.0,
                "rfm_frequency": 0.0,
                "rfm_monetary_total": 0.0,
                "rfm_monetary_avg": 0.0,
                "rfm_monetary_std": 0.0,
                "rfm_tenure_days": 0.0,
                "rfm_txn_per_day": 0.0,
            }

        if reference_date is None:
            reference_date = datetime.now(UTC)

        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if not sales:
            sales = transactions  # fallback

        timestamps = [t.timestamp for t in sales]
        amounts = [t.amount for t in sales if t.amount > 0]

        # Recency: days since last transaction
        last_txn = max(timestamps)
        recency = (reference_date - last_txn).days
        if hasattr(recency, 'total_seconds'):
            recency = recency.days

        # Frequency: total transaction count
        frequency = len(sales)

        # Monetary: total and average
        monetary_total = sum(amounts) if amounts else 0.0
        monetary_avg = float(np.mean(amounts)) if amounts else 0.0
        monetary_std = float(np.std(amounts)) if len(amounts) > 1 else 0.0

        # Tenure: days between first and last transaction
        first_txn = min(timestamps)
        tenure = (last_txn - first_txn).days
        if hasattr(tenure, 'total_seconds'):
            tenure = tenure.days

        # Transactions per day (active days)
        active_days = len(set(t.timestamp.strftime("%Y-%m-%d") for t in sales))
        txn_per_day = frequency / max(active_days, 1)

        return {
            "rfm_recency_days": float(recency),
            "rfm_frequency": float(frequency),
            "rfm_monetary_total": float(monetary_total),
            "rfm_monetary_avg": float(monetary_avg),
            "rfm_monetary_std": float(monetary_std),
            "rfm_tenure_days": float(max(tenure, 0)),
            "rfm_txn_per_day": float(txn_per_day),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Temporal Features
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def temporal_features(transactions: list[Any]) -> dict[str, float]:
        """
        Extract temporal patterns from transaction data.

        Captures day-of-week, time-of-day, and seasonal patterns
        that are strong predictors for demand forecasting and churn.

        Args:
            transactions: List of Transaction objects

        Returns:
            Dict of temporal features
        """
        if not transactions:
            return {
                "temporal_dow_entropy": 0.0,
                "temporal_peak_dow": -1.0,
                "temporal_weekend_ratio": 0.0,
                "temporal_morning_ratio": 0.0,
                "temporal_afternoon_ratio": 0.0,
                "temporal_evening_ratio": 0.0,
                "temporal_hour_entropy": 0.0,
                "temporal_days_since_last_active": 999.0,
                "temporal_active_days_ratio": 0.0,
                "temporal_max_gap_days": 999.0,
                "temporal_avg_gap_days": 999.0,
            }

        # Day-of-week distribution
        dow_counts = [0] * 7
        hour_counts = [0] * 24
        weekend_count = 0
        morning_count = 0
        afternoon_count = 0
        evening_count = 0
        active_dates = set()

        for t in transactions:
            ts = t.timestamp
            dow = ts.weekday()
            hour = ts.hour

            dow_counts[dow] += 1
            hour_counts[hour] += 1
            active_dates.add(ts.strftime("%Y-%m-%d"))

            if dow >= 5:  # Saturday, Sunday
                weekend_count += 1
            if 6 <= hour < 12:
                morning_count += 1
            elif 12 <= hour < 18:
                afternoon_count += 1
            elif 18 <= hour < 22:
                evening_count += 1

        total = len(transactions)

        # DOW entropy (diversity of activity across weekdays)
        dow_probs = np.array(dow_counts, dtype=float) / max(total, 1)
        dow_probs = dow_probs[dow_probs > 0]
        dow_entropy = float(-np.sum(dow_probs * np.log2(dow_probs + 1e-10)))

        # Hour entropy
        hour_probs = np.array(hour_counts, dtype=float) / max(total, 1)
        hour_probs = hour_probs[hour_probs > 0]
        hour_entropy = float(-np.sum(hour_probs * np.log2(hour_probs + 1e-10)))

        # Peak day of week
        peak_dow = int(np.argmax(dow_counts))

        # Gap analysis (consecutive inactive days)
        if len(active_dates) >= 2:
            sorted_dates = sorted(active_dates)
            date_objects = [datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=UTC) for d in sorted_dates]
            gaps = [(date_objects[i+1] - date_objects[i]).days for i in range(len(date_objects)-1)]
            max_gap = max(gaps) if gaps else 0
            avg_gap = float(np.mean(gaps)) if gaps else 0
            days_since_last = (datetime.now(UTC) - date_objects[-1]).days
            if hasattr(days_since_last, 'total_seconds'):
                days_since_last = days_since_last.days
        else:
            max_gap = 999
            avg_gap = 999
            days_since_last = 999

        # Active days ratio (over last 90 days)
        if transactions:
            earliest = min(t.timestamp for t in transactions)
            span_days = max((datetime.now(UTC) - earliest).days, 1)
            active_ratio = len(active_dates) / min(span_days, 90)
        else:
            active_ratio = 0.0

        return {
            "temporal_dow_entropy": round(dow_entropy, 4),
            "temporal_peak_dow": float(peak_dow),
            "temporal_weekend_ratio": round(weekend_count / max(total, 1), 4),
            "temporal_morning_ratio": round(morning_count / max(total, 1), 4),
            "temporal_afternoon_ratio": round(afternoon_count / max(total, 1), 4),
            "temporal_evening_ratio": round(evening_count / max(total, 1), 4),
            "temporal_hour_entropy": round(hour_entropy, 4),
            "temporal_days_since_last_active": float(days_since_last),
            "temporal_active_days_ratio": round(min(active_ratio, 1.0), 4),
            "temporal_max_gap_days": float(max_gap),
            "temporal_avg_gap_days": round(avg_gap, 2),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Product Mix Features
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def product_mix_features(transactions: list[Any]) -> dict[str, float]:
        """
        Extract product mix and business profile features.

        Captures category diversity, concentration (HHI), and
        product-level patterns.

        Args:
            transactions: List of Transaction objects

        Returns:
            Dict of product mix features
        """
        if not transactions:
            return {
                "pmix_unique_categories": 0.0,
                "pmix_unique_items": 0.0,
                "pmix_hhi": 1.0,
                "pmix_top_category_share": 1.0,
                "pmix_avg_item_price": 0.0,
                "pmix_price_range": 0.0,
                "pmix_qty_per_txn": 0.0,
                "pmix_profit_margin": 0.0,
            }

        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if not sales:
            sales = transactions

        # Category distribution
        cat_amounts: dict[str, float] = defaultdict(float)
        item_prices: list[float] = []
        quantities: list[float] = []
        profits: list[float] = []

        for t in sales:
            cat = t.item_category or "other"
            cat_amounts[cat] += t.amount
            if t.unit_price and t.unit_price > 0:
                item_prices.append(t.unit_price)
            if t.quantity and t.quantity > 0:
                quantities.append(t.quantity)
            if t.profit is not None and t.amount > 0:
                profits.append(t.profit / t.amount)

        total_revenue = sum(cat_amounts.values())
        unique_categories = len(cat_amounts)
        unique_items = len(set(t.item for t in sales if t.item))

        # Herfindahl-Hirschman Index (concentration)
        if total_revenue > 0:
            shares = [amt / total_revenue for amt in cat_amounts.values()]
            hhi = sum(s ** 2 for s in shares)
            top_category_share = max(shares)
        else:
            hhi = 1.0
            top_category_share = 1.0

        avg_price = float(np.mean(item_prices)) if item_prices else 0.0
        price_range = (max(item_prices) - min(item_prices)) if len(item_prices) > 1 else 0.0
        qty_per_txn = float(np.mean(quantities)) if quantities else 0.0
        profit_margin = float(np.mean(profits)) if profits else 0.0

        return {
            "pmix_unique_categories": float(unique_categories),
            "pmix_unique_items": float(unique_items),
            "pmix_hhi": round(hhi, 4),
            "pmix_top_category_share": round(top_category_share, 4),
            "pmix_avg_item_price": round(avg_price, 2),
            "pmix_price_range": round(price_range, 2),
            "pmix_qty_per_txn": round(qty_per_txn, 2),
            "pmix_profit_margin": round(profit_margin, 4),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Location Features
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def location_features(transactions: list[Any]) -> dict[str, float]:
        """
        Extract location-based features from geohash data.

        Args:
            transactions: List of Transaction objects

        Returns:
            Dict of location features
        """
        if not transactions:
            return {
                "loc_unique_locations": 0.0,
                "loc_primary_location_share": 0.0,
                "loc_location_entropy": 0.0,
                "loc_has_geohash": 0.0,
            }

        geohashes: dict[str, int] = defaultdict(int)
        has_location = 0

        for t in transactions:
            if t.location_geohash:
                geohashes[t.location_geohash] += 1
                has_location += 1

        total = len(transactions)
        unique_locations = len(geohashes)

        if geohashes:
            counts = list(geohashes.values())
            total_loc = sum(counts)
            primary_share = max(counts) / total_loc if total_loc > 0 else 0
            probs = np.array(counts, dtype=float) / total_loc
            entropy = float(-np.sum(probs * np.log2(probs + 1e-10)))
        else:
            primary_share = 0.0
            entropy = 0.0

        return {
            "loc_unique_locations": float(unique_locations),
            "loc_primary_location_share": round(primary_share, 4),
            "loc_location_entropy": round(entropy, 4),
            "loc_has_geohash": round(has_location / max(total, 1), 4),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Derived / Rolling Features
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def derived_features(
        transactions: list[Any],
        windows: list[int] = [7, 14, 30],
    ) -> dict[str, float]:
        """
        Compute derived and rolling-window features.

        Captures momentum, volatility, and trend signals at
        multiple time scales.

        Args:
            transactions: List of Transaction objects
            windows: List of lookback windows in days

        Returns:
            Dict of derived features
        """
        if not transactions:
            result = {}
            for w in windows:
                result[f"derived_rev_{w}d"] = 0.0
                result[f"derived_count_{w}d"] = 0.0
                result[f"derived_avg_txn_{w}d"] = 0.0
                result[f"derived_volatility_{w}d"] = 0.0
            result["derived_momentum_7_30"] = 0.0
            result["derived_trend_slope"] = 0.0
            return result

        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if not sales:
            sales = transactions

        # Daily aggregation
        daily_rev: dict[str, float] = defaultdict(float)
        daily_count: dict[str, int] = defaultdict(int)
        for t in sales:
            day = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day] += t.amount
            daily_count[day] += 1

        sorted_days = sorted(daily_rev.keys())
        if not sorted_days:
            return {f"derived_rev_{w}d": 0.0 for w in windows}

        # Reference: last day with data
        last_day = datetime.strptime(sorted_days[-1], "%Y-%m-%d")

        result = {}
        for w in windows:
            cutoff = (last_day - timedelta(days=w)).strftime("%Y-%m-%d")
            window_rev = [daily_rev[d] for d in sorted_days if d >= cutoff]
            window_cnt = [daily_count[d] for d in sorted_days if d >= cutoff]

            result[f"derived_rev_{w}d"] = round(sum(window_rev), 2)
            result[f"derived_count_{w}d"] = float(sum(window_cnt))
            result[f"derived_avg_txn_{w}d"] = round(
                float(np.mean(window_rev)) if window_rev else 0.0, 2
            )
            result[f"derived_volatility_{w}d"] = round(
                float(np.std(window_rev) / max(np.mean(window_rev), 1)) if len(window_rev) > 1 else 0.0,
                4,
            )

        # Momentum: 7-day vs 30-day revenue ratio
        rev_7d = result.get("derived_rev_7d", 0)
        rev_30d = result.get("derived_rev_30d", 0)
        result["derived_momentum_7_30"] = round(
            rev_7d / max(rev_30d / 4.3, 1) if rev_30d > 0 else 0.0, 4
        )

        # Trend slope: linear regression on daily revenue
        if len(sorted_days) >= 7:
            y_vals = np.array([daily_rev[d] for d in sorted_days[-30:]], dtype=float)
            x_vals = np.arange(len(y_vals), dtype=float)
            try:
                slope = float(np.polyfit(x_vals, y_vals, 1)[0])
            except (np.linalg.LinAlgError, ValueError):
                slope = 0.0
            result["derived_trend_slope"] = round(slope, 4)
        else:
            result["derived_trend_slope"] = 0.0

        return result

    # ─────────────────────────────────────────────────────────────────────
    # Churn-specific Features
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def churn_features(transactions: list[Any]) -> dict[str, float]:
        """
        Compute features specifically designed for churn prediction.

        Captures engagement decay, session patterns, and behavioral
        signals that indicate a worker may stop using Msaidizi.

        Args:
            transactions: List of Transaction objects

        Returns:
            Dict of churn-specific features
        """
        if not transactions:
            return {
                "churn_days_since_last_txn": 999.0,
                "churn_txn_decline_rate": 1.0,
                "churn_rev_decline_rate": 1.0,
                "churn_short_session_ratio": 1.0,
                "churn_record_method_diversity": 0.0,
                "churn_voice_usage_ratio": 0.0,
                "churn_avg_confidence": 0.0,
            }

        sorted_txns = sorted(transactions, key=lambda t: t.timestamp)
        now = datetime.now(UTC)

        # Days since last transaction
        last_ts = sorted_txns[-1].timestamp
        days_since = (now - last_ts).days
        if hasattr(days_since, 'total_seconds'):
            days_since = days_since.days

        # Split into halves for decline rate
        mid = len(sorted_txns) // 2
        first_half = sorted_txns[:mid]
        second_half = sorted_txns[mid:]

        # Transaction count decline
        first_count = len(first_half)
        second_count = len(second_half)
        txn_decline = 1.0 - (second_count / max(first_count, 1)) if first_count > 0 else 0.0

        # Revenue decline
        first_rev = sum(t.amount for t in first_half)
        second_rev = sum(t.amount for t in second_half)
        rev_decline = 1.0 - (second_rev / max(first_rev, 1)) if first_rev > 0 else 0.0

        # Short session ratio (single-txn days)
        daily_counts: dict[str, int] = defaultdict(int)
        for t in sorted_txns:
            daily_counts[t.timestamp.strftime("%Y-%m-%d")] += 1
        short_sessions = sum(1 for c in daily_counts.values() if c == 1)
        short_ratio = short_sessions / max(len(daily_counts), 1)

        # Recording method diversity
        methods = set(t.recorded_via for t in sorted_txns if t.recorded_via)
        method_diversity = len(methods)

        # Voice usage ratio
        voice_count = sum(1 for t in sorted_txns if t.recorded_via == "voice")
        voice_ratio = voice_count / max(len(sorted_txns), 1)

        # Average confidence score
        confidences = [t.confidence_score for t in sorted_txns if t.confidence_score is not None]
        avg_confidence = float(np.mean(confidences)) if confidences else 0.0

        return {
            "churn_days_since_last_txn": float(days_since),
            "churn_txn_decline_rate": round(max(0, min(1, txn_decline)), 4),
            "churn_rev_decline_rate": round(max(0, min(1, rev_decline)), 4),
            "churn_short_session_ratio": round(short_ratio, 4),
            "churn_record_method_diversity": float(method_diversity),
            "churn_voice_usage_ratio": round(voice_ratio, 4),
            "churn_avg_confidence": round(avg_confidence, 4),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Anomaly Features
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def anomaly_features(
        transactions: list[Any],
        lookback_days: int = 30,
    ) -> dict[str, float]:
        """
        Compute features for anomaly detection on individual transactions.

        Each transaction is scored relative to the user's historical pattern.

        Args:
            transactions: List of Transaction objects (historical)
            lookback_days: Days of history for baseline

        Returns:
            Dict of baseline features for anomaly scoring
        """
        if not transactions:
            return {
                "anomaly_hist_mean_amount": 0.0,
                "anomaly_hist_std_amount": 0.0,
                "anomaly_hist_median_amount": 0.0,
                "anomaly_hist_max_amount": 0.0,
                "anomaly_hist_txn_count": 0.0,
                "anomaly_hist_unique_items": 0.0,
                "anomaly_hour_concentration": 0.0,
            }

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=lookback_days)
        recent = [t for t in transactions if t.timestamp >= cutoff]
        if not recent:
            recent = transactions

        amounts = [t.amount for t in recent if t.amount > 0]
        items = set(t.item for t in recent if t.item)

        # Hour concentration (what fraction happen in the most common hour)
        hour_counts: dict[int, int] = defaultdict(int)
        for t in recent:
            hour_counts[t.timestamp.hour] += 1
        if hour_counts:
            max_hour_count = max(hour_counts.values())
            hour_concentration = max_hour_count / len(recent)
        else:
            hour_concentration = 0.0

        return {
            "anomaly_hist_mean_amount": round(float(np.mean(amounts)), 2) if amounts else 0.0,
            "anomaly_hist_std_amount": round(float(np.std(amounts)), 2) if len(amounts) > 1 else 0.0,
            "anomaly_hist_median_amount": round(float(np.median(amounts)), 2) if amounts else 0.0,
            "anomaly_hist_max_amount": round(float(max(amounts)), 2) if amounts else 0.0,
            "anomaly_hist_txn_count": float(len(recent)),
            "anomaly_hist_unique_items": float(len(items)),
            "anomaly_hour_concentration": round(hour_concentration, 4),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Combined Feature Vector
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def extract_all_features(
        cls,
        transactions: list[Any],
        reference_date: datetime | None = None,
    ) -> dict[str, float]:
        """
        Extract all feature groups into a single flat feature dict.

        This is the main entry point for feature extraction. Combines
        RFM, temporal, product mix, location, derived, and churn features
        into a single feature vector ready for model input.

        Args:
            transactions: List of Transaction objects
            reference_date: Reference date for recency calculations

        Returns:
            Flat dict of all features (50+ features)
        """
        features = {}

        features.update(cls.rfm_features(transactions, reference_date))
        features.update(cls.temporal_features(transactions))
        features.update(cls.product_mix_features(transactions))
        features.update(cls.location_features(transactions))
        features.update(cls.derived_features(transactions))
        features.update(cls.churn_features(transactions))

        return features

    @classmethod
    def extract_transaction_features(
        cls,
        transaction: Any,
        user_history: list[Any],
    ) -> dict[str, float]:
        """
        Extract features for a single transaction (for anomaly detection).

        Combines transaction-level features with user baseline features.

        Args:
            transaction: Single Transaction object to score
            user_history: User's historical transactions for baseline

        Returns:
            Feature dict for this transaction
        """
        features = {}

        # Transaction-level features
        features["txn_amount"] = float(transaction.amount)
        features["txn_quantity"] = float(transaction.quantity or 0)
        features["txn_unit_price"] = float(transaction.unit_price or 0)
        features["txn_hour"] = float(transaction.timestamp.hour)
        features["txn_dow"] = float(transaction.timestamp.weekday())
        features["txn_is_weekend"] = 1.0 if transaction.timestamp.weekday() >= 5 else 0.0
        features["txn_has_mpesa"] = 1.0 if transaction.mpesa_receipt else 0.0
        features["txn_confidence"] = float(transaction.confidence_score or 1.0)

        # Category encoding (simple ordinal)
        category_map = {
            "food": 1, "household": 2, "health": 3, "transport": 4,
            "clothing": 5, "electronics": 6, "beauty": 7, "agriculture": 8,
            "services": 9, "rent": 10, "other": 11,
        }
        features["txn_category_id"] = float(
            category_map.get(transaction.item_category, 11)
        )

        # Baseline features from user history
        baseline = cls.anomaly_features(user_history)
        features.update(baseline)

        # Z-score of transaction amount vs user history
        if baseline["anomaly_hist_std_amount"] > 0:
            features["txn_amount_zscore"] = (
                (features["txn_amount"] - baseline["anomaly_hist_mean_amount"])
                / baseline["anomaly_hist_std_amount"]
            )
        else:
            features["txn_amount_zscore"] = 0.0

        return features

    @staticmethod
    def features_to_array(
        features: dict[str, float],
        feature_order: list[str] | None = None,
    ) -> tuple[np.ndarray, list[str]]:
        """
        Convert feature dict to numpy array with consistent ordering.

        Args:
            features: Feature dict
            feature_order: Optional explicit ordering (for model consistency)

        Returns:
            (feature_array, feature_names)
        """
        if feature_order is None:
            feature_order = sorted(features.keys())

        values = [features.get(k, 0.0) for k in feature_order]
        return np.array(values, dtype=np.float32), feature_order
