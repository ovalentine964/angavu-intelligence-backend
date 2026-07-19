"""
MCP Swarm Router — Domain-based task routing across Angavu swarms.

Inspired by: awesome-llm-apps/mcp_ai_agents/multi_mcp_agent_router/
Pattern: classify query domain → route to correct swarm → aggregate results

Routes incoming tasks to the appropriate swarm based on domain classification.
Each swarm specializes in a different aspect of Angavu Intelligence.

Architecture:
    DomainClassifier → classifies task by domain keywords + context
    MCPSwarmRouter → routes to correct swarm, manages MCP tool connections
    SwarmRoute → maps domains to swarm definitions and tools

Swarms:
    - Core Swarm: Transaction processing, intelligence generation
    - Domain Swarm: Sector-specific analysis (agriculture, retail, etc.)
    - Governance Swarm: Audit, ethics, privacy
    - Research Swarm: Market research, user insights, innovation
    - Financial Swarm: Credit scoring, forecasting
    - Utility Swarm: Data quality, anomaly detection
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

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
# Domain & Swarm Definitions
# ════════════════════════════════════════════════════════════════════


class TaskDomain(StrEnum):
    """Domains for task classification."""
    TRANSACTION = "transaction"
    INTELLIGENCE = "intelligence"
    REPORTING = "reporting"
    AGRICULTURE = "agriculture"
    RETAIL = "retail"
    TRANSPORT = "transport"
    DIGITAL = "digital"
    MANUFACTURING = "manufacturing"
    SERVICE = "service"
    FINANCIAL = "financial"
    GOVERNANCE = "governance"
    RESEARCH = "research"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    VOICE = "voice"
    GENERAL = "general"


class SwarmId(StrEnum):
    """Identifiers for Angavu swarms."""
    CORE = "core_swarm"
    DOMAIN = "domain_swarm"
    GOVERNANCE = "governance_swarm"
    RESEARCH = "research_swarm"
    FINANCIAL = "financial_swarm"
    UTILITY = "utility_swarm"


@dataclass(frozen=True)
class SwarmDefinition:
    """Definition of a swarm's capabilities and tools."""
    swarm_id: SwarmId
    name: str
    description: str
    agents: list[str]
    domains: list[TaskDomain]
    mcp_tools: list[str]          # MCP tool names available
    priority: int                 # Higher = preferred when multiple match
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id.value,
            "name": self.name,
            "description": self.description,
            "agents": self.agents,
            "domains": [d.value for d in self.domains],
            "mcp_tools": self.mcp_tools,
            "priority": self.priority,
            "capabilities": self.capabilities,
        }


@dataclass(frozen=True)
class SwarmRoute:
    """Result of routing a task to a swarm."""
    domain: TaskDomain
    swarm: SwarmDefinition
    confidence: float
    matched_keywords: list[str]
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain.value,
            "swarm": self.swarm.to_dict(),
            "confidence": round(self.confidence, 3),
            "matched_keywords": self.matched_keywords,
            "reasoning": self.reasoning,
        }


# ════════════════════════════════════════════════════════════════════
# Swarm Registry
# ════════════════════════════════════════════════════════════════════


