"""
Channel Health Monitor — Monitors all communication channels.

Continuously monitors the health of all registered channel adapters
(WhatsApp, Telegram, SMS, HTTP API) and triggers automatic failover
when a channel goes down.

Features:
- Periodic health checks for all channels
- Consecutive failure tracking
- Channel status history
- Automatic failover trigger
- Admin alerting on channel failures
- Health API for monitoring dashboards

Usage:
    monitor = ChannelHealthMonitor(registry)
    await monitor.start()  # Starts background monitoring

    # Check status
    status = monitor.get_channel_status()

    # Get recommended channel for delivery
    best_channel = monitor.get_best_channel()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

from app.channels.adapters.base import BaseChannelAdapter, ChannelType

# Channel names for failover (matching ChannelType values)
CHANNEL_WHATSAPP = ChannelType.WHATSAPP.value
CHANNEL_HTTP_API = ChannelType.HTTP_API.value

logger = structlog.get_logger(__name__)

# Health check interval in seconds
HEALTH_CHECK_INTERVAL = 60  # Check every minute

# Thresholds for channel health
CONSECUTIVE_FAILURE_THRESHOLD = 3  # Mark as unhealthy after 3 failures
RECOVERY_CHECK_INTERVAL = 300  # Check unhealthy channels every 5 min


class ChannelStatus(str, Enum):
    """Health status of a channel."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


@dataclass
class ChannelHealthState:
    """Health state for a single channel."""
    channel_type: str  # "whatsapp", "telegram", "sms", "http_api"
    status: ChannelStatus = ChannelStatus.UNKNOWN
    consecutive_failures: int = 0
    total_checks: int = 0
    total_failures: int = 0
    last_check_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_error: str | None = None
    latency_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "channel": self.channel_type,
            "status": self.status.value,
            "consecutive_failures": self.consecutive_failures,
            "total_checks": self.total_checks,
            "total_failures": self.total_failures,
            "last_check_at": self.last_check_at,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "last_error": self.last_error,
            "latency_ms": self.latency_ms,
        }


