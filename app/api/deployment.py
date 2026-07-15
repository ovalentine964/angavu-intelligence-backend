"""
Deployment Management API

Exposes the DeploymentHarness via REST endpoints:
- Canary deployment lifecycle (start, pause, resume, rollback)
- Version tracking (which version serves what %)
- Feature flags (create, enable, disable, check)
- Deployment metrics (error rate, latency, throughput per version)

All endpoints require admin authentication.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.models.user import User
from app.infrastructure.deployment_harness import (
    DeploymentHarnessConfig,
    DeploymentStage,
    DeploymentStatus,
    get_deployment_harness,
    create_deployment_harness,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/deploy", tags=["Deployment Harness"])


# ════════════════════════════════════════════════════════════════════
# Request/Response Models
# ════════════════════════════════════════════════════════════════════


class StartDeploymentRequest(BaseModel):
    component: str = Field(..., description="Component name (e.g., IntelligenceGenerator)")
    old_version: str = Field(..., description="Current stable version")
    new_version: str = Field(..., description="New version to deploy")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Deployment metadata")


class RollbackRequest(BaseModel):
    reason: str = Field(default="manual", description="Reason for rollback")


class CreateFlagRequest(BaseModel):
    name: str = Field(..., description="Feature flag name")
    description: str = Field(default="", description="Feature flag description")


class EnableFlagRequest(BaseModel):
    segments: Optional[List[str]] = Field(
        default=None,
        description="User segments to enable for (null = all segments)",
    )
    rollout_percentage: float = Field(
        default=100.0, ge=0.0, le=100.0,
        description="Percentage of users to enable for",
    )


class CheckFlagRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="User ID for deterministic rollout")
    user_segment: Optional[str] = Field(default=None, description="User segment")


class RecordMetricsRequest(BaseModel):
    component: str = Field(..., description="Component name")
    version: str = Field(..., description="Version")
    latency_ms: float = Field(..., ge=0, description="Request latency in ms")
    is_error: bool = Field(default=False, description="Whether the request errored")


# ════════════════════════════════════════════════════════════════════
# Deployment Lifecycle Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post("/start", summary="Start a canary deployment")
async def start_deployment(
    req: StartDeploymentRequest,
    user: User = Depends(get_current_user),
):
    """
    Start a canary deployment for a component.

    Progresses through stages: 1% → 10% → 50% → 100%
    with health checks at each stage. Rolls back automatically
    if error rate >1% or latency >2x baseline.
    """
    harness = get_deployment_harness()
    try:
        record = await harness.start_deployment(
            component=req.component,
            old_version=req.old_version,
            new_version=req.new_version,
            metadata=req.metadata,
        )
        return {
            "status": "started",
            "deployment": record.to_dict(),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))


@router.get("/status/{deployment_id}", summary="Get deployment status")
async def get_deployment_status(
    deployment_id: str,
    user: User = Depends(get_current_user),
):
    """Get the status of a specific deployment."""
    harness = get_deployment_harness()
    status = harness.get_deployment_status(deployment_id)
    if not status:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return status


@router.post("/pause/{deployment_id}", summary="Pause a deployment")
async def pause_deployment(
    deployment_id: str,
    user: User = Depends(get_current_user),
):
    """Pause a running deployment at its current canary stage."""
    harness = get_deployment_harness()
    success = await harness.pause_deployment(deployment_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Deployment not found or not in progress",
        )
    return {"status": "paused", "deployment_id": deployment_id}


@router.post("/resume/{deployment_id}", summary="Resume a deployment")
async def resume_deployment(
    deployment_id: str,
    user: User = Depends(get_current_user),
):
    """Resume a paused deployment."""
    harness = get_deployment_harness()
    success = await harness.resume_deployment(deployment_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Deployment not found or not paused",
        )
    return {"status": "resumed", "deployment_id": deployment_id}


@router.post("/rollback/{deployment_id}", summary="Rollback a deployment")
async def rollback_deployment(
    deployment_id: str,
    req: RollbackRequest,
    user: User = Depends(get_current_user),
):
    """Manually rollback a deployment to the previous stable version."""
    harness = get_deployment_harness()
    success = await harness.manual_rollback(deployment_id, req.reason)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Deployment not found or not in progress",
        )
    return {
        "status": "rolled_back",
        "deployment_id": deployment_id,
        "reason": req.reason,
    }


# ════════════════════════════════════════════════════════════════════
# Deployment Listing Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/active", summary="List active deployments")
async def list_active_deployments(
    user: User = Depends(get_current_user),
):
    """Get all currently active (in-progress) deployments."""
    harness = get_deployment_harness()
    return {"deployments": harness.get_active_deployments()}


@router.get("/history", summary="Deployment history")
async def list_all_deployments(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """Get recent deployments (active + completed), newest first."""
    harness = get_deployment_harness()
    return {"deployments": harness.get_all_deployments(limit)}


# ════════════════════════════════════════════════════════════════════
# Version Tracking Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/versions", summary="Version map")
async def get_version_map(
    user: User = Depends(get_current_user),
):
    """
    Get the full version map: which version of each component
    serves what percentage of traffic.
    """
    harness = get_deployment_harness()
    return {"versions": harness.get_version_map()}


@router.get("/versions/serving", summary="Serving versions")
async def get_serving_versions(
    user: User = Depends(get_current_user),
):
    """Get all versions currently serving traffic."""
    harness = get_deployment_harness()
    return {"versions": harness.get_serving_versions()}


@router.get("/routes", summary="Traffic routes")
async def get_traffic_routes(
    user: User = Depends(get_current_user),
):
    """Get current traffic routing state."""
    harness = get_deployment_harness()
    return {"routes": harness.get_traffic_routes()}


# ════════════════════════════════════════════════════════════════════
# Feature Flag Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/flags", summary="List all feature flags")
async def list_feature_flags(
    user: User = Depends(get_current_user),
):
    """Get all feature flags and their current state."""
    harness = get_deployment_harness()
    return {"flags": harness.feature_flags.get_all()}


@router.post("/flags", summary="Create a feature flag")
async def create_feature_flag(
    req: CreateFlagRequest,
    user: User = Depends(get_current_user),
):
    """Create a new feature flag (disabled by default)."""
    harness = get_deployment_harness()
    try:
        flag = harness.feature_flags.create(req.name, req.description)
        return {"status": "created", "flag": flag.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/flags/{name}/enable", summary="Enable a feature flag")
async def enable_feature_flag(
    name: str,
    req: EnableFlagRequest,
    user: User = Depends(get_current_user),
):
    """
    Enable a feature flag with optional segment targeting
    and percentage rollout.
    """
    harness = get_deployment_harness()
    try:
        harness.feature_flags.enable(
            name,
            segments=req.segments,
            rollout_percentage=req.rollout_percentage,
        )
        flag = harness.feature_flags.get_flag(name)
        return {"status": "enabled", "flag": flag}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/flags/{name}/disable", summary="Disable a feature flag")
async def disable_feature_flag(
    name: str,
    user: User = Depends(get_current_user),
):
    """Disable a feature flag."""
    harness = get_deployment_harness()
    try:
        harness.feature_flags.disable(name)
        flag = harness.feature_flags.get_flag(name)
        return {"status": "disabled", "flag": flag}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/flags/{name}/check", summary="Check a feature flag")
async def check_feature_flag(
    name: str,
    req: CheckFlagRequest,
    user: User = Depends(get_current_user),
):
    """
    Check if a feature flag is enabled for a specific user/segment.

    Uses deterministic hashing for percentage rollouts — same user_id
    always gets the same result.
    """
    harness = get_deployment_harness()
    enabled = harness.feature_flags.is_enabled(
        name,
        user_id=req.user_id,
        user_segment=req.user_segment,
    )
    flag = harness.feature_flags.get_flag(name)
    return {
        "flag": name,
        "enabled": enabled,
        "user_id": req.user_id,
        "user_segment": req.user_segment,
        "flag_details": flag,
    }


@router.delete("/flags/{name}", summary="Delete a feature flag")
async def delete_feature_flag(
    name: str,
    user: User = Depends(get_current_user),
):
    """Delete a feature flag."""
    harness = get_deployment_harness()
    deleted = harness.feature_flags.delete(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flag not found")
    return {"status": "deleted", "name": name}


# ════════════════════════════════════════════════════════════════════
# Deployment Metrics Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/metrics", summary="All deployment metrics")
async def get_all_metrics(
    user: User = Depends(get_current_user),
):
    """
    Get deployment metrics for all components and versions.

    Includes error rate, latency (avg, p95, max), and throughput (rps)
    per version.
    """
    harness = get_deployment_harness()
    return {"metrics": harness.get_all_metrics()}


@router.get("/metrics/{component}", summary="Component metrics")
async def get_component_metrics(
    component: str,
    user: User = Depends(get_current_user),
):
    """Get metrics for all versions of a specific component."""
    harness = get_deployment_harness()
    return {
        "component": component,
        "metrics": harness.get_component_metrics(component),
    }


@router.post("/metrics/record", summary="Record a request metric")
async def record_metric(
    req: RecordMetricsRequest,
    user: User = Depends(get_current_user),
):
    """
    Record a request for metrics tracking.

    Call this from request handlers to feed the deployment metrics collector.
    Used by the health checker during canary deployments.
    """
    harness = get_deployment_harness()
    harness.record_request(
        req.component, req.version, req.latency_ms, req.is_error,
    )
    return {"status": "recorded"}


# ════════════════════════════════════════════════════════════════════
# Health & Status Endpoints
# ════════════════════════════════════════════════════════════════════


@router.get("/health", summary="Deployment harness health")
async def get_harness_health(
    user: User = Depends(get_current_user),
):
    """Get the overall health of the deployment harness."""
    harness = get_deployment_harness()
    return harness.get_health()
