"""
Explainability API — SHAP-based prediction explanations.

Provides Swahili explanations for model predictions, enabling
workers to understand WHY they received a particular score.

Endpoints:
    GET /api/v1/explain/alama/{business_id} — Explain Alama Score
    GET /api/v1/explain/loan/{worker_id} — Explain loan default risk
    GET /api/v1/explain/gdp/{county} — Explain GDP estimate

All explanations are delivered in Swahili for worker-facing channels
(WhatsApp, USSD, SMS) and English for institutional buyers.
"""

import hashlib
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.ml.explainer import (
    AlamaScoreExplainer,
    LoanExplainer,
    GDPExplainer,
    PredictionExplanation,
    SHAP_AVAILABLE,
)
from app.services.intelligence.alama_score import AlamaScoreService
from app.services.intelligence.loan_intelligence import LoanIntelligenceService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/explain", tags=["Explainability"])


# ---------------------------------------------------------------------------
# Singleton Explainers
# ---------------------------------------------------------------------------

_alama_explainer: Optional[AlamaScoreExplainer] = None
_loan_explainer: Optional[LoanExplainer] = None
_gdp_explainer: Optional[GDPExplainer] = None


def _get_alama_explainer() -> AlamaScoreExplainer:
    global _alama_explainer
    if _alama_explainer is None:
        _alama_explainer = AlamaScoreExplainer()
    return _alama_explainer


def _get_loan_explainer() -> LoanExplainer:
    global _loan_explainer
    if _loan_explainer is None:
        _loan_explainer = LoanExplainer()
    return _loan_explainer


def _get_gdp_explainer() -> GDPExplainer:
    global _gdp_explainer
    if _gdp_explainer is None:
        _gdp_explainer = GDPExplainer()
    return _gdp_explainer


# ---------------------------------------------------------------------------
# Alama Score Explanation
# ---------------------------------------------------------------------------