SWARM_REGISTRY: dict[SwarmId, SwarmDefinition] = {
    SwarmId.CORE: SwarmDefinition(
        swarm_id=SwarmId.CORE,
        name="Core Processing Swarm",
        description="Transaction processing, intelligence generation, and reporting",
        agents=["TransactionProcessor", "IntelligenceGenerator", "ReportGenerator", "SelfEvolution"],
        domains=[TaskDomain.TRANSACTION, TaskDomain.INTELLIGENCE, TaskDomain.REPORTING],
        mcp_tools=["process_transaction", "generate_intelligence", "generate_report", "price_forecast", "credit_score"],
        priority=10,
        capabilities=["data_pipeline", "ml_inference", "report_generation"],
    ),
    SwarmId.DOMAIN: SwarmDefinition(
        swarm_id=SwarmId.DOMAIN,
        name="Domain Analysis Swarm",
        description="Sector-specific analysis for agriculture, retail, transport, digital, manufacturing, service",
        agents=["AgricultureDomainAgent", "RetailDomainAgent", "TransportDomainAgent",
                "DigitalDomainAgent", "ManufacturingDomainAgent", "ServiceDomainAgent"],
        domains=[TaskDomain.AGRICULTURE, TaskDomain.RETAIL, TaskDomain.TRANSPORT,
                 TaskDomain.DIGITAL, TaskDomain.MANUFACTURING, TaskDomain.SERVICE],
        mcp_tools=["domain_analysis", "sector_insights", "peer_comparison", "market_benchmark"],
        priority=8,
        capabilities=["sector_analysis", "peer_benchmarking", "domain_specific_ml"],
    ),
    SwarmId.GOVERNANCE: SwarmDefinition(
        swarm_id=SwarmId.GOVERNANCE,
        name="Governance & Compliance Swarm",
        description="Audit, ethics review, privacy protection, and regulatory compliance",
        agents=["AuditAgent", "EthicsAgent", "PrivacyAgent", "ComplianceAgent"],
        domains=[TaskDomain.GOVERNANCE, TaskDomain.COMPLIANCE],
        mcp_tools=["run_audit", "ethics_review", "privacy_check", "compliance_scan"],
        priority=9,
        capabilities=["audit_trail", "ethics_assessment", "privacy_enforcement"],
    ),
    SwarmId.RESEARCH: SwarmDefinition(
        swarm_id=SwarmId.RESEARCH,
        name="Research & Innovation Swarm",
        description="Market research, user insights, competitive intelligence, and innovation",
        agents=["MarketResearchAgent", "UserInsightAgent", "InnovationAgent"],
        domains=[TaskDomain.RESEARCH],
        mcp_tools=["market_research", "user_insights", "competitor_analysis", "innovation_proposal"],
        priority=7,
        capabilities=["market_scanning", "user_research", "innovation_generation"],
    ),
    SwarmId.FINANCIAL: SwarmDefinition(
        swarm_id=SwarmId.FINANCIAL,
        name="Financial Intelligence Swarm",
        description="Credit scoring, financial forecasting, and risk assessment",
        agents=["CreditScorerAgent", "FinancialForecasterAgent", "RiskAssessorAgent"],
        domains=[TaskDomain.FINANCIAL],
        mcp_tools=["credit_score", "financial_forecast", "risk_assessment", "liquidity_analysis"],
        priority=8,
        capabilities=["credit_scoring", "financial_modeling", "risk_quantification"],
    ),
    SwarmId.UTILITY: SwarmDefinition(
        swarm_id=SwarmId.UTILITY,
        name="Utility Services Swarm",
        description="Data quality, anomaly detection, prediction, and sync",
        agents=["DataQualityAgent", "AnomalyDetectorAgent", "PredictionAgent",
                "CommunicationAgent", "LearningAgent", "SyncAgent"],
        domains=[TaskDomain.GENERAL],
        mcp_tools=["data_quality_check", "anomaly_detect", "predict", "sync_data"],
        priority=3,
        capabilities=["data_validation", "anomaly_detection", "cross_service_sync"],
    ),
}


# ════════════════════════════════════════════════════════════════════
# DomainClassifier — Keyword + Context Classification
# ════════════════════════════════════════════════════════════════════


