"""
BiasharaAgent — Backward-Compatible Re-Export Shim.

This module re-exports all public symbols from the decomposed modules:
- base_events.py    — Event types, message types, data classes
- base_protocols.py — AgentMemory, AgentTools
- base_agent.py     — BiasharaAgent base class

All existing imports from `app.agents.base` continue to work.
"""

from __future__ import annotations

# Re-export everything from the three decomposed modules
from app.agents.base_agent import BiasharaAgent
from app.agents.base_events import (
    AgentDecision,
    AgentEvent,
    AgentMessage,
    AgentResult,
    AgentStatus,
    EventType,
)
from app.agents.base_protocols import AgentMemory, AgentTools

__all__ = [
    "AgentDecision",
    "AgentEvent",
    "AgentMemory",
    "AgentMessage",
    "AgentResult",
    "AgentStatus",
    "AgentTools",
    "BiasharaAgent",
    "EventType",
]
