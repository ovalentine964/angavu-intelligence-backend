"""
Harness API — Monitoring and control endpoints for the agent execution harness.

Endpoints:
    GET  /harness/health            — Overall harness health
    GET  /harness/agents            — Per-agent execution metrics
    GET  /harness/agents/{name}     — Single agent metrics
    GET  /harness/circuit-breakers  — Circuit breaker states
    POST /harness/circuit-breakers/{name}/reset — Reset a circuit breaker
    GET  /harness/costs             — Cost breakdown by agent
    GET  /harness/costs/{user_id}   — Cost breakdown by user
    GET  /harness/canary            — Canary routing weights
    POST /harness/canary            — Update canary weights
"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/harness", tags=["Agent Harness"])


def _get_harness():
    """Get the global execution harness instance."""
    from app.agents.harness import get_execution_harness
    return get_execution_harness()


# ── Request / Response Models ──────────────────────────────────────


class HarnessHealthResponse(BaseModel):
    status: str
    open_circuits: list
    half_open_circuits: list
    total_circuit_breakers: int
    total_executions: int
    config: dict


class CircuitBreakerResetRequest(BaseModel):
    agent_name: str = Field(..., description="Agent name whose circuit breaker to reset")


class CanaryWeightUpdateRequest(BaseModel):
    agent_name: str = Field(..., description="Agent name")
    version: str = Field(..., description="Version identifier")
    weight: float = Field(..., ge=0.0, description="New traffic weight (0.0-1.0)")


# ── Endpoints ──────────────────────────────────────────────────────


@router.get("/health", response_model=HarnessHealthResponse)
async def harness_health():
    """Get overall harness health status."""
    harness = _get_harness()
    return harness.get_health()


@router.get("/agents")
async def agent_metrics(hours: int = 24):
    """Get execution metrics for all agents."""
    harness = _get_harness()
    return harness.get_metrics(hours)


@router.get("/agents/{agent_name}")
async def single_agent_metrics(agent_name: str, hours: int = 24):
    """Get execution metrics for a specific agent."""
    harness = _get_harness()
    stats = harness.get_agent_metrics(agent_name, hours)
    if stats.get("calls", 0) == 0 and "agent_name" in stats:
        raise HTTPException(status_code=404, detail=f"No metrics found for agent: {agent_name}")
    return stats


@router.get("/circuit-breakers")
async def circuit_breaker_states():
    """Get state of all circuit breakers."""
    harness = _get_harness()
    return harness.get_circuit_breakers()


@router.post("/circuit-breakers/{agent_name}/reset")
async def reset_circuit_breaker(agent_name: str):
    """Manually reset a circuit breaker to closed state."""
    harness = _get_harness()
    success = harness.reset_circuit_breaker(agent_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"No circuit breaker found for agent: {agent_name}")
    return {"status": "reset", "agent_name": agent_name, "new_state": "closed"}


@router.get("/costs")
async def cost_breakdown(hours: int = 24):
    """Get cost breakdown by agent."""
    harness = _get_harness()
    return harness.get_metrics(hours)


@router.get("/costs/{user_id}")
async def user_cost_breakdown(user_id: str):
    """Get cost breakdown for a specific user."""
    harness = _get_harness()
    return harness.get_user_costs(user_id)


@router.get("/canary")
async def canary_weights(agent_name: Optional[str] = None):
    """Get canary routing weights."""
    # Canary router is a separate component — check if it exists
    try:
        from app.agents.harness import CanaryRouter
        # This would be injected in production
        return {"status": "canary_router_not_configured"}
    except ImportError:
        raise HTTPException(status_code=501, detail="Canary router not available")