class ChannelHealthMonitor:
    """
    Monitors the health of all communication channels.

    Runs periodic health checks on each registered adapter and
    tracks failure patterns. When a channel goes unhealthy,
    triggers automatic failover to backup channels.

    Channel priority (highest to lowest):
    1. WhatsApp (primary — workers' preferred channel)
    2. Telegram (backup — stable API, common in East Africa)
    3. SMS (fallback — works on any phone, no data needed)
    4. HTTP API (last resort — pull-based, always available)
    """

    def __init__(self, registry: Any = None):
        self._registry = registry
        self._channel_states: dict[str, ChannelHealthState] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._failover_callbacks: list[Callable[..., Coroutine]] = []

        # Channel priority (lower = higher priority)
        self._channel_priority: dict[str, int] = {
            ChannelType.WHATSAPP.value: 0,
            ChannelType.TELEGRAM.value: 1,
            ChannelType.SMS.value: 2,
            ChannelType.HTTP_API.value: 3,
        }

    def register_failover_callback(
        self, callback: Callable[..., Coroutine]
    ) -> None:
        """
        Register a callback to be called when failover occurs.

        The callback receives:
            (from_channel: str, to_channel: str, reason: str)
        """
        self._failover_callbacks.append(callback)

    async def start(self) -> None:
        """Start the background health monitoring task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("channel_health_monitor_started")

    async def stop(self) -> None:
        """Stop the background health monitoring task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("channel_health_monitor_stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop — checks all channels periodically."""
        while self._running:
            try:
                await self._check_all_channels()
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_monitor_error", error=str(e))
                await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _check_all_channels(self) -> None:
        """Run health checks on all registered channels."""
        if not self._registry:
            return

        for channel_type, adapter in self._registry.all_adapters.items():
            channel_name = channel_type.value
            await self._check_channel(channel_name, adapter)

    async def _check_channel(
        self, channel_name: str, adapter: BaseChannelAdapter
    ) -> None:
        """
        Run health check on a single channel.

        Updates the channel's health state and triggers failover
        if the channel goes unhealthy.
        """
        # Get or create state
        if channel_name not in self._channel_states:
            self._channel_states[channel_name] = ChannelHealthState(
                channel_type=channel_name
            )

        state = self._channel_states[channel_name]
        state.total_checks += 1
        state.last_check_at = datetime.now(UTC).isoformat()

        try:
            # Run health check with timeout
            import time
            start = time.monotonic()
            is_healthy = await asyncio.wait_for(
                adapter.health_check(), timeout=10.0
            )
            latency = (time.monotonic() - start) * 1000  # ms

            if is_healthy:
                previous_status = state.status
                state.status = ChannelStatus.HEALTHY
                state.consecutive_failures = 0
                state.last_success_at = datetime.now(UTC).isoformat()
                state.last_error = None
                state.latency_ms = round(latency, 1)

                # Log recovery if previously unhealthy
                if previous_status in (
                    ChannelStatus.UNHEALTHY,
                    ChannelStatus.DEGRADED,
                ):
                    logger.info(
                        "channel_recovered",
                        channel=channel_name,
                        previous_status=previous_status.value,
                    )
            else:
                state.consecutive_failures += 1
                state.total_failures += 1
                state.last_failure_at = datetime.now(UTC).isoformat()
                state.last_error = "Health check returned False"

                if state.consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
                    state.status = ChannelStatus.UNHEALTHY
                elif state.consecutive_failures >= 1:
                    state.status = ChannelStatus.DEGRADED

        except asyncio.TimeoutError:
            state.consecutive_failures += 1
            state.total_failures += 1
            state.last_failure_at = datetime.now(UTC).isoformat()
            state.last_error = "Health check timed out"

            if state.consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
                state.status = ChannelStatus.UNHEALTHY
            else:
                state.status = ChannelStatus.DEGRADED

        except Exception as e:
            state.consecutive_failures += 1
            state.total_failures += 1
            state.last_failure_at = datetime.now(UTC).isoformat()
            state.last_error = str(e)

            if state.consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
                state.status = ChannelStatus.UNHEALTHY
            else:
                state.status = ChannelStatus.DEGRADED

    def get_channel_status(
        self, channel_name: str | None = None
    ) -> dict[str, Any]:
        """
        Get health status for a specific channel or all channels.

        Args:
            channel_name: Specific channel, or None for all

        Returns:
            Dict with channel health information
        """
        if channel_name:
            state = self._channel_states.get(channel_name)
            if state:
                return state.to_dict()
            return {
                "channel": channel_name,
                "status": "unknown",
                "message": "No health data available",
            }

        return {
            "channels": {
                name: state.to_dict()
                for name, state in self._channel_states.items()
            },
            "overall": self._get_overall_status(),
            "best_channel": self.get_best_channel(),
        }

    def _get_overall_status(self) -> str:
        """Get overall communication status."""
        if not self._channel_states:
            return "no_channels"

        healthy_count = sum(
            1 for s in self._channel_states.values()
            if s.status == ChannelStatus.HEALTHY
        )

        if healthy_count == 0:
            return "all_down"
        elif healthy_count == len(self._channel_states):
            return "all_healthy"
        else:
            return "partial"

    def get_best_channel(self) -> str | None:
        """
        Get the best available channel based on health and priority.

        Returns the highest-priority channel that is healthy.
        Falls back to degraded channels if no healthy ones exist.

        Returns:
            Channel name or None if all channels are down
        """
        # Sort by priority
        sorted_channels = sorted(
            self._channel_priority.items(), key=lambda x: x[1]
        )

        # First pass: look for healthy channels
        for channel_name, _ in sorted_channels:
            state = self._channel_states.get(channel_name)
            if state and state.status == ChannelStatus.HEALTHY:
                return channel_name

        # Second pass: accept degraded channels
        for channel_name, _ in sorted_channels:
            state = self._channel_states.get(channel_name)
            if state and state.status == ChannelStatus.DEGRADED:
                return channel_name

        # Last resort: HTTP API is always available (in-memory)
        return "http_api"

    def get_failover_channel(
        self, failed_channel: str
    ) -> str | None:
        """
        Get the next best channel when a specific channel fails.

        Args:
            failed_channel: The channel that failed

        Returns:
            Next best channel name, or None
        """
        sorted_channels = sorted(
            self._channel_priority.items(), key=lambda x: x[1]
        )

        for channel_name, _ in sorted_channels:
            if channel_name == failed_channel:
                continue
            state = self._channel_states.get(channel_name)
            if state and state.status in (
                ChannelStatus.HEALTHY,
                ChannelStatus.DEGRADED,
            ):
                return channel_name

        # Ultimate fallback
        return CHANNEL_HTTP_API

    def is_channel_healthy(self, channel_name: str) -> bool:
        """Check if a specific channel is healthy."""
        state = self._channel_states.get(channel_name)
        if not state:
            return False
        return state.status in (
            ChannelStatus.HEALTHY,
            ChannelStatus.DEGRADED,
        )

    async def trigger_failover(
        self,
        from_channel: str,
        reason: str,
    ) -> str | None:
        """
        Trigger failover from a failed channel.

        Notifies all registered callbacks about the failover.

        Args:
            from_channel: The channel that failed
            reason: Why the failover was triggered

        Returns:
            The channel that will be used instead, or None
        """
        to_channel = self.get_failover_channel(from_channel)

        if to_channel:
            logger.warning(
                "channel_failover_triggered",
                from_channel=from_channel,
                to_channel=to_channel,
                reason=reason,
            )

            # Notify callbacks
            for callback in self._failover_callbacks:
                try:
                    await callback(from_channel, to_channel, reason)
                except Exception as e:
                    logger.error(
                        "failover_callback_error",
                        error=str(e),
                    )

        return to_channel
