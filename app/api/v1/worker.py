"""
Worker Domain — /api/v1/worker/*

Aggregates:
    - Worker Onboarding         (app.api.onboarding)
    - Worker Features           (app.api.worker_features)
    - Stickiness & Engagement   (app.api.stickiness)
    - Skills                    (app.api.skills)
    - Goal Planner              (app.api.v1.goals)
    - Loan Manager              (app.api.v1.loans)
    - Wealth Mindset            (app.api.v1.mindset)
    - Tithe Tracker             (app.api.v1.tithe)
"""

from fastapi import APIRouter

from app.api.onboarding import router as _onboarding
from app.api.skills import router as _skills
from app.api.stickiness import router as _stickiness
from app.api.v1.goals import router as _goals
from app.api.v1.loans import router as _loans
from app.api.v1.mindset import router as _mindset
from app.api.v1.tithe import router as _tithe
from app.api.worker_features import router as _worker

worker_router = APIRouter(tags=["Worker"])
worker_router.include_router(_onboarding)
worker_router.include_router(_worker)
worker_router.include_router(_stickiness)
worker_router.include_router(_skills)
worker_router.include_router(_goals)
worker_router.include_router(_loans)
worker_router.include_router(_mindset)
worker_router.include_router(_tithe)
