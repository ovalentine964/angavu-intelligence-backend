"""
Sync service — Device-to-cloud synchronization with vector clocks.

Architecture: arch_backend.md §2.6
- Vector clock conflict detection
- Per-entity conflict resolution
- Deduplication via idempotency keys
"""
from datetime import UTC, datetime
from enum import Enum
from dataclasses import dataclass
from typing import Any, Optional
import uuid

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, Inventory
from app.models.user import User

logger = structlog.get_logger(__name__)


# ─── Vector Clock Logic ──────────────────────────────────────────────────────

class EntityType(str, Enum):
    TRANSACTION = "transaction"
    INVENTORY = "inventory"
    PREFERENCE = "preference"
    SKILL = "skill"
    EPISODE = "episode"
    GOAL = "goal"
    LOAN = "loan"


class ResolutionAction(str, Enum):
    MERGE = "merge"
    KEEP_LATEST = "keep_latest"
    ESCALATE = "escalate"


@dataclass
class ConflictResolution:
    action: ResolutionAction
    merged_data: Optional[dict] = None
    winner_data: Optional[dict] = None
    escalate_reason: Optional[str] = None


def is_conflicted(vc_local: dict, vc_remote: dict) -> bool:
    """Two vector clocks are conflicted (concurrent) if neither dominates."""
    if vc_local == vc_remote:
        return False
    all_keys = set(vc_local.keys()) | set(vc_remote.keys())
    local_before_remote = True
    remote_before_local = True
    strictly_less = False
    strictly_greater = False

    for key in all_keys:
        a = vc_local.get(key, 0)
        b = vc_remote.get(key, 0)
        if a > b:
            remote_before_local = False
            strictly_greater = True
        if a < b:
            local_before_remote = False
            strictly_less = True

    return not (local_before_remote and strictly_less) and \
           not (remote_before_local and strictly_greater)


def merge_clocks(vc_local: dict, vc_remote: dict) -> dict:
    """Merge two vector clocks — take the max of each component."""
    all_keys = set(vc_local.keys()) | set(vc_remote.keys())
    return {key: max(vc_local.get(key, 0), vc_remote.get(key, 0)) for key in all_keys}


# ─── Conflict Resolution ─────────────────────────────────────────────────────

class ConflictResolver:
    """Resolves sync conflicts based on entity type."""

    def resolve(
        self,
        entity_type: EntityType,
        local_data: dict,
        remote_data: dict,
        local_clock: dict,
        remote_clock: dict,
    ) -> ConflictResolution:
        if entity_type == EntityType.TRANSACTION:
            return ConflictResolution(
                action=ResolutionAction.MERGE,
                merged_data={"keep_both": True},
            )
        elif entity_type == EntityType.INVENTORY:
            return self._resolve_inventory(local_data, remote_data)
        elif entity_type in (EntityType.PREFERENCE, EntityType.SKILL, EntityType.EPISODE):
            return self._merge_union(local_data, remote_data)
        elif entity_type in (EntityType.GOAL, EntityType.LOAN):
            return self._resolve_stateful(local_data, remote_data, entity_type)
        return ConflictResolution(
            action=ResolutionAction.KEEP_LATEST,
            winner_data=local_data if local_data.get("timestamp", "") > remote_data.get("timestamp", "") else remote_data,
        )

    def _resolve_inventory(self, local: dict, remote: dict) -> ConflictResolution:
        local_qty = local.get("quantity", 0)
        remote_qty = remote.get("quantity", 0)
        expected = max(local_qty, remote_qty)
        delta = abs(local_qty - remote_qty)
        if expected > 0 and delta / expected > 0.20:
            return ConflictResolution(
                action=ResolutionAction.ESCALATE,
                escalate_reason=f"Stock mismatch: device={local_qty}, cloud={remote_qty}, delta={delta}",
            )
        winner = local if local.get("timestamp", "") > remote.get("timestamp", "") else remote
        return ConflictResolution(action=ResolutionAction.KEEP_LATEST, winner_data=winner)

    def _merge_union(self, local: dict, remote: dict) -> ConflictResolution:
        merged = {}
        all_keys = set(local.keys()) | set(remote.keys())
        for key in all_keys:
            l_val = local.get(key)
            r_val = remote.get(key)
            if l_val is None:
                merged[key] = r_val
            elif r_val is None:
                merged[key] = l_val
            else:
                merged[key] = l_val if local.get("timestamp", "") > remote.get("timestamp", "") else r_val
        return ConflictResolution(action=ResolutionAction.MERGE, merged_data=merged)

    def _resolve_stateful(self, local: dict, remote: dict, entity_type: EntityType) -> ConflictResolution:
        terminal_states = {"paid", "completed", "cancelled"}
        local_state = local.get("state", "")
        remote_state = remote.get("state", "")
        if (local_state in terminal_states) != (remote_state in terminal_states):
            return ConflictResolution(
                action=ResolutionAction.ESCALATE,
                escalate_reason=f"{entity_type.value} state conflict: device={local_state}, cloud={remote_state}",
            )
        winner = local if local.get("timestamp", "") > remote.get("timestamp", "") else remote
        return ConflictResolution(action=ResolutionAction.KEEP_LATEST, winner_data=winner)


