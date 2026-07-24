"""Superagent endpoint — unified intelligence brain."""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException

from app.models.schemas import SuperagentRequest, SuperagentResponse

router = APIRouter()

# Map of capability names to their module paths
CAPABILITY_MAP = {
    "market_research": "app.superagent.capabilities.market_research",
    "credit_scoring": "app.superagent.capabilities.credit_scoring",
    "distribution_analysis": "app.superagent.capabilities.distribution_analysis",
    "fmcg_intelligence": "app.superagent.capabilities.fmcg_intelligence",
    "health_metrics": "app.superagent.capabilities.health_metrics",
    "economic_analysis": "app.superagent.capabilities.economic_analysis",
    "soko_pulse": "app.intelligence.soko_pulse",
    "alama_score": "app.intelligence.alama_score",
    "angavu_pulse": "app.intelligence.angavu_pulse",
    "distribution_intel": "app.intelligence.distribution_intel",
    "fmcg_intel": "app.intelligence.fmcg_intel",
    "market_heat_maps": "app.intelligence.market_heat_maps",
    "price_index": "app.intelligence.price_index",
    "trade_routes": "app.intelligence.trade_routes",
    "vendor_score": "app.intelligence.vendor_score",
    "consumer_pulse": "app.intelligence.consumer_pulse",
    "inventory_optimizer": "app.intelligence.inventory_optimizer",
    "cash_flow_predictor": "app.intelligence.cash_flow_predictor",
    "risk_radar": "app.intelligence.risk_radar",
    "growth_atlas": "app.intelligence.growth_atlas",
    "sector_benchmark": "app.intelligence.sector_benchmark",
}


@router.post("/invoke", response_model=SuperagentResponse)
async def invoke_superagent(req: SuperagentRequest):
    """Invoke the superagent orchestrator with a capability request."""
    if req.capability not in CAPABILITY_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown capability: {req.capability}. Available: {list(CAPABILITY_MAP.keys())}",
        )

    start = time.time()

    from app.superagent.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    result = await orchestrator.execute_capability(
        capability=req.capability,
        query=req.query,
        context=req.context,
        priority=req.priority,
    )

    elapsed_ms = (time.time() - start) * 1000

    return SuperagentResponse(
        request_id=uuid.uuid4(),
        capability=req.capability,
        result=result.get("result", {}),
        confidence=result.get("confidence", 0.0),
        processing_time_ms=round(elapsed_ms, 2),
        model_used=result.get("model_used", "unknown"),
        guardrails_applied=result.get("guardrails_applied", []),
    )


@router.get("/capabilities")
async def list_capabilities():
    """List all available superagent capabilities."""
    from app.superagent.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    return {
        "capabilities": orchestrator.list_capabilities(),
        "total": len(CAPABILITY_MAP),
    }


@router.get("/status")
async def superagent_status():
    """Get current superagent status and metrics."""
    from app.superagent.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    return orchestrator.get_status()
