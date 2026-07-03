"""
MCP Intelligence Product Tools.

Exposes the 6 intelligence products as MCP-compatible tools:
- soko_pulse: FMCG demand forecasting
- biashara_pulse: Government MSME activity index
- alama_score: Credit scoring (300-850)
- jamii_insights: Community/NGO financial inclusion
- distribution_gap: FMCG distribution gap analysis
- fmcg_intelligence: FMCG market intelligence
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any, Dict, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.config import MCPToolDefinition, MCPToolParameter
from app.db.database import get_db

logger = structlog.get_logger(__name__)


# ── Tool Definitions ────────────────────────────────────────────────

soko_pulse_tool = MCPToolDefinition(
    name="soko_pulse",
    description=(
        "Soko Pulse — FMCG Demand Forecasting. Returns real-time demand patterns "
        "from Kenya's informal markets: what sells, where, when, seasonal trends, "
        "price intelligence, and demand forecasting with confidence intervals. "
        "Buyers: FMCG companies (Unilever, Coca-Cola, P&G, EABL)."
    ),
    parameters=[
        MCPToolParameter(
            name="product_category",
            type="string",
            description="Product category (food, household, beverages, personal_care, etc.)",
            required=True,
        ),
        MCPToolParameter(
            name="product_name",
            type="string",
            description="Specific product name, or omit for category-level analysis",
            required=False,
        ),
        MCPToolParameter(
            name="region",
            type="string",
            description="Geographic region (county name, 'national', or omit for all)",
            required=False,
        ),
        MCPToolParameter(
            name="period_start",
            type="string",
            description="Analysis period start date (YYYY-MM-DD)",
            required=False,
        ),
        MCPToolParameter(
            name="period_end",
            type="string",
            description="Analysis period end date (YYYY-MM-DD)",
            required=False,
        ),
        MCPToolParameter(
            name="tier",
            type="string",
            description="Intelligence tier",
            required=False,
            default="standard",
            enum=["standard", "premium", "enterprise"],
        ),
    ],
    category="intelligence",
)

biashara_pulse_tool = MCPToolDefinition(
    name="biashara_pulse",
    description=(
        "Angavu Pulse — Government MSME Activity Index. Provides economic "
        "activity heatmaps: activity indices (0-100) by county/sub-county, "
        "business formation/destruction rates, sector breakdown, employment estimates. "
        "Buyers: KNBS, CBK, county governments."
    ),
    parameters=[
        MCPToolParameter(
            name="region",
            type="string",
            description="County or sub-county name, or 'national' for aggregate",
            required=True,
        ),
        MCPToolParameter(
            name="period_start",
            type="string",
            description="Period start date (YYYY-MM-DD)",
            required=False,
        ),
        MCPToolParameter(
            name="period_end",
            type="string",
            description="Period end date (YYYY-MM-DD)",
            required=False,
        ),
    ],
    category="intelligence",
)

alama_score_tool = MCPToolDefinition(
    name="alama_score",
    description=(
        "Alama Score — Transaction-Based Credit Scoring. Computes credit scores "
        "(300-850) from transaction history with activity, stability, growth, "
        "consistency, and diversity components. Supports Heckman correction. "
        "Buyers: Banks, MFIs, insurance companies."
    ),
    parameters=[
        MCPToolParameter(
            name="business_id",
            type="string",
            description="Business/user ID to score",
            required=True,
        ),
        MCPToolParameter(
            name="lookback_days",
            type="number",
            description="Number of days of history to analyze (30-365)",
            required=False,
            default=90,
        ),
        MCPToolParameter(
            name="query_tier",
            type="string",
            description="Query tier affecting detail and pricing",
            required=False,
            default="basic",
            enum=["basic", "enhanced", "full"],
        ),
        MCPToolParameter(
            name="include_heckman_correction",
            type="boolean",
            description="Apply Heckman selection-corrected scoring",
            required=False,
            default=False,
        ),
    ],
    category="intelligence",
)

jamii_insights_tool = MCPToolDefinition(
    name="jamii_insights",
    description=(
        "Jamii Insights — NGO Financial Inclusion Intelligence. Provides "
        "demographic-level inclusion metrics: financial inclusion index, "
        "digital payment adoption, savings/credit access, program impact "
        "measurement. Buyers: World Bank, USAID, DFID, NGOs."
    ),
    parameters=[
        MCPToolParameter(
            name="region",
            type="string",
            description="Region or 'national'",
            required=True,
        ),
        MCPToolParameter(
            name="demographic_segment",
            type="string",
            description="Demographic segment (youth, women, rural, urban, etc.)",
            required=False,
        ),
        MCPToolParameter(
            name="period_start",
            type="string",
            description="Period start (YYYY-MM-DD)",
            required=False,
        ),
        MCPToolParameter(
            name="period_end",
            type="string",
            description="Period end (YYYY-MM-DD)",
            required=False,
        ),
        MCPToolParameter(
            name="program_name",
            type="string",
            description="Specific program to measure impact for",
            required=False,
        ),
    ],
    category="intelligence",
)

distribution_gap_tool = MCPToolDefinition(
    name="distribution_gap",
    description=(
        "Distribution Gap Analysis — FMCG Market Coverage. Identifies where "
        "products are NOT reaching, underserved markets, revenue potential "
        "of gap markets, expansion recommendations with ROI estimates. "
        "Buyers: FMCG distribution companies."
    ),
    parameters=[
        MCPToolParameter(
            name="product_category",
            type="string",
            description="Product category to analyze",
            required=True,
        ),
        MCPToolParameter(
            name="product_name",
            type="string",
            description="Specific product name",
            required=False,
        ),
        MCPToolParameter(
            name="region",
            type="string",
            description="Region to focus analysis on",
            required=False,
        ),
        MCPToolParameter(
            name="period_start",
            type="string",
            description="Analysis period start (YYYY-MM-DD)",
            required=False,
        ),
        MCPToolParameter(
            name="period_end",
            type="string",
            description="Analysis period end (YYYY-MM-DD)",
            required=False,
        ),
    ],
    category="intelligence",
)

fmcg_intelligence_tool = MCPToolDefinition(
    name="fmcg_intelligence",
    description=(
        "FMCG Intelligence — Comprehensive market intelligence for fast-moving "
        "consumer goods. Combines demand forecasting, pricing intelligence, "
        "distribution analysis, and competitive landscape for FMCG companies "
        "operating in Kenya's informal markets."
    ),
    parameters=[
        MCPToolParameter(
            name="company_id",
            type="string",
            description="FMCG company identifier",
            required=True,
        ),
        MCPToolParameter(
            name="product_categories",
            type="array",
            description="List of product categories to analyze",
            required=False,
        ),
        MCPToolParameter(
            name="region",
            type="string",
            description="Geographic scope",
            required=False,
        ),
        MCPToolParameter(
            name="analysis_type",
            type="string",
            description="Type of analysis",
            required=False,
            default="comprehensive",
            enum=["demand", "pricing", "distribution", "comprehensive"],
        ),
    ],
    category="intelligence",
)

# Registry
INTELLIGENCE_TOOLS = [
    soko_pulse_tool,
    biashara_pulse_tool,
    alama_score_tool,
    jamii_insights_tool,
    distribution_gap_tool,
    fmcg_intelligence_tool,
]


# ── Tool Handlers ───────────────────────────────────────────────────


def _parse_date(val: Optional[str]) -> Optional[date]:
    """Parse ISO date string."""
    if not val:
        return None
    return date.fromisoformat(val)


async def handle_intelligence_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    buyer_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    Dispatch an intelligence tool call to the appropriate service.

    Args:
        tool_name: One of the intelligence tool names.
        arguments: Tool call arguments.
        buyer_id: Authenticated buyer ID.
        db: Database session.

    Returns:
        Tool result dictionary.
    """
    start = time.time()

    try:
        if tool_name == "soko_pulse":
            from app.services.intelligence.soko_pulse import SokoPulseService

            service = SokoPulseService(db)
            result = await service.generate_demand_forecast(
                product_category=arguments["product_category"],
                product_name=arguments.get("product_name"),
                region=arguments.get("region"),
                period_start=_parse_date(arguments.get("period_start")),
                period_end=_parse_date(arguments.get("period_end")),
                tier=arguments.get("tier", "standard"),
                buyer_id=buyer_id,
            )

        elif tool_name == "biashara_pulse":
            from app.services.intelligence.biashara_pulse import BiasharaPulseService

            service = BiasharaPulseService(db)
            result = await service.generate_activity_index(
                region=arguments["region"],
                period_start=_parse_date(arguments.get("period_start")),
                period_end=_parse_date(arguments.get("period_end")),
                buyer_id=buyer_id,
            )

        elif tool_name == "alama_score":
            from app.services.intelligence.alama_score import AlamaScoreService

            service = AlamaScoreService(db)
            result = await service.compute_score(
                business_id=arguments["business_id"],
                lookback_days=arguments.get("lookback_days", 90),
                query_tier=arguments.get("query_tier", "basic"),
                include_heckman=arguments.get("include_heckman_correction", False),
                buyer_id=buyer_id,
            )

        elif tool_name == "jamii_insights":
            from app.services.intelligence.jamii_insights import JamiiInsightsService

            service = JamiiInsightsService(db)
            result = await service.generate_inclusion_report(
                region=arguments["region"],
                demographic_segment=arguments.get("demographic_segment"),
                period_start=_parse_date(arguments.get("period_start")),
                period_end=_parse_date(arguments.get("period_end")),
                program_name=arguments.get("program_name"),
                buyer_id=buyer_id,
            )

        elif tool_name == "distribution_gap":
            from app.services.intelligence.distribution_gap import DistributionGapService

            service = DistributionGapService(db)
            result = await service.analyze_gaps(
                product_category=arguments["product_category"],
                product_name=arguments.get("product_name"),
                region=arguments.get("region"),
                period_start=_parse_date(arguments.get("period_start")),
                period_end=_parse_date(arguments.get("period_end")),
                buyer_id=buyer_id,
            )

        elif tool_name == "fmcg_intelligence":
            from app.services.intelligence.fmcg_intelligence import FMCGIntelligenceService

            service = FMCGIntelligenceService(db)
            analysis_type = arguments.get("analysis_type", "comprehensive")

            # Dispatch to the appropriate FMCG analysis method
            if analysis_type == "demand" or analysis_type == "comprehensive":
                result = await service.get_informal_channel_sales(
                    company_id=arguments["company_id"],
                    region=arguments.get("region"),
                )
            elif analysis_type == "distribution":
                result = await service.get_distribution_gaps(
                    company_id=arguments["company_id"],
                    region=arguments.get("region"),
                )
            elif analysis_type == "pricing":
                result = await service.get_competitive_pricing(
                    company_id=arguments["company_id"],
                    region=arguments.get("region"),
                )
            else:
                result = await service.get_informal_channel_sales(
                    company_id=arguments["company_id"],
                    region=arguments.get("region"),
                )

        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown intelligence tool: {tool_name}"}],
            }

        elapsed = time.time() - start

        if result is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "Insufficient data for analysis (k-anonymity not met or no data available)"}],
            }

        logger.info(
            "mcp_intelligence_tool_executed",
            tool=tool_name,
            buyer_id=buyer_id,
            elapsed_ms=round(elapsed * 1000, 1),
        )

        return {
            "content": [{"type": "text", "text": _format_result(result)}],
            "metadata": {
                "tool": tool_name,
                "buyer_id": buyer_id,
                "elapsed_ms": round(elapsed * 1000, 1),
            },
        }

    except Exception as e:
        logger.error("mcp_intelligence_tool_error", tool=tool_name, error=str(e), exc_info=True)
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Tool execution error: {str(e)}"}],
        }


def _format_result(result: Any) -> str:
    """Format a tool result as readable text."""
    if isinstance(result, dict):
        import json
        return json.dumps(result, indent=2, default=str)
    return str(result)
