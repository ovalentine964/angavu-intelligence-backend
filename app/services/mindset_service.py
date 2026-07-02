"""
Wealth Mindset Service — 56 voice lessons, progress tracking, rich habits score.

Core capabilities:
- Serve 56 voice lessons across 6 modules
- Track lesson delivery and completion
- Rich habits score calculation (0-100 daily)
- Daily/weekly mindset briefings
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_features import (
    MindsetLesson,
    MindsetLessonProgress,
    RichHabitScore,
)

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Module & Lesson Definitions (56 lessons across 6 modules)
# ─────────────────────────────────────────────────────────────────────────────

MODULE_DEFINITIONS = [
    {
        "module_number": 1,
        "title_en": "Believe You Can",
        "title_sw": "Iniamini Unaweza",
        "source_book": "The Magic of Thinking Big — David Schwartz",
        "lessons": [
            (1, "The Power of Belief", "Nguvu ya Kuamini", 2, "Success starts in your mind"),
            (2, "Open the 'I Can't' Door", "Fungua Milango ya 'Siwezi'", 2, "Most limits are self-imposed"),
            (3, "Think Big", "Fikiri Kubwa", 3, "Size of thinking = size of results"),
            (4, "Words Have Power", "Neno Lina Nguvu", 2, "Your language shapes your reality"),
            (5, "Leader or Follower?", "Kiongozi ama Mfuasi?", 2, "Leaders create, followers wait"),
            (6, "Fear of Failure", "Woga wa Kushindwa", 3, "Failure is education, not death"),
            (7, "Story of the Dreaming Mama Mboga", "Hadithi ya Mama Mboga Mwenye Ndoto", 3, "Real story of transformation"),
            (8, "The Day to Believe", "Siku ya Kuamini", 2, "Today is the day you start"),
            (9, "Daily Practice", "Mazoezi ya Kila Siku", 2, "Morning affirmation routine"),
        ],
    },
    {
        "module_number": 2,
        "title_en": "Think and Grow Rich",
        "title_sw": "Fikiri na Ukuwe Tajiri",
        "source_book": "Think and Grow Rich — Napoleon Hill",
        "lessons": [
            (1, "Desire", "Tamaa ya Kupata", 3, "You must want success with burning desire"),
            (2, "Faith", "Imani Inayobadilisha", 2, "Visualization of attainment"),
            (3, "Auto-suggestion", "Zungumza na Nafsi Yako", 2, "Program your subconscious"),
            (4, "Specialized Knowledge", "Elimu Maalum", 3, "Specific knowledge earns money"),
            (5, "Imagination", "Uundaji wa Mawazo", 2, "Synthetic and creative imagination"),
            (6, "Organized Planning", "Mpango wa Kupanga", 3, "Desire without plan is a dream"),
            (7, "Decision", "Maamuzi ya Haraka", 2, "Decide quickly, change slowly"),
            (8, "Persistence", "Uvumilivu", 3, "Most quit right before breakthrough"),
            (9, "Master Mind", "Nguvu ya Kikundi", 2, "Surround yourself with winners"),
            (10, "Energy Direction", "Nishati ya Malengo", 2, "Channel energy into goals"),
            (11, "Subconscious Mind", "Akili ya Ndani", 2, "Feed your mind goals, not worries"),
            (12, "The Brain", "Akili Yako ni Kituo", 2, "Stay tuned to positive frequencies"),
            (13, "The Sixth Sense", "Hekima ya Muda Mrefu", 2, "Experience creates intuition"),
        ],
    },
    {
        "module_number": 3,
        "title_en": "The Richest Man in Babylon",
        "title_sw": "Mwenye Utajiri Zaidi wa Babylon",
        "source_book": "The Richest Man in Babylon — George Clason",
        "lessons": [
            (1, "The Story of Arkad", "Hadithi ya Arkad", 3, "Part of all you earn is yours to keep"),
            (2, "Save 10% First", "Weka Akiba Kwanza", 3, "Pay yourself first"),
            (3, "Control Expenditures", "Dhibiti Matumizi Yako", 2, "Needs vs desires"),
            (4, "Make Gold Multiply", "Fanya Pesa Ikuzalishe", 3, "Idle money wastes away"),
            (5, "Guard From Loss", "Linda Mali Zako", 2, "Protect principal first"),
            (6, "Profitable Dwelling", "Nyumba Yako ni Biashara", 2, "Make your space profitable"),
            (7, "Insure Future Income", "Bima ya Kesho", 3, "Plan for old age and emergencies"),
            (8, "Increase Ability to Earn", "Ongeza Uwezo Wako", 3, "Invest in yourself"),
            (9, "The Chariot Maker", "Hadithi ya Mtu wa Magari", 2, "Working hard isn't enough"),
        ],
    },
    {
        "module_number": 4,
        "title_en": "Atomic Habits",
        "title_sw": "Tabia Ndogo, Matokeo Makubwa",
        "source_book": "Atomic Habits — James Clear",
        "lessons": [
            (1, "1% Daily Improvement", "1% Kila Siku", 2, "Small changes compound dramatically"),
            (2, "Identity-Based Habits", "Mimi Ni Mtu Gani?", 3, "Focus on who you want to become"),
            (3, "Make It Obvious", "Fanya Ionekane", 2, "Make desired behavior visible"),
            (4, "Make It Attractive", "Fanya Ivutie", 2, "Pair habits with enjoyment"),
            (5, "Make It Easy", "Fanya Rahisi", 2, "Reduce friction for good habits"),
            (6, "Make It Satisfying", "Fanya Irithishe", 2, "Immediate rewards reinforce habits"),
            (7, "Habit Stacking", "Mnyororo wa Tabia", 3, "After X, I will do Y"),
            (8, "Breaking Bad Habits", "Kuvunja Tabia Mbaya", 3, "Invert the 4 laws"),
            (9, "Money Garden Game", "Bustani ya Pesa Yako", 2, "Visualize your financial growth"),
        ],
    },
    {
        "module_number": 5,
        "title_en": "Psychology of Money",
        "title_sw": "Saikolojia ya Pesa",
        "source_book": "The Psychology of Money — Morgan Housel",
        "lessons": [
            (1, "Compounding", "Nguvu ya Kuzaliana", 3, "Time in market beats timing market"),
            (2, "Room for Error", "Nafasi ya Makosa", 2, "Survive bad times to enjoy good"),
            (3, "Wealth Is What You Don't Spend", "Utajiri ni Kile Usichotumia", 3, "True wealth is invisible"),
            (4, "Reasonable > Rational", "Wastani Bora Zaidi ya Kamili", 2, "Good enough consistently wins"),
            (5, "Seduction of Pessimism", "Uvivu wa Pesimism", 2, "Pessimism sounds smart but optimism wins"),
            (6, "Nothing Is Free", "Hakuna Kitu Bure", 2, "Every decision has hidden cost"),
            (7, "Freedom Is True Wealth", "Uhuru ni Utajiri Halisi", 3, "Wealth = freedom of time"),
            (8, "Save Without a Reason", "Hifadhi Bila Sababu", 2, "Save for options, not just goals"),
        ],
    },
    {
        "module_number": 6,
        "title_en": "Giving and Abundance",
        "title_sw": "Kutoa na Wingi",
        "source_book": "Original content — spiritual/philosophical foundation",
        "lessons": [
            (1, "The Secret of Giving", "Siri ya Kutoa", 3, "Giving opens the hand to receive"),
            (2, "Tithe and Taxes", "Zaka na Ushuru", 2, "Systematic proportional giving"),
            (3, "Giving Creates Space", "Kutoa kunatengeneza Nafasi", 2, "Abundance follows generosity"),
            (4, "True Generosity", "Ukarimu wa Kweli", 2, "Give from the heart, not obligation"),
            (5, "The Abundance Cycle", "Mzunguko wa Wingi", 3, "Income and giving grow together"),
            (6, "Wise Giving", "Kutoa kwa Busara", 2, "Strategic, not reckless, generosity"),
            (7, "Story of the Giver", "Hadithi ya Mtoaji", 3, "Real transformation through giving"),
            (8, "End of Journey — New Beginning", "Mwisho wa Safari — Mwanzo Mpya", 3, "This is just the beginning"),
        ],
    },
]

# Rich habits and their point values
RICH_HABITS = {
    "record_sales": {"points": 10, "en": "Record Sales", "sw": "Rekodi Mauzo"},
    "check_balance": {"points": 5, "en": "Check Balance", "sw": "Angalia Salio"},
    "save_money": {"points": 15, "en": "Save Money", "sw": "Hifadhi Pesa"},
    "avoid_waste": {"points": 10, "en": "Avoid Unnecessary Spending", "sw": "Epuka Matumizi"},
    "give": {"points": 10, "en": "Give/Help Someone", "sw": "Toa/Msaidia Mtu"},
    "learn": {"points": 10, "en": "Learn Something New", "sw": "Jifunze Jambo Jipya"},
    "set_goal": {"points": 5, "en": "Set Today's Goal", "sw": "Weka Lengo la Leo"},
    "review_day": {"points": 5, "en": "Review Today's Progress", "sw": "Fuatilia Maendeleo ya Leo"},
    "help_peer": {"points": 10, "en": "Help Another Worker", "sw": "Msaidie Mfanyakzi Mwingine"},
    "no_debt": {"points": 20, "en": "Stay Debt-Free Today", "sw": "Kaa Bila Deni Leo"},
}

SCORE_RATINGS = [
    (90, "⭐ Superstar", "Umeongeza mbegu 10 za utajiri leo!", "Gold"),
    (75, "🌟 Great", "Siku nzuri! Uko kwenye njia sahihi.", "Green"),
    (60, "👍 Good", "Vizuri! Jaribu kuongeza kidogo kesho.", "Blue"),
    (40, "🤔 Fair", "Umefanya vizuri, lakini unaweza zaidi.", "Yellow"),
    (20, "⚠️ Needs Work", "Leo ilikuwa ngumu. Kesho ni nafasi mpya.", "Orange"),
    (0, "🔴 Wake Up", "Rafiki yangu, biashara yako inahitaji uangalifu.", "Red"),
]

LEVEL_THRESHOLDS = [
    (365, 5, "Money Forest"),
    (180, 4, "Fruit Tree"),
    (90, 3, "Tree"),
    (30, 2, "Sapling"),
    (0, 1, "Seedling"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Lesson Management
# ─────────────────────────────────────────────────────────────────────────────


async def seed_lessons(db: AsyncSession) -> int:
    """Seed all 56 lessons into the database. Returns count of new lessons created."""

    # Check if already seeded
    count_result = await db.execute(select(func.count(MindsetLesson.id)))
    existing = count_result.scalar() or 0
    if existing >= 56:
        return 0

    created = 0
    order_index = 1
    for module in MODULE_DEFINITIONS:
        for lesson_num, title_en, title_sw, duration, takeaway in module["lessons"]:
            # Check if exists
            exists = await db.execute(
                select(MindsetLesson).where(
                    and_(
                        MindsetLesson.module_number == module["module_number"],
                        MindsetLesson.lesson_number == lesson_num,
                    )
                )
            )
            if exists.scalar_one_or_none():
                order_index += 1
                continue

            lesson = MindsetLesson(
                module_number=module["module_number"],
                lesson_number=lesson_num,
                title_en=title_en,
                title_sw=title_sw,
                source_book=module["source_book"],
                key_takeaway=takeaway,
                duration_minutes=duration,
                order_index=order_index,
                is_active=True,
            )
            db.add(lesson)
            created += 1
            order_index += 1

    await db.flush()
    return created


async def get_today_lesson(
    db: AsyncSession,
    user_id: UUID,
) -> Dict[str, Any]:
    """
    Get today's lesson for a user based on their progress.

    Returns the next uncompleted lesson in sequence.
    """

    # Get user's completed lessons
    completed_result = await db.execute(
        select(MindsetLessonProgress.lesson_id).where(
            and_(
                MindsetLessonProgress.user_id == user_id,
                MindsetLessonProgress.completed == True,
            )
        )
    )
    completed_ids = set(row[0] for row in completed_result.all())

    # Get next uncompleted lesson
    all_lessons_result = await db.execute(
        select(MindsetLesson)
        .where(MindsetLesson.is_active == True)
        .order_by(MindsetLesson.order_index)
    )
    all_lessons = all_lessons_result.scalars().all()

    next_lesson = None
    for lesson in all_lessons:
        if lesson.id not in completed_ids:
            next_lesson = lesson
            break

    if not next_lesson:
        return {
            "status": "all_completed",
            "message_sw": "Hongera! Umekamilisha masomo yote 56! Wewe ni mtaalamu wa utajiri.",
            "message_en": "Congratulations! You've completed all 56 lessons! You're a wealth expert.",
            "total_completed": len(completed_ids),
            "total_lessons": len(all_lessons),
        }

    # Get module info
    module_info = None
    for m in MODULE_DEFINITIONS:
        if m["module_number"] == next_lesson.module_number:
            module_info = m
            break

    # Module progress
    module_lessons = [l for l in all_lessons if l.module_number == next_lesson.module_number]
    module_completed = sum(1 for l in module_lessons if l.id in completed_ids)

    return {
        "status": "available",
        "lesson": {
            "id": str(next_lesson.id),
            "module_number": next_lesson.module_number,
            "lesson_number": next_lesson.lesson_number,
            "title_en": next_lesson.title_en,
            "title_sw": next_lesson.title_sw,
            "source_book": next_lesson.source_book,
            "key_takeaway": next_lesson.key_takeaway,
            "duration_minutes": next_lesson.duration_minutes,
            "audio_url": next_lesson.audio_url,
            "content_text": next_lesson.content_text,
            "order_index": next_lesson.order_index,
        },
        "module": {
            "number": next_lesson.module_number,
            "title_en": module_info["title_en"] if module_info else None,
            "title_sw": module_info["title_sw"] if module_info else None,
            "progress": f"{module_completed}/{len(module_lessons)}",
        },
        "overall_progress": {
            "completed": len(completed_ids),
            "total": len(all_lessons),
            "pct": round(len(completed_ids) / max(len(all_lessons), 1) * 100, 1),
        },
        "greeting_sw": "Karibu, rafiki yangu. Leo tutaanza somo jipya...",
        "greeting_en": "Welcome, my friend. Today we start a new lesson...",
    }


async def mark_lesson_complete(
    db: AsyncSession,
    user_id: UUID,
    lesson_id: UUID,
) -> Dict[str, Any]:
    """Mark a lesson as completed for a user."""

    # Upsert progress
    result = await db.execute(
        select(MindsetLessonProgress).where(
            and_(
                MindsetLessonProgress.user_id == user_id,
                MindsetLessonProgress.lesson_id == lesson_id,
            )
        )
    )
    progress = result.scalar_one_or_none()

    if progress:
        progress.completed = True
        progress.completed_at = datetime.now(timezone.utc)
        progress.listen_count += 1
    else:
        progress = MindsetLessonProgress(
            user_id=user_id,
            lesson_id=lesson_id,
            completed=True,
            completed_at=datetime.now(timezone.utc),
            last_listened_at=datetime.now(timezone.utc),
            listen_count=1,
        )
        db.add(progress)

    await db.flush()

    # Get overall progress
    total_completed_result = await db.execute(
        select(func.count(MindsetLessonProgress.id)).where(
            and_(
                MindsetLessonProgress.user_id == user_id,
                MindsetLessonProgress.completed == True,
            )
        )
    )
    total_completed = total_completed_result.scalar() or 0

    total_lessons_result = await db.execute(
        select(func.count(MindsetLesson.id)).where(MindsetLesson.is_active == True)
    )
    total_lessons = total_lessons_result.scalar() or 56

    # Check module completion
    lesson_result = await db.execute(
        select(MindsetLesson).where(MindsetLesson.id == lesson_id)
    )
    lesson = lesson_result.scalar_one_or_none()

    module_complete = False
    if lesson:
        module_lessons_result = await db.execute(
            select(MindsetLesson.id).where(
                MindsetLesson.module_number == lesson.module_number
            )
        )
        module_lesson_ids = [row[0] for row in module_lessons_result.all()]

        module_progress_result = await db.execute(
            select(func.count(MindsetLessonProgress.id)).where(
                and_(
                    MindsetLessonProgress.user_id == user_id,
                    MindsetLessonProgress.lesson_id.in_(module_lesson_ids),
                    MindsetLessonProgress.completed == True,
                )
            )
        )
        module_completed_count = module_progress_result.scalar() or 0
        module_complete = module_completed_count >= len(module_lesson_ids)

    return {
        "lesson_id": str(lesson_id),
        "completed": True,
        "total_completed": total_completed,
        "total_lessons": total_lessons,
        "pct": round(total_completed / max(total_lessons, 1) * 100, 1),
        "module_complete": module_complete,
        "message_sw": (
            "Somo limekamilika! Hongera!"
            if not module_complete
            else "Moduli imekamilika! Umefungua moduli mpya! Hongera sana!"
        ),
        "message_en": (
            "Lesson complete! Well done!"
            if not module_complete
            else "Module complete! You've unlocked a new module! Congratulations!"
        ),
    }


async def get_rich_habits_score(
    db: AsyncSession,
    user_id: UUID,
    score_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Get or calculate rich habits score for a given date."""

    if score_date is None:
        score_date = date.today()

    result = await db.execute(
        select(RichHabitScore).where(
            and_(
                RichHabitScore.user_id == user_id,
                RichHabitScore.score_date == score_date,
            )
        )
    )
    score_record = result.scalar_one_or_none()

    if not score_record:
        # Create empty score for today
        score_record = RichHabitScore(
            user_id=user_id,
            score_date=score_date,
            total_score=0,
        )
        db.add(score_record)
        await db.flush()

    # Build habit breakdown
    habits = {}
    total = 0
    for habit_key, habit_info in RICH_HABITS.items():
        completed = getattr(score_record, habit_key, False)
        habits[habit_key] = {
            "name_en": habit_info["en"],
            "name_sw": habit_info["sw"],
            "points": habit_info["points"],
            "completed": completed,
        }
        if completed:
            total += habit_info["points"]

    # Rating
    rating_label, rating_msg_sw, rating_color = "🔴 Wake Up", "Rafiki yangu...", "Red"
    for threshold, label, msg, color in SCORE_RATINGS:
        if total >= threshold:
            rating_label, rating_msg_sw, rating_color = label, msg, color
            break

    # Streak (consecutive days with score >= 60)
    streak = await _calculate_streak(db, user_id, score_date)

    # Level
    level = 1
    level_name = "Seedling"
    for days_threshold, lvl, name in LEVEL_THRESHOLDS:
        if streak >= days_threshold:
            level = lvl
            level_name = name
            break

    return {
        "date": str(score_date),
        "total_score": total,
        "rating": rating_label,
        "rating_color": rating_color,
        "message_sw": rating_msg_sw,
        "streak": streak,
        "level": level,
        "level_name": level_name,
        "habits": habits,
    }


