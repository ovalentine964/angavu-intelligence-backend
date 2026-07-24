"""
WhatsApp Report Handler — Processes incoming messages and delivers reports.

Handles WhatsApp messages from workers requesting business reports.
Integrates with OpenWA (Baileys) for message delivery.

Supported commands:
    "ripoti"           → Generate and send business report (Swahili)
    "report"           → Generate and send business report (English)
    "score"            → Send Alama Score summary
    "benki"            → Bank-ready formal report with QR code
    "ripoti ya benki"  → Same as "benki"
    "msaada"           → Help menu

Flow:
    Worker texts "nipatie ripoti ya benki"
    → Parse command
    → Fetch user from DB
    → Generate ReportData from transactions
    → Render bank-ready HTML template
    → Convert to PDF
    → Send PDF via OpenWA /send-media endpoint
    → Send confirmation text message
"""

from __future__ import annotations

import base64
import re
from datetime import date, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User

from .report_generator import WhatsAppReportGenerator
from .templates import ReportData, TemplateType

logger = structlog.get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Command Patterns
# ---------------------------------------------------------------------------

# Primary command patterns (Swahili + English)
COMMAND_PATTERNS = {
    "bank_report": r"(ripoti\s+ya\s+benki|bank\s*report|benki|nipatie\s+ripoti\s+ya\s+benki)",
    "report": r"(ripoti|report|muhtasari|summary)",
    "score": r"(score|alama|alama\s+score|pointi|credit\s*score)",
    "help": r"(msaada|help|amri|commands|saaide)",
}

# Sub-type patterns for report language detection
LANG_PATTERNS = {
    "en": r"\b(report|english|summary|bank)\b",
    "sw": r"\b(ripoti|benki|leo|wiki|mwezi|muhtasari)\b",
}

# Period patterns
PERIOD_PATTERNS = {
    7: r"\b(wiki|week|weekly|ya wiki)\b",
    30: r"\b(mwezi|month|monthly|ya mwezi)\b",
    90: r"\b(robo|quarter|quarterly|3\s*month)\b",
    180: r"\b(nusu\s*mwaka|semi|6\s*month)\b",
    365: r"\b(mwaka|year|annual|ya mwaka)\b",
}


# ---------------------------------------------------------------------------
# Response Messages
# ---------------------------------------------------------------------------

