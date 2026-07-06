"""
Evolution / Feedback Sync Endpoints.

Handles feedback from Msaidizi devices for self-evolution:
- Feature requests
- Bug reports
- Improvement suggestions
- Praise

Feedback is anonymized before storage — no PII leaves the device.
Used for pattern analysis and feature prioritization.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from fastapi import Depends

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/evolution", tags=["Evolution / Feedback"])


# =========================================================================
# Schemas (match FeedbackCollector.kt)
# =========================================================================


class AnonymizedFeedback(BaseModel):
    """Anonymized feedback from device — no PII."""
    id: str = Field(..., description="UUID from device")
    worker_hash: str = Field(..., max_length=64, description="SHA-256 hashed worker ID")
    type: str = Field(
        ...,
        description="FEATURE_REQUEST | BUG_REPORT | IMPROVEMENT | PRAISE",
    )
    text: str = Field(..., max_length=2000)
    language: str = Field("sw")
    timestamp: int = Field(..., description="Unix timestamp (ms)")
    category: Optional[str] = None


class FeedbackSyncRequest(BaseModel):
    """Batch feedback sync request."""
    feedback: List[AnonymizedFeedback] = Field(..., max_length=100)


class FeedbackSyncResponse(BaseModel):
    """Response after feedback sync."""
    status: str = "ok"
    synced: int = 0
    failed: int = 0
    error: Optional[str] = None


class FeatureRequestCluster(BaseModel):
    """Aggregated feature request from multiple workers."""
    cluster_id: str
    description: str
    request_count: int
    worker_types: List[str]
    priority: float
    status: str = "NEW"
    created_at: str
    last_updated: str


# =========================================================================
# In-memory store (production: database table)
# =========================================================================

_feedback_store: List[dict] = []


# =========================================================================
# Endpoints
# =========================================================================


@router.post("/feedback/sync", response_model=FeedbackSyncResponse)
async def sync_feedback(
    request: FeedbackSyncRequest,
):
    """
    Sync anonymized feedback from Msaidizi devices.

    Feedback is stored for pattern analysis and feature prioritization.
    Worker IDs are already hashed on-device — no PII in this endpoint.

    **Batch Limits:** Max 100 feedback entries per sync.
    """
    synced = 0
    failed = 0

    for item in request.feedback:
        try:
            # Validate type
            valid_types = {"FEATURE_REQUEST", "BUG_REPORT", "IMPROVEMENT", "PRAISE"}
            if item.type not in valid_types:
                failed += 1
                continue

            # Store feedback
            _feedback_store.append({
                "id": item.id,
                "worker_hash": item.worker_hash,
                "type": item.type,
                "text": item.text,
                "language": item.language,
                "timestamp": item.timestamp,
                "category": item.category,
                "received_at": datetime.now(timezone.utc).isoformat(),
            })
            synced += 1

        except Exception as e:
            logger.warning("feedback_item_failed", error=str(e))
            failed += 1

    logger.info("feedback_synced", synced=synced, failed=failed)

    return FeedbackSyncResponse(
        status="ok" if failed == 0 else "partial",
        synced=synced,
        failed=failed,
    )


@router.get("/feedback/stats")
async def feedback_stats():
    """
    Get feedback statistics for the evolution dashboard.

    Returns aggregated feedback counts by type and category.
    """
    total = len(_feedback_store)
    by_type = {}
    by_category = {}

    for item in _feedback_store:
        ftype = item.get("type", "UNKNOWN")
        by_type[ftype] = by_type.get(ftype, 0) + 1

        cat = item.get("category")
        if cat:
            by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "total_feedback": total,
        "counts_by_type": by_type,
        "counts_by_category": by_category,
        "last_sync": _feedback_store[-1]["received_at"] if _feedback_store else None,
    }


@router.get("/feedback/feature-requests")
async def get_feature_requests():
    """
    Get clustered feature requests.

    Groups similar feedback into feature request clusters
    for prioritization.
    """
    # Simple clustering by keyword matching
    feature_requests = [
        item for item in _feedback_store
        if item.get("type") == "FEATURE_REQUEST"
    ]

    # Count by category
    clusters = {}
    for item in feature_requests:
        cat = item.get("category", "general")
        if cat not in clusters:
            clusters[cat] = {
                "count": 0,
                "texts": [],
                "workers": set(),
            }
        clusters[cat]["count"] += 1
        clusters[cat]["texts"].append(item["text"][:100])
        clusters[cat]["workers"].add(item["worker_hash"][:8])

    return {
        "clusters": [
            {
                "category": cat,
                "request_count": data["count"],
                "unique_workers": len(data["workers"]),
                "sample_texts": data["texts"][:5],
            }
            for cat, data in sorted(clusters.items(), key=lambda x: -x[1]["count"])
        ],
        "total_feature_requests": len(feature_requests),
    }
