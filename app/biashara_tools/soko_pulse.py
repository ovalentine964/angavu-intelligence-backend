"""
Soko Pulse — DeerFlow Tool Wrapper.

Wraps the existing SokoPulseService as a LangChain @tool for DeerFlow
agent orchestration. Provides FMCG demand forecasting, price intelligence,
and seasonal analysis for Kenya's informal markets.

DeerFlow agents invoke this tool when users ask about:
- Market demand for specific products
- Price trends and forecasting
- Seasonal patterns in informal trade
- Consumer surplus and welfare analysis
"""

import json
import asyncio
from datetime import date, timedelta
from typing import Optional

from langchain.tools import tool


@tool("soko_pulse", parse_docstring=True)
def soko_pulse_tool(
    product_category: str,
    product_name: Optional[str] = None,
    region: Optional[str] = None,
    tier: str = "standard",
    lookback_days: int = 90,
) -> str:
    """Generate FMCG demand forecasting intelligence for informal markets.

    Use this tool when the user asks about market demand, price trends,
    seasonal patterns, or consumer behavior for products in Kenya's
    informal economy (dukas, kiosks, mama mbogas).

    Args:
        product_category: Product category to analyze (food, household, health, clothing, electronics, beauty, agriculture, services).
        product_name: Specific product name, or None for category-level analysis.
        region: Geographic region code (e.g., "KSM" for Kisumu, "NBI" for Nairobi), or None for national.
        tier: Analysis tier — "basic", "standard", "premium", or "enterprise". Higher tiers include forecasting and advanced analytics.
        lookback_days: Number of days of historical data to analyze (30-365).

    Returns:
        JSON string with demand forecast, price intelligence, seasonal patterns, and market insights.
    """
    try:
        from app.db.database import async_session_factory
        from app.services.intelligence.soko_pulse import SokoPulseService

        async def _run():
            async with async_session_factory() as db:
                service = SokoPulseService(db)
                period_end = date.today()
                period_start = period_end - timedelta(days=lookback_days)
                result = await service.generate_demand_forecast(
                    product_category=product_category,
                    product_name=product_name,
                    region=region,
                    period_start=period_start,
                    period_end=period_end,
                    tier=tier,
                )
                return result

        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(lambda: asyncio.run(_run())).result()
        else:
            result = asyncio.run(_run())

        if result is None:
            return json.dumps({
                "error": "insufficient_data",
                "message": f"Not enough data for {product_category} in {region or 'national'} market. Try a different category or region.",
            })

        return json.dumps(result, default=str, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "error": "service_error",
            "tool": "soko_pulse",
            "message": str(e),
        })