# Domain keyword mappings
DOMAIN_KEYWORDS: dict[TaskDomain, set[str]] = {
    TaskDomain.TRANSACTION: {
        "transaction", "payment", "mpesa", "mobile money", "pos",
        "receipt", "sale", "purchase", "checkout", "invoice",
        "batch", "pipeline", "ingest",
    },
    TaskDomain.INTELLIGENCE: {
        "intelligence", "insight", "analysis", "forecast", "predict",
        "trend", "pattern", "anomaly", "signal", "metric",
        "dashboard", "kpi", "report",
    },
    TaskDomain.REPORTING: {
        "report", "generate report", "pdf", "export", "summary",
        "briefing", "digest", "presentation",
    },
    TaskDomain.AGRICULTURE: {
        "agriculture", "farming", "crop", "harvest", "livestock",
        "maize", "beans", "rice", "coffee", "tea", "fertilizer",
        "irrigation", "yield", "acre", "farm",
    },
    TaskDomain.RETAIL: {
        "retail", "shop", "store", "inventory", "stock",
        "customer", "sales", "wholesale", "market", "vendor",
        "supermarket", "duka", "kiosk",
    },
    TaskDomain.TRANSPORT: {
        "transport", "logistics", "delivery", "matatu", "fleet",
        "route", "shipping", "freight", "psv", "ntsa",
        "fuel", "mileage",
    },
    TaskDomain.DIGITAL: {
        "digital", "online", "e-commerce", "website", "app",
        "social media", "digital marketing", "seo", "saas",
        "tech", "startup",
    },
    TaskDomain.MANUFACTURING: {
        "manufacturing", "factory", "production", "assembly",
        "quality control", "supply chain", "raw material",
        "kebs", "standard", "machinery",
    },
    TaskDomain.SERVICE: {
        "service", "hospitality", "tourism", "restaurant", "hotel",
        "salon", "spa", "cleaning", "repair", "consulting",
    },
    TaskDomain.FINANCIAL: {
        "credit", "loan", "finance", "banking", "interest rate",
        "collateral", "repayment", "microfinance", "sacco",
        "investment", "portfolio", "risk",
    },
    TaskDomain.GOVERNANCE: {
        "audit", "compliance", "ethics", "privacy", "governance",
        "regulation", "policy", "legal", "gdpr", "odpc",
        "data protection", "security scan",
    },
    TaskDomain.RESEARCH: {
        "research", "market research", "competitor", "survey",
        "user insight", "innovation", "r&d", "prototype",
        "experiment", "hypothesis",
    },
    TaskDomain.COMPLIANCE: {
        "compliance", "regulation", "kra", "tax", "vat",
        "withholding", "nssf", "nhif", "permit", "license",
        "penalty", "fine",
    },
    TaskDomain.SECURITY: {
        "security", "vulnerability", "threat", "incident",
        "breach", "encryption", "authentication", "authorization",
        "owasp", "penetration",
    },
    TaskDomain.VOICE: {
        "voice", "speech", "transcription", "audio",
        "call", "ivr", "stt", "tts", "whisper",
    },
}


class DomainClassifier:
    """
    Classifies tasks by domain using keyword matching and context.

    Inspired by multi_mcp_agent_router's classify_query:
    - Keyword matching against domain vocabularies
    - Context-aware boosting (e.g., previous events in conversation)
    - Confidence scoring based on keyword density
    """

    def __init__(self):
        self._logger = logger.bind(component="domain_classifier")

    def classify(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[TaskDomain, float, list[str]]:
        """
        Classify a query into a domain.

        Returns:
            (domain, confidence, matched_keywords)
        """
        query_lower = query.lower()
        scores: dict[TaskDomain, tuple[int, list[str]]] = {}

        for domain, keywords in DOMAIN_KEYWORDS.items():
            matched = [kw for kw in keywords if kw in query_lower]
            if matched:
                scores[domain] = (len(matched), matched)

        if not scores:
            return TaskDomain.GENERAL, 0.3, []

        # Pick domain with most keyword hits
        best_domain = max(scores, key=lambda d: scores[d][0])
        hit_count, matched = scores[best_domain]

        # Confidence: more hits = higher confidence, capped at 0.99
        total_keywords = len(DOMAIN_KEYWORDS[best_domain])
        confidence = min(0.99, 0.4 + (hit_count / max(total_keywords, 1)) * 0.6)

        # Context boosting
        if context:
            recent_events = context.get("recent_events", [])
            for evt in recent_events:
                evt_type = evt.get("event_type", "")
                if best_domain.value in evt_type:
                    confidence = min(0.99, confidence + 0.1)
                    break

        return best_domain, round(confidence, 3), matched

    def classify_multi(
        self,
        query: str,
        top_n: int = 3,
    ) -> list[tuple[TaskDomain, float, list[str]]]:
        """Return top N domain classifications."""
        query_lower = query.lower()
        results = []

        for domain, keywords in DOMAIN_KEYWORDS.items():
            matched = [kw for kw in keywords if kw in query_lower]
            if matched:
                hit_count = len(matched)
                total = len(DOMAIN_KEYWORDS[domain])
                confidence = min(0.99, 0.4 + (hit_count / max(total, 1)) * 0.6)
                results.append((domain, round(confidence, 3), matched))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]


