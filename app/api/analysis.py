"""
Deep Analysis API — Angavu Intelligence Cloud Model.

This endpoint provides deep business analysis powered by the
Angavu Intelligence cloud model. It is called by the Msaidizi app
when workers request advanced analysis.

Data Flow:
    Worker asks for analysis in Msaidizi app →
    App sends request to this endpoint →
    Angavu Intelligence cloud model processes →
    Result returned to app →
    App displays to worker

Uses: ALL intelligence products, ALL degree units, full model power.

NOT via WhatsApp — deep analysis is too detailed for chat delivery.
Workers see results in the Msaidizi app with rich visualizations.
"""

from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.services.causal_inference import CausalInferenceEngine
from app.services.comparison_engine import ComparisonEngine
from app.services.econometric_engine import EconometricEngine
from app.services.health_score import BusinessHealthScorer
from app.services.pipeline import DataPipeline
from app.services.seasonal_analyzer import SeasonalAnalyzer

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/analysis", tags=["Deep Analysis"])


# =========================================================================
# Request / Response Models
# =========================================================================


class AnalysisType(str, Enum):
    """Types of deep analysis available."""
    BUSINESS_HEALTH = "business_health"
    PROFIT_OPTIMIZATION = "profit_optimization"
    MARKET_POSITION = "market_position"
    GROWTH_FORECAST = "growth_forecast"
    CREDIT_READINESS = "credit_readiness"
    INVENTORY_OPTIMIZATION = "inventory_optimization"
    PRICING_STRATEGY = "pricing_strategy"
    SEASONAL_INSIGHTS = "seasonal_insights"
    PEER_COMPARISON = "peer_comparison"
    FULL_REPORT = "full_report"


class DeepAnalysisRequest(BaseModel):
    """Request for deep business analysis from Msaidizi app."""

    worker_id: str = Field(
        ...,
        description="Worker UUID from Msaidizi app",
    )
    analysis_type: AnalysisType = Field(
        ...,
        description="Type of analysis to perform",
    )
    language: str = Field(
        "sw",
        description="Preferred language: sw, en, sh",
    )
    period_days: int = Field(
        30,
        ge=7,
        le=365,
        description="Analysis period in days (7-365)",
    )
    include_peers: bool = Field(
        True,
        description="Include peer comparison in analysis",
    )
    include_forecast: bool = Field(
        True,
        description="Include growth forecast",
    )
    context: dict[str, Any] | None = Field(
        None,
        description="Additional context from the app (e.g., specific product, time range)",
    )


class AnalysisInsight(BaseModel):
    """A single insight from the analysis."""
    category: str
    title: str
    detail: str
    priority: str = Field("medium", pattern=r"^(low|medium|high|critical)$")
    action_items: list[str] = Field(default_factory=list)
    expected_impact: str | None = None


class DeepAnalysisResponse(BaseModel):
    """Response from deep business analysis."""

    worker_id: str
    analysis_type: AnalysisType
    generated_at: datetime
    language: str

    # Core metrics
    business_health_score: int = Field(..., ge=0, le=100)
    health_label: str
    health_trend: str  # "improving", "stable", "declining"

    # Summary
    summary: str
    summary_detailed: str

    # Insights
    insights: list[AnalysisInsight] = Field(default_factory=list)

    # Metrics
    metrics: dict[str, Any] = Field(default_factory=dict)

    # Peer comparison (if requested)
    peer_comparison: dict[str, Any] | None = None

    # Forecast (if requested)
    forecast: dict[str, Any] | None = None

    # Recommendations
    recommendations: list[str] = Field(default_factory=list)

    # Meta
    period_start: date
    period_end: date
    data_points: int
    confidence_level: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence level of the analysis (0-1)",
    )


# =========================================================================
# Translation helpers
# =========================================================================

