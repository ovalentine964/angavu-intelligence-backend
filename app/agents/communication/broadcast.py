"""
BroadcastProtocol — EventBus-based broadcast communication.

Events are published to the EventBus and delivered to all subscribers.
This is the primary communication pattern for the pipeline:
    TransactionProcessor → IntelligenceGenerator → ReportGenerator

Pattern:
    Agent A ──publish──▶ EventBus ──deliver──▶ Agent B, C, D
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import AgentEvent, BiasharaAgent, EventType

logger = structlog.get_logger(__name__)


class BroadcastProtocol:
    """
    Manages broadcast communication via the EventBus.

    Provides convenience methods for publishing events with
    proper metadata, correlation tracking, and delivery confirmation.
    """

    def __init__(self, event_bus: Any):
        self._event_bus = event_bus
        self._publish_count: int = 0
        self._delivery_log: List[Dict[str, Any]] = []
        self._logger = logger.bind(component="broadcast_protocol")

    async def publish(
        self,
        source: str,
        event_type: EventType,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Publish a broadcast event to the EventBus.

        Args:
            source: Name of the publishing agent
            event_type: The event type to publish
            payload: Event payload
            correlation_id: Optional ID to link related events
            metadata: Optional metadata for tracing

        Returns:
            The event ID
        """
        event = AgentEvent(
            event_type=event_type,
            source=source,
            payload=payload,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )

        event_id = await self._event_bus.publish(event)
        self._publish_count += 1

        self._delivery_log.append({
            "event_id": event_id,
            "event_type": event_type.value,
            "source": source,
            "timestamp": time.time(),
        })

        # Keep log bounded
        if len(self._delivery_log) > 1000:
            self._delivery_log = self._delivery_log[-500:]

        self._logger.debug(
            "broadcast_published",
            event_type=event_type.value,
            source=source,
            event_id=event_id,
        )
        return event_id

    async def publish_pipeline_event(
        self,
        source: str,
        event_type: EventType,
        data: Dict[str, Any],
        worker_id: Optional[str] = None,
        worker_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Convenience method for publishing pipeline events with worker context."""
        payload = {**data}
        if worker_id:
            payload["worker_id"] = worker_id
        if worker_type:
            payload["worker_type"] = worker_type

        return await self.publish(
            source=source,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
            metadata={"pipeline_event": True},
        )

    async def broadcast_alert(
        self,
        source: str,
        alert_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Broadcast a system alert to all listening agents."""
        return await self.publish(
            source=source,
            event_type=EventType.MARKET_ALERT,
            payload={
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
                "details": details or {},
            },
        )

    async def broadcast_health_report(
        self,
        source: str,
        overall_status: str,
        agent_statuses: Dict[str, str],
    ) -> str:
        """Broadcast a system health report."""
        return await self.publish(
            source=source,
            event_type=EventType.SYSTEM_HEALTH_REPORT,
            payload={
                "overall_status": overall_status,
                "agent_statuses": agent_statuses,
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        """Return broadcast protocol statistics."""
        return {
            "total_published": self._publish_count,
            "recent_deliveries": self._delivery_log[-10:],
            "delivery_log_size": len(self._delivery_log),
        }