# ─── Sync Processing ─────────────────────────────────────────────────────────

resolver = ConflictResolver()


async def process_sync_upload(
    db: AsyncSession,
    worker_id_hash: str,
    device_id: str,
    transactions: list[dict],
    vector_clock: dict,
) -> dict:
    """Process a sync upload from a device. Returns sync result."""
    conflicts = []
    synced_count = 0
    skipped_count = 0

    for tx_data in transactions:
        idempotency_key = tx_data.get("idempotency_key")
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())

        # Check for duplicate by idempotency key
        existing_row = await db.execute(
            select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        )
        existing_txn = existing_row.scalar_one_or_none()
        if existing_txn is not None:
            skipped_count += 1
            continue

        # ── Vector clock conflict detection ──────────────────────────────
        # remote_clock: the clock the device sent with this transaction
        # stored_clock: the clock we already have in the DB for this entity
        #   (empty dict if this entity is brand-new to us)
        entity_id = tx_data.get("id")
        remote_clock = tx_data.get("vector_clock", {}) or {}
        stored_clock: dict = {}

        # If the device sent an entity ID, look up the existing stored clock
        if entity_id:
            existing_entity = await db.execute(
                select(Transaction).where(
                    and_(
                        Transaction.user_id == worker_id_hash,
                        Transaction.id == entity_id,
                    )
                )
            )
            existing_entity_txn = existing_entity.scalar_one_or_none()
            if existing_entity_txn is not None:
                stored_clock = existing_entity_txn.vector_clock or {}

        # Determine if clocks are concurrent (conflicted)
        if stored_clock and is_conflicted(stored_clock, remote_clock):
            resolution = resolver.resolve(
                EntityType.TRANSACTION,
                {"stored": stored_clock, "entity_id": entity_id},
                {"remote": remote_clock, **tx_data},
                stored_clock,
                remote_clock,
            )
            if resolution.action == ResolutionAction.ESCALATE:
                conflicts.append({
                    "entity_type": "transaction",
                    "entity_id": entity_id,
                    "stored_clock": stored_clock,
                    "remote_clock": remote_clock,
                    "reason": resolution.escalate_reason,
                    "action": "escalate",
                })
                continue
            elif resolution.action == ResolutionAction.MERGE:
                conflicts.append({
                    "entity_type": "transaction",
                    "entity_id": entity_id,
                    "stored_clock": stored_clock,
                    "remote_clock": remote_clock,
                    "merged_data": resolution.merged_data,
                    "action": "merge",
                })
            elif resolution.action == ResolutionAction.KEEP_LATEST:
                conflicts.append({
                    "entity_type": "transaction",
                    "entity_id": entity_id,
                    "stored_clock": stored_clock,
                    "remote_clock": remote_clock,
                    "winner_data": resolution.winner_data,
                    "action": "keep_latest",
                })

        # Store the transaction with a properly merged clock
        merged_clock = merge_clocks(stored_clock, remote_clock)
        merged_clock = merge_clocks(merged_clock, {"backend:primary": 1})

        txn = Transaction(
            id=entity_id or str(uuid.uuid4()),
            user_id=worker_id_hash,
            idempotency_key=idempotency_key,
            tx_type=tx_data.get("tx_type", "sale"),
            amount=tx_data.get("amount", 0),
            currency=tx_data.get("currency", "KES"),
            description=tx_data.get("description"),
            product_name=tx_data.get("product_name"),
            product_category=tx_data.get("product_category"),
            quantity=tx_data.get("quantity", 1),
            payment_method=tx_data.get("payment_method", "cash"),
            location_geohash=tx_data.get("location_geohash"),
            vector_clock=merged_clock,
            device_timestamp=tx_data.get("device_timestamp"),
        )
        db.add(txn)
        synced_count += 1

    # Compute the backend clock as the total synced across all transactions
    backend_clock = {"backend:primary": synced_count}

    await db.flush()

    status = "ok"
    if conflicts:
        has_escalations = any(c["action"] == "escalate" for c in conflicts)
        status = "conflict" if has_escalations else "partial"

    return {
        "status": status,
        "synced_count": synced_count,
        "skipped_count": skipped_count,
        "conflicts": conflicts,
        "backend_clock": backend_clock,
        "intelligence_updates_available": True,
    }
