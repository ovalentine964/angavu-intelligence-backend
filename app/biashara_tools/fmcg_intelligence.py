"""
FMCG Intelligence — DeerFlow Tool Wrapper.

Wraps the existing FMCGIntelligenceService as a LangChain @tool for
DeerFlow agent orchestration. Provides informal channel tracking,
route-to-market optimization, and trade promotion ROI for FMCG companies.

DeerFlow agents invoke this tool when users ask about:
- Informal channel sales (dukas, kiosks, markets)
- Route-to-market optimization
- Trade promotion effectiveness
- Competitive pricing in informal channels
- Fleet utilization and distribution efficiency
"""

import json
import asyncio
from typing import Optional

from langchain.tools import tool


@tool("fmcg_intelligence", parse_docstring=True)
def fmcg_intelligence_tool(
    query_type: str,
    company: Optional[str] = None,
    product_category: Optional[str] = None,
    region: Optional[str] = None,
) -> str:
    """Get FMCG intelligence for informal market channels in East Africa.

    Use this tool when the user asks about FMCG performance in informal
    channels, route optimization, trade promotions, or competitive
    intelligence for companies like Pwani Oil, Unilever, Bidco, etc.

    Args:
        query_type: Type of intelligence — "channel_sales", "route_optimization", "promotion_roi", "competitive_pricing", "fleet_utilization".
        company: Company name (e.g., "pwani_oil", "unilever", "bidco"), or None for all.
        product_category: Product category filter (food, household, beauty, etc.), or None for all.
        region: Geographic region filter, or None for national.

    Returns:
        JSON string with FMCG intelligence data, insights, and recommendations.
    """
    try:
        from app.db.database import async_session_factory
        from app.services.intelligence.fmcg_intelligence import FMCGIntelligenceService

        async def _run():
            async with async_session_factory() as db:
                service = FMCGIntelligenceService(db)

                if query_type == "channel_sales":
                    result = await service.get_informal_channel_sales(
                        product_category=product_category,
                        region=region,
                    )
                elif query_type == "route_optimization":
                    result = await service.optimize_routes(
                        company=company,
                        region=region,
                    )
                elif query_type == "competitive_pricing":
                    result = await service.get_competitive_pricing(
                        product_category=product_category,
                        region=region,
                    )
                else:
                    result = await service.get_informal_channel_sales(
                        product_category=product_category,
                        region=region,
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
                "message": f"No FMCG data available for query_type={query_type}.",
            })

        return json.dumps(result, default=str, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "error": "service_error",
            "tool": "fmcg_intelligence",
            "message": str(e),
        })
