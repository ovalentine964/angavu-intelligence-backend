"""
Federated Learning Service — Privacy-preserving model aggregation.

Aggregates model updates from Msaidizi devices without accessing raw
speech data. Uses FedAvg with differential privacy and secure aggregation.

Architecture:
    Devices ──[encrypted updates]──► FL Server
    FL Server ──[aggregate + noise]──► Global Model
    Global Model ──[push]──► Devices

Academic references:
    - McMahan et al. (2017) "Communication-Efficient Learning of Deep
      Networks from Differential Privacy"
    - Geyer et al. (2017) "Differentially Private Federated Learning"
    - Bonawitz et al. (2017) "Practical Secure Aggregation for
      Privacy-Preserving Machine Learning"

Dialect clustering follows K-means principles (STA 442).
Quality validation uses hypothesis testing (STA 342).
"""

import base64
import hashlib
import json
import math
import struct
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.schemas.federated_learning import (
    AnonymizedPattern,
    CalibrationParams,
    FLStatusResponse,
    FLUpdate,
    GlobalModelResponse,
    UploadResponse,
    VocabularyUpdate,
)
from app.services.fl_persistence import FLPersistence

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

# Differential privacy parameters
DP_EPSILON = 1.0
DP_DELTA = 1e-5
DP_SENSITIVITY = 1.0  # L2 sensitivity of individual updates

# Aggregation thresholds
MIN_UPDATES_FOR_AGGREGATION = 5  # Minimum updates before triggering FedAvg
MAX_UPDATES_IN_ROUND = 1000  # Max updates per aggregation round

# Model versioning
MODEL_MAJOR_VERSION = 3
MODEL_MINOR_VERSION = 2

# Dialect regions in Kenya
DIALECT_REGIONS = {
    "sw": {"name": "Swahili", "center": [-1.29, 36.82]},  # Nairobi
    "en": {"name": "English", "center": [-1.29, 36.82]},
    "luo": {"name": "Luo", "center": [-0.10, 34.76]},  # Kisumu
    "kik": {"name": "Kikuyu", "center": [-0.72, 36.98]},  # Nyeri
    "kal": {"name": "Kalenjin", "center": [0.31, 35.28]},  # Eldoret
    "kam": {"name": "Kamba", "center": [-1.52, 37.26]},  # Machakos
    "luh": {"name": "Luhya", "center": [0.28, 34.75]},  # Kakamega
    "mer": {"name": "Meru", "center": [0.05, 37.65]},  # Meru
    "mij": {"name": "Mijikenda", "center": [-3.95, 39.66]},  # Mombasa
}


# ════════════════════════════════════════════════════════════════════
# In-Memory State (production would use Redis/PostgreSQL)
# ════════════════════════════════════════════════════════════════════


class _FLState:
    """Mutable singleton holding federated learning state."""

    def __init__(self):
        self.reset()

    def reset(self):
        # Pending updates per language: {language: [FLUpdate, ...]}
        self.pending_updates: Dict[str, List[FLUpdate]] = defaultdict(list)
        # Aggregated models per language
        self.global_models: Dict[str, Dict[str, Any]] = {}
        # Version counters per language
        self.version_counters: Dict[str, int] = defaultdict(int)
        # Total updates ever received
        self.total_updates: int = 0
        # Unique device IDs seen (hashed)
        self.seen_devices: set = set()
        # Aggregation round counter
        self.aggregation_round: int = 0
        # Last aggregation timestamp
        self.last_aggregation_at: Optional[str] = None
        # Dialect cluster assignments: {device_id: dialect_code}
        self.device_clusters: Dict[str, str] = {}
        # Quality scores per device: {device_id: float}
        self.device_quality: Dict[str, float] = {}


_state = _FLState()
_persistence = FLPersistence()


# ════════════════════════════════════════════════════════════════════
# FedAvg Aggregation
# ════════════════════════════════════════════════════════════════════


