"""
Agent Loops API — Endpoints for agentic loop pattern introspection.

Exposes the internal state of loop patterns for debugging,
monitoring, and observability:

    GET  /api/v1/loops/traces          — ReAct reasoning traces
    GET  /api/v1/loops/critiques       — Reflexion self-critiques
    GET  /api/v1/loops/plans           — Plan-and-Execute execution plans
    GET  /api/v1/loops/events          — Event store query
    GET  /api/v1/loops/events/replay   — Replay events from a sequence
    GET  /api/v1/loops/supervision     — Supervisor stats and execution history
    GET  /api/v1/loops/agents          — All agent metrics
    POST /api/v1/loops/supervise       — Manually trigger supervised execution
"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.agents.loops import EventStore

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/loops", tags=["Agent Loops"])

# Global references — set during app startup
_supervisor = None
_event_store: Optional[EventStore] = None
_agents = {}


def set_loop_infrastructure(supervisor, event_store, agents):
    """Set the loop infrastructure (called during app startup)."""
    global _supervisor, _event_store, _agents
    _supervisor = supervisor
    _event_store = event_store
    _agents = {a.name: a for a in agents}


# ── ReAct Traces ────────────────────────────────────────────────────


@router.get("/traces")
async def get_react_traces(
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get ReAct reasoning traces.

    Shows the explicit reasoning chain for each agent execution:
    what it thought, what action it took, what it observed, and
    what it reflected on.
    """
    traces = []
    target_agents = [_agents[agent_name]] if agent_name and agent_name in _agents else _agents.values()

    for agent in target_agents:
        if hasattr(agent, "get_recent_traces"):
            agent_traces = agent.get_recent_traces(limit)
            traces.extend(agent_traces)

    return {
        "traces": traces[-limit:],
        "total": len(traces),
    }


@router.get("/traces/examples")
async def get_reasoning_examples(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
):
    """
    Get successful reasoning chains for few-shot learning.

    Returns traces where the final result was successful,
    which can be used as examples for the agent's context.
    """
    examples = []
    target_agents = [_agents[agent_name]] if agent_name and agent_name in _agents else _agents.values()

    for agent in target_agents:
        if hasattr(agent, "get_reasoning_examples"):
            agent_examples = agent.get_reasoning_examples(limit)
            examples.extend(agent_examples)

    return {
        "examples": examples[-limit:],
        "total": len(examples),
    }


# ── Reflexion Critiques ─────────────────────────────────────────────


