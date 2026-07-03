"""
CommunicationAgent — Tier 3 utility agent for message formatting and delivery.

Handles message formatting, translation, and delivery across channels
(WhatsApp, SMS, email). Used by ReportGenerator and other agents.

Tier: 3 (Utility) — stateless, on-demand invocation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import structlog

from app.agents.base import (
    AgentDecision, AgentEvent, AgentResult, BiasharaAgent,
)

logger = structlog.get_logger(__name__)


class CommunicationAgent(BiasharaAgent):
    """
    Formats and routes messages to workers across communication channels.

    Capabilities:
    - Message formatting (WhatsApp, SMS, USSD)
    - Language translation (English, Swahili, Sheng)
    - Template rendering
    - Delivery tracking

    Tier: 3 (Utility) — stateless
    """

    name = "CommunicationAgent"
    role = "Communication and delivery specialist"
    tier = 3
    capabilities = [
        "message_formatting",
        "language_translation",
        "template_rendering",
        "whatsapp_delivery",
        "sms_delivery",
        "delivery_tracking",
    ]

    # Language templates
    TEMPLATES = {
        "en": {
            "greeting": "Hello {name}! 👋",
            "report_intro": "Here's your business intelligence report:",
            "profit": "💰 Profit: KSh {amount:,.0f}",
            "loss": "📉 Loss: KSh {amount:,.0f}",
            "recommendation": "💡 {title}: {message}",
            "footer": "Powered by Biashara Intelligence 🇰🇪",
        },
        "sw": {
            "greeting": "Habari {name}! 👋",
            "report_intro": "Hii ripoti ya biashara yako:",
            "profit": "💰 Faida: KSh {amount:,.0f}",
            "loss": "📉 Hasara: KSh {amount:,.0f}",
            "recommendation": "💡 {title}: {message}",
            "footer": "Imeendeshwa na Biashara Intelligence 🇰🇪",
        },
    }

    def __init__(self):
        super().__init__(name=self.name, role=self.role, capabilities=self.capabilities, tier=3)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event = context.get("event", {})
        payload = event.get("payload", {})
        action = payload.get("action", "format_message")

        if action in ("format_message", "format_report", "translate"):
            return AgentDecision(
                action="format_and_deliver",
                parameters={
                    "content": payload.get("content", {}),
                    "channel": payload.get("channel", "whatsapp"),
                    "language": payload.get("language", "en"),
                    "worker_name": payload.get("worker_name", "Biashara Owner"),
                    "template": payload.get("template", "report"),
                },
                confidence=0.95,
                reasoning="Formatting message for delivery",
            )
        return AgentDecision(action="noop", parameters={}, confidence=0.5, reasoning="No formatting requested")

    async def act(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        action = decision.action
        params = decision.parameters

        try:
            if action == "format_and_deliver":
                result = self._format_message(params)
                duration_ms = (time.time() - start) * 1000
                return AgentResult(success=True, data=result, duration_ms=duration_ms)
            elif action == "noop":
                return AgentResult(success=True, data=None, duration_ms=(time.time() - start) * 1000)
            else:
                return AgentResult(success=False, error=f"Unknown action: {action}", duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)

    def _format_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Format content into a channel-appropriate message."""
        content = params.get("content", {})
        channel = params.get("channel", "whatsapp")
        language = params.get("language", "en")
        worker_name = params.get("worker_name", "Biashara Owner")
        template = params.get("template", "report")

        templates = self.TEMPLATES.get(language, self.TEMPLATES["en"])

        parts = [templates["greeting"].format(name=worker_name)]
        parts.append(templates["report_intro"])

        # Format profit/loss
        profit = content.get("profit", content.get("total_profit", 0))
        if profit >= 0:
            parts.append(templates["profit"].format(amount=profit))
        else:
            parts.append(templates["loss"].format(amount=abs(profit)))

        # Format recommendations
        recs = content.get("recommendations", [])
        for rec in recs[:3]:
            parts.append(templates["recommendation"].format(
                title=rec.get("title", ""),
                message=rec.get("message", ""),
            ))

        parts.append(templates["footer"])

        formatted = "\n\n".join(parts)

        # Channel-specific formatting
        if channel == "sms":
            # SMS: truncate to 160 chars per segment
            formatted = formatted[:480]  # 3 SMS segments max
        elif channel == "ussd":
            # USSD: very short
            formatted = formatted[:180]

        return {
            "formatted_message": formatted,
            "channel": channel,
            "language": language,
            "char_count": len(formatted),
            "sms_segments": max(1, len(formatted) // 160 + (1 if len(formatted) % 160 else 0)) if channel == "sms" else None,
        }
