"""
Intelligence Domain — /api/v1/intelligence/*

Aggregates:
    - Intelligence API          (app.api.intelligence)
    - Intelligence Products     (app.api.intelligence_products)
    - Phase 1 Intelligence      (app.api.phase1_intelligence)
    - Deep Analysis             (app.api.analysis)
    - Explainability (SHAP)     (app.api.explain)
    - FMCG Intelligence         (app.api.fmcg)
    - Dialect Dictionary        (app.api.dialect_dictionary)
    - Federated Learning        (app.api.federated_learning)
    - FL Aggregator             (app.api.fl_aggregator)
"""

from fastapi import APIRouter

from app.api.analysis import router as _analysis
from app.api.dialect_dictionary import router as _dialect
from app.api.explain import router as _explain
from app.api.federated_learning import router as _fl
from app.api.fl_aggregator import router as _fl_agg
from app.api.fmcg import router as _fmcg
from app.api.intelligence import router as _intel
from app.api.intelligence_products import router as _intel_products
from app.api.phase1_intelligence import router as _phase1

intelligence_router = APIRouter(tags=["Intelligence"])
intelligence_router.include_router(_intel)
intelligence_router.include_router(_intel_products)
intelligence_router.include_router(_phase1)
intelligence_router.include_router(_analysis)
intelligence_router.include_router(_explain)
intelligence_router.include_router(_fmcg)
intelligence_router.include_router(_dialect)
intelligence_router.include_router(_fl)
intelligence_router.include_router(_fl_agg)
