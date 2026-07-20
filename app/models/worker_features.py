"""
Worker feature models — backward-compatibility re-exports.

The canonical model definitions now live in their own modules:
- app.models.goal      → Goal, GoalMilestone, GoalProgressEntry
- app.models.loan      → Loan, LoanRepayment, PurposeVerification
- app.models.mindset   → MindsetLesson, UserLessonProgress, RichHabitsScore, Affirmation
- app.models.tithe     → TitheRecord, TitheReport, AbundancePattern

This file re-exports them so existing imports continue to work
during the transition period. Remove these re-exports once all
callers have been updated.
"""

# Tithe — canonical definition
from app.models.tithe import TitheRecord  # noqa: F401

# Goals — V2 canonical (replaces GoalRecord/GoalContribution)
from app.models.goal import Goal, GoalMilestone, GoalProgressEntry  # noqa: F401

# Loans — V2 canonical (replaces LoanRecord/LoanRepayment/LoanROICheckin)
from app.models.loan import Loan, LoanRepayment, PurposeVerification  # noqa: F401

# Mindset — canonical (replaces old MindsetLesson/MindsetLessonProgress/RichHabitScore)
from app.models.mindset import (  # noqa: F401
    Affirmation,
    MindsetLesson,
    RichHabitsScore,
    UserLessonProgress,
)

# Backward-compat aliases for code that imports old class names.
# These map old names → new canonical classes so callers don't break.
GoalRecord = Goal
GoalContribution = GoalProgressEntry
LoanRecord = Loan
LoanROICheckin = PurposeVerification
MindsetLessonProgress = UserLessonProgress
