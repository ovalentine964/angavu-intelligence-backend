"""
MetaAgent — Tier 1 System Orchestrator.

Central coordinator that monitors all agents, resolves conflicts,
routes requests to the best agent, and manages cross-agent learning.

Responsibilities:
    - Agent registry and capability tracking
    - Request routing to the best-suited agent
    - Conflict detection and resolution
    - Cross-agent learning and knowledge sharing
    - System-wide health monitoring

Tier: 1 (Core) — started last, monitors everything.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Classes
# ════════════════════════════════════════════════════════════════════


@dataclass
class AgentMetrics:
    """Per-agent performance metrics tracked by MetaAgent."""
    agent_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_confidence: float = 0.0
    avg_duration_ms: float = 0.0
    last_active: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_requests": self.total_requests,
            "success_rate": round(self.success_rate, 3),
            "avg_confidence": round(self.avg_confidence, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "last_active": self.last_active,
        }


@dataclass
class ConflictRecord:
    """Record of a conflict detected between agents."""
    conflict_id: str
    agents_involved: List[str]
    conflict_type: str
    description: str
    resolution: str = ""
    resolved: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "agents_involved": self.agents_involved,
            "conflict_type": self.conflict_type,
            "description": self.description,
            "resolution": self.resolution,
            "resolved": self.resolved,
            "created_at": self.created_at,
        }


@dataclass
class LearningShare:
    """A learning shared between agents."""
    source_agent: str
    target_agents: List[str]
    insight: str
    confidence: float
    shared_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_agent": self.source_agent,
            "target_agents": self.target_agents,
            "insight": self.insight,
            "confidence": round(self.confidence, 3),
            "shared_at": self.shared_at,
        }


# ════════════════════════════════════════════════════════════════════
# Capability Router
# ════════════════════════════════════════════════════════════════════


class CapabilityRouter:
    """
    Routes requests to the best-suited agent based on capabilities
    and historical performance.
    """

    def __init__(self):
        self._agent_capabilities: Dict[str, List[str]] = {}
        self._agent_metrics: Dict[str, AgentMetrics] = {}

    def register(self, agent_name: str, capabilities: List[str]) -> None:
        self._agent_capabilities[agent_name] = capabilities
        if agent_name not in self._agent_metrics:
            self._agent_metrics[agent_name] = AgentMetrics(agent_name=agent_name)

    def route(self, required_capability: str) -> Optional[str]:
        """Find the best agent for a given capability."""
        candidates = [
            name for name, caps in self._agent_capabilities.items()
            if required_capability in caps
        ]
        if not candidates:
            return None

        # Rank by success rate, then by avg confidence
        ranked = sorted(
            candidates,
            key=lambda n: (
                self._agent_metrics[n].success_rate,
                self._agent_metrics[n].avg_confidence,
            ),
            reverse=True,
        )
        return ranked[0]

    def update_metrics(
        self, agent_name: str, success: bool, confidence: float, duration_ms: float
    ) -> None:
        m = self._agent_metrics.get(agent_name)
        if not m:
            return
        m.total_requests += 1
        if success:
            m.successful_requests += 1
        else:
            m.failed_requests += 1
        # Running average
        n = m.total_requests
        m.avg_confidence = ((m.avg_confidence * (n - 1)) + confidence) / n
        m.avg_duration_ms = ((m.avg_duration_ms * (n - 1)) + duration_ms) / n
        m.last_active = time.time()

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        return {name: m.to_dict() for name, m in self._agent_metrics.items()}


# ════════════════════════════════════════════════════════════════════
# Conflict Resolver
# ════════════════════════════════════════════════════════════════════


class ConflictResolver:
    """Detects and resolves conflicts between agents."""

    def __init__(self):
        self._conflicts: Dict[str, ConflictRecord] = {}
        self._counter = 0

    def detect(
        self,
        agents_involved: List[str],
        conflict_type: str,
        description: str,
    ) -> ConflictRecord:
        self._counter += 1
        conflict = ConflictRecord(
            conflict_id=f"conflict_{self._counter}",
            agents_involved=agents_involved,
            conflict_type=conflict_type,
            description=description,
        )
        self._conflicts[conflict.conflict_id] = conflict
        return conflict

    def resolve(self, conflict_id: str, resolution: str) -> bool:
        c = self._conflicts.get(conflict_id)
        if not c or c.resolved:
            return False
        c.resolution = resolution
        c.resolved = True
        return True

    def get_unresolved(self) -> List[Dict[str, Any]]:
        return [
            c.to_dict() for c in self._conflicts.values() if not c.resolved
        ]

    def get_all(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self._conflicts.values()]


# ════════════════════════════════════════════════════════════════════
# Cross-Agent Learning Manager
# ════════════════════════════════════════════════════════════════════


class CrossAgentLearningManager:
    """Shares learnings across agents to improve system-wide performance."""

    def __init__(self):
        self._shared_learnings: List[LearningShare] = []

    def share(
        self,
        source_agent: str,
        target_agents: List[str],
        insight: str,
        confidence: float,
    ) -> LearningShare:
        learning = LearningShare(
            source_agent=source_agent,
            target_agents=target_agents,
            insight=insight,
            confidence=confidence,
        )
        self._shared_learnings.append(learning)
        return learning

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [l.to_dict() for l in self._shared_learnings[-limit:]]

    def get_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        return [
            l.to_dict()
            for l in self._shared_learnings
            if agent_name in l.target_agents
        ]


# ════════════════════════════════════════════════════════════════════
# MetaAgent
# ════════════════════════════════════════════════════════════════════


class MetaAgent(BiasharaAgent):
    """
    Tier 1 MetaAgent — System-wide orchestrator.

    Does not process transactions directly. Instead:
    - Monitors all agent activity
    - Routes requests to the best agent
    - Resolves conflicts between agents
    - Facilitates cross-agent learning
    """

    def __init__(self):
        super().__init__(
            name="MetaAgent",
            role="System orchestrator — routing, conflict resolution, learning",
            capabilities=[
                "agent_routing",
                "conflict_resolution",
                "cross_agent_learning",
                "system_monitoring",
                "health_checking",
            ],
        )
        self._registered_agents: Dict[str, BiasharaAgent] = {}
        self._capability_router = CapabilityRouter()
        self._conflict_resolver = ConflictResolver()
        self._learning_manager = CrossAgentLearningManager()
        self._event_count: int = 0

    def register_agent(self, agent: BiasharaAgent) -> None:
        """Register an agent for monitoring and routing."""
        self._registered_agents[agent.name] = agent
        self._capability_router.register(agent.name, list(agent.capabilities))
        self._logger.info("agent_registered", agent=agent.name, capabilities=agent.capabilities)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """Analyze the event and decide on a meta-action."""
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")

        if event_type == EventType.CONFLICT_DETECTED.value:
            return AgentDecision(
                action="resolve_conflict",
                parameters=event_data.get("payload", {}),
                confidence=0.9,
                reasoning="Conflict detected between agents",
            )

        if event_type == EventType.AGENT_HEALTH_CHECK.value:
            return AgentDecision(
                action="check_health",
                parameters=event_data.get("payload", {}),
                confidence=0.95,
                reasoning="Health check requested",
            )

        if event_type == EventType.PIPELINE_ERROR.value:
            return AgentDecision(
                action="handle_error",
                parameters=event_data.get("payload", {}),
                confidence=0.85,
                reasoning="Pipeline error detected",
            )

        # For domain analysis requests, route to best agent
        if event_type in (
            EventType.DOMAIN_ANALYSIS_REQUESTED.value,
            EventType.INTELLIGENCE_REQUESTED.value,
        ):
            payload = event_data.get("payload", {})
            capability = payload.get("capability", "intelligence_generation")
            best_agent = self._capability_router.route(capability)
            return AgentDecision(
                action="route_request",
                parameters={
                    "target_agent": best_agent,
                    "capability": capability,
                    "payload": payload,
                },
                confidence=0.8 if best_agent else 0.3,
                reasoning=f"Routing to {best_agent}" if best_agent else "No suitable agent found",
            )

        return AgentDecision(
            action="monitor",
            parameters={},
            confidence=0.5,
            reasoning="Routine monitoring pass",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the meta-action."""
        start = time.time()
        action = decision.action
        params = decision.parameters

        try:
            if action == "resolve_conflict":
                result = await self._resolve_conflict(params)
            elif action == "check_health":
                result = self._check_all_health()
            elif action == "handle_error":
                result = self._handle_error(params)
            elif action == "route_request":
                result = await self._route_request(params)
            elif action == "monitor":
                result = self._system_status()
            else:
                result = {"status": "unknown_action", "action": action}

            return AgentResult(
                success=True,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _resolve_conflict(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve an agent conflict."""
        agents = params.get("agents_involved", [])
        conflict_type = params.get("conflict_type", "unknown")
        description = params.get("description", "")

        conflict = self._conflict_resolver.detect(agents, conflict_type, description)

        # Auto-resolve by selecting agent with higher success rate
        if len(agents) >= 2:
            best = max(
                agents,
                key=lambda a: self._capability_router._agent_metrics.get(
                    a, AgentMetrics(agent_name=a)
                ).success_rate,
            )
            self._conflict_resolver.resolve(conflict.conflict_id, f"Preferred {best} based on track record")
            return {
                "conflict_id": conflict.conflict_id,
                "resolution": f"Preferred {best}",
                "resolved": True,
            }

        return {"conflict_id": conflict.conflict_id, "resolved": False}

    def _check_all_health(self) -> Dict[str, Any]:
        """Check health of all registered agents."""
        health = {}
        for name, agent in self._registered_agents.items():
            try:
                health[name] = agent.health_check()
            except Exception as exc:
                health[name] = {"status": "error", "error": str(exc)}
        return {"agents": health, "total": len(health)}

    def _handle_error(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a pipeline error."""
        source = params.get("source", "unknown")
        error = params.get("error", "unknown")
        self._logger.warning("pipeline_error_handled", source=source, error=error)
        return {"action": "logged", "source": source}

    async def _route_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Route a request to the best agent."""
        target = params.get("target_agent")
        if target and target in self._registered_agents:
            return {"routed_to": target, "status": "routed"}
        return {"routed_to": None, "status": "no_suitable_agent"}

    def _system_status(self) -> Dict[str, Any]:
        """Get system-wide status."""
        return {
            "registered_agents": len(self._registered_agents),
            "metrics": self._capability_router.get_all_metrics(),
            "unresolved_conflicts": len(self._conflict_resolver.get_unresolved()),
            "recent_learnings": len(self._learning_manager.get_recent()),
        }

    # ── Query API ───────────────────────────────────────────────────

    def get_routing_metrics(self) -> Dict[str, Any]:
        return self._capability_router.get_all_metrics()

    def get_conflicts(self) -> List[Dict[str, Any]]:
        return self._conflict_resolver.get_all()

    def get_learnings(self) -> List[Dict[str, Any]]:
        return self._learning_manager.get_recent()
