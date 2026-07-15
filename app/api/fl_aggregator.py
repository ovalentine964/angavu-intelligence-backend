"""
Federated Aggregator REST API — Advanced aggregation server.

Exposes the FederatedAggregator (from msaidizi-language-pipeline) as
REST endpoints. Supports FedAvg, Krum, and Trimmed Mean aggregation
with secure aggregation (gradient encryption) and anomaly detection.

Endpoints:
- POST /fl-aggregator/delta     — Submit a gradient delta
- POST /fl-aggregator/aggregate — Trigger aggregation for a cohort
- GET  /fl-aggregator/status    — System-wide stats
- GET  /fl-aggregator/cohort/{cohort_id} — Per-cohort stats
- GET  /fl-aggregator/model/{cohort_id}  — Get latest aggregated model
"""

import sys
import os
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Federated Aggregator"])

# Import FederatedAggregator from language pipeline
_pipeline_path = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "msaidizi-language-pipeline"
)
if os.path.isdir(_pipeline_path):
    sys.path.insert(0, os.path.abspath(_pipeline_path))

try:
    from federated_learning import (
        FederatedAggregator,
        GradientDelta,
        AggregationMethod,
        DifferentialPrivacy,
    )
    _aggregator = FederatedAggregator()
    _aggregator_available = True
except ImportError as e:
    logger.warning("fl_aggregator_import_failed", error=str(e))
    _aggregator = None
    _aggregator_available = False


# ════════════════════════════════════════════════════════════════════
# Request / Response Schemas
# ════════════════════════════════════════════════════════════════════


class GradientDeltaRequest(BaseModel):
    """Request to submit a gradient delta from a device."""
    device_id_hash: str = Field(..., description="SHA-256 hashed device ID")
    user_id_hash: str = Field("", description="SHA-256 hashed user ID")
    dialect: str = Field(..., description="Language/dialect code (e.g. 'sw', 'luo')")
    adapter_type: str = Field("user", description="Adapter type: 'user' or 'dialect'")
    weight_delta: Dict[str, Any] = Field(..., description="LoRA weight changes (serialized)")
    delta_l2_norm: float = Field(..., description="L2 norm of the delta")
    num_examples: int = Field(1, description="Number of training examples used")
    training_loss: float = Field(0.0, description="Final training loss")
    round_id: int = Field(0, description="Federated round ID")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AggregateRequest(BaseModel):
    """Request to trigger aggregation for a cohort."""
    cohort_id: str = Field(..., description="Cohort ID (e.g. 'sw_user', 'luo_dialect')")


class AggregateResponse(BaseModel):
    """Response from aggregation."""
    status: str
    cohort_id: Optional[str] = None
    version: Optional[str] = None
    num_contributors: int = 0
    avg_loss: float = 0.0
    quality_score: float = 0.0
    is_anomaly_detected: bool = False
    anomaly_details: Optional[str] = None


class AggregatorStatusResponse(BaseModel):
    """System-wide aggregator status."""
    available: bool
    total_deltas_received: int = 0
    total_anomalies_detected: int = 0
    active_cohorts: int = 0
    completed_rounds: int = 0
    aggregation_method: str = "trimmed_mean"
    dp_epsilon: float = 0.1
    dp_delta: float = 1e-5
    secure_aggregation_enabled: bool = True


class CohortStatsResponse(BaseModel):
    """Per-cohort statistics."""
    cohort_id: str
    status: str
    total_rounds: int = 0
    latest_round: int = 0
    latest_contributors: int = 0
    latest_loss: float = 0.0
    latest_quality: float = 0.0
    anomalies_detected: int = 0


# ════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post(
    "/fl-aggregator/delta",
    summary="Submit gradient delta",
    description=(
        "Submit an encrypted gradient delta from a device. "
        "The delta is clipped, noised (DP), and encrypted before storage. "
        "Raw gradients are never visible to the server."
    ),
)
@router.post(
    "/federated/delta",
    summary="Submit gradient delta (alias)",
    include_in_schema=False,
)
async def submit_delta(
    req: GradientDeltaRequest,
    user: User = Depends(get_current_user),
):
    """Submit a gradient delta for federated aggregation."""
    if not _aggregator_available or _aggregator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Federated aggregator not available",
        )

    import time

    delta = GradientDelta(
        device_id_hash=req.device_id_hash,
        user_id_hash=req.user_id_hash,
        dialect=req.dialect,
        adapter_type=req.adapter_type,
        weight_delta=req.weight_delta,
        delta_l2_norm=req.delta_l2_norm,
        num_examples=req.num_examples,
        training_loss=req.training_loss,
        timestamp=time.time(),
        round_id=req.round_id,
        metadata=req.metadata,
    )

    accepted = _aggregator.receive_delta(delta)
    cohort_id = f"{req.dialect}_{req.adapter_type}"

    return {
        "status": "accepted" if accepted else "rejected",
        "cohort_id": cohort_id,
        "cohort_size": len(_aggregator.cohorts.get(cohort_id, [])),
        "secure_aggregation": "gradient_encrypted_with_per_round_key",
    }


