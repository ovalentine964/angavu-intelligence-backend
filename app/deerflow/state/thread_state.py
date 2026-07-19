"""
Thread State — Core state object for DeerFlow agent conversations.

Represents the full state of a conversation thread including
messages, tool calls, metadata, and intelligence products.
Used by StatePersistence for checkpoint/restore.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.deerflow.state.reducers import reduce_state


@dataclass
class ThreadState:
    """
    Core state for a DeerFlow conversation thread.

    This is the state schema passed to LangGraph's StateGraph.
    All fields use reducers for concurrent update handling.
    """

    thread_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    delegations: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    intelligence_products: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    current_agent: str = ""
    plan: dict[str, Any] | None = None
    todos: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def serialize(self) -> str:
        """Serialize state to JSON string for persistence."""
        return json.dumps({
            "thread_id": self.thread_id,
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "metadata": self.metadata,
            "delegations": self.delegations,
            "artifacts": self.artifacts,
            "intelligence_products": self.intelligence_products,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_agent": self.current_agent,
            "plan": self.plan,
            "todos": self.todos,
            "error": self.error,
        }, default=str)

    @classmethod
    def deserialize(cls, data: str) -> ThreadState:
        """Deserialize state from JSON string."""
        parsed = json.loads(data)
        return cls(
            thread_id=parsed.get("thread_id", uuid.uuid4().hex[:16]),
            messages=parsed.get("messages", []),
            tool_calls=parsed.get("tool_calls", []),
            metadata=parsed.get("metadata", {}),
            delegations=parsed.get("delegations", []),
            artifacts=parsed.get("artifacts", []),
            intelligence_products=parsed.get("intelligence_products", []),
            created_at=parsed.get("created_at", time.time()),
            updated_at=parsed.get("updated_at", time.time()),
            current_agent=parsed.get("current_agent", ""),
            plan=parsed.get("plan"),
            todos=parsed.get("todos", []),
            error=parsed.get("error"),
        )

    def apply_update(self, updates: dict[str, Any]) -> ThreadState:
        """Apply state updates using reducers and return new state."""
        new_data = reduce_state(self.__dict__.copy(), updates)
        return ThreadState(**{k: v for k, v in new_data.items() if k in ThreadState.__dataclass_fields__})

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add a message to the thread."""
        self.messages.append({
            "message_id": uuid.uuid4().hex[:12],
            "role": role,
            "content": content,
            "timestamp": time.time(),
            **kwargs,
        })
        self.updated_at = time.time()

    def get_last_user_message(self) -> str | None:
        """Get the content of the last user message."""
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                return msg.get("content")
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "thread_id": self.thread_id,
            "message_count": len(self.messages),
            "tool_call_count": len(self.tool_calls),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_agent": self.current_agent,
            "has_plan": self.plan is not None,
            "error": self.error,
        }
