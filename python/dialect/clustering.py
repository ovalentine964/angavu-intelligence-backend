"""
Dialect Cluster Engine — Groups workers by dialect similarity.

Two workers both speaking "sw-KE-urban" may have very different Sheng
usage patterns. This engine clusters by actual linguistic features,
not just language codes.

Minimum cluster size: 100 workers (privacy requirement).
Maximum clusters: 50 (practical limit).
"""

import hashlib
import logging
import math
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class WorkerFeatureVector:
    """Compressed feature representation of a worker's dialect."""
    device_id: str
    dialect_code: str
    region: str
    phonetic_embed: list = field(default_factory=list)  # Phonetic substitution rates
    vocab_signature: dict = field(default_factory=dict)  # term → frequency
    grammar_signature: dict = field(default_factory=dict)  # tense → distribution
    prosody_signature: dict = field(default_factory=dict)  # rate, rhythm, etc.
    interaction_count: int = 0
    asr_accuracy: float = 0.0


@dataclass
class DialectCluster:
    """A group of workers with similar dialect features."""
    id: str
    dialect_label: str
    region: str
    members: list = field(default_factory=list)  # List of device_ids
    centroid: dict = field(default_factory=dict)
    cohort_size: int = 0
    mean_asr_accuracy: float = 0.0
    new_terms_this_period: list = field(default_factory=list)
    is_new: bool = False

    def contains(self, device_id: str) -> bool:
        return device_id in self.members


@dataclass
class DriftAlert:
    """Alert when a dialect is evolving (new terms, changing patterns)."""
    dialect: str
    drift_type: str  # "vocabulary_expansion", "phonetic_shift", "vocabulary_contraction"
    description: str
    severity: str  # "high", "medium", "low"