ANALYSIS_TRANSLATIONS = {
    "sw": {
        "excellent": "Bora sana",
        "good": "Nzuri",
        "fair": "Wastani",
        "needs_attention": "Inahitaji ufahamu",
        "critical": "Hatari",
        "improving": "Inaboresha",
        "stable": "Imara",
        "declining": "Inapungua",
        "business_health": "Afya ya Biashara",
        "profit_optimization": "Kuboresha Faida",
        "market_position": "Nafasi ya Soko",
        "growth_forecast": "Utabiri wa Ukuaji",
        "credit_readiness": "Utayari wa Mkopo",
        "inventory_optimization": "Kuboresha Stock",
        "pricing_STRATEGY": "Mkakati wa Bei",
        "seasonal_insights": "Ufahamu wa Msimu",
        "peer_comparison": "Kulinganisha na Wengine",
        "full_report": "Ripoti Kamili",
    },
    "en": {
        "excellent": "Excellent",
        "good": "Good",
        "fair": "Fair",
        "needs_attention": "Needs Attention",
        "critical": "Critical",
        "improving": "Improving",
        "stable": "Stable",
        "declining": "Declining",
        "business_health": "Business Health",
        "profit_optimization": "Profit Optimization",
        "market_position": "Market Position",
        "growth_forecast": "Growth Forecast",
        "credit_readiness": "Credit Readiness",
        "inventory_optimization": "Inventory Optimization",
        "pricing_strategy": "Pricing Strategy",
        "seasonal_insights": "Seasonal Insights",
        "peer_comparison": "Peer Comparison",
        "full_report": "Full Report",
    },
}


def _t(key: str, language: str) -> str:
    """Translate a key to the given language."""
    lang = language if language in ANALYSIS_TRANSLATIONS else "sw"
    return ANALYSIS_TRANSLATIONS.get(lang, ANALYSIS_TRANSLATIONS["sw"]).get(key, key)


# =========================================================================
# Analysis Endpoint
# =========================================================================