@router.post(
    "/fl-aggregator/aggregate",
    response_model=AggregateResponse,
    summary="Trigger aggregation",
    description=(
        "Trigger FedAvg/Krum/Trimmed Mean aggregation for a cohort. "
        "Requires minimum cohort size (default 10). "
        "Anomalous gradients are detected and removed before aggregation."
    ),
)
@router.post(
    "/federated/aggregate",
    response_model=AggregateResponse,
    summary="Trigger aggregation (alias)",
    include_in_schema=False,
)
async def trigger_aggregation(
    req: AggregateRequest,
    user: User = Depends(get_current_user),
):
    """Trigger aggregation for a cohort."""
    if not _aggregator_available or _aggregator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Federated aggregator not available",
        )

    update = _aggregator.try_aggregate(req.cohort_id)

    if update is None:
        cohort_size = len(_aggregator.cohorts.get(req.cohort_id, []))
        return AggregateResponse(
            status="insufficient_deltas",
            cohort_id=req.cohort_id,
            num_contributors=cohort_size,
        )

    return AggregateResponse(
        status="aggregated",
        cohort_id=update.cohort_id,
        num_contributors=update.num_contributors,
        avg_loss=update.avg_loss,
        quality_score=update.quality_score,
        is_anomaly_detected=update.is_anomaly_detected,
        anomaly_details=update.anomaly_details,
    )


@router.get(
    "/fl-aggregator/status",
    response_model=AggregatorStatusResponse,
    summary="Aggregator status",
)
@router.get(
    "/federated/status",
    response_model=AggregatorStatusResponse,
    summary="Aggregator status (alias)",
    include_in_schema=False,
)
async def get_status():
    """Get system-wide federated aggregator status."""
    if not _aggregator_available or _aggregator is None:
        return AggregatorStatusResponse(available=False)

    stats = _aggregator.get_global_stats()
    return AggregatorStatusResponse(
        available=True,
        total_deltas_received=stats["total_deltas_received"],
        total_anomalies_detected=stats["total_anomalies_detected"],
        active_cohorts=stats["active_cohorts"],
        completed_rounds=stats["completed_rounds"],
        aggregation_method=stats["aggregation_method"],
        dp_epsilon=stats["dp_epsilon"],
        dp_delta=stats["dp_delta"],
        secure_aggregation_enabled=True,
    )


@router.get(
    "/fl-aggregator/cohort/{cohort_id}",
    response_model=CohortStatsResponse,
    summary="Cohort statistics",
)
@router.get(
    "/federated/cohort/{cohort_id}",
    response_model=CohortStatsResponse,
    summary="Cohort statistics (alias)",
    include_in_schema=False,
)
async def get_cohort_stats(cohort_id: str):
    """Get statistics for a specific cohort."""
    if not _aggregator_available or _aggregator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Federated aggregator not available",
        )

    stats = _aggregator.get_cohort_stats(cohort_id)
    return CohortStatsResponse(**stats)


@router.get(
    "/fl-aggregator/model/{cohort_id}",
    summary="Get latest aggregated model for a cohort",
)
@router.get(
    "/federated/model/{cohort_id}",
    summary="Get latest aggregated model (alias)",
    include_in_schema=False,
)
async def get_cohort_model(cohort_id: str):
    """Get the latest aggregated model update for a cohort."""
    if not _aggregator_available or _aggregator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Federated aggregator not available",
        )

    updates = _aggregator.cohort_updates.get(cohort_id, [])
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No aggregated model for cohort '{cohort_id}'",
        )

    latest = updates[-1]
    return {
        "cohort_id": latest.cohort_id,
        "dialect": latest.dialect,
        "round_id": latest.round_id,
        "aggregated_delta": latest.aggregated_delta,
        "num_contributors": latest.num_contributors,
        "avg_loss": latest.avg_loss,
        "quality_score": latest.quality_score,
        "is_anomaly_detected": latest.is_anomaly_detected,
        "timestamp": latest.timestamp,
    }