MESSAGES = {
    "sw": {
        "welcome": (
            "👋 *Karibu Angavu Intelligence!*\n\n"
            "Ninaweza kukusaidia na:\n"
            "📋 *ripoti* — Ripoti ya biashara yako\n"
            "🏦 *benki* — Ripoti ya benki (ya kutoa kwenye benki)\n"
            "📊 *score* — Alama Score yako\n"
            "❓ *msaada* — Orodha ya amri\n\n"
            "Tuma ujumbe mmoja kati ya haya!"
        ),
        "generating": "⏳ *Inaandaa ripoti yako...*\nTafadhali subiri dakika 1-2.",
        "generating_bank": "🏦 *Inaandaa ripoti ya benki...*\nRipoti hii ni ya kutoa Equity Bank. Subiri kidogo...",
        "score_only": "📊 *Alama Score yako*\n\n",
        "report_sent": "✅ *Ripoti imetumwa!*\n\nAngalia PDF iliyoambatishwa hapo juu.",
        "bank_sent": "✅ *Ripoti ya benki imetumwa!*\n\n📄 PDF imeambatishwa. Unaweza kuipakua na kupeleka benki.\n\n💡 *Dokezo:* Hakikisha una M-Pesa receipts za miezi 3 iliyopita kama uthibitisho.",
        "error": "😞 *Samahani, kuna hitilafu.*\n\nJaribu tena baada ya dakika chache. Tuma *msaada* kwa msaada zaidi.",
        "no_data": (
            "📭 *Hakuna data ya kutosha*\n\n"
            "Ripoti inahitaji angalau miamala 5 ya siku 7 zilizopita.\n"
            "Tafadhali rekodi miamala yako kwenye app ya Msaidizi kwanza."
        ),
        "help": (
            "📋 *Orodha ya Amri*\n\n"
            "• *ripoti* — Ripoti ya biashara (mwezi 1)\n"
            "• *benki* — Ripoti ya benki (PDF, QR code)\n"
            "• *score* — Alama Score yako (0-1000)\n"
            "• *ripoti ya wiki* — Ripoti ya wiki\n"
            "• *ripoti ya mwezi* — Ripoti ya mwezi\n"
            "• *msaada* — Orodha hii\n\n"
            "💡 Unaweza pia kutuma: *nipatie ripoti ya benki*"
        ),
    },
    "en": {
        "welcome": (
            "👋 *Welcome to Angavu Intelligence!*\n\n"
            "I can help you with:\n"
            "📋 *report* — Your business report\n"
            "🏦 *bank* — Bank-ready report (for loan applications)\n"
            "📊 *score* — Your Alama Score\n"
            "❓ *help* — List of commands\n\n"
            "Send any of these messages!"
        ),
        "generating": "⏳ *Generating your report...*\nPlease wait 1-2 minutes.",
        "generating_bank": "🏦 *Preparing bank report...*\nThis report is for Equity Bank. One moment...",
        "score_only": "📊 *Your Alama Score*\n\n",
        "report_sent": "✅ *Report sent!*\n\nCheck the PDF attachment above.",
        "bank_sent": "✅ *Bank report sent!*\n\n📄 PDF attached. Download and present at the bank.\n\n💡 *Tip:* Keep your M-Pesa receipts from the last 3 months as proof.",
        "error": "😞 *Sorry, something went wrong.*\n\nPlease try again in a few minutes. Send *help* for assistance.",
        "no_data": (
            "📭 *Not enough data*\n\n"
            "The report needs at least 5 transactions from the past 7 days.\n"
            "Please record your transactions in the Msaidizi app first."
        ),
        "help": (
            "📋 *Command List*\n\n"
            "• *report* — Business report (1 month)\n"
            "• *bank* — Bank report (PDF, QR code)\n"
            "• *score* — Your Alama Score (0-1000)\n"
            "• *weekly report* — Weekly report\n"
            "• *monthly report* — Monthly report\n"
            "• *help* — This list\n\n"
            "💡 You can also say: *send me the bank report*"
        ),
    },
}


# ---------------------------------------------------------------------------
# WhatsApp Report Handler
# ---------------------------------------------------------------------------

