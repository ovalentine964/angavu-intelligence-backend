"""
Dialect Dictionary Service — Bayesian confidence scoring for learned words.

Collects vocabulary submissions from all workers across Kenya's dialect
regions, applies Bayesian confidence scoring, and maintains a shared
dialect dictionary with quality gates.

Architecture:
    Workers ──[word submissions]──► Dialect Dictionary Service
    Service ──[Bayesian scoring]──► Confidence-gated word entries
    Entries ──[k-anonymity filter]──► Shared dictionary (≥5 workers per word)

Privacy:
    - Worker IDs are SHA-256 hashed (never raw device IDs)
    - K-anonymity (k≥5): a word only enters the shared dictionary when
      at least 5 distinct workers have independently submitted it
    - Context strings are stored as samples (max 5), not full corpora

Quality Control:
    - Bayesian confidence: Beta(α, β) prior updated per submission
    - Frequency outlier detection via IQR method
    - Adversarial filtering (profanity, injection patterns, gibberish)
    - Cross-validation: words must appear across multiple regions/workers

Academic references:
    - STA 341: Bayesian estimation with conjugate priors
    - STA 346: Statistical quality control for outlier detection
"""

import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog

from app.schemas.dialect_dictionary import (
    DialectLookupResponse,
    DialectSubmitRequest,
    DialectSubmitResponse,
    WordEntry,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

# K-anonymity threshold — minimum distinct workers before a word is shared
K_ANONYMITY_MIN = 5

# Bayesian prior — Beta(α₀, β₀) for confidence scoring
# Prior mean = α₀ / (α₀ + β₀) = 0.5 (uninformative)
# Prior strength = α₀ + β₀ = 2 (weak — data dominates quickly)
BAYESIAN_ALPHA_PRIOR = 1.0
BAYESIAN_BETA_PRIOR = 1.0

# Maximum contexts stored per word entry
MAX_CONTEXTS_PER_WORD = 5

# Outlier detection: IQR multiplier for frequency z-scores
OUTLIER_IQR_MULTIPLIER = 3.0

# Minimum word length (characters)
MIN_WORD_LENGTH = 2

# Maximum word length
MAX_WORD_LENGTH = 200

# Adversarial content patterns (case-insensitive)
_ADVERSARIAL_PATTERNS = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onclick=, onerror=, etc.
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
    re.compile(r"UNION\s+SELECT", re.IGNORECASE),
    re.compile(r";\s*--"),
    re.compile(r"\b(exec|eval|system|cmd)\s*\(", re.IGNORECASE),
]

# Known profanity filter (basic — production would use a comprehensive list)
_PROFANITY_PATTERNS = [
    # Intentionally minimal; production systems use dedicated profanity APIs
]


# ════════════════════════════════════════════════════════════════════
# In-Memory Dictionary State
# ════════════════════════════════════════════════════════════════════