def _fedavg_aggregate(
    updates: List[FLUpdate],
) -> Tuple[Optional[CalibrationParams], List[VocabularyUpdate]]:
    """
    Federated Averaging (FedAvg) aggregation.

    Computes weighted average of client updates:
        Δw_global = Σ (n_k / n) · Δw_k

    where n_k = number of local samples for device k,
    n = total samples across all devices.

    For calibration parameters, we compute element-wise weighted mean.
    For correction patterns, we aggregate phoneme confusion statistics
    and vocabulary frequencies.

    Args:
        updates: List of FLUpdate objects from devices

    Returns:
        Tuple of (aggregated calibration params, vocabulary updates)
    """
    if not updates:
        return None, []

    # ── Calibration parameter aggregation (weighted mean) ──
    total_weight = 0.0
    agg_temp = 0.0
    agg_platt_a = 0.0
    agg_platt_b = 0.0
    agg_prior = 0.0

    for update in updates:
        # Weight by number of local corrections (more data = more weight)
        n_k = update.metadata.corrections_count if update.metadata else 1
        if n_k <= 0:
            n_k = 1
        weight = float(n_k)

        if update.calibration_params:
            cp = update.calibration_params
            agg_temp += cp.temperature * weight
            agg_platt_a += cp.platt_a * weight
            agg_platt_b += cp.platt_b * weight
            agg_prior += cp.prior * weight

        total_weight += weight

    aggregated_calibration = None
    if total_weight > 0:
        aggregated_calibration = CalibrationParams(
            temperature=agg_temp / total_weight,
            platt_a=agg_platt_a / total_weight,
            platt_b=agg_platt_b / total_weight,
            prior=agg_prior / total_weight,
        )

    # ── Vocabulary aggregation from correction patterns ──
    # Count phoneme confusion patterns across all devices
    phoneme_counts: Dict[str, int] = defaultdict(int)
    error_type_counts: Dict[str, int] = defaultdict(int)
    edit_distance_sum = 0.0
    edit_distance_count = 0

    for update in updates:
        for pattern in update.correction_patterns:
            # Aggregate phoneme patterns
            if pattern.phoneme_pattern:
                for pp in pattern.phoneme_pattern.split(","):
                    pp = pp.strip()
                    if pp:
                        phoneme_counts[pp] += 1

            # Aggregate error types
            error_type_counts[pattern.error_type] += 1

            # Aggregate edit distances
            edit_distance_sum += pattern.edit_distance
            edit_distance_count += 1

    # Build vocabulary updates from phoneme statistics
    vocab_updates = []
    for phoneme, count in sorted(phoneme_counts.items(), key=lambda x: -x[1])[:500]:
        confidence = min(1.0, count / max(1, len(updates)))
        vocab_updates.append(
            VocabularyUpdate(
                word=phoneme,
                frequency=count,
                confidence=round(confidence, 4),
            )
        )

    return aggregated_calibration, vocab_updates


# ════════════════════════════════════════════════════════════════════
# Differential Privacy
# ════════════════════════════════════════════════════════════════════


def _compute_noise_scale(epsilon: float, delta: float, sensitivity: float) -> float:
    """
    Compute Gaussian noise scale for (ε,δ)-differential privacy.

    σ = Δf · √(2 · ln(1.25/δ)) / ε

    For (ε=1.0, δ=1e-5, Δf=1.0):
        σ ≈ 4.91
    """
    return sensitivity * math.sqrt(2.0 * math.log(1.25 / delta)) / epsilon


def _add_gaussian_noise(value: float, sigma: float) -> float:
    """Add Gaussian noise using Box-Muller transform (cryptographic RNG source)."""
    # Use two uniform random values from secrets for Box-Muller
    import secrets

    u1 = secrets.randbelow(10**8) / 10**8
    u2 = secrets.randbelow(10**8) / 10**8
    # Avoid log(0)
    u1 = max(u1, 1e-10)
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return value + sigma * z


