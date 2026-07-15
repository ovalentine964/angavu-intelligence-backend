"""
Infrastructure V2 API Endpoints.

Exposes the new infrastructure services:
- Health monitoring (server metrics, inference latency, costs)
- Model registry (versions, A/B testing, rollback)
- Federated learning v2 (enhanced privacy, multi-category)

Endpoints:
    GET  /api/v1/infrastructure/health     — Server & cluster health
    GET  /api/v1/infrastructure/models     — Model registry
    POST /api/v1/infrastructure/federated  — Submit federated training data
    GET  /api/v1/infrastructure/costs      — Cost tracking & analysis
    GET  /api/v1/infrastructure/inference  — Inference performance metrics
    POST /api/v1/infrastructure/ab-test    — Start/manage A/B tests
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.models.user import User

from app.services.federated_learning_v2 import (
    AnonymizedUpdate,
    DataCategory,
    FederatedLearningV2Service,
)
from app.services.model_registry import ModelRegistry
from app.services.infrastructure.health_monitor import HealthMonitor

# Singleton instances
_fl_v2 = FederatedLearningV2Service()
_registry = ModelRegistry()
_monitor = HealthMonitor()

router = APIRouter(tags=["Infrastructure V2"])


# ════════════════════════════════════════════════════════════════════
# Request/Response Models
# ════════════════════════════════════════════════════════════════════


class FederatedUpdateRequest(BaseModel):
    """Request body for submitting federated learning updates."""
    device_id_hash: str = Field(..., min_length=8, description="SHA-256 hash of device ID")
    category: str = Field(
        ...,
        description="Data category: transaction_patterns, vocabulary, behavior, pricing, inventory, demand",
    )
    dialect: str = Field(default="sw", description="Language/dialect code")
    gradient_deltas: Optional[str] = Field(None, description="Base64-encoded gradient deltas (encrypted)")
    pattern_count: int = Field(default=0, ge=0, le=10000, description="Number of correction patterns")
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Average confidence score")
    feature_vector: Optional[List[float]] = Field(None, description="Anonymized feature vector")
    transaction_summary: Optional[dict] = Field(None, description="Anonymized transaction pattern summary")
    phoneme_corrections: Optional[List[dict]] = Field(None, description="Vocabulary correction patterns")
    session_duration_avg_s: Optional[float] = Field(None, description="Average session duration in seconds")
    feature_usage_counts: Optional[dict] = Field(None, description="Feature usage frequency counts")
    device_tier: str = Field(default="basic", description="Device capability tier")
    timestamp_ms: int = Field(default=0, description="Device-side timestamp in milliseconds")


class ModelRegisterRequest(BaseModel):
    """Request body for registering a model version."""
    model_name: str = Field(..., description="Model name (e.g. 'qwen-0.5b-fl-sw')")
    version: str = Field(..., description="Semantic version (e.g. 'v3.2.1')")
    base_model: str = Field(..., description="Base model (e.g. 'qwen-0.5b')")
    dialect: str = Field(default="sw", description="Target dialect")
    description: str = Field(default="", description="Model description")
    changelog: str = Field(default="", description="What changed from previous version")
    training_data_points: int = Field(default=0, description="Number of training data points")
    federated_rounds: int = Field(default=0, description="Number of FL rounds")


class ModelDeployRequest(BaseModel):
    """Request body for deploying a model version."""
    model_name: str
    version: str
    traffic_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    target_business_types: Optional[List[str]] = None
    target_regions: Optional[List[str]] = None


class ABTestRequest(BaseModel):
    """Request body for starting an A/B test."""
    model_name: str
    champion_version: str
    challenger_version: str
    traffic_split: float = Field(default=50.0, ge=0.0, le=100.0)
    description: str = ""


class MetricRecordRequest(BaseModel):
    """Request body for recording server metrics."""
    server_id: str
    cpu_usage_pct: float = Field(ge=0.0, le=100.0)
    ram_usage_pct: float = Field(ge=0.0, le=100.0)
    disk_usage_pct: float = Field(ge=0.0, le=100.0)
    network_in_mbps: float = Field(default=0.0, ge=0.0)
    network_out_mbps: float = Field(default=0.0, ge=0.0)
    inference_latency_ms: Optional[float] = None
    inference_count: int = Field(default=0, ge=0)


class InferenceRecordRequest(BaseModel):
    """Request body for recording an inference event."""
    model_name: str
    latency_ms: float = Field(ge=0.0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    success: bool = True


class CostRecordRequest(BaseModel):
    """Request body for recording a cost entry."""
    component: str = Field(description="server, inference, storage, network, training, other")
    amount_usd: float = Field(ge=0.0)
    phase: str = Field(default="cloud")
    model_name: Optional[str] = None
    inference_count: Optional[int] = None
    workers_served: Optional[int] = None
    period_hours: float = Field(default=1.0, gt=0.0)
    notes: str = ""


# ════════════════════════════════════════════════════════════════════
# Health Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/infrastructure/health")
async def get_infrastructure_health():
    """
    Get overall infrastructure health.

    Returns cluster health including:
    - Server status (CPU, RAM, disk, network)
    - Inference latency per model
    - Cost summary
    - Active alerts
    """
    return _monitor.get_cluster_health()


@router.get("/infrastructure/health/servers")
async def get_server_health(server_id: Optional[str] = Query(None)):
    """
    Get health status for specific server or all servers.
    """
    return _monitor.get_server_health(server_id)


@router.post("/infrastructure/health/metrics")
async def record_server_metric(
    req: MetricRecordRequest,
    user: User = Depends(get_current_user),
):
    """
    Record a server health metric snapshot.

    Used by monitoring agents running on each server.
    """
    return _monitor.record_metric(
        server_id=req.server_id,
        cpu_usage_pct=req.cpu_usage_pct,
        ram_usage_pct=req.ram_usage_pct,
        disk_usage_pct=req.disk_usage_pct,
        network_in_mbps=req.network_in_mbps,
        network_out_mbps=req.network_out_mbps,
        inference_latency_ms=req.inference_latency_ms,
        inference_count=req.inference_count,
    )


@router.get("/infrastructure/inference")
async def get_inference_metrics(model_name: Optional[str] = Query(None)):
    """
    Get inference latency and cost metrics per model.

    Returns P50/P95/P99 latency, total inferences, error rate,
    and cost per inference.
    """
    return _monitor.get_inference_metrics(model_name)


@router.post("/infrastructure/inference")
async def record_inference(
    req: InferenceRecordRequest,
    user: User = Depends(get_current_user),
):
    """
    Record an inference event for latency and cost tracking.
    """
    return _monitor.record_inference(
        model_name=req.model_name,
        latency_ms=req.latency_ms,
        cost_usd=req.cost_usd,
        success=req.success,
    )


# ════════════════════════════════════════════════════════════════════
# Model Registry Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/infrastructure/models")
async def list_models(
    model_name: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    dialect: Optional[str] = Query(None),
):
    """
    List registered model versions.

    Supports filtering by model name, status, and dialect.
    Returns version details, performance metrics, and A/B test info.
    """
    models = _registry.list_models(
        model_name=model_name,
        status=status_filter,
        dialect=dialect,
    )
    summary = _registry.get_registry_summary()
    return {
        "models": models,
        "summary": summary,
        "total": len(models),
    }


@router.get("/infrastructure/models/{model_name}/champion")
async def get_champion(model_name: str):
    """Get the current champion (production) model for a given model name."""
    champion = _registry.get_champion(model_name)
    if not champion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No champion model found for '{model_name}'",
        )
    return champion


@router.get("/infrastructure/models/{model_name}/performance")
async def get_model_performance(
    model_name: str,
    version: Optional[str] = Query(None),
):
    """Get performance metrics for a model, optionally by version."""
    return _registry.get_model_performance(model_name, version)


@router.post("/infrastructure/models")
async def register_model(
    req: ModelRegisterRequest,
    user: User = Depends(get_current_user),
):
    """
    Register a new model version.

    The model enters 'training' status. Use deploy to move to production.
    """
    result = _registry.register_model(
        model_name=req.model_name,
        version=req.version,
        base_model=req.base_model,
        dialect=req.dialect,
        description=req.description,
        changelog=req.changelog,
        training_data_points=req.training_data_points,
        federated_rounds=req.federated_rounds,
    )
    return result


@router.post("/infrastructure/models/deploy")
async def deploy_model(
    req: ModelDeployRequest,
    user: User = Depends(get_current_user),
):
    """
    Deploy a model version to receive traffic.

    Use traffic_pct < 100 for canary/A-B test deployments.
    """
    result = _registry.deploy(
        model_name=req.model_name,
        version=req.version,
        traffic_pct=req.traffic_pct,
        target_business_types=req.target_business_types,
        target_regions=req.target_regions,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    return result


@router.post("/infrastructure/models/{model_name}/rollback")
async def rollback_model(
    model_name: str,
    user: User = Depends(get_current_user),
):
    """
    Rollback a model to the previous active version.
    """
    result = _registry.rollback(model_name)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    return result


@router.post("/infrastructure/models/{model_name}/promote/{version}")
async def promote_model(
    model_name: str,
    version: str,
    user: User = Depends(get_current_user),
):
    """
    Promote a model version to champion (100% traffic).
    """
    result = _registry.promote(model_name, version)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    return result


@router.get("/infrastructure/ab-tests")
async def list_ab_tests(model_name: Optional[str] = Query(None)):
    """List A/B tests, optionally filtered by model name."""
    return {
        "tests": _registry.get_ab_tests(model_name),
    }


@router.post("/infrastructure/ab-test")
async def start_ab_test(
    req: ABTestRequest,
    user: User = Depends(get_current_user),
):
    """
    Start an A/B test between two model versions.
    """
    result = _registry.start_ab_test(
        model_name=req.model_name,
        champion_version=req.champion_version,
        challenger_version=req.challenger_version,
        traffic_split=req.traffic_split,
        description=req.description,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    return result


@router.post("/infrastructure/ab-test/{test_id}/end")
async def end_ab_test(
    test_id: str,
    winner: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    """End an A/B test. Optionally specify the winner version."""
    return _registry.end_ab_test(test_id, winner=winner)


# ════════════════════════════════════════════════════════════════════
# Federated Learning V2 Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post("/infrastructure/federated")
async def submit_federated_update(
    req: FederatedUpdateRequest,
    user: User = Depends(get_current_user),
):
    """
    Submit anonymized training data via federated learning.

    Privacy guarantees:
    - Raw data NEVER leaves the device
    - K-anonymity (k≥5): aggregation only when ≥5 devices in cohort
    - Differential privacy (ε=0.1): noise added to all aggregated outputs
    - Device IDs are one-way hashed — server cannot identify users

    Supported data categories:
    - transaction_patterns: anonymized transaction flow statistics
    - vocabulary: speech recognition correction patterns
    - behavior: app usage patterns (session duration, feature usage)
    - pricing: anonymized price point data
    - inventory: stock level patterns
    - demand: demand signal patterns
    """
    # Validate category
    try:
        category = DataCategory(req.category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category: {req.category}. Valid: {[c.value for c in DataCategory]}",
        )

    update = AnonymizedUpdate(
        device_id_hash=req.device_id_hash,
        category=category,
        dialect=req.dialect,
        gradient_deltas=req.gradient_deltas,
        pattern_count=req.pattern_count,
        avg_confidence=req.avg_confidence,
        feature_vector=req.feature_vector,
        transaction_summary=req.transaction_summary,
        phoneme_corrections=req.phoneme_corrections,
        session_duration_avg_s=req.session_duration_avg_s,
        feature_usage_counts=req.feature_usage_counts,
        device_tier=req.device_tier,
        timestamp_ms=req.timestamp_ms,
    )

    result = _fl_v2.submit_update(update)

    if result["status"] == "rejected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Update rejected: {result.get('reason', 'unknown')}",
        )

    return result


@router.get("/infrastructure/federated/status")
async def federated_status():
    """
    Get federated learning v2 system status.

    Returns:
    - Total updates received and aggregated
    - Cohort sizes and k-anonymity status
    - Privacy parameters (ε, δ, k)
    - Per-category breakdown
    """
    return _fl_v2.get_status()


@router.get("/infrastructure/federated/models")
async def list_federated_models(dialect: Optional[str] = Query(None)):
    """
    List aggregated federated learning models.
    """
    return {
        "models": _fl_v2.list_models(dialect),
    }


@router.get("/infrastructure/federated/model/{category}/{dialect}")
async def get_federated_model(
    category: str,
    dialect: str,
    version: Optional[str] = Query(None),
):
    """
    Get an aggregated model for a specific category and dialect.
    """
    model = _fl_v2.get_model(category, dialect, version)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No model found for category='{category}', dialect='{dialect}'",
        )
    return {
        "category": model.category.value,
        "dialect": model.dialect,
        "version": model.version,
        "avg_confidence": model.avg_confidence,
        "vocabulary_updates": model.vocabulary_updates[:50],  # Top 50
        "transaction_patterns": model.transaction_patterns,
        "behavioral_insights": model.behavioral_insights,
        "privacy": {
            "dp_epsilon": model.dp_epsilon,
            "dp_noise_applied": model.dp_noise_applied,
            "k_anonymity_k": model.k_anonymity_k,
        },
        "updates_included": model.updates_included,
        "timestamp_ms": model.timestamp_ms,
    }


# ════════════════════════════════════════════════════════════════════
# Cost Tracking Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/infrastructure/costs")
async def get_costs(
    component: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
):
    """
    Get infrastructure cost tracking data.

    Returns:
    - Total costs and breakdown by component/phase
    - Inference cost per model
    - Cost per worker
    - Historical cost trends
    """
    return _monitor.get_cost_summary(component=component, phase=phase)


@router.post("/infrastructure/costs")
async def record_cost(
    req: CostRecordRequest,
    user: User = Depends(get_current_user),
):
    """
    Record an infrastructure cost entry.
    """
    return _monitor.record_cost(
        component=req.component,
        amount_usd=req.amount_usd,
        phase=req.phase,
        model_name=req.model_name,
        inference_count=req.inference_count,
        workers_served=req.workers_served,
        period_hours=req.period_hours,
        notes=req.notes,
    )


@router.get("/infrastructure/alerts")
async def get_alerts(unresolved_only: bool = Query(True)):
    """
    Get infrastructure alerts.
    """
    return {
        "alerts": _monitor.get_alerts(unresolved_only=unresolved_only),
    }
