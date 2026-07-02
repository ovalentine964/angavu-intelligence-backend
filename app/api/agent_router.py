"""
Agent Router API — Multi-agent architecture endpoints.

Endpoints:
    POST /api/v1/agents/classify          — Classify worker type
    GET  /api/v1/agents/{worker_type}/insights  — Get domain insights
    GET  /api/v1/agents/{worker_type}/recommendations — Get recommendations
    GET  /api/v1/agents/catalog           — List all agents and their capabilities

These endpoints bridge the Android app's domain agents with the
backend's transaction data and analytics engine.
"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.db.database import get_db
from app.models.agent_models import (
    AgentInsight,
    AgentRecommendation,
    ClassifyRequest,
    ClassifyResponse,
    InsightsResponse,
    RecommendationsResponse,
    WorkerType,
)
from app.models.transaction import Transaction
from app.services.agents import (
    AgricultureAgent,
    DigitalAgent,
    ManufacturingAgent,
    RetailAgent,
    ServiceAgent,
    TransportAgent,
)
from app.services.worker_classifier import get_worker_classifier

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


# ── Agent Registry ──────────────────────────────────────────────────

AGENT_REGISTRY = {
    WorkerType.TRANSPORT: TransportAgent(),
    WorkerType.TRADER: RetailAgent(),
    WorkerType.AGRICULTURE: AgricultureAgent(),
    WorkerType.SERVICE: ServiceAgent(),
    WorkerType.DIGITAL: DigitalAgent(),
    WorkerType.MANUFACTURING: ManufacturingAgent(),
}


def _get_agent(worker_type: str):
    """Get domain agent for worker type."""
    try:
        wt = WorkerType(worker_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid worker type: {worker_type}. "
                   f"Valid types: {[t.value for t in WorkerType]}",
        )
    agent = AGENT_REGISTRY.get(wt)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"No agent available for worker type: {worker_type}",
        )
    return agent, wt


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/classify", response_model=ClassifyResponse)
async def classify_worker(request: ClassifyRequest):
    """
    Classify a worker's type based on transaction patterns.

    Analyzes transaction history to determine which domain agent(s)
    should be activated. Supports multi-type classification.

    If no transactions are provided, fetches from the database.
    """
    transactions = request.transactions

    if not transactions:
        # Fetch from database
        async for db in get_db():
            result = await db.execute(
                select(Transaction)
                .where(Transaction.user_id == request.user_id)
                .order_by(Transaction.timestamp.desc())
                .limit(500)
            )
            rows = result.scalars().all()
            transactions = [
                {
                    "item": t.item,
                    "transaction_type": t.transaction_type,
                    "amount": t.amount,
                    "quantity": t.quantity,
                    "profit": t.profit,
                    "item_category": t.item_category,
                    "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                    "customer_phone_hash": t.customer_phone_hash,
                    "recorded_via": t.recorded_via,
                }
                for t in rows
            ]

    classifier = get_worker_classifier()
    result = classifier.classify(transactions or [])

    return ClassifyResponse(
        user_id=request.user_id,
        primary_type=WorkerType(result["primary_type"]),
        types=result["types"],
        is_multi_type=result["is_multi_type"],
    )


@router.get("/catalog")
async def list_agents():
    """
    List all available domain agents and their capabilities.

    Returns the full catalog of Tier 2 domain agents with their
    supported worker types and capabilities.
    """
    catalog = []
    for wt, agent in AGENT_REGISTRY.items():
        catalog.append({
            "agent_name": agent.name,
            "worker_type": wt.value,
            "tier": agent.tier,
            "role": agent.role,
            "worker_types": agent.worker_types,
        })

    return {
        "agents": catalog,
        "total": len(catalog),
        "architecture": {
            "tier_1_core": 5,
            "tier_2_domain": 6,
            "tier_3_utility": 5,
            "total_agents": 16,
        },
    }


@router.get("/{worker_type}/insights", response_model=InsightsResponse)
async def get_insights(
    worker_type: str,
    user_id: str = Query(..., description="User ID to analyze"),
    period_days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
):
    """
    Get domain-specific insights for a worker type.

    Fetches the user's transactions, runs them through the appropriate
    domain agent, and returns structured insights.
    """
    agent, wt = _get_agent(worker_type)

    # Fetch transactions from database
    async for db in get_db():
        result = await db.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.timestamp.desc())
            .limit(1000)
        )
        rows = result.scalars().all()

    transactions = [
        {
            "item": t.item,
            "transaction_type": t.transaction_type,
            "amount": t.amount,
            "quantity": t.quantity,
            "unit_price": t.unit_price,
            "profit": t.profit,
            "item_category": t.item_category,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "customer_phone_hash": t.customer_phone_hash,
            "recorded_via": t.recorded_via,
        }
        for t in rows
    ]

    if not transactions:
        return InsightsResponse(
            user_id=user_id,
            worker_type=wt,
            agent_name=agent.name,
            period_days=period_days,
            insights=[],
            analysis={"message": "No transactions found for analysis"},
        )

    # Run analysis through domain agent
    if wt == WorkerType.TRANSPORT:
        analysis = agent.analyze_trips(transactions, period_days)
    elif wt == WorkerType.TRADER:
        analysis = agent.analyze_sales(transactions, period_days=period_days)
    elif wt == WorkerType.AGRICULTURE:
        analysis = agent.analyze_farm(transactions, period_days)
    elif wt == WorkerType.SERVICE:
        analysis = agent.analyze_services(transactions, period_days)
    elif wt == WorkerType.DIGITAL:
        analysis = agent.analyze_income(transactions, period_days)
    elif wt == WorkerType.MANUFACTURING:
        analysis = agent.analyze_production(transactions, period_days)
    else:
        analysis = {}

    # Extract key insights from analysis
    insights = _extract_insights(analysis, agent.name, wt)

    return InsightsResponse(
        user_id=user_id,
        worker_type=wt,
        agent_name=agent.name,
        period_days=period_days,
        insights=insights,
        analysis=analysis,
    )


@router.get("/{worker_type}/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    worker_type: str,
    user_id: str = Query(..., description="User ID to analyze"),
    language: str = Query("en", description="Language: en or sw"),
    period_days: int = Query(30, ge=1, le=365, description="Analysis period"),
):
    """
    Get domain-specific recommendations for a worker type.

    Runs analysis and generates actionable recommendations
    in the worker's preferred language.
    """
    agent, wt = _get_agent(worker_type)

    # Fetch transactions
    async for db in get_db():
        result = await db.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.timestamp.desc())
            .limit(1000)
        )
        rows = result.scalars().all()

    transactions = [
        {
            "item": t.item,
            "transaction_type": t.transaction_type,
            "amount": t.amount,
            "quantity": t.quantity,
            "unit_price": t.unit_price,
            "profit": t.profit,
            "item_category": t.item_category,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "customer_phone_hash": t.customer_phone_hash,
            "recorded_via": t.recorded_via,
        }
        for t in rows
    ]

    if not transactions:
        return RecommendationsResponse(
            user_id=user_id,
            worker_type=wt,
            agent_name=agent.name,
            recommendations=[],
            language=language,
        )

    # Run analysis
    if wt == WorkerType.TRANSPORT:
        analysis = agent.analyze_trips(transactions, period_days)
    elif wt == WorkerType.TRADER:
        analysis = agent.analyze_sales(transactions, period_days=period_days)
    elif wt == WorkerType.AGRICULTURE:
        analysis = agent.analyze_farm(transactions, period_days)
    elif wt == WorkerType.SERVICE:
        analysis = agent.analyze_services(transactions, period_days)
    elif wt == WorkerType.DIGITAL:
        analysis = agent.analyze_income(transactions, period_days)
    elif wt == WorkerType.MANUFACTURING:
        analysis = agent.analyze_production(transactions, period_days)
    else:
        analysis = {}

    # Generate recommendations
    raw_recs = agent.get_recommendations(analysis, language)

    recommendations = [
        AgentRecommendation(
            agent_name=agent.name,
            worker_type=wt,
            category=r.get("category", "general"),
            title=r.get("title", ""),
            message=r.get("message", ""),
            priority=r.get("priority", "medium"),
            language=language,
        )
        for r in raw_recs
    ]

    return RecommendationsResponse(
        user_id=user_id,
        worker_type=wt,
        agent_name=agent.name,
        recommendations=recommendations,
        language=language,
    )


# ── Helpers ─────────────────────────────────────────────────────────


def _extract_insights(
    analysis: dict, agent_name: str, worker_type: WorkerType
) -> list[AgentInsight]:
    """Extract key insights from analysis data."""
    insights = []

    # Common metrics
    for key, title, category, metric in [
        ("total_earnings", "Total Earnings", "earnings", "KES"),
        ("total_revenue", "Total Revenue", "revenue", "KES"),
        ("total_profit", "Total Profit", "profitability", "KES"),
        ("total_income", "Total Income", "income", "KES"),
        ("net_income", "Net Income", "income", "KES"),
        ("trip_count", "Total Trips", "activity", "trips"),
        ("sale_count", "Total Sales", "activity", "sales"),
        ("job_count", "Total Jobs", "activity", "jobs"),
        ("order_count", "Total Orders", "activity", "orders"),
    ]:
        if key in analysis and analysis[key]:
            insights.append(AgentInsight(
                agent_name=agent_name,
                worker_type=worker_type,
                category=category,
                title=title,
                value=analysis[key],
                metric=metric,
            ))

    # Margin
    for key in ["avg_margin_pct", "profit_margin_pct", "gross_margin_pct"]:
        if key in analysis and analysis[key]:
            insights.append(AgentInsight(
                agent_name=agent_name,
                worker_type=worker_type,
                category="profitability",
                title="Profit Margin",
                value=analysis[key],
                metric="%",
            ))
            break

    # Fuel cost (transport)
    if "fuel_cost_pct" in analysis:
        insights.append(AgentInsight(
            agent_name=agent_name,
            worker_type=worker_type,
            category="fuel",
            title="Fuel Cost %",
            value=analysis["fuel_cost_pct"],
            metric="%",
        ))

    # Client retention (service/digital)
    client_data = analysis.get("client_analysis", {})
    if client_data.get("retention_rate_pct"):
        insights.append(AgentInsight(
            agent_name=agent_name,
            worker_type=worker_type,
            category="clients",
            title="Client Retention",
            value=client_data["retention_rate_pct"],
            metric="%",
        ))

    # Income stability (digital)
    smoothing = analysis.get("income_smoothing", {})
    if smoothing.get("stability_score"):
        insights.append(AgentInsight(
            agent_name=agent_name,
            worker_type=worker_type,
            category="stability",
            title="Income Stability Score",
            value=smoothing["stability_score"],
            metric="score",
        ))

    # Waste rate (manufacturing)
    waste = analysis.get("waste_analysis", {})
    if waste.get("waste_rate_pct"):
        insights.append(AgentInsight(
            agent_name=agent_name,
            worker_type=worker_type,
            category="waste",
            title="Material Waste Rate",
            value=waste["waste_rate_pct"],
            metric="%",
        ))

    return insights
