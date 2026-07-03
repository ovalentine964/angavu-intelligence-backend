"""
PointToPointProtocol — Direct agent-to-agent messaging.

Unlike broadcast (EventBus pub/sub), point-to-point messages are
directed to a specific agent. Used for:
- Delegation requests
- Request-response patterns
- Negotiation messages

Pattern:
    Agent A ──message──▶ Agent B
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import AgentEvent, AgentMessage, BiasharaAgent, EventType

logger = structlog.get_logger(__name__)


class PointToPointProtocol:
    """
    Manages direct agent-to-agent messaging.

    Messages are delivered via the EventBus but targeted to specific agents.
    Supports request-response with correlation IDs and timeouts.
    """

    def __init__(self, event_bus: Any):
        self._event_bus = event_bus
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._message_log: List[Dict[str, Any]] = []
        self._logger = logger.bind(component="p2p_protocol")

    async def send(
        self,
        sender: str,
        recipient: str,
        content: Dict[str, Any],
        message_type: str = "notification",
        correlation_id: Optional[str] = None,
        priority: int = 5,
    ) -> str:
        """
        Send a point-to-point message to a specific agent.

        Args:
            sender: Sending agent name
            recipient: Receiving agent name
            content: Message payload
            message_type: "request" | "response" | "notification" | "negotiation"
            correlation_id: Links request to response
            priority: 1 (highest) to 10 (lowest)

        Returns:
            The message ID
        """
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            content=content,
            message_type=message_type,
            correlation_id=correlation_id,
        )

        # Publish as a targeted event
        event = AgentEvent(
            event_type=EventType.AGENT_HEALTH_CHECK,  # generic envelope
            source=sender,
            payload={
                "message_type": "point_to_point",
                "recipient": recipient,
                "content": content,
                "msg_type": message_type,
                "priority": priority,
                "message_id": message.message_id,
                "correlation_id": correlation_id,
            },
            correlation_id=correlation_id,
            metadata={"p2p": True, "recipient": recipient},
        )

        await self._event_bus.publish(event)

        self._message_log.append({
            "message_id": message.message_id,
            "sender": sender,
            "recipient": recipient,
            "message_type": message_type,
            "timestamp": time.time(),
        })

        if len(self._message_log) > 1000:
            self._message_log = self._message_log[-500:]

        self._logger.debug(
            "p2p_message_sent",
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            message_id=message.message_id,
        )
        return message.message_id

    async def request(
        self,
        sender: str,
        recipient: str,
        content: Dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Send a request and wait for a response.

        Creates a correlation ID and waits for a response event
        with the same correlation ID.

        Args:
            sender: Sending agent name
            recipient: Receiving agent name
            content: Request payload
            timeout_seconds: How long to wait for response

        Returns:
            Response content dict

        Raises:
            asyncio.TimeoutError: If no response within timeout
        """
        correlation_id = uuid.uuid4().hex[:12]
        future = asyncio.get_event_loop().create_future()
        self._pending_responses[correlation_id] = future

        try:
            await self.send(
                sender=sender,
                recipient=recipient,
                content=content,
                message_type="request",
                correlation_id=correlation_id,
            )

            response = await asyncio.wait_for(future, timeout=timeout_seconds)
            return response

        finally:
            self._pending_responses.pop(correlation_id, None)

    async def respond(
        self,
        sender: str,
        recipient: str,
        correlation_id: str,
        content: Dict[str, Any],
    ) -> str:
        """Send a response to a previous request."""
        # Resolve pending future if exists
        future = self._pending_responses.get(correlation_id)
        if future and not future.done():
            future.set_result(content)

        return await self.send(
            sender=sender,
            recipient=recipient,
            content=content,
            message_type="response",
            correlation_id=correlation_id,
        )

    async def negotiate(
        self,
        sender: str,
        recipient: str,
        proposal: Dict[str, Any],
        timeout_seconds: float = 15.0,
    ) -> Dict[str, Any]:
        """
        Send a negotiation proposal and wait for acceptance/rejection.

        Used for conflict resolution between agents.
        """
        return await self.request(
            sender=sender,
            recipient=recipient,
            content={
                "type": "negotiation",
                "proposal": proposal,
            },
            timeout_seconds=timeout_seconds,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Return P2P protocol statistics."""
        return {
            "total_sent": len(self._message_log),
            "pending_responses": len(self._pending_responses),
            "recent_messages": self._message_log[-10:],
        }
