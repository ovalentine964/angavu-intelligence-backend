"""
Dialect Dictionary schemas — request/response models for the dialect
dictionary service, language aggregation, and model distribution APIs.

Privacy model:
- Words are submitted with anonymized worker IDs (SHA-256 hashed)
- K-anonymity (k≥5) enforced before any word enters the shared dictionary
- Bayesian confidence scoring prevents low-quality entries from propagating
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Dialect Dictionary — Submit / Lookup
# ──────────────────────────────────────────────────────────────────────


class WordSubmission(BaseModel):
    """A single word submission from a worker device."""

    word: str = Field(
        ..., min_length=1, max_length=200,
        description="The word or phrase learned",
    )
    dialect: str = Field(
        ..., min_length=2, max_length=10,
        description="Dialect code (e.g. 'sw', 'luo', 'kik', 'kal')",
    )
    context: str = Field(
        "", max_length=1000,
        description="Sentence or context where the word was observed",
    )
    pronunciation_ipa: Optional[str] = Field(
        None, max_length=200,
        description="IPA pronunciation hint (optional)",
    )
    frequency_hint: int = Field(
        1, ge=1, le=10000,
        description="How many times the worker observed this word locally",
    )


class DialectSubmitRequest(BaseModel):
    """POST /api/v1/dialect/submit — batch word submission."""

    worker_id: str = Field(
        ..., description="SHA-256 hashed worker device ID (anonymized)",
    )
    words: List[WordSubmission] = Field(
        ..., min_length=1, max_length=500,
        description="Batch of observed words (max 500 per submission)",
    )
    region: Optional[str] = Field(
        None, description="Geographic region code (e.g. 'nairobi', 'kisumu')",
    )
    timestamp: Optional[int] = Field(
        None, description="Device-side epoch milliseconds",
    )


class WordEntry(BaseModel):
    """A single word in the dialect dictionary."""

    word: str
    dialect: str
    frequency: int = Field(..., description="Total occurrence count across all workers")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Bayesian confidence score")
    contributor_count: int = Field(..., description="Number of distinct workers who submitted this word")
    contexts: List[str] = Field(default_factory=list, description="Sample contexts (max 5)")
    pronunciation_ipa: Optional[str] = None
    regions: List[str] = Field(default_factory=list, description="Regions where observed")
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


class DialectLookupResponse(BaseModel):
    """GET /api/v1/dialect/lookup response."""

    query: str
    dialect: Optional[str] = None
    results: List[WordEntry] = Field(default_factory=list)
    total_results: int = 0


class DialectSubmitResponse(BaseModel):
    """POST /api/v1/dialect/submit response."""

    status: str = "accepted"
    words_received: int
    words_accepted: int
    words_rejected: int
    rejection_reasons: Dict[str, int] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Language Aggregation — Federated dialect building
# ──────────────────────────────────────────────────────────────────────


class DialectPattern(BaseModel):
    """Aggregated dialect pattern from multiple workers."""

    pattern_type: str = Field(..., description="'pronunciation', 'grammar', 'vocabulary'")
    pattern: str = Field(..., description="The pattern string")
    dialect: str
    frequency: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    contributing_workers: int = Field(..., description="Workers contributing (k-anonymity enforced)")


class RegionDialectSummary(BaseModel):
    """Summary of dialect data for a geographic region."""

    region: str
    dialects: List[str]
    total_words: int
    unique_words: int
    top_words: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top 20 words by frequency",
    )
    contributing_workers: int
    last_aggregated: Optional[str] = None


class AggregationStatusResponse(BaseModel):
    """Status of the language aggregation system."""

    status: str = "ok"
    total_words_tracked: int = 0
    total_dialects: int = 0
    total_workers_contributing: int = 0
    last_aggregation_at: Optional[str] = None
    dialects: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    privacy: Dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# Model Distribution — Delta updates for on-device consumption
# ──────────────────────────────────────────────────────────────────────


class DialectModelVersion(BaseModel):
    """Version information for a dialect model."""

    dialect: str
    version: str = Field(..., description="Semantic version (e.g. '1.3.7')")
    word_count: int
    created_at: str
    checksum: str = Field(..., description="SHA-256 of the model payload")
    is_delta: bool = Field(False, description="True if this is a delta update")


class DeltaUpdatePayload(BaseModel):
    """Delta update — only new/changed words since client's version."""

    dialect: str
    base_version: str = Field(..., description="Client's current version")
    target_version: str = Field(..., description="Server's latest version")
    new_words: List[WordEntry] = Field(default_factory=list)
    updated_words: List[WordEntry] = Field(default_factory=list)
    removed_words: List[str] = Field(default_factory=list, description="Words removed (below confidence threshold)")
    checksum: str
    compressed_size_bytes: int = 0


class FullModelPayload(BaseModel):
    """Full dialect model for fresh installs."""

    dialect: str
    version: str
    words: List[WordEntry]
    checksum: str
    total_words: int
    compressed_size_bytes: int = 0


class ModelDistributionResponse(BaseModel):
    """GET /api/v1/dialect/model/{dialect} response."""

    update_type: str = Field(..., description="'delta' or 'full'")
    dialect: str
    version: str
    payload: Dict[str, Any] = Field(..., description="DeltaUpdatePayload or FullModelPayload as dict")
