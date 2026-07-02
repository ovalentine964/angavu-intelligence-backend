"""
Goal Planning Service — Create, track, and predict goal completion.

Core capabilities:
- Create/track goals with milestones (25/50/75/100%)
- Time-to-goal prediction based on income patterns
- Progress tracking with voice-friendly summaries
- Goal categories: business, personal, savings, debt
- Behavioral nudge generation
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_features import GoalContribution, GoalRecord

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Nudge Messages
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
    "streak_7": {
        "sw": "Wiki 1 mfululizo! Umefanya kazi nzuri. Endelea hivyo!",
        "en": "1 week streak! Great work. Keep going!",
    },
    "streak_30": {
        "sw": "Siku 30 mfululizo! Wewe ni mfano wa kuokoa!",
        "en": "30 days in a row! You're a savings role model!",
    },
    "missed_day": {
        "sw": "Hujaokoa leo — si vibaya. Kesho ni nafasi mpya. Hata KSh 20 inatosha!",
        "en": "Didn't save today — that's okay. Tomorrow is a fresh start. Even KSh 20 works!",
    },
    "milestone_25": {
        "sw": "Hongera! Umefikia 25% ya lengo lako! Uko kwenye njia sahihi!",
        "en": "Congratulations! You've reached 25% of your goal! You're on track!",
    },
    "milestone_50": {
        "sw": "NUSU! Umefikia nusu ya lengo lako! Sasa ni wakati wa kuongeza kasi!",
        "en": "HALFWAY! You've reached 50% of your goal! Time to pick up pace!",
    },
    "milestone_75": {
        "sw": "75%! Umefikia robo tatu! Baki kidogo tu — unaweza!",
        "en": "75%! Three quarters done! Just a little more — you can do it!",
    },
    "goal_complete": {
        "sw": "Hongera sana! Umefikia lengo lako! Je, ungependa kuanza lengo jipya?",
        "en": "Congratulations! You've reached your goal! Want to start a new one?",
    },
    "behind_schedule": {
        "sw": "Wiki hii hujaokoa kama ulivyopanga. Sijali — hebu tubadilishe mpango kidogo.",
        "en": "Didn't save as planned this week. That's okay — let's adjust the plan a bit.",
    },
    "ahead_of_schedule": {
        "sw": "Uko mbele ya mpango! Kwa kasi hii, utafikia lengo lako mapema!",
        "en": "You're ahead of schedule! At this pace, you'll reach your goal early!",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Goal CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def create_goal(
    db: AsyncSession,
    user_id: UUID,
    goal_type: str,
    title: str,
    target_amount: float,
    current_amount: float = 0,
    title_sw: Optional[str] = None,
    description: Optional[str] = None,
    deadline: Optional[date] = None,
    deeper_purpose: Optional[str] = None,
    currency: str = "KES",
) -> Dict[str, Any]:
    """Create a new goal with auto-generated milestones."""

    # Auto-generate deadline if not provided (estimate based on amount)
    if deadline is None:
        # Assume KSh 1,500/month savings capacity as default
        months_needed = max(1, round(target_amount / 1500))
        deadline = date.today() + timedelta(days=months_needed * 30)

    remaining = target_amount - current_amount
    days_to_deadline = max(1, (deadline - date.today()).days)
    weeks_to_deadline = max(1, days_to_deadline / 7)
    daily_target = round(remaining / max(1, days_to_deadline), 0)
    weekly_target = round(remaining / max(1, weeks_to_deadline), 0)

    # Generate milestones
    milestones = []
    for pct in [25, 50, 75, 100]:
        milestone_amount = round(target_amount * pct / 100, 2)
        milestones.append({
            "pct": pct,
            "amount": milestone_amount,
            "reached": current_amount >= milestone_amount,
            "date": None,
        })

    # Check if user already has a primary goal
    existing_primary = await db.execute(
        select(GoalRecord).where(
            and_(
                GoalRecord.user_id == user_id,
                GoalRecord.priority == "primary",
                GoalRecord.status == "active",
            )
        )
    )
    has_primary = existing_primary.scalar_one_or_none() is not None
    priority = "queued" if has_primary else "primary"

    goal = GoalRecord(
        user_id=user_id,
        goal_type=goal_type,
        title=title,
        title_sw=title_sw,
        description=description,
        target_amount=target_amount,
        current_amount=current_amount,
        currency=currency,
        deadline=deadline,
        status="active",
        priority=priority,
        milestones=milestones,
        weekly_target=weekly_target,
        daily_target=daily_target,
        deeper_purpose=deeper_purpose,
    )
    db.add(goal)
    await db.flush()

    return {
        "goal_id": str(goal.id),
        "title": title,
        "goal_type": goal_type,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "remaining": round(remaining, 2),
        "deadline": str(deadline),
        "daily_target": daily_target,
        "weekly_target": weekly_target,
        "priority": priority,
        "milestones": milestones,
        "message_sw": f"Lengo lako: {title}. Kwa KSh {weekly_target:,.0f}/wiki, utafikia tarehe {deadline}. Twende!",
        "message_en": f"Your goal: {title}. At KSh {weekly_target:,.0f}/week, you'll reach it by {deadline}. Let's go!",
    }


async def record_contribution(
    db: AsyncSession,
    goal_id: UUID,
    user_id: UUID,
    amount: float,
    source: str = "manual",
) -> Dict[str, Any]:
    """Record a contribution toward a goal and update progress."""

    # Get the goal
    result = await db.execute(
        select(GoalRecord).where(
            and_(GoalRecord.id == goal_id, GoalRecord.user_id == user_id)
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        return {"error": "Goal not found"}

    # Record contribution
    contribution = GoalContribution(
        goal_id=goal_id,
        user_id=user_id,
        amount=amount,
        source=source,
    )
    db.add(contribution)

    # Update goal
    new_amount = goal.current_amount + amount
    today = date.today()

    # Update streak
    if goal.last_save_date == today:
        # Already saved today, no streak change
        pass
    elif goal.last_save_date and (today - goal.last_save_date).days == 1:
        goal.current_streak += 1
    elif goal.last_save_date and (today - goal.last_save_date).days > 1:
        goal.current_streak = 1
    else:
        goal.current_streak = 1

    goal.last_save_date = today
    goal.current_amount = round(new_amount, 2)
    if goal.current_streak > goal.best_streak:
        goal.best_streak = goal.current_streak

    # Check milestones
    milestone_hit = None
    if goal.milestones:
        for m in goal.milestones:
            if not m["reached"] and new_amount >= m["amount"]:
                m["reached"] = True
                m["date"] = str(today)
                milestone_hit = m["pct"]

    # Check completion
    completed = new_amount >= goal.target_amount
    if completed:
        goal.status = "completed"
        goal.completed_at = datetime.now(timezone.utc)
        goal.priority = "completed"

    # Time-to-goal prediction
    prediction = await _predict_time_to_goal(db, goal)

    # Build encouragement
    encouragement = None
    if completed:
        encouragement = NUDGE_MESSAGES["goal_complete"]
    elif milestone_hit == 25:
        encouragement = NUDGE_MESSAGES["milestone_25"]
    elif milestone_hit == 50:
        encouragement = NUDGE_MESSAGES["milestone_50"]
    elif milestone_hit == 75:
        encouragement = NUDGE_MESSAGES["milestone_75"]

    return {
        "goal_id": str(goal.id),
        "new_total": round(new_amount, 2),
        "target": goal.target_amount,
        "progress_pct": round((new_amount / goal.target_amount) * 100, 1),
        "streak": goal.current_streak,
        "milestone_hit": milestone_hit,
        "completed": completed,
        "prediction": prediction,
        "encouragement": encouragement,
    }


async def get_goal_progress(
    db: AsyncSession,
    user_id: UUID,
    goal_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Get progress for a user's goal (defaults to primary active goal)."""

    if goal_id:
        result = await db.execute(
            select(GoalRecord).where(
                and_(GoalRecord.id == goal_id, GoalRecord.user_id == user_id)
            )
        )
    else:
        result = await db.execute(
            select(GoalRecord).where(
                and_(
                    GoalRecord.user_id == user_id,
                    GoalRecord.status == "active",
                    GoalRecord.priority == "primary",
                )
            )
        )

    goal = result.scalar_one_or_none()
    if not goal:
        # Try any active goal
        result = await db.execute(
            select(GoalRecord).where(
                and_(GoalRecord.user_id == user_id, GoalRecord.status == "active")
            ).order_by(GoalRecord.created_at.desc()).limit(1)
        )
        goal = result.scalar_one_or_none()

    if not goal:
        return {"error": "No active goal found"}

    prediction = await _predict_time_to_goal(db, goal)

    # Weekly history summary
    weekly_summary = None
    if goal.weekly_history:
        last_4 = goal.weekly_history[-4:] if len(goal.weekly_history) >= 4 else goal.weekly_history
        avg_actual = sum(w.get("actual", 0) for w in last_4) / max(len(last_4), 1)
        avg_target = sum(w.get("target", 0) for w in last_4) / max(len(last_4), 1)
        weekly_summary = {
            "avg_weekly_savings": round(avg_actual, 0),
            "avg_weekly_target": round(avg_target, 0),
            "weeks_tracked": len(goal.weekly_history),
        }

    progress_pct = round((goal.current_amount / goal.target_amount) * 100, 1)

    # Voice-friendly summary
    remaining = goal.target_amount - goal.current_amount
    voice_summary_sw = (
        f"{goal.title}: KSh {goal.current_amount:,.0f} ya KSh {goal.target_amount:,.0f}. "
        f"{progress_pct}%. Streak: siku {goal.current_streak}. "
        f"Baki KSh {remaining:,.0f}. "
    )
    if prediction.get("expected_date"):
        voice_summary_sw += f"Kwa kasi hii: tarehe {prediction['expected_date']}."

    return {
        "goal_id": str(goal.id),
        "title": goal.title,
        "goal_type": goal.goal_type,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "remaining": round(remaining, 2),
        "progress_pct": progress_pct,
        "deadline": str(goal.deadline) if goal.deadline else None,
        "status": goal.status,
        "priority": goal.priority,
        "streak": {
            "current": goal.current_streak,
            "best": goal.best_streak,
            "last_save_date": str(goal.last_save_date) if goal.last_save_date else None,
        },
        "milestones": goal.milestones,
        "prediction": prediction,
        "weekly_summary": weekly_summary,
        "deeper_purpose": goal.deeper_purpose,
        "voice_summary_sw": voice_summary_sw,
        "voice_summary_en": (
            f"{goal.title}: KSh {goal.current_amount:,.0f} of KSh {goal.target_amount:,.0f}. "
            f"{progress_pct}% done. Streak: {goal.current_streak} days. "
            f"KSh {remaining:,.0f} remaining."
        ),
    }


