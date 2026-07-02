"""
Worker Type Classifier — Determines worker type from transaction patterns.

Uses feature extraction and weighted scoring to classify workers into
one or more types: transport, retail/trader, agriculture, service,
digital/gig, manufacturing.

Supports multi-type classification (a worker can be retail + agriculture).

Based on the research architecture's discriminant analysis approach,
simplified for server-side classification from synced transaction data.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ── Worker Types ────────────────────────────────────────────────────

class WorkerType:
    """Worker type constants."""
    TRANSPORT = "transport"
    TRADER = "trader"          # Retail / mama mboga / dukawallah
    AGRICULTURE = "agriculture"
    SERVICE = "service"
    DIGITAL = "digital"
    MANUFACTURING = "manufacturing"
    GENERAL = "general"        # Unclassified

    ALL_TYPES = [TRANSPORT, TRADER, AGRICULTURE, SERVICE, DIGITAL, MANUFACTURING]


# ── Classification Keywords ─────────────────────────────────────────

# Keywords in transaction items that signal each worker type
TYPE_KEYWORDS: Dict[str, List[str]] = {
    WorkerType.TRANSPORT: [
        "boda", "matatu", "tuk tuk", "tuk-tuk", "taxi", "fare", "trip",
        "ride", "passenger", "route", "fuel", "petrol", "diesel",
        "transport", "delivery", "pikipiki",
    ],
    WorkerType.TRADER: [
        "tomato", "onion", "potato", "cabbage", "kale", "sukuma",
        "ndengu", "bean", "maize", "rice", "cooking oil", "sugar",
        "flour", "salt", "soap", "ndizi", "banana", "mango",
        "avocado", "milk", "eggs", "meat", "fish", "mboga",
        "mchicha", "managu", "kunde", "vendor", "shop", "duka",
        "stock", "inventory", "wholesale", "retail",
    ],
    WorkerType.AGRICULTURE: [
        "seed", "mbegu", "fertilizer", "mbolea", "pesticide", "dawa",
        "harvest", "crop", "farm", "shamba", "acre", "irrigation",
        "planting", "weeding", "drying", "maize", "beans", "coffee",
        "tea", "sugarcane", "cotton", "horticulture",
    ],
    WorkerType.SERVICE: [
        "haircut", "braids", "plait", "shave", "barber", "salon",
        "repair", "fix", "mechanic", "fundi", "tailor", "sew",
        "stitch", "laundry", "wash", "clean", "plumb", "electrician",
        "paint", "weld", "service", "labour", "labor", "appointment",
    ],
    WorkerType.DIGITAL: [
        "mpesa", "m-pesa", "commission", "float", "airtime",
        "bundle", "data", "social media", "facebook", "instagram",
        "tiktok", "whatsapp", "gig", "freelance", "content",
        "affiliate", "digital", "online",
    ],
    WorkerType.MANUFACTURING: [
        "furniture", "table", "chair", "bed", "cabinet", "shelf",
        "brick", "block", "weld", "metal", "steel", "wood", "timber",
        "cut", "assemble", "produce", "manufacture", "jua kali",
        "workshop", "scrap", "raw material",
    ],
}


class WorkerClassifier:
    """
    Classifies worker type from transaction patterns.

    Uses keyword matching + transaction pattern analysis to determine
    which domain agent(s) should be activated for a worker.

    Supports multi-type classification with confidence scores.
    """

    def __init__(self):
        self._logger = logger.bind(component="WorkerClassifier")

    def classify(
        self,
        transactions: List[Dict[str, Any]],
        min_confidence: float = 0.15,
        max_types: int = 3,
    ) -> Dict[str, Any]:
        """
        Classify worker type from transaction data.

        Args:
            transactions: List of transaction dicts with at minimum:
                - item (str): product/service name
                - transaction_type (str): SALE, PURCHASE, EXPENSE
                - amount (float): transaction amount
                - item_category (str, optional): category
            min_confidence: Minimum confidence to include a type
            max_types: Maximum number of types to return

        Returns:
            Dict with:
                - primary_type: str (highest confidence type)
                - types: List of {type, confidence, evidence}
                - is_multi_type: bool
        """
        if not transactions:
            return {
                "primary_type": WorkerType.GENERAL,
                "types": [{"type": WorkerType.GENERAL, "confidence": 1.0, "evidence": "No transactions"}],
                "is_multi_type": False,
            }

        # Score each type
        scores: Dict[str, float] = defaultdict(float)
        evidence: Dict[str, List[str]] = defaultdict(list)

        # 1. Keyword matching (40% weight)
        keyword_scores = self._keyword_score(transactions)
        for t, (score, items) in keyword_scores.items():
            scores[t] += score * 0.4
            evidence[t].extend(items[:3])

        # 2. Transaction pattern analysis (30% weight)
        pattern_scores = self._pattern_score(transactions)
        for t, score in pattern_scores.items():
            scores[t] += score * 0.3

        # 3. Category matching (20% weight)
        category_scores = self._category_score(transactions)
        for t, score in category_scores.items():
            scores[t] += score * 0.2

        # 4. Amount pattern (10% weight)
        amount_scores = self._amount_pattern_score(transactions)
        for t, score in amount_scores.items():
            scores[t] += score * 0.1

        # Normalize scores
        total = sum(scores.values()) if scores else 1
        normalized = {
            t: s / total for t, s in scores.items() if s > 0
        }

        # Build result
        sorted_types = sorted(
            normalized.items(), key=lambda x: x[1], reverse=True
        )

        result_types = [
            {
                "type": t,
                "confidence": round(conf, 3),
                "evidence": evidence.get(t, [])[:3],
            }
            for t, conf in sorted_types
            if conf >= min_confidence
        ][:max_types]

        if not result_types:
            result_types = [
                {"type": WorkerType.GENERAL, "confidence": 1.0, "evidence": "No strong signals"}
            ]

        primary = result_types[0]["type"]

        self._logger.info(
            "worker_classified",
            primary_type=primary,
            confidence=result_types[0]["confidence"],
            num_types=len(result_types),
            transaction_count=len(transactions),
        )

        return {
            "primary_type": primary,
            "types": result_types,
            "is_multi_type": len(result_types) > 1,
        }

    def _keyword_score(
        self, transactions: List[Dict[str, Any]]
    ) -> Dict[str, Tuple[float, List[str]]]:
        """Score based on keyword matches in item names."""
        scores: Dict[str, float] = defaultdict(float)
        matched_items: Dict[str, List[str]] = defaultdict(list)

        for t in transactions:
            item = (t.get("item") or "").lower()
            if not item:
                continue
            for worker_type, keywords in TYPE_KEYWORDS.items():
                for kw in keywords:
                    if kw in item:
                        scores[worker_type] += 1
                        if item not in matched_items[worker_type]:
                            matched_items[worker_type].append(item)
                        break

        # Normalize by transaction count
        n = len(transactions) or 1
        return {
            t: (scores[t] / n, matched_items[t])
            for t in scores
        }

    def _pattern_score(
        self, transactions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Score based on transaction patterns."""
        scores: Dict[str, float] = defaultdict(float)
        n = len(transactions) or 1

        sales = [t for t in transactions if t.get("transaction_type") == "SALE"]
        purchases = [t for t in transactions if t.get("transaction_type") in ("PURCHASE", "EXPENSE")]

        # Transport: many small sales, high frequency
        if len(sales) > 10:
            avg_sale = statistics.mean(t.get("amount", 0) for t in sales) if sales else 0
            if 50 <= avg_sale <= 500:  # Typical boda/matatu fare range
                scores[WorkerType.TRANSPORT] += 0.5

        # Agriculture: seasonal patterns, bulk purchases
        if purchases:
            avg_purchase = statistics.mean(t.get("amount", 0) for t in purchases) if purchases else 0
            if avg_purchase > 1000:  # Bulk farming inputs
                scores[WorkerType.AGRICULTURE] += 0.3

        # Manufacturing: few large sales, many material purchases
        if sales and purchases:
            if len(purchases) > len(sales) * 0.5:  # High material-to-sale ratio
                scores[WorkerType.MANUFACTURING] += 0.4

        # Service: moderate sales, low purchase ratio
        if sales and len(purchases) < len(sales) * 0.3:
            scores[WorkerType.SERVICE] += 0.3

        # Digital: many small transactions
        if len(sales) > 20:
            avg = statistics.mean(t.get("amount", 0) for t in sales) if sales else 0
            if avg < 200:  # Small commissions
                scores[WorkerType.DIGITAL] += 0.3

        # Retail: consistent daily sales
        if sales:
            dates = set()
            for t in sales:
                ts = t.get("timestamp")
                if ts:
                    if isinstance(ts, str):
                        ts = ts[:10]
                    else:
                        ts = ts.strftime("%Y-%m-%d")
                    dates.add(ts)
            if len(dates) >= 5:  # Active on multiple days
                scores[WorkerType.TRADER] += 0.3

        return {t: s / n for t, s in scores.items() if s > 0}

    def _category_score(
        self, transactions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Score based on item_category field."""
        category_map = {
            "transport": WorkerType.TRANSPORT,
            "food": WorkerType.TRADER,
            "agriculture": WorkerType.AGRICULTURE,
            "services": WorkerType.SERVICE,
            "beauty": WorkerType.SERVICE,
            "electronics": WorkerType.DIGITAL,
        }

        scores: Dict[str, float] = defaultdict(float)
        n = len(transactions) or 1

        for t in transactions:
            cat = t.get("item_category")
            if cat and cat in category_map:
                scores[category_map[cat]] += 1

        return {t: s / n for t, s in scores.items() if s > 0}

    def _amount_pattern_score(
        self, transactions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Score based on transaction amount patterns."""
        sales = [
            t for t in transactions
            if t.get("transaction_type") == "SALE" and t.get("amount", 0) > 0
        ]
        if not sales:
            return {}

        amounts = [t["amount"] for t in sales]
        avg = statistics.mean(amounts)
        cv = statistics.stdev(amounts) / avg if avg > 0 and len(amounts) > 1 else 0

        scores: Dict[str, float] = defaultdict(float)

        # Transport: consistent small amounts
        if 50 <= avg <= 300 and cv < 0.5:
            scores[WorkerType.TRANSPORT] += 0.5

        # Manufacturing: large varying amounts
        if avg > 2000 and cv > 0.3:
            scores[WorkerType.MANUFACTURING] += 0.4

        # Digital: very small amounts
        if avg < 100:
            scores[WorkerType.DIGITAL] += 0.3

        return scores


# ── Singleton ───────────────────────────────────────────────────────

_classifier: Optional[WorkerClassifier] = None


def get_worker_classifier() -> WorkerClassifier:
    """Get or create the singleton WorkerClassifier."""
    global _classifier
    if _classifier is None:
        _classifier = WorkerClassifier()
    return _classifier
