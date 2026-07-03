"""
Distribution Gap — DeerFlow Tool Wrapper.

Wraps the existing DistributionGapService as a LangChain @tool for
DeerFlow agent orchestration. Identifies underserved markets and
expansion opportunities for FMCG distribution.

DeerFlow agents invoke this tool when users ask about:
- Where products are NOT reaching
- Market coverage and penetration gaps
- Expansion recommendations with ROI estimates
- Distribution network optimization
"""

import json
import asyncio
from typing import Optional

from langchain.tools import tool


@tool("distribution_gap", parse_docstring=True)
def distribution_gap_tool(
    product_category: str,
    region: Optional[str] = None,
    tier: str = "standard",
) -> str:
    """Analyze distribution gaps and identify underserved markets for FMCG products.

    Use this tool when the user asks about market coverage gaps, where to
    expand distribution, underserved regions, or penetration analysis for
    products in Kenya's informal economy.

    Args:
        product_category: Product category to analyze (food, household, health, etc.).
        region: Geographic region to focus on, or None for national analysis.
        tier: Analysis tier — "basic", "standard", or "premium". Premium includes HHI and contestable market analysis.

    Returns:
        JSON string with coverage gaps, underserved markets, expansion recommendations, and ROI estimates.
    """
    try:
        from app.db.database import async_session_factory
        from app.services.intelligence.distribution_gap import DistributionGapService

        async def _run():
            async with async_session_factory() as db:
                service = DistributionGapService(db)
                result = await service.analyze_distribution_gaps(
                    product_category=product_category,
                    region=region,
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
                "message": f"Not enough distribution data for {product_category} in {region or 'national'} market.",
            })

        return json.dumps(result, default=str, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "error": "service_error",
            "tool": "distribution_gap",
            "message": str(e),
        })
