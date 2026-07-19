"""
WhatsApp Delivery Service — Sends reports via OpenWA.

Bridges the gap between intelligence generation (BriefingDelivery, worker_reports)
and actual delivery to workers via WhatsApp.

Flow:
    7 PM EAT cron → gather worker list → generate evening report per worker
    → POST to OpenWA /send-message → worker receives WhatsApp message

Supports:
    - Text messages (daily summaries, alerts)
    - Voice notes (for low-literacy workers)
    - Image attachments (charts, graphs)
    - PDF documents (formal reports)

Configuration:
    OPENWA_URL: URL of the OpenWA service (default: http://localhost:3000)
    OPENWA_ENABLED: Whether WhatsApp delivery is enabled (default: false)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# =========================================================================
# Configuration
# =========================================================================

# OpenWA service URL (internal Docker network or localhost)
OPENWA_URL = "http://localhost:3000"

# Maximum message length for WhatsApp (WhatsApp limit is ~65536 chars,
# but we keep it shorter for readability)
MAX_MESSAGE_LENGTH = 4000

# Rate limit: max messages per minute to avoid WhatsApp bans
RATE_LIMIT_PER_MINUTE = 20

# =========================================================================
# WhatsApp Delivery Service
# =========================================================================


class WhatsAppDelivery:
    """
    Delivers reports and briefings to workers via WhatsApp using OpenWA.

    Handles:
    - Text message delivery (daily summaries, alerts)
    - Voice note delivery (for low-literacy workers)
    - Image delivery (charts, graphs)
    - PDF delivery (formal reports)
    - Rate limiting (to avoid WhatsApp bans)
    - Retry logic with exponential backoff
    """

    def __init__(self, openwa_url: str = OPENWA_URL):
        self.openwa_url = openwa_url.rstrip("/")
        self._last_send_time: dict[str, float] = {}
        self._send_count: int = 0
        self._window_start: float = 0
        # Check if WhatsApp is enabled via settings
        try:
            from app.config import get_settings
            self.enabled = get_settings().ENABLE_WHATSAPP
        except Exception:
            self.enabled = False

    async def send_message(
        self,
        phone: str,
        message: str,
        retry_attempts: int = 3,
    ) -> bool:
        """
        Send a text message to a worker via WhatsApp.

        Args:
            phone: Phone number (will be normalized to digits only)
            message: Text message to send
            retry_attempts: Number of retry attempts on failure

        Returns:
            True if message was sent successfully
        """
        normalized = self._normalize_phone(phone)
        if not normalized:
            logger.error("invalid_phone", phone=phone)
            return False

        if not self.enabled:
            logger.debug("whatsapp_disabled_skip_delivery", phone=normalized[:6] + "****")
            return False

        # Truncate if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[:MAX_MESSAGE_LENGTH - 50] + "\n\n... (ripoti imefupishwa)"

        # Rate limiting
        if not self._check_rate_limit():
            logger.warning("rate_limited", phone=normalized[:6] + "****")
            await asyncio.sleep(60)  # Wait for rate limit window

        for attempt in range(retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{self.openwa_url}/send-message",
                        json={"to": normalized, "message": message},
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("sent"):
                            self._record_send(normalized)
                            logger.info(
                                "whatsapp_message_sent",
                                phone=normalized[:6] + "****",
                                length=len(message),
                                attempt=attempt + 1,
                            )
                            return True

                    logger.warning(
                        "whatsapp_send_failed",
                        status=response.status_code,
                        body=response.text[:200],
                        attempt=attempt + 1,
                    )

            except httpx.TimeoutException:
                logger.warning("whatsapp_timeout", attempt=attempt + 1)
            except Exception as e:
                logger.error(
                    "whatsapp_send_error",
                    error=str(e),
                    attempt=attempt + 1,
                )

            # Exponential backoff
            if attempt < retry_attempts - 1:
                await asyncio.sleep(2 ** attempt * 2)

        logger.error(
            "whatsapp_send_giveup",
            phone=normalized[:6] + "****",
            attempts=retry_attempts,
        )
        return False

    async def send_voice_note(
        self,
        phone: str,
        audio_base64: str,
        retry_attempts: int = 3,
    ) -> bool:
        """
        Send a voice note to a worker via WhatsApp.
        Used for low-literacy workers who prefer listening.

        Args:
            phone: Phone number
            audio_base64: Base64-encoded audio (MP4/AAC)
            retry_attempts: Number of retry attempts

        Returns:
            True if voice note was sent successfully
        """
        normalized = self._normalize_phone(phone)
        if not normalized:
            return False

        if not self._check_rate_limit():
            await asyncio.sleep(60)

        for attempt in range(retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{self.openwa_url}/send-voice",
                        json={"to": normalized, "audio": audio_base64},
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("sent"):
                            self._record_send(normalized)
                            logger.info(
                                "whatsapp_voice_sent",
                                phone=normalized[:6] + "****",
                            )
                            return True

            except Exception as e:
                logger.error("whatsapp_voice_error", error=str(e), attempt=attempt + 1)

            if attempt < retry_attempts - 1:
                await asyncio.sleep(2 ** attempt * 2)

        return False

    async def send_image(
        self,
        phone: str,
        image_base64: str,
        caption: str = "",
        retry_attempts: int = 3,
    ) -> bool:
        """
        Send an image with optional caption via WhatsApp.
        Used for chart/graph attachments in reports.

        Args:
            phone: Phone number
            image_base64: Base64-encoded image (PNG/JPEG)
            caption: Optional caption text
            retry_attempts: Number of retry attempts

        Returns:
            True if image was sent successfully
        """
        normalized = self._normalize_phone(phone)
        if not normalized:
            return False

        for attempt in range(retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{self.openwa_url}/send-image",
                        json={
                            "to": normalized,
                            "image": image_base64,
                            "caption": caption,
                        },
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if result.get("sent"):
                            self._record_send(normalized)
                            return True

            except Exception as e:
                logger.error("whatsapp_image_error", error=str(e), attempt=attempt + 1)

            if attempt < retry_attempts - 1:
                await asyncio.sleep(2 ** attempt * 2)

        return False

    async def send_evening_report(
        self,
        phone: str,
        worker_name: str,
        sales: float,
        profit: float,
        transaction_count: int,
        language: str = "sw",
        agent_name: str = "Msaidizi",
    ) -> bool:
        """
        Send the daily 7 PM evening report via WhatsApp.

        This is the main entry point for daily report delivery.
        Generates a formatted report and sends it as a WhatsApp message.

        Args:
            phone: Worker's WhatsApp phone number
            worker_name: Worker's name for personalization
            sales: Today's total sales
            profit: Today's total profit
            transaction_count: Number of transactions today
            language: Preferred language (sw/en)
            agent_name: What the worker calls the AI

        Returns:
            True if report was delivered successfully
        """
        from app.services.intelligence_delivery import get_greeting

        greeting = get_greeting(language)

        if language == "sw":
            message = self._build_swahili_evening_report(
                worker_name, agent_name, greeting, sales, profit, transaction_count
            )
        else:
            message = self._build_english_evening_report(
                worker_name, agent_name, greeting, sales, profit, transaction_count
            )

        return await self.send_message(phone, message)

    async def send_morning_briefing(
        self,
        phone: str,
        briefing_text: str,
    ) -> bool:
        """
        Send morning briefing via WhatsApp.
        Called by the cron scheduler at 7 AM EAT.

        Args:
            phone: Worker's WhatsApp phone number
            briefing_text: Pre-generated briefing text from BriefingDelivery

        Returns:
            True if briefing was delivered successfully
        """
        return await self.send_message(phone, briefing_text)

    async def send_alert(
        self,
        phone: str,
        alert_message: str,
    ) -> bool:
        """
        Send a proactive alert via WhatsApp.
        Called when CFOEngine detects an urgent condition.

        Args:
            phone: Worker's WhatsApp phone number
            alert_message: Alert message text

        Returns:
            True if alert was delivered successfully
        """
        return await self.send_message(phone, alert_message)

    async def check_openwa_status(self) -> dict[str, Any]:
        """
        Check if the OpenWA service is running and connected.

        Returns:
            Status dictionary with connection info
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.openwa_url}/status")
                if response.status_code == 200:
                    return response.json()
                return {"connected": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _build_swahili_evening_report(
        self,
        worker_name: str,
        agent_name: str,
        greeting: str,
        sales: float,
        profit: float,
        transaction_count: int,
    ) -> str:
        """Build Swahili evening report for WhatsApp."""
        from app.services.intelligence_delivery import format_currency_kes

        lines = [
            f"🌆 {greeting} {workerName}!",
            "",
            f"📊 Muhtasari wa leo ({datetime.now(UTC).strftime('%d/%m/%Y')}):",
            "",
            f"💰 Mauzo: {format_currency_kes(sales, 'sw')}",
            f"📈 Faida: {format_currency_kes(profit, 'sw')}",
            f"📋 Shughuli: {transaction_count}",
        ]

        if profit > 0:
            savings = (profit * 0.20)
            lines.append("")
            lines.append(f"💡 {agent_name} anapendekeza: Weka {format_currency_kes(savings, 'sw')} kwenye akiba ya dharura.")
        elif profit < 0:
            lines.append("")
            lines.append(f"💪 Leo haikuwa siku nzuri. Kesho ni nafasi mpya! {agent_name} ana imani na wewe.")

        lines.append("")
        lines.append("Usiku mwema! 🌙")

        return "\n".join(lines)

    def _build_english_evening_report(
        self,
        worker_name: str,
        agent_name: str,
        greeting: str,
        sales: float,
        profit: float,
        transaction_count: int,
    ) -> str:
        """Build English evening report for WhatsApp."""
        from app.services.intelligence_delivery import format_currency_kes

        lines = [
            f"🌆 {greeting} {worker_name}!",
            "",
            f"📊 Today's summary ({datetime.now(UTC).strftime('%d/%m/%Y')}):",
            "",
            f"💰 Sales: {format_currency_kes(sales, 'en')}",
            f"📈 Profit: {format_currency_kes(profit, 'en')}",
            f"📋 Transactions: {transaction_count}",
        ]

        if profit > 0:
            savings = (profit * 0.20)
            lines.append("")
            lines.append(f"💡 {agent_name} recommends: Save {format_currency_kes(savings, 'en')} for emergencies.")
        elif profit < 0:
            lines.append("")
            lines.append(f"💪 Today wasn't great. Tomorrow is a new opportunity! {agent_name} believes in you.")

        lines.append("")
        lines.append("Good night! 🌙")

        return "\n".join(lines)

    def _normalize_phone(self, phone: str) -> str | None:
        """
        Normalize phone number to digits-only format.
        Handles: 0712345678, +254712345678, 254712345678, 712345678
        Returns: 254712345678 or None if invalid
        """
        digits = "".join(c for c in phone if c.isdigit())

        if digits.startswith("254") and len(digits) == 12:
            return digits
        elif digits.startswith("0") and len(digits) == 10:
            return "254" + digits[1:]
        elif len(digits) == 9:
            return "254" + digits
        else:
            return None

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
        # Simple rate limiting: max RATE_LIMIT_PER_MINUTE per 60 seconds
        if now - self._window_start > 60:
            self._send_count = 0
            self._window_start = now
        return self._send_count < RATE_LIMIT_PER_MINUTE

    def _record_send(self, phone: str):
        """Record a successful send for rate limiting."""
        self._send_count += 1
        self._last_send_time[phone] = (
            asyncio.get_event_loop().time()
            if asyncio.get_event_loop().is_running()
            else 0
        )
