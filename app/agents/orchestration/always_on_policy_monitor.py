"""
Always-On Policy Monitor — Monitor/Rank/Alert pattern for regulatory changes.

Inspired by: awesome-llm-apps/always_on_agents/release_radar_agent/
Pattern: monitor (scan sources) → rank (classify impact) → alert (emit events)

Watches government gazettes, regulatory announcements, and policy changes
relevant to East African SMEs. Emits alerts through the Angavu event bus.

Architecture:
    PolicyRadar → scans regulatory data sources
    PolicyRanker → classifies impact on SME sectors
    AlwaysOnPolicyMonitor → orchestrates pipeline, emits events

Integrates with:
    - Angavu EventBus (Redis Streams)
    - ComplianceAgent (downstream compliance checks)
    - BiasharaAgent lifecycle (observe → think → act → reflect)
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import asdict, dataclass, field
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
# Data Types
# ════════════════════════════════════════════════════════════════════


class PolicyImpact(StrEnum):
    """Impact level on SME operations."""
    CRITICAL = "critical"     # Immediate compliance required
    HIGH = "high"             # Action needed within days
    MEDIUM = "medium"         # Review within weeks
    LOW = "low"               # Awareness only
    INFORMATIONAL = "info"    # No direct impact


class PolicyDomain(StrEnum):
    """Regulatory domains relevant to Angavu."""
    TAX = "tax"                       # KRA, VAT, withholding
    TRADE = "trade"                   # Import/export, customs
    FINANCIAL = "financial"           # CBK, CMA, microfinance
    LABOR = "labor"                   # Employment, NSSF, NHIF
    DATA_PROTECTION = "data_protection"  # ODPC, privacy
    HEALTH = "health"                 # KEBS, health standards
    ENVIRONMENT = "environment"       # NEMA, green regulations
    DIGITAL = "digital"               # ICT, e-commerce, mobile money
    AGRICULTURE = "agriculture"       # Agriculture, food safety
    GENERAL = "general"               # Cross-cutting policies


@dataclass(frozen=True)
class PolicyItem:
    """A single policy/regulatory observation."""
    title: str
    source: str               # e.g., "kenya_gazette", "kra", "cbk"
    domain: PolicyDomain
    summary: str
    url: str
    published_at: str         # ISO date
    effective_date: str | None = None
    sectors_affected: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RankedPolicy:
    """A policy item with impact classification."""
    item: PolicyItem
    impact: PolicyImpact
    impact_score: int         # 0-100
    reasons: tuple[str, ...]
    sme_relevance: str        # Why SMEs should care
    action_required: str      # What to do

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyBrief:
    """Ranked policy intelligence brief."""
    generated_at: str
    watch_mode: str
    policies: list[RankedPolicy]
    summary_text: str
    summary_html: str
    next_actions: list[str]
    impact_breakdown: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


# ════════════════════════════════════════════════════════════════════
# Sample Data — East African Regulatory Context
# ════════════════════════════════════════════════════════════════════


SAMPLE_POLICIES: list[PolicyItem] = [
    PolicyItem(
        title="KRA: New Digital Services Tax Rate Effective August 2026",
        source="kra",
        domain=PolicyDomain.TAX,
        summary="Digital services tax increased from 3% to 5% on gross transaction value. Applies to all digital marketplace platforms.",
        url="https://www.kra.go.ke/notices/dst-2026",
        published_at="2026-07-15",
        effective_date="2026-08-01",
        sectors_affected=["digital", "retail", "service"],
    ),
    PolicyItem(
        title="CBK: New Mobile Money Transaction Limits",
        source="cbk",
        domain=PolicyDomain.FINANCIAL,
        summary="Daily mobile money transaction limit raised from KES 300,000 to KES 500,000. Monthly limit raised to KES 3,000,000.",
        url="https://www.centralbank.go.ke/circulars/2026-07",
        published_at="2026-07-10",
        effective_date="2026-07-20",
        sectors_affected=["retail", "transport", "service"],
    ),
    PolicyItem(
        title="KEBS: Mandatory Product Certification for Agricultural Exports",
        source="kebs",
        domain=PolicyDomain.HEALTH,
        summary="All agricultural exports now require KEBS pre-export certification. Non-compliant shipments face 100% inspection at port.",
        url="https://www.kebs.org/certification-notice-2026",
        published_at="2026-07-12",
        effective_date="2026-09-01",
        sectors_affected=["agriculture"],
    ),
    PolicyItem(
        title="ODPC: Data Protection Impact Assessment Requirements Expanded",
        source="odpc",
        domain=PolicyDomain.DATA_PROTECTION,
        summary="All businesses processing over 10,000 customer records must complete DPIA by December 2026. Penalties up to KES 5M for non-compliance.",
        url="https://www.odpc.go.ke/dipa-2026",
        published_at="2026-07-08",
        effective_date="2026-12-01",
        sectors_affected=["digital", "retail", "service", "financial"],
    ),
    PolicyItem(
        title="NEMA: Single-Use Plastic Ban Enforcement Intensified",
        source="nema",
        domain=PolicyDomain.ENVIRONMENT,
        summary="Immediate enforcement of single-use plastic ban. Fines of KES 50,000-4,000,000 for manufacturers and distributors.",
        url="https://www.nema.go.ke/plastic-ban-2026",
        published_at="2026-07-14",
        effective_date="2026-07-14",
        sectors_affected=["manufacturing", "retail"],
    ),
    PolicyItem(
        title="Treasury: VAT Exemption on Solar Products Extended",
        source="treasury",
        domain=PolicyDomain.TAX,
        summary="VAT exemption on solar panels, batteries, and related equipment extended through 2028. Reduces cost of solar installations by 16%.",
        url="https://www.treasury.go.ke/vat-solar-2026",
        published_at="2026-07-05",
        effective_date="2026-07-05",
        sectors_affected=["manufacturing", "agriculture", "transport"],
    ),
    PolicyItem(
        title="NTSA: New Matatu Safety Compliance Requirements",
        source="ntsa",
        domain=PolicyDomain.GENERAL,
        summary="All PSV vehicles must install speed governors and CCTV by October 2026. Non-compliant vehicles face immediate suspension.",
        url="https://www.ntsa.go.ke/psv-compliance-2026",
        published_at="2026-07-11",
        effective_date="2026-10-01",
        sectors_affected=["transport"],
    ),
]


# ════════════════════════════════════════════════════════════════════
# PolicyRadar — Data Fetching Layer
# ════════════════════════════════════════════════════════════════════


# Signal terms that increase urgency
URGENCY_SIGNALS = {
    "immediate": 30,
    "mandatory": 25,
    "penalty": 20,
    "fine": 20,
    "suspension": 25,
    "enforcement": 20,
    "non-compliance": 22,
    "deadline": 15,
    "new requirement": 18,
    "must": 15,
}

# Terms that decrease urgency (more time to comply)
DEESCALATION_SIGNALS = {
    "voluntary": -10,
    "guidance": -5,
    "consultation": -8,
    "proposed": -10,
    "draft": -12,
    "extended": -5,
}


class PolicyRadar:
    """
    Scans regulatory data sources for policy changes.

    In live mode: fetches from government APIs, gazette RSS feeds.
    In sample mode: uses deterministic data for demos/tests.
    """

    def __init__(self, live: bool = False):
        self._live = live
        self._known_policies: set[str] = set()  # track seen policy IDs
        self._logger = logger.bind(component="policy_radar")

    async def scan_policies(self) -> list[PolicyItem]:
        """Scan for new policy items."""
        if self._live:
            return await self._scan_live_sources()
        return self._scan_sample_data()

    def _scan_sample_data(self) -> list[PolicyItem]:
        """Return sample policies, filtering already-seen ones."""
        new_policies = []
        for policy in SAMPLE_POLICIES:
            policy_id = hashlib.sha256(policy.title.encode()).hexdigest()[:16]
            if policy_id not in self._known_policies:
                self._known_policies.add(policy_id)
                new_policies.append(policy)
        return new_policies

    async def _scan_live_sources(self) -> list[PolicyItem]:
        """Scan live government/regulatory sources."""
        # In production: HTTP requests to gazette APIs, RSS feeds, etc.
        # Stub for now — falls back to sample
        self._logger.info("live_policy_scan_not_implemented_using_sample")
        return self._scan_sample_data()


# ════════════════════════════════════════════════════════════════════
# PolicyRanker — Impact Classification
# ════════════════════════════════════════════════════════════════════


import hashlib


class PolicyRanker:
    """
    Classifies policy items by SME impact level.

    Inspired by release_radar_agent's ranker:
    - Signal detection in policy text
    - Domain-based weighting
    - Time-to-compliance urgency scoring
    """

    def __init__(self):
        self._logger = logger.bind(component="policy_ranker")

    def rank_policies(self, policies: list[PolicyItem]) -> list[RankedPolicy]:
        """Score and rank policies by SME impact."""
        ranked = []
        for policy in policies:
            ranked_policy = self._classify_policy(policy)
            if ranked_policy:
                ranked.append(ranked_policy)
        return sorted(ranked, key=lambda p: p.impact_score, reverse=True)

    def _classify_policy(self, item: PolicyItem) -> RankedPolicy | None:
        """Classify a single policy item."""
        searchable = f"{item.title}\n{item.summary}".lower()

        # Compute signal score
        score = 0
        reasons = []

        # Urgency signals
        for term, weight in URGENCY_SIGNALS.items():
            if term in searchable:
                score += weight
                reasons.append(f"contains '{term}'")

        # De-escalation signals
        for term, weight in DEESCALATION_SIGNALS.items():
            if term in searchable:
                score += weight
                reasons.append(f"contains '{term}' (de-escalating)")

        # Domain weighting
        domain_weights = {
            PolicyDomain.TAX: 30,
            PolicyDomain.FINANCIAL: 25,
            PolicyDomain.DATA_PROTECTION: 22,
            PolicyDomain.HEALTH: 20,
            PolicyDomain.LABOR: 18,
            PolicyDomain.ENVIRONMENT: 15,
            PolicyDomain.TRADE: 15,
            PolicyDomain.DIGITAL: 12,
            PolicyDomain.AGRICULTURE: 12,
            PolicyDomain.GENERAL: 8,
        }
        domain_weight = domain_weights.get(item.domain, 10)
        score += domain_weight
        reasons.append(f"domain={item.domain.value} (weight={domain_weight})")

        # Effective date urgency
        if item.effective_date:
            try:
                from datetime import datetime
                effective = datetime.fromisoformat(item.effective_date)
                days_until = (effective - datetime.now()).days
                if days_until <= 0:
                    score += 40
                    reasons.append("already in effect")
                elif days_until <= 7:
                    score += 30
                    reasons.append(f"effective in {days_until} days")
                elif days_until <= 30:
                    score += 20
                    reasons.append(f"effective in {days_until} days")
                elif days_until <= 90:
                    score += 10
                    reasons.append(f"effective in {days_until} days")
            except (ValueError, TypeError):
                pass

        # Sectors affected breadth
        if len(item.sectors_affected) >= 3:
            score += 15
            reasons.append(f"broad impact: {len(item.sectors_affected)} sectors")

        # Clamp score
        score = max(0, min(100, score))

        # Classify impact
        if score >= 70:
            impact = PolicyImpact.CRITICAL
        elif score >= 55:
            impact = PolicyImpact.HIGH
        elif score >= 35:
            impact = PolicyImpact.MEDIUM
        elif score >= 15:
            impact = PolicyImpact.LOW
        else:
            impact = PolicyImpact.INFORMATIONAL

        sme_relevance = self._generate_sme_relevance(item, impact)
        action_required = self._generate_action_required(item, impact)

        return RankedPolicy(
            item=item,
            impact=impact,
            impact_score=score,
            reasons=tuple(reasons),
            sme_relevance=sme_relevance,
            action_required=action_required,
        )

    def _generate_sme_relevance(self, item: PolicyItem, impact: PolicyImpact) -> str:
        """Generate a human-readable SME relevance statement."""
        sector_str = ", ".join(item.sectors_affected) if item.sectors_affected else "all sectors"
        if impact == PolicyImpact.CRITICAL:
            return f"CRITICAL for {sector_str} businesses. Immediate action required to avoid penalties."
        if impact == PolicyImpact.HIGH:
            return f"HIGH relevance for {sector_str}. Review and prepare compliance measures."
        if impact == PolicyImpact.MEDIUM:
            return f"Moderate relevance for {sector_str}. Plan for upcoming changes."
        return f"Low direct impact on {sector_str}. Monitor for future developments."

    def _generate_action_required(self, item: PolicyItem, impact: PolicyImpact) -> str:
        """Generate recommended action."""
        if impact == PolicyImpact.CRITICAL:
            return "Review immediately. Assess compliance gap. Update processes before effective date."
        if impact == PolicyImpact.HIGH:
            return "Review within this week. Identify affected operations. Budget for compliance."
        if impact == PolicyImpact.MEDIUM:
            return "Review within this month. Add to compliance calendar."
        return "Awareness only. No immediate action needed."


# ════════════════════════════════════════════════════════════════════
# AlwaysOnPolicyMonitor — BiasharaAgent Integration
# ════════════════════════════════════════════════════════════════════


class AlwaysOnPolicyMonitor(BiasharaAgent):
    """
    Always-on policy monitoring agent for Angavu Intelligence.

    Lifecycle:
        - Runs background polling loop (inherited from BiasharaAgent)
        - PolicyRadar scans for new regulatory items
        - PolicyRanker classifies impact on SME sectors
        - Alerts emitted as AgentEvents through the event bus

    Subscribes to: compliance.check, compliance.violation
    Publishes: market.alert (regulatory), compliance.check

    Integrates with:
    - BiasharaAgent.observe → think → act → reflect lifecycle
    - ComplianceAgent (downstream compliance verification)
    - MetaAgent routing for policy-related queries
    """

    def __init__(
        self,
        live: bool = False,
        poll_interval: float = 3600.0,  # 1 hour
        top_n: int = 10,
    ):
        super().__init__(
            name="AlwaysOnPolicyMonitor",
            role="Continuous regulatory and policy surveillance",
            capabilities=[
                "policy_scanning",
                "regulatory_monitoring",
                "impact_classification",
                "compliance_alerting",
                "effective_date_tracking",
            ],
        )
        self._radar = PolicyRadar(live=live)
        self._ranker = PolicyRanker()
        self._top_n = top_n
        self._poll_interval = poll_interval
        self._brief_history: list[PolicyBrief] = []
        self._logger = logger.bind(agent="AlwaysOnPolicyMonitor")

    # ── BiasharaAgent lifecycle ─────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Handle incoming compliance-related events."""
        await super().observe(event)
        if event.event_type in (EventType.COMPLIANCE_CHECK, EventType.COMPLIANCE_VIOLATION):
            self._logger.info(
                "received_compliance_event",
                event_type=event.event_type.value,
                source=event.source,
            )

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Decide whether to run a policy scanning cycle.

        On timer triggers: run full scan → rank → alert pipeline.
        On compliance events: analyze for policy implications.
        """
        event = context.get("event", {})
        event_type = event.get("event_type", "")

        if event_type == EventType.COMPLIANCE_VIOLATION.value:
            return AgentDecision(
                action="analyze_compliance_violation",
                parameters={"violation_data": event.get("payload", {})},
                confidence=0.95,
                reasoning="Compliance violation detected — checking for related policy changes.",
            )

        return AgentDecision(
            action="run_policy_scan",
            parameters={"top_n": self._top_n},
            confidence=1.0,
            reasoning="Scheduled policy scan — check regulatory sources, rank by impact.",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the policy monitoring decision."""
        start = time.time()

        if decision.action == "analyze_compliance_violation":
            return await self._analyze_violation(decision.parameters)
        if decision.action == "run_policy_scan":
            return await self._run_policy_scan(decision.parameters)

        return AgentResult(
            success=False,
            error=f"Unknown action: {decision.action}",
            duration_ms=(time.time() - start) * 1000,
        )

    async def _run_policy_scan(self, params: dict) -> AgentResult:
        """Full scan → rank → alert pipeline."""
        start = time.time()
        try:
            # Scan for new policies
            policies = await self._radar.scan_policies()

            # Rank by impact
            ranked = self._ranker.rank_policies(policies)

            # Take top N
            top_policies = ranked[: self._top_n]

            # Build brief
            brief = self._render_brief(top_policies)
            self._brief_history.append(brief)
            if len(self._brief_history) > 50:
                self._brief_history = self._brief_history[-50:]

            # Emit events for high-impact policies
            events_to_publish = []
            for ranked_policy in top_policies:
                if ranked_policy.impact in (PolicyImpact.CRITICAL, PolicyImpact.HIGH):
                    events_to_publish.append(AgentEvent(
                        event_type=EventType.COMPLIANCE_CHECK,
                        source=self.name,
                        payload={
                            "policy_title": ranked_policy.item.title,
                            "domain": ranked_policy.item.domain.value,
                            "impact": ranked_policy.impact.value,
                            "impact_score": ranked_policy.impact_score,
                            "effective_date": ranked_policy.item.effective_date,
                            "sectors_affected": ranked_policy.item.sectors_affected,
                            "action_required": ranked_policy.action_required,
                            "source": ranked_policy.item.source,
                            "url": ranked_policy.item.url,
                        },
                    ))

                # Also emit market alert for trade/tax changes
                if ranked_policy.item.domain in (PolicyDomain.TAX, PolicyDomain.TRADE):
                    events_to_publish.append(AgentEvent(
                        event_type=EventType.MARKET_ALERT,
                        source=self.name,
                        payload={
                            "type": "policy_change",
                            "title": ranked_policy.item.title,
                            "domain": ranked_policy.item.domain.value,
                            "impact_score": ranked_policy.impact_score,
                            "effective_date": ranked_policy.item.effective_date,
                        },
                    ))

            duration_ms = (time.time() - start) * 1000
            self._logger.info(
                "policy_scan_complete",
                policies_scanned=len(policies),
                high_impact=len([r for r in ranked if r.impact in (PolicyImpact.CRITICAL, PolicyImpact.HIGH)]),
                events_emitted=len(events_to_publish),
                duration_ms=round(duration_ms, 1),
            )

            return AgentResult(
                success=True,
                data={
                    "brief": brief.to_dict(),
                    "policies_scanned": len(policies),
                    "events_emitted": len(events_to_publish),
                },
                duration_ms=duration_ms,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            self._logger.error("policy_scan_failed", error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    async def _analyze_violation(self, params: dict) -> AgentResult:
        """Analyze a compliance violation for policy context."""
        violation_data = params.get("violation_data", {})
        self.memory.remember({
            "type": "violation_received",
            "violation": violation_data,
        })
        return AgentResult(
            success=True,
            data={"analyzed": True, "violation": violation_data},
            duration_ms=0,
        )

    def _render_brief(self, policies: list[RankedPolicy]) -> PolicyBrief:
        """Render a policy intelligence brief."""
        import html as html_module

        impact_breakdown = {}
        for p in policies:
            key = p.impact.value
            impact_breakdown[key] = impact_breakdown.get(key, 0) + 1

        text_lines = [
            "Angavu Policy Intelligence Brief",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Policies scanned: {len(policies)}",
            "",
        ]
        for i, p in enumerate(policies, 1):
            text_lines.append(f"{i}. [{p.impact.value.upper()}] {p.item.title}")
            text_lines.append(f"   Domain: {p.item.domain.value} | Score: {p.impact_score}")
            text_lines.append(f"   Impact: {p.sme_relevance}")
            text_lines.append(f"   Action: {p.action_required}")
            if p.item.effective_date:
                text_lines.append(f"   Effective: {p.item.effective_date}")
            text_lines.append("")

        html_lines = [
            "<h2>Angavu Policy Intelligence Brief</h2>",
            f"<p><strong>Generated:</strong> {html_module.escape(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>",
            f"<p>Policies: {len(policies)}</p>",
            "<ol>",
        ]
        for p in policies:
            color = {
                "critical": "#dc3545",
                "high": "#fd7e14",
                "medium": "#ffc107",
                "low": "#28a745",
                "info": "#6c757d",
            }.get(p.impact.value, "#6c757d")
            html_lines.extend([
                "<li>",
                f'<span style="color:{color};font-weight:bold">[{p.impact.value.upper()}]</span> '
                f"<strong>{html_module.escape(p.item.title)}</strong>",
                f"<p>{html_module.escape(p.sme_relevance)}</p>",
                f"<p><em>Action:</em> {html_module.escape(p.action_required)}</p>",
                f"<small>Domain: {html_module.escape(p.item.domain.value)} | Score: {p.impact_score}"
                + (f" | Effective: {p.item.effective_date}" if p.item.effective_date else "")
                + "</small>",
                "</li>",
            ])
        html_lines.append("</ol>")

        next_actions = [
            "Review critical/high policies for compliance gaps.",
            "Notify affected business units of upcoming regulatory changes.",
            "Update compliance calendar with new effective dates.",
        ]

        return PolicyBrief(
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            watch_mode="live" if self._radar._live else "sample",
            policies=policies,
            summary_text="\n".join(text_lines),
            summary_html="\n".join(html_lines),
            next_actions=next_actions,
            impact_breakdown=impact_breakdown,
        )

    async def get_latest_brief(self) -> dict[str, Any] | None:
        """Return the most recent policy brief."""
        if self._brief_history:
            return self._brief_history[-1].to_dict()
        return None
