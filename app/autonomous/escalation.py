"""
Escalation System — Clear triggers and SLAs for human intervention.

The escalation system defines when autonomous agents should hand off
decisions to the human founder (Valentine). This ensures the human
stays in the loop for high-stakes decisions while agents handle
routine operations independently.

Priority Levels:
    P1 — Critical: immediate human attention (financial loss, security)
    P2 — High: respond within 1 hour (customer complaints, failed payments)
    P3 — Medium: respond within 4 hours (content approval, partnership inquiries)
    P4 — Low: respond within 24 hours (optimization suggestions, reports)

Escalation Channels:
    Telegram → real-time notifications (P1, P2)
    Email → detailed reports (P3, P4)
    Dashboard → always-visible status

Target: <5% escalation rate by month 3 of operation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class Priority(IntEnum):
    """Escalation priority levels with SLA definitions."""
    P1_CRITICAL = 1
    P2_HIGH = 2
    P3_MEDIUM = 3
    P4_LOW = 4


@dataclass
class SLA:
    """Service Level Agreement for a priority level."""
    priority: Priority
    response_time_seconds: int      # Max time to acknowledge
    resolution_time_seconds: int    # Max time to resolve
    channels: List[str]             # Notification channels
    auto_escalate_seconds: int = 0  # Auto-escalate if no response (0 = disabled)

    @property
    def response_time_label(self) -> str:
        seconds = self.response_time_seconds
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        return f"{seconds // 3600}h"


# Default SLAs
DEFAULT_SLAS: Dict[Priority, SLA] = {
    Priority.P1_CRITICAL: SLA(
        priority=Priority.P1_CRITICAL,
        response_time_seconds=300,       # 5 minutes
        resolution_time_seconds=3600,    # 1 hour
        channels=["telegram", "email", "sms"],
        auto_escalate_seconds=600,
    ),
    Priority.P2_HIGH: SLA(
        priority=Priority.P2_HIGH,
        response_time_seconds=3600,      # 1 hour
        resolution_time_seconds=14400,   # 4 hours
        channels=["telegram", "email"],
        auto_escalate_seconds=7200,
    ),
    Priority.P3_MEDIUM: SLA(
        priority=Priority.P3_MEDIUM,
        response_time_seconds=14400,     # 4 hours
        resolution_time_seconds=86400,   # 24 hours
        channels=["email", "dashboard"],
    ),
    Priority.P4_LOW: SLA(
        priority=Priority.P4_LOW,
        response_time_seconds=86400,     # 24 hours
        resolution_time_seconds=259200,  # 3 days
        channels=["dashboard"],
    ),
}


@dataclass
class EscalationTrigger:
    """Defines when an agent should escalate to human."""
    name: str
    description: str
    priority: Priority
    condition: str  # Human-readable condition (e.g., "error_count >= 3")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "priority": self.priority.name,
            "condition": self.condition,
        }


# Predefined escalation triggers
ESCALATION_TRIGGERS: Dict[str, EscalationTrigger] = {
    "consecutive_errors": EscalationTrigger(
        name="consecutive_errors",
        description="Agent failed 3+ consecutive tasks",
        priority=Priority.P2_HIGH,
        condition="error_count >= 3",
    ),
    "low_confidence": EscalationTrigger(
        name="low_confidence",
        description="Agent confidence below threshold on a decision",
        priority=Priority.P3_MEDIUM,
        condition="confidence < 0.6",
    ),
    "cost_overrun": EscalationTrigger(
        name="cost_overrun",
        description="Task cost exceeds budget threshold",
        priority=Priority.P2_HIGH,
        condition="task_cost_usd > threshold",
    ),
    "task_timeout": EscalationTrigger(
        name="task_timeout",
        description="Task exceeded maximum execution time",
        priority=Priority.P3_MEDIUM,
        condition="execution_time > 300s",
    ),
    "financial_action": EscalationTrigger(
        name="financial_action",
        description="Agent attempting financial transaction over $100",
        priority=Priority.P1_CRITICAL,
        condition="amount_usd > 100",
    ),
    "customer_complaint": EscalationTrigger(
        name="customer_complaint",
        description="Customer complaint detected in agent interaction",
        priority=Priority.P2_HIGH,
        condition="sentiment == 'negative' AND topic == 'complaint'",
    ),
    "new_partnership": EscalationTrigger(
        name="new_partnership",
        description="Partnership or business opportunity detected",
        priority=Priority.P3_MEDIUM,
        condition="opportunity_type == 'partnership'",
    ),
    "compliance_risk": EscalationTrigger(
        name="compliance_risk",
        description="Potential regulatory or compliance issue",
        priority=Priority.P1_CRITICAL,
        condition="risk_type == 'compliance'",
    ),
    "system_degradation": EscalationTrigger(
        name="system_degradation",
        description="Multiple agents showing degraded performance",
        priority=Priority.P1_CRITICAL,
        condition="degraded_agent_count >= 3",
    ),
}


@dataclass
class EscalationTicket:
    """A ticket created when an agent escalates to human."""
    ticket_id: str
    trigger_name: str
    priority: Priority
    agent_name: str
    summary: str
    details: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    acknowledged_at: Optional[float] = None
    resolved_at: Optional[float] = None
    resolution: Optional[str] = None
    status: str = "open"  # open | acknowledged | resolved | dismissed

    @property
    def is_breached(self) -> bool:
        """Check if SLA has been breached."""
        sla = DEFAULT_SLAS.get(self.priority)
        if not sla:
            return False
        elapsed = time.time() - self.created_at
        if self.status == "open" and elapsed > sla.response_time_seconds:
            return True
        if self.status in ("open", "acknowledged") and elapsed > sla.resolution_time_seconds:
            return True
        return False

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def acknowledge(self) -> None:
        self.status = "acknowledged"
        self.acknowledged_at = time.time()

    def resolve(self, resolution: str) -> None:
        self.status = "resolved"
        self.resolved_at = time.time()
        self.resolution = resolution

    def dismiss(self) -> None:
        self.status = "dismissed"
        self.resolved_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "trigger_name": self.trigger_name,
            "priority": self.priority.name,
            "agent_name": self.agent_name,
            "summary": self.summary,
            "details": self.details,
            "created_at": self.created_at,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
            "status": self.status,
            "age_seconds": round(self.age_seconds, 1),
            "is_breached": self.is_breached,
        }


class EscalationManager:
    """
    Manages escalation tickets and notification delivery.

    Tracks escalation rate and ensures the target of <5% is met.
    Provides metrics for the monitoring dashboard.
    """

    def __init__(self):
        self._tickets: Dict[str, EscalationTicket] = {}
        self._resolved_tickets: List[EscalationTicket] = []
        self._total_tasks: int = 0
        self._total_escalations: int = 0
        self._notification_handlers: Dict[str, Callable[..., Coroutine]] = {}
        self._logger = logger.bind(component="escalation_manager")

    def register_notification_handler(
        self, channel: str, handler: Callable[..., Coroutine]
    ) -> None:
        """Register a notification delivery handler (e.g., Telegram, email)."""
        self._notification_handlers[channel] = handler
        self._logger.info("notification_handler_registered", channel=channel)

    def record_task(self) -> None:
        """Record a completed task (for escalation rate calculation)."""
        self._total_tasks += 1

    async def escalate(
        self,
        trigger_name: str,
        agent_name: str,
        summary: str,
        details: Optional[Dict[str, Any]] = None,
        priority: Optional[Priority] = None,
    ) -> EscalationTicket:
        """
        Create an escalation ticket and notify the human.

        Args:
            trigger_name: Name of the trigger (from ESCALATION_TRIGGERS)
            agent_name: Which agent is escalating
            summary: Brief description of the issue
            details: Additional context
            priority: Override priority (defaults to trigger's priority)

        Returns:
            The created EscalationTicket
        """
        trigger = ESCALATION_TRIGGERS.get(trigger_name)
        if not trigger:
            self._logger.warning("unknown_trigger", trigger_name=trigger_name)
            trigger = EscalationTrigger(
                name=trigger_name,
                description=summary,
                priority=Priority.P3_MEDIUM,
                condition="manual",
            )

        ticket = EscalationTicket(
            ticket_id=uuid.uuid4().hex[:12],
            trigger_name=trigger_name,
            priority=priority or trigger.priority,
            agent_name=agent_name,
            summary=summary,
            details=details or {},
        )

        self._tickets[ticket.ticket_id] = ticket
        self._total_escalations += 1

        self._logger.warning(
            "escalation_created",
            ticket_id=ticket.ticket_id,
            trigger=trigger_name,
            priority=ticket.priority.name,
            agent=agent_name,
            summary=summary[:200],
        )

        # Send notifications
        await self._notify(ticket)

        return ticket

    async def _notify(self, ticket: EscalationTicket) -> None:
        """Send notifications through appropriate channels."""
        sla = DEFAULT_SLAS.get(ticket.priority)
        if not sla:
            return

        for channel in sla.channels:
            handler = self._notification_handlers.get(channel)
            if handler:
                try:
                    await handler(ticket)
                    self._logger.info(
                        "notification_sent",
                        channel=channel,
                        ticket_id=ticket.ticket_id,
                    )
                except Exception as exc:
                    self._logger.error(
                        "notification_failed",
                        channel=channel,
                        ticket_id=ticket.ticket_id,
                        error=str(exc),
                    )

    def acknowledge_ticket(self, ticket_id: str) -> bool:
        """Acknowledge an open ticket."""
        ticket = self._tickets.get(ticket_id)
        if not ticket or ticket.status != "open":
            return False
        ticket.acknowledge()
        self._logger.info("ticket_acknowledged", ticket_id=ticket_id)
        return True

    def resolve_ticket(self, ticket_id: str, resolution: str) -> bool:
        """Resolve a ticket with a resolution note."""
        ticket = self._tickets.get(ticket_id)
        if not ticket or ticket.status in ("resolved", "dismissed"):
            return False
        ticket.resolve(resolution)
        self._resolved_tickets.append(ticket)
        del self._tickets[ticket_id]
        self._logger.info("ticket_resolved", ticket_id=ticket_id, resolution=resolution[:100])
        return True

    def dismiss_ticket(self, ticket_id: str) -> bool:
        """Dismiss a ticket as not requiring action."""
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return False
        ticket.dismiss()
        self._resolved_tickets.append(ticket)
        del self._tickets[ticket_id]
        self._logger.info("ticket_dismissed", ticket_id=ticket_id)
        return True

    # ── Query API ───────────────────────────────────────────────────

    def get_open_tickets(self) -> List[Dict[str, Any]]:
        """Get all open/acknowledged tickets sorted by priority."""
        tickets = [t for t in self._tickets.values() if t.status in ("open", "acknowledged")]
        tickets.sort(key=lambda t: (t.priority.value, -t.created_at))
        return [t.to_dict() for t in tickets]

    def get_breached_tickets(self) -> List[Dict[str, Any]]:
        """Get tickets that have breached their SLA."""
        breached = [t for t in self._tickets.values() if t.is_breached]
        return [t.to_dict() for t in breached]

    def get_metrics(self) -> Dict[str, Any]:
        """Get escalation metrics for the monitoring dashboard."""
        escalation_rate = (
            self._total_escalations / self._total_tasks
            if self._total_tasks > 0
            else 0.0
        )
        open_count = len([t for t in self._tickets.values() if t.status == "open"])
        acknowledged_count = len([
            t for t in self._tickets.values() if t.status == "acknowledged"
        ])

        return {
            "total_tasks": self._total_tasks,
            "total_escalations": self._total_escalations,
            "escalation_rate": round(escalation_rate * 100, 2),  # percentage
            "escalation_target": 5.0,  # percent
            "on_target": escalation_rate <= 0.05,
            "open_tickets": open_count,
            "acknowledged_tickets": acknowledged_count,
            "resolved_total": len(self._resolved_tickets),
            "breached_count": len(self.get_breached_tickets()),
            "by_priority": self._tickets_by_priority(),
            "by_trigger": self._tickets_by_trigger(),
        }

    def _tickets_by_priority(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for ticket in self._tickets.values():
            key = ticket.priority.name
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _tickets_by_trigger(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for ticket in self._tickets.values():
            key = ticket.trigger_name
            counts[key] = counts.get(key, 0) + 1
        return counts
