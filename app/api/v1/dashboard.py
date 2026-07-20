"""
Dashboard Domain — /api/v1/dashboard/*

Aggregates:
    - Dashboard                 (app.api.dashboard)
    - Long-Horizon Research     (app.api.long_horizon)
"""

from fastapi import APIRouter

from app.api.dashboard import router as _dashboard
from app.api.long_horizon import router as _research

dashboard_router = APIRouter(tags=["Dashboard & Research"])
dashboard_router.include_router(_dashboard)
dashboard_router.include_router(_research)
