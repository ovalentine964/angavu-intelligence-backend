"""ORM Models for Msaidizi backend."""

from app.models.agent_models import (
    AgentConfig,
    AgentInsight,
    AgentRecommendation,
    WorkerType,
)
from app.models.buyer import Buyer, BuyerAPIKey
from app.models.goal import (
    Goal,
    GoalMilestone,
    GoalProgressEntry,
)
from app.models.infrastructure import (
    CostTracking,
    FederatedUpdate,
    ModelVersion,
    ServerMetric,
)
from app.models.intelligence import DataAccessLog, IntelligenceProduct
from app.models.intelligence_products import (
    AlamaScore,
    BiasharaPulseReport,
    DistributionGapReport,
    JamiiInsightsReport,
    SokoPulseReport,
    TaxBaseEstimation,
)
from app.models.loan import (
    Loan,
    PurposeVerification,
)
from app.models.loan import (
    LoanRepayment as LoanRepaymentV2,
)
from app.models.mindset import (
    Affirmation,
    RichHabitsScore,
    UserLessonProgress,
)
from app.models.mindset import (
    MindsetLesson as MindsetLessonV2,
)
from app.models.stickiness import (
    Badge,
    Streak,
    UserBadge,
    UserEngagement,
    UserLevel,
)
from app.models.tithe import AbundancePattern, TitheRecord, TitheReport
from app.models.transaction import Inventory, Transaction
from app.models.user import User
from app.models.worker_features import (
    GoalContribution,
    # TitheRecord is re-exported from app.models.tithe
    GoalRecord,
    LoanRecord,
    LoanRepayment,
    LoanROICheckin,
    MindsetLesson,
    MindsetLessonProgress,
    RichHabitScore,
)

__all__ = [
    "AbundancePattern",
    "Affirmation",
    "AgentConfig",
    "AgentInsight",
    "AgentRecommendation",
    "AlamaScore",
    "Badge",
    "BiasharaPulseReport",
    "Buyer",
    "BuyerAPIKey",
    "CostTracking",
    "DataAccessLog",
    "DistributionGapReport",
    "FederatedUpdate",
    "Goal",
    "GoalContribution",
    "GoalMilestone",
    "GoalProgressEntry",
    "GoalRecord",
    "IntelligenceProduct",
    "Inventory",
    "JamiiInsightsReport",
    "Loan",
    "LoanROICheckin",
    "LoanRecord",
    "LoanRepayment",
    "LoanRepaymentV2",
    "MindsetLesson",
    "MindsetLessonProgress",
    "MindsetLessonV2",
    "ModelVersion",
    "PurposeVerification",
    "RichHabitScore",
    "RichHabitsScore",
    "ServerMetric",
    "SokoPulseReport",
    "Streak",
    "TaxBaseEstimation",
    "TitheRecord",
    "TitheReport",
    "Transaction",
    "User",
    "UserBadge",
    "UserEngagement",
    "UserLessonProgress",
    "UserLevel",
    "WorkerType",
]
