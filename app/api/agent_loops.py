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

    OODA Loop:
    GET  /api/v1/loops/ooda/cycles     — OODA cycle history
    GET  /api/v1/loops/ooda/velocity   — Decision velocity metrics
    GET  /api/v1/loops/ooda/orientation — Current orientation state

    Feedback Loop:
    GET  /api/v1/loops/feedback/signals    — Learning signals summary
    GET  /api/v1/loops/feedback/patterns   — Detected patterns
    GET  /api/v1/loops/feedback/strategy   — Current strategy
    GET  /api/v1/loops/feedback/history    — Strategy version history

    Human-in-the-Loop:
    GET  /api/v1/loops/hitl/escalations    — Escalation history
    GET  /api/v1/loops/hitl/trust-scores   — Per-worker trust scores
    GET  /api/v1/loops/hitl/autonomy       — Autonomy level distribution
    GET  /api/v1/loops/hitl/pending        — Pending escalation requests
    POST /api/v1/loops/hitl/resolve        — Resolve an escalation
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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
_ooda_agents = {}  # name -> OODAAgent
_feedback_agents = {}  # name -> FeedbackAgent
_hitl_agents = {}  # name -> HumanInTheLoopAgent


def set_loop_infrastructure(supervisor, event_store, agents):
    """Set the loop infrastructure (called during app startup)."""
    global _supervisor, _event_store, _agents
    _supervisor = supervisor
    _event_store = event_store
    _agents = {a.name: a for a in agents}

    # Index new loop agents by type
    from app.agents.loops.ooda_loop import OODAAgent
    from app.agents.loops.feedback_loop import FeedbackAgent
    from app.agents.loops.human_in_the_loop import HumanInTheLoopAgent

    for a in agents:
        if isinstance(a, OODAAgent):
            _ooda_agents[a.name] = a
        if isinstance(a, FeedbackAgent):
            _feedback_agents[a.name] = a
        if isinstance(a, HumanInTheLoopAgent):
            _hitl_agents[a.name] = a


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


# ── OODA Loop ──────────────────────────────────────────────────────


