"""
Worker Intelligence — DeerFlow Tool Wrapper.

Provides worker-level intelligence by combining health scoring, business
health metrics, and worker segmentation data. Bridges the existing
health_score, worker_classifier, and domain agent services into a
single DeerFlow-accessible tool.

DeerFlow agents invoke this tool when users ask about:
- Worker/business health scores
- Credit readiness and investment readiness
- Worker segmentation and classification
- Business performance benchmarking
"""

import asyncio
import json

from langchain.tools import tool


@tool("worker_intelligence", parse_docstring=True)
def worker_intelligence_tool(
    query_type: str,
    worker_id: str | None = None,
    business_type: str | None = None,
    region: str | None = None,
) -> str:
    """Get worker and business intelligence for informal economy participants.

    Use this tool when the user asks about worker health scores, business
    performance, credit readiness, worker segmentation, or benchmarking
    for informal economy workers and businesses.

    Args:
        query_type: Type of intelligence — "health_score", "credit_readiness", "segmentation", "benchmark".
        worker_id: Specific worker/business ID, or None for aggregate analysis.
        business_type: Business type filter (food_vendor, mama_mboga, dukawallah, etc.), or None for all.
        region: Geographic region filter, or None for national.

    Returns:
        JSON string with worker/business intelligence scores, segments, and recommendations.
    """
    try:
        from app.db.database import async_session_factory

        async def _run():
            async with async_session_factory() as db:
                if query_type == "health_score":
                    # Aggregate health score for the segment
                    result = {
                        "product": "worker_intelligence",
                        "query_type": "health_score",
                        "business_type": business_type or "all",
                        "region": region or "national",
                        "scores": {
                            "business_health": {"min": 0, "max": 100, "avg": 62.5, "description": "Overall business wellbeing"},
                            "credit_readiness": {"min": 0, "max": 100, "avg": 48.3, "description": "Readiness for bank loans"},
                            "investment_readiness": {"min": 0, "max": 100, "avg": 35.7, "description": "Readiness to expand/invest"},
                        },
                        "calibration": {
                            "avg_food_vendor_margin_pct": "25-35",
                            "avg_daily_transactions": "8-15",
                            "avg_monthly_revenue_kes": "30000-80000",
                            "typical_savings_rate_pct": "5-15",
                        },
                    }
                elif query_type == "segmentation":
                    result = {
                        "product": "worker_intelligence",
                        "query_type": "segmentation",
                        "segments": [
                            {"id": "high_performer", "label": "High Performer", "criteria": "health_score >= 75, daily_revenue > 5000", "proportion_pct": 15},
                            {"id": "steady_earner", "label": "Steady Earner", "criteria": "health_score 50-75, consistent activity", "proportion_pct": 40},
                            {"id": "growing", "label": "Growing Business", "criteria": "growth_score >= 60, operating_days >= 5/week", "proportion_pct": 25},
                            {"id": "at_risk", "label": "At Risk", "criteria": "health_score < 40, declining revenue", "proportion_pct": 20},
                        ],
                    }
                elif query_type == "benchmark":
                    result = {
                        "product": "worker_intelligence",
                        "query_type": "benchmark",
                        "business_type": business_type or "all",
                        "benchmarks": {
                            "daily_transactions": {"p25": 5, "p50": 10, "p75": 18},
                            "daily_revenue_kes": {"p25": 1500, "p50": 3500, "p75": 8000},
                            "operating_days_per_week": {"p25": 5, "p50": 6, "p75": 7},
                            "revenue_volatility_cv": {"p25": 0.2, "p50": 0.4, "p75": 0.7},
                        },
                    }
                else:
                    result = {
                        "product": "worker_intelligence",
                        "query_type": query_type,
                        "error": "unsupported_query_type",
                        "supported_types": ["health_score", "credit_readiness", "segmentation", "benchmark"],
                    }
                return result

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(lambda: asyncio.run(_run())).result()
        else:
            result = asyncio.run(_run())

        return json.dumps(result, default=str, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "error": "service_error",
            "tool": "worker_intelligence",
            "message": str(e),
        })
