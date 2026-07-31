"""
Dialect Adapter Registry — Manages versioned LoRA adapters for dialect clusters.

Stores, versions, and distributes dialect-specific LoRA adapters.
Devices can fetch the latest adapter for their dialect cluster,
or get delta updates to minimize bandwidth.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AdapterQuality:
    """Quality metrics for a dialect adapter."""
    wer_reduction: float = 0.0              # WER improvement vs base model
    intent_accuracy_improvement: float = 0.0
    vocabulary_coverage: float = 0.0        # % of dialect terms handled
    evaluated_on_worker_count: int = 0


@dataclass
class DialectAdapter:
    """A versioned LoRA adapter for a specific dialect cluster."""
    adapter_id: str
    dialect_code: str
    cluster_id: str
    base_model: str                         # "whisper-small-v3"
    version: str
    weights: bytes = b""                    # LoRA weights (~5MB)
    weights_compressed: bytes = b""         # Compressed for distribution (~1MB)
    checksum: str = ""
    training_worker_count: int = 0
    round_number: int = 0
    quality: AdapterQuality = field(default_factory=AdapterQuality)
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0                 # Auto-expire after 30 days


class DialectAdapterRegistry:
    """
    Registry for dialect-specific LoRA adapters.
    
    Manages versioning, quality evaluation, and distribution of adapters.
    Adapters are auto-expired after 30 days if not updated.
    """

    ADAPTER_EXPIRY_DAYS = 30
    MIN_QUALITY_WER_REDUCTION = 0.05  # Minimum 5% WER improvement to publish

    def __init__(self):
        # dialect_code → {version → DialectAdapter}
        self._adapters: dict = {}
        # cluster_id → latest adapter_id
        self._latest_by_cluster: dict = {}

    def register(self, adapter: DialectAdapter) -> bool:
        """
        Register a new adapter version.
        Returns True if the adapter was accepted (meets quality threshold).
        """
        # Quality gate
        if adapter.quality.wer_reduction < self.MIN_QUALITY_WER_REDUCTION:
            logger.warning(f"Adapter {adapter.adapter_id} below quality threshold: "
                         f"WER reduction={adapter.quality.wer_reduction:.3f}")
            return False

        # Set expiry
        adapter.expires_at = time.time() + (self.ADAPTER_EXPIRY_DAYS * 86400)

        # Compute checksum
        if adapter.weights:
            adapter.checksum = hashlib.sha256(adapter.weights).hexdigest()

        # Store
        dialect = adapter.dialect_code
        if dialect not in self._adapters:
            self._adapters[dialect] = {}

        self._adapters[dialect][adapter.version] = adapter
        self._latest_by_cluster[adapter.cluster_id] = adapter.adapter_id

        logger.info(f"Registered adapter: {adapter.adapter_id} for {dialect} "
                   f"(v{adapter.version}, WER reduction={adapter.quality.wer_reduction:.3f})")
        return True

    def get_latest_adapter(self, dialect_code: str, cluster_id: str = "") -> Optional[DialectAdapter]:
        """Get the latest adapter for a dialect code or cluster."""
        # Try cluster first
        if cluster_id and cluster_id in self._latest_by_cluster:
            adapter_id = self._latest_by_cluster[cluster_id]
            for versions in self._adapters.values():
                for adapter in versions.values():
                    if adapter.adapter_id == adapter_id and not self._is_expired(adapter):
                        return adapter

        # Try dialect code
        dialect_adapters = self._adapters.get(dialect_code, {})
        if not dialect_adapters:
            return None

        # Get latest non-expired version
        latest = None
        for adapter in dialect_adapters.values():
            if not self._is_expired(adapter):
                if latest is None or adapter.created_at > latest.created_at:
                    latest = adapter

        return latest

    def get_regional_adapter(self, region: str) -> Optional[DialectAdapter]:
        """Get the best adapter for a region (for cold-start)."""
        # Map region to dialect code
        dialect = self._region_to_dialect(region)
        return self.get_latest_adapter(dialect)

    def get_adapter_by_id(self, adapter_id: str) -> Optional[DialectAdapter]:
        """Get an adapter by its ID."""
        for versions in self._adapters.values():
            for adapter in versions.values():
                if adapter.adapter_id == adapter_id:
                    return adapter
        return None

    def active_adapter_count(self) -> int:
        """Get count of active (non-expired) adapters."""
        count = 0
        for versions in self._adapters.values():
            for adapter in versions.values():
                if not self._is_expired(adapter):
                    count += 1
        return count

    def get_all_dialects(self) -> list:
        """Get all dialect codes with registered adapters."""
        return list(self._adapters.keys())

    def cleanup_expired(self):
        """Remove expired adapters."""
        now = time.time()
        for dialect in list(self._adapters.keys()):
            expired = [v for v, a in self._adapters[dialect].items()
                      if self._is_expired(a)]
            for v in expired:
                del self._adapters[dialect][v]
                logger.info(f"Expired adapter: {dialect}/v{v}")
            if not self._adapters[dialect]:
                del self._adapters[dialect]

    def get_registry_stats(self) -> dict:
        """Get registry statistics."""
        total = 0
        active = 0
        for versions in self._adapters.values():
            for adapter in versions.values():
                total += 1
                if not self._is_expired(adapter):
                    active += 1

        return {
            "total_adapters": total,
            "active_adapters": active,
            "dialects_covered": len(self._adapters),
            "clusters_mapped": len(self._latest_by_cluster)
        }

    # ── Private helpers ──────────────────────────────────────

    def _is_expired(self, adapter: DialectAdapter) -> bool:
        """Check if an adapter has expired."""
        return adapter.expires_at > 0 and time.time() > adapter.expires_at

    def _region_to_dialect(self, region: str) -> str:
        """Map a region code to a dialect code."""
        mapping = {
            "KE-Nairobi": "sw-KE-urban",
            "KE-Mombasa": "sw-KE-coastal",
            "TZ-Dar": "sw-TZ-dar",
            "UG-Kampala": "sw-UG",
        }
        return mapping.get(region, "sw-KE-urban")
