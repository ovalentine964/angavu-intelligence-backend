"""
Model Distribution Service — Delta updates for on-device dialect models.

Packages learned dialect data from the LanguageAggregator into compact,
versioned models that can be distributed to worker devices. Supports:
- Delta updates (only new/changed words since client's version)
- Full model downloads (for fresh installs)
- Version tracking with semantic versioning
- SHA-256 checksums for integrity verification
- Compressed payloads for bandwidth efficiency

Distribution flow:
    Language Aggregator ──[aggregated dialect data]──► Model Distribution
    Model Distribution ──[delta/full packaging]──► Worker Devices

Version scheme: MAJOR.MINOR.PATCH
- MAJOR: Breaking schema changes (new fields required by clients)
- MINOR: New words added (backward-compatible)
- PATCH: Confidence/frequency updates, removed low-quality words

Delta update logic:
    1. Compare client's version to server's latest
    2. Compute diff: new words, updated words, removed words
    3. Package diff as compact delta payload
    4. Client applies delta to local dictionary
"""

import gzip
import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.schemas.dialect_dictionary import (
    DeltaUpdatePayload,
    DialectModelVersion,
    FullModelPayload,
    ModelDistributionResponse,
    WordEntry,
)
from app.services.language_aggregator import get_language_aggregator
from app.services.dialect_dictionary import get_dialect_dictionary

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

# Model version — starts at 1.0.0 per dialect
MODEL_MAJOR = 1
MODEL_MINOR = 0
MODEL_PATCH = 0

# Maximum words per delta update (to keep payloads small)
MAX_DELTA_WORDS = 2000

# Minimum confidence for inclusion in distributed models
MIN_CONFIDENCE_FOR_DISTRIBUTION = 0.3


# ════════════════════════════════════════════════════════════════════
# Version Parsing
# ════════════════════════════════════════════════════════════════════


def _parse_version(version: str) -> Tuple[int, int, int]:
    """Parse 'MAJOR.MINOR.PATCH' into (major, minor, patch)."""
    try:
        parts = version.lstrip("v").split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return (0, 0, 0)


def _format_version(major: int, minor: int, patch: int) -> str:
    """Format version tuple as 'MAJOR.MINOR.PATCH'."""
    return f"{major}.{minor}.{patch}"


def _is_newer(server_version: str, client_version: str) -> bool:
    """Check if server version is newer than client version."""
    return _parse_version(server_version) > _parse_version(client_version)


def _compute_checksum(data: Any) -> str:
    """Compute SHA-256 checksum of data."""
    if isinstance(data, str):
        payload = data.encode("utf-8")
    else:
        payload = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ════════════════════════════════════════════════════════════════════
# Model Distribution State
# ════════════════════════════════════════════════════════════════════


class _ModelState:
    """Tracks distributed model versions per dialect."""

    def __init__(self):
        # {dialect: {version: snapshot_of_words}}
        self.version_snapshots: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        # {dialect: current_version}
        self.current_versions: Dict[str, str] = {}
        # {dialect: {version: checksum}}
        self.checksums: Dict[str, Dict[str, str]] = defaultdict(dict)
        # {dialect: {version: created_at}}
        self.created_at: Dict[str, Dict[str, str]] = defaultdict(dict)
        # {dialect: {version: word_count}}
        self.word_counts: Dict[str, Dict[str, int]] = defaultdict(dict)


_model_state = _ModelState()


# ════════════════════════════════════════════════════════════════════
# Model Distribution Service
# ════════════════════════════════════════════════════════════════════


