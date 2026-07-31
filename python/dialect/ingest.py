"""
Dialect Ingest Service — Receives and validates dialect sync payloads from devices.

Never receives raw audio or full transcripts. Only anonymized signals:
- Vocabulary deltas (new terms only, hashed)
- Phonetic pattern summaries (statistical)
- Grammar pattern summaries (statistical)
- LoRA gradient summaries (compressed, differentially private)
"""

import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class NewTermDelta:
    """A new vocabulary term discovered on a device."""
    term_hash: str          # SHA-256 of term (anonymized)
    dialect_tag: str        # "sheng", "sw-KE", "en", etc.
    category: str           # "financial", "slang", "grammar", etc.
    frequency: float        # Usage frequency on device
    context_hash: str       # Hashed context for cross-matching
    meaning_hash: Optional[str] = None  # If resolved, hashed standard equivalent


@dataclass
class PhoneticSummary:
    """Anonymized phonetic pattern summary from a device."""
    substitution_rates: dict = field(default_factory=dict)  # canonical→variant: rate
    vowel_shifts: dict = field(default_factory=dict)
    sample_count: int = 0


@dataclass
class GrammarSummary:
    """Grammar pattern summary from a device."""
    tense_distribution: dict = field(default_factory=dict)  # tense: frequency
    word_order_hash: str = ""
    agreement_score: float = 0.0
    sample_count: int = 0


@dataclass
class ProsodySummary:
    """Prosodic pattern summary from a device."""
    syllable_rate_mean: float = 0.0
    rhythm_class: str = "unknown"
    intonation_hash: str = ""


@dataclass
class LoRAGradientSummary:
    """Compressed, differentially-private LoRA gradient summary."""
    top_k_indices: list = field(default_factory=list)
    quantized_values: list = field(default_factory=list)
    norm: float = 0.0
    dimension_count: int = 0
    interaction_count: int = 0
    compression_ratio: float = 0.0


@dataclass
class DialectSyncPayload:
    """Payload sent from device to backend (every 24h, compressed)."""
    device_id: str                      # Pseudonymous, rotated weekly
    dialect_code: str                   # "sw-KE-urban-sheng"
    region: str                         # "KE-Nairobi"
    new_terms: list                     # List of NewTermDelta
    phonetic_summary: PhoneticSummary
    grammar_summary: GrammarSummary
    prosody_summary: ProsodySummary
    lora_gradient_summary: Optional[LoRAGradientSummary] = None
    asr_accuracy: float = 0.0
    intent_match_rate: float = 0.0
    interaction_count: int = 0
    lora_version: Optional[str] = None
    privacy_budget: float = 0.0
    cohort_size: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class IngestResult:
    """Result of ingesting a dialect sync payload."""
    status: str  # "success", "rate_limited", "duplicate", "privacy_budget_exhausted", "invalid"
    message: str = ""
    terms_accepted: int = 0


