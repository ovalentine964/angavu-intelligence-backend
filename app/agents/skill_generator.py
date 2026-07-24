"""
Skill Generator — Closed-loop skill creation and management.

Implements the Hermes skill generation pattern:
- Traces capture task execution steps
- Successful traces are converted into reusable skills
- Skills are searchable, versioned, and track usage metrics
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillCategory(str, Enum):
    """Categories of generated skills."""
    TRANSACTION = "transaction"
    MARKET_ANALYSIS = "market_analysis"
    CREDIT_SCORING = "credit_scoring"
    CUSTOMER_SERVICE = "customer_service"
    INVENTORY = "inventory"
    PRICING = "pricing"
    REPORTING = "reporting"
    GENERAL = "general"


@dataclass
class GeneratedSkill:
    """A skill generated from successful task execution."""
    skill_id: str
    title: str
    description: str
    category: SkillCategory
    procedure: str  # Step-by-step procedure in markdown
    pitfalls: str = ""  # Known pitfalls and how to avoid them
    verification: str = ""  # How to verify the skill worked
    content: str = ""  # Full skill content
    confidence: float = 0.5
    complexity: str = "medium"  # low, medium, high
    usage_count: int = 0
    success_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float | None = None
    version: int = 1

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.usage_count, 1)


@dataclass
class ExecutionTrace:
    """A trace of task execution steps."""
    trace_id: str
    worker_id: str
    query: str
    session_id: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    outcome: str | None = None


class SkillGenerator:
    """
    Generates and manages skills from task execution traces.

    When a task completes successfully, the execution trace
    is analyzed and converted into a reusable skill.
    """

    def __init__(self, min_steps_for_skill: int = 3, min_confidence: float = 0.6):
        self._skills: dict[str, GeneratedSkill] = {}
        self._traces: dict[str, ExecutionTrace] = {}
        self._min_steps = min_steps_for_skill
        self._min_confidence = min_confidence
        self._total_generated = 0
        self._total_searches = 0

    def search_skills(self, query: str, limit: int = 10) -> list[GeneratedSkill]:
        """Search skills by relevance to a query."""
        self._total_searches += 1
        query_lower = query.lower()
        scored: list[tuple[float, GeneratedSkill]] = []

        for skill in self._skills.values():
            # Simple keyword relevance scoring
            score = 0.0
            if query_lower in skill.title.lower():
                score += 0.5
            if query_lower in skill.description.lower():
                score += 0.3
            if query_lower in skill.content.lower():
                score += 0.2
            # Boost by confidence and usage
            score *= skill.confidence
            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in scored[:limit]]

    def start_trace(self, worker_id: str, query: str, session_id: str) -> str:
        """Start a new execution trace."""
        trace_id = str(uuid.uuid4())
        self._traces[trace_id] = ExecutionTrace(
            trace_id=trace_id,
            worker_id=worker_id,
            query=query,
            session_id=session_id,
        )
        return trace_id

    def record_step(
        self,
        trace_id: str,
        step_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a step in an execution trace."""
        trace = self._traces.get(trace_id)
        if trace:
            trace.steps.append({
                "step_type": step_type,
                "content": content,
                "metadata": metadata or {},
                "timestamp": time.time(),
            })

    def end_trace(
        self,
        trace_id: str,
        outcome: str = "success",
        feedback: str | None = None,
    ) -> GeneratedSkill | None:
        """Complete a trace and potentially generate a skill."""
        trace = self._traces.get(trace_id)
        if not trace:
            return None

        trace.completed_at = time.time()
        trace.outcome = outcome

        # Only generate skills from successful traces with enough steps
        if outcome != "success" or len(trace.steps) < self._min_steps:
            return None

        # Generate skill from trace
        skill_id = str(uuid.uuid4())
        skill = GeneratedSkill(
            skill_id=skill_id,
            title=f"Skill from: {trace.query[:60]}",
            description=f"Auto-generated skill from successful execution by {trace.worker_id}",
            category=self._categorize_query(trace.query),
            procedure=self._extract_procedure(trace.steps),
            pitfalls=self._extract_pitfalls(trace.steps),
            verification=self._extract_verification(trace.steps),
            confidence=self._calculate_confidence(trace),
            complexity="medium" if len(trace.steps) < 10 else "high",
        )
        skill.content = f"# {skill.title}\n\n{skill.description}\n\n## Procedure\n{skill.procedure}"

        self._skills[skill_id] = skill
        self._total_generated += 1

        return skill

    def record_skill_usage(
        self,
        skill_id: str,
        worker_id: str,
        success: bool,
    ) -> None:
        """Record that a skill was used."""
        skill = self._skills.get(skill_id)
        if skill:
            skill.usage_count += 1
            if success:
                skill.success_count += 1
            skill.last_used = time.time()

    def get_skill(self, skill_id: str) -> GeneratedSkill | None:
        """Get a skill by ID."""
        return self._skills.get(skill_id)

    def get_stats(self) -> dict[str, Any]:
        """Get skill generator statistics."""
        return {
            "total_skills": len(self._skills),
            "total_generated": self._total_generated,
            "total_searches": self._total_searches,
            "active_traces": len(self._traces),
            "categories": {
                cat.value: sum(1 for s in self._skills.values() if s.category == cat)
                for cat in SkillCategory
            },
        }

    def _categorize_query(self, query: str) -> SkillCategory:
        """Categorize a query into a skill category."""
        q = query.lower()
        if any(w in q for w in ["transaction", "payment", "mpesa", "sale"]):
            return SkillCategory.TRANSACTION
        if any(w in q for w in ["market", "price", "demand", "supply"]):
            return SkillCategory.MARKET_ANALYSIS
        if any(w in q for w in ["credit", "loan", "score", "repay"]):
            return SkillCategory.CREDIT_SCORING
        if any(w in q for w in ["customer", "client", "service"]):
            return SkillCategory.CUSTOMER_SERVICE
        if any(w in q for w in ["stock", "inventory", "order"]):
            return SkillCategory.INVENTORY
        if any(w in q for w in ["price", "cost", "margin"]):
            return SkillCategory.PRICING
        if any(w in q for w in ["report", "summary", "analysis"]):
            return SkillCategory.REPORTING
        return SkillCategory.GENERAL

    def _extract_procedure(self, steps: list[dict[str, Any]]) -> str:
        """Extract a procedure from execution steps."""
        procedure_parts = []
        for i, step in enumerate(steps, 1):
            content = step.get("content", "")
            step_type = step.get("step_type", "action")
            procedure_parts.append(f"{i}. [{step_type}] {content}")
        return "\n".join(procedure_parts)

    def _extract_pitfalls(self, steps: list[dict[str, Any]]) -> str:
        """Extract pitfalls from execution steps."""
        pitfalls = []
        for step in steps:
            if step.get("step_type") in ("error", "retry", "fallback"):
                pitfalls.append(f"- {step.get('content', 'Unknown issue')}")
        return "\n".join(pitfalls) if pitfalls else "None identified"

    def _extract_verification(self, steps: list[dict[str, Any]]) -> str:
        """Extract verification steps from execution."""
        for step in reversed(steps):
            if step.get("step_type") == "verification":
                return step.get("content", "")
        return "Verify output matches expected result"

    def _calculate_confidence(self, trace: ExecutionTrace) -> float:
        """Calculate confidence score for a generated skill."""
        base = 0.5
        # More steps = higher confidence (up to a point)
        step_bonus = min(len(trace.steps) * 0.05, 0.3)
        # No errors = higher confidence
        error_steps = sum(1 for s in trace.steps if s.get("step_type") in ("error", "retry"))
        error_penalty = error_steps * 0.1
        return max(0.1, min(1.0, base + step_bonus - error_penalty))
