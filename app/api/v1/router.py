"""V1 API router aggregation."""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    transactions,
    intelligence,
    credit,
    market,
    superagent,
    sync,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["Intelligence"])
api_router.include_router(credit.router, prefix="/credit", tags=["Credit Scoring"])
api_router.include_router(market.router, prefix="/market", tags=["Market Signals"])
api_router.include_router(superagent.router, prefix="/superagent", tags=["Superagent"])
api_router.include_router(sync.router, prefix="/sync", tags=["Device Sync"])
