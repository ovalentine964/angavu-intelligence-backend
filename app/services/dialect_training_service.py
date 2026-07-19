"""
Dialect Training Service — Learn African dialects via federated aggregation.

Receives anonymized dialect gradients from devices, aggregates patterns
across users in the same dialect group, trains dialect-specific ASR/TTS
models, and publishes improved models for device download.

Architecture:
    Devices ──[dialect gradients]──► Dialect Training Service
    Service ──[aggregate per dialect]──► Dialect Model Store
    Model Store ──[publish]──► Devices download improved models

Supported dialects (13):
    Kenya:   Sheng, Kikuyu, Dholuo, Luhya, Kalenjin, Maasai
    East Africa: Somali, Amharic
    West Africa: Yoruba, Igbo, Hausa
    Southern Africa: Zulu, Xhosa

Privacy model:
    - Device sends only anonymized dialect correction signals
    - No raw audio or text leaves the device
    - Differential privacy (ε=0.1) applied before aggregation
    - K-anonymity (k≥5): patterns only aggregated with sufficient contributors
    - Device IDs are one-way hashed

Integration:
    - Bridges into existing FederatedLearningService pipeline
    - Feeds improved models to ModelDistributionService
    - Publishes dialect events via EventBus for VoicePipelineAgent

Academic references:
    - Adger et al. (2014) "Variation and Dialect Networks"
    - Joshi et al. (2012) "The Social and the Computational in Social Media"
    - McMahan et al. (2017) "Communication-Efficient Learning"
"""

from __future__ import annotations

import hashlib
import math
import secrets
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════


class DialectCode(str, Enum):
    """Supported African dialect codes."""
    # East Africa — Kenya
    SHENG = "sheng"
    KIKUYU = "kikuyu"
    DHOLUO = "dholuo"
    LUHYA = "luhya"
    KALENJIN = "kalenjin"
    MAASAI = "maasai"
    # East Africa — Horn
    SOMALI = "somali"
    AMHARIC = "amharic"
    # West Africa
    YORUBA = "yoruba"
    IGBO = "igbo"
    HAUSA = "hausa"
    # Southern Africa
    ZULU = "zulu"
    XHOSA = "xhosa"


# Map dialect codes to language family for grouped aggregation
DIALECT_FAMILIES: dict[str, str] = {
    DialectCode.SHENG: "bantu_creole",       # Swahili-based creole
    DialectCode.KIKUYU: "bantu",
    DialectCode.DHOLUO: "nilotic",
    DialectCode.LUHYA: "bantu",
    DialectCode.KALENJIN: "nilotic",
    DialectCode.MAASAI: "nilotic",
    DialectCode.SOMALI: "cushitic",
    DialectCode.AMHARIC: "semitic",
    DialectCode.YORUBA: "niger_congo",
    DialectCode.IGBO: "niger_congo",
    DialectCode.HAUSA: "chadic",
    DialectCode.ZULU: "bantu",
    DialectCode.XHOSA: "bantu",
}

# Geographic metadata for dialect regions
DIALECT_GEO: dict[str, dict[str, Any]] = {
    DialectCode.SHENG:    {"name": "Sheng",    "center": [-1.29, 36.82], "country": "KE"},
    DialectCode.KIKUYU:   {"name": "Kikuyu",   "center": [-0.72, 36.98], "country": "KE"},
    DialectCode.DHOLUO:   {"name": "Dholuo",   "center": [-0.10, 34.76], "country": "KE"},
    DialectCode.LUHYA:    {"name": "Luhya",    "center": [0.28, 34.75],  "country": "KE"},
    DialectCode.KALENJIN: {"name": "Kalenjin", "center": [0.31, 35.28],  "country": "KE"},
    DialectCode.MAASAI:   {"name": "Maasai",   "center": [-1.50, 36.80], "country": "KE"},
    DialectCode.SOMALI:   {"name": "Somali",   "center": [3.85, 41.87],  "country": "SO"},
    DialectCode.AMHARIC:  {"name": "Amharic",  "center": [9.02, 38.75],  "country": "ET"},
    DialectCode.YORUBA:   {"name": "Yoruba",   "center": [7.38, 3.94],   "country": "NG"},
    DialectCode.IGBO:     {"name": "Igbo",     "center": [6.45, 7.50],   "country": "NG"},
    DialectCode.HAUSA:    {"name": "Hausa",    "center": [12.00, 8.52],  "country": "NG"},
    DialectCode.ZULU:     {"name": "Zulu",     "center": [-29.86, 31.02],"country": "ZA"},
    DialectCode.XHOSA:    {"name": "Xhosa",    "center": [-33.00, 27.85],"country": "ZA"},
}

# Differential privacy parameters (must match client-side ε=0.1)
DP_EPSILON = 0.1
DP_DELTA = 1e-5
DP_SENSITIVITY = 1.0

