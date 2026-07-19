"""
Autonomous Orchestrator — Central coordination for all autonomous operations.

The orchestrator manages the lifecycle of autonomous agents, schedules
recurring tasks, routes events, and integrates with the existing
BiasharaAgent infrastructure (EventBus, AgentTracer, loops).

Key Responsibilities:
    - Agent lifecycle management (create, start, stop, restart)
    - Task scheduling (recurring autonomous tasks)
    - Event routing between autonomous agents and core agents
    - Health monitoring and automatic recovery
    - Integration with escalation and monitoring systems

Design:
    The orchestrator wraps the existing AgentFactory and EventBus,
    adding a scheduling layer and health-check loop on top.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import structlog

from app.agents.base import AgentEvent, BiasharaAgent
from app.agents.event_bus import EventBus
from app.agents.observability import AgentTracer
from app.autonomous.config import AgentConfig, AgentConfigManager
from app.autonomous.escalation import EscalationManager
from app.autonomous.monitoring import AgentMonitor, TaskRecord

logger = structlog.get_logger(__name__)


@dataclass
class ScheduledTask:
    """A recurring task definition."""
    name: str
    agent_name: str
    interval_seconds: int
    handler: Callable[..., Coroutine]
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent_name": self.agent_name,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "next_run_in": max(0, self.interval_seconds - (time.time() - self.last_run)),
        }


class AutonomousOrchestrator:
    """
    Central orchestrator for autonomous operations.

    Integrates with existing BiasharaAgent infrastructure and adds:
    - Autonomous agent lifecycle
    - Scheduled task execution
    - Health monitoring with auto-recovery
    - Escalation and monitoring wiring
    """

    def __init__(
        self,
        event_bus: EventBus,
        tracer: AgentTracer,
        escalation_manager: EscalationManager | None = None,
        monitor: AgentMonitor | None = None,
        config_manager: AgentConfigManager | None = None,
    ):
        self._event_bus = event_bus
        self._tracer = tracer
        self._escalation = escalation_manager or EscalationManager()
        self._monitor = monitor or AgentMonitor()
        self._config_manager = config_manager or AgentConfigManager()

        # Agent registry
        self._agents: dict[str, BiasharaAgent] = {}
        self._agent_configs: dict[str, AgentConfig] = {}

        # Scheduled tasks
        self._scheduled_tasks: dict[str, ScheduledTask] = {}

        # Background loops
        self._scheduler_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._running: bool = False

        # Integration hooks
        self._agent_infra: Any = None  # AgentInfrastructure reference

        self._logger = logger.bind(component="autonomous_orchestrator")

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the orchestrator and all autonomous agents."""
        if self._running:
            return

        self._running = True
        self._logger.info("orchestrator_starting")

        # Create and start autonomous agents
        await self._create_agents()

        # Start background loops
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self._health_task = asyncio.create_task(self._health_loop())

        self._logger.info(
            "orchestrator_started",
            agents=list(self._agents.keys()),
            scheduled_tasks=list(self._scheduled_tasks.keys()),
        )

    async def stop(self) -> None:
        """Stop the orchestrator and all autonomous agents gracefully."""
        self._running = False

        # Stop background loops
        for task in [self._scheduler_task, self._health_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop agents
        for agent in self._agents.values():
            try:
                await agent.stop()
            except Exception as exc:
                self._logger.warning("agent_stop_error", agent=agent.name, error=str(exc))

        self._logger.info("orchestrator_stopped")

    def set_agent_infrastructure(self, infra: Any) -> None:
        """Link to the main AgentFactory infrastructure for cross-wiring."""
        self._agent_infra = infra

    # ── Agent Management ────────────────────────────────────────────

    async def _create_agents(self) -> None:
        """Create and register all autonomous agents."""
        from app.autonomous.agents.content_agent import ContentAgent
        from app.autonomous.agents.operations_agent import OperationsAgent
        from app.autonomous.agents.sales_agent import SalesAgent

        agent_classes = [SalesAgent, ContentAgent, OperationsAgent]

        for cls in agent_classes:
            try:
                config = self._config_manager.load(cls.CONFIG_NAME)
                agent = cls(config=config)

                # Wire infrastructure
                agent.set_event_bus(self._event_bus)
                agent.set_tracer(self._tracer)
                agent.set_monitor(self._monitor)
                agent.set_escalation(self._escalation)

                # Subscribe to relevant events
                await self._event_bus.subscribe(agent, agent.SUBSCRIBED_EVENTS)

                # Start agent
                await agent.start()

                self._agents[agent.name] = agent
                self._agent_configs[agent.name] = config

                self._logger.info("autonomous_agent_created", agent=agent.name, role=config.role.value)
            except Exception as exc:
                self._logger.error("agent_creation_failed", agent_cls=cls.__name__, error=str(exc))

    async def restart_agent(self, agent_name: str) -> bool:
        """Restart a specific agent."""
        agent = self._agents.get(agent_name)
        if not agent:
            return False

        try:
            await agent.stop()
            config = self._config_manager.reload(agent_name)
            agent.set_event_bus(self._event_bus)
            agent.set_tracer(self._tracer)
            await agent.start()
            self._logger.info("agent_restarted", agent=agent_name)
            return True
        except Exception as exc:
            self._logger.error("agent_restart_failed", agent=agent_name, error=str(exc))
            return False

    # ── Task Scheduling ─────────────────────────────────────────────

    def register_scheduled_task(self, task: ScheduledTask) -> None:
        """Register a recurring task."""
        self._scheduled_tasks[task.name] = task
        self._logger.info(
            "scheduled_task_registered",
            task=task.name,
            agent=task.agent_name,
            interval=task.interval_seconds,
        )

    async def _scheduler_loop(self) -> None:
        """Background loop that executes scheduled tasks."""
        self._logger.debug("scheduler_loop_started")
        while self._running:
            try:
                now = time.time()
                for name, task in self._scheduled_tasks.items():
                    if not task.enabled:
                        continue
                    if now - task.last_run < task.interval_seconds:
                        continue

                    try:
                        task_start = time.time()
                        await task.handler()
                        task.last_run = time.time()
                        task.run_count += 1

                        self._logger.debug(
                            "scheduled_task_executed",
                            task=name,
                            duration_ms=(time.time() - task_start) * 1000,
                        )
                    except Exception as exc:
                        task.error_count += 1
                        self._logger.error(
                            "scheduled_task_failed",
                            task=name,
                            error=str(exc),
                        )

                        # Escalate after repeated failures
                        if task.error_count >= 3:
                            await self._escalation.escalate(
                                trigger_name="consecutive_errors",
                                agent_name=task.agent_name,
                                summary=f"Scheduled task '{name}' failed {task.error_count} times",
                                details={"error": str(exc), "task": name},
                            )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.warning("scheduler_loop_error", error=str(exc))

            await asyncio.sleep(5)  # Check every 5 seconds

    # ── Health Monitoring ───────────────────────────────────────────

    async def _health_loop(self) -> None:
        """Background health check for all autonomous agents."""
        self._logger.debug("health_loop_started")
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                for name, agent in self._agents.items():
                    health = agent.health_check()

                    if health.get("status") == "error":
                        self._logger.warning(
                            "agent_unhealthy",
                            agent=name,
                            health=health,
                        )
                        # Attempt auto-recovery
                        await self.restart_agent(name)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.warning("health_loop_error", error=str(exc))

    # ── Event Handling ──────────────────────────────────────────────

    async def handle_cross_agent_event(self, event: AgentEvent) -> None:
        """
        Route events between autonomous agents and core agents.

        Called by the EventBus when an autonomous agent publishes
        an event that needs to reach core agents or vice versa.
        """
        self._logger.debug(
            "cross_agent_event",
            event_type=event.event_type.value,
            source=event.source,
        )

        # Record for monitoring
        self._monitor.record_task(TaskRecord(
            task_id=event.event_id,
            agent_name=event.source,
            task_type=event.event_type.value,
            success=True,
            duration_ms=0,
        ))

    # ── Query API ───────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get orchestrator status for health endpoints."""
        return {
            "running": self._running,
            "agents": {
                name: agent.health_check()
                for name, agent in self._agents.items()
            },
            "scheduled_tasks": {
                name: task.to_dict()
                for name, task in self._scheduled_tasks.items()
            },
            "escalation_metrics": self._escalation.get_metrics(),
            "monitor_metrics": self._monitor.get_metrics(),
        }

    def get_agents(self) -> list[dict[str, Any]]:
        """Get list of all autonomous agents."""
        return [
            {
                "name": agent.name,
                "config": self._agent_configs.get(agent.name, AgentConfig(name=agent.name, role="operations")).to_dict(),
                "health": agent.health_check(),
            }
            for agent in self._agents.values()
        ]
