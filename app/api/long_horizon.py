"""
Long-Horizon Research API — Endpoints for long-running research tasks.

Endpoints:
    POST /api/v1/research/start           — start a long-horizon research task
    GET  /api/v1/research/{id}/status     — check progress
    GET  /api/v1/research/{id}/results    — get results
    GET  /api/v1/research/                — list all research tasks
    POST /api/v1/research/{id}/cancel     — cancel a running task
    GET  /api/v1/research/health          — orchestrator health check

Supports 4 intelligence pipeline types:
    - market_analysis
    - credit_scoring
    - distribution_analysis
    - competitor_analysis

Plus a generic research flow for custom research tasks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.long_horizon import LongHorizonOrchestrator, TaskStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/research", tags=["Long-Horizon Research"])

# Global references — set during app startup
_orchestrators: Dict[str, LongHorizonOrchestrator] = {}
_research_orchestrator: Optional[LongHorizonOrchestrator] = None


def set_long_horizon_infrastructure(
    intelligence_flows: Dict[str, LongHorizonOrchestrator],
    research_orchestrator: LongHorizonOrchestrator,
) -> None:
    """Set the long-horizon infrastructure (called during app startup)."""
    global _orchestrators, _research_orchestrator
    _orchestrators = intelligence_flows
    _research_orchestrator = research_orchestrator


# ════════════════════════════════════════════════════════════════════
# Request / Response Models
# ════════════════════════════════════════════════════════════════════


class ResearchStartRequest(BaseModel):
    """Request to start a long-horizon research task."""
    goal: str = Field(..., description="The research goal or question")
    pipeline_type: str = Field(
        default="generic",
        description=(
            "Pipeline type: market_analysis, credit_scoring, "
            "distribution_analysis, competitor_analysis, or generic"
        ),
    )
    scope: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Research scope parameters: region, product_category, "
            "time_horizon, depth (quick/standard/deep), sources, worker_id"
        ),
    )
    timeout_seconds: float = Field(
        default=3600.0,
        ge=60.0,
        le=14400.0,
        description="Task timeout in seconds (1 min to 4 hours)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for the task",
    )


class ResearchStartResponse(BaseModel):
    """Response after starting a research task."""
    task_id: str
    goal: str
    pipeline_type: str
    status: str
    message: str


class SubTaskStatusResponse(BaseModel):
    """Status of a single sub-task."""
    subtask_id: str
    name: str
    status: str
    assigned_agent: Optional[str] = None
    attempts: int = 0
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None


class ResearchStatusResponse(BaseModel):
    """Response for task status check."""
    task_id: str
    goal: str
    status: str
    progress_pct: float
    subtask_count: int
    subtasks_completed: int
    subtasks_running: int
    subtasks_failed: int
    subtasks_pending: int
    elapsed_seconds: Optional[float] = None
    checkpoint_count: int
    error: Optional[str] = None


class ResearchResultsResponse(BaseModel):
    """Response containing research results."""
    task_id: str
    goal: str
    status: str
    progress_pct: float
    aggregated_result: Optional[Dict[str, Any]] = None
    subtasks: List[SubTaskStatusResponse] = []
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None


# ════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════


@router.post("/start", response_model=ResearchStartResponse)
async def start_research(request: ResearchStartRequest):
    """
    Start a long-horizon research task.

    The task runs asynchronously. Use GET /research/{id}/status
    to poll for progress, or GET /research/{id}/results when complete.

    Pipeline types:
    - **market_analysis**: Price trends, supply/demand, trade volumes
    - **credit_scoring**: Transaction history, repayment, behavioral scoring
    - **distribution_analysis**: Coverage gaps, logistics, expansion planning
    - **competitor_analysis**: Competitor mapping, pricing, features, threats
    - **generic**: Custom research using the full research flow
    """
    import asyncio

    pipeline_type = request.pipeline_type

    # Select orchestrator
    if pipeline_type == "generic":
        orchestrator = _research_orchestrator
    elif pipeline_type in _orchestrators:
        orchestrator = _orchestrators[pipeline_type]
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown pipeline type: {pipeline_type}. "
                   f"Available: {list(_orchestrators.keys()) + ['generic']}",
        )

    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail=f"Pipeline '{pipeline_type}' not configured",
        )

    # Build context
    context = {
        "scope": request.scope,
        "goal": request.goal,
    }

    # Start task in background
    task = await orchestrator.execute(
        goal=request.goal,
        context=context,
        timeout_seconds=request.timeout_seconds,
        metadata=request.metadata,
    )

    logger.info(
        "research_started",
        task_id=task.task_id,
        pipeline_type=pipeline_type,
        goal=request.goal,
    )

    return ResearchStartResponse(
        task_id=task.task_id,
        goal=request.goal,
        pipeline_type=pipeline_type,
        status=task.status.value,
        message=f"Research task started. Poll GET /api/v1/research/{task.task_id}/status for progress.",
    )


@router.get("/{task_id}/status", response_model=ResearchStatusResponse)
async def get_research_status(task_id: str):
    """
    Check the progress of a long-horizon research task.

    Returns current status, progress percentage, and sub-task breakdown.
    """
    task = _find_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task.update_progress()

    completed = sum(1 for st in task.subtasks if st.status.value == "completed")
    running = sum(1 for st in task.subtasks if st.status.value == "running")
    failed = sum(1 for st in task.subtasks if st.status.value == "failed")
    pending = sum(1 for st in task.subtasks if st.status.value == "pending")

    return ResearchStatusResponse(
        task_id=task.task_id,
        goal=task.goal,
        status=task.status.value,
        progress_pct=task.progress_pct,
        subtask_count=len(task.subtasks),
        subtasks_completed=completed,
        subtasks_running=running,
        subtasks_failed=failed,
        subtasks_pending=pending,
        elapsed_seconds=(
            (task.completed_at or time.time()) - task.started_at
            if task.started_at else None
        ),
        checkpoint_count=len(task.checkpoints),
        error=task.error,
    )


@router.get("/{task_id}/results", response_model=ResearchResultsResponse)
async def get_research_results(task_id: str):
    """
    Get the results of a completed research task.

    Returns the aggregated result, individual sub-task outcomes,
    and any errors encountered during execution.

    Returns 404 if task not found, 409 if task is still running.
    """
    task = _find_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status in (TaskStatus.EXECUTING, TaskStatus.PLANNING, TaskStatus.AGGREGATING):
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} is still {task.status.value}. "
                   f"Progress: {task.progress_pct}%. Use /status endpoint to poll.",
        )

    subtasks = [
        SubTaskStatusResponse(
            subtask_id=st.subtask_id,
            name=st.name,
            status=st.status.value,
            assigned_agent=st.assigned_agent,
            attempts=st.attempts,
            error=st.error,
            elapsed_seconds=(
                (st.completed_at - st.started_at)
                if st.started_at and st.completed_at else None
            ),
        )
        for st in task.subtasks
    ]

    return ResearchResultsResponse(
        task_id=task.task_id,
        goal=task.goal,
        status=task.status.value,
        progress_pct=task.progress_pct,
        aggregated_result=task.aggregated_result,
        subtasks=subtasks,
        error=task.error,
        elapsed_seconds=(
            (task.completed_at or time.time()) - task.started_at
            if task.started_at else None
        ),
    )


@router.get("/")
async def list_research_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
):
    """List all research tasks, optionally filtered by status."""
    all_tasks = []

    # Collect from all orchestrators
    for name, orch in _orchestrators.items():
        tasks = orch.tracker.list_tasks(limit=limit)
        for t in tasks:
            task_dict = t.to_dict()
            task_dict["pipeline_type"] = name
            all_tasks.append(task_dict)

    if _research_orchestrator:
        tasks = _research_orchestrator.tracker.list_tasks(limit=limit)
        for t in tasks:
            task_dict = t.to_dict()
            task_dict["pipeline_type"] = "generic"
            all_tasks.append(task_dict)

    # Filter by status
    if status:
        all_tasks = [t for t in all_tasks if t.get("status") == status]

    # Sort by created_at descending
    all_tasks.sort(key=lambda t: t.get("created_at", 0), reverse=True)

    return {
        "tasks": all_tasks[:limit],
        "total": len(all_tasks),
    }


@router.post("/{task_id}/cancel")
async def cancel_research(task_id: str):
    """Cancel a running research task."""
    for name, orch in _orchestrators.items():
        if await orch.cancel_task(task_id):
            return {"task_id": task_id, "status": "cancelled", "pipeline": name}

    if _research_orchestrator:
        if await _research_orchestrator.cancel_task(task_id):
            return {"task_id": task_id, "status": "cancelled", "pipeline": "generic"}

    raise HTTPException(status_code=404, detail=f"Task {task_id} not found or not cancellable")


@router.get("/health")
async def research_health():
    """
    Health check for all long-horizon research orchestrators.

    Returns the status of each pipeline and overall system health.
    """
    health = {
        "status": "ok",
        "pipelines": {},
        "total_registered_agents": 0,
        "total_active_tasks": 0,
        "total_tasks": 0,
    }

    for name, orch in _orchestrators.items():
        orch_status = orch.get_status()
        health["pipelines"][name] = orch_status
        health["total_registered_agents"] += len(orch_status.get("registered_agents", []))
        health["total_active_tasks"] += orch_status.get("active_tasks", 0)
        health["total_tasks"] += orch_status.get("total_tasks", 0)

    if _research_orchestrator:
        orch_status = _research_orchestrator.get_status()
        health["pipelines"]["generic"] = orch_status
        health["total_registered_agents"] += len(orch_status.get("registered_agents", []))
        health["total_active_tasks"] += orch_status.get("active_tasks", 0)
        health["total_tasks"] += orch_status.get("total_tasks", 0)

    if health["total_active_tasks"] > 10:
        health["status"] = "degraded"

    return health


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def _find_task(task_id: str):
    """Find a task across all orchestrators."""
    import time as _time

    for orch in _orchestrators.values():
        task = orch.tracker.get_task(task_id)
        if task:
            return task

    if _research_orchestrator:
        task = _research_orchestrator.tracker.get_task(task_id)
        if task:
            return task

    return None