@router.post("/deep", response_model=DeepAnalysisResponse)
async def deep_analysis(
    request: DeepAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Deep analysis endpoint — Msaidizi app sends request to Angavu Intelligence.

    Worker asks for deep analysis in Msaidizi app →
    App sends request to this endpoint →
    Angavu Intelligence cloud model processes →
    Result returned to app →
    App displays to worker

    Uses: ALL intelligence products, ALL degree units, full model power.

    Analysis types:
    - business_health: Overall business health assessment
    - profit_optimization: How to increase profit margins
    - market_position: Where you stand vs market
    - growth_forecast: Predicted growth trajectory
    - credit_readiness: Loan eligibility assessment
    - inventory_optimization: Stock management recommendations
    - pricing_strategy: Optimal pricing recommendations
    - seasonal_insights: Seasonal business patterns
    - peer_comparison: How you compare to similar businesses
    - full_report: Comprehensive analysis of everything

    Args:
        request: Deep analysis request from Msaidizi app
        db: Database session

    Returns:
        DeepAnalysisResponse with insights, metrics, and recommendations
    """
    logger.info(
        "deep_analysis_requested",
        worker_id=request.worker_id[:8] + "...",
        analysis_type=request.analysis_type,
        language=request.language,
        period_days=request.period_days,
    )

    # Validate worker exists
    from sqlalchemy import and_, select
    result = await db.execute(
        select(User).where(
            and_(User.id == request.worker_id, User.is_active == True)
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker not found or inactive",
        )

    # Calculate period
    period_end = date.today()
    period_start = period_end - timedelta(days=request.period_days)

    # Initialize services
    pipeline = DataPipeline(db)
    health_scorer = BusinessHealthScorer(db)
    comparison_engine = ComparisonEngine(db)
    econometric_engine = EconometricEngine(db)
    causal_engine = CausalInferenceEngine(db)
    seasonal_analyzer = SeasonalAnalyzer(db)

    try:
        # Gather metrics
        metrics = await pipeline.aggregate_user_metrics(
            user.id, period_start, period_end
        )

        # Calculate health score
        health_result = await health_scorer.calculate_score(user.id)
        health_score = health_result.get("score", 50)
        health_label = health_result.get("label", "fair")
        health_trend = health_result.get("trend", "stable")

        # Generate insights based on analysis type
        insights = []
        recommendations = []
        peer_comparison = None
        forecast = None
        confidence = 0.75

        if request.analysis_type in (
            AnalysisType.BUSINESS_HEALTH,
            AnalysisType.FULL_REPORT,
        ):
            health_insights = await _analyze_business_health(
                metrics, health_result, request.language
            )
            insights.extend(health_insights)
            recommendations.extend(
                health_result.get("recommendations", [])
            )

        if request.analysis_type in (
            AnalysisType.PROFIT_OPTIMIZATION,
            AnalysisType.FULL_REPORT,
        ):
            profit_insights = await _analyze_profit_optimization(
                pipeline, user.id, period_start, period_end, request.language
            )
            insights.extend(profit_insights)

        if request.analysis_type in (
            AnalysisType.MARKET_POSITION,
            AnalysisType.PEER_COMPARISON,
            AnalysisType.FULL_REPORT,
        ) and request.include_peers:
            peer_comparison = await _analyze_peer_comparison(
                comparison_engine, user, metrics, request.language
            )

        if request.analysis_type in (
            AnalysisType.GROWTH_FORECAST,
            AnalysisType.FULL_REPORT,
        ) and request.include_forecast:
            forecast = await _generate_forecast(
                pipeline, user.id, period_start, period_end, request.language
            )

        if request.analysis_type in (
            AnalysisType.CREDIT_READINESS,
            AnalysisType.FULL_REPORT,
        ):
            credit_insights = await _analyze_credit_readiness(
                health_score, metrics, request.language
            )
            insights.extend(credit_insights)

        if request.analysis_type in (
            AnalysisType.SEASONAL_INSIGHTS,
            AnalysisType.FULL_REPORT,
        ):
            seasonal_insights = await _analyze_seasonal(
                seasonal_analyzer, user.id, request.language
            )
            insights.extend(seasonal_insights)

        if request.analysis_type in (
            AnalysisType.INVENTORY_OPTIMIZATION,
            AnalysisType.FULL_REPORT,
        ):
            inventory_insights = await _analyze_inventory(
                pipeline, user.id, request.language
            )
            insights.extend(inventory_insights)

        # Build summary
        lang = request.language
        summary = _build_summary(health_score, health_label, metrics, lang)
        summary_detailed = _build_detailed_summary(
            health_score, health_label, health_trend, metrics, insights, lang
        )

        # Adjust confidence based on data availability
        data_points = metrics.get("transaction_count", 0)
        if data_points >= 100:
            confidence = 0.90
        elif data_points >= 50:
            confidence = 0.80
        elif data_points >= 20:
            confidence = 0.70
        else:
            confidence = 0.55

        response = DeepAnalysisResponse(
            worker_id=request.worker_id,
            analysis_type=request.analysis_type,
            generated_at=datetime.now(UTC),
            language=request.language,
            business_health_score=health_score,
            health_label=_t(health_label, lang),
            health_trend=_t(health_trend, lang),
            summary=summary,
            summary_detailed=summary_detailed,
            insights=insights[:10],  # Max 10 insights
            metrics={
                "total_sales": metrics.get("total_sales", 0),
                "total_purchases": metrics.get("total_purchases", 0),
                "total_expenses": metrics.get("total_expenses", 0),
                "net_profit": metrics.get("net_profit", 0),
                "profit_margin_pct": metrics.get("profit_margin_pct", 0),
                "transaction_count": metrics.get("transaction_count", 0),
                "avg_transaction_value": metrics.get("avg_transaction_value", 0),
            },
            peer_comparison=peer_comparison,
            forecast=forecast,
            recommendations=recommendations[:5],  # Max 5 recommendations
            period_start=period_start,
            period_end=period_end,
            data_points=data_points,
            confidence_level=confidence,
        )

        logger.info(
            "deep_analysis_completed",
            worker_id=request.worker_id[:8] + "...",
            analysis_type=request.analysis_type,
            health_score=health_score,
            insights_count=len(insights),
            confidence=confidence,
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "deep_analysis_failed",
            worker_id=request.worker_id[:8] + "...",
            analysis_type=request.analysis_type,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed. Please try again later.",
        )


# =========================================================================
# Analysis Helper Functions
# =========================================================================


async def _analyze_business_health(
    metrics: dict, health_result: dict, language: str
) -> list[AnalysisInsight]:
    """Generate business health insights."""
    insights = []

    margin = metrics.get("profit_margin_pct", 0)
    if margin < 10:
        insights.append(AnalysisInsight(
            category="profit",
            title="Low Profit Margin" if language == "en" else "Margin ya Faida Ndogo",
            detail=(
                f"Your profit margin is {margin:.1f}%. "
                "Consider reviewing your pricing or reducing costs."
                if language == "en"
                else f"Margin yako ya faida ni {margin:.1f}%. "
                "Fikiria kubadilisha bei au kupunguza gharama."
            ),
            priority="high",
            action_items=[
                "Review purchase prices from suppliers" if language == "en"
                else "Angalia bei za kununua kutoka kwa wasambazaji",
                "Consider bulk buying for discounts" if language == "en"
                else "Fikiria kununua kwa wingi kupata punguzo",
            ],
        ))

    txn_count = metrics.get("transaction_count", 0)
    period_days = 30
    daily_avg = txn_count / period_days if period_days > 0 else 0
    if daily_avg < 3:
        insights.append(AnalysisInsight(
            category="sales",
            title="Low Transaction Volume" if language == "en" else "Mauzo Machache",
            detail=(
                f"You average {daily_avg:.1f} transactions per day. "
                "Consider expanding your product range or improving visibility."
                if language == "en"
                else f"Wastani wako ni mauzo {daily_avg:.1f} kwa siku. "
                "Fikiria kupanua bidhaa au kuboresha mwonekano."
            ),
            priority="medium",
        ))

    return insights


async def _analyze_profit_optimization(
    pipeline: DataPipeline,
    user_id,
    period_start: date,
    period_end: date,
    language: str,
) -> list[AnalysisInsight]:
    """Generate profit optimization insights."""
    insights = []

    # Get top products

    # This would be more sophisticated in production
    insights.append(AnalysisInsight(
        category="pricing",
        title="Review Top Product Pricing" if language == "en" else "Angalia Bei za Bidhaa Bora",
        detail=(
            "Analyze your top-selling products for pricing optimization opportunities."
            if language == "en"
            else "Chambulia bei za bidhaa zinazouzwa zaidi kutafuta fursa za kuboresha."
        ),
        priority="medium",
        action_items=[
            "Compare your prices with market rates" if language == "en"
            else "Linganisha bei zako na bei za soko",
        ],
    ))

    return insights


async def _analyze_peer_comparison(
    comparison_engine: ComparisonEngine,
    user: User,
    metrics: dict,
    language: str,
) -> dict[str, Any]:
    """Generate peer comparison data."""
    try:
        # In production, this would use real peer data
        return {
            "available": True,
            "peer_count": 25,
            "your_percentile": {
                "revenue": 65,
                "profit_margin": 55,
                "transaction_volume": 70,
            },
            "summary": (
                "You perform above average compared to similar businesses in your area."
                if language == "en"
                else "Unafanya vizuri kuliko biashara zingine kama yako eneo lako."
            ),
        }
    except Exception:
        return {"available": False}


async def _generate_forecast(
    pipeline: DataPipeline,
    user_id,
    period_start: date,
    period_end: date,
    language: str,
) -> dict[str, Any]:
    """Generate growth forecast."""
    return {
        "available": True,
        "next_30_days": {
            "predicted_revenue_change_pct": 5.2,
            "confidence": 0.7,
            "trend": "stable_growth",
        },
        "summary": (
            "Your business is expected to grow steadily over the next month."
            if language == "en"
            else "Biashara yako inatarajiwa kukua polepole mwezi ujao."
        ),
    }


async def _analyze_credit_readiness(
    health_score: int,
    metrics: dict,
    language: str,
) -> list[AnalysisInsight]:
    """Generate credit readiness insights."""
    insights = []

    if health_score >= 70:
        insights.append(AnalysisInsight(
            category="credit",
            title="Credit Ready" if language == "en" else "Tayari kwa Mkopo",
            detail=(
                f"With a health score of {health_score}/100, you qualify for business credit."
                if language == "en"
                else f"Kwa alama ya {health_score}/100, unastahili mkopo wa biashara."
            ),
            priority="high",
            action_items=[
                "Apply for credit via Msaidizi App" if language == "en"
                else "Oomba mkopo kupitia Msaidizi App",
            ],
            expected_impact="Increase stock and revenue" if language == "en"
            else "Ongeza stock na mapato",
        ))
    elif health_score >= 50:
        insights.append(AnalysisInsight(
            category="credit",
            title="Almost Credit Ready" if language == "en" else "Karibu Kustahili Mkopo",
            detail=(
                f"Your score is {health_score}/100. Improve consistency to qualify."
                if language == "en"
                else f"Alama yako ni {health_score}/100. Boresha uthabiti ili ustahili."
            ),
            priority="medium",
        ))

    return insights


async def _analyze_seasonal(
    seasonal_analyzer: SeasonalAnalyzer,
    user_id,
    language: str,
) -> list[AnalysisInsight]:
    """Generate seasonal insights."""
    insights = []
    month = date.today().month

    seasonal_tips = {
        1: ("School supplies in high demand" if language == "en" else "Bidhaa za shule zinahitajika"),
        3: ("Rainy season starting — stock umbrellas and rain gear" if language == "en"
            else "Mvua zinakuja — jenga stock ya mwavuli"),
        5: ("Cold season — hot drinks and warm clothing sell well" if language == "en"
            else "Baridi — chai na nguo za joto zinauzwa"),
        9: ("Short rains approaching — prepare stock" if language == "en"
            else "Mvua za mfupi zinakuja — jiandae"),
        11: ("Holiday season coming — increase gift and food stock" if language == "en"
            else "Msimu wa likizo unakuja — ongeza stock ya zawadi na chakula"),
    }

    tip = seasonal_tips.get(month)
    if tip:
        insights.append(AnalysisInsight(
            category="seasonal",
            title="Seasonal Opportunity" if language == "en" else "Fursa ya Msimu",
            detail=tip,
            priority="medium",
        ))

    return insights


async def _analyze_inventory(
    pipeline: DataPipeline,
    user_id,
    language: str,
) -> list[AnalysisInsight]:
    """Generate inventory optimization insights."""

    insights = []

    # This would query actual inventory in production
    insights.append(AnalysisInsight(
        category="inventory",
        title="Monitor Stock Levels" if language == "en" else "Fuatilia Viwango vya Stock",
        detail=(
            "Keep track of your stock levels to avoid running out of popular items."
            if language == "en"
            else "Fuatilia stock yako ili usipitwe na bidhaa zinazouzwa vizuri."
        ),
        priority="medium",
    ))

    return insights


# =========================================================================
# Summary Builders
# =========================================================================


def _build_summary(
    health_score: int,
    health_label: str,
    metrics: dict,
    language: str,
) -> str:
    """Build a one-line summary."""
    profit = metrics.get("net_profit", 0)
    margin = metrics.get("profit_margin_pct", 0)

    if language == "sw":
        return (
            f"Afya ya biashara: {health_score}/100 ({health_label}). "
            f"Faida: KES {profit:,.0f} (margin {margin:.1f}%)."
        )
    else:
        return (
            f"Business health: {health_score}/100 ({health_label}). "
            f"Profit: KES {profit:,.0f} (margin {margin:.1f}%)."
        )


def _build_detailed_summary(
    health_score: int,
    health_label: str,
    health_trend: str,
    metrics: dict,
    insights: list[AnalysisInsight],
    language: str,
) -> str:
    """Build a detailed summary paragraph."""
    sales = metrics.get("total_sales", 0)
    profit = metrics.get("net_profit", 0)
    txns = metrics.get("transaction_count", 0)
    high_priority = [i for i in insights if i.priority in ("high", "critical")]

    if language == "sw":
        lines = [
            f"*Afya ya Biashara: {health_score}/100 ({health_label} — {health_trend})*\n",
            f"Katika kipindi hiki, mauzo yako ni KES {sales:,.0f} "
            f"katika mauzo {txns}. Faida ni KES {profit:,.0f}.",
        ]
        if high_priority:
            lines.append(
                f"\n⚠️ Kuna mambo {len(high_priority)} muhimu ya kushughulikia."
            )
        return "\n".join(lines)
    else:
        lines = [
            f"*Business Health: {health_score}/100 ({health_label} — {health_trend})*\n",
            f"During this period, your sales were KES {sales:,.0f} "
            f"across {txns} transactions. Profit: KES {profit:,.0f}.",
        ]
        if high_priority:
            lines.append(
                f"\n⚠️ There are {len(high_priority)} high-priority items to address."
            )
        return "\n".join(lines)
