"""
DelegationProtocol — Task delegation with timeout and result collection.

Higher-level protocol for delegating tasks to sub-agents.
Used by Tier 1 agents to invoke Tier 2/3 agents and collect results.

Pattern:
    Orchestrator ──subtask──▶ Agent ──result──▶ Orchestrator
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import AgentEvent, AgentResult, BiasharaAgent, EventType

logger = structlog.get_logger(__name__)


@dataclass
class DelegationTask:
    """A task delegated from one agent to another."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    delegator: str = ""          # agent that delegated
    delegatee: str = ""          # agent that executes
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    priority: int = 5
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[AgentResult] = None
    status: str = "pending"      # pending | running | completed | failed | timeout

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "delegator": self.delegator,
            "delegatee": self.delegatee,
            "action": self.action,
            "status": self.status,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": (
                (self.completed_at - self.started_at) * 1000
                if self.started_at and self.completed_at else None
            ),
            "success": self.result.success if self.result else None,
        }


class DelegationProtocol:
    """
    Manages task delegation between agents.

    Features:
    - Delegate tasks to specific agents with timeout
    - Parallel delegation to multiple agents
    - Result collection and aggregation
    - Delegation history for observability
    """

    def __init__(self, event_bus: Optional[Any] = None):
        self._event_bus = event_bus
        self._active_delegations: Dict[str, DelegationTask] = {}
        self._history: List[DelegationTask] = []
        self._logger = logger.bind(component="delegation_protocol")

    async def delegate(
        self,
        delegator: BiasharaAgent,
        delegatee: BiasharaAgent,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = 30.0,
    ) -> AgentResult:
        """
        Delegate a task to a specific agent and wait for the result.

        Args:
            delegator: The agent delegating the task
            delegatee: The agent to execute the task
            action: The action to perform
            parameters: Task parameters
            timeout_seconds: Maximum wait time

        Returns:
            AgentResult from the delegatee
        """
        task = DelegationTask(
            delegator=delegator.name,
            delegatee=delegatee.name,
            action=action,
            parameters=parameters or {},
            timeout_seconds=timeout_seconds,
        )

        self._active_delegations[task.task_id] = task
        task.started_at = time.time()
        task.status = "running"

        # Publish delegation event
        if self._event_bus:
            await self._event_bus.publish(AgentEvent(
                event_type=EventType.AGENT_STARTED,
                source=delegator.name,
                payload={
                    "delegation_task_id": task.task_id,
                    "delegatee": delegatee.name,
                    "action": action,
                },
            ))

        try:
            # Use the delegate_to method on BiasharaAgent
            result = await delegator.delegate_to(
                target_agent=delegatee,
                action=action,
                parameters=parameters,
                timeout_seconds=timeout_seconds,
            )

            task.completed_at = time.time()
            task.result = result
            task.status = "completed" if result.success else "failed"

            self._logger.info(
                "delegation_completed",
                task_id=task.task_id,
                delegator=delegator.name,
                delegatee=delegatee.name,
                success=result.success,
                duration_ms=result.duration_ms,
            )

        except asyncio.TimeoutError:
            task.completed_at = time.time()
            task.status = "timeout"
            result = AgentResult(
                success=False,
                error=f"Delegation to {delegatee.name} timed out after {timeout_seconds}s",
                duration_ms=timeout_seconds * 1000,
            )
            task.result = result

            self._logger.warning(
                "delegation_timeout",
                task_id=task.task_id,
                delegatee=delegatee.name,
                timeout=timeout_seconds,
            )

        except Exception as exc:
            task.completed_at = time.time()
            task.status = "failed"
            result = AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - task.started_at) * 1000,
            )
            task.result = result

            self._logger.error(
                "delegation_error",
                task_id=task.task_id,
                delegatee=delegatee.name,
                error=str(exc),
            )

        finally:
            self._active_delegations.pop(task.task_id, None)
            self._history.append(task)
            if len(self._history) > 500:
                self._history = self._history[-250:]

        return result

    async def delegate_parallel(
        self,
        delegator: BiasharaAgent,
        tasks: List[Dict[str, Any]],
        timeout_seconds: float = 30.0,
    ) -> List[AgentResult]:
        """
        Delegate multiple tasks in parallel.

        Args:
            delegator: The agent delegating
            tasks: List of {"agent": BiasharaAgent, "action": str, "parameters": dict}
            timeout_seconds: Maximum wait time for all tasks

        Returns:
            List of AgentResults in the same order as tasks
        """
        coroutines = [
            self.delegate(
                delegator=delegator,
                delegatee=task["agent"],
                action=task["action"],
                parameters=task.get("parameters", {}),
                timeout_seconds=timeout_seconds,
            )
            for task in tasks
        ]

        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Convert exceptions to AgentResult
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append(AgentResult(
                    success=False,
                    error=str(r),
                ))
            else:
                final_results.append(r)

        return final_results

    async def delegate_to_best(
        self,
        delegator: BiasharaAgent,
        candidates: List[BiasharaAgent],
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = 30.0,
    ) -> AgentResult:
        """
        Delegate to the first successful agent from a list of candidates.

        Tries each candidate in order. If one fails, tries the next.
        """
        last_error = None
        for candidate in candidates:
            result = await self.delegate(
                delegator=delegator,
                delegatee=candidate,
                action=action,
                parameters=parameters,
                timeout_seconds=timeout_seconds,
            )
            if result.success:
                return result
            last_error = result.error

        return AgentResult(
            success=False,
            error=f"All {len(candidates)} candidates failed. Last error: {last_error}",
        )

    def get_active(self) -> List[Dict[str, Any]]:
        """Return currently active delegations."""
        return [t.to_dict() for t in self._active_delegations.values()]

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return delegation history."""
        return [t.to_dict() for t in self._history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Return delegation protocol statistics."""
        total = len(self._history)
        successful = sum(1 for t in self._history if t.status == "completed" and t.result and t.result.success)
        return {
            "total_delegations": total,
            "successful": successful,
            "success_rate": round(successful / max(total, 1), 3),
            "active_count": len(self._active_delegations),
            "timeout_count": sum(1 for t in self._history if t.status == "timeout"),
        }