class ModelDistributionService:
    """
    Packages learned dialect data for on-device consumption.

    Manages versioned dialect models with delta update support.
    """

    def __init__(self):
        self._state = _model_state
        self._aggregator = get_language_aggregator()
        self._dict = get_dialect_dictionary()

    async def publish_dialect_model(self, dialect: str) -> Optional[DialectModelVersion]:
        """
        Publish a new version of a dialect model.

        Takes the latest aggregated dialect data from the LanguageAggregator,
        packages it as a versioned model, and stores a snapshot for delta
        computation.

        Version is auto-incremented (MINOR for new words, PATCH for updates).

        Returns:
            DialectModelVersion if published, None if no new data
        """
        dialect = dialect.lower().strip()

        # Get aggregated words for this dialect
        words = await self._dict.get_dialect_words(
            dialect,
            min_confidence=MIN_CONFIDENCE_FOR_DISTRIBUTION,
        )

        if not words:
            logger.info("model_publish_no_words", dialect=dialect)
            return None

        # Build current word map
        current_words = {}
        for w in words:
            if w.contributor_count >= 5:  # k-anonymity
                current_words[w.word] = {
                    "word": w.word,
                    "dialect": w.dialect,
                    "frequency": w.frequency,
                    "confidence": w.confidence,
                    "contributor_count": w.contributor_count,
                    "contexts": w.contexts[:3],
                    "pronunciation_ipa": w.pronunciation_ipa,
                    "regions": w.regions,
                }

        if not current_words:
            return None

        # Determine version bump
        current_version = self._state.current_versions.get(dialect, _format_version(MODEL_MAJOR, MODEL_MINOR, MODEL_PATCH))
        major, minor, patch = _parse_version(current_version)

        previous_snapshot = self._state.version_snapshots.get(dialect, {}).get(current_version, {})

        # Count new vs updated words
        new_words = set(current_words.keys()) - set(previous_snapshot.keys())
        updated_words = set()
        for w in set(current_words.keys()) & set(previous_snapshot.keys()):
            if current_words[w]["frequency"] != previous_snapshot[w].get("frequency"):
                updated_words.add(w)

        if new_words:
            minor += 1
            patch = 0
        elif updated_words:
            patch += 1
        else:
            # No changes — don't publish
            return None

        new_version = _format_version(major, minor, patch)
        checksum = _compute_checksum(current_words)
        now = datetime.now(timezone.utc).isoformat()

        # Store snapshot
        self._state.version_snapshots[dialect][new_version] = current_words
        self._state.current_versions[dialect] = new_version
        self._state.checksums[dialect][new_version] = checksum
        self._state.created_at[dialect][new_version] = now
        self._state.word_counts[dialect][new_version] = len(current_words)

        version_info = DialectModelVersion(
            dialect=dialect,
            version=new_version,
            word_count=len(current_words),
            created_at=now,
            checksum=checksum,
        )

        logger.info(
            "dialect_model_published",
            dialect=dialect,
            version=new_version,
            total_words=len(current_words),
            new_words=len(new_words),
            updated_words=len(updated_words),
        )

        return version_info

    async def get_delta_update(
        self,
        dialect: str,
        client_version: str,
    ) -> Optional[DeltaUpdatePayload]:
        """
        Compute a delta update between client's version and server's latest.

        Returns only new/changed/removed words — not the full dictionary.
        This minimizes bandwidth for on-device updates.

        Args:
            dialect: Dialect code
            client_version: Client's current model version

        Returns:
            DeltaUpdatePayload if an update is available, None otherwise
        """
        dialect = dialect.lower().strip()
        latest_version = self._state.current_versions.get(dialect)

        if not latest_version:
            return None

        if not _is_newer(latest_version, client_version):
            return None  # Client already up to date

        latest_snapshot = self._state.version_snapshots.get(dialect, {}).get(latest_version, {})
        client_snapshot = self._state.version_snapshots.get(dialect, {}).get(client_version, {})

        # If we don't have the client's snapshot, return a full model instead
        if not client_snapshot:
            return None  # Caller should request full model

        # Compute diff
        latest_words = set(latest_snapshot.keys())
        client_words = set(client_snapshot.keys())

        new_word_keys = latest_words - client_words
        removed_word_keys = client_words - latest_words
        common_words = latest_words & client_words

        # Find updated words (frequency or confidence changed)
        updated_word_keys = set()
        for w in common_words:
            old = client_snapshot[w]
            new = latest_snapshot[w]
            if (old.get("frequency") != new.get("frequency") or
                    old.get("confidence") != new.get("confidence")):
                updated_word_keys.add(w)

        # Build delta payload (capped at MAX_DELTA_WORDS)
        new_entries = []
        for w in sorted(new_word_keys)[:MAX_DELTA_WORDS]:
            data = latest_snapshot[w]
            new_entries.append(WordEntry(
                word=data["word"],
                dialect=data["dialect"],
                frequency=data["frequency"],
                confidence=data["confidence"],
                contributor_count=data["contributor_count"],
                contexts=data.get("contexts", []),
                pronunciation_ipa=data.get("pronunciation_ipa"),
                regions=data.get("regions", []),
            ))

        updated_entries = []
        for w in sorted(updated_word_keys):
            if len(new_entries) + len(updated_entries) >= MAX_DELTA_WORDS:
                break
            data = latest_snapshot[w]
            updated_entries.append(WordEntry(
                word=data["word"],
                dialect=data["dialect"],
                frequency=data["frequency"],
                confidence=data["confidence"],
                contributor_count=data["contributor_count"],
                contexts=data.get("contexts", []),
                pronunciation_ipa=data.get("pronunciation_ipa"),
                regions=data.get("regions", []),
            ))

        removed = sorted(removed_word_keys)

        checksum = _compute_checksum({
            "new": [e.word for e in new_entries],
            "updated": [e.word for e in updated_entries],
            "removed": removed,
        })

        # Estimate compressed size
        payload_dict = {
            "new_words": [e.model_dump() for e in new_entries],
            "updated_words": [e.model_dump() for e in updated_entries],
            "removed_words": removed,
        }
        raw_json = json.dumps(payload_dict).encode("utf-8")
        compressed = gzip.compress(raw_json)
        compressed_size = len(compressed)

        delta = DeltaUpdatePayload(
            dialect=dialect,
            base_version=client_version,
            target_version=latest_version,
            new_words=new_entries,
            updated_words=updated_entries,
            removed_words=removed,
            checksum=checksum,
            compressed_size_bytes=compressed_size,
        )

        logger.info(
            "delta_computed",
            dialect=dialect,
            base=client_version,
            target=latest_version,
            new=len(new_entries),
            updated=len(updated_entries),
            removed=len(removed),
            size_bytes=compressed_size,
        )

        return delta

    async def get_full_model(self, dialect: str) -> Optional[FullModelPayload]:
        """
        Get the full dialect model (for fresh installs or version mismatches).

        Returns the complete word dictionary for a dialect.
        """
        dialect = dialect.lower().strip()
        version = self._state.current_versions.get(dialect)

        if not version:
            # Try to publish first
            version_info = await self.publish_dialect_model(dialect)
            if not version_info:
                return None
            version = version_info.version

        snapshot = self._state.version_snapshots.get(dialect, {}).get(version, {})
        if not snapshot:
            return None

        words = []
        for data in snapshot.values():
            words.append(WordEntry(
                word=data["word"],
                dialect=data["dialect"],
                frequency=data["frequency"],
                confidence=data["confidence"],
                contributor_count=data["contributor_count"],
                contexts=data.get("contexts", []),
                pronunciation_ipa=data.get("pronunciation_ipa"),
                regions=data.get("regions", []),
            ))

        # Sort by confidence descending
        words.sort(key=lambda w: (-w.confidence, -w.frequency))

        checksum = self._state.checksums.get(dialect, {}).get(version, "")
        raw_json = json.dumps([w.model_dump() for w in words]).encode("utf-8")
        compressed_size = len(gzip.compress(raw_json))

        return FullModelPayload(
            dialect=dialect,
            version=version,
            words=words,
            checksum=checksum,
            total_words=len(words),
            compressed_size_bytes=compressed_size,
        )

    async def check_version(
        self,
        dialect: str,
        client_version: str,
    ) -> Dict[str, Any]:
        """
        Lightweight version check — returns whether an update is available.

        Devices poll this endpoint before deciding to download.
        """
        dialect = dialect.lower().strip()
        latest_version = self._state.current_versions.get(dialect)

        if not latest_version:
            return {
                "update_available": False,
                "current_version": client_version,
                "latest_version": client_version,
                "reason": "no_model_available",
            }

        update_available = _is_newer(latest_version, client_version)
        word_count = self._state.word_counts.get(dialect, {}).get(latest_version, 0)

        return {
            "update_available": update_available,
            "current_version": client_version,
            "latest_version": latest_version,
            "word_count": word_count,
            "download_url": f"/api/v1/dialect/model/{dialect}" if update_available else None,
            "delta_url": f"/api/v1/dialect/model/{dialect}/delta?from={client_version}" if update_available else None,
        }

    async def list_models(self) -> List[DialectModelVersion]:
        """List all published dialect models with their latest versions."""
        models = []
        for dialect, version in self._state.current_versions.items():
            models.append(DialectModelVersion(
                dialect=dialect,
                version=version,
                word_count=self._state.word_counts.get(dialect, {}).get(version, 0),
                created_at=self._state.created_at.get(dialect, {}).get(version, ""),
                checksum=self._state.checksums.get(dialect, {}).get(version, ""),
            ))
        return models

    async def get_version_history(self, dialect: str) -> List[Dict[str, Any]]:
        """Get version history for a dialect model."""
        dialect = dialect.lower().strip()
        history = []

        for version in sorted(
            self._state.version_snapshots.get(dialect, {}).keys(),
            key=lambda v: _parse_version(v),
        ):
            history.append({
                "version": version,
                "word_count": self._state.word_counts.get(dialect, {}).get(version, 0),
                "checksum": self._state.checksums.get(dialect, {}).get(version, ""),
                "created_at": self._state.created_at.get(dialect, {}).get(version, ""),
            })

        return history

    async def auto_publish_all(self) -> Dict[str, Any]:
        """
        Auto-publish models for all dialects with new data.

        Called periodically (e.g., after aggregation) to keep
        distributed models up to date.
        """
        all_dialects = list(self._dict._state.by_dialect.keys())
        published = {}

        for dialect in all_dialects:
            version_info = await self.publish_dialect_model(dialect)
            if version_info:
                published[dialect] = {
                    "version": version_info.version,
                    "word_count": version_info.word_count,
                    "checksum": version_info.checksum,
                }

        return {
            "status": "ok",
            "dialects_published": len(published),
            "published": published,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Module-level singleton
_distribution_service: Optional[ModelDistributionService] = None


def get_model_distribution() -> ModelDistributionService:
    """Get or create the model distribution service singleton."""
    global _distribution_service
    if _distribution_service is None:
        _distribution_service = ModelDistributionService()
    return _distribution_service
