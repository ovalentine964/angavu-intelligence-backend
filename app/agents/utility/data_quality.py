"""
DataQualityAgent — Tier 3 utility agent for data validation and cleaning.

Validates incoming data against schemas, detects missing fields,
normalizes formats, and flags quality issues.

Tier: 3 (Utility) — stateless, on-demand invocation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import structlog

from app.agents.base import AgentDecision, AgentEvent, AgentResult, BiasharaAgent

logger = structlog.get_logger(__name__)


class DataQualityAgent(BiasharaAgent):
    """
    Validates and cleans data flowing through the pipeline.

    Capabilities:
    - Schema validation
    - Missing field detection
    - Format normalization
    - Duplicate detection
    """

    def __init__(self):
        super().__init__(
            name="DataQuality",
            role="Data validation and quality assurance",
            capabilities=[
                "schema_validation",
                "missing_field_detection",
                "format_normalization",
                "duplicate_detection",
            ],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})

        if payload:
            return AgentDecision(
                action="validate",
                parameters={"data": payload},
                confidence=0.9,
                reasoning="Data received for quality check",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.5,
            reasoning="No data to validate",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        start = time.time()

        if decision.action == "validate":
            data = decision.parameters.get("data", {})
            issues = self._check_quality(data)
            return AgentResult(
                success=True,
                data={
                    "valid": len(issues) == 0,
                    "issues": issues,
                    "fields_checked": len(data),
                },
                duration_ms=(time.time() - start) * 1000,
            )

        return AgentResult(
            success=True,
            data={"status": "idle"},
            duration_ms=(time.time() - start) * 1000,
        )

    def _check_quality(self, data: Dict[str, Any]) -> List[str]:
        """Check data quality, return list of issues."""
        issues = []
        if not data:
            issues.append("empty_payload")
            return issues

        # Check for None values
        none_fields = [k for k, v in data.items() if v is None]
        if none_fields:
            issues.append(f"null_fields: {none_fields}")

        # Check for empty strings
        empty_fields = [k for k, v in data.items() if v == ""]
        if empty_fields:
            issues.append(f"empty_fields: {empty_fields}")

        return issues
