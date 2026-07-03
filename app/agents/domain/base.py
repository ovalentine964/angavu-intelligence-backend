"""
Base Domain Agent — Shared infrastructure for Tier 2 domain agents.

Each domain agent specializes in one industry vertical but shares
the same observe → think → act → reflect lifecycle.
"""

from __future__ import annotations

import time
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


class DomainAgent(BiasharaAgent):
    """
    Base class for Tier 2 domain-specific agents.

    Subclasses must define DOMAIN_NAME and DOMAIN_KEYWORDS.
    """

    DOMAIN_NAME: str = "generic"
    DOMAIN_KEYWORDS: List[str] = []

    def __init__(
        self,
        name: str,
        capabilities: List[str],
    ):
        super().__init__(
            name=name,
            role=f"Domain agent — {self.DOMAIN_NAME}",
            capabilities=capabilities,
        )
        self._domain_logger = logger.bind(domain=self.DOMAIN_NAME, agent=name)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")
        payload = event_data.get("payload", {})

        if event_type in (
            EventType.DOMAIN_ANALYSIS_REQUESTED.value,
            EventType.INTELLIGENCE_REQUESTED.value,
        ):
            domain_match = self._matches_domain(payload)
            if domain_match:
                return AgentDecision(
                    action="analyze_domain",
                    parameters={"payload": payload, "match_reason": domain_match},
                    confidence=0.8,
                    reasoning=f"Request matches {self.DOMAIN_NAME} domain: {domain_match}",
                )

        if event_type == EventType.TRANSACTION_PROCESSED.value:
            if self._matches_domain(payload):
                return AgentDecision(
                    action="process_transaction",
                    parameters={"payload": payload},
                    confidence=0.7,
                    reasoning=f"Transaction relevant to {self.DOMAIN_NAME}",
                )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.3,
            reasoning=f"No {self.DOMAIN_NAME} signal in event",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        action = decision.action

        try:
            if action == "analyze_domain":
                result = self._analyze(decision.parameters.get("payload", {}))
            elif action == "process_transaction":
                result = self._process_transaction(decision.parameters.get("payload", {}))
            elif action == "idle":
                result = {"status": "idle", "domain": self.DOMAIN_NAME}
            else:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )

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

    def _matches_domain(self, payload: Dict[str, Any]) -> Optional[str]:
        """Check if payload matches this domain. Returns match reason or None."""
        text = str(payload).lower()
        for kw in self.DOMAIN_KEYWORDS:
            if kw.lower() in text:
                return kw
        sector = payload.get("sector", "").lower()
        if self.DOMAIN_NAME.lower() in sector:
            return f"sector={sector}"
        return None

    def _analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze domain-specific data. Override in subclasses."""
        return {
            "domain": self.DOMAIN_NAME,
            "analysis": "basic",
            "signals": len(payload),
        }

    def _process_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process a domain-relevant transaction. Override in subclasses."""
        return {
            "domain": self.DOMAIN_NAME,
            "processed": True,
        }
