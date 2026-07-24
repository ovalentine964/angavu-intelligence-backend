"""USSD trigger stub."""
from __future__ import annotations

from typing import Any

from app.triggers._base import IntentType, TriggerIntent


class USSDTrigger:
    async def receive(self, data: dict[str, Any]) -> TriggerIntent:
        return TriggerIntent(
            intent_type=IntentType.COMMAND,
            extracted_data=data,
            metadata={"channel": "ussd", "menu_key": None},
        )
