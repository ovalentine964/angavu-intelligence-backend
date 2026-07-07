"""
WhatsApp Trigger — Factor 11: Trigger from Anywhere.

Integrates with WhatsApp Business API (via OpenWA) to receive
messages and send responses. Handles text, voice, and interactive
messages.

Flow:
    WhatsApp → OpenWA webhook → WhatsAppTrigger.receive() → TriggerIntent
    TriggerResponse → WhatsAppTrigger.send() → OpenWA API → WhatsApp
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

import structlog

from app.triggers.base import (
    BaseTrigger,
    IntentType,
    TriggerChannel,
    TriggerIntent,
    TriggerResponse,
)

logger = structlog.get_logger(__name__)


class WhatsAppTrigger(BaseTrigger):
    """
    WhatsApp Business API trigger.

    Receives messages via OpenWA webhook and sends responses
    back through the OpenWA API.

    Supported message types:
    - Text: Direct intent parsing
    - Voice: Transcribed text → intent parsing
    - Interactive: Button/list selections

    Intent patterns (Swahili + English):
    - "Nimeuza nyanya 500" → RECORD_SALE
    - "Salio" / "Balance" → CHECK_BALANCE
    - "Ripoti ya leo" → CHECK_REPORT
    - "Msaada" / "Help" → HELP
    """

    def __init__(self, openwa_url: str = "http://localhost:3000"):
        super().__init__()
        self.openwa_url = openwa_url
        self._intent_patterns = self._build_intent_patterns()

    def get_channel(self) -> TriggerChannel:
        return TriggerChannel.WHATSAPP

    async def receive(self, raw_input: Any) -> TriggerIntent:
        """
        Parse a WhatsApp message into a TriggerIntent.

        Args:
            raw_input: Dict with keys: from, body, type, media_url, etc.
        """
        if isinstance(raw_input, dict):
            from_number = raw_input.get("from", "")
            body = raw_input.get("body", "")
            msg_type = raw_input.get("type", "text")
            media_url = raw_input.get("media_url")
        else:
            # Assume it's already a parsed message object
            from_number = getattr(raw_input, "from_number", "")
            body = getattr(raw_input, "body", "")
            msg_type = getattr(raw_input, "type", "text")
            media_url = getattr(raw_input, "media_url", None)

        # Handle voice messages (already transcribed by OpenWA)
        text = body or ""
        if msg_type == "voice" and not text and media_url:
            # Voice without transcription — mark for external processing
            text = "[VOICE_MESSAGE]"
            self._logger.info("voice_message_received", from_number=from_number[:6])

        # Detect language
        language = self._detect_language(text)

        # Parse intent
        intent_type, extracted_data, confidence = self._parse_intent(text, language)

        # Get or create session
        session_id = f"wa:{from_number}"
        self.get_session(session_id)

        intent = TriggerIntent(
            intent_type=intent_type,
            raw_input=text,
            channel=TriggerChannel.WHATSAPP,
            user_id=from_number,
            session_id=session_id,
            language=language,
            extracted_data=extracted_data,
            metadata={
                "message_type": msg_type,
                "media_url": media_url,
            },
            confidence=confidence,
        )

        self._logger.info(
            "whatsapp_intent_parsed",
            from_number=from_number[:6] + "****",
            intent=intent_type.value,
            confidence=confidence,
        )

        return intent

    async def send(
        self,
        response: TriggerResponse,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Send a response back via WhatsApp (OpenWA API).

        Args:
            response: The agent's response
            user_id: WhatsApp phone number
            session_id: Session ID
        """
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.openwa_url}/send-message",
                    json={
                        "to": user_id,
                        "message": response.text,
                        "type": response.response_type,
                    },
                    timeout=30.0,
                )

                if resp.status_code == 200:
                    self._logger.info(
                        "whatsapp_response_sent",
                        to=user_id[:6] + "****",
                        length=len(response.text),
                    )

                    if response.session_end:
                        self.end_session(session_id or f"wa:{user_id}")

                    return True
                else:
                    self._logger.warning(
                        "whatsapp_send_failed",
                        status=resp.status_code,
                        to=user_id[:6] + "****",
                    )
                    return False

        except Exception as exc:
            self._logger.error(
                "whatsapp_send_error",
                error=str(exc),
                to=user_id[:6] + "****",
            )
            return False

    # ── Intent Parsing ──────────────────────────────────────────────

    def _parse_intent(
        self,
        text: str,
        language: str,
    ) -> tuple:
        """Parse intent from message text. Returns (intent_type, data, confidence)."""
        if not text or text == "[VOICE_MESSAGE]":
            return IntentType.UNKNOWN, {}, 0.5

        normalized = text.strip().lower()

        for pattern, intent_type, extractor in self._intent_patterns:
            match = pattern.search(normalized)
            if match:
                data = extractor(match, text)
                return intent_type, data, 0.9

        # Fallback: try to extract basic transaction info
        transaction_match = re.search(
            r'(\w+)\s+(\d+)',
            normalized,
        )
        if transaction_match:
            return IntentType.RECORD_SALE, {
                "item": transaction_match.group(1),
                "amount": transaction_match.group(2),
            }, 0.5

        return IntentType.UNKNOWN, {"raw": text}, 0.3

    def _build_intent_patterns(self):
        """Build intent matching patterns."""
        return [
            # Sales
            (re.compile(r'\b(nimeuza|nauza|sold|sell|record.*sale)\b'),
             IntentType.RECORD_SALE,
             lambda m, t: self._extract_transaction(t)),

            # Purchases
            (re.compile(r'\b(nimenunua|nunua|bought|buy|purchase)\b'),
             IntentType.RECORD_PURCHASE,
             lambda m, t: self._extract_transaction(t)),

            # Expenses
            (re.compile(r'\b(nimetumia|umetoa|spent|expense|cost)\b'),
             IntentType.RECORD_EXPENSE,
             lambda m, t: self._extract_transaction(t)),

            # Balance
            (re.compile(r'\b(salio|balance|pesa|money)\b'),
             IntentType.CHECK_BALANCE,
             lambda m, t: {}),

            # Sales check
            (re.compile(r'\b(nimeuza|sales|mauzo|leo|today).*\b(kiasi|how much|ngapi)\b'),
             IntentType.CHECK_SALES,
             lambda m, t: self._extract_timeframe(t)),

            # Stock
            (re.compile(r'\b(stock|inventory|bidhaa|goods|staki)\b'),
             IntentType.CHECK_STOCK,
             lambda m, t: {}),

            # Profit
            (re.compile(r'\b(faida|profit|margin|earnings)\b'),
             IntentType.CHECK_PROFIT,
             lambda m, t: self._extract_timeframe(t)),

            # Report
            (re.compile(r'\b(ripoti|report|summary)\b'),
             IntentType.CHECK_REPORT,
             lambda m, t: self._extract_timeframe(t)),

            # Help
            (re.compile(r'\b(msaada|help|menu|commands|saidia)\b'),
             IntentType.HELP,
             lambda m, t: {}),

            # Tithe
            (re.compile(r'\b(zakat|tithe|sadaka|church|mosque)\b'),
             IntentType.TITHE_RECORD,
             lambda m, t: self._extract_transaction(t)),

            # Goals
            (re.compile(r'\b(goal|target|kusudi|malengo)\b'),
             IntentType.GOAL_CREATE,
             lambda m, t: self._extract_transaction(t)),
        ]

    def _extract_transaction(self, text: str) -> Dict[str, Any]:
        """Extract transaction details from text."""
        data = {}

        # Extract amount (number pattern)
        amounts = re.findall(r'\b(\d+(?:,\d{3})*(?:\.\d+)?)\b', text)
        if amounts:
            data["amount"] = amounts[0].replace(",", "")

        # Extract item name (word before amount, or common patterns)
        item_match = re.search(
            r'(?:nimeuza|nauza|nimenunua|sold|bought)\s+(\w+)',
            text.lower(),
        )
        if item_match:
            data["item"] = item_match.group(1)

        return data

    def _extract_timeframe(self, text: str) -> Dict[str, Any]:
        """Extract timeframe from text."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["leo", "today"]):
            return {"timeframe": "today"}
        elif any(w in text_lower for w in ["jana", "yesterday"]):
            return {"timeframe": "yesterday"}
        elif any(w in text_lower for w in ["wiki", "week"]):
            return {"timeframe": "week"}
        elif any(w in text_lower for w in ["mwezi", "month"]):
            return {"timeframe": "month"}
        return {"timeframe": "today"}

    def _detect_language(self, text: str) -> str:
        """Detect language from text. Default to Swahili."""
        if not text:
            return "sw"

        text_lower = text.lower()

        # English indicators
        english_words = ["the", "and", "what", "how", "much", "today", "report", "help"]
        english_count = sum(1 for w in english_words if w in text_lower)

        # Swahili indicators
        swahili_words = ["nimeuza", "salio", "ripoti", "msaada", "leo", "jana", "faida"]
        swahili_count = sum(1 for w in swahili_words if w in text_lower)

        if english_count > swahili_count:
            return "en"
        return "sw"
