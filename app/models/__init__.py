"""ORM Models for Msaidizi backend."""

from app.models.user import User
from app.models.transaction import Transaction, Inventory
from app.models.intelligence import IntelligenceProduct, DataAccessLog
from app.models.buyer import Buyer, BuyerAPIKey
from app.models.intelligence_products import (
    SokoPulseReport,
    BiasharaPulseReport,
    AlamaScore,
    JamiiInsightsReport,
    TaxBaseEstimation,
    DistributionGapReport,
)
from app.models.tithe import TitheRecord, TitheReport, AbundancePattern
from app.models.worker_features import (
    # TitheRecord is re-exported from app.models.tithe
    GoalRecord,
    GoalContribution,
    LoanRecord,
    LoanRepayment,
    LoanROICheckin,
    MindsetLesson,
    MindsetLessonProgress,
    RichHabitScore,
)
from app.models.goal import (
    Goal,
    GoalMilestone,
    GoalProgressEntry,
)
from app.models.infrastructure import (
    ServerMetric,
    ModelVersion,
    FederatedUpdate,
    CostTracking,
)
from app.models.agent_models import (
    WorkerType,
    AgentConfig,
    AgentInsight,
    AgentRecommendation,
)
from app.models.stickiness import (
    UserEngagement,
    Badge,
    UserBadge,
    UserLevel,
    Streak,
)

__all__ = [
    "User",
    "Transaction",
    "Inventory",
    "IntelligenceProduct",
    "DataAccessLog",
    "Buyer",
    "BuyerAPIKey",
    "SokoPulseReport",
    "BiasharaPulseReport",
    "AlamaScore",
    "JamiiInsightsReport",
    "TaxBaseEstimation",
    "DistributionGapReport",
    "TitheRecord",
    "TitheReport",
    "AbundancePattern",
    "GoalRecord",
    "GoalContribution",
    "LoanRecord",
    "LoanRepayment",
    "LoanROICheckin",
    "MindsetLesson",
    "MindsetLessonProgress",
    "RichHabitScore",
    "Goal",
    "GoalMilestone",
    "GoalProgressEntry",
    "ServerMetric",
    "ModelVersion",
    "FederatedUpdate",
    "CostTracking",
    "WorkerType",
    "AgentConfig",
    "AgentInsight",
    "AgentRecommendation",
    "UserEngagement",
    "Badge",
    "UserBadge",
    "UserLevel",
    "Streak",
]