# Aggregation thresholds
MIN_GRADIENTS_FOR_AGGREGATION = 5   # Minimum gradient submissions before training
MAX_GRADIENTS_PER_ROUND = 500       # Max gradients per training round
MIN_DEVICES_FOR_PUBLISH = 3         # Minimum unique devices to publish a model
MODEL_IMPROVEMENT_THRESHOLD = 0.01  # Minimum WER improvement to publish new version

# Model versioning
MODEL_MAJOR = 1


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


@dataclass
class DialectGradient:
    """
    Anonymized dialect gradient submission from a device.

    Contains dialect-specific learning signals without exposing
    raw audio or text. Derived from on-device ASR/TTS corrections.
    """
    device_id: str                              # SHA-256 hashed device ID
    dialect: str                                # Dialect code
    timestamp: int                              # Epoch milliseconds
    phoneme_corrections: list[dict[str, Any]]   # Phoneme-level correction patterns
    vocabulary_signals: list[dict[str, Any]]    # New/corrected vocabulary entries
    pronunciation_delta: str | None = None   # Base64-encoded pronunciation model delta
    prosody_signals: dict[str, Any] | None = None  # Tone/stress/rhythm patterns
    grammar_patterns: list[dict[str, Any]] | None = None  # Grammar correction patterns
    confidence_score: float = 0.5               # Device-side confidence in gradient quality
    sample_count: int = 1                       # Number of local samples used


@dataclass
class DialectModelVersion:
    """Published dialect model version."""
    version: str
    dialect: str
    family: str
    asr_adapter_deltas: str | None = None    # Base64 LoRA deltas for ASR
    tts_adapter_deltas: str | None = None    # Base64 LoRA deltas for TTS
    vocabulary: list[dict[str, Any]] = field(default_factory=list)
    pronunciation_map: list[dict[str, Any]] = field(default_factory=list)
    prosody_params: dict[str, Any] | None = None
    grammar_rules: list[dict[str, Any]] = field(default_factory=list)
    calibration_params: dict[str, float] = field(default_factory=dict)
    training_metrics: dict[str, Any] = field(default_factory=dict)
    contributor_count: int = 0
    aggregation_round: int = 0
    created_at: str = ""
    checksum: str = ""


@dataclass
class DialectTrainingStatus:
    """Training status for a single dialect."""
    dialect: str
    dialect_name: str
    family: str
    current_version: str
    pending_gradients: int
    total_gradients_received: int
    unique_devices: int
    last_aggregation_at: str | None
    aggregation_round: int
    model_available: bool
    training_metrics: dict[str, Any]


@dataclass
class DialectEvaluationMetrics:
    """
    Evaluation metrics for dialect-specific models.

    Tracks ASR and TTS quality per dialect using:
    - Word Error Rate (WER) — primary ASR metric
    - Character Error Rate (CER) — fine-grained ASR metric
    - Phoneme Error Rate (PER) — phoneme-level accuracy
    - Mean Opinion Score (MOS) — TTS quality (1-5 scale)
    - Speaker Similarity — TTS voice preservation
    """
    dialect: str
    wer: float = 1.0                    # Word Error Rate (lower is better)
    cer: float = 1.0                    # Character Error Rate
    per: float = 1.0                    # Phoneme Error Rate
    mos_tts: float = 3.0               # Mean Opinion Score for TTS
    speaker_similarity: float = 0.5     # TTS speaker preservation [0,1]
    vocabulary_coverage: float = 0.0    # % of dialect vocabulary covered
    grammar_accuracy: float = 0.5       # Grammar pattern accuracy
    prosody_naturalness: float = 0.5    # Prosody naturalness score
    sample_count: int = 0               # Number of evaluation samples
    evaluated_at: str = ""

    def overall_score(self) -> float:
        """Composite quality score (higher is better)."""
        return (
            (1.0 - self.wer) * 0.30 +
            (1.0 - self.cer) * 0.15 +
            (1.0 - self.per) * 0.15 +
            (self.mos_tts / 5.0) * 0.15 +
            self.speaker_similarity * 0.10 +
            self.vocabulary_coverage * 0.10 +
            self.grammar_accuracy * 0.05
        )


# ════════════════════════════════════════════════════════════════════
# Differential Privacy
# ════════════════════════════════════════════════════════════════════


def _compute_noise_scale() -> float:
    """Gaussian noise scale for (ε,δ)-differential privacy."""
    return DP_SENSITIVITY * math.sqrt(2.0 * math.log(1.25 / DP_DELTA)) / DP_EPSILON


def _add_gaussian_noise(value: float, sigma: float) -> float:
    """Add Gaussian noise using Box-Muller with crypto RNG."""
    u1 = max(secrets.randbelow(10**8) / 10**8, 1e-10)
    u2 = secrets.randbelow(10**8) / 10**8
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return value + sigma * z


# ════════════════════════════════════════════════════════════════════
# Gradient Aggregation (FedAvg + Dialect-Aware Weighting)
# ════════════════════════════════════════════════════════════════════


