"""
Wealth Mindset Service — 56 voice lessons, progress tracking, rich habits score.

Core capabilities:
- Serve 56 voice lessons across 6 modules (Swahili & English)
- Track lesson delivery and completion with scoring
- Rich habits score calculation (0-100 daily)
- Daily affirmations in Swahili and English
- Habit stacking formulas per worker type
- Mastermind group recommendations
- Daily/weekly mindset briefings

Research basis:
- 12 books analyzed, 56 voice lessons across 6 modules (~134 min total)
- Key books: Magic of Thinking Big, Think and Grow Rich, Richest Man in Babylon,
  Atomic Habits, Psychology of Money
- KSh 50/day → KSh 1.1M in 20 years (compound interest)
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.mindset_lessons import (
    AFFIRMATIONS,
    COMPOUND_INTEREST_STORY,
    HABIT_STACKS,
    MODULE_DEFINITIONS,
    get_affirmation_by_index,
    get_affirmations_by_category,
    get_all_affirmations,
    get_all_lessons,
    get_all_worker_types,
    get_habit_stack,
)
from app.models.mindset import (
    Affirmation,
    MindsetLesson,
    RichHabitsScore,
    UserLessonProgress,
)

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Rich Habits Definitions
# ─────────────────────────────────────────────────────────────────────────────

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

# Mastermind group recommendations by worker type
MASTERMIND_GROUPS = {
    "mama_mboga": {
        "name_en": "Mama Mboga Wealth Circle",
        "name_sw": "Duara la Utajiri la Mama Mboga",
        "description_en": "A group of 5-7 vegetable vendors who meet weekly to share savings progress, business tips, and hold each other accountable.",
        "description_sw": "Kikundi cha wachuuzi 5-7 wa mboga ambao wanakutana kila wiki kushiriki maendeleo ya akiba, vidokezo vya biashara, na kushikamana.",
        "meeting_frequency": "weekly",
        "focus_areas": ["savings_consistency", "inventory_management", "price_negotiation", "bulk_buying"],
        "suggested_members": "Other mama mbogas in your market or neighborhood",
        "benefits_en": [
            "Accountability: Someone checks if you saved this week",
            "Knowledge sharing: Learn what products sell best",
            "Bulk buying power: Buy stock together for better prices",
            "Emotional support: You're not alone in the struggle",
        ],
        "benefits_sw": [
            "Uwajibikaji: Mtu anayekagua kama umehifadhi wiki hii",
            "Kushiriki maarifa: Jifunze bidhaa gani zinauzwa vizuri",
            "Nguvu ya kununua pamoja: Nunua hisa pamoja kwa bei nzuri",
            "Msaada wa kihisia: Wewe si peke yako katika changamoto",
        ],
        "compound_interest": COMPOUND_INTEREST_STORY,
    },
    "boda_boda": {
        "name_en": "Boda Boda Riders' Investment Club",
        "name_sw": "Klabu ya Uwekezaji ya Waendesha Boda Boda",
        "description_en": "5-7 riders pooling savings weekly. Target: each rider owns their motorcycle within 18 months.",
        "description_sw": "Waendesha boda boda 5-7 wanachangisha akiba kila wiki. Lengo: kila mpanda anamiliki pikipiki yake ndani ya miezi 18.",
        "meeting_frequency": "weekly",
        "focus_areas": ["vehicle_ownership", "emergency_fund", "insurance", "savings_discipline"],
        "suggested_members": "Trusted riders from your stage or route",
        "benefits_en": [
            "Group savings: Buy motorcycles through SACCO loans",
            "Emergency fund: Pool money for breakdowns and accidents",
            "Insurance awareness: NHIF and motor insurance knowledge",
            "Debt avoidance: No shylocks, no daily repayment traps",
        ],
        "benefits_sw": [
            "Akiba ya kikundi: Nunua pikipiki kupitia mikopo ya SACCO",
            "Fedha ya dharura: Changisha pesa kwa ajili ya kuvunjika na ajali",
            "Ufahamu wa bima: Maarifa ya NHIF na bima ya pikipiki",
            "Kuepuka madeni: Hakuna wakopeshaji, hakina mitego ya kulipa kila siku",
        ],
        "compound_interest": COMPOUND_INTEREST_STORY,
    },
    "duka_owner": {
        "name_en": "Dukawallah Growth Alliance",
        "name_sw": "Muungano wa Ukuaji wa Wamiliki wa Maduka",
        "description_en": "Shop owners sharing supplier contacts, best practices, and financial discipline strategies.",
        "description_sw": "Wamiliki wa maduka wanashiriki mawasiliano ya wauzaji, mazoezi bora, na mikakati ya nidhamu ya kifedha.",
        "meeting_frequency": "biweekly",
        "focus_areas": ["supplier_network", "profit_maximization", "record_keeping", "expansion_planning"],
        "suggested_members": "Non-competing duka owners in your area",
        "benefits_en": [
            "Supplier sharing: Get better prices through referrals",
            "Financial literacy: Learn profit vs revenue thinking",
            "Record keeping: Peer accountability for daily books",
            "Growth planning: When and how to open a second location",
        ],
        "benefits_sw": [
            "Kushiriki wauzaji: Pata bei bora kupitia rufaa",
            "Ujuzi wa kifedha: Jifunze kufikiri faida dhidi ya mapato",
            "Uhifadhi wa rekodi: Uwajibikaji wa rika kwa vitabu vya kila siku",
            "Mpango wa ukuaji: Linapofaa na jinsi ya kufungua eneo la pili",
        ],
        "compound_interest": COMPOUND_INTEREST_STORY,
    },
    "mitumba_vendor": {
        "name_en": "Mitumba Traders' Savings Group",
        "name_sw": "Kikundi cha Akiba ya Wachuuzi wa Mitumba",
        "description_en": "Clothing vendors forming a chama for bulk purchasing and profit sharing.",
        "description_sw": "Wachuuzi wa nguo wanaunda chama kwa kununua pamoja na kushiriki faida.",
        "meeting_frequency": "weekly",
        "focus_areas": ["bulk_import", "market_trends", "quality_assessment", "seasonal_planning"],
        "suggested_members": "Mitumba vendors from different markets (to avoid direct competition)",
        "benefits_en": [
            "Bulk buying: Import containers together, split costs",
            "Market intelligence: Share what styles are trending",
            "Quality grading: Learn to assess bale quality",
            "Seasonal planning: Coordinate stock for holidays and events",
        ],
        "benefits_sw": [
            "Kununua pamoja: Ingiza kontena pamoja, gawanya gharama",
            "Ujasusi wa soko: Shiriki mitindo inayotrendi",
            "Ubora wa kiwango: Jifunze kutathmini ubora wa mabale",
            "Mpango wa msimu: Panga hisa kwa likizo na matukio",
        ],
        "compound_interest": COMPOUND_INTEREST_STORY,
    },
    "mkono_worker": {
        "name_en": "Jua Kali Workers' Advancement Circle",
        "name_sw": "Duara la Kupanda kwa Wafanyakazi wa Mikono",
        "description_en": "Casual laborers supporting each other in skill development and savings.",
        "description_sw": "Wafanyakazi wa mkono wanasaidiana katika maendeleo ya ujuzi na akiba.",
        "meeting_frequency": "weekly",
        "focus_areas": ["skill_development", "savings_habit", "job_seeking", "health_insurance"],
        "suggested_members": "Fellow workers from your site or trade",
        "benefits_en": [
            "Skill sharing: Learn from each other's trades",
            "Savings accountability: Save before you spend",
            "Job networking: Share opportunities with each other",
            "NHIF awareness: Everyone should have health insurance",
        ],
        "benefits_sw": [
            "Kushiriki ujuzi: Jifunze kutoka kwa kila mmoja",
            "Uwajibikaji wa akiba: Hifadhi kabla ya kutumia",
            "Mitandao ya kazi: Shiriki fursa kwa kila mmoja",
            "Ufahamu wa NHIF: Kila mtu anapaswa kuwa na bima ya afya",
        ],
        "compound_interest": COMPOUND_INTEREST_STORY,
    },
    "beautician": {
        "name_en": "Beauty Professionals' Wealth Network",
        "name_sw": "Mitandao ya Utajiri ya Wataalamu wa Urembo",
        "description_en": "Salon and barbershop workers building financial literacy together.",
        "description_sw": "Wafanyakazi wa saluni na kinyozi wanajenga ujuzi wa kifedha pamoja.",
        "meeting_frequency": "biweekly",
        "focus_areas": ["client_retention", "product_investment", "savings_discipline", "skill_certification"],
        "suggested_members": "Beauty professionals in your area (different specializations)",
        "benefits_en": [
            "Client referrals: Send overflow to trusted colleagues",
            "Product knowledge: Share supplier contacts and reviews",
            "Financial goals: Track savings progress together",
            "Certification: Pool resources for training courses",
        ],
        "benefits_sw": [
            "Rufaa za wateja: Tuma ziada kwa wenzako unaowaamini",
            "Ujuzi wa bidhaa: Shiriki mawasiliano ya wauzaji na ukaguzi",
            "Malengo ya kifedha: Fuatilia maendeleo ya akiba pamoja",
            "Uthibitisho: Changisha rasilimali kwa kozi za mafunzo",
        ],
        "compound_interest": COMPOUND_INTEREST_STORY,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Lesson Management
# ─────────────────────────────────────────────────────────────────────────────


async def seed_lessons(db: AsyncSession) -> int:
    """Seed all 56 lessons into the database. Returns count of new lessons created."""

    count_result = await db.execute(select(func.count(MindsetLesson.id)))
    existing = count_result.scalar() or 0
    if existing >= 56:
        return 0

    created = 0
    for lesson_data in get_all_lessons():
        exists = await db.execute(
            select(MindsetLesson).where(
                and_(
                    MindsetLesson.module_number == lesson_data["module_number"],
                    MindsetLesson.lesson_number == lesson_data["lesson_number"],
                )
            )
        )
        if exists.scalar_one_or_none():
            continue

        lesson = MindsetLesson(
            module_number=lesson_data["module_number"],
            lesson_number=lesson_data["lesson_number"],
            title_en=lesson_data["title_en"],
            title_sw=lesson_data["title_sw"],
            source_book=lesson_data["source_book"],
            key_takeaway=lesson_data["key_takeaway"],
            duration_minutes=lesson_data["duration_minutes"],
            difficulty=lesson_data["difficulty"],
            order_index=lesson_data["order_index"],
            is_active=True,
        )
        db.add(lesson)
        created += 1

    await db.flush()
    logger.info("mindset_lessons_seeded", created=created)
    return created


async def seed_affirmations(db: AsyncSession) -> int:
    """Seed all affirmations into the database. Returns count of new affirmations created."""

    count_result = await db.execute(select(func.count(Affirmation.id)))
    existing = count_result.scalar() or 0
    if existing >= len(AFFIRMATIONS):
        return 0

    created = 0
    for aff_data in AFFIRMATIONS:
        exists = await db.execute(
            select(Affirmation).where(
                and_(
                    Affirmation.text_en == aff_data["text_en"],
                    Affirmation.category == aff_data["category"],
                )
            )
        )
        if exists.scalar_one_or_none():
            continue

        affirmation = Affirmation(
            text_en=aff_data["text_en"],
            text_sw=aff_data["text_sw"],
            category=aff_data["category"],
            source_book=aff_data.get("source_book"),
            is_active=True,
        )
        db.add(affirmation)
        created += 1

    await db.flush()
    logger.info("affirmations_seeded", created=created)
    return created


async def get_daily_lesson(
    db: AsyncSession,
    user_id: UUID,
) -> Dict[str, Any]:
    """
    Get personalized daily lesson for a user.

    Returns the next uncompleted lesson in sequence based on user progress.
    Falls back to cycling through lessons if all are completed.
    """

    # Get user's completed lessons
    completed_result = await db.execute(
        select(UserLessonProgress.lesson_id).where(
            and_(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.completed == True,
            )
        )
    )
    completed_ids = set(row[0] for row in completed_result.all())

    # Get all active lessons ordered
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
        # All completed — cycle back to first lesson for review
        next_lesson = all_lessons[0] if all_lessons else None
        if next_lesson:
            return {
                "status": "review_mode",
                "message_sw": "Hongera! Umekamilisha masomo yote 56! Sasa anza tena kwa ukaguzi.",
                "message_en": "Congratulations! You've completed all 56 lessons! Starting review cycle.",
                "lesson": _format_lesson(next_lesson),
                "overall_progress": {
                    "completed": len(completed_ids),
                    "total": len(all_lessons),
                    "pct": 100.0,
                },
            }
        return {
            "status": "no_lessons",
            "message_sw": "Hakuna masomo bado.",
            "message_en": "No lessons available yet.",
        }

    # Get module info
    module_info = next(
        (m for m in MODULE_DEFINITIONS if m["module_number"] == next_lesson.module_number),
        None,
    )

    # Module progress
    module_lessons = [l for l in all_lessons if l.module_number == next_lesson.module_number]
    module_completed = sum(1 for l in module_lessons if l.id in completed_ids)

    return {
        "status": "available",
        "lesson": _format_lesson(next_lesson),
        "module": {
            "number": next_lesson.module_number,
            "title_en": module_info["title_en"] if module_info else None,
            "title_sw": module_info["title_sw"] if module_info else None,
            "description_en": module_info.get("description_en") if module_info else None,
            "description_sw": module_info.get("description_sw") if module_info else None,
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


def _format_lesson(lesson: MindsetLesson) -> Dict[str, Any]:
    """Format a lesson for API response."""
    return {
        "id": str(lesson.id),
        "module_number": lesson.module_number,
        "lesson_number": lesson.lesson_number,
        "title_en": lesson.title_en,
        "title_sw": lesson.title_sw,
        "source_book": lesson.source_book,
        "key_takeaway": lesson.key_takeaway,
        "duration_minutes": lesson.duration_minutes,
        "difficulty": lesson.difficulty,
        "audio_url": lesson.audio_url,
        "content_text": lesson.content_text,
        "order_index": lesson.order_index,
    }


async def track_lesson_completion(
    db: AsyncSession,
    user_id: UUID,
    lesson_id: UUID,
    score: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Track lesson completion for a user.

    Args:
        user_id: The user completing the lesson
        lesson_id: The lesson being completed
        score: Optional comprehension score (0-100)

    Returns:
        Completion status with progress info and module completion check
    """

    # Validate lesson exists
    lesson_result = await db.execute(
        select(MindsetLesson).where(MindsetLesson.id == lesson_id)
    )
    lesson = lesson_result.scalar_one_or_none()
    if not lesson:
        return {"error": "Lesson not found", "lesson_id": str(lesson_id)}

    # Upsert progress
    result = await db.execute(
        select(UserLessonProgress).where(
            and_(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.lesson_id == lesson_id,
            )
        )
    )
    progress = result.scalar_one_or_none()

    if progress:
        progress.completed = True
        progress.completed_at = datetime.now(timezone.utc)
        progress.listen_count += 1
        if score is not None:
            progress.score = score
    else:
        progress = UserLessonProgress(
            user_id=user_id,
            lesson_id=lesson_id,
            completed=True,
            completed_at=datetime.now(timezone.utc),
            last_listened_at=datetime.now(timezone.utc),
            listen_count=1,
            score=score,
        )
        db.add(progress)

    await db.flush()

    # Get overall progress
    total_completed_result = await db.execute(
        select(func.count(UserLessonProgress.id)).where(
            and_(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.completed == True,
            )
        )
    )
    total_completed = total_completed_result.scalar() or 0

    total_lessons_result = await db.execute(
        select(func.count(MindsetLesson.id)).where(MindsetLesson.is_active == True)
    )
    total_lessons = total_lessons_result.scalar() or 56

    # Check module completion
    module_lessons_result = await db.execute(
        select(MindsetLesson.id).where(
            MindsetLesson.module_number == lesson.module_number
        )
    )
    module_lesson_ids = [row[0] for row in module_lessons_result.all()]

    module_progress_result = await db.execute(
        select(func.count(UserLessonProgress.id)).where(
            and_(
                UserLessonProgress.user_id == user_id,
                UserLessonProgress.lesson_id.in_(module_lesson_ids),
                UserLessonProgress.completed == True,
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
        "module_number": lesson.module_number,
        "message_sw": (
            "Moduli imekamilika! Umefungua moduli mpya! Hongera sana!"
            if module_complete
            else "Somo limekamilika! Hongera!"
        ),
        "message_en": (
            "Module complete! You've unlocked a new module! Congratulations!"
            if module_complete
            else "Lesson complete! Well done!"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rich Habits Score
# ─────────────────────────────────────────────────────────────────────────────


async def get_rich_habits_score(
    db: AsyncSession,
    user_id: UUID,
    score_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Get or calculate rich habits score for a given date.

    Tracks 10 daily wealth-building habits:
    record_sales, check_balance, save_money, avoid_waste,
    give, learn, set_goal, review_day, help_peer, no_debt.

    Returns score (0-100), streak, level, and habit breakdown.
    """

    if score_date is None:
        score_date = date.today()

    result = await db.execute(
        select(RichHabitsScore).where(
            and_(
                RichHabitsScore.user_id == user_id,
                RichHabitsScore.score_date == score_date,
            )
        )
    )
    score_record = result.scalar_one_or_none()

    if not score_record:
        score_record = RichHabitsScore(
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

    # Streak
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
        "max_possible": sum(h["points"] for h in RICH_HABITS.values()),
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
        return {"error": f"Unknown habit: {habit_key}. Valid: {list(RICH_HABITS.keys())}"}

    if score_date is None:
        score_date = date.today()

    # Get or create today's score
    result = await db.execute(
        select(RichHabitsScore).where(
            and_(
                RichHabitsScore.user_id == user_id,
                RichHabitsScore.score_date == score_date,
            )
        )
    )
    score_record = result.scalar_one_or_none()

    if not score_record:
        score_record = RichHabitsScore(
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
        "habit_name_en": RICH_HABITS[habit_key]["en"],
        "habit_name_sw": RICH_HABITS[habit_key]["sw"],
        "completed": completed,
        "total_score": total,
        "max_possible": sum(h["points"] for h in RICH_HABITS.values()),
        "streak": streak,
        "level": score_record.level,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Daily Affirmations
# ─────────────────────────────────────────────────────────────────────────────


async def get_affirmation(
    db: AsyncSession,
    language: str = "en",
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get a daily affirmation in the specified language.

    Uses day-of-year rotation so the same affirmation appears each day,
    with category filtering optional.

    Args:
        db: Database session
        language: "en" for English, "sw" for Swahili
        category: Optional filter: belief, wealth, habits, savings, giving, compound

    Returns:
        Affirmation text, source, and category
    """

    valid_categories = {"belief", "wealth", "habits", "savings", "giving", "compound"}

    if category and category not in valid_categories:
        return {
            "error": f"Invalid category: {category}",
            "valid_categories": sorted(valid_categories),
        }

    # Use day-of-year for rotation
    day_index = date.today().timetuple().tm_yday - 1

    if category:
        pool = get_affirmations_by_category(category)
    else:
        pool = get_all_affirmations()

    if not pool:
        return {
            "text": "I am building wealth, one day at a time.",
            "text_sw": "Ninajenga utajiri, siku moja kwa wakati.",
            "category": "belief",
            "source_book": "Angavu Intelligence",
        }

    affirmation = pool[day_index % len(pool)]

    text_key = "text_sw" if language == "sw" else "text_en"

    return {
        "text": affirmation.get(text_key, affirmation["text_en"]),
        "text_en": affirmation["text_en"],
        "text_sw": affirmation["text_sw"],
        "category": affirmation["category"],
        "source_book": affirmation.get("source_book", "Unknown"),
        "language": language,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Habit Stacking Formulas
# ─────────────────────────────────────────────────────────────────────────────


async def get_habit_stack(
    db: AsyncSession,
    user_id: UUID,
    worker_type: str,
) -> Dict[str, Any]:
    """
    Get habit stacking formula for a specific worker type.

    Habit stacking (from Atomic Habits): "After X, I will do Y."
    Each worker type has a tailored daily chain of 10-12 habits
    linked to their specific work routine.

    Args:
        db: Database session
        user_id: User requesting the stack
        worker_type: One of mama_mboga, boda_boda, duka_owner,
                     mitumba_vendor, mkono_worker, beautician

    Returns:
        Full habit stack with times, descriptions, and daily affirmation
    """

    stack = get_habit_stack(worker_type)
    if not stack:
        available = get_all_worker_types()
        return {
            "error": f"Unknown worker type: {worker_type}",
            "available_types": available,
        }

    # Get user's current score to personalize
    score_result = await db.execute(
        select(RichHabitsScore).where(
            and_(
                RichHabitsScore.user_id == user_id,
                RichHabitsScore.score_date == date.today(),
            )
        )
    )
    current_score = score_result.scalar_one_or_none()

    total_points = sum(h["points"] for h in stack["stack"])

    return {
        "worker_type": stack["worker_type"],
        "name_en": stack["name_en"],
        "name_sw": stack["name_sw"],
        "description_en": stack["description_en"],
        "description_sw": stack["description_sw"],
        "total_habits": len(stack["stack"]),
        "total_points": total_points,
        "stack": stack["stack"],
        "daily_affirmation_en": stack["daily_affirmation_en"],
        "daily_affirmation_sw": stack["daily_affirmation_sw"],
        "current_score": current_score.total_score if current_score else 0,
        "tip_en": "Start with the first habit. Build one at a time. Consistency beats intensity.",
        "tip_sw": "Anza na tabia ya kwanza. Jenga moja kwa wakati. Uthabiti unashinda ukubwa.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mastermind Group Recommendations
# ─────────────────────────────────────────────────────────────────────────────


async def get_mastermind_group(
    db: AsyncSession,
    user_id: UUID,
    worker_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get mastermind group recommendations for a user.

    Based on Napoleon Hill's Master Mind principle: "No two minds ever
    come together without creating a third, invisible, intangible force
    which may be likened to a third mind."

    If worker_type is not provided, tries to detect from user's habit stack
    history or defaults to a generic recommendation.
    """

    if not worker_type:
        # Default to mama_mboga if no type specified
        worker_type = "mama_mboga"

    group = MASTERMIND_GROUPS.get(worker_type)
    if not group:
        available = list(MASTERMIND_GROUPS.keys())
        return {
            "error": f"Unknown worker type: {worker_type}",
            "available_types": available,
        }

    # Get user's streak for personalization
    streak_result = await db.execute(
        select(RichHabitsScore).where(
            and_(
                RichHabitsScore.user_id == user_id,
                RichHabitsScore.score_date >= date.today() - timedelta(days=30),
                RichHabitsScore.total_score >= 60,
            )
        )
    )
    recent_scores = streak_result.scalars().all()

    # Find best score
    best_score = max((s.total_score for s in recent_scores), default=0)

    motivation_message = ""
    if best_score >= 80:
        motivation_message = (
            "You're ready to lead a mastermind group! Your consistency shows discipline."
            if len(recent_scores) >= 5
            else "Great scores! Invite others to match your consistency."
        )
    elif best_score >= 50:
        motivation_message = (
            "You're building the habit. A mastermind group will accelerate your growth."
        )
    else:
        motivation_message = (
            "Start by finding 2-3 people who share your financial goals. "
            "You don't need to be perfect — you need to be committed."
        )

    return {
        "worker_type": worker_type,
        "group_name_en": group["name_en"],
        "group_name_sw": group["name_sw"],
        "description_en": group["description_en"],
        "description_sw": group["description_sw"],
        "meeting_frequency": group["meeting_frequency"],
        "focus_areas": group["focus_areas"],
        "suggested_members": group["suggested_members"],
        "benefits_en": group["benefits_en"],
        "benefits_sw": group["benefits_sw"],
        "compound_interest": group["compound_interest"],
        "motivation_message": motivation_message,
        "your_best_score": best_score,
        "how_to_start_en": (
            "1. Find 4-6 people with similar goals\n"
            "2. Agree to meet weekly (even 30 minutes)\n"
            "3. Each person shares: wins, challenges, next week's goal\n"
            "4. Hold each other accountable with kindness\n"
            "5. Track savings progress together"
        ),
        "how_to_start_sw": (
            "1. Tafuta watu 4-6 wenye malengo sawa\n"
            "2. Kubaliana kukutana kila wiki (hata dakika 30)\n"
            "3. Kila mtu ashiriki: ushindi, changamoto, lengo la wiki ijayo\n"
            "4. Shikamaneni kwa upole\n"
            "5. Fuatilia maendeleo ya akiba pamoja"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mindset Briefing
# ─────────────────────────────────────────────────────────────────────────────


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
    lesson = await get_daily_lesson(db, user_id)

    # Today's affirmation
    affirmation = await get_affirmation(db, language="en")

    if briefing_type == "weekly":
        week_start = today - timedelta(days=7)
        week_scores_result = await db.execute(
            select(RichHabitsScore).where(
                and_(
                    RichHabitsScore.user_id == user_id,
                    RichHabitsScore.score_date >= week_start,
                    RichHabitsScore.score_date <= today,
                )
            )
        )
        week_scores = week_scores_result.scalars().all()
        avg_score = (
            sum(s.total_score for s in week_scores) / max(len(week_scores), 1)
            if week_scores
            else 0
        )

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
            "affirmation": affirmation,
            "message_sw": f"Ripoti ya wiki: Score yako ya wastani ni {avg_score:.0f}. Endelea kujenga!",
            "message_en": f"Weekly report: Your average score is {avg_score:.0f}. Keep building!",
        }

    return {
        "type": "daily",
        "date": str(today),
        "score": score,
        "today_lesson": lesson,
        "affirmation": affirmation,
        "compound_interest": COMPOUND_INTEREST_STORY,
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

    start = as_of_date - timedelta(days=365)
    result = await db.execute(
        select(RichHabitsScore.score_date, RichHabitsScore.total_score)
        .where(
            and_(
                RichHabitsScore.user_id == user_id,
                RichHabitsScore.score_date >= start,
                RichHabitsScore.score_date <= as_of_date,
                RichHabitsScore.total_score >= 60,
            )
        )
        .order_by(RichHabitsScore.score_date.desc())
    )
    qualifying_dates = [row[0] for row in result.all()]

    if not qualifying_dates:
        return 0

    streak = 0
    expected = as_of_date
    for d in qualifying_dates:
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d == expected - timedelta(days=1):
            streak += 1
            expected = d - timedelta(days=1)
        else:
            break

    return streak
