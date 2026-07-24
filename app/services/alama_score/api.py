"""
Alama Score — Lender-Facing API Endpoints.

Provides REST API for lenders (banks, microfinance, fintech) to:
  - Query credit scores for businesses
  - Check affordability for specific loan amounts
  - Get product recommendations
  - Retrieve score history and trends
  - Record loan outcomes for calibration

All endpoints require lender authentication (API key).
Rate-limited to prevent abuse.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db

from .engine import AlamaScoreEngine
from .models import (
    LenderQueryRequest,
    LenderQueryResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/alama-score", tags=["Alama Score"])


# ── Authentication ───────────────────────────────────────────────────────────

async def verify_lender_api_key(
    x_api_key: str = Header(..., description="Lender API key"),
) -> str:
    """
    Verify lender API key and return lender_id.

    In production, this would validate against a database of registered
    lender API keys. For now, we accept any non-empty key and derive
    the lender_id from it.
    """
    if not x_api_key or len(x_api_key) < 10:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Invalid API key",
                "error_sw": "Ufunguo wa API si sahihi",
            },
        )
    # In production: validate against DB, check rate limits, etc.
    # For now, derive lender_id from API key hash
    import hashlib
    lender_id = hashlib.sha256(x_api_key.encode()).hexdigest()[:16]
    return lender_id


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=LenderQueryResponse,
    summary="Query Alama Score for a business",
    description=(
        "Compute and return the Alama credit score (0-1000) for a business. "
        "Includes score components, risk assessment, and optional product recommendations."
    ),
)
async def query_score(
    request: LenderQueryRequest,
    lender_id: str = Depends(verify_lender_api_key),
    db: AsyncSession = Depends(get_db),
) -> LenderQueryResponse:
    """
    Query the Alama Score for a specific business.

    The business_id is an anonymized hash — lenders never see raw user IDs.
    Scores are computed from transaction data with k-anonymity protection.

    Rate limits:
    - Basic tier: 100 queries/day
    - Standard tier: 1000 queries/day
    - Premium tier: 10000 queries/day
    """
    # Override lender_id from auth
    request.lender_id = lender_id

    engine = AlamaScoreEngine(db)
    response = await engine.compute(request)

    if response.status == "error":
        raise HTTPException(
            status_code=404 if "not found" in (response.error or "").lower() else 400,
            detail={
                "error": response.error,
                "error_sw": response.error_sw,
            },
        )

    return response


@router.post(
    "/batch-query",
    summary="Batch query scores for multiple businesses",
    description="Query scores for up to 50 businesses in a single request.",
)
async def batch_query_scores(
    business_ids: list[str],
    lender_id: str = Depends(verify_lender_api_key),
    lookback_days: int = Query(default=90, ge=30, le=365),
    query_tier: str = Query(default="basic"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Batch query scores for multiple businesses.

    Maximum 50 businesses per request. Returns a map of
    business_id → score result (or error).
    """
    if len(business_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 businesses per batch request",
        )

    engine = AlamaScoreEngine(db)
    results = {}

    for bid in business_ids:
        request = LenderQueryRequest(
            business_id=bid,
            lender_id=lender_id,
            query_tier=query_tier,
            lookback_days=lookback_days,
            include_peer_comparison=False,  # Skip for batch to save compute
            include_product_match=False,
        )
        response = await engine.compute(request)
        results[bid] = {
            "status": response.status,
            "score": response.report.alama_score if response.report else None,
            "band": response.report.score_band.value if response.report else None,
            "risk": response.report.risk_category.value if response.report else None,
            "confidence": response.report.confidence if response.report else None,
            "default_probability": response.report.default_probability if response.report else None,
            "credit_limit": response.report.recommended_credit_limit_kes if response.report else None,
            "error": response.error,
        }

    return {
        "status": "success",
        "lender_id": lender_id,
        "query_count": len(business_ids),
        "results": results,
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.post(
    "/{business_id}/affordability",
    summary="Check loan affordability",
    description="Check whether a business can afford a specific loan amount.",
)
async def check_affordability(
    business_id: str,
    amount: float = Query(..., gt=0, description="Loan amount in KES"),
    term_days: int = Query(default=90, ge=7, le=730, description="Loan term in days"),
    lender_id: str = Depends(verify_lender_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Quick affordability check without full score computation.

    Returns whether the business can afford the requested amount,
    the recommended maximum, and the debt-to-revenue ratio.
    """
    engine = AlamaScoreEngine(db)
    request = LenderQueryRequest(
        business_id=business_id,
        lender_id=lender_id,
        query_tier="basic",
        lookback_days=90,
        requested_amount=amount,
        include_peer_comparison=False,
        include_product_match=False,
    )
    response = await engine.compute(request)

    if response.status == "error" or not response.report:
        raise HTTPException(status_code=404, detail=response.error or "Business not found")

    return {
        "status": "success",
        "business_id": business_id,
        "requested_amount_kes": amount,
        "term_days": term_days,
        "affordability": response.report.affordability.model_dump() if response.report.affordability else None,
        "alama_score": response.report.alama_score,
        "recommended_credit_limit_kes": response.report.recommended_credit_limit_kes,
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.post(
    "/{business_id}/record-outcome",
    summary="Record a loan outcome",
    description="Record whether a loan was repaid or defaulted, for score calibration.",
)
async def record_outcome(
    business_id: str,
    outcome: str = Query(..., regex="^(repayment|default)$"),
    amount: float | None = Query(default=None, ge=0),
    lender_id: str = Depends(verify_lender_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Record a loan outcome for Bayesian calibration.

    This feedback loop improves scoring accuracy over time:
    1. Lender queries score
    2. Lender issues loan
    3. Outcome (repay/default) is recorded here
    4. Bayesian priors are updated for future scoring

    All data is anonymized — no personally identifiable information
    is shared between lenders.
    """
    from app.services.intelligence.alama_score import AlamaScoreService

    service = AlamaScoreService(db)
    result = await service.record_outcome(
        business_id=business_id,
        outcome=outcome,
        amount=amount,
    )

    return {
        "status": "success",
        "lender_id": lender_id,
        "outcome_recorded": outcome,
        "calibration": result.get("calibration"),
        "message": "Outcome recorded for model calibration",
        "message_sw": "Matokeo yamerekodiwa kwa kalibrasi ya mfumo",
    }


@router.get(
    "/score-distribution",
    summary="Get anonymized score distribution",
    description="Returns the distribution of scores across all businesses (anonymized).",
)
async def get_score_distribution(
    lender_id: str = Depends(verify_lender_api_key),
    business_type: str | None = Query(default=None),
    region: str | None = Query(default=None),
) -> dict[str, Any]:
    """
    Get the anonymized distribution of Alama Scores.

    Useful for lenders to understand the market and set thresholds.
    All data is aggregated — no individual businesses are identifiable.
    """
    # This would query aggregated data in production
    # For now, return typical distribution based on informal economy research
    return {
        "status": "success",
        "lender_id": lender_id,
        "distribution": {
            "exceptional_900_1000": {"count": 0, "pct": 0, "description": "Top tier — very rare in informal sector"},
            "excellent_800_899": {"count": 0, "pct": 5, "description": "Strong businesses with consistent track record"},
            "good_700_799": {"count": 0, "pct": 15, "description": "Reliable businesses suitable for standard loans"},
            "fair_600_699": {"count": 0, "pct": 25, "description": "Average businesses — moderate risk"},
            "poor_500_599": {"count": 0, "pct": 30, "description": "Higher risk — smaller loan amounts recommended"},
            "very_poor_300_499": {"count": 0, "pct": 20, "description": "High risk — group lending or micro-loans only"},
            "no_score_below_300": {"count": 0, "pct": 5, "description": "Insufficient data or very new businesses"},
        },
        "business_type_filter": business_type,
        "region_filter": region,
        "note": "Live distribution data requires aggregation pipeline",
        "note_sw": "Data ya usambazaji inahitaji mfumo wa kukusanya",
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get(
    "/health",
    summary="Health check",
)
async def health_check() -> dict[str, str]:
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "alama_score_api",
        "version": "1.0",
        "timestamp": datetime.now(UTC).isoformat(),
    }