@router.get("/critiques")
async def get_critiques(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get Reflexion self-critiques.

    Shows how the agent evaluated its own output quality,
    what issues it found, and what suggestions it made for improvement.
    """
    critiques = []
    target_agents = [_agents[agent_name]] if agent_name and agent_name in _agents else _agents.values()

    for agent in target_agents:
        if hasattr(agent, "get_critique_history"):
            agent_critiques = agent.get_critique_history(limit)
            critiques.extend(agent_critiques)

    return {
        "critiques": critiques[-limit:],
        "total": len(critiques),
    }


# ── Plan-and-Execute ────────────────────────────────────────────────


@router.get("/plans")
async def get_plans(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get Plan-and-Execute execution plans.

    Shows multi-step plans with their current progress,
    step statuses, and any re-planning history.
    """
    plans = []
    target_agents = [_agents[agent_name]] if agent_name and agent_name in _agents else _agents.values()

    for agent in target_agents:
        if hasattr(agent, "get_plan_history"):
            agent_plans = agent.get_plan_history(limit)
            plans.extend(agent_plans)

    return {
        "plans": plans[-limit:],
        "total": len(plans),
    }


# ── Event Store ─────────────────────────────────────────────────────


@router.get("/events")
async def get_events(
    event_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    aggregate_id: Optional[str] = Query(None),
    since_sequence: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Query the event store.

    All filters are AND-combined. Returns stored events with
    full audit metadata including sequence numbers and timestamps.
    """
    if not _event_store:
        raise HTTPException(status_code=503, detail="Event store not configured")

    events = _event_store.get_events(
        event_type=event_type,
        source=source,
        aggregate_id=aggregate_id,
        since_sequence=since_sequence,
        limit=limit,
    )

    return {
        "events": [e.to_dict() for e in events],
        "total": len(events),
        "stats": _event_store.get_stats(),
    }


@router.get("/events/replay")
async def replay_events(
    from_sequence: int = Query(0, ge=0),
    to_sequence: Optional[int] = Query(None, ge=0),
):
    """
    Replay events from a sequence range.

    Useful for:
    - Rebuilding projections/read models
    - Debugging by replaying the exact event sequence
    - Testing by replaying production events
    """
    if not _event_store:
        raise HTTPException(status_code=503, detail="Event store not configured")

    events = _event_store.replay(
        from_sequence=from_sequence,
        to_sequence=to_sequence,
    )

    return {
        "events": [e.to_dict() for e in events],
        "total": len(events),
        "from_sequence": from_sequence,
        "to_sequence": to_sequence,
    }


@router.get("/events/correlated/{correlation_id}")
async def get_correlated_events(correlation_id: str):
    """
    Get all events sharing a correlation ID.

    Traces the full lifecycle of a request across multiple agents.
    """
    if not _event_store:
        raise HTTPException(status_code=503, detail="Event store not configured")

    events = _event_store.get_correlated_events(correlation_id)

    return {
        "events": [e.to_dict() for e in events],
        "total": len(events),
        "correlation_id": correlation_id,
    }


@router.get("/events/stats")
async def get_event_stats():
    """Get event store statistics."""
    if not _event_store:
        raise HTTPException(status_code=503, detail="Event store not configured")

    return _event_store.get_stats()


# ── Supervisor ──────────────────────────────────────────────────────


@router.get("/supervision")
async def get_supervision_stats():
    """
    Get supervisor statistics.

    Shows:
    - Overall success rate
    - Per-agent performance metrics
    - Fallback and retry counts
    - Recent supervised executions
    """
    if not _supervisor:
        raise HTTPException(status_code=503, detail="Supervisor not configured")

    return _supervisor.get_supervision_stats()


@router.get("/supervision/history")
async def get_supervision_history(
    limit: int = Query(20, ge=1, le=100),
):
    """Get recent supervised executions with supervision decisions."""
    if not _supervisor:
        raise HTTPException(status_code=503, detail="Supervisor not configured")

    return {
        "executions": _supervisor.get_execution_history(limit),
    }


@router.get("/supervision/agents")
async def get_agent_metrics():
    """Get performance metrics for all managed agents."""
    if not _supervisor:
        raise HTTPException(status_code=503, detail="Supervisor not configured")

    return _supervisor.get_agent_metrics()


# ── Combined View ───────────────────────────────────────────────────


@router.get("/health")
async def loop_health():
    """
    Health check for all loop patterns.

    Returns the status of each loop pattern and overall system health.
    """
    health = {
        "react_traces": 0,
        "reflexion_critiques": 0,
        "plan_executions": 0,
        "event_store_events": 0,
        "supervision_executions": 0,
        "agents": {},
    }

    for name, agent in _agents.items():
        agent_health = {"name": name, "patterns": []}

        if hasattr(agent, "get_recent_traces"):
            traces = agent.get_recent_traces(1)
            health["react_traces"] += len(traces)
            agent_health["patterns"].append("react")

        if hasattr(agent, "get_critique_history"):
            critiques = agent.get_critique_history(1)
            health["reflexion_critiques"] += len(critiques)
            agent_health["patterns"].append("reflexion")

        if hasattr(agent, "get_plan_history"):
            plans = agent.get_plan_history(1)
            health["plan_executions"] += len(plans)
            agent_health["patterns"].append("plan_execute")

        if hasattr(agent, "get_audit_trail"):
            agent_health["patterns"].append("event_sourced")

        health["agents"][name] = agent_health

    if _event_store:
        health["event_store_events"] = _event_store.get_stats().get("total_events", 0)

    if _supervisor:
        stats = _supervisor.get_supervision_stats()
        health["supervision_executions"] = stats.get("total_executions", 0)

    return health
