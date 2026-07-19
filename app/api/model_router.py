"""
Model Router API — OmniRoute-inspired inference gateway endpoints.

Endpoints:
    POST /inference             — Route inference request to optimal provider
    GET  /inference/providers   — List available providers
    GET  /inference/health      — Provider health status
    GET  /inference/stats       — Usage and cost statistics
    GET  /inference/failures    — Recent failure history
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.model_router import get_model_router

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/inference", tags=["Model Router"])


# ── Request / Response Models ──────────────────────────────────────


class Message(BaseModel):
    role: str = Field(..., description="Message role: system, user, assistant")
    content: str = Field(..., description="Message content")


class InferenceRequest(BaseModel):
    messages: list[Message] = Field(..., description="Conversation messages")
    model: str | None = Field(None, description="Preferred model name")
    max_tokens: int = Field(1024, ge=1, le=32768, description="Max output tokens")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    task_complexity: str = Field("medium", description="Task complexity: low, medium, high")
    preferred_providers: list[str] | None = Field(None, description="Ordered list of preferred provider IDs")
    enable_compression: bool | None = Field(None, description="Override compression setting")
    user_id: str | None = Field(None, description="User ID for tracking")


class InferenceResponse(BaseModel):
    request_id: str
    provider_id: str
    model_used: str
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    fallback_count: int
    compression_info: dict
    cost_estimate: float


class ProviderInfo(BaseModel):
    provider_id: str
    type: str
    display_name: str
    status: str
    models: list[str]
    capabilities: list[str]
    cost_per_1k_input: float
    cost_per_1k_output: float
    max_context_tokens: int
    priority: int
    active_requests: int
    total_requests: int
    total_failures: int
    consecutive_failures: int
    error_rate: float
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    is_available: bool
    registered_at: str
    last_success_at: str | None
    last_failure_at: str | None


class HealthResponse(BaseModel):
    total_providers: int
    healthy: int
    degraded: int
    unhealthy: int
    offline: int
    available: int
    providers: list[ProviderInfo]


class StatsResponse(BaseModel):
    total_requests: int
    total_tokens_input: int
    total_tokens_output: int
    total_cost_estimate: float
    requests_by_provider: dict
    requests_by_model: dict
    compression_stats: dict
    fallback_stats: dict
    provider_health: dict


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("", response_model=InferenceResponse, summary="Route inference request")
async def route_inference(req: InferenceRequest):
    """
    Route an inference request to the optimal provider.

    Automatically handles:
    - Provider selection based on task complexity and cost
    - Token compression for long prompts
    - Fallback to alternative providers on failure
    """
    router_instance = get_model_router()

    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        response = await router_instance.infer(
            messages=messages,
            model=req.model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            task_complexity=req.task_complexity,
            preferred_providers=req.preferred_providers,
            enable_compression=req.enable_compression,
            user_id=req.user_id,
        )
        return InferenceResponse(
            request_id=response.request_id,
            provider_id=response.provider_id,
            model_used=response.model_used,
            content=response.content,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=round(response.latency_ms, 2),
            fallback_count=response.fallback_count,
            compression_info=response.compression_info,
            cost_estimate=round(response.cost_estimate, 6),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("inference_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Inference failed: {e!s}")


@router.get("/providers", response_model=list[ProviderInfo], summary="List providers")
async def list_providers(
    provider_type: str | None = Query(None, description="Filter by type: on_device, cloud_api, self_hosted, edge"),
    available_only: bool = Query(False, description="Only show available providers"),
):
    """List all registered AI inference providers with their status and metrics."""
    router_instance = get_model_router()
    providers = router_instance.list_providers()

    if provider_type:
        providers = [p for p in providers if p["type"] == provider_type]
    if available_only:
        providers = [p for p in providers if p["is_available"]]

    return [ProviderInfo(**p) for p in providers]


@router.get("/health", response_model=HealthResponse, summary="Provider health")
async def get_provider_health():
    """Get health status of all inference providers."""
    router_instance = get_model_router()
    health = router_instance.get_provider_health()
    return HealthResponse(**health)


@router.get("/stats", response_model=StatsResponse, summary="Usage statistics")
async def get_usage_stats():
    """Get comprehensive usage, cost, and performance statistics."""
    router_instance = get_model_router()
    stats = router_instance.get_stats()
    return StatsResponse(**stats)


@router.get("/failures", summary="Failure history")
async def get_failure_history(
    provider_id: str | None = Query(None, description="Filter by provider"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get recent inference failure history for debugging."""
    router_instance = get_model_router()
    return router_instance.fallback.get_failure_history(
        provider_id=provider_id,
        limit=limit,
    )


@router.get("/recent", summary="Recent requests")
async def get_recent_requests(limit: int = Query(20, ge=1, le=100)):
    """Get recent inference requests for monitoring."""
    router_instance = get_model_router()
    return router_instance.get_recent_requests(limit=limit)
