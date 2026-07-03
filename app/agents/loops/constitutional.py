"""
Constitutional AI — Principle-based self-correction.

Before delivering output, the agent critiques itself against
a set of principles (the constitution). If violations are found,
the output is revised to comply.

Constitution for Biashara Intelligence:
    - Privacy:    Never expose individual transaction details
    - Accuracy:   Never present uncertain data as fact
    - Fairness:   Credit scores must not discriminate
    - Safety:     Flag potentially harmful recommendations
    - Business:   Reports must be actionable

Compliance flow:
    generate -> check principles -> violations? -> revise -> re-check -> deliver
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import structlog

from app.agents.base import AgentEvent, AgentResult
from app.agents.loops.core import Critique, ReflexionAgent

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Structures
# ════════════════════════════════════════════════════════════════════


@dataclass
class Principle:
    """A principle in the agent's constitution."""
    principle_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    description: str = ""
    category: str = ""            # "safety", "privacy", "accuracy", "fairness", "business"
    severity: str = "high"        # "low", "medium", "high", "critical"
    enabled: bool = True
    check_fn: Optional[Callable[[str], Optional[str]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
            "enabled": self.enabled,
        }


@dataclass
class ComplianceResult:
    """Result of checking output against a single principle."""
    principle_id: str = ""
    principle_name: str = ""
    compliant: bool = True
    violation_detail: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "principle_name": self.principle_name,
            "compliant": self.compliant,
            "violation_detail": self.violation_detail,
            "suggested_fix": self.suggested_fix,
        }


# ════════════════════════════════════════════════════════════════════
# Built-in check functions
# ════════════════════════════════════════════════════════════════════


def _check_privacy(output_str: str) -> Optional[str]:
    """Check for potential PII exposure."""
    pii_patterns = ["phone", "mpesa id", "national id", "passport", "ssn"]
    for pattern in pii_patterns:
        if pattern in output_str:
            return f"Output may contain personal identifier: '{pattern}'"
    return None


def _check_accuracy(output_str: str) -> Optional[str]:
    """Check for absolute claims without qualification."""
    absolute_words = ["definitely", "certainly", "guaranteed", "always", "never"]
    for word in absolute_words:
        if word in output_str:
            return f"Output contains absolute claim '{word}' without qualification"
    return None


def _check_fairness(output_str: str) -> Optional[str]:
    """Check for potentially discriminatory factors."""
    discriminatory = ["gender", "tribe", "ethnic", "race", "religion"]
    for factor in discriminatory:
        if factor in output_str:
            return f"Output references potentially discriminatory factor: '{factor}'"
    return None


def _check_safety(output_str: str) -> Optional[str]:
    """Check for potentially harmful recommendations."""
    harmful = ["overtrade", "leverage all", "invest everything", "ignore risk"]
    for pattern in harmful:
        if pattern in output_str:
            return f"Output contains potentially harmful recommendation: '{pattern}'"
    return None


def _check_actionability(output_str: str) -> Optional[str]:
    """Check that output includes actionable recommendations."""
    action_words = ["recommend", "suggest", "should", "next step", "action"]
    if len(output_str) > 100 and not any(w in output_str for w in action_words):
        return "Output lacks actionable recommendations"
    return None


def create_biashara_constitution() -> List[Principle]:
    """Create the default Biashara Intelligence constitution."""
    return [
        Principle(
            principle_id="privacy_1",
            name="Individual Privacy",
            description="Never expose individual transaction details or personal information",
            category="privacy",
            severity="critical",
            check_fn=_check_privacy,
        ),
        Principle(
            principle_id="accuracy_1",
            name="Accuracy Over Confidence",
            description="Never present uncertain data as fact. Always include confidence levels.",
            category="accuracy",
            severity="high",
            check_fn=_check_accuracy,
        ),
        Principle(
            principle_id="fairness_1",
            name="Non-Discriminatory Scoring",
            description="Credit scores must not discriminate based on gender, location, or transaction volume alone",
            category="fairness",
            severity="critical",
            check_fn=_check_fairness,
        ),
        Principle(
            principle_id="safety_1",
            name="Market Safety",
            description="Flag potentially harmful market recommendations",
            category="safety",
            severity="high",
            check_fn=_check_safety,
        ),
        Principle(
            principle_id="business_1",
            name="Actionable Intelligence",
            description="Reports must include specific, actionable recommendations",
            category="business",
            severity="medium",
            check_fn=_check_actionability,
        ),
    ]


# ════════════════════════════════════════════════════════════════════
# Severity penalties
# ════════════════════════════════════════════════════════════════════

SEVERITY_PENALTY: Dict[str, float] = {
    "low": 0.05,
    "medium": 0.10,
    "high": 0.20,
    "critical": 0.50,
}


# ════════════════════════════════════════════════════════════════════
# Constitutional Agent
# ════════════════════════════════════════════════════════════════════


