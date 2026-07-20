"""
BiasharaAgent — Memory & Tool Protocols.

AgentMemory: Short-term context + long-term knowledge storage.
AgentTools: Registry of tools available to an agent.
"""

from __future__ import annotations

import time
from typing import Any


# ════════════════════════════════════════════════════════════════════
# Memory & Tools
# ════════════════════════════════════════════════════════════════════


class AgentMemory:
    """
    Per-agent memory: short-term context + long-term knowledge.

    Short-term (context window):
        Recent events, current task state, last N results.
        Cleared between task cycles.

    Long-term (persistent):
        Learned patterns, performance metrics, feedback summaries.
        Persists across sessions.
    """

    def __init__(self, max_short_term: int = 50):
        self._short_term: list[dict[str, Any]] = []
        self._long_term: dict[str, Any] = {}
        self._max_short_term = max_short_term

    # ── Short-term ──────────────────────────────────────────────────

    def remember(self, item: dict[str, Any]) -> None:
        """Add an item to short-term memory."""
        self._short_term.append({**item, "_ts": time.time()})
        if len(self._short_term) > self._max_short_term:
            self._short_term = self._short_term[-self._max_short_term :]

    def recall_recent(self, n: int = 10) -> list[dict[str, Any]]:
        """Get the N most recent short-term memories."""
        return self._short_term[-n:]

    def clear_short_term(self) -> None:
        """Clear short-term memory (e.g. between task cycles)."""
        self._short_term.clear()

    # ── Long-term ───────────────────────────────────────────────────

    def store(self, key: str, value: Any) -> None:
        """Persist knowledge in long-term memory."""
        self._long_term[key] = value

    def retrieve(self, key: str, default: Any = None) -> Any:
        """Retrieve knowledge from long-term memory."""
        return self._long_term.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        """Full memory snapshot for debugging / observability."""
        return {
            "short_term_count": len(self._short_term),
            "short_term_recent": self._short_term[-5:],
            "long_term_keys": list(self._long_term.keys()),
        }


class AgentTools:
    """
    Registry of tools available to an agent.

    Tools are callables (sync or async) that an agent can invoke
    during its act phase. Each tool has a name and description
    for observability.
    """

    def __init__(self):
        self._tools: dict[str, Any] = {}
        self._descriptions: dict[str, str] = {}

    def register(self, name: str, fn: Any, description: str = "") -> None:
        """Register a tool for this agent."""
        self._tools[name] = fn
        self._descriptions[name] = description or name

    def get(self, name: str) -> Any:
        """Retrieve a registered tool."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """List all available tools with descriptions."""
        return [
            {"name": name, "description": self._descriptions.get(name, "")} for name in self._tools
        ]

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools
