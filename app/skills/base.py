"""Base skill classes for Angavu Intelligence."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SkillStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    DEPRECATED = "deprecated"


@dataclass
class SkillMetrics:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0

    @property
    def success_rate(self) -> float:
        return self.successful_calls / max(self.total_calls, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": self.success_rate,
        }


@dataclass
class SkillResult:
    success: bool
    skill_name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSkill:
    """Base class for all Angavu Intelligence skills."""

    name: str = "base_skill"
    description: str = ""
    course_unit: str = ""
    version: str = "1.0.0"
    status: SkillStatus = SkillStatus.ACTIVE

    def __init__(self) -> None:
        self.metrics = SkillMetrics()

    async def safe_execute(self, action: str, **kwargs: Any) -> SkillResult:
        """Execute a skill action with error handling and metrics."""
        self.metrics.total_calls += 1
        try:
            result = await self.execute(action=action, **kwargs)
            self.metrics.successful_calls += 1
            return result
        except Exception as exc:
            self.metrics.failed_calls += 1
            logger.error("skill_execution_failed", skill=self.name, error=str(exc))
            return SkillResult(
                success=False,
                skill_name=self.name,
                error=str(exc),
            )

    async def execute(self, action: str, **kwargs: Any) -> SkillResult:
        """Override in subclasses to implement skill logic."""
        return SkillResult(
            success=False,
            skill_name=self.name,
            error="Not implemented",
        )