@router.get("/alama/{business_id}", summary="Explain Alama Score prediction")
async def explain_alama_score(
    business_id: str,
    lookback_days: int = Query(default=90, ge=30, le=365),
    tier: str = Query(default="basic", regex="^(basic|enhanced|full)$"),
    format: str = Query(default="json", regex="^(json|whatsapp)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Explain WHY a business received its Alama Score.

    Generates SHAP values for each feature, producing a Swahili
    explanation suitable for delivery via WhatsApp:

        "Ulipata Alama ya 720 kwa sababu: Unauza mara nyingi —
         5 mauzo kwa siku. Lakini, Biashara yako imepungua."

    Args:
        business_id: Anonymized business hash
        lookback_days: Analysis window (30-365)
        tier: Query tier (basic/enhanced/full)
        format: Response format (json or whatsapp)

    Returns:
        PredictionExplanation with Swahili summaries and feature attributions
    """
    start = time.time()

    # Get the actual Alama Score
    alama_service = AlamaScoreService(db)
    score_result = await alama_service.compute_score(
        business_id=business_id,
        lookback_days=lookback_days,
        query_tier=tier,
    )

    if not score_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hakuna data ya kutosha kwa biashara hii. Rekodi mauzo zaidi.",
        )

    # Extract features from score result
    components = score_result.get("components", {})
    activity = components.get("activity", 50)
    stability = components.get("stability", 50)
    growth = components.get("growth", 50)
    consistency = components.get("consistency", 50)
    diversity = components.get("diversity", 50)
    avg_daily_rev = score_result.get("avg_daily_revenue_kes", 0)
    avg_daily_txn = score_result.get("avg_daily_transactions", 0)
    operating_days = score_result.get("operating_days_per_week", 5) / 7.0
    revenue_vol = score_result.get("revenue_volatility", 0.3)
    unique_categories = len(set(score_result.get("risk_indicators", {}).get("risk_factors", [])))

    feature_values = np.array([
        activity, stability, growth, consistency, diversity,
        avg_daily_rev, avg_daily_txn, operating_days,
        revenue_vol, max(unique_categories, 1),
    ])

    predicted_score = score_result.get("alama_score", 525)
    score_band = score_result.get("score_band", "fair")

    # Generate explanation
    explainer = _get_alama_explainer()

    if format == "whatsapp":
        whatsapp_msg = explainer.explain_for_whatsapp(
            feature_values=feature_values,
            predicted_score=predicted_score,
            score_band=score_band,
            worker_name="Mfanyabiashara",
        )
        return {
            "format": "whatsapp",
            "message": whatsapp_msg,
            "score": predicted_score,
            "band": score_band,
            "shap_available": SHAP_AVAILABLE,
        }

    explanation = explainer.explain_alama_score(
        feature_values=feature_values,
        predicted_score=predicted_score,
        score_band=score_band,
    )

    result = explanation.to_dict()
    result["business_id"] = business_id
    result["alama_score"] = predicted_score
    result["score_band"] = score_band
    result["shap_available"] = SHAP_AVAILABLE
    result["duration_ms"] = round((time.time() - start) * 1000, 1)

    logger.info(
        "alama_score_explained",
        business=business_id,
        score=predicted_score,
        top_feature=explanation.feature_contributions[0].feature_name
        if explanation.feature_contributions
        else None,
    )

    return result


# ---------------------------------------------------------------------------
# Loan Default Risk Explanation
# ---------------------------------------------------------------------------

@router.get("/loan/{worker_id}", summary="Explain loan default risk")
async def explain_loan_default(
    worker_id: str,
    format: str = Query(default="json", regex="^(json|whatsapp)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Explain WHY a worker has a particular default risk.

    Generates SHAP values for loan risk features, producing
    Swahili explanations for workers.

    Args:
        worker_id: Worker UUID
        format: Response format (json or whatsapp)

    Returns:
        PredictionExplanation with Swahili risk explanations
    """
    start = time.time()

    loan_service = LoanIntelligenceService(db)
    risk_result = await loan_service.get_default_risk(worker_id)

    if not risk_result or risk_result.get("default_probability") is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hakuna data ya kutosha. Rekodi mauzo zaidi.",
        )

    # Extract features
    features = risk_result.get("features", {})
    feature_values = np.array([
        features.get("income_consistency", 0.5),
        features.get("income_volatility", 0.5),
        features.get("avg_monthly_income", 10000) / 50000,  # Normalize
        features.get("savings_rate", 0),
        features.get("active_days_ratio", 0.3),
        features.get("on_time_rate", 0.5),
        features.get("debt_to_income_ratio", 0.3),
        features.get("completion_rate", 0.5),
    ])

    default_prob = risk_result.get("default_probability", 0.15)

    explainer = _get_loan_explainer()
    explanation = explainer.explain_default_risk(feature_values, default_prob)

    if format == "whatsapp":
        lines = [
            f"📊 *Hatari ya Kutolipa Mkopo*",
            f"",
            f"Uwezekano: *{default_prob*100:.0f}*%",
            f"Kiwango: *{risk_result.get('risk_level', 'N/A')}*",
            f"",
        ]
        if explanation.top_negative:
            lines.append("⚠️ *Sababu Kuu:*")
            for fc in explanation.top_negative[:3]:
                lines.append(f"  • {fc.explanation_sw}")
        if explanation.top_positive:
            lines.append("")
            lines.append("✅ *Mambo Mazuri:*")
            for fc in explanation.top_positive[:2]:
                lines.append(f"  • {fc.explanation_sw}")
        lines.append("")
        lines.append(f"💡 *Ushauri:* {explanation.summary_sw}")
        return {"format": "whatsapp", "message": "\n".join(lines)}

    result = explanation.to_dict()
    result["worker_id"] = worker_id
    result["default_probability"] = default_prob
    result["risk_level"] = risk_result.get("risk_level")
    result["shap_available"] = SHAP_AVAILABLE
    result["duration_ms"] = round((time.time() - start) * 1000, 1)

    return result


# ---------------------------------------------------------------------------
# GDP Estimate Explanation
# ---------------------------------------------------------------------------

@router.get("/gdp/{county}", summary="Explain GDP estimate")
async def explain_gdp_estimate(
    county: str,
    period: str = Query(default="quarterly", regex="^(monthly|quarterly|annual)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Explain the GDP estimate for a county.

    Shows which factors contributed most to the GDP estimate,
    useful for institutional buyers (KNBS, CBK, Treasury).

    Args:
        county: County code or 'national'
        period: Analysis period

    Returns:
        Explanation of GDP estimate factors
    """
    from app.services.intelligence.gdp_estimator import GDPEstimatorService

    start = time.time()

    gdp_service = GDPEstimatorService(db)
    gdp_result = await gdp_service.estimate_gdp(county=county, period=period)

    if not gdp_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hakuna data ya kutosha kwa hesabu ya GDP.",
        )

    # Extract features for explanation
    sector_breakdown = gdp_result.get("sector_gdp_breakdown", {})
    total_output = gdp_result.get("total_gross_output_kes", 0)
    value_added_ratio = gdp_result.get("value_added_ratio", 0.4)
    total_businesses = gdp_result.get("total_businesses", 0)
    avg_daily_rev = gdp_result.get("avg_daily_revenue", 0)
    growth_pct = gdp_result.get("gdp_growth_pct", 0) or 0
    cycle_phase = gdp_result.get("business_cycle_phase", "indeterminate")

    # Map cycle phase to numeric
    phase_map = {"expansion": 1.0, "peak": 0.5, "contraction": -0.5, "trough": -1.0}
    cycle_value = phase_map.get(cycle_phase, 0.0)

    feature_values = np.array([
        total_output / 1e6,  # Normalize to millions
        value_added_ratio,
        len(sector_breakdown),
        total_businesses / 100,
        avg_daily_rev / 1000,
        growth_pct / 10,
        1.0,  # seasonal factor placeholder
        cycle_value,
    ])

    nominal_gdp = gdp_result.get("nominal_gdp_kes", 0)

    explainer = _get_gdp_explainer()
    explanation = explainer.explain(
        feature_values=feature_values,
        predicted_value=nominal_gdp / 1e6,  # In millions
        base_value=nominal_gdp / 1e6 * 0.8,
    )

    result = explanation.to_dict()
    result["county"] = county
    result["period"] = period
    result["nominal_gdp_kes"] = nominal_gdp
    result["business_cycle_phase"] = cycle_phase
    result["gdp_growth_pct"] = growth_pct
    result["shap_available"] = SHAP_AVAILABLE
    result["duration_ms"] = round((time.time() - start) * 1000, 1)

    return result