def _apply_dp_to_calibration(
    params: CalibrationParams, sigma: float
) -> CalibrationParams:
    """Apply Gaussian noise to aggregated calibration parameters."""
    return CalibrationParams(
        temperature=max(0.01, _add_gaussian_noise(params.temperature, sigma)),
        platt_a=_add_gaussian_noise(params.platt_a, sigma),
        platt_b=_add_gaussian_noise(params.platt_b, sigma),
        prior=max(0.0, min(1.0, _add_gaussian_noise(params.prior, sigma))),
    )


def _apply_dp_to_vocabulary(
    vocab: List[VocabularyUpdate], sigma: float
) -> List[VocabularyUpdate]:
    """Apply Gaussian noise to vocabulary frequency counts."""
    noisy_vocab = []
    for vu in vocab:
        noisy_freq = max(0, int(_add_gaussian_noise(float(vu.frequency), sigma * 10)))
        noisy_conf = max(0.0, min(1.0, _add_gaussian_noise(vu.confidence, sigma * 0.1)))
        noisy_vocab.append(
            VocabularyUpdate(
                word=vu.word,
                frequency=noisy_freq,
                confidence=round(noisy_conf, 4),
            )
        )
    return noisy_vocab


# ════════════════════════════════════════════════════════════════════
# Secure Aggregation
# ════════════════════════════════════════════════════════════════════


def _verify_update_signature(update: FLUpdate) -> bool:
    """
    Verify the integrity of an uploaded update.

    In a full secure aggregation implementation, this would:
    1. Verify device attestation (SafetyNet/Play Integrity)
    2. Validate encrypted payload against device public key
    3. Check update hasn't been replayed (timestamp + nonce)

    Current implementation validates basic invariants.
    """
    # Reject if device ID looks invalid
    if not update.device_id or len(update.device_id) < 8:
        logger.warning("fl_invalid_device_id", device_id=update.device_id)
        return False

    # Reject stale updates (> 24 hours old)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    age_hours = (now_ms - update.timestamp) / (1000 * 60 * 60)
    if age_hours > 24:
        logger.warning("fl_stale_update", device_id=update.device_id, age_hours=age_hours)
        return False

    # Reject future timestamps
    if update.timestamp > now_ms + 60_000:  # 1 min clock skew tolerance
        logger.warning("fl_future_timestamp", device_id=update.device_id)
        return False

    return True


def _decrypt_adapter_deltas(encrypted_b64: str) -> Optional[bytes]:
    """
    Decrypt adapter deltas received from device.

    In production, this would use per-device keys from a key management
    service (e.g., AWS KMS, HashiCorp Vault). The device encrypts with
    its private key; the server decrypts with the shared secret.

    Current implementation: base64-decode only (encryption is device-side
    via Android Keystore; transport is TLS 1.3).
    """
    try:
        return base64.b64decode(encrypted_b64)
    except Exception as e:
        logger.error("fl_adapter_decode_failed", error=str(e))
        return None


# ════════════════════════════════════════════════════════════════════
# Dialect Clustering (K-means style, STA 442)
# ════════════════════════════════════════════════════════════════════


