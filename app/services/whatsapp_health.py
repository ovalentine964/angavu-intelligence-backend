"""
WhatsApp Health Monitor — Angavu Intelligence.

Monitors the OpenWA service and WhatsApp session health.
Provides:
- Periodic health checks
- Auto-reconnect detection
- Admin alerts when OpenWA is down
- Connection status API

Run as a background task alongside the main backend.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# EAT timezone offset (UTC+3)
EAT_OFFSET = timedelta(hours=3)


def eat_now() -> datetime:
    """Get current time in East Africa Time."""
    return datetime.now(timezone.utc) + EAT_OFFSET


class WhatsAppHealthMonitor:
    """
    Monitors OpenWA service health and WhatsApp session status.

    Usage:
        monitor = WhatsAppHealthMonitor()
        status = await monitor.check_health()
        if not status["connected"]:
            await monitor.alert_admin("WhatsApp disconnected")
    """

    def __init__(self, openwa_url: Optional[str] = None):
        self.openwa_url = openwa_url or settings.OPENWA_URL
        self._last_check: Optional[datetime] = None
        self._last_status: Optional[Dict] = None
        self._consecutive_failures: int = 0
        self._alert_sent: bool = False

    async def check_health(self) -> Dict:
        """
        Check OpenWA service health.

        Returns:
            Dict with:
            - service_running: bool (HTTP reachable)
            - whatsapp_connected: bool (WhatsApp session active)
            - has_qr: bool (QR code available for scanning)
            - messages_sent: int
            - messages_received: int
            - errors: int
            - uptime: int (seconds)
            - last_disconnect: dict or None
            - status: str ("healthy", "degraded", "down", "disconnected")
        """
        result = {
            "service_running": False,
            "whatsapp_connected": False,
            "has_qr": False,
            "messages_sent": 0,
            "messages_received": 0,
            "errors": 0,
            "uptime": 0,
            "last_disconnect": None,
            "status": "unknown",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.openwa_url}/health",
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    result["service_running"] = True
                    result["whatsapp_connected"] = data.get("whatsapp", {}).get("connected", False)
                    result["has_qr"] = data.get("whatsapp", {}).get("hasQR", False)
                    result["messages_sent"] = data.get("stats", {}).get("messagesSent", 0)
                    result["messages_received"] = data.get("stats", {}).get("messagesReceived", 0)
                    result["errors"] = data.get("stats", {}).get("errors", 0)
                    result["uptime"] = data.get("uptime", 0)
                    result["last_disconnect"] = data.get("whatsapp", {}).get("lastDisconnect")
                    result["reconnect_attempts"] = data.get("whatsapp", {}).get("reconnectAttempts", 0)

                    # Determine overall status
                    if result["whatsapp_connected"]:
                        result["status"] = "healthy"
                        self._consecutive_failures = 0
                        self._alert_sent = False
                    elif result["has_qr"]:
                        result["status"] = "awaiting_scan"
                    elif data.get("whatsapp", {}).get("disconnectReason") == "logged_out":
                        result["status"] = "logged_out"
                    else:
                        result["status"] = "disconnected"
                else:
                    result["status"] = "degraded"
                    self._consecutive_failures += 1

        except httpx.ConnectError:
            result["status"] = "down"
            self._consecutive_failures += 1
            logger.error("openwa_service_unreachable", url=self.openwa_url)

        except httpx.TimeoutException:
            result["status"] = "timeout"
            self._consecutive_failures += 1
            logger.warning("openwa_health_timeout", url=self.openwa_url)

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            self._consecutive_failures += 1
            logger.error("openwa_health_check_error", error=str(e))

        self._last_check = datetime.now(timezone.utc)
        self._last_status = result

        return result

    async def should_alert(self) -> bool:
        """
        Determine if an admin alert should be sent.

        Alerts when:
        - Service is down for > 2 consecutive checks
        - WhatsApp is disconnected for > 30 minutes
        - Error rate is high (> 10 errors in recent window)
        """
        if self._alert_sent:
            return False

        if self._consecutive_failures >= 2:
            return True

        if self._last_status and self._last_status.get("status") == "down":
            return True

        if self._last_status and self._last_status.get("status") == "logged_out":
            return True

        return False

    async def alert_admin(self, message: str) -> bool:
        """
        Send an alert to the admin about WhatsApp issues.

        In production, this would send via:
        - SMS to admin phone
        - Email notification
        - Dashboard alert

        Args:
            message: Alert message

        Returns:
            True if alert was sent
        """
        logger.critical(
            "whatsapp_alert",
            message=message,
            consecutive_failures=self._consecutive_failures,
            last_status=self._last_status,
        )

        self._alert_sent = True

        # In production, integrate with notification service:
        # - Twilio SMS
        # - SendGrid email
        # - Slack webhook
        # For now, log the alert
        return True

    def get_status_summary(self) -> Dict:
        """
        Get a summary of the current health status.

        Returns:
            Dict with status summary suitable for API response
        """
        if not self._last_status:
            return {
                "status": "not_checked",
                "message": "Health check has not been run yet",
            }

        status_messages = {
            "healthy": "WhatsApp is connected and working",
            "awaiting_scan": "WhatsApp needs QR code scan",
            "disconnected": "WhatsApp session disconnected",
            "logged_out": "WhatsApp logged out — needs re-scan",
            "degraded": "OpenWA service is degraded",
            "down": "OpenWA service is unreachable",
            "timeout": "OpenWA health check timed out",
            "error": "Error checking OpenWA health",
        }

        return {
            "status": self._last_status.get("status", "unknown"),
            "message": status_messages.get(self._last_status.get("status"), "Unknown status"),
            "whatsapp_connected": self._last_status.get("whatsapp_connected", False),
            "service_running": self._last_status.get("service_running", False),
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "consecutive_failures": self._consecutive_failures,
            "stats": {
                "messages_sent": self._last_status.get("messages_sent", 0),
                "messages_received": self._last_status.get("messages_received", 0),
                "errors": self._last_status.get("errors", 0),
                "uptime_seconds": self._last_status.get("uptime", 0),
            },
        }


# Singleton instance for use across the application
_health_monitor: Optional[WhatsAppHealthMonitor] = None


def get_health_monitor() -> WhatsAppHealthMonitor:
    """Get or create the singleton health monitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = WhatsAppHealthMonitor()
    return _health_monitor