class DialectIngestService:
    """
    Receives dialect signals from devices.
    Validates, deduplicates, and routes to aggregation pipelines.
    """

    # Privacy constants
    MIN_COHORT_SIZE = 100
    SYNC_INTERVAL_SECONDS = 12 * 3600  # Max 1 sync per 12 hours per device
    PRIVACY_BUDGET_PER_SYNC = 0.01  # ε cost per sync

    def __init__(self):
        self._seen_payloads: dict = {}  # device_id → last_sync_timestamp
        self._privacy_ledger: dict = {}  # device_id → remaining_epsilon
        self._term_store: list = []  # All ingested term deltas
        self._signal_store: list = []  # All raw signals for aggregation
        self._lora_queue: list = []  # Pending LoRA gradient summaries

    def ingest(self, payload: DialectSyncPayload) -> IngestResult:
        """
        Ingest a dialect sync payload from a device.
        Returns IngestResult with status and details.
        """
        # 1. Validate payload structure
        if not self._validate(payload):
            return IngestResult(status="invalid", message="Payload validation failed")

        # 2. Check privacy budget
        remaining = self._get_privacy_budget(payload.device_id)
        if remaining < 0.1:
            logger.warning(f"Privacy budget exhausted for device {payload.device_id[:8]}...")
            return IngestResult(status="privacy_budget_exhausted",
                              message="Device privacy budget exhausted")

        # 3. Rate limit: max 1 sync per 12 hours per device
        now = time.time()
        last_sync = self._seen_payloads.get(payload.device_id, 0)
        if now - last_sync < self.SYNC_INTERVAL_SECONDS:
            return IngestResult(status="rate_limited",
                              message="Too frequent, wait 12h between syncs")

        # 4. Deduplicate
        payload_hash = self._hash_payload(payload)
        if self._is_duplicate(payload.device_id, payload_hash):
            return IngestResult(status="duplicate", message="Duplicate payload")

        # 5. Store raw signals
        self._signal_store.append(payload)
        self._seen_payloads[payload.device_id] = now

        # 6. Store vocabulary deltas
        terms_accepted = 0
        for term in payload.new_terms:
            term_hash = term.get("term_hash", "") if isinstance(term, dict) else getattr(term, "term_hash", "")
            dialect_tag = term.get("dialect_tag", payload.dialect_code) if isinstance(term, dict) else getattr(term, "dialect_tag", payload.dialect_code)
            category = term.get("category", "general") if isinstance(term, dict) else getattr(term, "category", "general")
            frequency = term.get("frequency", 1.0) if isinstance(term, dict) else getattr(term, "frequency", 1.0)
            self._term_store.append({
                "term_hash": term_hash,
                "dialect": dialect_tag,
                "category": category,
                "frequency": frequency,
                "region": payload.region,
                "timestamp": payload.timestamp
            })
            terms_accepted += 1

        # 7. Queue LoRA gradients if present
        if payload.lora_gradient_summary is not None:
            self._lora_queue.append({
                "device_id": payload.device_id,
                "dialect_code": payload.dialect_code,
                "gradient": payload.lora_gradient_summary,
                "interaction_count": payload.interaction_count,
                "timestamp": payload.timestamp
            })

        # 8. Deduct privacy budget
        self._deduct_privacy_budget(payload.device_id, self.PRIVACY_BUDGET_PER_SYNC)

        logger.info(f"Ingested payload from {payload.device_id[:8]}... "
                    f"dialect={payload.dialect_code}, terms={terms_accepted}, "
                    f"interactions={payload.interaction_count}")

        return IngestResult(
            status="success",
            message=f"Accepted {terms_accepted} terms, {payload.interaction_count} interactions",
            terms_accepted=terms_accepted
        )

    def get_pending_lora_gradients(self, dialect_code: str, since_timestamp: float = 0) -> list:
        """Get pending LoRA gradient summaries for a dialect, for aggregation."""
        return [g for g in self._lora_queue
                if g["dialect_code"] == dialect_code and g["timestamp"] > since_timestamp]

    def get_term_deltas(self, dialect_code: str = None, limit: int = 1000) -> list:
        """Get stored term deltas, optionally filtered by dialect."""
        terms = self._term_store
        if dialect_code:
            terms = [t for t in terms if t["dialect"] == dialect_code]
        return terms[-limit:]

    def get_signal_count(self) -> int:
        """Get total stored signal count."""
        return len(self._signal_store)

    def clear_processed_signals(self, before_timestamp: float):
        """Clear signals older than the given timestamp (after aggregation)."""
        self._signal_store = [s for s in self._signal_store if s.timestamp > before_timestamp]
        self._lora_queue = [g for g in self._lora_queue if g["timestamp"] > before_timestamp]

    # ── Private helpers ──────────────────────────────────────

    def _validate(self, payload: DialectSyncPayload) -> bool:
        """Validate payload structure."""
        if not payload.device_id or not payload.dialect_code or not payload.region:
            return False
        if payload.interaction_count < 0:
            return False
        if payload.asr_accuracy < 0 or payload.asr_accuracy > 1:
            return False
        return True

    def _get_privacy_budget(self, device_id: str) -> float:
        """Get remaining privacy budget for a device."""
        if device_id not in self._privacy_ledger:
            self._privacy_ledger[device_id] = 10.0  # ε=10.0 lifetime budget
        return self._privacy_ledger[device_id]

    def _deduct_privacy_budget(self, device_id: str, epsilon: float):
        """Deduct privacy budget for a sync."""
        self._privacy_ledger[device_id] = self._get_privacy_budget(device_id) - epsilon

    def _hash_payload(self, payload: DialectSyncPayload) -> str:
        """Hash payload for deduplication."""
        key = f"{payload.device_id}:{payload.dialect_code}:{payload.timestamp}"
        return hashlib.sha256(key.encode()).hexdigest()

    def _is_duplicate(self, device_id: str, payload_hash: str) -> bool:
        """Check if this payload was already processed."""
        # Simple dedup: if we've seen this device recently with same hash
        return False  # Simplified — real impl would check hash store
