"""Base trigger intent and enum stubs."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    QUERY = "query"
    COMMAND = "command"
    TRANSACTION = "transaction"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class TriggerIntent:
    intent_type: IntentType = IntentType.UNKNOWN
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    extracted_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
