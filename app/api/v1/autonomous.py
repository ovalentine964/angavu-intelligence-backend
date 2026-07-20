"""
Autonomous Domain — /api/v1/revenue-ops/*

Aggregates:
    - Revenue Operations        (app.autonomous.api.router)

The autonomous router prefix was corrected from "/api/v1/revenue-ops"
to "/revenue-ops" so it composes correctly under the v1_router at
/api/v1. Final path: /api/v1/revenue-ops/*.
"""

from fastapi import APIRouter

from app.autonomous.api.router import router as _autonomous

autonomous_router = APIRouter(tags=["Revenue Operations"])
autonomous_router.include_router(_autonomous)