class ConstitutionalAgent(ReflexionAgent):
    """
    Agent with Constitutional AI self-correction.

    Extends ReflexionAgent to add principle compliance checking
    in the critique phase. Before delivering output, the agent
    checks it against the constitution and revises if needed.

    Composition with Reflexion:
        execute -> constitutional critique -> (revise -> execute -> critique)* -> accept
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        principles: Optional[List[Principle]] = None,
        **kwargs: Any,
    ):
        super().__init__(name, role, capabilities, **kwargs)
        self._principles = principles or create_biashara_constitution()
        self._violation_history: List[ComplianceResult] = []
        self._compliance_checks: int = 0
        self._logger = logger.bind(agent=name, loop="constitutional")

    # ── Principle management ───────────────────────────────────────

    def add_principle(self, principle: Principle) -> None:
        """Add a principle to the constitution."""
        self._principles.append(principle)
        self._logger.info(
            "principle_added",
            principle_id=principle.principle_id, name=principle.name,
        )

    def remove_principle(self, principle_id: str) -> bool:
        """Remove a principle by ID."""
        for i, p in enumerate(self._principles):
            if p.principle_id == principle_id:
                self._principles.pop(i)
                return True
        return False

    def get_principles(self) -> List[Dict[str, Any]]:
        """Get all principles in the constitution."""
        return [p.to_dict() for p in self._principles]

    # ── Constitutional critique ────────────────────────────────────

    async def _critique(self, event: AgentEvent, result: AgentResult) -> Critique:
        """
        Critique output against constitution + Reflexion heuristics.
        """
        base_critique = await super()._critique(event, result)

        if result.success and result.data:
            compliance_results = self._check_compliance(result.data)
            self._compliance_checks += 1

            violations = [r for r in compliance_results if not r.compliant]

            if violations:
                self._violation_history.extend(violations)

                for violation in violations:
                    principle = self._get_principle(violation.principle_id)
                    if principle:
                        penalty = SEVERITY_PENALTY.get(principle.severity, 0.1)
                        base_critique.score -= penalty
                        base_critique.issues.append(
                            f"Constitutional [{principle.category}]: {violation.violation_detail}"
                        )
                        base_critique.suggestions.append(violation.suggested_fix)

                base_critique.should_retry = True
                base_critique.revision_plan = (
                    f"Fix {len(violations)} constitutional violation(s): "
                    + "; ".join(v.violation_detail for v in violations)
                )

                self._logger.warning(
                    "constitutional_violations",
                    count=len(violations),
                    violations=[v.violation_detail for v in violations],
                )

        base_critique.score = max(0.0, min(1.0, base_critique.score))
        return base_critique

    def _check_compliance(self, output: Any) -> List[ComplianceResult]:
        """Check output against all constitutional principles."""
        results: List[ComplianceResult] = []
        output_str = str(output).lower()

        for principle in self._principles:
            if not principle.enabled:
                continue

            violation: Optional[str] = None

            if principle.check_fn:
                try:
                    violation = principle.check_fn(output_str)
                except Exception as exc:
                    self._logger.warning(
                        "check_fn_error",
                        principle=principle.name, error=str(exc),
                    )
            else:
                violation = self._builtin_check(principle, output_str)

            results.append(
                ComplianceResult(
                    principle_id=principle.principle_id,
                    principle_name=principle.name,
                    compliant=violation is None,
                    violation_detail=violation or "",
                    suggested_fix=f"Address: {violation}" if violation else "",
                )
            )

        return results

    def _builtin_check(self, principle: Principle, output_str: str) -> Optional[str]:
        """Built-in keyword checks by principle category."""
        checks = {
            "privacy": _check_privacy,
            "accuracy": _check_accuracy,
            "fairness": _check_fairness,
            "safety": _check_safety,
            "business": _check_actionability,
        }
        fn = checks.get(principle.category)
        return fn(output_str) if fn else None

    def _get_principle(self, principle_id: str) -> Optional[Principle]:
        """Look up a principle by ID."""
        for p in self._principles:
            if p.principle_id == principle_id:
                return p
        return None

    # ── Introspection ──────────────────────────────────────────────

    def get_violation_history(self, last_n: int = 20) -> List[Dict[str, Any]]:
        """Get recent constitutional violations."""
        return [v.to_dict() for v in self._violation_history[-last_n:]]

    def get_compliance_stats(self) -> Dict[str, Any]:
        """Get compliance statistics."""
        by_category: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}

        for v in self._violation_history:
            principle = self._get_principle(v.principle_id)
            if principle:
                by_category[principle.category] = by_category.get(principle.category, 0) + 1
                by_severity[principle.severity] = by_severity.get(principle.severity, 0) + 1

        return {
            "total_compliance_checks": self._compliance_checks,
            "total_violations": len(self._violation_history),
            "violations_by_category": by_category,
            "violations_by_severity": by_severity,
            "principles_count": len(self._principles),
            "enabled_principles": sum(1 for p in self._principles if p.enabled),
        }