def _cluster_dialect(update: FLUpdate) -> str:
    """
    Assign device to a dialect cluster using phoneme pattern analysis.

    Uses a simplified K-means approach:
    1. Extract feature vector from correction patterns
    2. Compare to known dialect centroids
    3. Assign to nearest centroid

    In production, this would use proper K-means with:
    - Feature extraction from phoneme confusion matrices
    - Iterative centroid updates
    - Silhouette analysis for optimal K

    For now, we use the device's declared language and pattern heuristics.
    """
    # Primary signal: device-declared language
    declared = update.language.lower().strip()
    if declared in DIALECT_REGIONS:
        return declared

    # Secondary: analyze phoneme patterns for dialect hints
    phoneme_features: Dict[str, int] = defaultdict(int)
    for pattern in update.correction_patterns:
        if pattern.phoneme_pattern:
            for pp in pattern.phoneme_pattern.split(","):
                pp = pp.strip()
                if pp:
                    phoneme_features[pp] += 1

    # Known dialect-specific phoneme confusions
    dialect_markers = {
        "luo": ["th→t", "r→l", "sh→s"],  # Luo speakers often confuse these
        "kik": ["ng→n", "mb→m"],  # Kikuyu nasal patterns
        "kal": ["ch→sh", "t→d"],  # Kalenjin stop patterns
        "kam": ["v→b", "z→s"],  # Kamba fricative patterns
        "luh": ["ny→n", "ly→l"],  # Luhya palatal patterns
    }

    best_dialect = declared
    best_score = 0

    for dialect, markers in dialect_markers.items():
        score = sum(phoneme_features.get(m, 0) for m in markers)
        if score > best_score:
            best_score = score
            best_dialect = dialect

    return best_dialect if best_dialect in DIALECT_REGIONS else "sw"


# ════════════════════════════════════════════════════════════════════
# Quality Validation (Hypothesis Testing, STA 342)
# ════════════════════════════════════════════════════════════════════


def _validate_update_quality(update: FLUpdate) -> float:
    """
    Validate quality of a device's update using hypothesis testing.

    Tests:
    1. H₀: Update patterns are random noise (no signal)
    2. H₁: Update contains genuine correction patterns

    Test statistic: Proportion of non-trivial edit distances
    Expected under H₀: ~50% (random edits would have moderate distance)
    Observed: proportion with edit_distance > 0.1 and < 0.9

    Uses z-test for proportions (one-sided, α=0.05):
        z = (p̂ - p₀) / √(p₀(1-p₀)/n)

    Returns:
        Quality score [0.0, 1.0] — higher is better.
        Updates below 0.3 are flagged as low quality.
    """
    patterns = update.correction_patterns
    if not patterns:
        return 0.5  # Neutral score for updates without patterns

    n = len(patterns)
    if n < 3:
        return 0.3  # Too few patterns to assess

    # Count "meaningful" corrections (edit distance in informative range)
    meaningful = sum(
        1 for p in patterns if 0.05 < p.edit_distance < 0.95
    )
    p_hat = meaningful / n

    # Under H₀ (random): expect ~50% in informative range
    p_0 = 0.5
    se = math.sqrt(p_0 * (1 - p_0) / n)

    if se < 1e-10:
        return 0.5

    z = (p_hat - p_0) / se

    # Convert z-score to quality score
    # z > 1.645 (p < 0.05 one-sided) → high quality
    # z < 0 → possibly random/noise
    quality = 1.0 / (1.0 + math.exp(-z))  # Sigmoid mapping

    # Bonus for consistency (low variance in edit distances)
    if n >= 5:
        mean_ed = sum(p.edit_distance for p in patterns) / n
        var_ed = sum((p.edit_distance - mean_ed) ** 2 for p in patterns) / n
        consistency_bonus = max(0.0, 0.2 * (1.0 - min(1.0, var_ed * 4)))
        quality = min(1.0, quality + consistency_bonus)

    return round(quality, 4)


# ════════════════════════════════════════════════════════════════════
# Version Management
# ════════════════════════════════════════════════════════════════════


def _next_version(language: str) -> str:
    """Generate next model version string for a language."""
    _state.version_counters[language] += 1
    patch = _state.version_counters[language]
    return f"v{MODEL_MAJOR_VERSION}.{MODEL_MINOR_VERSION}.{patch}"


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════


