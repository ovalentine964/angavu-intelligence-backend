"""
Skill Registry — Central registry for all Angavu Intelligence skills.

Maps degree course units to executable AI skills, tracks usage,
and manages skill lifecycle (versioning, activation, metrics).

Each skill corresponds to a course unit from Valentine Owuor's
BSc Economics & Statistics (Masinde Muliro University, 42 units,
545,000+ words mapped to Angavu Intelligence products).
"""

from __future__ import annotations

from typing import Any

import structlog

from app.skills.base import BaseSkill, SkillResult, SkillStatus

logger = structlog.get_logger(__name__)


class SkillRegistry:
    """
    Central registry for all Angavu Intelligence skills.

    Responsibilities:
    - Register skills from degree units
    - Map skills to agents
    - Track skill usage and effectiveness
    - Version control for skills
    - Provide skill lookup for API and agents
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._agent_skills: dict[str, list[str]] = {}  # agent → [skill_names]
        self._logger = logger.bind(component="SkillRegistry")

    def register(self, skill: BaseSkill) -> None:
        """Register a skill in the registry."""
        self._skills[skill.name] = skill

        # Build reverse mapping: agent → skills
        for agent_name in skill.agent_bindings:
            if agent_name not in self._agent_skills:
                self._agent_skills[agent_name] = []
            if skill.name not in self._agent_skills[agent_name]:
                self._agent_skills[agent_name].append(skill.name)

        self._logger.info(
            "skill_registered",
            skill_name=skill.name,
            course_unit=skill.course_unit,
            agents=skill.agent_bindings,
        )

    def get(self, name: str) -> BaseSkill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered skills with metadata."""
        return [skill.get_info() for skill in self._skills.values()]

    def list_for_agent(self, agent_name: str) -> list[dict[str, Any]]:
        """List skills available to a specific agent."""
        skill_names = self._agent_skills.get(agent_name, [])
        return [
            self._skills[name].get_info()
            for name in skill_names
            if name in self._skills
        ]

    def get_skills_for_agent(self, agent_name: str) -> list[BaseSkill]:
        """Get skill instances for an agent."""
        skill_names = self._agent_skills.get(agent_name, [])
        return [
            self._skills[name]
            for name in skill_names
            if name in self._skills
        ]

    async def execute_skill(
        self,
        skill_name: str,
        action: str,
        **kwargs,
    ) -> SkillResult:
        """Execute a skill action by name."""
        skill = self._skills.get(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                skill_name=skill_name,
                error=f"Skill not found: {skill_name}",
            )

        if skill.status != SkillStatus.ACTIVE:
            return SkillResult(
                success=False,
                skill_name=skill_name,
                error=f"Skill is not active: {skill.status.value}",
            )

        return await skill.safe_execute(action=action, **kwargs)

    def get_metrics(self, skill_name: str | None = None) -> dict[str, Any]:
        """Get metrics for one or all skills."""
        if skill_name:
            skill = self._skills.get(skill_name)
            if not skill:
                return {"error": f"Skill not found: {skill_name}"}
            return skill.metrics.to_dict()

        return {
            name: skill.metrics.to_dict()
            for name, skill in self._skills.items()
        }

    def get_summary(self) -> dict[str, Any]:
        """Get registry summary statistics."""
        total_calls = sum(s.metrics.total_calls for s in self._skills.values())
        total_success = sum(s.metrics.successful_calls for s in self._skills.values())

        return {
            "total_skills": len(self._skills),
            "active_skills": sum(1 for s in self._skills.values() if s.status == SkillStatus.ACTIVE),
            "agent_mappings": len(self._agent_skills),
            "total_executions": total_calls,
            "total_successes": total_success,
            "overall_success_rate": round(total_success / max(total_calls, 1), 4),
            "skills": {
                name: {
                    "course_unit": skill.course_unit,
                    "status": skill.status.value,
                    "calls": skill.metrics.total_calls,
                    "success_rate": round(skill.metrics.success_rate, 4),
                }
                for name, skill in self._skills.items()
            },
            "agent_mappings_detail": {
                agent: skills for agent, skills in self._agent_skills.items()
            },
        }


# ── Singleton ───────────────────────────────────────────────────────

_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Get or create the singleton SkillRegistry."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _register_default_skills(_registry)
    return _registry


def _register_default_skills(registry: SkillRegistry) -> None:
    """Register all default skills from degree course units."""
    from app.skills.econometric_modeler import EconometricModeler
    from app.skills.microfinance_analyzer import MicrofinanceAnalyzer
    from app.skills.nonparametric_analyzer import NonparametricAnalyzer
    from app.skills.statistical_estimator import StatisticalEstimator
    from app.skills.time_series_forecaster import TimeSeriesForecasterSkill
    from app.skills.worker_segmenter import WorkerSegmenter

    skills = [
        MicrofinanceAnalyzer(),       # ECO 206
        TimeSeriesForecasterSkill(),  # STA 244
        StatisticalEstimator(),       # STA 341
        EconometricModeler(),         # ECO 424
        WorkerSegmenter(),            # STA 442
        NonparametricAnalyzer(),      # STA 444
    ]

    for skill in skills:
        registry.register(skill)

    logger.info(
        "default_skills_registered",
        count=len(skills),
        skills=[s.name for s in skills],
    )
