"""
Tests for the Credit Intelligence Module.

Tests AlamaScoreEngine credit scoring, risk profiling,
and creditworthiness assessment.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.superagent.credit.module import CreditModule


@pytest.fixture
def credit_module():
    return CreditModule()


class TestCreditModuleInit:
    """Test initialization."""

    def test_default_state(self, credit_module):
        assert credit_module._alama_score is None
        assert credit_module._initialized is False


class TestCreditModuleObserve:
    """Test the observe phase — gathering credit-relevant data."""

    @pytest.mark.asyncio
    async def test_observe_with_transactions(self, credit_module):
        data = {
            "transactions": [
                {"amount": 500, "type": "SALE"},
                {"amount": 1200, "type": "SALE"},
                {"amount": 300, "type": "SALE"},
            ]
        }
        result = await credit_module.observe(data)

        assert result["module"] == "credit"
        assert len(result["indicators"]) >= 1

        volume_ind = next(i for i in result["indicators"] if i["type"] == "transaction_volume")
        assert volume_ind["value"] == 2000
        assert volume_ind["count"] == 3

    @pytest.mark.asyncio
    async def test_observe_with_no_transactions(self, credit_module):
        result = await credit_module.observe({})
        assert result["module"] == "credit"
        assert result["indicators"] == []

    @pytest.mark.asyncio
    async def test_observe_consistency_indicator(self, credit_module):
        """With 10+ transactions, a consistency indicator should be added."""
        data = {
            "transactions": [{"amount": 100 + i * 10, "type": "SALE"} for i in range(15)]
        }
        result = await credit_module.observe(data)

        consistency = [i for i in result["indicators"] if i["type"] == "consistency"]
        assert len(consistency) == 1
        assert "coefficient_of_variation" in consistency[0]


class TestCreditModuleOrient:
    """Test the orient phase — assessing credit situation."""

    @pytest.mark.asyncio
    async def test_orient_default_risk_profile(self, credit_module):
        observation = {"enrichment": {"indicators": []}}
        result = await credit_module.orient(observation)

        assert result["risk_profile"] == "moderate"
        assert result["creditworthiness"] == "assessing"

    @pytest.mark.asyncio
    async def test_orient_high_volume_tier(self, credit_module):
        observation = {
            "enrichment": {
                "indicators": [
                    {"type": "transaction_volume", "value": 150000, "count": 50}
                ]
            }
        }
        result = await credit_module.orient(observation)
        assert result["volume_tier"] == "high"

    @pytest.mark.asyncio
    async def test_orient_low_volume_tier(self, credit_module):
        observation = {
            "enrichment": {
                "indicators": [
                    {"type": "transaction_volume", "value": 10000, "count": 5}
                ]
            }
        }
        result = await credit_module.orient(observation)
        assert result["volume_tier"] == "low"


class TestCreditModuleExecute:
    """Test the execute phase."""

    @pytest.mark.asyncio
    async def test_execute_without_alama_score(self, credit_module):
        result = await credit_module.execute({"action": "score"})

        assert result["module"] == "credit"
        assert result["status"] == "completed"
        assert result["alama_score_available"] is False
        assert "note" in result

    @pytest.mark.asyncio
    async def test_execute_with_alama_score(self, credit_module):
        credit_module._alama_score = MagicMock()

        result = await credit_module.execute({"action": "score"})
        assert result["alama_score_available"] is True
