"""
SMS Trigger — Factor 11: Trigger from Anywhere.

SMS gateway integration for users without smartphones or internet.
Supports Africa's Talking, Twilio, and generic SMPP gateways.

Flow:
    SMS Gateway → POST /sms → SMSTrigger.receive() → TriggerIntent
    TriggerResponse → SMSTrigger.send() → SMS Gateway → User's Phone

SMS Commands:
    "SALE nyanya 500" → Record sale
    "BALANCE" → Check balance
    "SALES" → Today's sales
    "HELP" → Show commands
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

# SMS command patterns (case-insensitive)
SMS_COMMANDS = {
    # Sale: "SALE nyanya 500" or "SALE tomatoes 500 3"
    r'^sale\s+(\w+)\s+(\d+)(?:\s+(\d+))?\s*$': {
        "intent": IntentType.RECORD_SALE,
        "extractor": lambda m: {
            "item": m.group(1),
            "amount": m.group(2),
            "quantity": m.group(3) or "1",
        },
    },

    # Purchase: "BUY nyanya 500"
    r'^buy\s+(\w+)\s+(\d+)(?:\s+(\d+))?\s*$': {
        "intent": IntentType.RECORD_PURCHASE,
        "extractor": lambda m: {
            "item": m.group(1),
            "amount": m.group(2),
            "quantity": m.group(3) or "1",
        },
    },

    # Expense: "EXPENSE transport 200"
    r'^expense\s+(\w+)\s+(\d+)\s*$': {
        "intent": IntentType.RECORD_EXPENSE,
        "extractor": lambda m: {
            "category": m.group(1),
            "amount": m.group(2),
        },
    },

    # Balance
    r'^(balance|salio|pesa)\s*$': {
        "intent": IntentType.CHECK_BALANCE,
        "extractor": lambda m: {},
    },

    # Sales check
    r'^(sales|mauzo)(?:\s+(today|yesterday|week|month|leo|jana|wiki|mwezi))?\s*$': {
        "intent": IntentType.CHECK_SALES,
        "extractor": lambda m: {
            "timeframe": m.group(2) or "today",
        },
    },

    # Stock
    r'^(stock|inventory|bidhaa)\s*$': {
        "intent": IntentType.CHECK_STOCK,
        "extractor": lambda m: {},
    },

    # Profit
    r'^(profit|faida)(?:\s+(today|yesterday|week|month))?\s*$': {
        "intent": IntentType.CHECK_PROFIT,
        "extractor": lambda m: {
            "timeframe": m.group(2) or "today",
        },
    },

    # Report
    r'^(report|ripoti)\s*$': {
        "intent": IntentType.CHECK_REPORT,
        "extractor": lambda m: {},
    },

    # Help
    r'^(help|msaada|menu|commands)\s*$': {
        "intent": IntentType.HELP,
        "extractor": lambda m: {},
    },

    # Tithe
    r'^tithe\s+(\d+)\s*$': {
        "intent": IntentType.TITHE_RECORD,
        "extractor": lambda m: {"amount": m.group(1)},
    },
}


class SMSTrigger(BaseTrigger):
    """
    SMS trigger for users without internet access.

    Supports multiple SMS gateway providers:
    - Africa's Talking (primary for East Africa)
    - Twilio (global)
    - Generic SMPP

    SMS is stateless (no session), so each message is a complete
    command. Format: COMMAND [args...]
    """

    def __init__(self, gateway_provider: str = "africastalking"):
        super().__init__()
        self.gateway_provider = gateway_provider
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), spec)
            for pattern, spec in SMS_COMMANDS.items()
        ]

    def get_channel(self) -> TriggerChannel:
        return TriggerChannel.SMS

    async def receive(self, raw_input: Any) -> TriggerIntent:
        """
        Parse an SMS message into a TriggerIntent.

        Args:
            raw_input: Dict with keys:
                - from: Sender's phone number
                - to: Receiver's number (short code)
                - text: SMS body
                - id: SMS ID from gateway
                - date: Timestamp
                - gateway: Gateway provider name
        """
        if isinstance(raw_input, dict):
            from_number = raw_input.get("from", "")
            text = raw_input.get("text", "").strip()
            sms_id = raw_input.get("id", "")
            gateway_data = raw_input
        else:
            from_number = getattr(raw_input, "from_number", "")
            text = getattr(raw_input, "body", "").strip()
            sms_id = getattr(raw_input, "message_id", "")
            gateway_data = {"id": sms_id}

        # Parse command
        intent_type, extracted_data, confidence = self._parse_command(text)

        # SMS is stateless — create a one-shot session
        session_id = f"sms:{sms_id or from_number}"

        intent = TriggerIntent(
            intent_type=intent_type,
            raw_input=text,
            channel=TriggerChannel.SMS,
            user_id=from_number,
            session_id=session_id,
            language=self._detect_language(text),
            extracted_data=extracted_data,
            metadata={
                "sms_id": sms_id,
                "gateway": self.gateway_provider,
            },
            confidence=confidence,
        )

        self._logger.info(
            "sms_intent_parsed",
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
        Send an SMS response.

        SMS has a 160 character limit (or 70 for Unicode).
        Responses are truncated to fit.
        """
        # Truncate for SMS
        text = response.text
        if len(text) > 160:
            text = text[:157] + "..."

        try:
            await self._send_via_gateway(user_id, text)
            self._logger.info(
                "sms_response_sent",
                to=user_id[:6] + "****",
                length=len(text),
            )
            return True
        except Exception as exc:
            self._logger.error(
                "sms_send_error",
                error=str(exc),
                to=user_id[:6] + "****",
            )
            return False

    async def _send_via_gateway(self, to: str, text: str) -> None:
        """Send SMS via the configured gateway."""
        import httpx

        if self.gateway_provider == "africastalking":
            # Africa's Talking API
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://api.africastalking.com/version1/messaging",
                    headers={
                        "apiKey": "",  # Set from config
                        "Accept": "application/json",
                    },
                    data={
                        "username": "",
                        "to": to,
                        "message": text,
                    },
                    timeout=10.0,
                )
        elif self.gateway_provider == "twilio":
            # Twilio API
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://api.twilio.com/2010-04-01/Accounts//Messages.json",
                    data={
                        "To": to,
                        "From": "",  # Set from config
                        "Body": text,
                    },
                    auth=("", ""),  # Set from config
                    timeout=10.0,
                )
        else:
            # Generic — log and return
            self._logger.info("sms_generic_send", to=to, text=text)

    def _parse_command(self, text: str) -> tuple:
        """Parse SMS command. Returns (intent_type, data, confidence)."""
        if not text:
            return IntentType.UNKNOWN, {}, 0.0

        for pattern, spec in self._compiled_patterns:
            match = pattern.match(text)
            if match:
                data = spec["extractor"](match)
                return spec["intent"], data, 0.9

        # Fallback: try natural language
        return self._parse_natural_language(text)

    def _parse_natural_language(self, text: str) -> tuple:
        """Attempt natural language parsing for SMS without command prefix."""
        text_lower = text.lower()

        # "nimeuza nyanya 500" → sale
        sale_match = re.match(
            r'(?:nimeuza|nauza|sold)\s+(\w+)\s+(\d+)',
            text_lower,
        )
        if sale_match:
            return IntentType.RECORD_SALE, {
                "item": sale_match.group(1),
                "amount": sale_match.group(2),
            }, 0.7

        return IntentType.UNKNOWN, {"raw": text}, 0.3

    def _detect_language(self, text: str) -> str:
        """Detect language from SMS text."""
        if not text:
            return "sw"
        text_lower = text.lower()
        swahili_indicators = ["nimeuza", "salio", "ripoti", "msaada", "nimenunua"]
        if any(w in text_lower for w in swahili_indicators):
            return "sw"
        return "en"
