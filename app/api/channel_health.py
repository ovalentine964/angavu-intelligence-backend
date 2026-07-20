"""
Channel Health API — Monitor communication channel status.

Provides endpoints for:
- Checking health of all channels (WhatsApp, Telegram, SMS, HTTP API)
- Viewing failover status and history
- Manual channel enable/disable
- Triggering manual failover

Used by:
- Monitoring dashboards
- Admin tools
- Health check systems (e.g., UptimeRobot, Pingdom)
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/channels", tags=["Channel Health"])

# Injected at startup
_health_monitor = None
_failover_manager = None


def set_channel_infrastructure(
    health_monitor: Any, failover_manager: Any
) -> None:
    """Set the health monitor and failover manager instances."""
    global _health_monitor, _failover_manager
    _health_monitor = health_monitor
    _failover_manager = failover_manager


# =========================================================================
# Schemas
# =========================================================================


class ChannelStatusResponse(BaseModel):
    """Response for channel status."""
    channels: dict[str, Any]
    overall: str
    best_channel: str | None = None


class FailoverStatsResponse(BaseModel):
    """Failover manager statistics."""
    total_sent: int = 0
    total_failed: int = 0
    failover_count: int = 0
    channel_send_counts: dict[str, int] = {}
    channel_fail_counts: dict[str, int] = {}
    telegram_id_mappings: int = 0


class ChannelTestRequest(BaseModel):
    """Request to test a specific channel."""
    channel: str = Field(
        ...,
        description="Channel to test: whatsapp, telegram, sms, http_api",
    )
    recipient_id: str = Field(
        ...,
        description="Recipient to send test message to",
    )
    message: str = Field(
        default="Channel test message from Angavu Intelligence",
        description="Test message content",
    )


class ChannelTestResponse(BaseModel):
    """Response from channel test."""
    channel: str
    success: bool
    error: str | None = None
    latency_ms: float | None = None


class FailoverTriggerRequest(BaseModel):
    """Request to manually trigger failover."""
    from_channel: str = Field(
        ...,
        description="Channel to failover FROM",
    )
    reason: str = Field(
        default="Manual failover triggered",
        description="Reason for failover",
    )


class FailoverTriggerResponse(BaseModel):
    """Response from manual failover trigger."""
    from_channel: str
    to_channel: str | None = None
    triggered: bool
    reason: str


# =========================================================================
# Endpoints
# =========================================================================


@router.get("/health", response_model=ChannelStatusResponse)
async def get_channel_health() -> ChannelStatusResponse:
    """
    Get health status of all communication channels.

    Returns the status of each channel (WhatsApp, Telegram, SMS, HTTP API),
    overall system health, and the recommended best channel for delivery.

    **Status values:**
    - `healthy`: Channel is working normally
    - `degraded`: Channel has intermittent issues
    - `unhealthy`: Channel is down (≥3 consecutive failures)
    - `disabled`: Channel is not configured
    - `unknown`: No health data yet
    """
    if _health_monitor:
        status_data = _health_monitor.get_channel_status()
        return ChannelStatusResponse(
            channels=status_data.get("channels", {}),
            overall=status_data.get("overall", "unknown"),
            best_channel=status_data.get("best_channel"),
        )

    return ChannelStatusResponse(
        channels={},
        overall="no_monitor",
        best_channel=None,
    )


@router.get("/health/{channel_name}")
async def get_specific_channel_health(channel_name: str) -> dict[str, Any]:
    """
    Get health status for a specific channel.

    Args:
        channel_name: Channel to check (whatsapp, telegram, sms, http_api)
    """
    if _health_monitor:
        return _health_monitor.get_channel_status(channel_name)

    return {
        "channel": channel_name,
        "status": "no_monitor",
        "message": "Health monitor not configured",
    }


@router.get("/failover/stats", response_model=FailoverStatsResponse)
async def get_failover_stats() -> FailoverStatsResponse:
    """
    Get failover manager statistics.

    Shows how many messages were sent via each channel,
    how many times failover was triggered, and overall delivery stats.
    """
    if _failover_manager:
        stats = _failover_manager.get_stats()
        return FailoverStatsResponse(**stats)

    return FailoverStatsResponse()


@router.post("/test", response_model=ChannelTestResponse)
async def test_channel(request: ChannelTestRequest) -> ChannelTestResponse:
    """
    Test a specific channel by sending a test message.

    Useful for verifying channel configuration and connectivity.

    **Channels:**
    - `whatsapp`: Test via OpenWA
    - `telegram`: Test via Telegram Bot API
    - `sms`: Test via Africa's Talking
    - `http_api`: Test via HTTP API queue
    """
    import time

    if not _failover_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failover manager not configured",
        )

    adapter = _failover_manager._get_adapter(request.channel)
    if not adapter:
        return ChannelTestResponse(
            channel=request.channel,
            success=False,
            error=f"No adapter found for channel: {request.channel}",
        )

    try:
        start = time.monotonic()
        success = await adapter.send_message(
            request.recipient_id,
            request.message,
        )
        latency = (time.monotonic() - start) * 1000

        return ChannelTestResponse(
            channel=request.channel,
            success=success,
            latency_ms=round(latency, 1),
            error=None if success else "Send returned False",
        )
    except Exception as e:
        return ChannelTestResponse(
            channel=request.channel,
            success=False,
            error=str(e),
        )


@router.post("/failover/trigger", response_model=FailoverTriggerResponse)
async def trigger_failover(
    request: FailoverTriggerRequest,
) -> FailoverTriggerResponse:
    """
    Manually trigger failover from one channel to another.

    Used by admins to manually switch delivery channels
    (e.g., during planned maintenance).

    Args:
        from_channel: Channel to failover FROM
        reason: Reason for the failover
    """
    if not _health_monitor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health monitor not configured",
        )

    to_channel = await _health_monitor.trigger_failover(
        from_channel=request.from_channel,
        reason=request.reason,
    )

    return FailoverTriggerResponse(
        from_channel=request.from_channel,
        to_channel=to_channel,
        triggered=to_channel is not None,
        reason=request.reason,
    )


@router.post("/ban-detected")
async def handle_ban_detected(request: dict[str, Any]) -> dict[str, Any]:
    """
    Handle ban detection notification from OpenWA.

    When OpenWA detects that the WhatsApp number has been banned,
    it calls this endpoint to trigger automatic failover to Telegram.

    This is a critical safety endpoint — it ensures messages continue
    to be delivered even when WhatsApp bans the number.
    """
    channel = request.get("channel", "whatsapp")
    reason = request.get("reason", "unknown")
    detected_at = request.get("detected_at")

    logger.critical(
        "ban_detected_notification",
        channel=channel,
        reason=reason,
        detected_at=detected_at,
    )

    # Trigger failover if health monitor is available
    to_channel = None
    if _health_monitor:
        to_channel = await _health_monitor.trigger_failover(
            from_channel=channel,
            reason=f"BAN DETECTED: {reason}",
        )

    # Mark WhatsApp as unhealthy
    if _health_monitor:
        wa_state = _health_monitor._channel_states.get(channel)
        if wa_state:
            from app.channels.health_monitor import ChannelStatus
            wa_state.status = ChannelStatus.UNHEALTHY
            wa_state.last_error = f"BANNED: {reason}"
            wa_state.metadata["ban_detected"] = True
            wa_state.metadata["ban_reason"] = reason
            wa_state.metadata["ban_at"] = detected_at

    return {
        "status": "acknowledged",
        "channel": channel,
        "failover_to": to_channel,
        "message": f"Ban acknowledged. Failover to {to_channel or 'none'} triggered.",
    }


@router.get("/ban-status")
async def get_ban_status() -> dict[str, Any]:
    """
    Check if any channel has been banned.

    Returns ban status for all monitored channels.
    """
    bans = {}
    if _health_monitor:
        for name, state in _health_monitor._channel_states.items():
            if state.metadata.get("ban_detected"):
                bans[name] = {
                    "banned": True,
                    "reason": state.metadata.get("ban_reason"),
                    "at": state.metadata.get("ban_at"),
                    "status": state.status.value,
                }

    return {
        "bans": bans,
        "has_bans": len(bans) > 0,
    }


@router.get("/summary")
async def get_channel_summary() -> dict[str, Any]:
    """
    Get a summary of all channel infrastructure.

    Returns a combined view of:
    - Channel health status
    - Failover statistics
    - Best available channel
    - Recommendations
    """
    health_data = {}
    failover_data = {}

    if _health_monitor:
        health_data = _health_monitor.get_channel_status()

    if _failover_manager:
        failover_data = _failover_manager.get_stats()

    # Generate recommendations
    recommendations = []
    best_channel = health_data.get("best_channel")

    channels = health_data.get("channels", {})
    whatsapp_status = channels.get("whatsapp", {}).get("status", "unknown")
    telegram_status = channels.get("telegram", {}).get("status", "unknown")

    if whatsapp_status == "unhealthy":
        recommendations.append(
            "WhatsApp is down. Check OpenWA service status."
        )
    if telegram_status == "unhealthy":
        recommendations.append(
            "Telegram fallback is down. Check bot token and API connectivity."
        )
    if whatsapp_status == "unhealthy" and telegram_status == "unhealthy":
        recommendations.append(
            "CRITICAL: Both WhatsApp and Telegram are down. "
            "SMS and HTTP API are the only remaining channels."
        )

    return {
        "health": health_data,
        "failover": failover_data,
        "best_channel": best_channel,
        "recommendations": recommendations,
        "overall_status": health_data.get("overall", "unknown"),
    }
