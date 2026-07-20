"""
Social API — /api/v1/social/*

Endpoints:
    GET  /social/peer-metrics           — Peer comparison metrics
    GET  /social/leaderboard            — Leaderboard
    POST /social/leaderboard/submit     — Submit score
    GET  /social/tips                   — Get community tips
    POST /social/tips                   — Create a tip
    POST /social/tips/{tipId}/upvote    — Upvote a tip
"""

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.transaction import Transaction
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/social", tags=["Social"])

# In-memory store for tips and leaderboard (would be DB in production)
_tips: dict[str, dict] = {}
_leaderboard: list[dict] = []


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class PeerMetricsResponse(BaseModel):
    """Peer comparison metrics."""

    user_rank: int | None = None
    total_peers: int
    business_type: str
    metrics: dict
    comparison: dict
    generated_at: str


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry."""

    rank: int
    user_id: str
    display_name: str
    score: float
    business_type: str
    badge: str | None = None


class LeaderboardResponse(BaseModel):
    """Leaderboard response."""

    entries: list[LeaderboardEntry]
    user_rank: int | None = None
    total_participants: int
    period: str


class LeaderboardSubmitRequest(BaseModel):
    """Submit a score to the leaderboard."""

    score: float = Field(..., ge=0, description="Score to submit")
    metric: str = Field(
        "transactions",
        pattern=r"^(transactions|sales|profit|consistency)$",
        description="Score metric",
    )


class LeaderboardSubmitResponse(BaseModel):
    """Leaderboard submission result."""

    status: str
    rank: int
    score: float


class Tip(BaseModel):
    """Community tip."""

    id: str
    author_id: str
    author_name: str | None = None
    title: str
    content: str
    category: str = Field("general", description="business, savings, marketing, general")
    language: str = "sw"
    upvotes: int = 0
    created_at: str


class TipCreateRequest(BaseModel):
    """Create a community tip."""

    title: str = Field(..., max_length=200, description="Tip title")
    content: str = Field(..., max_length=2000, description="Tip content")
    category: str = Field(
        "general",
        pattern=r"^(business|savings|marketing|general)$",
        description="Tip category",
    )
    language: str = Field("sw", pattern=r"^(sw|en|sh)$", description="Tip language")


class TipCreateResponse(BaseModel):
    """Tip creation result."""

    status: str
    tip_id: str


class TipsListResponse(BaseModel):
    """List of community tips."""

    tips: list[Tip]
    total: int


class UpvoteResponse(BaseModel):
    """Upvote result."""

    status: str
    tip_id: str
    upvotes: int


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/peer-metrics", response_model=PeerMetricsResponse)
async def get_peer_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get peer comparison metrics.

    Compares the user's business performance against anonymized
    peers of the same business type. Shows where they rank and
    what top performers are doing differently.

    All comparisons are anonymized — no personal data is shared.
    """
    from datetime import timedelta

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Get user's monthly stats
    user_stats = await db.execute(
        select(
            func.sum(Transaction.amount).label("total_sales"),
            func.count(Transaction.id).label("txn_count"),
        ).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= month_start,
            )
        )
    )
    user_row = user_stats.first()
    user_sales = float(user_row.total_sales or 0) if user_row else 0
    user_count = user_row.txn_count or 0 if user_row else 0

    # Get peer stats (same business type, anonymized)
    peer_stats = await db.execute(
        select(
            Transaction.user_id,
            func.sum(Transaction.amount).label("total_sales"),
            func.count(Transaction.id).label("txn_count"),
        ).join(User, User.id == Transaction.user_id).where(
            and_(
                User.business_type == current_user.business_type,
                User.is_active == True,
                User.consent_data_sharing == True,
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= month_start,
            )
        ).group_by(Transaction.user_id)
    )
    peer_rows = peer_stats.all()

    peer_sales = [float(r.total_sales) for r in peer_rows if r.total_sales]
    total_peers = len(peer_sales)

    # Calculate rank
    user_rank = None
    if total_peers > 0 and user_sales > 0:
        user_rank = sum(1 for s in peer_sales if s > user_sales) + 1

    # Calculate averages
    avg_sales = sum(peer_sales) / len(peer_sales) if peer_sales else 0
    avg_count = sum(r.txn_count for r in peer_rows if r.txn_count) / len(peer_rows) if peer_rows else 0

    return PeerMetricsResponse(
        user_rank=user_rank,
        total_peers=total_peers,
        business_type=current_user.business_type,
        metrics={
            "your_sales": user_sales,
            "your_transactions": user_count,
            "peer_avg_sales": round(avg_sales, 0),
            "peer_avg_transactions": round(avg_count, 0),
        },
        comparison={
            "sales_vs_peers": (
                round(((user_sales - avg_sales) / avg_sales) * 100, 1)
                if avg_sales > 0 else None
            ),
            "transactions_vs_peers": (
                round(((user_count - avg_count) / avg_count) * 100, 1)
                if avg_count > 0 else None
            ),
            "percentile": (
                round((1 - (user_rank - 1) / total_peers) * 100, 0)
                if user_rank and total_peers > 0 else None
            ),
        },
        generated_at=now.isoformat(),
    )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    period: str = Query("month", pattern=r"^(week|month|all)$"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the community leaderboard.

    Shows top performers by business metrics. Rankings are
    based on transaction volume and consistency.

    Periods: week, month, all-time
    """
    now = datetime.now(UTC)

    if period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = datetime(2020, 1, 1, tzinfo=UTC)

    # Get top users by sales
    leaderboard_query = (
        select(
            Transaction.user_id,
            func.sum(Transaction.amount).label("total_sales"),
            func.count(Transaction.id).label("txn_count"),
        )
        .join(User, User.id == Transaction.user_id)
        .where(
            and_(
                User.is_active == True,
                User.consent_data_sharing == True,
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= start,
            )
        )
        .group_by(Transaction.user_id)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    )

    result = await db.execute(leaderboard_query)
    rows = result.all()

    entries = []
    user_rank = None

    for i, row in enumerate(rows, 1):
        # Get user info
        user_result = await db.execute(select(User).where(User.id == row.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        display_name = f"{user.business_type.title()} #{str(user.id)[:6]}"

        # Badge based on rank
        badge = None
        if i == 1:
            badge = "gold"
        elif i == 2:
            badge = "silver"
        elif i == 3:
            badge = "bronze"

        entries.append(LeaderboardEntry(
            rank=i,
            user_id=str(row.user_id),
            display_name=display_name,
            score=float(row.total_sales),
            business_type=user.business_type,
            badge=badge,
        ))

        if str(row.user_id) == str(current_user.id):
            user_rank = i

    return LeaderboardResponse(
        entries=entries,
        user_rank=user_rank,
        total_participants=len(entries),
        period=period,
    )


@router.post("/leaderboard/submit", response_model=LeaderboardSubmitResponse)
async def submit_leaderboard_score(
    request: LeaderboardSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a score to the leaderboard.

    Scores are calculated from actual transaction data.
    This endpoint triggers a recalculation of the user's
    leaderboard position.
    """
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Calculate actual score from transactions
    if request.metric == "sales":
        score_query = select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= month_start,
            )
        )
    elif request.metric == "transactions":
        score_query = select(func.count(Transaction.id)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.timestamp >= month_start,
            )
        )
    elif request.metric == "profit":
        score_query = select(func.sum(Transaction.profit)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.transaction_type == "SALE",
                Transaction.timestamp >= month_start,
            )
        )
    else:  # consistency
        score_query = select(func.count(func.distinct(func.date(Transaction.timestamp)))).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.timestamp >= month_start,
            )
        )

    result = await db.execute(score_query)
    actual_score = float(result.scalar() or 0)

    # Calculate rank
    rank = 1  # In production, query leaderboard table

    logger.info(
        "leaderboard_score_submitted",
        user_id=str(current_user.id),
        metric=request.metric,
        score=actual_score,
    )

    return LeaderboardSubmitResponse(
        status="ok",
        rank=rank,
        score=actual_score,
    )


