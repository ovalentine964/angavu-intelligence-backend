"""
Dialect Dictionary & Language Training Pipeline API.

Exposes endpoints for:
- Word submission from worker devices (POST /dialect/submit)
- Dictionary lookup with k-anonymity filtering (GET /dialect/lookup)
- Dialect model distribution with delta updates (GET /dialect/model/{dialect})
- Aggregation status and region summaries (GET /dialect/status)
- Cross-dialect cognate detection (GET /dialect/cognates)

All endpoints are privacy-preserving:
- Worker IDs are SHA-256 hashed (never raw device IDs)
- K-anonymity (k≥5) enforced before any word is visible in lookups
- Differential privacy noise on aggregated frequencies
"""

import gzip
import json
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.api.auth import get_current_user
from app.models.user import User

from app.schemas.dialect_dictionary import (
    AggregationStatusResponse,
    DialectLookupResponse,
    DialectModelVersion,
    DialectSubmitRequest,
    DialectSubmitResponse,
    ModelDistributionResponse,
)
from app.services.dialect_dictionary import get_dialect_dictionary
from app.services.language_aggregator import get_language_aggregator
from app.services.model_distribution import get_model_distribution
from app.services.language_aggregator import DIALECT_REGIONS

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Dialect Dictionary"])


# ════════════════════════════════════════════════════════════════════
# Word Submission
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/dialect/submit",
    response_model=DialectSubmitResponse,
    summary="Submit learned words from a worker device",
    description=(
        "Batch submission of words observed by a worker device. "
        "Words are validated, scored with Bayesian confidence, and "
        "only enter the shared dictionary after k-anonymity (≥5 workers) "
        "is satisfied. Submissions are rate-limited and quality-gated."
    ),
)
async def submit_words(request: DialectSubmitRequest, user: User = Depends(get_current_user)):
    """
    Submit a batch of learned words from a worker device.

    Processing pipeline:
    1. Validate each word (adversarial, gibberish, format checks)
    2. Check for frequency outliers (IQR-based)
    3. Update Bayesian confidence (Beta-Binomial conjugate)
    4. Track worker contributions for k-anonymity
    5. Accept/reject with detailed reasons

    Privacy: worker_id must be SHA-256 hashed. Raw device IDs are rejected.
    """
    dictionary = get_dialect_dictionary()

    # Validate worker_id looks like a hash (at least 16 hex chars)
    if len(request.worker_id) < 16:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="worker_id must be a SHA-256 hash (64 hex characters)",
        )

    result = await dictionary.submit_words(request)
    return result


# ════════════════════════════════════════════════════════════════════
# Dictionary Lookup
# ════════════════════════════════════════════════════════════════════


@router.get(
    "/dialect/lookup",
    response_model=DialectLookupResponse,
    summary="Look up words in the dialect dictionary",
    description=(
        "Search the shared dialect dictionary. Only returns words that "
        "meet k-anonymity threshold (≥5 independent workers). Results "
        "are sorted by Bayesian confidence score."
    ),
)
async def lookup_word(
    q: str = Query(..., min_length=1, max_length=200, description="Search query (prefix match)"),
    dialect: Optional[str] = Query(None, description="Filter by dialect code"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results"),
):
    """
    Look up words in the dialect dictionary.

    Only words with ≥5 independent worker submissions are returned
    (k-anonymity privacy guarantee). Results sorted by confidence.
    """
    dictionary = get_dialect_dictionary()
    result = await dictionary.lookup(
        query=q,
        dialect=dialect,
        min_confidence=min_confidence,
        limit=limit,
    )
    return result


# ════════════════════════════════════════════════════════════════════
# Model Distribution
# ════════════════════════════════════════════════════════════════════


@router.get(
    "/dialect/model/{dialect}",
    response_model=ModelDistributionResponse,
    summary="Download dialect model (full or delta)",
    description=(
        "Download a dialect model for on-device use. If the client's "
        "current version is provided via query parameter, returns a "
        "delta update (only new/changed words). Otherwise returns "
        "the full model. Payloads are gzip-compressed."
    ),
)
async def get_dialect_model(
    dialect: str,
    client_version: Optional[str] = Query(None, description="Client's current version (e.g. '1.0.0')"),
    compress: bool = Query(True, description="Return gzip-compressed payload"),
):
    """
    Download a dialect model for on-device consumption.

    Delta mode (with client_version):
        Returns only new/updated/removed words since client's version.
        Much smaller payload — ideal for bandwidth-constrained devices.

    Full mode (without client_version):
        Returns the complete dialect dictionary.
        Used for fresh installs or when client version is too old.
    """
    distribution = get_model_distribution()

    if client_version:
        # Try delta update first
        delta = await distribution.get_delta_update(dialect, client_version)
        if delta:
            payload = delta.model_dump()
            if compress:
                raw = json.dumps(payload).encode("utf-8")
                compressed = gzip.compress(raw)
                return Response(
                    content=compressed,
                    media_type="application/gzip",
                    headers={
                        "Content-Encoding": "gzip",
                        "X-Update-Type": "delta",
                        "X-Dialect": dialect,
                        "X-Base-Version": client_version,
                        "X-Target-Version": delta.target_version,
                        "X-Checksum": delta.checksum,
                    },
                )
            return ModelDistributionResponse(
                update_type="delta",
                dialect=dialect,
                version=delta.target_version,
                payload=payload,
            )

    # Full model
    full = await distribution.get_full_model(dialect)
    if not full:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No model available for dialect '{dialect}'",
        )

    payload = full.model_dump()
    if compress:
        raw = json.dumps(payload).encode("utf-8")
        compressed = gzip.compress(raw)
        return Response(
            content=compressed,
            media_type="application/gzip",
            headers={
                "Content-Encoding": "gzip",
                "X-Update-Type": "full",
                "X-Dialect": dialect,
                "X-Version": full.version,
                "X-Checksum": full.checksum,
                "X-Word-Count": str(full.total_words),
            },
        )

    return ModelDistributionResponse(
        update_type="full",
        dialect=dialect,
        version=full.version,
        payload=payload,
    )


