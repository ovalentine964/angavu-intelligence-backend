"""
USSD Trigger — Factor 11: Trigger from Anywhere.

USSD menu system for feature phone users. No internet required.
Provides structured menu navigation for business operations.

Flow:
    USSD Gateway → POST /ussd → USSDTrigger.receive() → TriggerIntent
    TriggerResponse → USSDTrigger.send() → USSD Gateway → Feature Phone

USSD Menu Structure:
    *123# → Angavu Intelligence
    1. Record Sale
    2. Check Balance
    3. Today's Sales
    4. Stock Check
    5. Help
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.triggers.base import (
    BaseTrigger,
    IntentType,
    TriggerChannel,
    TriggerIntent,
    TriggerResponse,
)

logger = structlog.get_logger(__name__)


# USSD menu tree
USSD_MENU = {
    "root": {
        "text": "Welcome to Angavu Intelligence\n"
                "1. Record Sale\n"
                "2. Check Balance\n"
                "3. Today's Sales\n"
                "4. Stock\n"
                "5. Profit\n"
                "6. Report\n"
                "7. Help\n"
                "0. Exit",
        "options": {
            "1": "record_sale",
            "2": "check_balance",
            "3": "check_sales",
            "4": "check_stock",
            "5": "check_profit",
            "6": "check_report",
            "7": "help",
            "0": "exit",
        },
    },
    "record_sale": {
        "text": "Record a Sale\n"
                "Enter item and amount\n"
                "Example: nyanya 500\n"
                "Or: tomatoes 500",
        "free_text": True,
        "intent": IntentType.RECORD_SALE,
    },
    "check_balance": {
        "text": "Checking your balance...",
        "intent": IntentType.CHECK_BALANCE,
    },
    "check_sales": {
        "text": "Sales Period:\n"
                "1. Today\n"
                "2. Yesterday\n"
                "3. This Week\n"
                "4. This Month\n"
                "0. Back",
        "options": {
            "1": "sales_today",
            "2": "sales_yesterday",
            "3": "sales_week",
            "4": "sales_month",
            "0": "root",
        },
    },
    "sales_today": {
        "text": "Fetching today's sales...",
        "intent": IntentType.CHECK_SALES,
        "data": {"timeframe": "today"},
    },
    "sales_yesterday": {
        "text": "Fetching yesterday's sales...",
        "intent": IntentType.CHECK_SALES,
        "data": {"timeframe": "yesterday"},
    },
    "sales_week": {
        "text": "Fetching this week's sales...",
        "intent": IntentType.CHECK_SALES,
        "data": {"timeframe": "week"},
    },
    "sales_month": {
        "text": "Fetching this month's sales...",
        "intent": IntentType.CHECK_SALES,
        "data": {"timeframe": "month"},
    },
    "check_stock": {
        "text": "Checking your stock...",
        "intent": IntentType.CHECK_STOCK,
    },
    "check_profit": {
        "text": "Checking your profit...",
        "intent": IntentType.CHECK_PROFIT,
    },
    "check_report": {
        "text": "Generating report...",
        "intent": IntentType.CHECK_REPORT,
    },
    "help": {
        "text": "Angavu Intelligence Help\n"
                "- Record sales, purchases, expenses\n"
                "- Check balance, stock, profit\n"
                "- View daily/weekly reports\n"
                "- Voice: Call *123*1#\n"
                "- WhatsApp: Send 'Help'\n"
                "\n0. Back",
        "options": {"0": "root"},
    },
    "exit": {
        "text": "Thank you for using Angavu Intelligence!\n"
                "Have a profitable day! 📈",
        "session_end": True,
    },
}


class USSDSession:
    """Manages a USSD session with menu navigation state."""

    def __init__(self, session_id: str, phone_number: str):
        self.session_id = session_id
        self.phone_number = phone_number
        self.current_menu = "root"
        self.history: list[str] = ["root"]
        self.collected_data: dict[str, Any] = {}
        self.free_text_mode = False

    def navigate(self, input_text: str) -> tuple[str, dict[str, Any]]:
        """
        Process USSD input and return (menu_key, data).

        Returns the next menu node and any collected data.
        """
        menu_node = USSD_MENU.get(self.current_menu, USSD_MENU["root"])

        # Handle free text input
        if self.free_text_mode:
            self.collected_data["raw_input"] = input_text
            self.free_text_mode = False
            intent = menu_node.get("intent", IntentType.UNKNOWN)
            data = {**menu_node.get("data", {}), **self.collected_data}
            return self.current_menu, data

        # Handle menu option selection
        options = menu_node.get("options", {})
        if input_text in options:
            next_menu = options[input_text]

            if next_menu == "exit":
                return "exit", {}

            if next_menu == "root":
                self.current_menu = "root"
                self.history = ["root"]
                self.collected_data = {}
                return "root", {}

            self.current_menu = next_menu
            self.history.append(next_menu)

            # Check if this is a terminal node with intent
            next_node = USSD_MENU.get(next_menu, {})
            if next_node.get("free_text"):
                self.free_text_mode = True
            elif "intent" in next_node:
                return next_menu, next_node.get("data", {})

            return next_menu, {}

        # Invalid input — stay on current menu
        return self.current_menu, {"error": "invalid_option"}


class USSDTrigger(BaseTrigger):
    """
    USSD trigger for feature phone users.

    Handles the USSD session lifecycle:
    - Session creation on first request
    - Menu navigation
    - Intent extraction from menu selections
    - Free text input for transaction recording
    - Session timeout (USSD sessions expire after ~180s)
    """

    def __init__(self):
        super().__init__()
        self._sessions: dict[str, USSDSession] = {}

    def get_channel(self) -> TriggerChannel:
        return TriggerChannel.USSD

    async def receive(self, raw_input: Any) -> TriggerIntent:
        """
        Parse USSD input into a TriggerIntent.

        Args:
            raw_input: Dict with keys:
                - session_id: USSD session ID
                - phone_number: Caller's phone number
                - text: USSD input text (empty for initial request)
                - service_code: USSD service code (e.g., *123#)
        """
        if isinstance(raw_input, dict):
            session_id = raw_input.get("session_id", "")
            phone_number = raw_input.get("phone_number", "")
            text = raw_input.get("text", "")
            service_code = raw_input.get("service_code", "")
        else:
            session_id = getattr(raw_input, "session_id", "")
            phone_number = getattr(raw_input, "phone_number", "")
            text = getattr(raw_input, "text", "")
            service_code = getattr(raw_input, "service_code", "")

        # Get or create USSD session
        if session_id not in self._sessions:
            self._sessions[session_id] = USSDSession(session_id, phone_number)

        session = self._sessions[session_id]

        # Parse input through menu navigation
        menu_key, data = session.navigate(text)

        # Get the menu node for intent extraction
        menu_node = USSD_MENU.get(menu_key, USSD_MENU["root"])
        intent_type = menu_node.get("intent", IntentType.UNKNOWN)

        # For free text input, parse the transaction
        if "raw_input" in data:
            parsed = self._parse_free_text(data["raw_input"])
            intent_type = parsed.get("intent", intent_type)
            data.update(parsed.get("data", {}))

        # Create session in base class
        base_session_id = f"ussd:{session_id}"
        self.get_session(base_session_id)

        intent = TriggerIntent(
            intent_type=intent_type,
            raw_input=text or "[INITIAL]",
            channel=TriggerChannel.USSD,
            user_id=phone_number,
            session_id=base_session_id,
            language="sw",  # USSD defaults to Swahili
            extracted_data=data,
            metadata={
                "ussd_session_id": session_id,
                "service_code": service_code,
                "menu_key": menu_key,
                "menu_history": session.history,
            },
            confidence=0.95,  # USSD selections are high confidence
        )

        self._logger.info(
            "ussd_intent_parsed",
            phone=phone_number[:6] + "****",
            menu=menu_key,
            intent=intent_type.value,
        )

        return intent

    async def send(
        self,
        response: TriggerResponse,
        user_id: str,
        session_id: str | None = None,
    ) -> bool:
        """
        Send USSD response back to the gateway.

        For USSD, the response text is returned directly to the
        USSD gateway, which displays it on the feature phone.

        Returns:
            True (USSD responses are synchronous)
        """
        self._logger.info(
            "ussd_response_sent",
            to=user_id[:6] + "****",
            length=len(response.text),
        )

        if response.session_end and session_id:
            # Clean up USSD session
            ussd_session_id = session_id.replace("ussd:", "")
            self._sessions.pop(ussd_session_id, None)
            self.end_session(session_id)

        return True

    def format_ussd_response(
        self,
        response: TriggerResponse,
        menu_key: str,
    ) -> str:
        """
        Format a response for USSD display.

        USSD screens are typically 160-182 characters.
        Must be concise and structured.
        """
        text = response.text

        # Truncate if too long for USSD
        if len(text) > 160:
            text = text[:157] + "..."

        # Add navigation hint
        if not response.session_end:
            text += "\n\n0. Menu"

        return text

    def _parse_free_text(self, text: str) -> dict[str, Any]:
        """Parse free text input (e.g., 'nyanya 500')."""
        # Pattern: item amount
        match = re.match(r'(\w+)\s+(\d+)', text.strip())
        if match:
            return {
                "intent": IntentType.RECORD_SALE,
                "data": {
                    "item": match.group(1),
                    "amount": match.group(2),
                },
            }

        return {
            "intent": IntentType.UNKNOWN,
            "data": {"raw": text},
        }