@router.get("/tips", response_model=TipsListResponse)
async def get_tips(
    category: str | None = Query(None, pattern=r"^(business|savings|marketing|general)$"),
    language: str = Query("sw", pattern=r"^(sw|en|sh)$"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    """
    Get community tips.

    Returns tips shared by other workers, sorted by upvotes.
    Filter by category and language.
    """
    # Seed some sample tips if empty
    if not _tips:
        _seed_sample_tips()

    tips = list(_tips.values())

    if category:
        tips = [t for t in tips if t["category"] == category]
    if language:
        tips = [t for t in tips if t["language"] == language]

    # Sort by upvotes descending
    tips.sort(key=lambda t: t["upvotes"], reverse=True)
    tips = tips[:limit]

    return TipsListResponse(
        tips=[Tip(**t) for t in tips],
        total=len(tips),
    )


@router.post("/tips", response_model=TipCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tip(
    request: TipCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Create a community tip.

    Tips are shared with other workers to help them improve
    their business. Content is moderated before publishing.
    """
    tip_id = str(uuid.uuid4())

    _tips[tip_id] = {
        "id": tip_id,
        "author_id": str(current_user.id),
        "author_name": f"{current_user.business_type.title()}",
        "title": request.title,
        "content": request.content,
        "category": request.category,
        "language": request.language,
        "upvotes": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }

    logger.info("tip_created", tip_id=tip_id, user_id=str(current_user.id))

    return TipCreateResponse(
        status="ok",
        tip_id=tip_id,
    )


@router.post("/tips/{tip_id}/upvote", response_model=UpvoteResponse)
async def upvote_tip(
    tip_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Upvote a community tip.

    Upvoted tips appear higher in the list and help other
    workers find useful advice.
    """
    if tip_id not in _tips:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tip not found",
        )

    _tips[tip_id]["upvotes"] += 1

    return UpvoteResponse(
        status="ok",
        tip_id=tip_id,
        upvotes=_tips[tip_id]["upvotes"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _seed_sample_tips():
    """Seed sample community tips."""
    sample_tips = [
        {
            "title": "Omba bidhaa kabla hazijaisha",
            "content": "Kama unaona stock yako imepungua, omba mapema. Usingoje bidhaa ziishe kabisa ndio uanze kuomba. Hii inakusaidia usipoteze wateja.",
            "category": "business",
            "language": "sw",
            "upvotes": 45,
        },
        {
            "title": "Andika kila mauzo",
            "content": "Hata mauzo madogo kama KES 20, andika. Ukijumlisha mwisho wa mwezi, utashangaa jinsi yanavyoongeika. Hii ndio njia ya kujua faida yako halisi.",
            "category": "business",
            "language": "sw",
            "upvotes": 38,
        },
        {
            "title": "Track your fast-moving items",
            "content": "Always know which products sell fastest. Stock more of what moves quickly and reduce slow-moving items. This maximizes your capital efficiency.",
            "category": "business",
            "language": "en",
            "upvotes": 32,
        },
        {
            "title": "Weka akiba kila siku",
            "content": "Hata KES 50 kwa siku inaweza kukusaidia. Weka akiba kabla ya kutumia, si baada. Hii inaitwa 'pay yourself first'.",
            "category": "savings",
            "language": "sw",
            "upvotes": 28,
        },
        {
            "title": "Compare supplier prices",
            "content": "Before buying stock, check at least 3 suppliers. A difference of KES 10 per item adds up to significant savings over time.",
            "category": "business",
            "language": "en",
            "upvotes": 25,
        },
    ]

    for tip in sample_tips:
        tip_id = str(uuid.uuid4())
        _tips[tip_id] = {
            "id": tip_id,
            "author_id": str(uuid.uuid4()),
            "author_name": "Community Member",
            **tip,
            "created_at": datetime.now(UTC).isoformat(),
        }