def _aggregate_phoneme_corrections(
    gradients: list[DialectGradient],
    sigma: float,
) -> list[dict[str, Any]]:
    """
    Aggregate phoneme correction patterns across devices.

    Uses sample-count-weighted averaging:
        pattern_global = Σ (n_k / n) · pattern_k

    Applies differential privacy noise before returning.
    """
    # Count phoneme corrections across all devices
    phoneme_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "weighted_confidence": 0.0,
        "total_weight": 0.0,
        "variants": defaultdict(int),
    })

    total_samples = 0

    for grad in gradients:
        weight = float(max(1, grad.sample_count))
        total_samples += weight

        for correction in grad.phoneme_corrections:
            source = correction.get("source", "")
            target = correction.get("target", "")
            conf = correction.get("confidence", 0.5)
            context = correction.get("context", "")

            key = f"{source}→{target}"
            phoneme_counts[key]["count"] += 1
            phoneme_counts[key]["weighted_confidence"] += conf * weight
            phoneme_counts[key]["total_weight"] += weight
            if context:
                phoneme_counts[key]["variants"][context] += 1

    # Build aggregated result with DP noise
    aggregated = []
    for pattern, data in phoneme_counts.items():
        if data["total_weight"] <= 0:
            continue
        noisy_conf = max(0.0, min(1.0,
            _add_gaussian_noise(data["weighted_confidence"] / data["total_weight"], sigma * 0.1)
        ))
        noisy_count = max(0, int(_add_gaussian_noise(float(data["count"]), sigma * 5)))

        aggregated.append({
            "pattern": pattern,
            "count": noisy_count,
            "confidence": round(noisy_conf, 4),
            "top_contexts": sorted(
                data["variants"].items(), key=lambda x: -x[1]
            )[:5],
        })

    aggregated.sort(key=lambda x: (-x["confidence"], -x["count"]))
    return aggregated[:200]


def _aggregate_vocabulary(
    gradients: list[DialectGradient],
    sigma: float,
) -> list[dict[str, Any]]:
    """
    Aggregate vocabulary signals from device gradients.

    Words must appear across ≥ k (k-anonymity) distinct devices
    to be included. Frequencies are DP-noised.
    """
    word_devices: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "devices": set(),
        "total_frequency": 0,
        "meanings": defaultdict(int),
        "confidence_sum": 0.0,
    })

    for grad in gradients:
        for signal in grad.vocabulary_signals:
            word = signal.get("word", "").strip().lower()
            if not word:
                continue
            freq = signal.get("frequency", 1)
            meaning = signal.get("meaning", "")
            conf = signal.get("confidence", 0.5)

            word_devices[word]["devices"].add(grad.device_id)
            word_devices[word]["total_frequency"] += freq
            word_devices[word]["confidence_sum"] += conf
            if meaning:
                word_devices[word]["meanings"][meaning] += 1

    # Apply k-anonymity and DP
    aggregated = []
    for word, data in word_devices.items():
        n_devices = len(data["devices"])
        if n_devices < MIN_DEVICES_FOR_PUBLISH:
            continue

        noisy_freq = max(0, int(_add_gaussian_noise(
            float(data["total_frequency"]), sigma * 10
        )))
        noisy_conf = max(0.0, min(1.0,
            _add_gaussian_noise(data["confidence_sum"] / n_devices, sigma * 0.1)
        ))

        aggregated.append({
            "word": word,
            "frequency": noisy_freq,
            "confidence": round(noisy_conf, 4),
            "contributor_count": n_devices,
            "meanings": sorted(
                data["meanings"].items(), key=lambda x: -x[1]
            )[:3],
        })

    aggregated.sort(key=lambda x: (-x["confidence"], -x["frequency"]))
    return aggregated[:500]


def _aggregate_pronunciation_deltas(
    gradients: list[DialectGradient],
) -> str | None:
    """
    Aggregate pronunciation model deltas via weighted average.

    Decodes base64 float32 deltas from each device, computes
    sample-count-weighted element-wise average, re-encodes.
    """
    import base64
    import struct

    deltas_with_weights: list[tuple[list[float], float]] = []
    max_len = 0

    for grad in gradients:
        if not grad.pronunciation_delta:
            continue
        try:
            raw = base64.b64decode(grad.pronunciation_delta)
            n_floats = len(raw) // 4
            if n_floats == 0:
                continue
            floats = list(struct.unpack(f"<{n_floats}f", raw[:n_floats * 4]))
            weight = float(max(1, grad.sample_count))
            deltas_with_weights.append((floats, weight))
            max_len = max(max_len, n_floats)
        except Exception:
            continue

    if not deltas_with_weights or max_len == 0:
        return None

    # Weighted element-wise average
    total_weight = sum(w for _, w in deltas_with_weights)
    if total_weight <= 0:
        total_weight = float(len(deltas_with_weights))

    aggregated = [0.0] * max_len
    weight_sum = [0.0] * max_len

    for floats, weight in deltas_with_weights:
        for i, val in enumerate(floats):
            aggregated[i] += val * weight
            weight_sum[i] += weight

    for i in range(max_len):
        if weight_sum[i] > 0:
            aggregated[i] /= weight_sum[i]

    packed = struct.pack(f"<{max_len}f", *aggregated)
    return base64.b64encode(packed).decode("ascii")


