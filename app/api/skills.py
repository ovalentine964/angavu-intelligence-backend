"""
Skills API — REST endpoints for skill management and execution.

Endpoints:
    GET  /api/v1/skills              — List all skills
    GET  /api/v1/skills/{name}       — Get skill details
    POST /api/v1/skills/{name}/execute — Execute a skill action
    GET  /api/v1/skills/{name}/metrics — Skill performance metrics
    GET  /api/v1/skills/summary      — Registry summary
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.skill_registry import get_skill_registry

router = APIRouter(prefix="/skills", tags=["Skills"])


# ── Request/Response Models ─────────────────────────────────────────


class SkillExecuteRequest(BaseModel):
    """Request body for skill execution."""
    action: str = Field(..., description="Skill action to execute")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class SkillExecuteResponse(BaseModel):
    """Response from skill execution."""
    success: bool
    skill_name: str
    data: Dict[str, Any] = {}
    error: Optional[str] = None
    duration_ms: float = 0.0
    confidence: float = 0.0


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("", summary="List all skills")
async def list_skills():
    """
    List all registered skills with their metadata.

    Returns skill name, course unit, description, version, status,
    agent bindings, and usage metrics.
    """
    registry = get_skill_registry()
    return {
        "skills": registry.list_all(),
        "total": len(registry.list_all()),
    }


@router.get("/summary", summary="Registry summary")
async def skill_summary():
    """
    Get registry summary statistics.

    Returns total skills, active skills, agent mappings,
    total executions, and success rates.
    """
    registry = get_skill_registry()
    return registry.get_summary()


@router.get("/{skill_name}", summary="Get skill details")
async def get_skill(skill_name: str):
    """
    Get detailed information about a specific skill.

    Includes metadata, agent bindings, and current metrics.
    """
    registry = get_skill_registry()
    skill = registry.get(skill_name)

    if not skill:
        raise HTTPException(
            status_code=404,
            detail=f"Skill not found: {skill_name}",
        )

    return skill.get_info()


@router.post("/{skill_name}/execute", summary="Execute a skill action")
async def execute_skill(skill_name: str, request: SkillExecuteRequest):
    """
    Execute a specific action on a skill.

    The request body must specify:
    - action: The skill action to run (e.g., 'predict_default_risk')
    - params: Parameters for the action

    Returns the skill result with data, confidence, and diagnostics.
    """
    registry = get_skill_registry()
    skill = registry.get(skill_name)

    if not skill:
        raise HTTPException(
            status_code=404,
            detail=f"Skill not found: {skill_name}",
        )

    result = await registry.execute_skill(
        skill_name=skill_name,
        action=request.action,
        **request.params,
    )

    return result.to_dict()


@router.get("/{skill_name}/metrics", summary="Skill performance metrics")
async def get_skill_metrics(skill_name: str):
    """
    Get performance metrics for a specific skill.

    Returns call counts, success rate, average duration,
    confidence tracking, and last execution details.
    """
    registry = get_skill_registry()
    metrics = registry.get_metrics(skill_name)

    if "error" in metrics:
        raise HTTPException(status_code=404, detail=metrics["error"])

    return {
        "skill_name": skill_name,
        "metrics": metrics,
    }
