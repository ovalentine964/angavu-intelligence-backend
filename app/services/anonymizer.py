"""
Anonymization service — PII stripping, k-anonymity, differential privacy.

This is the most critical service from a privacy and compliance perspective.
Msaidizi handles data from economically vulnerable people in Kenya.
A data breach or privacy violation would be catastrophic.

Privacy Architecture (4 Layers):
    Layer 1 (Raw): Full data with PII — encrypted, access: user + system only
    Layer 2 (Internal): Pseudonymized — user IDs hashed
    Layer 3 (Licensed): k-anonymity (k≥10) enforced
    Layer 4 (Public): Aggregated statistics only

Kenya Data Protection Act 2019 compliance:
    - No individual data ever shared with buyers
    - All queries go through k-anonymity check
    - Differential privacy for sensitive aggregates
    - Full audit logging of all data access
"""

import hashlib
import math
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.intelligence import DataAccessLog

logger = structlog.get_logger(__name__)
settings = get_settings()


class Anonymizer:
    """
    Handles all anonymization, pseudonymization, and privacy enforcement.

    Key responsibilities:
    - Strip PII from data before any external sharing
    - Enforce k-anonymity on all buyer-facing queries
    - Apply differential privacy to aggregate statistics
    - Log all data access for audit compliance
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # PII Stripping
    # =========================================================================

    @staticmethod
    def strip_pii(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove all personally identifiable information from a data record.

        Strips:
        - Names
        - Phone numbers (raw)
        - Exact GPS coordinates
        - Voice recordings
        - M-Pesa receipt numbers
        - Customer phone numbers

        Args:
            data: Dictionary with transaction/user data

        Returns:
            Cleaned dictionary with PII removed
        """
        pii_fields = [
            "name", "name_encrypted", "phone", "phone_encrypted",
            "phone_hash", "customer_phone", "customer_phone_hash",
            "mpesa_receipt", "source_text", "voice_recording",
            "exact_latitude", "exact_longitude", "gps_coordinates",
            "email", "national_id", "date_of_birth",
        ]

        cleaned = {}
        for key, value in data.items():
            if key in pii_fields:
                continue  # Skip PII fields
            cleaned[key] = value

        # Coarsen location to geohash-5 if geohash is present
        if "location_geohash" in cleaned and cleaned["location_geohash"]:
            cleaned["location_geohash"] = cleaned["location_geohash"][:5]

        return cleaned

    @staticmethod
    def pseudonymize_user_id(user_id: str, salt: str = None) -> str:
        """
        Create a pseudonymized user ID that's consistent but not reversible.

        Uses HMAC-SHA256 with a secret salt so the same user always
        maps to the same pseudonym, but the original ID cannot be
        recovered without the salt.

        Args:
            user_id: Original user UUID
            salt: Secret salt (defaults to config salt)

        Returns:
            Pseudonymized ID (hex string)
        """
        if salt is None:
            salt = settings.DATA_ENCRYPTION_SALT
        import hmac as _hmac
        return _hmac.new(
            salt.encode(),
            str(user_id).encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

    # =========================================================================
    # k-Anonymity Enforcement
    # =========================================================================

    def check_k_anonymity(
        self,
        group_size: int,
        custom_threshold: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """
        Check if a group meets k-anonymity requirements.

        Args:
            group_size: Number of individuals in the aggregation group
            custom_threshold: Override default k threshold

        Returns:
            Tuple of (passes_check, k_value)
        """
        threshold = custom_threshold or settings.K_ANONYMITY_THRESHOLD
        if group_size < threshold:
            return False, 0
        return True, group_size

    def enforce_k_anonymity_on_query(
        self,
        data: List[Dict[str, Any]],
        group_key: str,
        min_group_size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Filter query results to enforce k-anonymity.

        Groups records by group_key and removes groups with fewer
        than k members. This prevents identification of individuals
        in small groups.

        Args:
            data: List of data records
            group_key: Field to group by (e.g., 'market_id', 'business_type')
            min_group_size: Override default k threshold

        Returns:
            Filtered list with small groups removed
        """
        threshold = min_group_size or settings.K_ANONYMITY_THRESHOLD

        # Count records per group
        group_counts = {}
        for record in data:
            key = record.get(group_key)
            if key:
                group_counts[key] = group_counts.get(key, 0) + 1

        # Filter to groups that meet threshold
        valid_groups = {
            k for k, v in group_counts.items() if v >= threshold
        }

        filtered = [
            record for record in data
            if record.get(group_key) in valid_groups
        ]

        suppressed_count = len(data) - len(filtered)
        if suppressed_count > 0:
            logger.info(
                "k_anonymity_suppressed",
                group_key=group_key,
                threshold=threshold,
                suppressed_records=suppressed_count,
                remaining_records=len(filtered),
            )

        return filtered

    # =========================================================================
    # Differential Privacy
    # =========================================================================

    @staticmethod
    def add_laplace_noise(
        value: float,
        sensitivity: float = 1.0,
        epsilon: Optional[float] = None,
    ) -> float:
        """
        Add Laplacian noise for differential privacy.

        The Laplace mechanism is the standard approach for achieving
        ε-differential privacy for numeric queries.

        Args:
            value: True aggregate value
            sensitivity: Query sensitivity (max change from one individual)
            epsilon: Privacy budget (defaults to config)

        Returns:
            Noised value
        """
        if epsilon is None:
            epsilon = settings.DIFFERENTIAL_PRIVACY_EPSILON
        scale = sensitivity / epsilon
        noise = np.random.Generator(np.random.PCG64()).laplace(0, scale)
        return value + noise

    @staticmethod
    def add_gaussian_noise(
        value: float,
        sensitivity: float = 1.0,
        epsilon: Optional[float] = None,
        delta: Optional[float] = None,
    ) -> float:
        """
        Add Gaussian noise for (ε,δ)-differential privacy.

        Provides tighter privacy bounds for high-dimensional queries.

        Args:
            value: True aggregate value
            sensitivity: L2 sensitivity
            epsilon: Privacy budget
            delta: Failure probability

        Returns:
            Noised value
        """
        if epsilon is None:
            epsilon = settings.DIFFERENTIAL_PRIVACY_EPSILON
        if delta is None:
            delta = settings.DIFFERENTIAL_PRIVACY_DELTA

        sigma = (
            sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon
        )
        noise = np.random.Generator(np.random.PCG64()).normal(0, sigma)
        return value + noise

    def anonymize_aggregate(
        self,
        data: Dict[str, Any],
        sensitive_fields: List[str],
        sensitivity: float = 1000.0,
    ) -> Dict[str, Any]:
        """
        Apply differential privacy to sensitive fields in an aggregate result.

        Args:
            data: Aggregate data dictionary
            sensitive_fields: Fields that need noise added
            sensitivity: Query sensitivity for these fields

        Returns:
            Anonymized data dictionary
        """
        anonymized = data.copy()
        for field in sensitive_fields:
            if field in anonymized and isinstance(anonymized[field], (int, float)):
                anonymized[field] = round(
                    self.add_laplace_noise(
                        float(anonymized[field]),
                        sensitivity=sensitivity,
                    ),
                    2,
                )
        return anonymized

    # =========================================================================
    # Temporal Aggregation
    # =========================================================================

    @staticmethod
    def enforce_temporal_minimums(
        granularity: str,
        geography_level: str,
    ) -> bool:
        """
        Enforce minimum temporal granularity based on geography level.

        Rules:
        - Ward-level: minimum weekly aggregation
        - County-level: daily allowed
        - National: daily allowed

        This prevents identification through temporal patterns
        in small geographies.

        Args:
            granularity: Requested time granularity (daily, weekly, monthly)
            geography_level: Geographic level (ward, county, national)

        Returns:
            True if allowed, False if must be aggregated further
        """
        temporal_minimums = {
            "ward": "weekly",
            "sub_county": "weekly",
            "county": "daily",
            "national": "daily",
        }

        minimum = temporal_minimums.get(geography_level, "weekly")
        granularity_order = ["daily", "weekly", "monthly", "quarterly"]

        if granularity_order.index(granularity) < granularity_order.index(minimum):
            return False
        return True

    # =========================================================================
    # Audit Logging
    # =========================================================================

    async def log_data_access(
        self,
        buyer_id: Optional[str],
        api_key_id: Optional[str],
        endpoint: str,
        query_params: Optional[Dict] = None,
        response_size_bytes: Optional[int] = None,
        records_returned: Optional[int] = None,
        processing_time_ms: Optional[float] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> DataAccessLog:
        """
        Log a data access event for audit compliance.

        Every query to the intelligence API is logged. This is required
        for:
        - Kenya Data Protection Act 2019 compliance
        - Buyer contract auditing
        - Security monitoring
        - Usage metering

        Args:
            buyer_id: ID of the buyer making the query
            api_key_id: ID of the API key used
            endpoint: API endpoint called
            query_params: Query parameters (will be sanitized)
            response_size_bytes: Size of response
            records_returned: Number of records returned
            processing_time_ms: Query processing time
            ip_address: Client IP address
            user_agent: Client user agent string
            status_code: HTTP response status
            error_message: Error details if query failed

        Returns:
            Created DataAccessLog entry
        """
        # Sanitize query params — remove any potential PII
        sanitized_params = None
        if query_params:
            sanitized_params = {
                k: v for k, v in query_params.items()
                if k not in ("phone", "name", "email", "user_id")
            }

        log_entry = DataAccessLog(
            buyer_id=buyer_id,
            api_key_id=api_key_id,
            endpoint=endpoint,
            query_params=sanitized_params,
            response_size_bytes=response_size_bytes,
            records_returned=records_returned,
            processing_time_ms=processing_time_ms,
            ip_address=ip_address,
            user_agent=user_agent,
            status_code=status_code,
            error_message=error_message,
        )

        self.db.add(log_entry)
        await self.db.flush()

        logger.info(
            "data_access_logged",
            buyer_id=str(buyer_id),
            endpoint=endpoint,
            records=records_returned,
            status=status_code,
        )

        return log_entry

    # =========================================================================
    # Product Generalization
    # =========================================================================

    @staticmethod
    def generalize_product(product: str, level: int = 1) -> str:
        """
        Generalize a specific product to a broader category.

        Levels:
        - 0: Specific product (e.g., "tomatoes")
        - 1: Sub-category (e.g., "vegetables")
        - 2: Category (e.g., "food")
        - 3: Sector (e.g., "consumer_goods")

        This prevents identification through rare product combinations.

        Args:
            product: Specific product name
            level: Generalization level (0-3)

        Returns:
            Generalized product category
        """
        product_hierarchy = {
            "tomatoes": {1: "vegetables", 2: "food", 3: "consumer_goods"},
            "onions": {1: "vegetables", 2: "food", 3: "consumer_goods"},
            "kale": {1: "vegetables", 2: "food", 3: "consumer_goods"},
            "potatoes": {1: "vegetables", 2: "food", 3: "consumer_goods"},
            "rice": {1: "grains", 2: "food", 3: "consumer_goods"},
            "maize_flour": {1: "grains", 2: "food", 3: "consumer_goods"},
            "sugar": {1: "staples", 2: "food", 3: "consumer_goods"},
            "cooking_oil": {1: "staples", 2: "food", 3: "consumer_goods"},
            "soap": {1: "cleaning", 2: "household", 3: "consumer_goods"},
            "paraffin": {1: "energy", 2: "household", 3: "consumer_goods"},
        }

        if product in product_hierarchy and level in product_hierarchy[product]:
            return product_hierarchy[product][level]
        if level >= 2:
            return "other"
        return product

    # =========================================================================
    # Data Minimization
    # =========================================================================

    # =========================================================================
    # Sync Pipeline Anonymization
    # =========================================================================

    @staticmethod
    def anonymize_for_sync(transaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Anonymize a transaction before sending to backend.

        Privacy rules for the Msaidizi ↔ Angavu Intelligence sync pipeline:

        KEEP: type, category, amount, timestamp, worker_type, dialect, coarse_location
        REMOVE: customer_name, exact_location, personal_notes
        HASH: worker_id (one-way hash for privacy)

        This ensures that raw data leaving the device never contains PII.
        The backend only ever sees anonymized data.

        Args:
            transaction: Raw transaction dictionary from the device

        Returns:
            Anonymized transaction dictionary safe for sync
        """
        import hmac as _hmac

        PII_REMOVE = {
            "customer_name",
            "customer_phone",
            "customer_phone_hash",
            "exact_location",
            "exact_latitude",
            "exact_longitude",
            "gps_coordinates",
            "personal_notes",
            "voice_recording",
            "source_text",
            "mpesa_receipt",
            "national_id",
            "email",
            "date_of_birth",
            "name",
            "phone",
        }

        # Fields to keep (allowlist)
        KEEP_FIELDS = {
            "transaction_type",
            "item",
            "item_category",
            "amount",
            "quantity",
            "unit",
            "unit_price",
            "profit",
            "payment_method",
            "recorded_via",
            "confidence_score",
            "timestamp",
            "location_geohash",
            "worker_type",
            "dialect",
        }

        anonymized = {}
        for key, value in transaction.items():
            if key in PII_REMOVE:
                continue  # Strip PII
            if key in KEEP_FIELDS:
                anonymized[key] = value

        # Coarsen location to geohash-5 (~5km²) for privacy
        if "location_geohash" in anonymized and anonymized["location_geohash"]:
            anonymized["location_geohash"] = anonymized["location_geohash"][:5]

        # Hash worker_id with HMAC-SHA256 (one-way, consistent)
        worker_id = transaction.get("worker_id") or transaction.get("user_id")
        if worker_id:
            salt = settings.DATA_ENCRYPTION_SALT
            anonymized["worker_id_hash"] = _hmac.new(
                salt.encode(),
                str(worker_id).encode(),
                hashlib.sha256,
            ).hexdigest()[:16]

        return anonymized

    @staticmethod
    def anonymize_transaction_batch(
        transactions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Anonymize a batch of transactions for sync.

        Args:
            transactions: List of raw transaction dictionaries

        Returns:
            List of anonymized transaction dictionaries
        """
        return [
            Anonymizer.anonymize_for_sync(txn)
            for txn in transactions
        ]

    @staticmethod
    def minimize_for_export(
        data: Dict[str, Any],
        purpose: str = "intelligence",
    ) -> Dict[str, Any]:
        """
        Apply data minimization — only include fields necessary for purpose.

        Args:
            data: Full data record
            purpose: Purpose of export (intelligence, credit, market)

        Returns:
            Minimized data dictionary
        """
        field_sets = {
            "intelligence": {
                "market_id", "period_start", "period_end",
                "active_businesses", "total_transactions",
                "avg_daily_revenue", "avg_transaction_value",
                "category_breakdown", "payment_methods",
            },
            "credit": {
                "business_hash", "activity_score", "stability_index",
                "growth_trajectory", "avg_daily_revenue",
                "operating_days_per_week", "revenue_consistency",
                "category_risk", "data_points", "confidence",
            },
            "market": {
                "product", "region", "total_volume",
                "avg_daily_volume", "price_range", "day_of_week_pattern",
                "monthly_trend", "vendor_count",
            },
        }

        allowed_fields = field_sets.get(purpose, set())
        if not allowed_fields:
            return data

        return {k: v for k, v in data.items() if k in allowed_fields}
