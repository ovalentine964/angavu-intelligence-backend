"""
Tests for the Federated Learning Module.

Tests observation, orientation, and execution of the learning module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.superagent.learning.module import LearningModule


@pytest.fixture
def learning_module():
    return LearningModule()


class TestLearningModuleInit:
    """Test initialization."""

    def test_default_state(self, learning_module):
        assert learning_module._fl_service is None
        assert learning_module._initialized is False


class TestLearningModuleObserve:
    """Test observation phase."""

    @pytest.mark.asyncio
    async def test_observe_with_model_updates(self, learning_module):
        data = {
            "model_updates": [
                {"layer": "attention", "delta": [0.1, 0.2]},
                {"layer": "ffn", "delta": [0.3, 0.4]},
            ]
        }
        result = await learning_module.observe(data)

        assert result["module"] == "learning"
        assert len(result["signals"]) == 1
        assert result["signals"][0]["type"] == "model_updates"
        assert result["signals"][0]["count"] == 2

    @pytest.mark.asyncio
    async def test_observe_empty_data(self, learning_module):
        result = await learning_module.observe({})
        assert result["signals"] == []


class TestLearningModuleOrient:
    """Test orientation phase."""

    @pytest.mark.asyncio
    async def test_orient_default_state(self, learning_module):
        result = await learning_module.orient({})
        assert result["training_status"] == "stable"
        assert result["model_health"] == "good"


class TestLearningModuleExecute:
    """Test execution phase."""

    @pytest.mark.asyncio
    async def test_execute_without_service(self, learning_module):
        result = await learning_module.execute({})
        assert result["module"] == "learning"
        assert result["status"] == "completed"
        assert result["fl_service_available"] is False
        assert "note" in result

    @pytest.mark.asyncio
    async def test_execute_with_service(self, learning_module):
        learning_module._fl_service = MagicMock()
        result = await learning_module.execute({})
        assert result["fl_service_available"] is True
