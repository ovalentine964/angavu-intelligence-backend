"""
Finance Domain — /api/v1/finance/*

Aggregates:
    - Biashara Sync Protocol    (app.api.biashara_sync)
    - Data Sync                 (app.api.sync)
    - Business Reports          (app.api.reports)
    - Formal Reports            (app.api.formal_reports)
"""

from fastapi import APIRouter

from app.api.biashara_sync import router as _biashara
from app.api.formal_reports import router as _formal
from app.api.reports import router as _reports
from app.api.sync import router as _sync

finance_router = APIRouter(tags=["Finance"])
finance_router.include_router(_biashara)
finance_router.include_router(_sync)
finance_router.include_router(_reports)
finance_router.include_router(_formal)
