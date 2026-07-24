"""Credit scoring endpoints — Alama Score."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.domain import CreditScore
from app.models.schemas import CreditScoreRequest, CreditScoreResponse

router = APIRouter()


@router.post("/score", response_model=CreditScoreResponse)
async def get_credit_score(
    req: CreditScoreRequest,
    db: AsyncSession = Depends(get_db),
):
    """Get or compute Alama credit score (300-850)."""
    # Check for recent valid score
    result = await db.execute(
        select(CreditScore)
        .where(
            CreditScore.user_id == req.user_id,
            CreditScore.valid_until > datetime.now(timezone.utc),
        )
        .order_by(CreditScore.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing:
        return CreditScoreResponse(
            score=existing.score,
            tier=existing.tier,
            factors=existing.factors if req.include_factors else None,
            model_version=existing.model_version,
            valid_until=existing.valid_until,
        )

    # Compute new score via credit scoring engine
    from app.intelligence.credit_scoring import CreditScoringEngine

    engine = CreditScoringEngine(db)
    score_result = await engine.compute_score(req.user_id)

    # Store the score
    credit_score = CreditScore(
        user_id=req.user_id,
        score=score_result["score"],
        tier=score_result["tier"],
        factors=score_result["factors"],
        model_version=score_result["model_version"],
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(credit_score)
    await db.flush()

    return CreditScoreResponse(
        score=credit_score.score,
        tier=credit_score.tier,
        factors=credit_score.factors if req.include_factors else None,
        model_version=credit_score.model_version,
        valid_until=credit_score.valid_until,
    )


@router.get("/history/{user_id}")
async def get_score_history(
    user_id: uuid.UUID,
    limit: int = 12,
    db: AsyncSession = Depends(get_db),
):
    """Get credit score history for a user."""
    result = await db.execute(
        select(CreditScore)
        .where(CreditScore.user_id == user_id)
        .order_by(CreditScore.created_at.desc())
        .limit(limit)
    )
    scores = result.scalars().all()
    return [
        {
            "score": s.score,
            "tier": s.tier,
            "model_version": s.model_version,
            "created_at": s.created_at.isoformat(),
        }
        for s in scores
    ]
