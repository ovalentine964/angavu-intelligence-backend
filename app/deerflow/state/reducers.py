"""
State Reducers — Merge functions for concurrent state updates.

Reducers are functions that combine multiple state updates into
a single coherent state. They follow the Redux/Elm pattern:
    new_state = reducer(current_state, action)

DeerFlow uses reducers to handle:
- Multiple agents writing to the same state
- Parallel tool calls returning results
- Concurrent message additions
- Metadata merging from different sources
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def merge_messages(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge message lists, deduplicating by message_id.

    Appends new messages that don't already exist in existing.
    """
    existing_ids = {m.get("message_id") for m in existing}
    merged = list(existing)

    for msg in new:
        msg_id = msg.get("message_id")
        if msg_id and msg_id not in existing_ids:
            merged.append(msg)
            existing_ids.add(msg_id)
        elif not msg_id:
            # No ID — always append
            merged.append(msg)

    return merged


def merge_tool_results(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge tool call results, updating existing calls by call_id.

    If a tool call with the same call_id exists, update it.
    Otherwise, append the new call.
    """
    existing_by_id = {c.get("call_id"): i for i, c in enumerate(existing) if c.get("call_id")}
    merged = list(existing)

    for call in new:
        call_id = call.get("call_id")
        if call_id and call_id in existing_by_id:
            # Update existing
            idx = existing_by_id[call_id]
            merged[idx] = {**merged[idx], **call}
        else:
            # Append new
            merged.append(call)

    return merged


def merge_metadata(
    existing: dict[str, Any],
    new: dict[str, Any],
    strategy: str = "update",
) -> dict[str, Any]:
    """
    Merge metadata dictionaries.

    Strategies:
    - update: overwrite existing keys with new values
    - keep: only add keys that don't exist
    - deep: recursively merge nested dicts
    """
    if strategy == "update":
        return {**existing, **new}
    elif strategy == "keep":
        return {**new, **{k: v for k, v in existing.items() if k not in new}}
    elif strategy == "deep":
        return _deep_merge(existing, new)
    return {**existing, **new}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def reduce_state(
    current_state: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply state updates using appropriate reducers for each field.

    This is the main reducer function that handles all state fields.
    """
    result = dict(current_state)

    for key, value in updates.items():
        if key == "messages" and isinstance(value, list):
            result["messages"] = merge_messages(
                current_state.get("messages", []),
                value,
            )
        elif key == "tool_calls" and isinstance(value, list):
            result["tool_calls"] = merge_tool_results(
                current_state.get("tool_calls", []),
                value,
            )
        elif key == "metadata" and isinstance(value, dict):
            result["metadata"] = merge_metadata(
                current_state.get("metadata", {}),
                value,
            )
        elif key == "delegations" and isinstance(value, list):
            existing = current_state.get("delegations", [])
            result["delegations"] = existing + value
        elif key == "artifacts" and isinstance(value, list):
            existing = current_state.get("artifacts", [])
            result["artifacts"] = list(set(existing + value))
        elif key == "intelligence_products" and isinstance(value, list):
            existing = current_state.get("intelligence_products", [])
            result["intelligence_products"] = existing + value
        else:
            result[key] = value

    result["updated_at"] = time.time()
    return result


# ── Reducer Registry ──────────────────────────────────────────────


class ReducerRegistry:
    """
    Registry of field-specific reducers.

    Allows custom reducers to be registered for specific fields.
    """

    def __init__(self):
        self._reducers: dict[str, Callable] = {
            "messages": merge_messages,
            "tool_calls": merge_tool_results,
            "metadata": merge_metadata,
        }

    def register(self, field: str, reducer: Callable) -> None:
        """Register a custom reducer for a field."""
        self._reducers[field] = reducer

    def get(self, field: str) -> Callable | None:
        """Get the reducer for a field."""
        return self._reducers.get(field)

    def reduce(
        self,
        field: str,
        existing: Any,
        new: Any,
    ) -> Any:
        """Apply the reducer for a field."""
        reducer = self._reducers.get(field)
        if reducer:
            return reducer(existing, new)
        return new