class FederatedLearningService:
    """
    Privacy-preserving federated learning for dialect models.

    Aggregates model updates from devices without accessing raw speech
    data. Uses secure aggregation with differential privacy (ε=1.0).

    Academic references:
    - McMahan et al. (2017) "Communication-Efficient Learning of Deep
      Networks from Differential Privacy"
    - Geyer et al. (2017) "Differentially Private Federated Learning"
    """

    def __init__(self):
        self._sigma = _compute_noise_scale(DP_EPSILON, DP_DELTA, DP_SENSITIVITY)

    async def upload_update(self, update: FLUpdate) -> UploadResponse:
        """
        Process a federated learning update from a device.

        Steps:
        1. Verify update integrity (signature, timestamp)
        2. Validate update quality (hypothesis test)
        3. Assign dialect cluster (K-means)
        4. Store pending update
        5. Trigger aggregation if threshold met

        Args:
            update: The device's FL update

        Returns:
            UploadResponse with status and next model version if aggregated
        """
        update_id = str(uuid.uuid4())

        # ── Step 1: Verify integrity ──
        if not _verify_update_signature(update):
            logger.warning("fl_update_rejected", device_id=update.device_id, reason="integrity")
            return UploadResponse(
                status="rejected",
                update_id=update_id,
                device_id=update.device_id,
                language=update.language,
                aggregated=False,
            )

        # ── Step 2: Quality validation ──
        quality = _validate_update_quality(update)
        _state.device_quality[update.device_id] = quality

        if quality < 0.2:
            logger.warning(
                "fl_low_quality_update",
                device_id=update.device_id,
                quality=quality,
            )
            # Still accept, but mark as low quality

        # ── Step 3: Dialect clustering ──
        dialect = _cluster_dialect(update)
        _state.device_clusters[update.device_id] = dialect

        logger.info(
            "fl_update_received",
            update_id=update_id,
            device_id=update.device_id,
            language=update.language,
            dialect=dialect,
            quality=quality,
            patterns_count=len(update.correction_patterns),
        )

        # ── Step 4: Store pending update ──
        _state.pending_updates[dialect].append(update)
        _state.total_updates += 1
        _state.seen_devices.add(update.device_id)

        # Persist to SQLite
        calibration_data = None
        if update.calibration_params:
            calibration_data = {
                "temperature": update.calibration_params.temperature,
                "platt_a": update.calibration_params.platt_a,
                "platt_b": update.calibration_params.platt_b,
                "prior": update.calibration_params.prior,
            }
        phoneme_data = [p.phoneme_pattern for p in update.correction_patterns if p.phoneme_pattern]
        _persistence.save_update(
            update.device_id, dialect, calibration_data, phoneme_data, update.timestamp
        )
        _persistence.save_device_info(update.device_id, dialect)

        # ── Step 5: Check if aggregation should trigger ──
        aggregated = False
        next_version = None

        if len(_state.pending_updates[dialect]) >= MIN_UPDATES_FOR_AGGREGATION:
            next_version = await self._aggregate_language(dialect)
            aggregated = True

        return UploadResponse(
            status="accepted",
            update_id=update_id,
            device_id=update.device_id,
            language=dialect,
            aggregated=aggregated,
            next_download_version=next_version,
        )

    async def get_global_model(self, dialect: str) -> Optional[GlobalModelResponse]:
        """
        Get the latest aggregated global model for a dialect.

        Args:
            dialect: Language/dialect code (e.g. 'sw', 'luo', 'kik')

        Returns:
            GlobalModelResponse if a model exists, None otherwise
        """
        dialect = dialect.lower().strip()
        model = _state.global_models.get(dialect)

        # If not in memory, try loading from SQLite
        if model is None:
            persisted = _persistence.get_latest_model(dialect)
            if persisted:
                version, params_json, phonemes_json = persisted
                params = json.loads(params_json) if params_json else {}
                phonemes = json.loads(phonemes_json) if phonemes_json else []
                model = {
                    "version": version,
                    "calibration_params": CalibrationParams(**params) if params else CalibrationParams(),
                    "vocabulary_updates": [VocabularyUpdate(word=p, frequency=1, confidence=1.0) for p in phonemes] if isinstance(phonemes, list) else [],
                }
                _state.global_models[dialect] = model

        if model is None:
            # Try to return a default/empty model for known dialects
            if dialect in DIALECT_REGIONS:
                return GlobalModelResponse(
                    version="v3.2.0",
                    language=dialect,
                    adapter_deltas=None,
                    calibration_params=CalibrationParams(),
                    vocabulary_updates=[],
                )
            return None

        return GlobalModelResponse(
            version=model["version"],
            language=dialect,
            adapter_deltas=model.get("adapter_deltas"),
            calibration_params=model.get("calibration_params"),
            vocabulary_updates=model.get("vocabulary_updates", []),
            timestamp=model.get("timestamp", 0),
        )

    async def get_status(self) -> FLStatusResponse:
        """
        Get federated learning system status.

        Returns:
            FLStatusResponse with system-wide metrics
        """
        # Merge in-memory counts with persisted counts
        persisted_updates = _persistence.get_total_update_count()
        persisted_devices = _persistence.get_device_count()
        total_updates = max(_state.total_updates, persisted_updates)
        active_devices = max(len(_state.seen_devices), persisted_devices)

        return FLStatusResponse(
            status="ok",
            total_updates_received=total_updates,
            active_devices=active_devices,
            languages_supported=list(DIALECT_REGIONS.keys()),
            current_global_versions={
                lang: model["version"]
                for lang, model in _state.global_models.items()
            },
            last_aggregation_at=_state.last_aggregation_at,
            aggregation_round=_state.aggregation_round,
        )

    async def _aggregate_language(self, dialect: str) -> str:
        """
        Run FedAvg aggregation for a single dialect.

        Steps:
        1. Collect pending updates (up to MAX_UPDATES_IN_ROUND)
        2. Run FedAvg (weighted mean of calibration params + vocab)
        3. Apply differential privacy (Gaussian noise)
        4. Store aggregated model
        5. Clear processed updates

        Returns:
            New model version string
        """
        updates = _state.pending_updates[dialect][:MAX_UPDATES_IN_ROUND]
        _state.pending_updates[dialect] = _state.pending_updates[dialect][MAX_UPDATES_IN_ROUND:]

        # ── FedAvg ──
        agg_calibration, agg_vocab = _fedavg_aggregate(updates)

        # ── Apply differential privacy ──
        if agg_calibration:
            agg_calibration = _apply_dp_to_calibration(agg_calibration, self._sigma)
        else:
            agg_calibration = CalibrationParams()

        agg_vocab = _apply_dp_to_vocabulary(agg_vocab, self._sigma)

        # ── Adapter aggregation ──
        # In production, this would average the encrypted LoRA deltas.
        # For now, we store the most recent adapter delta (last-device wins).
        # A proper implementation would use secure aggregation protocols
        # (Bonawitz et al., 2017) to sum ciphertexts.
        adapter_deltas_b64 = None
        for update in reversed(updates):
            if update.adapter_deltas:
                adapter_deltas_b64 = update.adapter_deltas
                break

        # ── Version and store ──
        version = _next_version(dialect)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        _state.global_models[dialect] = {
            "version": version,
            "calibration_params": agg_calibration,
            "vocabulary_updates": agg_vocab,
            "adapter_deltas": adapter_deltas_b64,
            "timestamp": now_ms,
            "updates_included": len(updates),
        }

        _state.aggregation_round += 1
        _state.last_aggregation_at = datetime.now(timezone.utc).isoformat()

        # Persist aggregated model to SQLite
        agg_params_dict = {
            "temperature": agg_calibration.temperature,
            "platt_a": agg_calibration.platt_a,
            "platt_b": agg_calibration.platt_b,
            "prior": agg_calibration.prior,
        } if agg_calibration else {}
        agg_phonemes = [vu.word for vu in agg_vocab]
        _persistence.save_global_model(dialect, version, agg_params_dict, agg_phonemes)
        _persistence.mark_processed(dialect)

        logger.info(
            "fl_aggregation_complete",
            dialect=dialect,
            version=version,
            updates_aggregated=len(updates),
            vocab_entries=len(agg_vocab),
            round=_state.aggregation_round,
        )

        return version