async def get_nudge(
    db: AsyncSession,
    user_id: UUID,
    nudge_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a behavioral nudge based on current goal state."""

    progress = await get_goal_progress(db, user_id)
    if "error" in progress:
        return {"nudge": "create_goal", "message_sw": "Huna lengo bado. Tuanze!", "message_en": "No goal yet. Let's start!"}

    streak = progress["streak"]["current"]
    pct = progress["progress_pct"]

    # Select nudge based on context
    if nudge_type:
        msg = NUDGE_MESSAGES.get(nudge_type)
    elif pct >= 100:
        msg = NUDGE_MESSAGES["goal_complete"]
    elif streak >= 30:
        msg = NUDGE_MESSAGES["streak_30"]
    elif streak >= 7:
        msg = NUDGE_MESSAGES["streak_7"]
    elif progress["prediction"].get("ahead_of_schedule"):
        msg = NUDGE_MESSAGES["ahead_of_schedule"]
    else:
        # Default: time-of-day based
        hour = datetime.now(timezone.utc).hour
        if hour < 10:
            msg = NUDGE_MESSAGES["morning_motivation"]
        elif hour < 14:
            msg = NUDGE_MESSAGES["eat_the_frog"]
        elif hour < 17:
            msg = NUDGE_MESSAGES["midday_check"]
        else:
            msg = NUDGE_MESSAGES["end_of_day"]

    return {
        "nudge_type": nudge_type or "auto",
        "goal_title": progress["title"],
        "progress_pct": progress["progress_pct"],
        "streak": progress["streak"]["current"],
        "message_sw": msg["sw"],
        "message_en": msg["en"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _predict_time_to_goal(
    db: AsyncSession,
    goal: GoalRecord,
) -> Dict[str, Any]:
    """Predict time-to-goal based on contribution history."""

    remaining = goal.target_amount - goal.current_amount
    if remaining <= 0:
        return {
            "status": "completed",
            "expected_date": str(date.today()),
            "days_remaining": 0,
        }

    # Get recent contributions (last 28 days)
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(days=28)
    result = await db.execute(
        select(GoalContribution).where(
            and_(
                GoalContribution.goal_id == goal.id,
                GoalContribution.recorded_at >= four_weeks_ago,
            )
        )
    )
    recent = result.scalars().all()

    if not recent:
        # No recent data — use weekly_target if set
        if goal.weekly_target and goal.weekly_target > 0:
            weeks_needed = remaining / goal.weekly_target
            expected = date.today() + timedelta(days=round(weeks_needed * 7))
            return {
                "status": "estimated",
                "method": "weekly_target",
                "weeks_remaining": round(weeks_needed, 1),
                "expected_date": str(expected),
                "ahead_of_schedule": goal.deadline and expected <= goal.deadline,
            }
        return {"status": "insufficient_data", "message": "No recent contributions to analyze"}

    # Calculate weekly rate
    total_recent = sum(c.amount for c in recent)
    weeks_span = max(1, (date.today() - four_weeks_ago.date()).days / 7)
    weekly_rate = total_recent / weeks_span

    if weekly_rate <= 0:
        return {"status": "stalled", "message": "No recent savings detected"}

    weeks_needed = remaining / weekly_rate
    expected = date.today() + timedelta(days=round(weeks_needed * 7))

    # Best/worst case (±30%)
    best_weeks = remaining / (weekly_rate * 1.3)
    worst_weeks = remaining / (weekly_rate * 0.7)

    ahead = goal.deadline and expected <= goal.deadline

    return {
        "status": "predicted",
        "weekly_rate": round(weekly_rate, 0),
        "weeks_remaining": round(weeks_needed, 1),
        "expected_date": str(expected),
        "best_case_date": str(date.today() + timedelta(days=round(best_weeks * 7))),
        "worst_case_date": str(date.today() + timedelta(days=round(worst_weeks * 7))),
        "ahead_of_schedule": ahead,
        "days_vs_deadline": (expected - goal.deadline).days if goal.deadline else None,
    }