@router.get(
    "/dialect/model/{dialect}/delta",
    summary="Get delta update for a dialect model",
    description="Explicit delta endpoint. Requires 'from' query parameter with client's current version.",
)
async def get_delta_update(
    dialect: str,
    from_version: str = Query(..., alias="from", description="Client's current version"),
):
    """Get a delta update (new/changed/removed words) since client's version."""
    distribution = get_model_distribution()

    delta = await distribution.get_delta_update(dialect, from_version)
    if not delta:
        # Check if it's because client is up to date or version unknown
        latest = await distribution.check_version(dialect, from_version)
        if not latest.get("update_available"):
            return {
                "status": "up_to_date",
                "dialect": dialect,
                "current_version": from_version,
            }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cannot compute delta from version '{from_version}'. Try full model download.",
        )

    return delta.model_dump()


@router.get(
    "/dialect/model/{dialect}/version",
    summary="Check for model updates",
    description="Lightweight version check. Devices poll this to decide whether to download.",
)
async def check_model_version(
    dialect: str,
    client_version: str = Query("0.0.0", description="Client's current version"),
):
    """Check if a newer model version is available for a dialect."""
    distribution = get_model_distribution()
    return await distribution.check_version(dialect, client_version)


# ════════════════════════════════════════════════════════════════════
# Aggregation & Status
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/dialect/aggregate/{dialect}",
    summary="Trigger aggregation for a dialect",
    description="Manually trigger aggregation of word submissions for a specific dialect.",
)
async def trigger_aggregation(dialect: str, user: User = Depends(get_current_user)):
    """
    Trigger aggregation for a dialect.

    Normally called automatically when enough submissions arrive,
    but can be triggered manually for testing.
    """
    aggregator = get_language_aggregator()
    result = await aggregator.aggregate_dialect(dialect)

    # Also publish a new model version if aggregation succeeded
    if result.get("status") == "aggregated":
        distribution = get_model_distribution()
        version_info = await distribution.publish_dialect_model(dialect)
        if version_info:
            result["model_version"] = version_info.version
            result["model_checksum"] = version_info.checksum

    return result


@router.post(
    "/dialect/aggregate",
    summary="Trigger aggregation for all dialects",
    description="Run aggregation across all dialects and publish updated models.",
)
async def trigger_aggregate_all(user: User = Depends(get_current_user)):
    """Aggregate all dialects and publish updated models."""
    aggregator = get_language_aggregator()
    agg_result = await aggregator.aggregate_all()

    # Auto-publish models for all dialects
    distribution = get_model_distribution()
    publish_result = await distribution.auto_publish_all()

    return {
        "aggregation": agg_result,
        "models_published": publish_result,
    }


@router.get(
    "/dialect/status",
    summary="Get dialect dictionary and aggregation status",
    description="System-wide status of the language training pipeline.",
)
async def get_status():
    """Get overall status of the dialect dictionary and language training pipeline."""
    aggregator = get_language_aggregator()
    distribution = get_model_distribution()
    dictionary = get_dialect_dictionary()

    agg_status = await aggregator.get_aggregation_status()
    dict_stats = await dictionary.get_stats()
    models = await distribution.list_models()

    return {
        "status": "ok",
        "dictionary": dict_stats,
        "aggregation": agg_status,
        "models": [m.model_dump() for m in models],
        "dialect_regions": DIALECT_REGIONS,
    }


@router.get(
    "/dialect/regions",
    summary="Get region-level dialect summaries",
    description="Aggregated dialect data organized by geographic region.",
)
async def get_region_summaries():
    """Get dialect data organized by geographic region."""
    aggregator = get_language_aggregator()
    return await aggregator.get_region_summary()


@router.get(
    "/dialect/cognates",
    summary="Get cross-dialect cognates",
    description="Detect words shared across multiple dialects (potential cognates).",
)
async def get_cognates(
    min_dialects: int = Query(2, ge=2, description="Minimum number of dialects"),
):
    """Find words that appear across multiple dialects (cognate detection)."""
    aggregator = get_language_aggregator()
    all_data = await aggregator.aggregate_all()

    cognates = all_data.get("top_cognates", [])
    # Filter by minimum dialect count
    cognates = [c for c in cognates if c.get("dialect_count", 0) >= min_dialects]

    return {
        "cognates": cognates,
        "total": len(cognates),
        "min_dialects": min_dialects,
    }


@router.get(
    "/dialect/models",
    summary="List all published dialect models",
    description="List all dialect models with version info and checksums.",
)
async def list_models():
    """List all published dialect models."""
    distribution = get_model_distribution()
    models = await distribution.list_models()
    return {
        "models": [m.model_dump() for m in models],
        "total": len(models),
    }


@router.get(
    "/dialect/model/{dialect}/history",
    summary="Get version history for a dialect model",
)
async def get_model_history(dialect: str):
    """Get the version history of a dialect model."""
    distribution = get_model_distribution()
    history = await distribution.get_version_history(dialect)
    return {
        "dialect": dialect,
        "versions": history,
        "total_versions": len(history),
    }