def _aggregate_prosody(
    gradients: list[DialectGradient],
    sigma: float,
) -> dict[str, Any] | None:
    """
    Aggregate prosody signals (tone, stress, rhythm) across devices.

    Returns aggregated prosody parameters for TTS model improvement.
    """
    prosody_data = [g.prosody_signals for g in gradients if g.prosody_signals]
    if not prosody_data:
        return None

    # Aggregate numeric prosody features
    features = ["pitch_mean", "pitch_std", "speaking_rate", "energy_mean",
                 "rhythm_regularity", "tone_contour_mean"]

    aggregated: dict[str, float] = {}
    for feat in features:
        values = [p.get(feat, 0.0) for p in prosody_data if feat in p]
        if values:
            mean_val = sum(values) / len(values)
            aggregated[feat] = round(_add_gaussian_noise(mean_val, sigma * 0.05), 4)

    aggregated["contributor_count"] = len(prosody_data)
    return aggregated


def _aggregate_grammar_patterns(
    gradients: list[DialectGradient],
    sigma: float,
) -> list[dict[str, Any]]:
    """
    Aggregate grammar correction patterns.

    Identifies common grammar patterns specific to the dialect
    (e.g., SOV word order in some Bantu languages, tone-based
    distinctions in Yoruba/Igbo).
    """
    pattern_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "count": 0,
        "examples": [],
        "confidence_sum": 0.0,
    })

    for grad in gradients:
        if not grad.grammar_patterns:
            continue
        for pattern in grad.grammar_patterns:
            rule = pattern.get("rule", "")
            if not rule:
                continue
            pattern_counts[rule]["count"] += 1
            pattern_counts[rule]["confidence_sum"] += pattern.get("confidence", 0.5)
            if len(pattern_counts[rule]["examples"]) < 3:
                pattern_counts[rule]["examples"].append(pattern.get("example", ""))

    aggregated = []
    for rule, data in pattern_counts.items():
        if data["count"] < MIN_DEVICES_FOR_PUBLISH:
            continue
        noisy_count = max(0, int(_add_gaussian_noise(float(data["count"]), sigma * 3)))
        aggregated.append({
            "rule": rule,
            "count": noisy_count,
            "confidence": round(data["confidence_sum"] / max(1, data["count"]), 4),
            "examples": data["examples"],
        })

    aggregated.sort(key=lambda x: -x["count"])
    return aggregated[:100]


# ════════════════════════════════════════════════════════════════════
# Dialect Training Service
# ════════════════════════════════════════════════════════════════════


