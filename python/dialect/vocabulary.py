"""
Vocabulary Aggregator — Aggregates dialect vocabulary from multiple devices.

Receives anonymized vocabulary deltas, cross-references across workers,
and builds authoritative dialect dictionaries.

Sheng vocabulary is treated as a first-class dialect with its own tracking
and community-driven updates.
"""

import logging
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AggregatedTerm:
    """A term that has been seen across multiple workers."""
    term_hash: str
    dialect: str
    category: str
    worker_count: int          # How many workers use this term
    total_frequency: float     # Sum of frequencies across workers
    mean_frequency: float      # Average frequency per worker
    standard_form_hash: Optional[str] = None  # Resolved standard equivalent
    first_seen: float = 0.0
    last_seen: float = 0.0
    verified: bool = False     # Confirmed by 10+ workers or linguist


class VocabularyAggregator:
    """
    Aggregates vocabulary terms from device sync payloads.
    
    Terms seen by 10+ workers are promoted to "official" dialect vocabulary.
    Sheng vocabulary is tracked separately with faster promotion thresholds
    (5 workers) due to its rapid evolution.
    """

    # Promotion thresholds
    MIN_WORKERS_FOR_PROMOTION = 10
    SHENG_MIN_WORKERS = 5  # Lower threshold for Sheng (evolves faster)
    VERIFICATION_THRESHOLD = 20  # Workers needed for "verified" status

    def __init__(self):
        # dialect → term_hash → AggregatedTerm
        self._term_store: dict = defaultdict(dict)
        # dialect → list of new terms this period
        self._new_terms_period: dict = defaultdict(list)

    def ingest_terms(self, terms: list, dialect_code: str, region: str = ""):
        """
        Ingest vocabulary deltas from a device sync payload.
        
        Args:
            terms: List of dicts with term_hash, category, frequency
            dialect_code: The dialect these terms belong to
            region: Geographic region
        """
        import time
        now = time.time()

        for term_data in terms:
            term_hash = term_data.get("term_hash", "")
            category = term_data.get("category", "general")
            frequency = term_data.get("frequency", 1.0)

            if not term_hash:
                continue

            dialect_terms = self._term_store[dialect_code]

            if term_hash in dialect_terms:
                # Update existing term
                existing = dialect_terms[term_hash]
                existing.worker_count += 1
                existing.total_frequency += frequency
                existing.mean_frequency = existing.total_frequency / existing.worker_count
                existing.last_seen = now

                # Check for promotion
                threshold = (self.SHENG_MIN_WORKERS if "sheng" in dialect_code
                           else self.MIN_WORKERS_FOR_PROMOTION)
                if existing.worker_count >= threshold and not existing.verified:
                    existing.verified = True
                    self._new_terms_period[dialect_code].append(term_hash)
                    logger.info(f"Term promoted: {term_hash[:16]}... in {dialect_code} "
                              f"({existing.worker_count} workers)")
            else:
                # New term
                dialect_terms[term_hash] = AggregatedTerm(
                    term_hash=term_hash,
                    dialect=dialect_code,
                    category=category,
                    worker_count=1,
                    total_frequency=frequency,
                    mean_frequency=frequency,
                    first_seen=now,
                    last_seen=now
                )

    def get_promoted_terms(self, dialect_code: str = None) -> list:
        """Get terms that have been promoted (seen by threshold+ workers)."""
        promoted = []
        dialects = [dialect_code] if dialect_code else list(self._term_store.keys())

        for dialect in dialects:
            for term_hash, term in self._term_store[dialect].items():
                if term.verified:
                    promoted.append({
                        "term_hash": term_hash,
                        "dialect": dialect,
                        "category": term.category,
                        "worker_count": term.worker_count,
                        "mean_frequency": term.mean_frequency
                    })

        return promoted

    def get_dialect_size(self, dialect_code: str) -> int:
        """Get the number of tracked terms for a dialect."""
        return len(self._term_store.get(dialect_code, {}))

    def get_new_terms_this_period(self, dialect_code: str = None) -> list:
        """Get terms that were newly promoted this period."""
        if dialect_code:
            return self._new_terms_period.get(dialect_code, [])
        return {k: v for k, v in self._new_terms_period.items() if v}

    def get_all_dialects(self) -> list:
        """Get all tracked dialect codes."""
        return list(self._term_store.keys())

    def get_dialect_stats(self) -> dict:
        """Get statistics for all dialects."""
        stats = {}
        for dialect, terms in self._term_store.items():
            verified_count = sum(1 for t in terms.values() if t.verified)
            stats[dialect] = {
                "total_terms": len(terms),
                "verified_terms": verified_count,
                "pending_terms": len(terms) - verified_count,
                "total_workers": sum(t.worker_count for t in terms.values())
            }
        return stats

    def aggregate_daily(self) -> list:
        """
        Run daily aggregation. Returns list of newly promoted terms
        for KnowledgeGraph integration.
        """
        all_promoted = []
        for dialect in self._term_store:
            promoted = self.get_promoted_terms(dialect)
            all_promoted.extend(promoted)

        # Clear the new terms queue
        self._new_terms_period.clear()

        logger.info(f"Daily aggregation: {len(all_promoted)} total promoted terms across "
                   f"{len(self._term_store)} dialects")
        return all_promoted

    def archive_stale_terms(self, dialect_code: str, stale_hashes: list):
        """Archive terms that are no longer used (dialect drift)."""
        dialect_terms = self._term_store.get(dialect_code, {})
        for h in stale_hashes:
            if h in dialect_terms:
                del dialect_terms[h]
                logger.info(f"Archived stale term: {h[:16]}... from {dialect_code}")
