"""ORM Models for Angavu Intelligence backend.

All models are defined once in their canonical module. This __init__.py
re-exports them for convenience. There are no duplicate table definitions.
"""

# ── Core ─────────────────────────────────────────────────────────────────
from app.models.user import User
from app.models.transaction import Inventory, Transaction
from app.models.refresh_token import RefreshToken

# ── Buyers & Intelligence ───────────────────────────────────────────────
from app.models.buyer import Buyer, BuyerAPIKey
from app.models.intelligence_products import (
    AlamaScore,
    AlamaScoreOutcome,
    BiasharaPulseReport,
    DataAccessLog,
    DistributionGapReport,
    IntelligenceProduct,
    JamiiInsightsReport,
    SokoPulseReport,
    TaxBaseEstimation,
)

# ── Worker Features (V2 — canonical) ────────────────────────────────────
from app.models.goal import Goal, GoalMilestone, GoalProgressEntry
from app.models.loan import Loan, LoanRepayment, PurposeVerification
from app.models.mindset import (
    Affirmation,
    MindsetLesson,
    RichHabitsScore,
    UserLessonProgress,
)
from app.models.tithe import AbundancePattern, TitheRecord, TitheReport

# ── Gamification / Stickiness ───────────────────────────────────────────
from app.models.stickiness import (
    Badge,
    Streak,
    UserBadge,
    UserEngagement,
    UserLevel,
)

# ── Infrastructure ──────────────────────────────────────────────────────
from app.models.infrastructure import (
    CostTracking,
    FederatedUpdate,
    ModelVersion,
    ServerMetric,
)

# ── Agent Models (Pydantic, not ORM) ────────────────────────────────────
from app.models.agent_models import (
    AgentConfig,
    AgentInsight,
    AgentRecommendation,
    WorkerType,
)

# ── Autonomous Operations ───────────────────────────────────────────────
from app.models.autonomous.invoice import InvoiceDB, InvoiceItemDB
from app.models.autonomous.lead import LeadDB
from app.models.autonomous.metric import RevenueMetricDB
from app.models.autonomous.onboarding import OnboardingFlowDB, OnboardingStepDB

# ── Backward-compat aliases (remove after callers are updated) ──────────
from app.models.worker_features import (  # noqa: F401
    GoalContribution,
    GoalRecord,
    LoanRecord,
    LoanROICheckin,
    MindsetLessonProgress,
)

__all__ = [
    # Core
    "User",
    "Transaction",
    "Inventory",
    "RefreshToken",
    # Buyers & Intelligence
    "Buyer",
    "BuyerAPIKey",
    "IntelligenceProduct",
    "DataAccessLog",
    "AlamaScore",
    "AlamaScoreOutcome",
    "SokoPulseReport",
    "BiasharaPulseReport",
    "JamiiInsightsReport",
    "TaxBaseEstimation",
    "DistributionGapReport",
    # Worker Features (V2)
    "Goal",
    "GoalMilestone",
    "GoalProgressEntry",
    "Loan",
    "LoanRepayment",
    "PurposeVerification",
    "MindsetLesson",
    "UserLessonProgress",
    "RichHabitsScore",
    "Affirmation",
    "TitheRecord",
    "TitheReport",
    "AbundancePattern",
    # Gamification
    "Badge",
    "UserBadge",
    "UserLevel",
    "Streak",
    "UserEngagement",
    # Infrastructure
    "ServerMetric",
    "ModelVersion",
    "FederatedUpdate",
    "CostTracking",
    # Agent (Pydantic)
    "AgentConfig",
    "AgentInsight",
    "AgentRecommendation",
    "WorkerType",
    # Autonomous
    "InvoiceDB",
    "InvoiceItemDB",
    "LeadDB",
    "RevenueMetricDB",
    "OnboardingFlowDB",
    "OnboardingStepDB",
    # Backward-compat aliases
    "GoalRecord",
    "GoalContribution",
    "LoanRecord",
    "LoanROICheckin",
    "MindsetLessonProgress",
]