class DialectClusterEngine:
    """
    Clusters workers by dialect similarity using hierarchical clustering.
    
    Similarity is computed across four dimensions:
    - Phonetic patterns (30% weight)
    - Vocabulary overlap (30% weight)
    - Grammar patterns (25% weight)
    - Prosodic features (15% weight)
    """

    MIN_CLUSTER_SIZE = 100  # Privacy requirement
    MAX_CLUSTERS = 50
    SIMILARITY_THRESHOLD = 0.5

    def __init__(self):
        self._clusters: dict = {}  # cluster_id → DialectCluster
        self._worker_features: dict = {}  # device_id → WorkerFeatureVector
        self._cluster_history: dict = {}  # cluster_id → historical data

    def register_worker(self, feature_vector: WorkerFeatureVector):
        """Register or update a worker's feature vector."""
        self._worker_features[feature_vector.device_id] = feature_vector

    def recluster(self) -> list:
        """
        Re-cluster all active workers by dialect similarity.
        Returns list of DialectCluster objects.
        
        Runs weekly. Workers are grouped by actual linguistic features,
        not just their declared dialect code.
        """
        if len(self._worker_features) < self.MIN_CLUSTER_SIZE:
            logger.info(f"Not enough workers ({len(self._worker_features)}) for clustering. "
                       f"Minimum: {self.MIN_CLUSTER_SIZE}")
            return list(self._clusters.values())

        # Build similarity matrix
        workers = list(self._worker_features.values())
        n = len(workers)

        # Hierarchical clustering (simplified agglomerative)
        # Start with each worker as its own cluster
        clusters = [[w] for w in workers]

        while len(clusters) > self.MAX_CLUSTERS:
            # Find the two most similar clusters
            best_sim = -1
            best_i, best_j = 0, 1

            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    sim = self._cluster_similarity(clusters[i], clusters[j])
                    if sim > best_sim:
                        best_sim = sim
                        best_i, best_j = i, j

            if best_sim < self.SIMILARITY_THRESHOLD:
                break  # No more similar clusters to merge

            # Merge clusters
            clusters[best_i] = clusters[best_i] + clusters[best_j]
            clusters.pop(best_j)

        # Create DialectCluster objects
        new_clusters = {}
        for i, members in enumerate(clusters):
            cluster_id = self._generate_cluster_id(members)
            device_ids = [w.device_id for w in members]

            centroid = self._compute_centroid(members)
            dialect_label = self._auto_label_dialect(members, centroid)

            cluster = DialectCluster(
                id=cluster_id,
                dialect_label=dialect_label,
                region=self._majority_region(members),
                members=device_ids,
                centroid=centroid,
                cohort_size=len(device_ids),
                mean_asr_accuracy=sum(w.asr_accuracy for w in members) / len(members),
                is_new=cluster_id not in self._clusters
            )
            new_clusters[cluster_id] = cluster

        self._clusters = new_clusters

        # Check for dialect drift
        drift_alerts = self._detect_drift()
        for alert in drift_alerts:
            logger.warning(f"Dialect drift: {alert.dialect} - {alert.description}")

        logger.info(f"Reclustered {n} workers into {len(new_clusters)} clusters")
        return list(new_clusters.values())

    def find_nearest_cluster(self, region: str, dialect_code: str = None) -> Optional[DialectCluster]:
        """Find the nearest cluster for a new worker (cold-start)."""
        candidates = [c for c in self._clusters.values() if c.cohort_size >= self.MIN_CLUSTER_SIZE]

        if dialect_code:
            exact = [c for c in candidates if c.dialect_label == dialect_code]
            if exact:
                return exact[0]

        region_matches = [c for c in candidates if c.region == region]
        if region_matches:
            return max(region_matches, key=lambda c: c.cohort_size)

        return max(candidates, key=lambda c: c.cohort_size) if candidates else None

    def get_clusters(self) -> list:
        """Get all current clusters."""
        return list(self._clusters.values())

    def get_cluster_count(self) -> int:
        """Get number of active clusters."""
        return len(self._clusters)

    # ── Private helpers ──────────────────────────────────────

    def _cluster_similarity(self, cluster_a: list, cluster_b: list) -> float:
        """Compute similarity between two clusters using centroid distance."""
        centroid_a = self._compute_centroid(cluster_a)
        centroid_b = self._compute_centroid(cluster_b)

        # Dialect code boost
        codes_a = set(w.dialect_code for w in cluster_a)
        codes_b = set(w.dialect_code for w in cluster_b)
        code_overlap = len(codes_a & codes_b) / max(len(codes_a | codes_b), 1)
        dialect_boost = code_overlap * 0.2

        # Phonetic similarity (cosine)
        phonetic_sim = self._cosine_similarity(
            centroid_a.get("phonetic", []),
            centroid_b.get("phonetic", [])
        ) * 0.30

        # Vocabulary similarity (Jaccard)
        vocab_a = set(centroid_a.get("vocab", {}).keys())
        vocab_b = set(centroid_b.get("vocab", {}).keys())
        vocab_sim = (len(vocab_a & vocab_b) / max(len(vocab_a | vocab_b), 1)) * 0.30

        # Grammar similarity
        grammar_sim = self._dict_similarity(
            centroid_a.get("grammar", {}),
            centroid_b.get("grammar", {})
        ) * 0.25

        # Prosody similarity
        prosody_sim = self._dict_similarity(
            centroid_a.get("prosody", {}),
            centroid_b.get("prosody", {})
        ) * 0.15

        return dialect_boost + phonetic_sim + vocab_sim + grammar_sim + prosody_sim

    def _compute_centroid(self, members: list) -> dict:
        """Compute centroid feature vector for a cluster."""
        if not members:
            return {}

        # Average phonetic embeddings
        phonetic_dim = max(len(w.phonetic_embed) for w in members) if members else 0
        phonetic_centroid = [0.0] * phonetic_dim
        for w in members:
            for i, v in enumerate(w.phonetic_embed):
                phonetic_centroid[i] += v / len(members)

        # Merge vocabularies (union with frequency averaging)
        vocab_centroid = defaultdict(float)
        for w in members:
            for term, freq in w.vocab_signature.items():
                vocab_centroid[term] += freq / len(members)

        # Average grammar distributions
        grammar_centroid = defaultdict(float)
        for w in members:
            for tense, freq in w.grammar_signature.items():
                grammar_centroid[tense] += freq / len(members)

        # Average prosody
        prosody_centroid = defaultdict(float)
        for w in members:
            for key, val in w.prosody_signature.items():
                prosody_centroid[key] += val / len(members)

        return {
            "phonetic": phonetic_centroid,
            "vocab": dict(vocab_centroid),
            "grammar": dict(grammar_centroid),
            "prosody": dict(prosody_centroid)
        }

    def _auto_label_dialect(self, members: list, centroid: dict) -> str:
        """Auto-label a cluster based on dominant features."""
        # Use majority dialect code
        codes = defaultdict(int)
        for w in members:
            codes[w.dialect_code] += 1
        return max(codes, key=codes.get) if codes else "unknown"

    def _majority_region(self, members: list) -> str:
        """Get majority region from cluster members."""
        regions = defaultdict(int)
        for w in members:
            regions[w.region] += 1
        return max(regions, key=regions.get) if regions else "unknown"

    def _generate_cluster_id(self, members: list) -> str:
        """Generate a deterministic cluster ID."""
        dialect = self._auto_label_dialect(members, {})
        device_hash = hashlib.md5(
            ",".join(sorted(w.device_id for w in members[:10])).encode()
        ).hexdigest()[:8]
        return f"cluster-{dialect}-{device_hash}"

    def _cosine_similarity(self, a: list, b: list) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _dict_similarity(self, a: dict, b: dict) -> float:
        """Compute similarity between two frequency distributions."""
        if not a or not b:
            return 0.0
        all_keys = set(a.keys()) | set(b.keys())
        if not all_keys:
            return 0.0
        dot = sum(a.get(k, 0) * b.get(k, 0) for k in all_keys)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _detect_drift(self) -> list:
        """Detect dialect drift across clusters."""
        alerts = []
        for cluster_id, cluster in self._clusters.items():
            history = self._cluster_history.get(cluster_id)

            if history is None:
                # First time seeing this cluster, store baseline
                self._cluster_history[cluster_id] = {
                    "vocab_snapshot": set(cluster.centroid.get("vocab", {}).keys()),
                    "phonetic_snapshot": cluster.centroid.get("phonetic", []),
                    "timestamp": time.time()
                }
                continue

            # Check vocabulary drift
            current_vocab = set(cluster.centroid.get("vocab", {}).keys())
            historical_vocab = history.get("vocab_snapshot", set())
            new_terms = current_vocab - historical_vocab

            if len(new_terms) > 20:
                alerts.append(DriftAlert(
                    dialect=cluster.dialect_label,
                    drift_type="vocabulary_expansion",
                    description=f"{len(new_terms)} new terms detected",
                    severity="high" if len(new_terms) > 50 else "medium"
                ))

            # Update history
            self._cluster_history[cluster_id] = {
                "vocab_snapshot": current_vocab,
                "phonetic_snapshot": cluster.centroid.get("phonetic", []),
                "timestamp": time.time()
            }

        return alerts


import time
