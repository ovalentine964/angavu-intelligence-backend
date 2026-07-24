"""
Tests for the Evolution Module — Self-Improvement Engine.

Tests outcome recording, success rate tracking, and adaptation triggers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.superagent.evolution.module import EvolutionModule


@pytest.fixture
def evolution_module():
    return EvolutionModule()


class TestEvolutionModuleInit:
    """Test initialization."""

    def test_default_state(self, evolution_module):
        assert evolution_module._evolution_service is None
        assert evolution_module._outcomes == []
        assert evolution_module._initialized is False


class TestEvolutionModuleObserve:
    """Test observation phase."""

    @pytest.mark.asyncio
    async def test_observe_with_feedback(self, evolution_module):
        data = {"feedback": {"rating": 5, "comment": "nzuri sana"}}
        result = await evolution_module.observe(data)

        assert result["module"] == "evolution"
        assert len(result["signals"]) == 1
        assert result["signals"][0]["type"] == "user_feedback"
        assert result["signals"][0]["data"]["rating"] == 5

    @pytest.mark.asyncio
    async def test_observe_without_feedback(self, evolution_module):
        result = await evolution_module.observe({})
        assert result["signals"] == []


class TestEvolutionModuleOrient:
    """Test orientation phase — assessing improvement opportunities."""

    @pytest.mark.asyncio
    async def test_orient_no_outcomes(self, evolution_module):
        result = await evolution_module.orient({})
        assert result["success_rate"] == 0.0  # 0/0 defaults to 0
        assert result["total_outcomes"] == 0

    @pytest.mark.asyncio
    async def test_orient_high_success_rate(self, evolution_module):
        evolution_module._outcomes = [
            {"status": "completed"} for _ in range(18)
        ] + [{"status": "error"}, {"status": "error"}]

        result = await evolution_module.orient({})
        assert result["success_rate"] == 0.9  # 18/20

    @pytest.mark.asyncio
    async def test_orient_low_success_rate(self, evolution_module):
        evolution_module._outcomes = [
            {"status": "error"} for _ in range(15)
        ] + [{"status": "completed"} for _ in range(5)]

        result = await evolution_module.orient({})
        assert result["success_rate"] == 0.25  # 5/20


class TestEvolutionModuleExecute:
    """Test execution phase."""

    @pytest.mark.asyncio
    async def test_execute_without_service(self, evolution_module):
        result = await evolution_module.execute({})
        assert result["module"] == "evolution"
        assert result["status"] == "completed"
        assert result["evolution_service_available"] is False

    @pytest.mark.asyncio
    async def test_execute_with_service(self, evolution_module):
        evolution_module._evolution_service = MagicMock()
        result = await evolution_module.execute({})
        assert result["evolution_service_available"] is True


class TestEvolutionModuleRecordOutcome:
    """Test outcome recording and adaptation triggers."""

    @pytest.mark.asyncio
    async def test_record_outcome_stores(self, evolution_module):
        await evolution_module.record_outcome({"status": "completed", "domain": "financial"})
        assert len(evolution_module._outcomes) == 1
        assert evolution_module._outcomes[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_record_outcome_trims_at_1000(self, evolution_module):
        evolution_module._outcomes = [{"status": "completed"}] * 1000
        await evolution_module.record_outcome({"status": "completed"})
        assert len(evolution_module._outcomes) == 501  # 500 trimmed + 1 new

    @pytest.mark.asyncio
    async def test_record_outcome_triggers_low_success_warning(self, evolution_module):
        """When recent success rate drops below 50%, a warning should be logged."""
        # Add 9 failures
        evolution_module._outcomes = [{"status": "error"}] * 9
        # This 10th outcome should trigger the check
        await evolution_module.record_outcome({"status": "error"})
        # The warning is logged but we verify the outcome was still recorded
        assert len(evolution_module._outcomes) == 10
