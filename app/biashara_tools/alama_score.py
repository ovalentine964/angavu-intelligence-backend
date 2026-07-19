"""
Alama Score — DeerFlow Tool Wrapper.

Wraps the existing AlamaScoreService as a LangChain @tool for DeerFlow
agent orchestration. Provides transaction-based credit scoring (300-850)
for informal businesses with Heckman correction for selection bias.

DeerFlow agents invoke this tool when users ask about:
- Creditworthiness of informal businesses
- Default probability and risk assessment
- Credit limit recommendations
- Peer comparison and percentile ranking
"""

import asyncio
import json

from langchain.tools import tool


@tool("alama_score", parse_docstring=True)
def alama_score_tool(
    business_id: str,
    lookback_days: int = 90,
    query_tier: str = "basic",
) -> str:
    """Compute Alama credit score (300-850) for an informal business.

    Use this tool when the user asks about credit scoring, default risk,
    creditworthiness, or loan eligibility for a business in Kenya's
    informal economy.

    Args:
        business_id: Anonymized business identifier (HMAC-SHA256 hash of user_id).
        lookback_days: Analysis window in days (30-365). Longer windows give more stable scores.
        query_tier: Detail level — "basic" (score only), "enhanced" (with Bayesian + multivariate), or "full" (with causal inference + Monte Carlo).

    Returns:
        JSON string with Alama score, score band, risk indicators, and credit recommendation.
    """
    try:
        from app.db.database import async_session_factory
        from app.services.intelligence.alama_score import AlamaScoreService

        async def _run():
            async with async_session_factory() as db:
                service = AlamaScoreService(db)
                result = await service.compute_score(
                    business_id=business_id,
                    lookback_days=lookback_days,
                    query_tier=query_tier,
                    include_heckman=(query_tier in ("enhanced", "full")),
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
                "message": f"Not enough transaction data for business {business_id}. Need at least 20 transactions.",
            })

        return json.dumps(result, default=str, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "error": "service_error",
            "tool": "alama_score",
            "message": str(e),
        })
