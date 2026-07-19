"""
Goal Planner Service — Accountability-driven goal tracking with Polars analytics.

Core capabilities:
- Create goals with auto-generated milestones and commitment devices
- Update progress with streak tracking and behavioral nudges
- Time-to-goal prediction using Polars rolling averages
- Obstacle analysis using contribution pattern detection
- Accountability partner reports (95% completion with accountability)

Research-backed behavioral nudges:
- Commitment devices (public declarations)
- Social proof (peer comparisons)
- Loss aversion (what you lose by not acting)
- Present bias countermeasures (small immediate wins)
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import polars as pl
import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal, GoalMilestone, GoalProgressEntry

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Swahili/English Nudge Messages
# ─────────────────────────────────────────────────────────────────────────────

NUDGE_MESSAGES = {
    "morning_motivation": {
        "sw": "Leo ni siku mpya ya lengo lako! Soko linafungua — fanya mauzo mazuri!",
        "en": "Today is a new day for your goal! Market opens — make great sales!",
    },
    "eat_the_frog": {
        "sw": "Kabla ya kuanza biashara, weka kidogo kwenye lengo. Fanya sasa!",
        "en": "Before starting business, set aside a little for your goal. Do it now!",
    },
    "midday_check": {
        "sw": "Jioni imefika! Umefanyaje? Je, umeweza kuokoa chochote?",
        "en": "Afternoon check! How's it going? Were you able to save anything?",
    },
    "end_of_day": {
        "sw": "Biashara imeisha. Umeokoa leo? Hata KSh 50 inatosha!",
        "en": "Business day done. Did you save today? Even KSh 50 is enough!",
    },
    "streak_3": {
        "sw": "Siku 3 mfululizo! Anza vizuri — mwanzo mzuri ni nusu ya kazi!",
        "en": "3 days in a row! Great start — well begun is half done!",
    },
    "streak_7": {
        "sw": "Wiki 1 mfululizo! Umefanya kazi nzuri. Endelea hivyo!",
        "en": "1 week streak! Great work. Keep going!",
    },
    "streak_14": {
        "sw": "Wiki 2 mfululizo! Tabia yako inaanza kuwa imara!",
        "en": "2 weeks straight! Your habit is becoming solid!",
    },
    "streak_30": {
        "sw": "Siku 30 mfululizo! Wewe ni mfano wa kuokoa! Wengine wanatazama!",
        "en": "30 days in a row! You're a savings role model! Others are watching!",
    },
    "streak_broken": {
        "sw": "Streak imevunjika — si vibaya! Kila mtaalamu alianza upya. Fanya leo!",
        "en": "Streak broken — that's okay! Every expert restarted. Do it today!",
    },
    "milestone_25": {
        "sw": "🎉 25%! Umefikia robo ya lengo lako! Uko kwenye njia sahihi!",
        "en": "🎉 25%! You've reached a quarter of your goal! You're on track!",
    },
    "milestone_50": {
        "sw": "🎉 NUSU! Umefikia nusu ya lengo lako! Sasa ni wakati wa kuongeza kasi!",
        "en": "🎉 HALFWAY! You've reached 50%! Time to pick up pace!",
    },
    "milestone_75": {
        "sw": "🎉 75%! Robo tatu imefikiwa! Baki kidogo tu — unaweza!",
        "en": "🎉 75%! Three quarters done! Just a little more — you can do it!",
    },
    "goal_complete": {
        "sw": "🎊 Hongera sana! Umefikia lengo lako! Je, ungependa kuanza lengo jipya?",
        "en": "🎊 Congratulations! You've reached your goal! Want to start a new one?",
    },
    "behind_schedule": {
        "sw": "Wiki hii hujaokoa kama ulivyopanga. Sijali — hebu tubadilishe mpango kidogo.",
        "en": "Didn't save as planned this week. That's okay — let's adjust the plan a bit.",
    },
    "ahead_of_schedule": {
        "sw": "Uko mbele ya mpango! Kwa kasi hii, utafikia lengo lako mapema!",
        "en": "You're ahead of schedule! At this pace, you'll reach your goal early!",
    },
    "loss_aversion": {
        "sw": "Ukisita, utapoteza siku {days} na KSh {amount}. Fanya leo!",
        "en": "If you skip, you lose {days} days and KSh {amount}. Do it today!",
    },
    "social_proof": {
        "sw": "Wafanyakazi {count} wanaokoa leo. Wewe pia uwe miongoni mwao!",
        "en": "{count} workers are saving today. Be among them!",
    },
    "small_win": {
        "sw": "Hata KSh 50 inatosha! Kidogo kidogo, hujaza kibaba. Fanya sasa!",
        "en": "Even KSh 50 is enough! Little by little fills the measure. Do it now!",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Natural Language Goal Parsing (Voice Support)
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_KEYWORDS = {
    "business": ["biashara", "business", "shop", "duka", "stock", "ghala", "inventory", "supplier"],
    "savings": ["okoa", "save", "savings", "akiba", "bank", "account", "emergency"],
    "personal": ["personal", "binafsi", "nyumba", "house", "gari", "car", "shule", "school", "education"],
    "debt": ["deni", "debt", "loan", "mkopo", "lipa", "pay", "owe"],
}


def _parse_voice_goal(transcript: str) -> dict[str, Any]:
    """
    Parse natural language (Swahili/English) into structured goal data.

    Examples:
        "Nataka kununua friji ya KSh 30,000 kabla ya Desemba"
        → title="Kununua friji", target_amount=30000, category="personal"

        "Save 50,000 for business stock in 3 months"
        → title="Save for business stock", target_amount=50000, category="business"
    """
    import re

    text = transcript.lower().strip()

    # Extract amount
    amount_match = re.search(r'(?:ksh|kes|shilingi|sh)?\s*(\d[\d,]*)\s*(?:ksh|kes)?', text)
    target_amount = None
    if amount_match:
        target_amount = float(amount_match.group(1).replace(",", ""))

    # Detect category
    category = "personal"  # default
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            category = cat
            break

    # Extract title (clean up the transcript)
    title = transcript.strip()
    # Remove amount patterns
    title = re.sub(r'(?:ksh|kes|shilingi)\s*[\d,]+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[\d,]+\s*(?:ksh|kes)?', '', title, flags=re.IGNORECASE)
    # Remove time patterns
    title = re.sub(r'(?:kabla ya|before|by|in)\s+\w+\s*\d*', '', title, flags=re.IGNORECASE)
    title = title.strip(" ,.-")
    if len(title) > 200:
        title = title[:200]

    return {
        "title": title or transcript[:200],
        "category": category,
        "target_amount": target_amount,
        "voice_created": True,
        "voice_transcript": transcript,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Goal CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def create_goal(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    category: str,
    target_amount: float,
    target_date: date | None = None,
    description: str | None = None,
    title_sw: str | None = None,
    deeper_purpose: str | None = None,
    what_i_lose: str | None = None,
    milestones: list[dict[str, Any]] | None = None,
    commitment_declaration: str | None = None,
    accountability_partner_id: UUID | None = None,
    voice_transcript: str | None = None,
    currency: str = "KES",
) -> dict[str, Any]:
    """
    Create a goal with auto-generated milestones and commitment device.

    If voice_transcript is provided, parses natural language to extract
    goal details (supports Swahili and English).
    """
    # Voice parsing fallback
    if voice_transcript and not title:
        parsed = _parse_voice_goal(voice_transcript)
        title = parsed["title"]
        category = parsed.get("category", category)
        if parsed.get("target_amount"):
            target_amount = parsed["target_amount"]

    # Validate category
    valid_categories = {"business", "personal", "savings", "debt"}
    if category not in valid_categories:
        return {"error": f"Invalid category. Must be one of: {valid_categories}"}

    if target_amount <= 0:
        return {"error": "Target amount must be positive"}

    # Auto-generate target date if not provided
    if target_date is None:
        months_needed = max(1, round(target_amount / 2000))
        target_date = date.today() + timedelta(days=months_needed * 30)

    # Calculate daily/weekly targets
    remaining = target_amount
    days_to_target = max(1, (target_date - date.today()).days)
    weeks_to_target = max(1, days_to_target / 7)
    daily_target = round(remaining / days_to_target, 0)
    weekly_target = round(remaining / weeks_to_target, 0)

    # Check for existing active primary goal
    existing = await db.execute(
        select(Goal).where(
            and_(
                Goal.user_id == user_id,
                Goal.status == "active",
            )
        ).limit(1)
    )
    has_active = existing.scalar_one_or_none() is not None

    # Create the goal
    goal = Goal(
        user_id=user_id,
        title=title,
        title_sw=title_sw,
        description=description,
        category=category,
        target_amount=target_amount,
        current_amount=0,
        currency=currency,
        target_date=target_date,
        status="active",
        commitment_declaration=commitment_declaration,
        commitment_made_at=datetime.now(UTC) if commitment_declaration else None,
        accountability_partner_id=accountability_partner_id,
        shared_with_partner=accountability_partner_id is not None,
        deeper_purpose=deeper_purpose,
        what_i_lose=what_i_lose,
        voice_created=voice_transcript is not None,
        voice_transcript=voice_transcript,
    )
    db.add(goal)
    await db.flush()

    # Create milestones
    default_milestones = milestones or [
        {"percentage": 25, "title": "25% — Robo ya kwanza", "title_sw": "Robo ya kwanza"},
        {"percentage": 50, "title": "50% — Nusu", "title_sw": "Nusu ya lengo"},
        {"percentage": 75, "title": "75% — Robo tatu", "title_sw": "Robo tatu"},
        {"percentage": 100, "title": "100% — Lengo kamilifu!", "title_sw": "Lengo kamilifu!"},
    ]

    created_milestones = []
    for m in default_milestones:
        pct = m["percentage"]
        milestone = GoalMilestone(
            goal_id=goal.id,
            title=m.get("title", f"{pct}%"),
            title_sw=m.get("title_sw"),
            target_amount=round(target_amount * pct / 100, 2),
            percentage=pct,
            completed=False,
            sort_order=pct,
        )
        db.add(milestone)
        created_milestones.append({
            "percentage": pct,
            "title": milestone.title,
            "target_amount": milestone.target_amount,
        })

    await db.flush()

    # Build commitment message
    commitment_msg = None
    if commitment_declaration:
        commitment_msg = {
            "sw": f"Umeahidi: '{commitment_declaration}' — Msaidizi atakukumbusha kila siku!",
            "en": f"You committed: '{commitment_declaration}' — Msaidizi will remind you daily!",
        }

    logger.info(
        "goal_created",
        goal_id=str(goal.id),
        user_id=str(user_id),
        category=category,
        target_amount=target_amount,
        voice_created=voice_transcript is not None,
    )

    return {
        "goal_id": str(goal.id),
        "title": title,
        "title_sw": title_sw,
        "category": category,
        "target_amount": target_amount,
        "current_amount": 0,
        "remaining": target_amount,
        "target_date": str(target_date),
        "daily_target": daily_target,
        "weekly_target": weekly_target,
        "milestones": created_milestones,
        "has_active_goal": has_active,
        "commitment": commitment_msg,
        "accountability_partner": str(accountability_partner_id) if accountability_partner_id else None,
        "message_sw": (
            f"Lengo lako jipya: {title}. "
            f"Kwa KSh {weekly_target:,.0f}/wiki, utafikia tarehe {target_date}. "
            f"Msaidizi atakukumbusha kila siku — pamoja tunafanikiwa!"
        ),
        "message_en": (
            f"Your new goal: {title}. "
            f"At KSh {weekly_target:,.0f}/week, you'll reach it by {target_date}. "
            f"Msaidizi will remind you daily — together we succeed!"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Progress Updates
# ─────────────────────────────────────────────────────────────────────────────


async def update_progress(
    db: AsyncSession,
    goal_id: UUID,
    user_id: UUID,
    amount: float,
    notes: str | None = None,
    source: str = "manual",
    voice_transcript: str | None = None,
    mood: str | None = None,
    entry_date: date | None = None,
) -> dict[str, Any]:
    """
    Record a progress entry and update goal state.

    Handles: streak tracking, milestone detection, completion check,
    and generates behavioral nudges.
    """
    # Fetch goal
    result = await db.execute(
        select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == user_id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return {"error": "Goal not found", "error_sw": "Lengo halijapatikana"}

    if goal.status != "active":
        return {"error": f"Goal is {goal.status}, cannot update", "error_sw": f"Lengo ni {goal.status}"}

    if amount <= 0:
        return {"error": "Amount must be positive", "error_sw": "Kiasi lazima kiwe chanya"}

    today = entry_date or date.today()

    # Create progress entry
    entry = GoalProgressEntry(
        goal_id=goal_id,
        user_id=user_id,
        amount=amount,
        notes=notes,
        entry_date=today,
        source=source,
        voice_transcript=voice_transcript,
        mood=mood,
    )
    db.add(entry)

    # Update streak
    streak_broken = False
    if goal.last_contribution_date == today:
        pass  # Already contributed today
    elif goal.last_contribution_date and (today - goal.last_contribution_date).days == 1:
        goal.current_streak += 1
    elif goal.last_contribution_date and (today - goal.last_contribution_date).days > 1:
        streak_broken = goal.current_streak > 0
        goal.current_streak = 1
    else:
        goal.current_streak = 1

    goal.last_contribution_date = today
    goal.current_streak = goal.current_streak or 1
    if goal.current_streak > goal.best_streak:
        goal.best_streak = goal.current_streak

    # Update amount
    new_total = round(goal.current_amount + amount, 2)
    goal.current_amount = new_total
    goal.total_contributions = (goal.total_contributions or 0) + 1

    # Check milestones
    milestone_result = await db.execute(
        select(GoalMilestone).where(
            and_(
                GoalMilestone.goal_id == goal_id,
                GoalMilestone.completed == False,
            )
        ).order_by(GoalMilestone.sort_order)
    )
    milestones = milestone_result.scalars().all()

    milestone_hit = None
    for m in milestones:
        if new_total >= m.target_amount:
            m.completed = True
            m.completed_at = datetime.now(UTC)
            m.completed_amount = new_total
            milestone_hit = m.percentage

    # Check completion
    completed = new_total >= goal.target_amount
    if completed:
        goal.status = "completed"
        goal.completed_at = datetime.now(UTC)

    await db.flush()

    # Get prediction
    prediction = await get_time_to_goal(db, goal_id, user_id)

    # Build encouragement based on context
    encouragement = _build_encouragement(
        completed=completed,
        milestone_hit=milestone_hit,
        streak=goal.current_streak,
        streak_broken=streak_broken,
        prediction=prediction,
    )

    # Nudge selection
    nudge = _select_nudge(
        completed=completed,
        milestone_hit=milestone_hit,
        streak=goal.current_streak,
        streak_broken=streak_broken,
        prediction=prediction,
    )

    progress_pct = round((new_total / goal.target_amount) * 100, 1)

    return {
        "goal_id": str(goal.id),
        "new_total": new_total,
        "target": goal.target_amount,
        "remaining": round(goal.target_amount - new_total, 2),
        "progress_pct": progress_pct,
        "streak": {
            "current": goal.current_streak,
            "best": goal.best_streak,
        },
        "milestone_hit": milestone_hit,
        "completed": completed,
        "prediction": prediction,
        "encouragement": encouragement,
        "nudge": nudge,
        "voice_summary_sw": (
            f"Umeweka KSh {amount:,.0f}. Jumla: KSh {new_total:,.0f} ya KSh {goal.target_amount:,.0f}. "
            f"{progress_pct}% imefikiwa. Streak: siku {goal.current_streak}."
        ),
        "voice_summary_en": (
            f"Added KSh {amount:,.0f}. Total: KSh {new_total:,.0f} of KSh {goal.target_amount:,.0f}. "
            f"{progress_pct}% reached. Streak: {goal.current_streak} days."
        ),
    }


def _build_encouragement(
    completed: bool,
    milestone_hit: int | None,
    streak: int,
    streak_broken: bool,
    prediction: dict[str, Any],
) -> dict[str, str]:
    """Build encouragement message based on context."""
    if completed:
        return NUDGE_MESSAGES["goal_complete"]
    if milestone_hit and milestone_hit in NUDGE_MESSAGES:
        return NUDGE_MESSAGES[f"milestone_{milestone_hit}"]
    if streak_broken:
        return NUDGE_MESSAGES["streak_broken"]
    if streak >= 30:
        return NUDGE_MESSAGES["streak_30"]
    if streak >= 14:
        return NUDGE_MESSAGES["streak_14"]
    if streak >= 7:
        return NUDGE_MESSAGES["streak_7"]
    if streak >= 3:
        return NUDGE_MESSAGES["streak_3"]
    if prediction.get("ahead_of_schedule"):
        return NUDGE_MESSAGES["ahead_of_schedule"]
    return NUDGE_MESSAGES["small_win"]


def _select_nudge(
    completed: bool,
    milestone_hit: int | None,
    streak: int,
    streak_broken: bool,
    prediction: dict[str, Any],
) -> dict[str, str]:
    """Select the most appropriate behavioral nudge."""
    if completed:
        return {"type": "celebration", **NUDGE_MESSAGES["goal_complete"]}

    # Time-of-day based nudge
    hour = datetime.now(UTC).hour
    if hour < 10:
        base = NUDGE_MESSAGES["morning_motivation"]
        nudge_type = "morning"
    elif hour < 14:
        base = NUDGE_MESSAGES["eat_the_frog"]
        nudge_type = "midday"
    elif hour < 17:
        base = NUDGE_MESSAGES["midday_check"]
        nudge_type = "afternoon"
    else:
        base = NUDGE_MESSAGES["end_of_day"]
        nudge_type = "evening"

    return {"type": nudge_type, **base}


# ─────────────────────────────────────────────────────────────────────────────
# Goal Progress Retrieval
# ─────────────────────────────────────────────────────────────────────────────


async def get_goal_progress(
    db: AsyncSession,
    goal_id: UUID,
    user_id: UUID,
) -> dict[str, Any]:
    """Get detailed goal progress with milestones, streak, and prediction."""

    result = await db.execute(
        select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == user_id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return {"error": "Goal not found", "error_sw": "Lengo halijapatikana"}

    # Get milestones
    ms_result = await db.execute(
        select(GoalMilestone).where(GoalMilestone.goal_id == goal_id)
        .order_by(GoalMilestone.sort_order)
    )
    milestones = ms_result.scalars().all()

    # Get recent entries
    entries_result = await db.execute(
        select(GoalProgressEntry).where(GoalProgressEntry.goal_id == goal_id)
        .order_by(GoalProgressEntry.entry_date.desc())
        .limit(10)
    )
    recent_entries = entries_result.scalars().all()

    # Get prediction
    prediction = await get_time_to_goal(db, goal_id, user_id)

    progress_pct = round((goal.current_amount / goal.target_amount) * 100, 1)
    remaining = round(goal.target_amount - goal.current_amount, 2)

    # Weekly summary
    weekly_summary = None
    if goal.weekly_history:
        last_4 = goal.weekly_history[-4:]
        avg_actual = sum(w.get("actual", 0) for w in last_4) / max(len(last_4), 1)
        avg_target = sum(w.get("target", 0) for w in last_4) / max(len(last_4), 1)
        weekly_summary = {
            "avg_weekly_savings": round(avg_actual, 0),
            "avg_weekly_target": round(avg_target, 0),
            "weeks_tracked": len(goal.weekly_history),
        }

    return {
        "goal_id": str(goal.id),
        "title": goal.title,
        "title_sw": goal.title_sw,
        "category": goal.category,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "remaining": remaining,
        "progress_pct": progress_pct,
        "target_date": str(goal.target_date) if goal.target_date else None,
        "status": goal.status,
        "streak": {
            "current": goal.current_streak,
            "best": goal.best_streak,
            "last_contribution_date": str(goal.last_contribution_date) if goal.last_contribution_date else None,
        },
        "total_contributions": goal.total_contributions,
        "milestones": [
            {
                "percentage": m.percentage,
                "title": m.title,
                "title_sw": m.title_sw,
                "target_amount": m.target_amount,
                "completed": m.completed,
                "completed_at": str(m.completed_at) if m.completed_at else None,
            }
            for m in milestones
        ],
        "recent_entries": [
            {
                "amount": e.amount,
                "date": str(e.entry_date),
                "source": e.source,
                "notes": e.notes,
            }
            for e in recent_entries
        ],
        "prediction": prediction,
        "weekly_summary": weekly_summary,
        "deeper_purpose": goal.deeper_purpose,
        "what_i_lose": goal.what_i_lose,
        "commitment": goal.commitment_declaration,
        "voice_summary_sw": (
            f"{goal.title}: KSh {goal.current_amount:,.0f} ya KSh {goal.target_amount:,.0f}. "
            f"{progress_pct}%. Streak: siku {goal.current_streak}. Baki KSh {remaining:,.0f}."
        ),
        "voice_summary_en": (
            f"{goal.title}: KSh {goal.current_amount:,.0f} of KSh {goal.target_amount:,.0f}. "
            f"{progress_pct}% done. Streak: {goal.current_streak} days. KSh {remaining:,.0f} remaining."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Time-to-Goal Prediction (Polars)
# ─────────────────────────────────────────────────────────────────────────────


async def get_time_to_goal(
    db: AsyncSession,
    goal_id: UUID,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Predict time-to-goal using Polars rolling averages.

    Analyzes contribution patterns to predict:
    - Expected completion date
    - Best/worst case scenarios
    - Whether the worker is ahead or behind schedule
    - Weekly savings rate trend (increasing/stable/decreasing)
    """
    result = await db.execute(
        select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == user_id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return {"error": "Goal not found"}

    remaining = goal.target_amount - goal.current_amount
    if remaining <= 0:
        return {
            "status": "completed",
            "expected_date": str(date.today()),
            "days_remaining": 0,
            "message_sw": "Lengo limefikiwa!",
            "message_en": "Goal achieved!",
        }

    # Get all contributions for this goal
    entries_result = await db.execute(
        select(GoalProgressEntry).where(GoalProgressEntry.goal_id == goal_id)
        .order_by(GoalProgressEntry.entry_date)
    )
    entries = entries_result.scalars().all()

    if not entries or len(entries) < 2:
        # Insufficient data — use weekly target
        if goal.weekly_target and goal.weekly_target > 0:
            weeks_needed = remaining / goal.weekly_target
            expected = date.today() + timedelta(days=round(weeks_needed * 7))
            return {
                "status": "estimated",
                "method": "weekly_target",
                "weekly_rate": goal.weekly_target,
                "weeks_remaining": round(weeks_needed, 1),
                "expected_date": str(expected),
                "ahead_of_schedule": goal.target_date and expected <= goal.target_date,
                "confidence": "low",
                "message_sw": f"Ukitumia lengo la wiki, utafikia tarehe {expected}.",
                "message_en": f"At weekly target pace, you'll reach it by {expected}.",
            }
        return {
            "status": "insufficient_data",
            "message_sw": "Hakuna data ya kutosha. Weka michango zaidi!",
            "message_en": "Not enough data. Add more contributions!",
        }

    # Build Polars DataFrame for analysis
    data = {
        "date": [e.entry_date for e in entries],
        "amount": [float(e.amount) for e in entries],
    }
    df = pl.DataFrame(data)

    # Aggregate by week
    df = df.with_columns(
        pl.col("date").dt.truncate("1w").alias("week")
    )
    weekly = df.group_by("week").agg(
        pl.col("amount").sum().alias("weekly_amount"),
        pl.col("amount").count().alias("entries_count"),
    ).sort("week")

    # Calculate rolling 4-week average
    if len(weekly) >= 4:
        weekly = weekly.with_columns(
            pl.col("weekly_amount")
            .rolling_mean(window_size=4)
            .alias("rolling_avg"),
        )
        recent_rate = weekly.select("rolling_avg").tail(1).item()
    else:
        recent_rate = weekly.select("weekly_amount").mean().item()

    # Trend analysis (slope of weekly amounts)
    if len(weekly) >= 3:
        weekly = weekly.with_columns(
            pl.arange(0, len(weekly)).alias("week_index"),
        )
        # Simple linear regression for trend
        x = weekly.select("week_index").to_series().to_list()
        y = weekly.select("weekly_amount").to_series().to_list()
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(a * b for a, b in zip(x, y))
        sum_x2 = sum(a * a for a in x)
        slope = (n * sum_xy - sum_x * sum_y) / max(1, (n * sum_x2 - sum_x * sum_x))

        if slope > recent_rate * 0.1:
            trend = "increasing"
        elif slope < -recent_rate * 0.1:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"
        slope = 0

    # Predictions
    if recent_rate <= 0:
        return {
            "status": "stalled",
            "weekly_rate": 0,
            "trend": trend,
            "message_sw": "Haujasema chochote wiki hii. Anza leo — hata KSh 50!",
            "message_en": "No savings this week. Start today — even KSh 50!",
        }

    weeks_needed = remaining / recent_rate
    expected_date = date.today() + timedelta(days=round(weeks_needed * 7))

    # Best/worst case based on trend
    if trend == "increasing":
        best_rate = recent_rate * 1.4
        worst_rate = recent_rate * 0.8
    elif trend == "decreasing":
        best_rate = recent_rate * 1.1
        worst_rate = recent_rate * 0.6
    else:
        best_rate = recent_rate * 1.3
        worst_rate = recent_rate * 0.7

    best_date = date.today() + timedelta(days=round((remaining / best_rate) * 7))
    worst_date = date.today() + timedelta(days=round((remaining / worst_rate) * 7))

    ahead = goal.target_date and expected_date <= goal.target_date

    return {
        "status": "predicted",
        "weekly_rate": round(recent_rate, 0),
        "trend": trend,
        "trend_slope": round(slope, 2),
        "weeks_remaining": round(weeks_needed, 1),
        "expected_date": str(expected_date),
        "best_case_date": str(best_date),
        "worst_case_date": str(worst_date),
        "ahead_of_schedule": ahead,
        "days_vs_target": (expected_date - goal.target_date).days if goal.target_date else None,
        "confidence": "high" if len(weekly) >= 8 else "medium" if len(weekly) >= 4 else "low",
        "message_sw": (
            f"Kwa kasi hii, utafikia tarehe {expected_date}. "
            + ("Uko mbele ya mpango!" if ahead else "Jaribu kuongeza kidogo kila wiki.")
        ),
        "message_en": (
            f"At this pace, you'll reach it by {expected_date}. "
            + ("You're ahead of schedule!" if ahead else "Try adding a little more each week.")
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Obstacle Analysis (Polars)
# ─────────────────────────────────────────────────────────────────────────────


async def get_obstacle_analysis(
    db: AsyncSession,
    goal_id: UUID,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Identify potential obstacles to goal achievement using Polars pattern analysis.

    Detects:
    - Contribution gaps (missing days/weeks)
    - Declining contribution amounts
    - Weekend/weekday patterns
    - Seasonal patterns
    - Risk of abandonment
    """
    result = await db.execute(
        select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == user_id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return {"error": "Goal not found"}

    # Get all entries
    entries_result = await db.execute(
        select(GoalProgressEntry).where(GoalProgressEntry.goal_id == goal_id)
        .order_by(GoalProgressEntry.entry_date)
    )
    entries = entries_result.scalars().all()

    if len(entries) < 3:
        return {
            "goal_id": str(goal_id),
            "risk_level": "unknown",
            "obstacles": [],
            "recommendations": [
                {"sw": "Hakuna data ya kutosha. Endelea kurekodi michango yako!", "en": "Not enough data. Keep recording your contributions!"},
            ],
            "message_sw": "Tafadhali weka michango zaidi ili tuweze kukuchunguza.",
            "message_en": "Please add more contributions so we can analyze your patterns.",
        }

    # Build Polars DataFrame
    data = {
        "date": [e.entry_date for e in entries],
        "amount": [float(e.amount) for e in entries],
        "source": [e.source for e in entries],
    }
    df = pl.DataFrame(data)

    # Add time features
    df = df.with_columns([
        pl.col("date").dt.weekday().alias("weekday"),  # 1=Mon, 7=Sun
        pl.col("date").dt.truncate("1w").alias("week"),
    ])

    obstacles = []
    recommendations = []

    # 1. Check for contribution gaps
    if len(entries) >= 7:
        date_range = (entries[-1].entry_date - entries[0].entry_date).days
        expected_contributions = max(1, date_range)
        actual_days = df.select("date").n_unique()
        coverage = actual_days / expected_contributions

        if coverage < 0.3:
            obstacles.append({
                "type": "inconsistent_contributions",
                "severity": "high",
                "detail_sw": f"Umekuwa ukichangia siku {actual_days} kati ya {expected_contributions}.",
                "detail_en": f"You've contributed on {actual_days} out of {expected_contributions} days.",
            })
            recommendations.append({
                "sw": "Jaribu kuweka amri ya kila siku — hata KSh 20. Msaidizi atakukumbusha!",
                "en": "Try a daily habit — even KSh 20. Msaidizi will remind you!",
            })

    # 2. Check for declining amounts
    weekly = df.group_by("week").agg(
        pl.col("amount").sum().alias("total"),
    ).sort("week")

    if len(weekly) >= 4:
        recent_4 = weekly.tail(4).select("total").to_series().to_list()
        earlier_4 = weekly.head(4).select("total").to_series().to_list()
        recent_avg = sum(recent_4) / len(recent_4)
        earlier_avg = sum(earlier_4) / len(earlier_4)

        if recent_avg < earlier_avg * 0.6:
            obstacles.append({
                "type": "declining_amounts",
                "severity": "medium",
                "detail_sw": f"Michango yako imepungua kutoka KSh {earlier_avg:,.0f} hadi KSh {recent_avg:,.0f} kwa wiki.",
                "detail_en": f"Your contributions dropped from KSh {earlier_avg:,.0f} to KSh {recent_avg:,.0f} per week.",
            })
            recommendations.append({
                "sw": "Biashara inaweza kuwa imepungua. Jaribu kuokoa hata nusu ya kawaida.",
                "en": "Business may have slowed. Try saving even half your usual amount.",
            })

    # 3. Weekend vs weekday pattern
    weekday_avg = df.filter(pl.col("weekday") <= 5).select("amount").mean().item() if len(df.filter(pl.col("weekday") <= 5)) > 0 else 0
    weekend_avg = df.filter(pl.col("weekday") > 5).select("amount").mean().item() if len(df.filter(pl.col("weekday") > 5)) > 0 else 0

    if weekend_avg > weekday_avg * 2 and weekday_avg > 0:
        obstacles.append({
            "type": "weekday_gap",
            "severity": "low",
            "detail_sw": "Unachangia zaidi wikendi kuliko wiki. Jaribu kuongeza wiki.",
            "detail_en": "You contribute more on weekends. Try adding weekday contributions.",
        })

    # 4. Recent inactivity
    last_entry_date = entries[-1].entry_date
    days_since_last = (date.today() - last_entry_date).days
    if days_since_last >= 7:
        obstacles.append({
            "type": "recent_inactivity",
            "severity": "high" if days_since_last >= 14 else "medium",
            "detail_sw": f"Hujachangia kwa siku {days_since_last}. Streak yako iko hatarini!",
            "detail_en": f"No contribution in {days_since_last} days. Your streak is at risk!",
        })
        recommendations.append({
            "sw": f"Siku {days_since_last} bila kuokoa! Fanya leo — hata KSh 50 inatosha kuanza upya.",
            "en": f"{days_since_last} days without saving! Do it today — even KSh 50 restarts your streak.",
        })

    # 5. Risk assessment
    risk_score = 0
    if len(entries) >= 7:
        # Consistency score
        date_range = (entries[-1].entry_date - entries[0].entry_date).days
        unique_days = df.select("date").n_unique()
        consistency = unique_days / max(1, date_range)
        risk_score += (1 - consistency) * 40

        # Amount trend
        if len(weekly) >= 4:
            recent_total = weekly.tail(2).select("total").sum().item()
            earlier_total = weekly.head(2).select("total").sum().item()
            if earlier_total > 0:
                trend_ratio = recent_total / earlier_total
                risk_score += max(0, (1 - trend_ratio) * 30)

    # Days since last contribution
    risk_score += min(30, days_since_last * 3)

    if risk_score >= 60:
        risk_level = "high"
    elif risk_score >= 35:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Add loss aversion nudge if risk is elevated
    if risk_level in ("medium", "high"):
        remaining = goal.target_amount - goal.current_amount
        days_lost = max(1, days_since_last)
        recommendations.append({
            "sw": NUDGE_MESSAGES["loss_aversion"]["sw"].format(days=days_lost, amount=f"{remaining:,.0f}"),
            "en": NUDGE_MESSAGES["loss_aversion"]["en"].format(days=days_lost, amount=f"{remaining:,.0f}"),
        })

    return {
        "goal_id": str(goal_id),
        "risk_level": risk_level,
        "risk_score": round(risk_score, 1),
        "days_since_last_contribution": days_since_last,
        "obstacles": obstacles,
        "recommendations": recommendations,
        "pattern_summary": {
            "total_entries": len(entries),
            "unique_contributing_days": df.select("date").n_unique(),
            "avg_contribution": round(df.select("amount").mean().item(), 0),
            "avg_weekly": round(weekly.select("total").mean().item(), 0) if len(weekly) > 0 else 0,
        },
        "message_sw": (
            f"Uchambuzi wa lengo: Hatari ya {risk_level}. "
            + (f"Kuna vikwazo {len(obstacles)} vinavyoweza kukuzuia." if obstacles else "Hakuna vikwazo vinavyoonekana.")
        ),
        "message_en": (
            f"Goal analysis: {risk_level} risk. "
            + (f"{len(obstacles)} potential obstacles detected." if obstacles else "No obstacles detected.")
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Accountability Report
# ─────────────────────────────────────────────────────────────────────────────


async def get_accountability_report(
    db: AsyncSession,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Generate an accountability partner report for all active goals.

    Shows:
    - Progress summary across all goals
    - Streak status and consistency score
    - Peer comparison (social proof)
    - Commitment adherence
    - Weekly report card
    """
    # Get all active goals
    goals_result = await db.execute(
        select(Goal).where(
            and_(Goal.user_id == user_id, Goal.status == "active")
        ).order_by(Goal.created_at.desc())
    )
    goals = goals_result.scalars().all()

    if not goals:
        return {
            "user_id": str(user_id),
            "has_goals": False,
            "message_sw": "Huna lengo lolote. Tuanze na lengo jipya!",
            "message_en": "You have no goals. Let's start with a new one!",
        }

    goal_reports = []
    total_target = 0
    total_saved = 0
    all_streaks = []
    commitment_count = 0

    for goal in goals:
        total_target += goal.target_amount
        total_saved += goal.current_amount
        all_streaks.append(goal.current_streak)
        if goal.commitment_declaration:
            commitment_count += 1

        # Get recent entries for consistency score
        entries_result = await db.execute(
            select(GoalProgressEntry).where(GoalProgressEntry.goal_id == goal.id)
            .order_by(GoalProgressEntry.entry_date.desc())
            .limit(14)
        )
        recent = entries_result.scalars().all()

        # Consistency: days with contributions in last 14 days
        if recent:
            recent_dates = set(e.entry_date for e in recent)
            # Check last 14 days
            today = date.today()
            expected_dates = {today - timedelta(days=i) for i in range(14)}
            consistency = len(recent_dates & expected_dates) / 14
        else:
            consistency = 0

        progress_pct = round((goal.current_amount / goal.target_amount) * 100, 1)

        goal_reports.append({
            "goal_id": str(goal.id),
            "title": goal.title,
            "title_sw": goal.title_sw,
            "category": goal.category,
            "progress_pct": progress_pct,
            "current_amount": goal.current_amount,
            "target_amount": goal.target_amount,
            "streak": goal.current_streak,
            "consistency_score": round(consistency * 100, 1),
            "has_commitment": goal.commitment_declaration is not None,
            "days_active": (date.today() - goal.created_at.date()).days,
        })

    # Overall metrics
    avg_streak = sum(all_streaks) / len(all_streaks) if all_streaks else 0
    overall_progress = round((total_saved / total_target) * 100, 1) if total_target > 0 else 0

    # Grade
    if overall_progress >= 80:
        grade = "A"
        grade_msg_sw = "Bora sana! Wewe ni mfano!"
        grade_msg_en = "Excellent! You're a role model!"
    elif overall_progress >= 60:
        grade = "B"
        grade_msg_sw = "Vizuri! Endelea hivyo!"
        grade_msg_en = "Good! Keep it up!"
    elif overall_progress >= 40:
        grade = "C"
        grade_msg_sw = "Wapo sawa, lakini unaweza zaidi!"
        grade_msg_en = "You're okay, but you can do more!"
    elif overall_progress >= 20:
        grade = "D"
        grade_msg_sw = "Jaribu zaidi wiki ijayo. Msaidizi anakusaidia!"
        grade_msg_en = "Try harder next week. Msaidizi is here to help!"
    else:
        grade = "F"
        grade_msg_sw = "Hii ni ngumu — lakini usikate tamaa! Anza leo!"
        grade_msg_en = "This is hard — but don't give up! Start today!"

    # Social proof (count of other active goal-setters)
    others_result = await db.execute(
        select(func.count(func.distinct(Goal.user_id))).where(Goal.status == "active")
    )
    active_goal_setters = others_result.scalar() or 0

    return {
        "user_id": str(user_id),
        "has_goals": True,
        "overall_progress_pct": overall_progress,
        "total_saved": round(total_saved, 2),
        "total_target": total_target,
        "active_goals": len(goals),
        "average_streak": round(avg_streak, 1),
        "commitments_made": commitment_count,
        "grade": grade,
        "grade_message": {"sw": grade_msg_sw, "en": grade_msg_en},
        "goals": goal_reports,
        "social_proof": {
            "active_goal_setters": active_goal_setters,
            "message_sw": f"Wafanyakazi {active_goal_setters} wana malengo! Wewe pia uwe miongoni mwao!",
            "message_en": f"{active_goal_setters} workers have goals! Be among them!",
        },
        "week_report_card": {
            "overall_grade": grade,
            "progress": f"{overall_progress}%",
            "best_streak": max(all_streaks) if all_streaks else 0,
            "commitment_adherence": f"{commitment_count}/{len(goals)}",
        },
        "message_sw": (
            "Ripoti ya Mkataba:\n"
            + "\n".join(
                f"• {g['title_sw'] or g['title']}: {g['progress_pct']}% — streak siku {g['streak']}"
                for g in goal_reports
            )
            + f"\n\nDaraja: {grade}. {grade_msg_sw}"
        ),
        "message_en": (
            "Accountability Report:\n"
            + "\n".join(
                f"• {g['title']}: {g['progress_pct']}% — streak {g['streak']} days"
                for g in goal_reports
            )
            + f"\n\nGrade: {grade}. {grade_msg_en}"
        ),
    }