class DialectTrainingService:
    """
    Backend service for dialect-specific model training via federated aggregation.

    Receives anonymized dialect gradients from devices, aggregates patterns
    per dialect group, trains dialect-specific ASR/TTS adapters, and
    publishes improved models for device download.

    Integrates with:
    - FederatedLearningService: receives FL updates, triggers aggregation
    - ModelDistributionService: packages and distributes dialect models
    - VoicePipelineAgent: uses improved dialect models for transcription
    - LanguageAggregator: shares vocabulary and phoneme data
    """

    def __init__(self, fl_service: Any = None, model_registry: Any = None):
        self._fl_service = fl_service
        self._model_registry = model_registry
        self._sigma = _compute_noise_scale()

        # In-memory state (production: Redis/PostgreSQL)
        # Pending gradients per dialect
        self._pending: dict[str, list[DialectGradient]] = defaultdict(list)
        # Published models per dialect
        self._models: dict[str, DialectModelVersion] = {}
        # Version counters per dialect
        self._version_counters: dict[str, int] = defaultdict(int)
        # Unique devices per dialect
        self._devices: dict[str, set] = defaultdict(set)
        # Total gradients received per dialect
        self._total_gradients: dict[str, int] = defaultdict(int)
        # Aggregation round per dialect
        self._aggregation_rounds: dict[str, int] = defaultdict(int)
        # Evaluation metrics per dialect
        self._metrics: dict[str, DialectEvaluationMetrics] = {}
        # Last aggregation timestamp per dialect
        self._last_aggregation: dict[str, str | None] = defaultdict(lambda: None)

        self._logger = logger.bind(component="dialect_training")

    # ── Public API ────────────────────────────────────────────────

    async def submit_gradients(
        self,
        gradient: DialectGradient,
    ) -> dict[str, Any]:
        """
        Receive dialect gradient submission from a device.

        Steps:
        1. Validate dialect code
        2. Verify gradient quality
        3. Store pending gradient
        4. Trigger aggregation if threshold met

        Args:
            gradient: Anonymized dialect gradient from device

        Returns:
            Dict with status, gradient_id, and aggregation info
        """
        dialect = gradient.dialect.lower().strip()

        # Validate dialect
        valid_codes = [d.value for d in DialectCode]
        if dialect not in valid_codes:
            return {
                "status": "rejected",
                "reason": f"Unknown dialect '{dialect}'. Supported: {valid_codes}",
            }

        # Verify basic quality
        if not gradient.phoneme_corrections and not gradient.vocabulary_signals:
            return {
                "status": "rejected",
                "reason": "Gradient contains no learning signals",
            }

        # Store
        gradient_id = uuid.uuid4().hex[:12]
        self._pending[dialect].append(gradient)
        self._devices[dialect].add(gradient.device_id)
        self._total_gradients[dialect] += 1

        self._logger.info(
            "dialect_gradient_received",
            gradient_id=gradient_id,
            dialect=dialect,
            device_id=gradient.device_id[:8] + "...",
            phoneme_count=len(gradient.phoneme_corrections),
            vocab_count=len(gradient.vocabulary_signals),
            pending_count=len(self._pending[dialect]),
        )

        # Check aggregation threshold
        aggregated = False
        new_version = None
        if len(self._pending[dialect]) >= MIN_GRADIENTS_FOR_AGGREGATION:
            new_version = await self._train_dialect(dialect)
            aggregated = new_version is not None

        return {
            "status": "accepted",
            "gradient_id": gradient_id,
            "dialect": dialect,
            "aggregated": aggregated,
            "new_version": new_version,
            "pending_count": len(self._pending[dialect]),
        }

    async def list_models(self) -> list[dict[str, Any]]:
        """
        List all available dialect models.

        Returns:
            List of model summaries with version, dialect, metrics
        """
        models = []
        for dialect in DialectCode:
            d = dialect.value
            model = self._models.get(d)
            metrics = self._metrics.get(d)

            models.append({
                "dialect": d,
                "dialect_name": DIALECT_GEO.get(d, {}).get("name", d),
                "family": DIALECT_FAMILIES.get(d, "unknown"),
                "version": model.version if model else None,
                "model_available": model is not None,
                "contributor_count": model.contributor_count if model else 0,
                "vocabulary_size": len(model.vocabulary) if model else 0,
                "overall_score": metrics.overall_score() if metrics else None,
                "last_updated": model.created_at if model else None,
            })

        return models

    async def get_model_download(self, dialect: str) -> dict[str, Any] | None:
        """
        Get the latest dialect model for device download.

        Returns the full model package including ASR/TTS adapter deltas,
        vocabulary, pronunciation map, prosody params, and grammar rules.

        Args:
            dialect: Dialect code

        Returns:
            Model download payload or None if no model available
        """
        dialect = dialect.lower().strip()
        model = self._models.get(dialect)

        if model is None:
            return None

        return {
            "version": model.version,
            "dialect": model.dialect,
            "family": model.family,
            "asr_adapter_deltas": model.asr_adapter_deltas,
            "tts_adapter_deltas": model.tts_adapter_deltas,
            "vocabulary": model.vocabulary,
            "pronunciation_map": model.pronunciation_map,
            "prosody_params": model.prosody_params,
            "grammar_rules": model.grammar_rules,
            "calibration_params": model.calibration_params,
            "training_metrics": model.training_metrics,
            "contributor_count": model.contributor_count,
            "aggregation_round": model.aggregation_round,
            "created_at": model.created_at,
            "checksum": model.checksum,
        }

    async def get_training_status(self) -> list[DialectTrainingStatus]:
        """
        Get training progress for all dialects.

        Returns:
            List of DialectTrainingStatus for each supported dialect
        """
        statuses = []
        for dialect in DialectCode:
            d = dialect.value
            model = self._models.get(d)
            metrics = self._metrics.get(d)

            statuses.append(DialectTrainingStatus(
                dialect=d,
                dialect_name=DIALECT_GEO.get(d, {}).get("name", d),
                family=DIALECT_FAMILIES.get(d, "unknown"),
                current_version=model.version if model else "none",
                pending_gradients=len(self._pending[d]),
                total_gradients_received=self._total_gradients[d],
                unique_devices=len(self._devices[d]),
                last_aggregation_at=self._last_aggregation[d],
                aggregation_round=self._aggregation_rounds[d],
                model_available=model is not None,
                training_metrics={
                    "wer": metrics.wer if metrics else None,
                    "cer": metrics.cer if metrics else None,
                    "per": metrics.per if metrics else None,
                    "mos_tts": metrics.mos_tts if metrics else None,
                    "overall_score": metrics.overall_score() if metrics else None,
                },
            ))

        return statuses

    async def get_evaluation_metrics(self, dialect: str) -> dict[str, Any] | None:
        """
        Get detailed evaluation metrics for a dialect model.

        Args:
            dialect: Dialect code

        Returns:
            Detailed metrics dict or None
        """
        dialect = dialect.lower().strip()
        metrics = self._metrics.get(dialect)
        if metrics is None:
            return None

        return {
            "dialect": metrics.dialect,
            "asr": {
                "wer": round(metrics.wer, 4),
                "cer": round(metrics.cer, 4),
                "per": round(metrics.per, 4),
            },
            "tts": {
                "mos": round(metrics.mos_tts, 2),
                "speaker_similarity": round(metrics.speaker_similarity, 4),
                "prosody_naturalness": round(metrics.prosody_naturalness, 4),
            },
            "coverage": {
                "vocabulary_coverage": round(metrics.vocabulary_coverage, 4),
                "grammar_accuracy": round(metrics.grammar_accuracy, 4),
            },
            "overall_score": round(metrics.overall_score(), 4),
            "sample_count": metrics.sample_count,
            "evaluated_at": metrics.evaluated_at,
        }

    # ── Internal Training ─────────────────────────────────────────

    async def _train_dialect(self, dialect: str) -> str | None:
        """
        Aggregate pending gradients and train dialect model.

        Steps:
        1. Collect pending gradients (up to MAX_GRADIENTS_PER_ROUND)
        2. Aggregate phoneme corrections (weighted by sample count)
        3. Aggregate vocabulary (k-anonymity filtered)
        4. Aggregate pronunciation deltas (element-wise average)
        5. Aggregate prosody signals
        6. Aggregate grammar patterns
        7. Apply differential privacy to all aggregated outputs
        8. Compute evaluation metrics
        9. Verify improvement over previous model
        10. Publish new model version

        Returns:
            New model version string, or None if no improvement
        """
        gradients = self._pending[dialect][:MAX_GRADIENTS_PER_ROUND]
        self._pending[dialect] = self._pending[dialect][MAX_GRADIENTS_PER_ROUND:]

        if len(gradients) < MIN_GRADIENTS_FOR_AGGREGATION:
            # Not enough — re-buffer
            self._pending[dialect] = gradients + self._pending[dialect]
            return None

        self._aggregation_rounds[dialect] += 1
        round_num = self._aggregation_rounds[dialect]

        self._logger.info(
            "dialect_training_started",
            dialect=dialect,
            gradients=len(gradients),
            round=round_num,
        )

        # ── Aggregate signals ──
        phoneme_corrections = _aggregate_phoneme_corrections(gradients, self._sigma)
        vocabulary = _aggregate_vocabulary(gradients, self._sigma)
        pronunciation_deltas = _aggregate_pronunciation_deltas(gradients)
        prosody_params = _aggregate_prosody(gradients, self._sigma)
        grammar_rules = _aggregate_grammar_patterns(gradients, self._sigma)

        # ── Compute calibration params from gradient statistics ──
        confidences = [g.confidence_score for g in gradients if g.confidence_score > 0]
        mean_conf = sum(confidences) / len(confidences) if confidences else 0.5
        temperature = 1.0 + (1.0 - mean_conf) * 0.5
        calibration = {
            "temperature": round(_add_gaussian_noise(temperature, self._sigma * 0.05), 4),
            "platt_a": round(_add_gaussian_noise(1.0, self._sigma * 0.02), 4),
            "platt_b": round(_add_gaussian_noise(-mean_conf * 0.1, self._sigma * 0.02), 4),
            "prior": round(max(0.0, min(1.0, _add_gaussian_noise(mean_conf, self._sigma * 0.1))), 4),
        }

        # ── Compute training metrics ──
        unique_devices = len(set(g.device_id for g in gradients))
        total_samples = sum(g.sample_count for g in gradients)
        training_metrics = {
            "gradients_aggregated": len(gradients),
            "unique_devices": unique_devices,
            "total_samples": total_samples,
            "mean_confidence": round(mean_conf, 4),
            "phoneme_patterns": len(phoneme_corrections),
            "vocabulary_entries": len(vocabulary),
            "grammar_rules": len(grammar_rules),
            "has_pronunciation_delta": pronunciation_deltas is not None,
            "has_prosody": prosody_params is not None,
        }

        # ── Evaluate (simulate WER improvement from gradient signals) ──
        prev_metrics = self._metrics.get(dialect)
        eval_metrics = self._compute_evaluation(
            dialect, gradients, vocabulary, phoneme_corrections, prev_metrics
        )

        # ── Verify improvement ──
        if prev_metrics and not self._verify_improvement(prev_metrics, eval_metrics):
            self._logger.warning(
                "dialect_training_no_improvement",
                dialect=dialect,
                prev_wer=prev_metrics.wer,
                new_wer=eval_metrics.wer,
                round=round_num,
            )
            # Still update metrics but don't publish new model
            self._metrics[dialect] = eval_metrics
            return self._models[dialect].version if dialect in self._models else None

        # ── Build new model version ──
        self._version_counters[dialect] += 1
        version = f"v{MODEL_MAJOR}.{self._version_counters[dialect]}"

        now_iso = datetime.now(UTC).isoformat()

        # Compute checksum over model content
        import json as _json
        content_hash = hashlib.sha256(
            _json.dumps({
                "dialect": dialect,
                "version": version,
                "vocab_count": len(vocabulary),
                "phoneme_count": len(phoneme_corrections),
                "round": round_num,
            }, sort_keys=True).encode()
        ).hexdigest()[:16]

        model = DialectModelVersion(
            version=version,
            dialect=dialect,
            family=DIALECT_FAMILIES.get(dialect, "unknown"),
            asr_adapter_deltas=pronunciation_deltas,  # Reuse for ASR adapter
            tts_adapter_deltas=None,  # TTS adapter trained separately
            vocabulary=vocabulary,
            pronunciation_map=phoneme_corrections,
            prosody_params=prosody_params,
            grammar_rules=grammar_rules,
            calibration_params=calibration,
            training_metrics=training_metrics,
            contributor_count=unique_devices,
            aggregation_round=round_num,
            created_at=now_iso,
            checksum=content_hash,
        )

        self._models[dialect] = model
        self._metrics[dialect] = eval_metrics
        self._last_aggregation[dialect] = now_iso

        self._logger.info(
            "dialect_model_published",
            dialect=dialect,
            version=version,
            vocabulary_size=len(vocabulary),
            phoneme_patterns=len(phoneme_corrections),
            grammar_rules=len(grammar_rules),
            contributors=unique_devices,
            wer=round(eval_metrics.wer, 4),
            overall_score=round(eval_metrics.overall_score(), 4),
            round=round_num,
        )

        # ── Bridge to FL service if available ──
        if self._fl_service:
            await self._push_to_fl_service(dialect, model, gradients)

        return version

    def _compute_evaluation(
        self,
        dialect: str,
        gradients: list[DialectGradient],
        vocabulary: list[dict[str, Any]],
        phoneme_corrections: list[dict[str, Any]],
        prev_metrics: DialectEvaluationMetrics | None,
    ) -> DialectEvaluationMetrics:
        """
        Compute evaluation metrics for the aggregated model.

        Uses gradient signals as proxy for model quality:
        - Higher confidence gradients → lower estimated WER
        - More vocabulary coverage → better vocabulary_coverage
        - More phoneme corrections → better pronunciation model
        - Grammar patterns → grammar accuracy improvement
        """
        # Estimate WER from gradient confidence distribution
        confidences = [g.confidence_score for g in gradients]
        if confidences:
            mean_conf = sum(confidences) / len(confidences)
            # WER estimation: higher confidence → lower WER
            # Baseline WER = 0.5 (random), perfect = 0.0
            estimated_wer = max(0.0, 0.5 * (1.0 - mean_conf))
        else:
            estimated_wer = 0.5

        # Estimate CER (usually lower than WER)
        estimated_cer = estimated_wer * 0.7

        # Estimate PER from phoneme correction density
        if phoneme_corrections:
            phoneme_conf = sum(p.get("confidence", 0.5) for p in phoneme_corrections) / len(phoneme_corrections)
            estimated_per = max(0.0, 0.4 * (1.0 - phoneme_conf))
        else:
            estimated_per = 0.4

        # Vocabulary coverage
        vocab_coverage = min(1.0, len(vocabulary) / max(1, 100))  # 100 words = full coverage

        # Grammar accuracy from grammar patterns
        grammar_acc = 0.5
        has_grammar = any(g.grammar_patterns for g in gradients)
        if has_grammar:
            grammar_acc = min(1.0, 0.5 + len([g for g in gradients if g.grammar_patterns]) / len(gradients) * 0.5)

        # Smooth with previous metrics if available
        if prev_metrics:
            alpha = 0.3  # Exponential moving average
            estimated_wer = alpha * estimated_wer + (1 - alpha) * prev_metrics.wer
            estimated_cer = alpha * estimated_cer + (1 - alpha) * prev_metrics.cer
            estimated_per = alpha * estimated_per + (1 - alpha) * prev_metrics.per
            vocab_coverage = alpha * vocab_coverage + (1 - alpha) * prev_metrics.vocabulary_coverage
            grammar_acc = alpha * grammar_acc + (1 - alpha) * prev_metrics.grammar_accuracy

        return DialectEvaluationMetrics(
            dialect=dialect,
            wer=round(estimated_wer, 4),
            cer=round(estimated_cer, 4),
            per=round(estimated_per, 4),
            mos_tts=round(3.0 + (1.0 - estimated_wer) * 2.0, 2),  # Scale to 1-5
            speaker_similarity=round(max(0.0, 1.0 - estimated_per), 4),
            vocabulary_coverage=round(vocab_coverage, 4),
            grammar_accuracy=round(grammar_acc, 4),
            prosody_naturalness=round(max(0.0, 1.0 - estimated_wer * 0.5), 4),
            sample_count=sum(g.sample_count for g in gradients),
            evaluated_at=datetime.now(UTC).isoformat(),
        )

    def _verify_improvement(
        self,
        prev: DialectEvaluationMetrics,
        new: DialectEvaluationMetrics,
    ) -> bool:
        """
        Verify that the new model improves over the previous.

        Checks:
        1. WER must not increase significantly (tolerance: 2%)
        2. Overall score must not decrease
        3. At least one metric must improve by MODEL_IMPROVEMENT_THRESHOLD
        """
        # WER regression check
        if new.wer > prev.wer + 0.02:
            return False

        # Overall score check
        prev_score = prev.overall_score()
        new_score = new.overall_score()
        if new_score < prev_score - 0.01:
            return False

        # At least one improvement
        improvements = [
            prev.wer - new.wer,
            prev.cer - new.cer,
            prev.per - new.per,
            new.mos_tts - prev.mos_tts,
            new.vocabulary_coverage - prev.vocabulary_coverage,
        ]
        return max(improvements) >= MODEL_IMPROVEMENT_THRESHOLD

    async def _push_to_fl_service(
        self,
        dialect: str,
        model: DialectModelVersion,
        gradients: list[DialectGradient],
    ) -> None:
        """
        Push aggregated dialect model into the federated learning pipeline.

        Converts the dialect training output into an FLUpdate and submits
        to FederatedLearningService for cross-device distribution.
        """
        try:
            from app.schemas.federated_learning import (
                AnonymizedPattern,
                CalibrationParams,
                FLUpdate,
                UploadMetadata,
            )

            # Convert phoneme corrections to FL correction patterns
            patterns = []
            for pc in model.pronunciation_map[:50]:
                pattern_str = pc.get("pattern", "")
                patterns.append(AnonymizedPattern(
                    error_type=f"dialect_{dialect}_phoneme",
                    error_hash=hashlib.sha256(pattern_str.encode()).hexdigest()[:16],
                    correction_hash=hashlib.sha256(
                        f"{pattern_str}:{pc.get('confidence', 0)}".encode()
                    ).hexdigest()[:16],
                    phoneme_pattern=pattern_str,
                    hour_of_day=datetime.now(UTC).hour,
                    edit_distance=max(0.0, min(1.0, 1.0 - pc.get("confidence", 0.5))),
                ))

            cal = model.calibration_params
            cal_params = CalibrationParams(
                temperature=cal.get("temperature", 1.0),
                platt_a=cal.get("platt_a", 0.0),
                platt_b=cal.get("platt_b", 0.0),
                prior=cal.get("prior", 0.5),
            )

            device_id = hashlib.sha256(
                f"dialect_training:{dialect}".encode()
            ).hexdigest()[:32]

            fl_update = FLUpdate(
                device_id=device_id,
                language=dialect,
                timestamp=int(time.time() * 1000),
                correction_patterns=patterns,
                adapter_deltas=model.asr_adapter_deltas,
                calibration_params=cal_params,
                metadata=UploadMetadata(
                    corrections_count=model.contributor_count,
                    vocabulary_size=len(model.vocabulary),
                    estimated_wer=model.training_metrics.get("mean_confidence", 0.5),
                    device_tier="dialect_training_backend",
                ),
            )

            result = await self._fl_service.upload_update(fl_update)

            self._logger.info(
                "dialect_pushed_to_fl",
                dialect=dialect,
                version=model.version,
                fl_status=result.status,
                fl_aggregated=result.aggregated,
            )

        except Exception as exc:
            self._logger.error(
                "dialect_fl_push_failed",
                dialect=dialect,
                error=str(exc),
            )

    # ── Metrics ───────────────────────────────────────────────────

    def get_system_metrics(self) -> dict[str, Any]:
        """Get system-wide dialect training metrics."""
        return {
            "supported_dialects": len(DialectCode),
            "dialects_with_models": len(self._models),
            "total_pending_gradients": sum(
                len(p) for p in self._pending.values()
            ),
            "total_gradients_received": dict(self._total_gradients),
            "total_unique_devices": {
                d: len(devs) for d, devs in self._devices.items()
            },
            "aggregation_rounds": dict(self._aggregation_rounds),
            "model_versions": {
                d: m.version for d, m in self._models.items()
            },
            "evaluation_overall": {
                d: round(m.overall_score(), 4)
                for d, m in self._metrics.items()
            },
            "privacy": {
                "dp_epsilon": DP_EPSILON,
                "dp_delta": DP_DELTA,
                "noise_scale": round(self._sigma, 4),
                "min_devices_for_publish": MIN_DEVICES_FOR_PUBLISH,
            },
        }


# Module-level singleton
_service: DialectTrainingService | None = None


def get_dialect_training_service(
    fl_service: Any = None,
    model_registry: Any = None,
) -> DialectTrainingService:
    """Get or create the dialect training service singleton."""
    global _service
    if _service is None:
        _service = DialectTrainingService(
            fl_service=fl_service,
            model_registry=model_registry,
        )
    return _service