class WhatsAppReportHandler:
    """
    Handles incoming WhatsApp messages for report generation.

    Integrates with:
    - OpenWA (Baileys) for message sending via /send-media
    - SQLAlchemy async DB for user/transaction data
    - WhatsAppReportGenerator for PDF generation
    - AlamaScoreEngine for credit scoring
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.generator = WhatsAppReportGenerator(db)
        self.openwa_url = getattr(settings, "OPENWA_URL", "http://localhost:3000")
        self.enabled = getattr(settings, "ENABLE_WHATSAPP", True)

    # ======================================================================
    # Main Message Handler
    # ======================================================================

    async def process_message(
        self,
        phone: str,
        message: str,
        message_type: str = "text",
    ) -> str | None:
        """
        Process an incoming WhatsApp message and handle report requests.

        Args:
            phone: Sender's phone number
            message: Message text
            message_type: Type of message (text, voice, image)

        Returns:
            Response text (or None if handled asynchronously)
        """
        logger.info(
            "whatsapp_report_msg",
            phone=phone[:6] + "****",
            type=message_type,
            length=len(message),
        )

        # Normalize
        msg = message.strip().lower()

        # Find user
        user = await self._get_user_by_phone(phone)
        if not user:
            return MESSAGES["sw"]["welcome"]

        lang = self._detect_language(msg, user)

        # Parse command
        command = self._parse_command(msg)

        if command == "bank_report":
            return await self._handle_bank_report(user, msg, lang)
        elif command == "report":
            return await self._handle_report(user, msg, lang)
        elif command == "score":
            return await self._handle_score(user, lang)
        elif command == "help":
            return MESSAGES[lang]["help"]

        # No command matched
        return MESSAGES[lang]["welcome"]

    # ======================================================================
    # Command Handlers
    # ======================================================================

    async def _handle_bank_report(self, user: User, msg: str, lang: str) -> str:
        """Generate and send a bank-ready PDF report."""
        period = self._detect_period(msg)

        # Send "generating" notification
        generating_msg = MESSAGES[lang]["generating_bank"]

        try:
            # Generate the report
            pdf_bytes, filename, html = await self.generator.generate_report(
                user=user,
                template_type=TemplateType.BANK_READY,
                period_days=period,
                language=lang,
            )

            # Send PDF via WhatsApp
            sent = await self._send_document(
                phone=user.phone,
                document_bytes=pdf_bytes,
                filename=filename,
                caption=MESSAGES[lang]["bank_sent"],
            )

            if sent:
                # Also send a brief text summary
                report_data = await self.generator.build_report_data(user, period, lang)
                summary = self._build_score_summary(report_data, lang)
                await self._send_message(user.phone, summary)
                return None  # Already sent via direct WhatsApp
            else:
                return MESSAGES[lang]["error"]

        except Exception as e:
            logger.error("bank_report_error", error=str(e), user_id=user.id)
            return MESSAGES[lang]["error"]

    async def _handle_report(self, user: User, msg: str, lang: str) -> str:
        """Generate and send a personal business report."""
        period = self._detect_period(msg)

        try:
            pdf_bytes, filename, html = await self.generator.generate_report(
                user=user,
                template_type=TemplateType.PERSONAL_SUMMARY,
                period_days=period,
                language=lang,
            )

            sent = await self._send_document(
                phone=user.phone,
                document_bytes=pdf_bytes,
                filename=filename,
                caption=MESSAGES[lang]["report_sent"],
            )

            if sent:
                return None
            return MESSAGES[lang]["error"]

        except Exception as e:
            logger.error("report_error", error=str(e), user_id=user.id)
            return MESSAGES[lang]["error"]

    async def _handle_score(self, user: User, lang: str) -> str:
        """Send Alama Score summary as text (no PDF needed)."""
        try:
            report_data = await self.generator.build_report_data(user, period_days=90, language=lang)
            summary = self._build_score_summary(report_data, lang)
            return MESSAGES[lang]["score_only"] + summary
        except Exception as e:
            logger.error("score_error", error=str(e), user_id=user.id)
            return MESSAGES[lang]["error"]

    # ======================================================================
    # Score Summary Builder
    # ======================================================================

    def _build_score_summary(self, data: ReportData, lang: str) -> str:
        """Build a WhatsApp-friendly Alama Score summary."""
        score = data.alama_score
        band = data.alama_score_band.replace("_", " ").title() if data.alama_score_band else "N/A"
        grade = data.health_grade.value
        risk = data.risk_category.replace("_", " ").title() if data.risk_category else "N/A"

        # Score emoji
        if score >= 800:
            emoji = "🟢"
        elif score >= 700:
            emoji = "🟡"
        elif score >= 600:
            emoji = "🟠"
        else:
            emoji = "🔴"

        # Score bar (Unicode blocks)
        filled = int(score / 100)
        bar = "█" * filled + "░" * (10 - filled)

        if lang == "sw":
            return (
                f"{emoji} *Alama Score: {score}/1000*\n"
                f"*Band:* {band}\n"
                f"*Grade:* {grade}\n"
                f"*Risk:* {risk}\n\n"
                f"Score: [{bar}] {score}\n\n"
                f"*Mapato:* {data._fmt(data.total_revenue)}\n"
                f"*Faida:* {data._fmt(data.total_profit)}\n"
                f"*Margin:* {data.profit_margin_pct:.1f}%\n\n"
                f"💡 Tuma *benki* kupata ripoti kamili ya PDF."
            )
        else:
            return (
                f"{emoji} *Alama Score: {score}/1000*\n"
                f"*Band:* {band}\n"
                f"*Grade:* {grade}\n"
                f"*Risk:* {risk}\n\n"
                f"Score: [{bar}] {score}\n\n"
                f"*Revenue:* {data._fmt(data.total_revenue)}\n"
                f"*Profit:* {data._fmt(data.total_profit)}\n"
                f"*Margin:* {data.profit_margin_pct:.1f}%\n\n"
                f"💡 Send *bank* to get the full PDF report."
            )

    # ======================================================================
    # Command Parsing
    # ======================================================================

    def _parse_command(self, message: str) -> str | None:
        """Parse message to extract command. Bank report checked first."""
        for command, pattern in COMMAND_PATTERNS.items():
            if re.search(pattern, message, re.IGNORECASE):
                return command
        return None

    def _detect_language(self, message: str, user: User) -> str:
        """Detect language from message and user preference."""
        # Check message content first
        if re.search(LANG_PATTERNS["en"], message, re.IGNORECASE):
            return "en"
        if re.search(LANG_PATTERNS["sw"], message, re.IGNORECASE):
            return "sw"
        # Fall back to user preference
        return getattr(user, "language", "sw") or "sw"

    def _detect_period(self, message: str) -> int:
        """Detect requested time period from message."""
        for days, pattern in PERIOD_PATTERNS.items():
            if re.search(pattern, message, re.IGNORECASE):
                return days
        return 30  # Default: 1 month

    # ======================================================================
    # Database Helpers
    # ======================================================================

    async def _get_user_by_phone(self, phone: str) -> User | None:
        """Look up user by phone number hash."""
        import hashlib
        phone_hash = hashlib.sha256(phone.encode()).hexdigest()
        result = await self.db.execute(
            select(User).where(
                and_(User.phone_hash == phone_hash, User.is_active == True)
            )
        )
        return result.scalar_one_or_none()

    # ======================================================================
    # WhatsApp Delivery (OpenWA)
    # ======================================================================

    async def _send_message(self, phone: str, message: str) -> bool:
        """Send a text message via OpenWA."""
        if not self.enabled:
            logger.debug("whatsapp_disabled_skip")
            return False

        normalized = self._normalize_phone(phone)
        if not normalized:
            return False

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.openwa_url}/send-message",
                    json={"to": normalized, "message": message},
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("sent"):
                        logger.info("whatsapp_text_sent", phone=normalized[:6] + "****")
                        return True
                    if result.get("banDetected"):
                        logger.fatal("whatsapp_ban_detected")
                        return False
                logger.warning("whatsapp_send_failed", status=response.status_code)
                return False
        except Exception as e:
            logger.error("whatsapp_send_error", error=str(e))
            return False

    async def _send_document(
        self,
        phone: str,
        document_bytes: bytes,
        filename: str,
        caption: str = "",
    ) -> bool:
        """Send a PDF document via OpenWA /send-media endpoint."""
        if not self.enabled:
            logger.debug("whatsapp_disabled_skip_doc")
            return False

        normalized = self._normalize_phone(phone)
        if not normalized:
            return False

        # Encode PDF to base64
        doc_base64 = base64.b64encode(document_bytes).decode("utf-8")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.openwa_url}/send-media",
                    json={
                        "to": normalized,
                        "type": "document",
                        "base64": doc_base64,
                        "caption": caption,
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("sent"):
                        logger.info(
                            "whatsapp_doc_sent",
                            phone=normalized[:6] + "****",
                            filename=filename,
                            size_kb=len(document_bytes) // 1024,
                        )
                        return True
                    if result.get("banDetected"):
                        logger.fatal("whatsapp_ban_detected_on_doc")
                        return False

                logger.warning(
                    "whatsapp_doc_send_failed",
                    status=response.status_code,
                    body=response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("whatsapp_doc_send_error", error=str(e))
            return False

    async def _send_image(
        self,
        phone: str,
        image_bytes: bytes,
        caption: str = "",
    ) -> bool:
        """Send an image via OpenWA /send-media endpoint."""
        if not self.enabled:
            return False

        normalized = self._normalize_phone(phone)
        if not normalized:
            return False

        img_base64 = base64.b64encode(image_bytes).decode("utf-8")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.openwa_url}/send-media",
                    json={
                        "to": normalized,
                        "type": "image",
                        "base64": img_base64,
                        "caption": caption,
                    },
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("sent"):
                        logger.info("whatsapp_image_sent", phone=normalized[:6] + "****")
                        return True
                return False
        except Exception as e:
            logger.error("whatsapp_image_send_error", error=str(e))
            return False

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number to digits-only format."""
        digits = re.sub(r"[^\d]", "", phone)
        if not digits:
            return ""
        # Ensure Kenyan format: 254XXXXXXXXX
        if digits.startswith("0") and len(digits) == 10:
            digits = "254" + digits[1:]
        elif digits.startswith("+"):
            digits = digits[1:]
        # Basic validation: must be 12 digits (254 + 9)
        if len(digits) < 10 or len(digits) > 15:
            return ""
        return digits
