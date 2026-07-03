"""
State Persistence — Save/restore thread state to disk or database.

Provides:
- File-based persistence (JSON files)
- In-memory persistence (for testing)
- Database persistence (SQLAlchemy, future)

DeerFlow pattern: The checkpointer saves state after each agent step,
enabling crash recovery and conversation resumption.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CheckpointRecord:
    """A checkpoint record for a thread state."""
    checkpoint_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    thread_id: str = ""
    state_data: str = ""  # Serialized state
    created_at: float = field(default_factory=time.time)
    step_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "thread_id": self.thread_id,
            "created_at": self.created_at,
            "step_index": self.step_index,
            "metadata": self.metadata,
            "state_size_bytes": len(self.state_data),
        }


class StatePersistence:
    """
    Thread state persistence layer.

    Supports:
    - File-based: saves state as JSON files
    - In-memory: keeps state in a dictionary (for testing)
    - Hybrid: in-memory with optional file backup

    Usage:
        persistence = StatePersistence(storage_dir="./checkpoints")
        persistence.save(state)
        restored = persistence.load(thread_id)
    """

    def __init__(
        self,
        name: str = "StatePersistence",
        storage_dir: Optional[str] = None,
        max_checkpoints_per_thread: int = 10,
    ):
        self.name = name
        self._storage_dir = Path(storage_dir) if storage_dir else None
        self._max_checkpoints = max_checkpoints_per_thread
        self._memory_store: Dict[str, List[CheckpointRecord]] = {}
        self._logger = logger.bind(component="state_persistence")

        if self._storage_dir:
            self._storage_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: Any) -> CheckpointRecord:
        """
        Save a thread state as a checkpoint.

        Args:
            state: ThreadState or BiasharaThreadState instance

        Returns:
            CheckpointRecord with checkpoint ID
        """
        thread_id = state.thread_id
        state_data = state.serialize()

        # Get current step index
        existing = self._memory_store.get(thread_id, [])
        step_index = len(existing)

        record = CheckpointRecord(
            thread_id=thread_id,
            state_data=state_data,
            step_index=step_index,
        )

        # Store in memory
        if thread_id not in self._memory_store:
            self._memory_store[thread_id] = []
        self._memory_store[thread_id].append(record)

        # Trim old checkpoints
        if len(self._memory_store[thread_id]) > self._max_checkpoints:
            self._memory_store[thread_id] = self._memory_store[thread_id][-self._max_checkpoints:]

        # Persist to disk if configured
        if self._storage_dir:
            self._persist_checkpoint(record)

        self._logger.info(
            "state_saved",
            thread_id=thread_id,
            checkpoint_id=record.checkpoint_id,
            step_index=step_index,
            state_size=len(state_data),
        )

        return record

    def load(
        self,
        thread_id: str,
        checkpoint_id: Optional[str] = None,
        state_class: Any = None,
    ) -> Optional[Any]:
        """
        Load a thread state from a checkpoint.

        Args:
            thread_id: Thread ID to load
            checkpoint_id: Specific checkpoint (latest if None)
            state_class: Class to deserialize into (ThreadState if None)

        Returns:
            Restored state, or None if not found
        """
        if state_class is None:
            from app.deerflow.state.thread_state import ThreadState
            state_class = ThreadState

        # Try memory first
        records = self._memory_store.get(thread_id, [])

        # Try disk if no memory records
        if not records and self._storage_dir:
            records = self._load_from_disk(thread_id)

        if not records:
            self._logger.warning("no_checkpoints_found", thread_id=thread_id)
            return None

        # Find the right checkpoint
        if checkpoint_id:
            record = next(
                (r for r in records if r.checkpoint_id == checkpoint_id),
                None,
            )
        else:
            record = records[-1]  # Latest

        if not record:
            return None

        try:
            state = state_class.deserialize(record.state_data)
            self._logger.info(
                "state_loaded",
                thread_id=thread_id,
                checkpoint_id=record.checkpoint_id,
            )
            return state
        except Exception as exc:
            self._logger.error(
                "state_load_failed",
                thread_id=thread_id,
                error=str(exc),
            )
            return None

    def list_checkpoints(self, thread_id: str) -> List[Dict[str, Any]]:
        """List all checkpoints for a thread."""
        records = self._memory_store.get(thread_id, [])
        if not records and self._storage_dir:
            records = self._load_from_disk(thread_id)
        return [r.to_dict() for r in records]

    def delete_thread(self, thread_id: str) -> bool:
        """Delete all checkpoints for a thread."""
        deleted = False

        if thread_id in self._memory_store:
            del self._memory_store[thread_id]
            deleted = True

        if self._storage_dir:
            for filepath in self._storage_dir.glob(f"{thread_id}_*.json"):
                filepath.unlink()
                deleted = True

        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """Get persistence statistics."""
        total_checkpoints = sum(len(records) for records in self._memory_store.values())
        return {
            "total_threads": len(self._memory_store),
            "total_checkpoints": total_checkpoints,
            "storage_dir": str(self._storage_dir) if self._storage_dir else None,
        }

    def _persist_checkpoint(self, record: CheckpointRecord) -> None:
        """Persist checkpoint to disk."""
        if not self._storage_dir:
            return
        try:
            filepath = self._storage_dir / f"{record.thread_id}_{record.checkpoint_id}.json"
            filepath.write_text(json.dumps({
                "checkpoint_id": record.checkpoint_id,
                "thread_id": record.thread_id,
                "state_data": record.state_data,
                "created_at": record.created_at,
                "step_index": record.step_index,
                "metadata": record.metadata,
            }, default=str))
        except Exception as exc:
            self._logger.warning("checkpoint_persist_failed", error=str(exc))

    def _load_from_disk(self, thread_id: str) -> List[CheckpointRecord]:
        """Load checkpoints from disk for a thread."""
        if not self._storage_dir:
            return []
        records = []
        try:
            for filepath in sorted(self._storage_dir.glob(f"{thread_id}_*.json")):
                data = json.loads(filepath.read_text())
                records.append(CheckpointRecord(
                    checkpoint_id=data["checkpoint_id"],
                    thread_id=data["thread_id"],
                    state_data=data["state_data"],
                    created_at=data.get("created_at", 0),
                    step_index=data.get("step_index", 0),
                    metadata=data.get("metadata", {}),
                ))
        except Exception as exc:
            self._logger.warning("checkpoint_load_failed", error=str(exc))
        return records