# ════════════════════════════════════════════════════════════════════
# MCPSwarmRouter — BiasharaAgent Integration
# ════════════════════════════════════════════════════════════════════


class MCPSwarmRouter(BiasharaAgent):
    """
    MCP-aware router that directs tasks to the correct Angavu swarm.

    Inspired by multi_mcp_agent_router:
    - Classifies incoming task by domain
    - Routes to the appropriate swarm's agents
    - Manages MCP tool connections per swarm
    - Aggregates results and returns to caller

    Subscribes to: intelligence.requested, domain.analysis.requested
    Publishes: domain.analysis.completed, intelligence.generated
    """

    def __init__(self):
        super().__init__(
            name="MCPSwarmRouter",
            role="Domain-aware task routing and MCP tool orchestration",
            capabilities=[
                "domain_classification",
                "swarm_routing",
                "mcp_tool_management",
                "task_delegation",
                "result_aggregation",
            ],
        )
        self._classifier = DomainClassifier()
        self._swarm_registry = dict(SWARM_REGISTRY)
        self._agent_map: dict[str, BiasharaAgent] = {}  # agent_name → agent
        self._mcp_sessions: dict[str, Any] = {}  # swarm_id → MCP session
        self._route_history: list[dict] = []
        self._logger = logger.bind(agent="MCPSwarmRouter")

    def register_agent(self, agent: BiasharaAgent) -> None:
        """Register an agent for routing."""
        self._agent_map[agent.name] = agent
        self._logger.debug("agent_registered", agent=agent.name)

    def register_swarm(self, swarm: SwarmDefinition) -> None:
        """Register a custom swarm definition."""
        self._swarm_registry[swarm.swarm_id] = swarm

    def get_swarm_for_domain(self, domain: TaskDomain) -> SwarmDefinition | None:
        """Get the best swarm for a given domain."""
        candidates = [
            swarm for swarm in self._swarm_registry.values()
            if domain in swarm.domains
        ]
        if not candidates:
            return self._swarm_registry.get(SwarmId.UTILITY)
        return max(candidates, key=lambda s: s.priority)

    # ── BiasharaAgent lifecycle ─────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Observe incoming routing requests."""
        await super().observe(event)

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Classify the incoming task and determine target swarm.
        """
        event = context.get("event", {})
        payload = event.get("payload", {})
        event_type = event.get("event_type", "")

        # Extract query from payload
        query = (
            payload.get("query")
            or payload.get("action")
            or payload.get("description")
            or payload.get("text")
            or ""
        )

        if not query:
            # If no query, check if this is a domain analysis request
            if event_type == EventType.DOMAIN_ANALYSIS_REQUESTED.value:
                domain_str = payload.get("domain", "general")
                try:
                    domain = TaskDomain(domain_str)
                except ValueError:
                    domain = TaskDomain.GENERAL
                return AgentDecision(
                    action="route_to_swarm",
                    parameters={
                        "domain": domain.value,
                        "confidence": 0.95,
                        "matched_keywords": [domain_str],
                        "original_event": event,
                    },
                    confidence=0.95,
                    reasoning=f"Domain analysis requested for {domain_str}.",
                )

            return AgentDecision(
                action="passthrough",
                parameters={"event": event},
                confidence=0.3,
                reasoning="No query found in payload — passing through to utility swarm.",
            )

        # Classify the query
        domain, confidence, matched = self._classifier.classify(query)

        return AgentDecision(
            action="route_to_swarm",
            parameters={
                "domain": domain.value,
                "confidence": confidence,
                "matched_keywords": matched,
                "query": query,
                "original_event": event,
            },
            confidence=confidence,
            reasoning=f"Classified as {domain.value} (confidence={confidence:.2f}, keywords={matched}).",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Route the task to the appropriate swarm."""
        start = time.time()

        if decision.action == "passthrough":
            return await self._passthrough(decision.parameters)

        if decision.action == "route_to_swarm":
            return await self._route_to_swarm(decision.parameters)

        return AgentResult(
            success=False,
            error=f"Unknown routing action: {decision.action}",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _route_to_swarm(self, params: dict) -> AgentResult:
        """Route task to the classified swarm's agents."""
        start = time.time()
        domain_str = params.get("domain", "general")
        confidence = params.get("confidence", 0.5)
        matched = params.get("matched_keywords", [])
        query = params.get("query", "")
        original_event = params.get("original_event", {})

        try:
            domain = TaskDomain(domain_str)
        except ValueError:
            domain = TaskDomain.GENERAL

        # Find target swarm
        swarm = self.get_swarm_for_domain(domain)
        if not swarm:
            return AgentResult(
                success=False,
                error=f"No swarm found for domain: {domain_str}",
                duration_ms=(time.time() - start) * 1000,
            )

        # Find available agents in the swarm
        available_agents = [
            self._agent_map[name]
            for name in swarm.agents
            if name in self._agent_map
        ]

        # Record route
        route = SwarmRoute(
            domain=domain,
            swarm=swarm,
            confidence=confidence,
            matched_keywords=matched,
            reasoning=f"Domain={domain_str}, swarm={swarm.name}, agents={len(available_agents)}",
        )
        self._route_history.append(route.to_dict())
        if len(self._route_history) > 1000:
            self._route_history = self._route_history[-1000:]

        self._logger.info(
            "task_routed",
            domain=domain_str,
            swarm=swarm.swarm_id.value,
            confidence=confidence,
            available_agents=len(available_agents),
            matched_keywords=matched,
        )

        # Delegate to the first available agent in the swarm
        # (In production, this would use the delegation protocol)
        if available_agents:
            target = available_agents[0]
            try:
                result = await target.handle_event(AgentEvent(
                    event_type=EventType.INTELLIGENCE_REQUESTED,
                    source=self.name,
                    payload={
                        "query": query,
                        "domain": domain_str,
                        "routed_by": self.name,
                        "original_payload": original_event.get("payload", {}),
                    },
                ))

                # Emit routing completion event
                events_to_publish = [
                    AgentEvent(
                        event_type=EventType.DOMAIN_ANALYSIS_COMPLETED,
                        source=self.name,
                        payload={
                            "domain": domain_str,
                            "swarm": swarm.swarm_id.value,
                            "agent": target.name,
                            "success": result.success,
                            "confidence": confidence,
                        },
                    )
                ]

                return AgentResult(
                    success=result.success,
                    data={
                        "route": route.to_dict(),
                        "agent_result": result.data,
                        "delegated_to": target.name,
                    },
                    error=result.error,
                    duration_ms=(time.time() - start) * 1000,
                    events_to_publish=events_to_publish,
                )

            except Exception as exc:
                self._logger.error(
                    "delegation_failed",
                    agent=target.name,
                    error=str(exc),
                )
                return AgentResult(
                    success=False,
                    error=f"Delegation to {target.name} failed: {exc}",
                    data={"route": route.to_dict()},
                    duration_ms=(time.time() - start) * 1000,
                )

        # No agents available — return route info only
        return AgentResult(
            success=True,
            data={
                "route": route.to_dict(),
                "note": f"No agents available in {swarm.name}. Route recorded for manual delegation.",
            },
            duration_ms=(time.time() - start) * 1000,
        )

    async def _passthrough(self, params: dict) -> AgentResult:
        """Pass through to utility swarm when classification fails."""
        event = params.get("event", {})
        utility_swarm = self._swarm_registry.get(SwarmId.UTILITY)

        return AgentResult(
            success=True,
            data={
                "route": {
                    "domain": TaskDomain.GENERAL.value,
                    "swarm": utility_swarm.to_dict() if utility_swarm else None,
                    "confidence": 0.3,
                    "reasoning": "No clear domain — routed to utility swarm.",
                },
            },
            duration_ms=0,
        )

    def get_route_history(self, limit: int = 50) -> list[dict]:
        """Return recent routing history."""
        return self._route_history[-limit:]

    def get_swarm_registry(self) -> dict[str, dict]:
        """Return all registered swarm definitions."""
        return {k.value: v.to_dict() for k, v in self._swarm_registry.items()}