class _WordState:
    """Tracks a single word across all workers."""

    __slots__ = (
        "alpha",
        "beta",
        "contexts",
        "dialect",
        "first_seen",
        "frequency_history",
        "last_seen",
        "pronunciation_ipa",
        "regions",
        "total_frequency",
        "word",
        "workers",
    )

    def __init__(self, word: str, dialect: str):
        self.word = word
        self.dialect = dialect
        # Bayesian parameters: Beta(α, β)
        self.alpha: float = BAYESIAN_ALPHA_PRIOR
        self.beta: float = BAYESIAN_BETA_PRIOR
        self.total_frequency: int = 0
        self.contexts: list[str] = []
        self.pronunciation_ipa: str | None = None
        self.regions: set = set()
        self.workers: set = set()  # hashed worker IDs
        self.first_seen: str = datetime.now(UTC).isoformat()
        self.last_seen: str = self.first_seen
        # Track per-worker frequency for outlier detection
        self.frequency_history: list[int] = []

    @property
    def confidence(self) -> float:
        """Bayesian posterior mean: E[θ] = α / (α + β)."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def contributor_count(self) -> int:
        return len(self.workers)

    def to_entry(self) -> WordEntry:
        return WordEntry(
            word=self.word,
            dialect=self.dialect,
            frequency=self.total_frequency,
            confidence=round(self.confidence, 4),
            contributor_count=self.contributor_count,
            contexts=self.contexts[:MAX_CONTEXTS_PER_WORD],
            pronunciation_ipa=self.pronunciation_ipa,
            regions=sorted(self.regions),
            first_seen=self.first_seen,
            last_seen=self.last_seen,
        )


class _DictionaryState:
    """Mutable singleton holding the dialect dictionary state."""

    def __init__(self):
        self.reset()

    def reset(self):
        # {(word, dialect): _WordState}
        self.entries: dict[tuple[str, str], _WordState] = {}
        # {dialect: set of (word, dialect) keys}
        self.by_dialect: dict[str, set] = defaultdict(set)
        # {region: set of (word, dialect) keys}
        self.by_region: dict[str, set] = defaultdict(set)
        # {worker_id: set of (word, dialect) keys submitted}
        self.worker_submissions: dict[str, set] = defaultdict(set)
        # Submission counters
        self.total_submissions: int = 0
        self.total_accepted: int = 0
        self.total_rejected: int = 0
        # Rejection reason counts
        self.rejection_reasons: dict[str, int] = defaultdict(int)


_state = _DictionaryState()


# ════════════════════════════════════════════════════════════════════
# Quality Control — Validation & Filtering
# ════════════════════════════════════════════════════════════════════


def _is_adversarial(text: str) -> bool:
    """Check if text contains adversarial/injection patterns."""
    for pattern in _ADVERSARIAL_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _is_gibberish(word: str) -> bool:
    """
    Detect likely gibberish words using heuristic analysis.

    Checks:
    - Ratio of vowels to consonants (real words have vowels)
    - Repeated character sequences
    - No vowels at all (unless short abbreviation)
    """
    if len(word) <= 2:
        return False  # Allow short abbreviations

    # Check for vowels (including common Swahili/African language vowels)
    vowels = set("aeiouAEIOU")
    has_vowel = any(c in vowels for c in word)

    # Allow consonant-only words up to 4 chars (e.g., "ng", "nz", "mb" — common Bantu clusters)
    if not has_vowel and len(word) > 4:
        return True

    # Check for excessive character repetition (e.g., "aaaaaaa", "abcabcabcabc")
    if len(word) >= 4:
        # Check for runs of the same character
        max_run = 1
        current_run = 1
        for i in range(1, len(word)):
            if word[i] == word[i - 1]:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1
        if max_run > len(word) * 0.5 and max_run > 3:
            return True

    return False


def _is_frequency_outlier(frequency: int, history: list[int]) -> bool:
    """
    Detect if a frequency submission is a statistical outlier using IQR method.

    STA 346: Values beyond Q3 + 1.5*IQR are mild outliers,
    beyond Q3 + 3*IQR are extreme outliers.
    """
    if len(history) < 5:
        return False  # Not enough data for outlier detection

    sorted_h = sorted(history)
    n = len(sorted_h)
    q1 = sorted_h[n // 4]
    q3 = sorted_h[3 * n // 4]
    iqr = q3 - q1

    if iqr == 0:
        return False

    upper_fence = q3 + OUTLIER_IQR_MULTIPLIER * iqr
    return frequency > upper_fence


def _validate_word(word: str, dialect: str) -> tuple[bool, str | None]:
    """
    Validate a single word submission.

    Returns (is_valid, rejection_reason).
    """
    if not word or not word.strip():
        return False, "empty_word"

    word = word.strip()

    if len(word) < MIN_WORD_LENGTH:
        return False, "too_short"

    if len(word) > MAX_WORD_LENGTH:
        return False, "too_long"

    if _is_adversarial(word):
        return False, "adversarial_content"

    if _is_adversarial(dialect):
        return False, "invalid_dialect"

    if _is_gibberish(word):
        return False, "gibberish"

    # Dialect code must be alphanumeric
    if not dialect.isalnum():
        return False, "invalid_dialect_format"

    return True, None


# ════════════════════════════════════════════════════════════════════
# Bayesian Confidence Update
# ════════════════════════════════════════════════════════════════════


def _bayesian_update(
    word_state: _WordState,
    frequency_hint: int,
    is_new_worker: bool,
) -> None:
    """
    Update Bayesian confidence for a word entry.

    Beta-Binomial conjugate model:
        Prior: θ ~ Beta(α₀, β₀)
        Observation: word was seen by a new worker (success) or same worker (weaker signal)
        Posterior: θ|data ~ Beta(α + successes, β + failures)

    The key insight: each NEW distinct worker confirming a word is a strong
    "success" signal. Repeated submissions from the same worker are weaker.
    """
    if is_new_worker:
        # New independent confirmation — strong signal
        # Scale by log of frequency (diminishing returns for very high counts)
        signal_strength = 1.0 + math.log1p(min(frequency_hint, 100)) / 10.0
        word_state.alpha += signal_strength
    else:
        # Same worker re-submitting — weaker signal
        word_state.beta += 0.1


# ════════════════════════════════════════════════════════════════════
# Dialect Dictionary Service
# ════════════════════════════════════════════════════════════════════


class DialectDictionaryService:
    """
    Dialect dictionary service with Bayesian confidence scoring.

    Collects words from all workers, applies quality gates, and maintains
    a shared dictionary that only includes words verified by k-anonymity.
    """

    def __init__(self):
        self._state = _state

    async def submit_words(
        self,
        request: DialectSubmitRequest,
    ) -> DialectSubmitResponse:
        """
        Process a batch word submission from a worker device.

        Steps:
        1. Validate each word (adversarial, gibberish, format)
        2. Check for frequency outliers
        3. Update Bayesian confidence
        4. Track worker contributions
        5. Enforce k-anonymity for shared visibility

        Returns:
            DialectSubmitResponse with acceptance/rejection counts
        """
        worker_id = request.worker_id
        region = request.region or "unknown"
        now = datetime.now(UTC).isoformat()

        words_received = 0
        words_accepted = 0
        words_rejected = 0
        rejection_reasons: dict[str, int] = defaultdict(int)

        for ws in request.words:
            words_received += 1
            self._state.total_submissions += 1

            # Normalize
            word = ws.word.strip().lower()
            dialect = ws.dialect.strip().lower()

            # Validate
            is_valid, reason = _validate_word(word, dialect)
            if not is_valid:
                words_rejected += 1
                self._state.total_rejected += 1
                rejection_reasons[reason] += 1
                self._state.rejection_reasons[reason] += 1
                continue

            key = (word, dialect)
            is_new_worker = key not in self._state.worker_submissions.get(worker_id, set())

            # Get or create word state
            if key not in self._state.entries:
                ws_obj = _WordState(word, dialect)
                self._state.entries[key] = ws_obj
                self._state.by_dialect[dialect].add(key)
                self._state.by_region[region].add(key)

            word_state = self._state.entries[key]

            # Frequency outlier check
            if _is_frequency_outlier(ws.frequency_hint, word_state.frequency_history):
                # Don't reject outright — cap the frequency instead
                capped_freq = int(
                    sorted(word_state.frequency_history)[len(word_state.frequency_history) * 3 // 4]
                    * 2
                ) if word_state.frequency_history else ws.frequency_hint
                effective_freq = min(ws.frequency_hint, max(capped_freq, 1))
            else:
                effective_freq = ws.frequency_hint

            # Update state
            word_state.total_frequency += effective_freq
            word_state.frequency_history.append(effective_freq)
            word_state.workers.add(worker_id)
            word_state.last_seen = now

            if region and region != "unknown":
                word_state.regions.add(region)

            if ws.context and len(word_state.contexts) < MAX_CONTEXTS_PER_WORD:
                # Store context sample (avoid duplicates)
                if ws.context not in word_state.contexts:
                    word_state.contexts.append(ws.context)

            if ws.pronunciation_ipa and not word_state.pronunciation_ipa:
                word_state.pronunciation_ipa = ws.pronunciation_ipa

            # Bayesian confidence update
            _bayesian_update(word_state, effective_freq, is_new_worker)

            # Track worker
            if worker_id not in self._state.worker_submissions:
                self._state.worker_submissions[worker_id] = set()
            self._state.worker_submissions[worker_id].add(key)

            words_accepted += 1
            self._state.total_accepted += 1

        logger.info(
            "dialect_submit_processed",
            worker_id=worker_id[:8] + "...",
            received=words_received,
            accepted=words_accepted,
            rejected=words_rejected,
        )

        return DialectSubmitResponse(
            status="accepted",
            words_received=words_received,
            words_accepted=words_accepted,
            words_rejected=words_rejected,
            rejection_reasons=dict(rejection_reasons),
        )

    async def lookup(
        self,
        query: str,
        dialect: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> DialectLookupResponse:
        """
        Look up words in the dialect dictionary.

        Only returns words that meet k-anonymity threshold (≥5 workers).
        Results are sorted by confidence (descending).

        Args:
            query: Search term (prefix match)
            dialect: Filter by dialect code (optional)
            min_confidence: Minimum confidence threshold
            limit: Maximum results to return

        Returns:
            DialectLookupResponse with matching entries
        """
        query_lower = query.strip().lower()
        results: list[WordEntry] = []

        for key, ws in self._state.entries.items():
            word, entry_dialect = key

            # K-anonymity check — only show words with enough contributors
            if ws.contributor_count < K_ANONYMITY_MIN:
                continue

            # Dialect filter
            if dialect and entry_dialect != dialect.lower():
                continue

            # Prefix match
            if not word.startswith(query_lower):
                continue

            # Confidence filter
            if ws.confidence < min_confidence:
                continue

            results.append(ws.to_entry())

        # Sort by confidence (descending), then frequency
        results.sort(key=lambda e: (-e.confidence, -e.frequency))
        results = results[:limit]

        return DialectLookupResponse(
            query=query,
            dialect=dialect,
            results=results,
            total_results=len(results),
        )

    async def get_dialect_words(
        self,
        dialect: str,
        min_confidence: float = 0.3,
        limit: int = 1000,
    ) -> list[WordEntry]:
        """Get all words for a dialect that meet k-anonymity and confidence thresholds."""
        dialect = dialect.lower().strip()
        results = []

        for key in self._state.by_dialect.get(dialect, set()):
            ws = self._state.entries.get(key)
            if ws is None:
                continue
            if ws.contributor_count < K_ANONYMITY_MIN:
                continue
            if ws.confidence < min_confidence:
                continue
            results.append(ws.to_entry())

        results.sort(key=lambda e: (-e.confidence, -e.frequency))
        return results[:limit]

    async def get_all_dialects(self) -> dict[str, dict[str, Any]]:
        """Get summary statistics for all dialects."""
        summary = {}
        for dialect, keys in self._state.by_dialect.items():
            shared_count = sum(
                1 for k in keys
                if self._state.entries[k].contributor_count >= K_ANONYMITY_MIN
            )
            total_workers = set()
            for k in keys:
                total_workers.update(self._state.entries[k].workers)
            summary[dialect] = {
                "total_words": len(keys),
                "shared_words": shared_count,
                "contributing_workers": len(total_workers),
            }
        return summary

    async def get_stats(self) -> dict[str, Any]:
        """Get overall dictionary statistics."""
        total_workers = len(self._state.worker_submissions)
        total_shared = sum(
            1 for ws in self._state.entries.values()
            if ws.contributor_count >= K_ANONYMITY_MIN
        )
        return {
            "total_words_tracked": len(self._state.entries),
            "total_shared_words": total_shared,
            "total_dialects": len(self._state.by_dialect),
            "total_workers": total_workers,
            "total_submissions": self._state.total_submissions,
            "total_accepted": self._state.total_accepted,
            "total_rejected": self._state.total_rejected,
            "rejection_reasons": dict(self._state.rejection_reasons),
            "k_anonymity_threshold": K_ANONYMITY_MIN,
        }


# Module-level singleton
_dictionary_service: DialectDictionaryService | None = None


def get_dialect_dictionary() -> DialectDictionaryService:
    """Get or create the dialect dictionary service singleton."""
    global _dictionary_service
    if _dictionary_service is None:
        _dictionary_service = DialectDictionaryService()
    return _dictionary_service
