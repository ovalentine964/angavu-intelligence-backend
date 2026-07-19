"""
DeerFlow State Management.

Provides:
- ThreadState: Core state object for agent conversations
- StatePersistence: Checkpoint/restore for crash recovery
- Reducers: Merge functions for concurrent state updates
"""

from app.deerflow.state.persistence import CheckpointRecord, StatePersistence
from app.deerflow.state.reducers import (
    ReducerRegistry,
    merge_messages,
    merge_metadata,
    merge_tool_results,
    reduce_state,
)
from app.deerflow.state.thread_state import ThreadState

__all__ = [
    "CheckpointRecord",
    "ReducerRegistry",
    "StatePersistence",
    "ThreadState",
    "merge_messages",
    "merge_metadata",
    "merge_tool_results",
    "reduce_state",
]
