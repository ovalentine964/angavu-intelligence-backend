"""
Tests for the Financial Intelligence Module.

Tests market intelligence, FMCG analytics, and financial analysis.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.superagent.financial.module import FinancialModule


@pytest.fixture
def financial_module():
    return FinancialModule()


class TestFinancialModuleInit:
    """Test initialization."""

    def test_default_state(self, financial_module):
        assert financial_module._soko_pulse is None
        assert financial_module._fmcg is None
        assert financial_module._distribution_gap is None
        assert financial_module._initialized is False


class TestFinancialModuleObserve:
    """Test observation phase — gathering financial context."""

    @pytest.mark.asyncio
    async def test_observe_with_transactions(self, financial_module):
        data = {
            "transactions": [
                {"amount": 500, "type": "SALE"},
                {"amount": 1500, "type": "SALE"},
            ]
        }
        result = await financial_module.observe(data)

        assert result["module"] == "financial"
        assert len(result["data_points"]) == 1
        dp = result["data_points"][0]
        assert dp["type"] == "transaction_summary"
        assert dp["count"] == 2
        assert dp["total_volume"] == 2000
        assert dp["avg_amount"] == 1000

    @pytest.mark.asyncio
    async def test_observe_empty_data(self, financial_module):
        result = await financial_module.observe({})
        assert result["module"] == "financial"
        assert result["data_points"] == []

    @pytest.mark.asyncio
    async def test_observe_zero_amounts(self, financial_module):
        data = {"transactions": [{"amount": 0}, {"amount": 0}]}
        result = await financial_module.observe(data)
        # Zero amounts are filtered out
        assert result["data_points"] == []


class TestFinancialModuleOrient:
    """Test orientation phase — analyzing financial situation."""

    @pytest.mark.asyncio
    async def test_orient_default_stable(self, financial_module):
        result = await financial_module.orient({"enrichment": {"data_points": []}})

        assert result["market_condition"] == "stable"
        assert result["trend"] == "neutral"
        assert result["risk_level"] == "low"

    @pytest.mark.asyncio
    async def test_orient_high_activity(self, financial_module):
        observation = {
            "enrichment": {
                "data_points": [
                    {"type": "transaction_summary", "count": 150, "total_volume": 50000}
                ]
            }
        }
        result = await financial_module.orient(observation)
        assert result["activity_level"] == "high"

    @pytest.mark.asyncio
    async def test_orient_low_activity(self, financial_module):
        observation = {
            "enrichment": {
                "data_points": [
                    {"type": "transaction_summary", "count": 5, "total_volume": 1000}
                ]
            }
        }
        result = await financial_module.orient(observation)
        assert result["activity_level"] == "low"


class TestFinancialModuleExecute:
    """Test execution phase."""

    @pytest.mark.asyncio
    async def test_execute_default(self, financial_module):
        result = await financial_module.execute({"action": "analyze"})

        assert result["module"] == "financial"
        assert result["status"] == "completed"
        assert result["action"] == "analyze"

    @pytest.mark.asyncio
    async def test_execute_price_forecast_without_service(self, financial_module):
        result = await financial_module.execute({"action": "price_forecast"})
        assert result["status"] == "completed"
        # No soko_pulse loaded, so no soko_pulse key
        assert "soko_pulse" not in result

    @pytest.mark.asyncio
    async def test_execute_fmcg_analysis_without_service(self, financial_module):
        result = await financial_module.execute({"action": "fmcg_analysis"})
        assert result["status"] == "completed"