@router.get("/ooda/cycles")
async def get_ooda_cycles(
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get OODA loop cycle history.

    Shows the observe-orient-decide-act cycles with timing
    data for each phase.
    """
    cycles = []
    targets = {agent_name: _ooda_agents[agent_name]} if agent_name and agent_name in _ooda_agents else _ooda_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_recent_cycles"):
            agent_cycles = agent.get_recent_cycles(limit)
            cycles.extend(agent_cycles)

    return {
        "cycles": cycles[-limit:],
        "total": len(cycles),
    }


@router.get("/ooda/velocity")
async def get_decision_velocity(
    agent_name: Optional[str] = Query(None),
):
    """
    Get decision velocity metrics.

    Decision velocity = how quickly the system converts
    observations to actions (in milliseconds).
    """
    velocities = {}
    targets = {agent_name: _ooda_agents[agent_name]} if agent_name and agent_name in _ooda_agents else _ooda_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_metrics"):
            metrics = agent.get_metrics()
            velocities[name] = metrics.get("decision_velocity", 0.0)

    return {"velocities": velocities}


@router.get("/ooda/orientation")
async def get_orientation_state(
    agent_name: Optional[str] = Query(None),
):
    """
    Get current OODA orientation state.

    The orientation state is the system's accumulated understanding
    of the current situation, built up over many observe-orient cycles.
    """
    orientations = {}
    targets = {agent_name: _ooda_agents[agent_name]} if agent_name and agent_name in _ooda_agents else _ooda_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_orientation"):
            orientations[name] = agent.get_orientation()

    return {"orientations": orientations}


@router.get("/ooda/stats")
async def get_ooda_stats(
    agent_name: Optional[str] = Query(None),
):
    """Get overall OODA loop statistics."""
    stats = {}
    targets = {agent_name: _ooda_agents[agent_name]} if agent_name and agent_name in _ooda_agents else _ooda_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_metrics"):
            stats[name] = agent.get_metrics()

    return {"ooda_stats": stats}


# ── Self-Improving Feedback Loop ────────────────────────────────────


@router.get("/feedback/signals")
async def get_feedback_signals(
    agent_name: Optional[str] = Query(None),
):
    """
    Get learning signals summary.

    Shows the signals extracted from transaction outcomes,
    including type distribution and effective strength.
    """
    signals = {}
    targets = {agent_name: _feedback_agents[agent_name]} if agent_name and agent_name in _feedback_agents else _feedback_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_signals_summary"):
            signals[name] = agent.get_signals_summary()
        elif hasattr(agent, "get_recent_signals"):
            signals[name] = agent.get_recent_signals(20)

    return {"signals": signals}


@router.get("/feedback/patterns")
async def get_feedback_patterns(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get detected patterns from the feedback loop.

    Shows patterns detected across accumulated signals,
    including recurring failures and success factors.
    """
    patterns = []
    targets = {agent_name: _feedback_agents[agent_name]} if agent_name and agent_name in _feedback_agents else _feedback_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_patterns"):
            agent_patterns = agent.get_patterns()
            patterns.extend(agent_patterns)

    return {
        "patterns": patterns[-limit:],
        "total": len(patterns),
    }


@router.get("/feedback/strategy")
async def get_current_strategy(
    agent_name: Optional[str] = Query(None),
):
    """
    Get current active strategy from the feedback loop.

    Shows the strategy parameters that are currently in effect,
    including which pattern triggered them.
    """
    strategies = {}
    targets = {agent_name: _feedback_agents[agent_name]} if agent_name and agent_name in _feedback_agents else _feedback_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_current_strategy"):
            strategies[name] = agent.get_current_strategy()
        elif hasattr(agent, "get_strategy_parameters"):
            strategies[name] = agent.get_strategy_parameters()

    return {"strategies": strategies}


@router.get("/feedback/history")
async def get_strategy_history(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    """Get strategy version history."""
    history = []
    targets = {agent_name: _feedback_agents[agent_name]} if agent_name and agent_name in _feedback_agents else _feedback_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_strategy_history"):
            agent_history = agent.get_strategy_history(limit)
            history.extend(agent_history)

    return {"history": history[-limit: ]}


@router.get("/feedback/stats")
async def get_feedback_stats(
    agent_name: Optional[str] = Query(None),
):
    """Get overall feedback loop statistics."""
    stats = {}
    targets = {agent_name: _feedback_agents[agent_name]} if agent_name and agent_name in _feedback_agents else _feedback_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_metrics"):
            stats[name] = agent.get_metrics()

    return {"feedback_stats": stats}


# ── Human-in-the-Loop ──────────────────────────────────────────────


class ResolveEscalationRequest(BaseModel):
    """Request to resolve a pending escalation."""
    escalation_id: str
    decision: str  # accepted | rejected | modified
    human_response: Optional[Dict[str, Any]] = None


@router.get("/hitl/escalations")
async def get_escalation_history(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get escalation history."""
    escalations = []
    targets = {agent_name: _hitl_agents[agent_name]} if agent_name and agent_name in _hitl_agents else _hitl_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_escalation_history"):
            agent_escalations = agent.get_escalation_history(limit)
            escalations.extend(agent_escalations)

    return {
        "escalations": escalations[-limit:],
        "total": len(escalations),
    }


@router.get("/hitl/trust-scores")
async def get_trust_scores(
    agent_name: Optional[str] = Query(None),
    worker_id: Optional[str] = Query(None),
):
    """
    Get trust scores for workers.

    Trust scores determine the autonomy level:
    - 0.0–0.2: Full Human (system only suggests)
    - 0.2–0.4: Human Confirms (system proposes, human approves)
    - 0.4–0.6: Human Informed (system acts, human notified)
    - 0.6–0.8: Human Override (system acts, human can override)
    - 0.8–1.0: Full Autonomy (system acts, periodic summary)
    """
    scores = []
    targets = {agent_name: _hitl_agents[agent_name]} if agent_name and agent_name in _hitl_agents else _hitl_agents

    for name, agent in targets.items():
        if worker_id:
            score = agent.get_trust_score(worker_id)
            scores.append(score)
        else:
            if hasattr(agent, "get_all_trust_scores"):
                all_scores = agent.get_all_trust_scores()
                scores.extend(all_scores)
            else:
                scores.append(agent.get_trust_score())

    return {"trust_scores": scores}


@router.get("/hitl/autonomy")
async def get_autonomy_levels(
    agent_name: Optional[str] = Query(None),
):
    """
    Get autonomy level distribution across workers.

    Shows how many workers are at each autonomy level.
    """
    distribution = {}
    targets = {agent_name: _hitl_agents[agent_name]} if agent_name and agent_name in _hitl_agents else _hitl_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_hitl_stats"):
            stats = agent.get_hitl_stats()
            distribution[name] = stats.get("autonomy_distribution", {})
        elif hasattr(agent, "get_metrics"):
            stats = agent.get_metrics()
            distribution[name] = stats.get("autonomy_distribution", {})

    return {"autonomy_distribution": distribution}


@router.get("/hitl/pending")
async def get_pending_escalations(
    agent_name: Optional[str] = Query(None),
):
    """Get pending escalation requests awaiting human response."""
    pending = []
    targets = {agent_name: _hitl_agents[agent_name]} if agent_name and agent_name in _hitl_agents else _hitl_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_pending_escalations"):
            agent_pending = agent.get_pending_escalations()
            pending.extend(agent_pending)

    return {
        "pending": pending,
        "count": len(pending),
    }


@router.post("/hitl/resolve")
async def resolve_escalation(
    request: ResolveEscalationRequest,
    agent_name: Optional[str] = Query(None),
):
    """
    Resolve a pending escalation with a human decision.

    Decision values: accepted, rejected, modified
    """
    valid_decisions = {"accepted", "rejected", "modified"}
    if request.decision not in valid_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision: {request.decision}. Must be one of: {sorted(valid_decisions)}",
        )

    # Find the agent with this pending escalation
    targets = {agent_name: _hitl_agents[agent_name]} if agent_name and agent_name in _hitl_agents else _hitl_agents

    for name, agent in targets.items():
        if hasattr(agent, "resolve_escalation"):
            result = await agent.resolve_escalation(
                escalation_id=request.escalation_id,
                resolution=request.decision,
                human_response=request.human_response,
            )
            if result.success:
                return result.data

    raise HTTPException(
        status_code=404,
        detail=f"Escalation {request.escalation_id} not found",
    )


@router.get("/hitl/stats")
async def get_hitl_stats(
    agent_name: Optional[str] = Query(None),
):
    """Get overall Human-in-the-Loop statistics."""
    stats = {}
    targets = {agent_name: _hitl_agents[agent_name]} if agent_name and agent_name in _hitl_agents else _hitl_agents

    for name, agent in targets.items():
        if hasattr(agent, "get_hitl_stats"):
            stats[name] = agent.get_hitl_stats()
        elif hasattr(agent, "get_metrics"):
            stats[name] = agent.get_metrics()

    return {"hitl_stats": stats}


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
        "ooda_cycles": 0,
        "feedback_signals": 0,
        "hitl_escalations": 0,
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

        if hasattr(agent, "get_metrics"):
            stats = agent.get_metrics()
            if "total_cycles" in stats:
                health["ooda_cycles"] += stats.get("total_cycles", 0)
                agent_health["patterns"].append("ooda")
            if "total_signals" in stats:
                health["feedback_signals"] += stats.get("total_signals", 0)
                agent_health["patterns"].append("feedback")
            if "total_decisions" in stats:
                health["hitl_escalations"] += stats.get("escalated_decisions", 0)
                agent_health["patterns"].append("hitl")

        health["agents"][name] = agent_health

    if _event_store:
        health["event_store_events"] = _event_store.get_stats().get("total_events", 0)

    if _supervisor:
        stats = _supervisor.get_supervision_stats()
        health["supervision_executions"] = stats.get("total_executions", 0)

    return health
