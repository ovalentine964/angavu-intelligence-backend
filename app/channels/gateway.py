"""
Multi-Channel Gateway — Central routing hub for all communication channels.

Implements the OpenClaw pattern: one agent system, multiple channels, same session.
Routes incoming messages from any channel through a unified pipeline.

Flow:
    1. Receive UnifiedMessage from any channel adapter
    2. Resolve worker identity → canonical user_id
    3. Get/create session (SAME session across channels)
    4. Route to Intelligence Pipeline
    5. Save to session history
    6. Return response through source channel
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.channels.adapters.base import (
    ChannelResponse,
    ChannelType,
    UnifiedMessage,
)
from app.channels.registry import ChannelRegistry
from app.channels.session_sync import SessionSync

logger = structlog.get_logger(__name__)


class MultiChannelGateway:
    """
    Central gateway that routes messages from any channel through
    a unified intelligence pipeline with shared sessions.

    Core principle: the session belongs to the WORKER, not the CHANNEL.
    A worker who starts on the app and switches to WhatsApp keeps
    their full conversation context.
    """

    def __init__(
        self,
        registry: ChannelRegistry,
        session_sync: SessionSync,
        pipeline: Any = None,
        failover_manager: Any = None,
    ):
        self.registry = registry
        self.session_sync = session_sync
        self.pipeline = pipeline
        self.failover_manager = failover_manager
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all registered channel adapters."""
        if self._initialized:
            return
        await self.registry.initialize_all()
        self._initialized = True
        logger.info(
            "gateway_initialized",
            channels=self.registry.registered_channels,
        )

    async def handle_message(self, message: UnifiedMessage) -> ChannelResponse:
        """
        Route an incoming message through the full pipeline.

        Steps:
            1. Validate the message
            2. Resolve worker identity
            3. Get or create cross-channel session
            4. Detect channel switch (log for analytics)
            5. Route to intelligence pipeline
            6. Save interaction to session history
            7. Return response through source channel
        """
        request_id = str(uuid.uuid4())
        start_time = datetime.now(UTC)

        logger.info(
            "gateway_message_received",
            request_id=request_id,
            channel=message.channel.value,
            worker_id=message.worker_id,
            content_length=len(message.content) if message.content else 0,
        )

        # Step 1: Validate
        if not message.worker_id:
            return ChannelResponse(
                success=False,
                error="Missing worker_id",
                channel=message.channel,
            )

        # Step 2: Resolve worker identity
        canonical_worker_id = await self._resolve_worker(message)

        # Step 3: Get or create session (same session across channels!)
        session = await self.session_sync.get_or_create_session(
            worker_id=canonical_worker_id,
            channel=message.channel,
        )

        # Step 4: Detect channel switch
        previous_channel = await self.session_sync.get_last_channel(
            canonical_worker_id
        )
        if previous_channel and previous_channel != message.channel:
            logger.info(
                "channel_switch_detected",
                worker_id=canonical_worker_id,
                from_channel=previous_channel.value,
                to_channel=message.channel.value,
            )
            message.metadata["channel_switch"] = {
                "from": previous_channel.value,
                "to": message.channel.value,
                "detected_at": start_time.isoformat(),
            }

        # Step 5: Route to intelligence pipeline
        try:
            if self.pipeline:
                response_text = await self._route_to_pipeline(
                    message=message,
                    session=session,
                    canonical_worker_id=canonical_worker_id,
                )
            else:
                response_text = await self._fallback_response(message)
        except Exception as e:
            logger.error(
                "pipeline_error",
                request_id=request_id,
                error=str(e),
                worker_id=canonical_worker_id,
            )
            response_text = (
                "Samadhani, kuna hitilafu. Tafadhali jaribu tena baadae."
            )

        # Step 6: Save to session history
        await self.session_sync.record_interaction(
            worker_id=canonical_worker_id,
            session_id=session.session_id,
            channel=message.channel,
            user_message=message.content,
            agent_response=response_text,
            metadata=message.metadata,
        )

        # Step 7: Build response
        elapsed_ms = int(
            (datetime.now(UTC) - start_time).total_seconds() * 1000
        )

        return ChannelResponse(
            success=True,
            content=response_text,
            channel=message.channel,
            session_id=session.session_id,
            metadata={
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
                "canonical_worker_id": canonical_worker_id,
                "channel_switch": previous_channel is not None
                and previous_channel != message.channel,
            },
        )

    async def send_proactive(
        self,
        worker_id: str,
        content: str,
        preferred_channel: ChannelType | None = None,
    ) -> bool:
        """
        Send a proactive message to a worker on their preferred channel.
        Used for alerts, reminders, and notifications.

        If failover_manager is available, uses automatic failover.
        Otherwise, falls back to direct adapter delivery.
        """
        # Use failover manager if available
        if self.failover_manager:
            channel_name = (
                preferred_channel.value if preferred_channel else None
            )
            result = await self.failover_manager.send(
                recipient_id=worker_id,
                content=content,
                preferred_channel=channel_name,
            )
            if result["success"]:
                logger.info(
                    "proactive_message_sent",
                    worker_id=worker_id,
                    channel_used=result["channel_used"],
                    failover=result["failover_triggered"],
                )
                return True
            else:
                logger.error(
                    "proactive_message_failed",
                    worker_id=worker_id,
                    attempted=result["attempted"],
                )
                return False

        # Direct delivery without failover
        if preferred_channel is None:
            preferred_channel = await self.session_sync.get_preferred_channel(
                worker_id
            )

        adapter = self.registry.get_adapter(preferred_channel)
        if adapter is None:
            logger.warning(
                "no_adapter_for_channel",
                worker_id=worker_id,
                channel=preferred_channel.value,
            )
            return False

        try:
            await adapter.send_message(
                recipient_id=worker_id,
                content=content,
            )
            logger.info(
                "proactive_message_sent",
                worker_id=worker_id,
                channel=preferred_channel.value,
            )
            return True
        except Exception as e:
            logger.error(
                "proactive_message_failed",
                worker_id=worker_id,
                channel=preferred_channel.value,
                error=str(e),
            )
            return False

    async def _resolve_worker(self, message: UnifiedMessage) -> str:
        """
        Resolve the canonical worker ID from channel-specific identifiers.

        For the app channel, worker_id is already the canonical UUID.
        For WhatsApp, we resolve from the phone number.
        For SMS/Voice, we resolve from the phone number.
        """
        # If already a UUID, return as-is
        if len(message.worker_id) == 36 and "-" in message.worker_id:
            return message.worker_id

        # Try to resolve from channel-specific ID
        resolved = await self.registry.resolve_worker_id(
            channel=message.channel,
            channel_user_id=message.worker_id,
        )
        return resolved or message.worker_id

    async def _route_to_pipeline(
        self,
        message: UnifiedMessage,
        session: Any,
        canonical_worker_id: str,
    ) -> str:
        """Route message through the intelligence pipeline."""
        # Build context from session history
        context = {
            "worker_id": canonical_worker_id,
            "channel": message.channel.value,
            "session_id": session.session_id,
            "language": message.language or "sw",
            "history": await self.session_sync.get_recent_history(
                worker_id=canonical_worker_id,
                limit=10,
            ),
        }

        # Add metadata
        if message.metadata:
            context.update(message.metadata)

        # Route through pipeline
        result = await self.pipeline.process(
            message=message.content,
            context=context,
        )

        return result.get("response", "Sijaelewa. Tafadhali rudia.")

    async def _fallback_response(self, message: UnifiedMessage) -> str:
        """Fallback when no pipeline is configured."""
        return (
            f"Ujumbe wako umepokelewa: '{message.content[:50]}...'. "
            "Tunafanya kazi kujibu."
        )

    def get_stats(self) -> dict[str, Any]:
        """Get gateway statistics."""
        return {
            "registered_channels": self.registry.registered_channels,
            "active_sessions": self.session_sync.active_session_count,
            "initialized": self._initialized,
        }
