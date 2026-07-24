"""
Skill Generator — Generates reusable skills from interaction traces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class SkillCategory(str, Enum):
    """Categories of generated skills."""
    FINANCIAL = "financial"
    CREDIT = "credit"
    MARKET = "market"
    OPERATIONS = "operations"
    COMPLIANCE = "compliance"
    GENERAL = "general"


@dataclass
class GeneratedSkill:
    """A skill generated from interaction patterns."""
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: SkillCategory = SkillCategory.GENERAL
    name: str = ""
    description: str = ""
    procedure: list[str] = field(default_factory=list)
    pitfalls: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    confidence: float = 0.5
    usage_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillGenerator:
    """
    Generates skills from successful interaction traces.

    Monitors complex interactions, identifies reusable patterns,
    and generates skill objects that can be applied to future
    similar situations.
    """

    def __init__(self):
        self._traces: dict[str, dict] = {}
        self._skills: dict[str, GeneratedSkill] = {}
        self._min_complexity = 3

    def start_trace(self, context: dict = None) -> str:
        """Start a new interaction trace."""
        trace_id = str(uuid.uuid4())
        self._traces[trace_id] = {
            "context": context or {},
            "started_at": __import__("time").time(),
            "events": [],
        }
        return trace_id

    def end_trace(
        self,
        trace_id: str,
        response: str = "",
        outcome: str = "success",
        lessons: list[str] | None = None,
    ) -> Optional[GeneratedSkill]:
        """
        End a trace and potentially generate a skill.

        Returns a GeneratedSkill if the trace was complex and successful.
        """
        trace = self._traces.pop(trace_id, None)
        if not trace:
            return None

        # Only generate skills from successful, complex interactions
        if outcome != "success":
            return None

        context = trace.get("context", {})
        complexity = len(context.get("steps", []))

        if complexity < self._min_complexity and not lessons:
            return None

        # Determine category
        domain = context.get("domain", "general")
        category = SkillCategory.GENERAL
        for cat in SkillCategory:
            if cat.value in domain.lower():
                category = cat
                break

        skill = GeneratedSkill(
            category=category,
            name=context.get("task", "unnamed_skill"),
            description=f"Generated from trace {trace_id}",
            procedure=context.get("steps", []),
            pitfalls=lessons or [],
            verification=[f"Verify outcome matches: {outcome}"],
            confidence=0.6,
        )

        self._skills[skill.skill_id] = skill
        logger.info("skill_generated", skill_id=skill.skill_id, category=category.value)
        return skill

    def get_skill(self, skill_id: str) -> Optional[GeneratedSkill]:
        """Get a skill by ID."""
        return self._skills.get(skill_id)

    def list_skills(self, category: Optional[SkillCategory] = None) -> list[GeneratedSkill]:
        """List all skills, optionally filtered by category."""
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return skills
