"""
SyncAgent — Tier 3 utility agent for data synchronization.

Handles data sync between local and cloud, conflict resolution for
offline-first scenarios, and cache management. Used by the sync API
and other agents that need data consistency.

Tier: 3 (Utility) — stateless, on-demand invocation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import (
    AgentDecision, AgentEvent, AgentResult, BiasharaAgent,
)

logger = structlog.get_logger(__name__)


class SyncAgent(BiasharaAgent):
    """
    Manages data synchronization between local devices and cloud.

    Capabilities:
    - Conflict detection and resolution
    - Delta sync (only changed records)
    - Batch sync optimization
    - Offline queue management
    - Cache invalidation

    Tier: 3 (Utility) — stateless
    """

    name = "SyncAgent"
    role = "Data synchronization specialist"
    tier = 3
    capabilities = [
        "data_sync",
        "conflict_resolution",
        "delta_sync",
        "batch_sync",
        "offline_queue",
        "cache_invalidation",
    ]

    def __init__(self):
        super().__init__(name=self.name, role=self.role, capabilities=self.capabilities)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event = context.get("event", {})
        payload = event.get("payload", {})
        action = payload.get("action", "sync")

        if action in ("sync", "resolve_conflicts", "delta_sync"):
            return AgentDecision(
                action=action,
                parameters={
                    "local_data": payload.get("local_data", []),
                    "cloud_data": payload.get("cloud_data", []),
                    "strategy": payload.get("strategy", "last_write_wins"),
                    "worker_id": payload.get("worker_id"),
                },
                confidence=0.9,
                reasoning=f"Running sync operation: {action}",
            )
        return AgentDecision(action="noop", parameters={}, confidence=0.5, reasoning="No sync requested")

    async def act(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        action = decision.action
        params = decision.parameters

        try:
            if action == "sync":
                result = self._full_sync(params)
            elif action == "resolve_conflicts":
                result = self._resolve_conflicts(params)
            elif action == "delta_sync":
                result = self._delta_sync(params)
            elif action == "noop":
                return AgentResult(success=True, data=None, duration_ms=(time.time() - start) * 1000)
            else:
                return AgentResult(success=False, error=f"Unknown action: {action}", duration_ms=(time.time() - start) * 1000)

            duration_ms = (time.time() - start) * 1000
            return AgentResult(success=True, data=result, duration_ms=duration_ms)

        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)

    def _full_sync(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Full bidirectional sync between local and cloud data."""
        local = params.get("local_data", [])
        cloud = params.get("cloud_data", [])
        strategy = params.get("strategy", "last_write_wins")

        # Build lookup maps by ID
        local_map = {r.get("id", r.get("record_id", i)): r for i, r in enumerate(local)}
        cloud_map = {r.get("id", r.get("record_id", i)): r for i, r in enumerate(cloud)}

        all_ids = set(local_map.keys()) | set(cloud_map.keys())

        conflicts = []
        to_upload = []  # local-only → push to cloud
        to_download = []  # cloud-only → pull to local
        merged = []

        for record_id in all_ids:
            in_local = record_id in local_map
            in_cloud = record_id in cloud_map

            if in_local and not in_cloud:
                to_upload.append(local_map[record_id])
                merged.append(local_map[record_id])
            elif in_cloud and not in_local:
                to_download.append(cloud_map[record_id])
                merged.append(cloud_map[record_id])
            elif in_local and in_cloud:
                # Both exist — check for conflicts
                local_rec = local_map[record_id]
                cloud_rec = cloud_map[record_id]

                if self._records_differ(local_rec, cloud_rec):
                    winner = self._resolve_record_conflict(local_rec, cloud_rec, strategy)
                    conflicts.append({
                        "record_id": record_id,
                        "local": local_rec,
                        "cloud": cloud_rec,
                        "resolution": winner,
                    })
                    merged.append(winner)
                else:
                    merged.append(cloud_rec)  # identical

        return {
            "sync_type": "full",
            "local_count": len(local),
            "cloud_count": len(cloud),
            "conflicts_found": len(conflicts),
            "to_upload": len(to_upload),
            "to_download": len(to_download),
            "merged_count": len(merged),
            "conflicts": conflicts[:20],
            "merged_sample": merged[:5],
        }

    def _delta_sync(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sync only changed records since last sync."""
        local = params.get("local_data", [])
        cloud = params.get("cloud_data", [])

        # Find records with newer timestamps
        local_map = {}
        for r in local:
            rid = r.get("id", r.get("record_id"))
            if rid:
                local_map[rid] = r

        cloud_map = {}
        for r in cloud:
            rid = r.get("id", r.get("record_id"))
            if rid:
                cloud_map[rid] = r

        to_upload = []
        to_download = []

        for rid, local_rec in local_map.items():
            cloud_rec = cloud_map.get(rid)
            if not cloud_rec:
                to_upload.append(local_rec)
            else:
                local_ts = self._get_timestamp(local_rec)
                cloud_ts = self._get_timestamp(cloud_rec)
                if local_ts > cloud_ts:
                    to_upload.append(local_rec)

        for rid, cloud_rec in cloud_map.items():
            if rid not in local_map:
                to_download.append(cloud_rec)
            else:
                local_ts = self._get_timestamp(local_map[rid])
                cloud_ts = self._get_timestamp(cloud_rec)
                if cloud_ts > local_ts:
                    to_download.append(cloud_rec)

        return {
            "sync_type": "delta",
            "to_upload": len(to_upload),
            "to_download": len(to_download),
            "upload_records": to_upload[:50],
            "download_records": to_download[:50],
        }

    def _resolve_conflicts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve sync conflicts using the specified strategy."""
        local = params.get("local_data", [])
        cloud = params.get("cloud_data", [])
        strategy = params.get("strategy", "last_write_wins")

        # Simple conflict resolution
        resolved = []
        for l, c in zip(local, cloud):
            winner = self._resolve_record_conflict(l, c, strategy)
            resolved.append(winner)

        return {
            "conflicts_resolved": len(resolved),
            "strategy": strategy,
            "resolved": resolved[:20],
        }

    def _records_differ(self, a: Dict, b: Dict) -> bool:
        """Check if two records have meaningful differences."""
        # Compare key fields (excluding metadata)
        skip_keys = {"updated_at", "synced_at", "_version", "_sync_status"}
        for key in set(a.keys()) | set(b.keys()):
            if key in skip_keys:
                continue
            if a.get(key) != b.get(key):
                return True
        return False

    def _resolve_record_conflict(self, local: Dict, cloud: Dict, strategy: str) -> Dict:
        """Resolve a single record conflict."""
        if strategy == "last_write_wins":
            local_ts = self._get_timestamp(local)
            cloud_ts = self._get_timestamp(cloud)
            return local if local_ts >= cloud_ts else cloud
        elif strategy == "cloud_wins":
            return cloud
        elif strategy == "local_wins":
            return local
        else:
            return cloud  # default: cloud wins

    def _get_timestamp(self, record: Dict) -> float:
        """Extract timestamp from a record."""
        ts = record.get("updated_at", record.get("timestamp", 0))
        if isinstance(ts, str):
            try:
                from datetime import datetime
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                return 0
        return float(ts) if ts else 0
