"""
Alama Score — Lender-Facing Credit Scoring API.

Provides a 0-1000 credit score for informal businesses,
queryable by banks, microfinance institutions, and fintech lenders.

Score factors:
  - Transaction consistency (20%)
  - Revenue growth (15%)
  - Profit margin (20%)
  - Customer retention (15%)
  - Inventory management (15%)
  - Business age (15%)

Built on top of the existing AlamaScoreService (300-850 range)
with additional lender-specific risk categorization and product matching.
"""

from .engine import AlamaScoreEngine
from .models import (
    AlamaScoreReport,
    LenderQueryRequest,
    LenderQueryResponse,
    RiskCategory,
    ScoreBand,
    ScoreComponent,
)

__all__ = [
    "AlamaScoreEngine",
    "AlamaScoreReport",
    "LenderQueryRequest",
    "LenderQueryResponse",
    "RiskCategory",
    "ScoreBand",
    "ScoreComponent",
]
