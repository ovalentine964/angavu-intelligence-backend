"""
DeerFlow State Management.

Provides:
- ThreadState: Core state object for agent conversations
- StatePersistence: Checkpoint/restore for crash recovery
- Reducers: Merge functions for concurrent state updates
"""

from app.deerflow.state.thread_state import ThreadState
from app.deerflow.state.persistence import StatePersistence, CheckpointRecord
from app.deerflow.state.reducers import (
    merge_messages,
    merge_tool_results,
    merge_metadata,
    reduce_state,
    ReducerRegistry,
)

__all__ = [
    "ThreadState",
    "StatePersistence",
    "CheckpointRecord",
    "merge_messages",
    "merge_tool_results",
    "merge_metadata",
    "reduce_state",
    "ReducerRegistry",
]
