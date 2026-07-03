"""
Gamification Data — Badges, Levels, Rewards, and Social Proof Templates.

Design principles:
- Anti-shame: No public leaderboards, no negative comparisons
- Variable rewards: Surprise elements to trigger dopamine
- Streak protection: Forgiveness mechanics (streak shields)
- Social proof: Anonymized peer comparison ("73% of sellers like you...")
- Swahili-first: All badge names and descriptions in Swahili
"""

from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# 18 Swahili Badges
# ═══════════════════════════════════════════════════════════════════════════════

BADGES: list[dict[str, Any]] = [
    # ── Onboarding Badges (Aha Moment) ──────────────────────────────────
    {
        "name": "kwanza_sale",
        "swahili_name": "Mauzo ya Kwanza",
        "description": "Record your first sale",
        "description_sw": "Andika mauzo yako ya kwanza",
        "icon": "🎯",
        "category": "onboarding",
        "criteria": {"type": "first_action", "action": "record_sale"},
        "xp_reward": 50,
    },
    {
        "name": "siku_ya_kwanza",
        "swahili_name": "Siku ya Kwanza",
        "description": "Complete your first full day of tracking",
        "description_sw": "Maliza siku yako ya kwanza ya kufuatilia",
        "icon": "☀️",
        "category": "onboarding",
        "criteria": {"type": "daily_active", "days": 1},
        "xp_reward": 30,
    },
    {
        "name": "mfanyakazi_mpya",
        "swahili_name": "Mfanyakazi Mpya",
        "description": "Set up your business profile completely",
        "description_sw": "Weka wasifu wako wa biashara kikamilifu",
        "icon": "📋",
        "category": "onboarding",
        "criteria": {"type": "profile_complete"},
        "xp_reward": 40,
    },
    # ── Consistency Badges ──────────────────────────────────────────────
    {
        "name": "mfululizo_wiki",
        "swahili_name": "Wiki Moja Mfululizo",
        "description": "7-day activity streak",
        "description_sw": "Siku 7 mfululizo za shughuli",
        "icon": "🔥",
        "category": "consistency",
        "criteria": {"type": "streak", "days": 7},
        "xp_reward": 100,
    },
    {
        "name": "mfululizo_mwezi",
        "swahili_name": "Mwezi Mmoja Mfululizo",
        "description": "30-day activity streak",
        "description_sw": "Siku 30 mfululizo za shughuli",
        "icon": "💪",
        "category": "consistency",
        "criteria": {"type": "streak", "days": 30},
        "xp_reward": 300,
    },
    {
        "name": "mfululizo_robo",
        "swahili_name": "Robo Mwaka Mfululizo",
        "description": "90-day activity streak",
        "description_sw": "Siku 90 mfululizo za shughuli",
        "icon": "👑",
        "category": "consistency",
        "criteria": {"type": "streak", "days": 90},
        "xp_reward": 500,
    },
    # ── Business Growth Badges ──────────────────────────────────────────
    {
        "name": "mauzo_mazuri",
        "swahili_name": "Mauzo Mazuri",
        "description": "Record 100 transactions",
        "description_sw": "Andika miamala 100",
        "icon": "📈",
        "category": "growth",
        "criteria": {"type": "transaction_count", "count": 100},
        "xp_reward": 150,
    },
    {
        "name": "mfalme_wa_mauzo",
        "swahili_name": "Mfalme wa Mauzo",
        "description": "Record 1,000 transactions",
        "description_sw": "Andika miamala 1,000",
        "icon": "🏆",
        "category": "growth",
        "criteria": {"type": "transaction_count", "count": 1000},
        "xp_reward": 500,
    },
    {
        "name": "biashara_inayokua",
        "swahili_name": "Biashara Inayokua",
        "description": "Increase daily sales by 20% over 2 weeks",
        "description_sw": "Ongeza mauzo ya kila siku kwa 20% kwa wiki 2",
        "icon": "🌱",
        "category": "growth",
        "criteria": {"type": "sales_growth", "percent": 20, "period_days": 14},
        "xp_reward": 200,
    },
    # ── Intelligence Badges ─────────────────────────────────────────────
    {
        "name": "msomi_wa_biashara",
        "swahili_name": "Msomi wa Biashara",
        "description": "Read 10 business insights",
        "description_sw": "Soma maarifa 10 ya biashara",
        "icon": "🧠",
        "category": "intelligence",
        "criteria": {"type": "insights_read", "count": 10},
        "xp_reward": 100,
    },
    {
        "name": "mchambuzi",
        "swahili_name": "Mchambuzi",
        "description": "Use the analysis feature 5 times",
        "description_sw": "Tumia kipengele cha uchambuzi mara 5",
        "icon": "🔍",
        "category": "intelligence",
        "criteria": {"type": "analysis_used", "count": 5},
        "xp_reward": 120,
    },
    {
        "name": "mjasiriamali_mwerevu",
        "swahili_name": "Mjasiriamali Mwerevu",
        "description": "Follow 5 AI recommendations and see improvement",
        "description_sw": "Fuata mapendekezo 5 ya AI na uone maboresho",
        "icon": "💡",
        "category": "intelligence",
        "criteria": {"type": "recommendations_followed", "count": 5},
        "xp_reward": 250,
    },
    # ── Financial Health Badges ─────────────────────────────────────────
    {
        "name": "akiba_ya_kwanza",
        "swahili_name": "Akiba ya Kwanza",
        "description": "Set aside savings for the first time",
        "description_sw": "Weka akiba kwa mara ya kwanza",
        "icon": "🏦",
        "category": "financial",
        "criteria": {"type": "first_savings"},
        "xp_reward": 80,
    },
    {
        "name": "mpango_wa_baadae",
        "swahili_name": "Mpango wa Baadaye",
        "description": "Create your first financial goal",
        "description_sw": "Unda lengo lako la kwanza la kifedha",
        "icon": "🎯",
        "category": "financial",
        "criteria": {"type": "first_goal"},
        "xp_reward": 60,
    },
    {
        "name": "deni_shujaa",
        "swahili_name": "Shujaa wa Deni",
        "description": "Pay off a loan completely",
        "description_sw": "Lipa mkopo wote",
        "icon": "🎖️",
        "category": "financial",
        "criteria": {"type": "loan_paid_off"},
        "xp_reward": 200,
    },
    # ── Social & Community Badges ───────────────────────────────────────
    {
        "name": "rafiki_wa_biashara",
        "swahili_name": "Rafiki wa Biashara",
        "description": "Share a tip with another seller",
        "description_sw": "Shiriki neno na muuzaji mwingine",
        "icon": "🤝",
        "category": "social",
        "criteria": {"type": "tip_shared"},
        "xp_reward": 50,
    },
    {
        "name": "kiongozi_wa_jamii",
        "swahili_name": "Kiongozi wa Jamii",
        "description": "Help 3 other sellers get started",
        "description_sw": "Saidia wauzaji 3 wengine kuanza",
        "icon": "⭐",
        "category": "social",
        "criteria": {"type": "referrals", "count": 3},
        "xp_reward": 300,
    },
    {
        "name": "mzee_wa_soko",
        "swahili_name": "Mzee wa Soko",
        "description": "Use Biashara Intelligence for 6 months",
        "description_sw": "Tumia Biashara Intelligence kwa miezi 6",
        "icon": "🏅",
        "category": "loyalty",
        "criteria": {"type": "account_age_days", "days": 180},
        "xp_reward": 400,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# 6 Levels — Mwanafunzi → Legend
# ═══════════════════════════════════════════════════════════════════════════════

LEVELS: list[dict[str, Any]] = [
    {
        "level": 1,
        "name": "Mwanafunzi",
        "name_en": "Student",
        "description": "Just getting started — learning the ropes",
        "description_sw": "Unaanza — kujifunza njia",
        "icon": "📚",
        "xp_required": 0,
        "xp_to_next": 200,
        "perks": ["basic_insights", "daily_tips"],
    },
    {
        "level": 2,
        "name": "Mfanyakazi",
        "name_en": "Worker",
        "description": "Building good habits — consistent tracking",
        "description_sw": "Kujenga tabia nzuri — kufuatilia mara kwa mara",
        "icon": "🔧",
        "xp_required": 200,
        "xp_to_next": 500,
        "perks": ["basic_insights", "daily_tips", "weekly_report", "streak_shield_1"],
    },
    {
        "level": 3,
        "name": "Mjasiriamali",
        "name_en": "Entrepreneur",
        "description": "Running a real business — insights matter",
        "description_sw": "Kuendesha biashara halisi — maarifa ni muhimu",
        "icon": "💼",
        "xp_required": 500,
        "xp_to_next": 1000,
        "perks": ["basic_insights", "daily_tips", "weekly_report", "streak_shield_2", "advanced_analysis"],
    },
    {
        "level": 4,
        "name": "Bingwa",
        "name_en": "Champion",
        "description": "Top performer — inspiring others",
        "description_sw": "Mfanyakazi bora — kuhamasisha wengine",
        "icon": "🏅",
        "xp_required": 1000,
        "xp_to_next": 2000,
        "perks": ["basic_insights", "daily_tips", "weekly_report", "streak_shield_3", "advanced_analysis", "priority_support"],
    },
    {
        "level": 5,
        "name": "Mzee",
        "name_en": "Elder",
        "description": "Wisdom and experience — a pillar of the community",
        "description_sw": "Busara na uzoefu — nguzo ya jamii",
        "icon": "👑",
        "xp_required": 2000,
        "xp_to_next": 5000,
        "perks": ["basic_insights", "daily_tips", "weekly_report", "streak_shield_5", "advanced_analysis", "priority_support", "custom_reports"],
    },
    {
        "level": 6,
        "name": "Legend",
        "name_en": "Legend",
        "description": "The best of the best — a true business legend",
        "description_sw": "Bora ya bora — hadithi halisi ya biashara",
        "icon": "🌟",
        "xp_required": 5000,
        "xp_to_next": None,  # Max level
        "perks": ["all_features", "streak_shield_unlimited", "vip_support", "beta_access"],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Variable Reward Templates
# ═══════════════════════════════════════════════════════════════════════════════

VARIABLE_REWARDS: list[dict[str, Any]] = [
    # ── Insight Surprises ───────────────────────────────────────────────
    {
        "type": "insight_boost",
        "title": "Ufunuo wa Siku!",
        "title_en": "Daily Revelation!",
        "message_sw": "Biashara yako inafanya vizuri kuliko {percent}% ya wauzaji wa {category} eneo lako!",
        "message_en": "Your business is doing better than {percent}% of {category} sellers in your area!",
        "icon": "💡",
        "weight": 25,
        "cooldown_hours": 24,
    },
    {
        "type": "market_tip",
        "title": "Neno la Soko",
        "title_en": "Market Word",
        "message_sw": "Wauzaji wa {category} wanaongeza bei ya {item} kwa {percent}% wiki hii. Fikiria kuuza zaidi!",
        "message_en": "{category} sellers are raising {item} prices by {percent}% this week. Consider stocking more!",
        "icon": "📊",
        "weight": 20,
        "cooldown_hours": 48,
    },
    # ── Motivation Surprises ────────────────────────────────────────────
    {
        "type": "streak_bonus",
        "title": "Zawadi ya Mfululizo!",
        "title_en": "Streak Bonus!",
        "message_sw": "Umefanya kazi kwa siku {days} mfululizo! Hii ni zawadi yako ya XP bonus: +{xp} XP!",
        "message_en": "You've worked {days} days in a row! Here's your bonus XP: +{xp} XP!",
        "icon": "🔥",
        "weight": 15,
        "cooldown_hours": 168,  # Weekly max
    },
    {
        "type": "peer_comparison",
        "title": "Uko Vizuri!",
        "title_en": "You're Doing Great!",
        "message_sw": "Wauzaji {count} kama wewe walipata faida zaidi wiki hii. Wewe ni mmoja wao!",
        "message_en": "{count} sellers like you earned more profit this week. You're one of them!",
        "icon": "🌟",
        "weight": 15,
        "cooldown_hours": 72,
    },
    # ── Fun/Luck Surprises ──────────────────────────────────────────────
    {
        "type": "lucky_day",
        "title": "Siku ya Bahati!",
        "title_en": "Lucky Day!",
        "message_sw": "Leo ni siku yako ya bahati! XP yako ya leo imeongezeka mara {multiplier}x!",
        "message_en": "Today is your lucky day! Your XP today is multiplied by {multiplier}x!",
        "icon": "🍀",
        "weight": 5,
        "cooldown_hours": 168,
    },
    {
        "type": "hidden_achievement",
        "title": "Fungua Siri!",
        "title_en": "Secret Unlocked!",
        "message_sw": "Umefungua jina la siri: '{badge_name}'! {description_sw}",
        "message_en": "You unlocked a secret badge: '{badge_name}'! {description_en}",
        "icon": "🎁",
        "weight": 5,
        "cooldown_hours": 336,  # Bi-weekly
    },
    {
        "type": "wisdom_quote",
        "title": "Neno la Hekima",
        "title_en": "Word of Wisdom",
        "message_sw": "\"{quote_sw}\" — {author}",
        "message_en": "\"{quote_en}\" — {author}",
        "icon": "📖",
        "weight": 15,
        "cooldown_hours": 24,
    },
]

# Wisdom quotes pool
WISDOM_QUOTES: list[dict[str, str]] = [
    {
        "quote_sw": "Akili ni mali — uwekezaji katika maarifa haujawahi kupoteza.",
        "quote_en": "Knowledge is wealth — investing in wisdom never loses.",
        "author": "Methali ya Kiafrika",
    },
    {
        "quote_sw": "Maji hufuata mkondo — fuate wateja wako.",
        "quote_en": "Water follows the stream — follow your customers.",
        "author": "Dukawallah wa Gikomba",
    },
    {
        "quote_sw": "Haba na haba, hujaza kibaba.",
        "quote_en": "Little by little, fills the measure.",
        "author": "Methali ya Kiswahili",
    },
    {
        "quote_sw": "Mti haumei siku moja — biashara inahitaji uvumilivu.",
        "quote_en": "A tree doesn't grow in one day — business needs patience.",
        "author": "Mama Mboga wa Korogocho",
    },
    {
        "quote_sw": "Samaki mkunje angali mbichi.",
        "quote_en": "Bend the fish while it's still fresh.",
        "author": "Methali ya Kiswahili",
    },
    {
        "quote_sw": "Penye nia pana njia.",
        "quote_en": "Where there's a will, there's a way.",
        "author": "Methali ya Kiswahili",
    },
    {
        "quote_sw": "Fanya kazi kwa bidii, lakini fanya kazi kwa akili.",
        "quote_en": "Work hard, but work smart.",
        "author": "Mfanyabiashara wa Nairobi",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Social Proof Templates
# ═══════════════════════════════════════════════════════════════════════════════

SOCIAL_PROOF_TEMPLATES: list[dict[str, Any]] = [
    {
        "type": "peer_activity",
        "message_sw": "{percent}% ya wauzaji wa {category} eneo lako walitumia Biashara Intelligence wiki hii.",
        "message_en": "{percent}% of {category} sellers in your area used Biashara Intelligence this week.",
        "icon": "👥",
    },
    {
        "type": "peer_savings",
        "message_sw": "Wauzaji {count} kama wewe waliweka akiba ya wastani KSh {amount} wiki hii.",
        "message_en": "{count} sellers like you saved an average of KSh {amount} this week.",
        "icon": "💰",
    },
    {
        "type": "peer_growth",
        "message_sw": "Wafanyabiashara waliofuata mapendekezo ya AI waliongeza mauzo kwa {percent}% mwezi huu.",
        "message_en": "Business owners who followed AI recommendations increased sales by {percent}% this month.",
        "icon": "📈",
    },
    {
        "type": "peer_streak",
        "message_sw": "Wauzaji {count} eneo lako wana mfululizo wa siku 7+ za kufuatilia biashara.",
        "message_en": "{count} sellers in your area have a 7+ day streak of tracking their business.",
        "icon": "🔥",
    },
    {
        "type": "community_milestone",
        "message_sw": "Jamii ya Biashara Intelligence imefikia wauzaji {count}! Wewe ni sehemu ya familia hii.",
        "message_en": "The Biashara Intelligence community reached {count} sellers! You're part of this family.",
        "icon": "🎉",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Aha Moment Tracking
# ═══════════════════════════════════════════════════════════════════════════════

AHA_MOMENTS: dict[str, dict[str, Any]] = {
    "first_sale": {
        "name": "First Sale Recorded",
        "name_sw": "Mauzo ya Kwanza Yameandikwa",
        "target_seconds": 60,
        "xp_reward": 100,
        "importance": "critical",
    },
    "first_insight_viewed": {
        "name": "First Insight Viewed",
        "name_sw": "Maarifa ya Kwanza Yameonekana",
        "target_seconds": 120,
        "xp_reward": 75,
        "importance": "high",
    },
    "first_report_generated": {
        "name": "First Report Generated",
        "name_sw": "Ripoti ya Kwanza Imetolewa",
        "target_seconds": 300,
        "xp_reward": 150,
        "importance": "high",
    },
    "profile_complete": {
        "name": "Profile Completed",
        "name_sw": "Wasifu Umekamilika",
        "target_seconds": 180,
        "xp_reward": 50,
        "importance": "medium",
    },
    "second_session": {
        "name": "Returned for Second Session",
        "name_sw": "Rudi Kwa Kipindi cha Pili",
        "target_seconds": None,
        "xp_reward": 60,
        "importance": "high",
    },
    "week_active": {
        "name": "Active for 7 Days",
        "name_sw": "Imetumika kwa Siku 7",
        "target_seconds": None,
        "xp_reward": 200,
        "importance": "critical",
    },
}


def get_badge_by_name(name: str) -> dict[str, Any] | None:
    """Look up a badge by its unique name."""
    for badge in BADGES:
        if badge["name"] == name:
            return badge
    return None


def get_level_for_xp(xp: int) -> dict[str, Any]:
    """Return the level definition for the given XP total."""
    current = LEVELS[0]
    for level in LEVELS:
        if xp >= level["xp_required"]:
            current = level
        else:
            break
    return current


def get_next_level(current_level: int) -> dict[str, Any] | None:
    """Return the next level definition, or None if max level."""
    for level in LEVELS:
        if level["level"] == current_level + 1:
            return level
    return None
