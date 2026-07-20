"""
Infrastructure Domain — /api/v1/infra/*

Aggregates:
    - Deployment Harness        (app.api.deployment)
    - Infrastructure            (app.api.infrastructure)
    - Infrastructure V2         (app.api.infrastructure_v2)
    - Evolution / Feedback      (app.api.evolution)
"""

from fastapi import APIRouter

from app.api.deployment import router as _deploy
from app.api.evolution import router as _evolution
from app.api.infrastructure import router as _infra
from app.api.infrastructure_v2 import router as _infra_v2

infra_router = APIRouter(tags=["Infrastructure"])
infra_router.include_router(_deploy)
infra_router.include_router(_infra)
infra_router.include_router(_infra_v2)
infra_router.include_router(_evolution)
