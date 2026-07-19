"""
Base Skill — Abstract base class for all Angavu Intelligence skills.

Each skill corresponds to a course unit from the BSc Economics & Statistics
degree and provides executable intelligence capabilities.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SkillStatus(str, Enum):
    """Skill lifecycle states."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class SkillResult:
    """Standardized output from any skill execution."""
    success: bool
    skill_name: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "skill_name": self.skill_name,
            "data": self.data,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "confidence": round(self.confidence, 4),
            "metadata": self.metadata,
        }


@dataclass
class SkillMetrics:
    """Tracks skill usage and effectiveness over time."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    avg_confidence: float = 0.0
    last_called_at: float | None = None
    last_error: str | None = None

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls

    def record(self, result: SkillResult) -> None:
        """Record a skill execution result."""
        self.total_calls += 1
        if result.success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            self.last_error = result.error
        self.total_duration_ms += result.duration_ms
        # Running average confidence
        n = self.total_calls
        self.avg_confidence = (
            (self.avg_confidence * (n - 1) + result.confidence) / n
        )
        self.last_called_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "avg_confidence": round(self.avg_confidence, 4),
            "last_called_at": self.last_called_at,
            "last_error": self.last_error,
        }


class BaseSkill(ABC):
    """
    Abstract base class for all Angavu Intelligence skills.

    Each skill must define:
    - name: Unique identifier
    - course_unit: The university course unit it maps to
    - description: What the skill does
    - execute(): The main computation method
    """

    def __init__(
        self,
        name: str,
        course_unit: str,
        description: str,
        version: str = "1.0.0",
        agent_bindings: list[str] | None = None,
    ):
        self.name = name
        self.course_unit = course_unit
        self.description = description
        self.version = version
        self.agent_bindings = agent_bindings or []
        self.status = SkillStatus.ACTIVE
        self.metrics = SkillMetrics()
        self._logger = logger.bind(skill=name, course=course_unit)

    @abstractmethod
    async def execute(self, **kwargs) -> SkillResult:
        """
        Execute the skill with given parameters.

        Must be implemented by subclasses. Returns a SkillResult.
        """
        ...

    async def safe_execute(self, **kwargs) -> SkillResult:
        """
        Execute with error handling, timing, and metrics recording.
        """
        start = time.time()
        try:
            result = await self.execute(**kwargs)
            result.duration_ms = (time.time() - start) * 1000
            self.metrics.record(result)
            if result.success:
                self._logger.info(
                    "skill_executed",
                    duration_ms=round(result.duration_ms, 2),
                    confidence=result.confidence,
                )
            else:
                self._logger.warning(
                    "skill_failed",
                    error=result.error,
                    duration_ms=round(result.duration_ms, 2),
                )
            return result
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            result = SkillResult(
                success=False,
                skill_name=self.name,
                error=str(exc),
                duration_ms=duration_ms,
            )
            self.metrics.record(result)
            self._logger.exception("skill_exception", error=str(exc))
            return result

    def get_info(self) -> dict[str, Any]:
        """Return skill metadata for the registry."""
        return {
            "name": self.name,
            "course_unit": self.course_unit,
            "description": self.description,
            "version": self.version,
            "status": self.status.value,
            "agent_bindings": self.agent_bindings,
            "metrics": self.metrics.to_dict(),
        }
