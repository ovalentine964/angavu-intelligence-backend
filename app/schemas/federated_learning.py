"""
Federated learning request/response schemas.

Defines the data contract between Msaidizi Android devices and the
federated learning server. Aligns with FederatedLearningClient.kt
data classes on the device side.

Privacy model:
- Devices send anonymized correction patterns (no raw text/audio)
- LoRA adapter deltas are encrypted client-side
- Differential privacy is applied with consistent ε=0.1 (client + server)
  to ensure the composed privacy budget is ε_total ≤ 0.2
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────────────
# Client → Server (upload)
# ──────────────────────────────────────────────────────────────────────


class AnonymizedPattern(BaseModel):
    """Anonymized correction pattern from a device (privacy-safe)."""

    error_type: str = Field(..., description="Type of correction error")
    error_hash: str = Field(..., description="SHA-256 hash of original text")
    correction_hash: str = Field(..., description="SHA-256 hash of corrected text")
    phoneme_pattern: str = Field("", description="Phoneme-level substitution pattern (e.g. 'th→t')")
    hour_of_day: int = Field(..., ge=0, le=23, description="Hour of correction (0-23)")
    edit_distance: float = Field(..., ge=0.0, le=1.0, description="Normalized edit distance")


class CalibrationParams(BaseModel):
    """Calibration parameters shared by devices."""

    temperature: float = Field(1.0, description="Temperature scaling parameter")
    platt_a: float = Field(0.0, description="Platt scaling parameter A")
    platt_b: float = Field(0.0, description="Platt scaling parameter B")
    prior: float = Field(0.5, description="Prior probability")


class UploadMetadata(BaseModel):
    """Metadata about the device's local training."""

    corrections_count: int = Field(0, description="Number of local corrections used")
    vocabulary_size: int = Field(0, description="Local vocabulary size")
    estimated_wer: float = Field(0.0, ge=0.0, le=1.0, description="Estimated word error rate")
    device_tier: str = Field("basic", description="Device compute tier")


class FLUpdate(BaseModel):
    """
    Federated learning update from a device.

    Matches FederatedUpload data class in FederatedLearningClient.kt.
    Sent as gzip-compressed JSON with Content-Encoding: gzip.
    """

    device_id: str = Field(..., description="SHA-256 hashed device ID (anonymized)")
    language: str = Field(..., description="Language code (e.g. 'sw', 'en', 'luo')")
    timestamp: int = Field(..., description="Device-side epoch milliseconds")
    correction_patterns: list[AnonymizedPattern] = Field(
        default_factory=list,
        description="Anonymized correction patterns with differential privacy applied",
    )
    adapter_deltas: str | None = Field(
        None,
        description="Base64-encoded encrypted LoRA adapter weight deltas",
    )
    calibration_params: CalibrationParams | None = Field(
        None,
        description="Calibration parameters to merge into global model",
    )
    metadata: UploadMetadata | None = Field(
        None,
        description="Device training metadata",
    )


# ──────────────────────────────────────────────────────────────────────
# Server → Client (download)
# ──────────────────────────────────────────────────────────────────────


class VocabularyUpdate(BaseModel):
    """A single vocabulary update from the global model."""

    word: str = Field(..., description="Vocabulary entry")
    frequency: int = Field(..., ge=0, description="Global frequency count")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")


class GlobalModelResponse(BaseModel):
    """
    Global model download for a language/dialect.

    Matches FederatedDownload data class in FederatedLearningClient.kt.
    """

    version: str = Field(..., description="Model version (e.g. 'v3.2.1')")
    language: str = Field(..., description="Language/dialect code")
    adapter_deltas: str | None = Field(
        None,
        description="Base64-encoded aggregated LoRA adapter deltas",
    )
    calibration_params: CalibrationParams | None = Field(
        None,
        description="Global calibration parameters",
    )
    vocabulary_updates: list[VocabularyUpdate] | None = Field(
        None,
        description="Aggregated vocabulary updates",
    )
    timestamp: int = Field(
        default_factory=lambda: int(datetime.now(UTC).timestamp() * 1000),
        description="Server timestamp (epoch ms)",
    )


class FLStatusResponse(BaseModel):
    """Federated learning system status."""

    status: str = Field("ok", description="System status")
    total_updates_received: int = Field(0)
    active_devices: int = Field(0)
    languages_supported: list[str] = Field(default_factory=list)
    current_global_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Current model version per language",
    )
    last_aggregation_at: str | None = Field(None)
    aggregation_round: int = Field(0)
    differential_privacy: dict[str, Any] = Field(
        default_factory=lambda: {
            "epsilon": 0.1,
            "delta": 1e-5,
            "mechanism": "gaussian",
            "client_epsilon": 0.1,
            "server_epsilon": 0.1,
            "composed_budget": 0.2,
        },
    )


class UploadResponse(BaseModel):
    """Response to an FL update upload."""

    status: str = Field("accepted", description="Upload status")
    update_id: str = Field(..., description="Server-assigned update ID")
    device_id: str = Field(..., description="Echoed device ID")
    language: str = Field(..., description="Echoed language")
    aggregated: bool = Field(False, description="Whether this update triggered aggregation")
    next_download_version: str | None = Field(
        None,
        description="New model version available for download, if any",
    )
