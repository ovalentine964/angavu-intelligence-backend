"""
Stickiness / Engagement Service — Gamification engine for habit formation.

Implements the Hook Model: Trigger → Action → Variable Reward → Investment.
Designed for Africa's informal economy workers with:
- Anti-shame: No public leaderboards, anonymized comparisons only
- Variable rewards: Surprise elements to maintain engagement
- Streak protection: Forgiveness mechanics (shields)
- Social proof: Anonymized peer comparison
- Swahili-first: All user-facing text in Swahili with English fallback

Target metrics:
- D1 retention >80%, D7 >40%, D30 >20%
- DAU/MAU ratio >50%
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.gamification import (
    AHA_MOMENTS,
    BADGES,
    LEVELS,
    SOCIAL_PROOF_TEMPLATES,
    VARIABLE_REWARDS,
    WISDOM_QUOTES,
    get_badge_by_name,
    get_level_for_xp,
    get_next_level,
)
from app.models.stickiness import (
    Badge,
    Streak,
    UserBadge,
    UserEngagement,
    UserLevel,
)

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Engagement Metrics
# ═══════════════════════════════════════════════════════════════════════════════


async def get_user_engagement(
    db: AsyncSession,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Get comprehensive engagement metrics for a user.

    Returns retention signals, activity summary, and streak info
    needed for the engagement dashboard.
    """
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Activity in last 30 days ────────────────────────────────────────
    thirty_days_ago = today - timedelta(days=30)
    result = await db.execute(
        select(UserEngagement)
        .where(
            and_(
                UserEngagement.user_id == user_id,
                UserEngagement.date >= thirty_days_ago,
            )
        )
        .order_by(UserEngagement.date.desc())
    )
    records = result.scalars().all()

    active_dates = {r.date.date() for r in records if r.daily_active}
    total_actions = sum(r.actions_count for r in records)
    total_xp = sum(r.xp_earned for r in records)

    # ── Retention calculations ──────────────────────────────────────────
    # D1: active today or yesterday
    d1_active = any(
        d >= (today - timedelta(days=1)).date() for d in active_dates
    )

    # D7: active in last 7 days
    seven_days_ago = (today - timedelta(days=7)).date()
    d7_active = any(d >= seven_days_ago for d in active_dates)
    d7_active_days = sum(1 for d in active_dates if d >= seven_days_ago)

    # D30: active in last 30 days
    d30_active_days = len(active_dates)

    # DAU/MAU ratio (approximate)
    dau = 1 if today.date() in active_dates else 0
    mau = len({d for d in active_dates if d >= (today - timedelta(days=30)).date()})
    dau_mau_ratio = round(dau / max(mau, 1), 2)

    # ── Current streak ──────────────────────────────────────────────────
    streak_result = await db.execute(
        select(Streak).where(Streak.user_id == user_id)
    )
    streak = streak_result.scalar_one_or_none()
    current_streak = streak.current_streak if streak else 0
    longest_streak = streak.longest_streak if streak else 0

    # ── Level info ──────────────────────────────────────────────────────
    level_result = await db.execute(
        select(UserLevel).where(UserLevel.user_id == user_id)
    )
    user_level = level_result.scalar_one_or_none()
    level = user_level.level if user_level else 1
    xp = user_level.xp if user_level else 0

    # ── Aha moments hit ─────────────────────────────────────────────────
    aha_moments_hit = set()
    for r in records:
        if r.aha_moments_hit:
            aha_moments_hit.update(r.aha_moments_hit)

    return {
        "user_id": str(user_id),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "level": level,
        "xp": xp,
        "total_actions_30d": total_actions,
        "total_xp_30d": total_xp,
        "active_days_30d": d30_active_days,
        "active_days_7d": d7_active_days,
        "retention": {
            "d1_active": d1_active,
            "d7_active": d7_active,
            "d30_active_days": d30_active_days,
            "dau_mau_ratio": dau_mau_ratio,
        },
        "aha_moments_hit": sorted(aha_moments_hit),
        "is_active_today": today.date() in active_dates,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Streak Management
# ═══════════════════════════════════════════════════════════════════════════════


async def get_streak_status(
    db: AsyncSession,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Get current streak status with protection info.

    Returns streak count, protection shields available, and
    motivational message in Swahili.
    """
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(Streak).where(Streak.user_id == user_id)
    )
    streak = result.scalar_one_or_none()

    if not streak:
        # Initialize streak record
        streak = Streak(user_id=user_id)
        db.add(streak)
        await db.flush()

    # Check if streak is at risk (missed yesterday)
    yesterday = (today - timedelta(days=1)).date()
    streak_at_risk = False
    if streak.last_active_date:
        last_active = streak.last_active_date.date()
        if last_active < yesterday and last_active < today.date():
            streak_at_risk = True

    # Get user level for shield count
    level_result = await db.execute(
        select(UserLevel).where(UserLevel.user_id == user_id)
    )
    user_level = level_result.scalar_one_or_none()
    protection_count = user_level.streak_protection_count if user_level else 0

    # Motivational message based on streak
    if streak.current_streak == 0:
        message_sw = "Anza mfululizo wako leo! Kila siku ni hatua mpya."
        message_en = "Start your streak today! Every day is a new step."
    elif streak.current_streak < 7:
        message_sw = f"Siku {streak.current_streak} mfululizo! Endelea — wiki moja inakuja!"
        message_en = f"{streak.current_streak} days in a row! Keep going — one week is coming!"
    elif streak.current_streak < 30:
        message_sw = f"Siku {streak.current_streak} mfululizo! Wewe ni mfano wa kuendelea!"
        message_en = f"{streak.current_streak} days in a row! You're a model of consistency!"
    else:
        message_sw = f"Siku {streak.current_streak} mfululizo! Wewe ni hadithi ya biashara!"
        message_en = f"{streak.current_streak} days in a row! You're a business legend!"

    return {
        "user_id": str(user_id),
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
        "protection_available": protection_count > 0,
        "protection_count": protection_count,
        "streak_at_risk": streak_at_risk,
        "last_active_date": streak.last_active_date.isoformat() if streak.last_active_date else None,
        "freeze_count": streak.freeze_count,
        "message_sw": message_sw,
        "message_en": message_en,
    }


async def record_activity(
    db: AsyncSession,
    user_id: UUID,
    xp_earned: int = 0,
    actions_increment: int = 1,
) -> dict[str, Any]:
    """
    Record user activity and update streak.

    Called on every meaningful action (login, transaction, insight view).
    Returns updated streak and any newly earned badges.
    """
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Update daily engagement ─────────────────────────────────────────
    result = await db.execute(
        select(UserEngagement).where(
            and_(
                UserEngagement.user_id == user_id,
                UserEngagement.date == today,
            )
        )
    )
    engagement = result.scalar_one_or_none()

    if not engagement:
        engagement = UserEngagement(
            user_id=user_id,
            date=today,
            daily_active=True,
            actions_count=actions_increment,
            xp_earned=xp_earned,
        )
        db.add(engagement)
    else:
        engagement.daily_active = True
        engagement.actions_count += actions_increment
        engagement.xp_earned += xp_earned

    # ── Update streak ───────────────────────────────────────────────────
    streak_result = await db.execute(
        select(Streak).where(Streak.user_id == user_id)
    )
    streak = streak_result.scalar_one_or_none()

    if not streak:
        streak = Streak(
            user_id=user_id,
            current_streak=1,
            longest_streak=1,
            last_active_date=today,
        )
        db.add(streak)
    else:
        last_active = streak.last_active_date
        if last_active is None:
            # First activity ever
            streak.current_streak = 1
            streak.longest_streak = 1
            streak.last_active_date = today
        elif last_active.date() == today.date():
            # Already active today — no streak change
            pass
        elif last_active.date() == (today - timedelta(days=1)).date():
            # Consecutive day — increment streak
            streak.current_streak += 1
            streak.longest_streak = max(streak.longest_streak, streak.current_streak)
            streak.last_active_date = today
            streak.protection_used_today = False
        elif streak.protection_count > 0 and not streak.protection_used_today:
            # Missed a day but has protection — use shield
            streak.protection_count -= 1
            streak.freeze_count += 1
            streak.last_active_date = today
            streak.protection_used_today = True
            logger.info(
                "streak_protection_used",
                user_id=str(user_id),
                remaining_shields=streak.protection_count,
            )
        else:
            # Missed a day, no protection — reset streak
            if streak.current_streak > 0:
                logger.info(
                    "streak_reset",
                    user_id=str(user_id),
                    lost_streak=streak.current_streak,
                )
            streak.current_streak = 1
            streak.last_active_date = today

    # ── Update XP and check level up ────────────────────────────────────
    level_result = await db.execute(
        select(UserLevel).where(UserLevel.user_id == user_id)
    )
    user_level = level_result.scalar_one_or_none()

    if not user_level:
        user_level = UserLevel(
            user_id=user_id,
            level=1,
            xp=xp_earned,
            xp_to_next=LEVELS[0]["xp_to_next"],
            streak_protection_count=0,
        )
        db.add(user_level)
    else:
        user_level.xp += xp_earned

    # Check for level up
    leveled_up = False
    while True:
        next_lvl = get_next_level(user_level.level)
        if next_lvl is None:
            break
        if user_level.xp >= next_lvl["xp_required"]:
            user_level.level = next_lvl["level"]
            user_level.xp_to_next = next_lvl["xp_to_next"]
            # Award streak shields based on level perks
            shield_count = sum(
                1 for p in next_lvl.get("perks", [])
                if p.startswith("streak_shield")
            )
            user_level.streak_protection_count = shield_count
            streak.protection_count = shield_count
            leveled_up = True
            logger.info(
                "user_leveled_up",
                user_id=str(user_id),
                new_level=next_lvl["level"],
                new_level_name=next_lvl["name"],
            )
        else:
            break

    await db.flush()

    # ── Check for new badge eligibility ─────────────────────────────────
    newly_earned = await _check_badge_eligibility(db, user_id, engagement)

    return {
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
        "xp_earned_today": engagement.xp_earned,
        "total_xp": user_level.xp,
        "level": user_level.level,
        "leveled_up": leveled_up,
        "newly_earned_badges": newly_earned,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Badges
# ═══════════════════════════════════════════════════════════════════════════════


async def get_badges(
    db: AsyncSession,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Get all badges with earned/unearned status for a user.

    Returns the full badge catalog with the user's progress,
    organized by category.
    """
    # Get user's earned badges
    result = await db.execute(
        select(UserBadge)
        .where(UserBadge.user_id == user_id)
        .join(Badge)
        .order_by(UserBadge.earned_at.desc())
    )
    earned_records = result.scalars().all()
    earned_ids = {str(r.badge_id) for r in earned_records}

    # Get badge definitions
    badge_result = await db.execute(select(Badge).where(Badge.is_active))
    db_badges = badge_result.scalars().all()
    db_badge_map = {str(b.id): b for b in db_badges}

    # Map earned badges with timestamps
    earned_at_map = {}
    for r in earned_records:
        earned_at_map[str(r.badge_id)] = r.earned_at.isoformat()

    # Build response organized by category
    categories: dict[str, list] = {}
    for badge_data in BADGES:
        category = badge_data["category"]
        if category not in categories:
            categories[category] = []

        # Find matching DB badge
        db_badge = None
        for b in db_badges:
            if b.name == badge_data["name"]:
                db_badge = b
                break

        badge_entry = {
            "name": badge_data["name"],
            "swahili_name": badge_data["swahili_name"],
            "description": badge_data["description"],
            "description_sw": badge_data.get("description_sw", ""),
            "icon": badge_data["icon"],
            "category": category,
            "xp_reward": badge_data["xp_reward"],
            "earned": str(db_badge.id) in earned_ids if db_badge else False,
            "earned_at": earned_at_map.get(str(db_badge.id)) if db_badge else None,
        }
        categories[category].append(badge_entry)

    total_earned = len(earned_ids)
    total_badges = len(BADGES)

    return {
        "user_id": str(user_id),
        "total_earned": total_earned,
        "total_available": total_badges,
        "completion_percent": round(total_earned / max(total_badges, 1) * 100, 1),
        "categories": categories,
        "recent_badges": [
            {
                "name": next(
                    (b["name"] for b in BADGES
                     if db_badge_map.get(str(r.badge_id)) and
                     db_badge_map[str(r.badge_id)].name == b["name"]),
                    "unknown"
                ),
                "swahili_name": next(
                    (b["swahili_name"] for b in BADGES
                     if db_badge_map.get(str(r.badge_id)) and
                     db_badge_map[str(r.badge_id)].name == b["name"]),
                    ""
                ),
                "icon": next(
                    (b["icon"] for b in BADGES
                     if db_badge_map.get(str(r.badge_id)) and
                     db_badge_map[str(r.badge_id)].name == b["name"]),
                    "🏅"
                ),
                "earned_at": r.earned_at.isoformat(),
            }
            for r in earned_records[:5]
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Level Progress
# ═══════════════════════════════════════════════════════════════════════════════


async def get_level_progress(
    db: AsyncSession,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Get user's current level, XP progress, and next level info.

    Includes a progress bar percentage and list of unlocked perks.
    """
    result = await db.execute(
        select(UserLevel).where(UserLevel.user_id == user_id)
    )
    user_level = result.scalar_one_or_none()

    if not user_level:
        # Initialize at level 1
        user_level = UserLevel(
            user_id=user_id,
            level=1,
            xp=0,
            xp_to_next=LEVELS[0]["xp_to_next"],
            streak_protection_count=0,
        )
        db.add(user_level)
        await db.flush()

    current_level_def = get_level_for_xp(user_level.xp)
    next_level_def = get_next_level(user_level.level)

    # Progress percentage to next level
    if next_level_def:
        xp_in_level = user_level.xp - current_level_def["xp_required"]
        xp_needed = next_level_def["xp_required"] - current_level_def["xp_required"]
        progress_percent = round(xp_in_level / max(xp_needed, 1) * 100, 1)
    else:
        progress_percent = 100.0  # Max level

    return {
        "user_id": str(user_id),
        "level": user_level.level,
        "level_name": current_level_def["name"],
        "level_name_en": current_level_def["name_en"],
        "level_icon": current_level_def["icon"],
        "xp": user_level.xp,
        "xp_to_next": user_level.xp_to_next,
        "progress_percent": min(progress_percent, 100.0),
        "current_level_description": current_level_def["description_sw"],
        "current_level_description_en": current_level_def["description"],
        "perks_unlocked": current_level_def.get("perks", []),
        "next_level": {
            "level": next_level_def["level"],
            "name": next_level_def["name"],
            "name_en": next_level_def["name_en"],
            "icon": next_level_def["icon"],
            "xp_required": next_level_def["xp_required"],
            "description": next_level_def["description_sw"],
            "description_en": next_level_def["description"],
        } if next_level_def else None,
        "streak_protection_count": user_level.streak_protection_count,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Variable Rewards
# ═══════════════════════════════════════════════════════════════════════════════


async def get_variable_reward(
    db: AsyncSession,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Generate a variable (surprise) reward for the user.

    Uses weighted random selection with cooldown tracking.
    The surprise element is key to the Hook Model — users don't know
    what reward they'll get, creating anticipation.
    """
    now = datetime.now(timezone.utc)

    # Get user level for context
    level_result = await db.execute(
        select(UserLevel).where(UserLevel.user_id == user_id)
    )
    user_level = level_result.scalar_one_or_none()

    if not user_level:
        return {
            "has_reward": False,
            "message_sw": "Anza kutumia Angavu Intelligence kupata zawadi!",
            "message_en": "Start using Angavu Intelligence to earn rewards!",
        }

    # Check cooldown (don't give rewards too frequently)
    if user_level.last_reward_at:
        hours_since_last = (now - user_level.last_reward_at).total_seconds() / 3600
        if hours_since_last < 4:
            return {
                "has_reward": False,
                "cooldown_remaining_hours": round(4 - hours_since_last, 1),
                "message_sw": f"Zawadi yako ijayo inapatikana baada ya saa {int(4 - hours_since_last)}. Endelea kufanya kazi!",
                "message_en": f"Your next reward is available in {int(4 - hours_since_last)}h. Keep working!",
            }

    # Weighted random selection
    reward_templates = [
        r for r in VARIABLE_REWARDS
        if r["cooldown_hours"]  # Include all
    ]
    weights = [r["weight"] for r in reward_templates]
    chosen = random.choices(reward_templates, weights=weights, k=1)[0]

    # Generate reward content based on type
    reward = _generate_reward_content(chosen, user_level)

    # Update last reward timestamp
    user_level.last_reward_at = now

    # Award bonus XP if applicable
    bonus_xp = reward.get("bonus_xp", 0)
    if bonus_xp > 0:
        user_level.xp += bonus_xp

    await db.flush()

    return {
        "has_reward": True,
        "reward_type": chosen["type"],
        "title": reward.get("title", chosen.get("title", "")),
        "title_en": reward.get("title_en", chosen.get("title_en", "")),
        "message_sw": reward.get("message_sw", ""),
        "message_en": reward.get("message_en", ""),
        "icon": reward.get("icon", chosen.get("icon", "🎁")),
        "bonus_xp": bonus_xp,
        "total_xp": user_level.xp,
    }


def _generate_reward_content(
    template: dict[str, Any],
    user_level: Any,
) -> dict[str, Any]:
    """Generate concrete reward content from a template."""
    reward_type = template["type"]

    if reward_type == "insight_boost":
        percent = random.randint(60, 95)
        categories = ["mama mboga", "dukawallah", "boda boda", "vendor"]
        category = random.choice(categories)
        return {
            "title": template["title"],
            "title_en": template["title_en"],
            "message_sw": template["message_sw"].format(percent=percent, category=category),
            "message_en": template["message_en"].format(percent=percent, category=category),
            "icon": template["icon"],
            "bonus_xp": 0,
        }

    elif reward_type == "streak_bonus":
        # Bonus XP scales with level
        base_xp = 20 * user_level.level
        return {
            "title": template["title"],
            "title_en": template["title_en"],
            "message_sw": template["message_sw"].format(days=7, xp=base_xp),
            "message_en": template["message_en"].format(days=7, xp=base_xp),
            "icon": template["icon"],
            "bonus_xp": base_xp,
        }

    elif reward_type == "peer_comparison":
        count = random.randint(50, 500)
        return {
            "title": template["title"],
            "title_en": template["title_en"],
            "message_sw": template["message_sw"].format(count=count),
            "message_en": template["message_en"].format(count=count),
            "icon": template["icon"],
            "bonus_xp": 0,
        }

    elif reward_type == "lucky_day":
        multiplier = random.choice([2, 3])
        return {
            "title": template["title"],
            "title_en": template["title_en"],
            "message_sw": template["message_sw"].format(multiplier=multiplier),
            "message_en": template["message_en"].format(multiplier=multiplier),
            "icon": template["icon"],
            "bonus_xp": 25 * multiplier,
        }

    elif reward_type == "wisdom_quote":
        quote = random.choice(WISDOM_QUOTES)
        return {
            "title": template["title"],
            "title_en": template["title_en"],
            "message_sw": template["message_sw"].format(
                quote_sw=quote["quote_sw"],
                author=quote["author"],
            ),
            "message_en": template["message_en"].format(
                quote_en=quote["quote_en"],
                author=quote["author"],
            ),
            "icon": template["icon"],
            "bonus_xp": 5,
        }

    else:
        return {
            "title": template.get("title", "Zawadi!"),
            "title_en": template.get("title_en", "Reward!"),
            "message_sw": "Umepata zawadi ya siri!",
            "message_en": "You got a mystery reward!",
            "icon": template.get("icon", "🎁"),
            "bonus_xp": 10,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Aha Moment Tracking
# ═══════════════════════════════════════════════════════════════════════════════


async def track_aha_moment(
    db: AsyncSession,
    user_id: UUID,
    action: str,
) -> dict[str, Any]:
    """
    Track when a user hits an aha moment.

    Aha moments are critical activation events that must happen within
    60 seconds for first sale, 2 minutes for first insight, etc.

    Returns whether this is a new aha moment and any rewards.
    """
    if action not in AHA_MOMENTS:
        return {
            "success": False,
            "error": f"Unknown aha moment: {action}",
            "valid_actions": list(AHA_MOMENTS.keys()),
        }

    moment = AHA_MOMENTS[action]
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Check if already recorded
    result = await db.execute(
        select(UserEngagement).where(
            and_(
                UserEngagement.user_id == user_id,
                UserEngagement.date == today,
            )
        )
    )
    engagement = result.scalar_one_or_none()

    if engagement and engagement.aha_moments_hit and action in engagement.aha_moments_hit:
        return {
            "success": True,
            "is_new": False,
            "action": action,
            "message_sw": f"'{moment['name_sw']}' tayari imeandikwa leo.",
            "message_en": f"'{moment['name']}' already recorded today.",
        }

    # Record the aha moment
    if not engagement:
        engagement = UserEngagement(
            user_id=user_id,
            date=today,
            daily_active=True,
            actions_count=1,
            xp_earned=moment["xp_reward"],
            aha_moments_hit=[action],
        )
        db.add(engagement)
    else:
        moments = engagement.aha_moments_hit or []
        moments.append(action)
        engagement.aha_moments_hit = moments
        engagement.xp_earned += moment["xp_reward"]
        engagement.daily_active = True

    # Award XP
    level_result = await db.execute(
        select(UserLevel).where(UserLevel.user_id == user_id)
    )
    user_level = level_result.scalar_one_or_none()
    if user_level:
        user_level.xp += moment["xp_reward"]

    # Update streak
    await record_activity(db, user_id, xp_earned=0, actions_increment=0)

    await db.flush()

    logger.info(
        "aha_moment_tracked",
        user_id=str(user_id),
        action=action,
        importance=moment["importance"],
        xp_awarded=moment["xp_reward"],
    )

    return {
        "success": True,
        "is_new": True,
        "action": action,
        "name": moment["name"],
        "name_sw": moment["name_sw"],
        "importance": moment["importance"],
        "xp_reward": moment["xp_reward"],
        "message_sw": f"Hongera! Umefikia '{moment['name_sw']}'! +{moment['xp_reward']} XP",
        "message_en": f"Congratulations! You reached '{moment['name']}'! +{moment['xp_reward']} XP",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Social Proof
# ═══════════════════════════════════════════════════════════════════════════════


async def get_social_proof(
    db: AsyncSession,
    user_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """
    Get anonymized social proof data.

    Anti-shame design: All comparisons are anonymized and positive.
    No negative comparisons, no exact rankings, no "you're behind" messages.
    """
    # Get aggregate stats (anonymized)
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    # Active users this week
    active_result = await db.execute(
        select(func.count(func.distinct(UserEngagement.user_id)))
        .where(
            and_(
                UserEngagement.date >= week_ago,
                UserEngagement.daily_active == True,
            )
        )
    )
    active_users_week = active_result.scalar() or 0

    # Total users
    total_result = await db.execute(
        select(func.count(func.distinct(UserEngagement.user_id)))
    )
    total_users = total_result.scalar() or 0

    # Average streak among active users
    avg_streak_result = await db.execute(
        select(func.avg(Streak.current_streak))
        .where(Streak.current_streak > 0)
    )
    avg_streak = round(avg_streak_result.scalar() or 0, 1)

    # Users with 7+ streak
    streak_7_result = await db.execute(
        select(func.count(Streak.id))
        .where(Streak.current_streak >= 7)
    )
    streak_7_count = streak_7_result.scalar() or 0

    # Build social proof messages
    proofs = []

    # Select 2-3 random proof templates
    selected_templates = random.sample(
        SOCIAL_PROOF_TEMPLATES,
        min(3, len(SOCIAL_PROOF_TEMPLATES)),
    )

    for template in selected_templates:
        if template["type"] == "peer_activity":
            percent = round(active_users_week / max(total_users, 1) * 100)
            categories = ["mama mboga", "dukawallah", "boda boda"]
            category = random.choice(categories)
            proofs.append({
                "type": template["type"],
                "icon": template["icon"],
                "message_sw": template["message_sw"].format(
                    percent=percent, category=category
                ),
                "message_en": template["message_en"].format(
                    percent=percent, category=category
                ),
            })
        elif template["type"] == "peer_streak":
            proofs.append({
                "type": template["type"],
                "icon": template["icon"],
                "message_sw": template["message_sw"].format(count=streak_7_count),
                "message_en": template["message_en"].format(count=streak_7_count),
            })
        elif template["type"] == "community_milestone":
            # Round to nearest nice number
            milestone = _round_to_milestone(total_users)
            proofs.append({
                "type": template["type"],
                "icon": template["icon"],
                "message_sw": template["message_sw"].format(count=milestone),
                "message_en": template["message_en"].format(count=milestone),
            })
        elif template["type"] == "peer_savings":
            count = max(1, active_users_week // 4)
            amount = random.choice([200, 350, 500, 750])
            proofs.append({
                "type": template["type"],
                "icon": template["icon"],
                "message_sw": template["message_sw"].format(count=count, amount=amount),
                "message_en": template["message_en"].format(count=count, amount=amount),
            })
        elif template["type"] == "peer_growth":
            percent = random.randint(10, 35)
            proofs.append({
                "type": template["type"],
                "icon": template["icon"],
                "message_sw": template["message_sw"].format(percent=percent),
                "message_en": template["message_en"].format(percent=percent),
            })

    return {
        "user_id": str(user_id) if user_id else None,
        "community_size": _round_to_milestone(total_users),
        "active_this_week": active_users_week,
        "average_streak": avg_streak,
        "proofs": proofs,
    }


def _round_to_milestone(n: int) -> int:
    """Round to nearest nice-looking milestone number."""
    if n < 100:
        return (n // 10) * 10 or 10
    elif n < 1000:
        return (n // 50) * 50
    elif n < 10000:
        return (n // 100) * 100
    else:
        return (n // 1000) * 1000


# ═══════════════════════════════════════════════════════════════════════════════
# Badge Eligibility (Internal)
# ═══════════════════════════════════════════════════════════════════════════════


async def _check_badge_eligibility(
    db: AsyncSession,
    user_id: UUID,
    engagement: UserEngagement,
) -> list[dict[str, Any]]:
    """
    Check if user qualifies for any new badges.

    Called after every activity update. Returns list of newly earned badges.
    """
    # Get already-earned badge IDs
    earned_result = await db.execute(
        select(UserBadge.badge_id).where(UserBadge.user_id == user_id)
    )
    earned_ids = set(earned_result.scalars().all())

    # Get badge table
    badge_result = await db.execute(select(Badge).where(Badge.is_active))
    db_badges = badge_result.scalars().all()
    badge_map = {b.name: b for b in db_badges}

    # Get user stats
    streak_result = await db.execute(
        select(Streak).where(Streak.user_id == user_id)
    )
    streak = streak_result.scalar_one_or_none()

    level_result = await db.execute(
        select(UserLevel).where(UserLevel.user_id == user_id)
    )
    user_level = level_result.scalar_one_or_none()

    # Count total engagement records
    count_result = await db.execute(
        select(func.count(UserEngagement.id))
        .where(
            and_(
                UserEngagement.user_id == user_id,
                UserEngagement.daily_active == True,
            )
        )
    )
    active_days = count_result.scalar() or 0

    newly_earned = []

    for badge_data in BADGES:
        db_badge = badge_map.get(badge_data["name"])
        if not db_badge or db_badge.id in earned_ids:
            continue

        criteria = badge_data["criteria"]
        earned = False

        if criteria["type"] == "first_action":
            earned = engagement.actions_count > 0

        elif criteria["type"] == "daily_active":
            earned = active_days >= criteria.get("days", 1)

        elif criteria["type"] == "profile_complete":
            # Check if engagement exists (proxy for profile activity)
            earned = active_days >= 1

        elif criteria["type"] == "streak":
            earned = streak and streak.current_streak >= criteria["days"]

        elif criteria["type"] == "transaction_count":
            # Total actions as proxy for transactions
            total_actions_result = await db.execute(
                select(func.sum(UserEngagement.actions_count))
                .where(UserEngagement.user_id == user_id)
            )
            total = total_actions_result.scalar() or 0
            earned = total >= criteria["count"]

        elif criteria["type"] == "first_savings":
            earned = active_days >= 1  # Proxy

        elif criteria["type"] == "first_goal":
            earned = active_days >= 1  # Proxy

        elif criteria["type"] == "account_age_days":
            # Check first engagement
            first_result = await db.execute(
                select(func.min(UserEngagement.date))
                .where(UserEngagement.user_id == user_id)
            )
            first_date = first_result.scalar()
            if first_date:
                days_active = (datetime.now(timezone.utc) - first_date).days
                earned = days_active >= criteria["days"]

        if earned:
            # Award badge
            user_badge = UserBadge(
                user_id=user_id,
                badge_id=db_badge.id,
            )
            db.add(user_badge)

            # Award XP
            if user_level:
                user_level.xp += badge_data["xp_reward"]

            newly_earned.append({
                "name": badge_data["name"],
                "swahili_name": badge_data["swahili_name"],
                "icon": badge_data["icon"],
                "xp_reward": badge_data["xp_reward"],
            })

            logger.info(
                "badge_earned",
                user_id=str(user_id),
                badge=badge_data["name"],
                xp_awarded=badge_data["xp_reward"],
            )

    return newly_earned


# ═══════════════════════════════════════════════════════════════════════════════
# Badge Seeding (startup)
# ═══════════════════════════════════════════════════════════════════════════════


async def seed_badges(db: AsyncSession) -> int:
    """
    Seed badge definitions from gamification data.

    Called on startup. Returns number of badges created/updated.
    """
    count = 0
    for badge_data in BADGES:
        result = await db.execute(
            select(Badge).where(Badge.name == badge_data["name"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update if changed
            existing.swahili_name = badge_data["swahili_name"]
            existing.description = badge_data["description"]
            existing.description_sw = badge_data.get("description_sw", "")
            existing.icon = badge_data["icon"]
            existing.category = badge_data["category"]
            existing.criteria = badge_data["criteria"]
            existing.xp_reward = badge_data["xp_reward"]
        else:
            badge = Badge(
                name=badge_data["name"],
                swahili_name=badge_data["swahili_name"],
                description=badge_data["description"],
                description_sw=badge_data.get("description_sw", ""),
                icon=badge_data["icon"],
                category=badge_data["category"],
                criteria=badge_data["criteria"],
                xp_reward=badge_data["xp_reward"],
            )
            db.add(badge)
        count += 1

    await db.commit()
    logger.info("badges_seeded", count=count)
    return count