async def update_habit(
    db: AsyncSession,
    user_id: UUID,
    habit_key: str,
    completed: bool = True,
    score_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Update a single habit for today and recalculate score."""

    if habit_key not in RICH_HABITS:
        return {"error": f"Unknown habit: {habit_key}"}

    if score_date is None:
        score_date = date.today()

    # Get or create today's score
    result = await db.execute(
        select(RichHabitScore).where(
            and_(
                RichHabitScore.user_id == user_id,
                RichHabitScore.score_date == score_date,
            )
        )
    )
    score_record = result.scalar_one_or_none()

    if not score_record:
        score_record = RichHabitScore(
            user_id=user_id,
            score_date=score_date,
        )
        db.add(score_record)

    # Update the habit
    setattr(score_record, habit_key, completed)

    # Recalculate total
    total = 0
    for key, info in RICH_HABITS.items():
        if getattr(score_record, key, False):
            total += info["points"]
    score_record.total_score = total

    # Update streak
    streak = await _calculate_streak(db, user_id, score_date)
    score_record.current_streak = streak
    if streak > score_record.best_streak:
        score_record.best_streak = streak

    # Update level
    for days_threshold, lvl, name in LEVEL_THRESHOLDS:
        if streak >= days_threshold:
            score_record.level = lvl
            break

    await db.flush()

    return {
        "habit": habit_key,
        "completed": completed,
        "total_score": total,
        "streak": streak,
        "level": score_record.level,
    }


async def get_mindset_briefing(
    db: AsyncSession,
    user_id: UUID,
    briefing_type: str = "daily",
) -> Dict[str, Any]:
    """Generate a daily or weekly mindset briefing."""

    today = date.today()

    # Today's score
    score = await get_rich_habits_score(db, user_id, today)

    # Today's lesson
    lesson = await get_today_lesson(db, user_id)

    if briefing_type == "weekly":
        # Weekly average
        week_start = today - timedelta(days=7)
        week_scores_result = await db.execute(
            select(RichHabitScore).where(
                and_(
                    RichHabitScore.user_id == user_id,
                    RichHabitScore.score_date >= week_start,
                    RichHabitScore.score_date <= today,
                )
            )
        )
        week_scores = week_scores_result.scalars().all()
        avg_score = (
            sum(s.total_score for s in week_scores) / max(len(week_scores), 1)
            if week_scores
            else 0
        )

        # Best day
        best_day = max(week_scores, key=lambda s: s.total_score) if week_scores else None

        return {
            "type": "weekly",
            "period": f"{week_start} to {today}",
            "avg_score": round(avg_score, 1),
            "days_tracked": len(week_scores),
            "best_day": {
                "date": str(best_day.score_date),
                "score": best_day.total_score,
            } if best_day else None,
            "current_streak": score.get("streak", 0),
            "level": score.get("level", 1),
            "level_name": score.get("level_name", "Seedling"),
            "today_lesson": lesson,
            "message_sw": f"Ripoti ya wiki: Score yako ya wastani ni {avg_score:.0f}. Endelea kujenga!",
            "message_en": f"Weekly report: Your average score is {avg_score:.0f}. Keep building!",
        }

    # Daily briefing
    return {
        "type": "daily",
        "date": str(today),
        "score": score,
        "today_lesson": lesson,
        "greeting_sw": "Habari! Leo ni siku mpya ya kujenga utajiri. Anza na Goal yako ya leo.",
        "greeting_en": "Hello! Today is a new day to build wealth. Start with today's goal.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _calculate_streak(
    db: AsyncSession,
    user_id: UUID,
    as_of_date: date,
) -> int:
    """Calculate consecutive days with score >= 60 ending at as_of_date."""

    # Get last 365 days of scores
    start = as_of_date - timedelta(days=365)
    result = await db.execute(
        select(RichHabitScore.score_date, RichHabitScore.total_score)
        .where(
            and_(
                RichHabitScore.user_id == user_id,
                RichHabitScore.score_date >= start,
                RichHabitScore.score_date <= as_of_date,
                RichHabitScore.total_score >= 60,
            )
        )
        .order_by(RichHabitScore.score_date.desc())
    )
    qualifying_dates = [row[0] for row in result.all()]

    if not qualifying_dates:
        return 0

    # Count consecutive days from as_of_date backward
    streak = 0
    expected = as_of_date
    for d in qualifying_dates:
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d == expected - timedelta(days=1):
            # Allow 1-day grace
            streak += 1
            expected = d - timedelta(days=1)
        else:
            break

    return streak
