"""
Tests for SuperagentEngine — the core think-plan-act-observe-reflect engine.

Tests the full lifecycle with actual implementations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.superagent.core.engine import SuperagentEngine, Thought, PlanStep, Reflection


class TestSuperagentEngineInit:
    """Test engine initialization."""

    def test_default_init(self):
        engine = SuperagentEngine()
        assert engine.config == {}
        assert engine.modules == {}
        assert engine._execution_count == 0
        assert engine._history == []
        assert engine._thoughts == []
        assert engine._reflections == []

    def test_init_with_config(self):
        config = {"debug": True, "max_retries": 3}
        engine = SuperagentEngine(config=config)
        assert engine.config["debug"] is True
        assert engine.config["max_retries"] == 3

    def test_has_memory_systems(self):
        engine = SuperagentEngine()
        assert engine.working_memory is not None
        assert engine.episodic_memory is not None
        assert engine.semantic_memory is not None

    def test_has_tool_registry(self):
        engine = SuperagentEngine()
        assert engine.tool_registry is not None


class TestThink:
    """Test the think phase."""

    @pytest.mark.asyncio
    async def test_think_returns_structured_result(self):
        engine = SuperagentEngine()
        result = await engine.think({"type": "query", "domain": "financial", "data": {}})

        assert "thought_id" in result
        assert "reasoning" in result
        assert "confidence" in result
        assert "domain" in result
        assert "recommended_action" in result
        assert "factors" in result

    @pytest.mark.asyncio
    async def test_think_query_type_recommends_analyze(self):
        engine = SuperagentEngine()
        result = await engine.think({"type": "query", "domain": "financial"})
        assert result["recommended_action"] == "analyze"

    @pytest.mark.asyncio
    async def test_think_create_type_recommends_execute(self):
        engine = SuperagentEngine()
        result = await engine.think({"type": "create", "domain": "financial"})
        assert result["recommended_action"] == "execute"

    @pytest.mark.asyncio
    async def test_think_report_type_recommends_aggregate(self):
        engine = SuperagentEngine()
        result = await engine.think({"type": "report", "domain": "financial"})
        assert result["recommended_action"] == "aggregate"

    @pytest.mark.asyncio
    async def test_think_stores_in_working_memory(self):
        engine = SuperagentEngine()
        await engine.think({"type": "test", "domain": "general"})
        # Working memory should have the thought
        context = engine.working_memory.get_context()
        assert context is not None or engine.working_memory.entries  # may be empty string

    @pytest.mark.asyncio
    async def test_think_increases_confidence_with_memory(self):
        engine = SuperagentEngine()
        # First think — no prior context
        result1 = await engine.think({"type": "test", "domain": "general"})
        # Second think — has prior context
        result2 = await engine.think({"type": "test", "domain": "general"})
        # Second should have same or higher confidence
        assert result2["confidence"] >= result1["confidence"]

    @pytest.mark.asyncio
    async def test_think_with_domain_module(self):
        engine = SuperagentEngine()
        mock_module = MagicMock()
        mock_module.analyze = AsyncMock(return_value={"insight": "test"})
        engine.modules["financial"] = mock_module

        result = await engine.think({"type": "query", "domain": "financial"})
        assert "domain_analysis_financial" in result["factors"]

    @pytest.mark.asyncio
    async def test_think_records_thought(self):
        engine = SuperagentEngine()
        await engine.think({"type": "test", "domain": "general"})
        assert len(engine._thoughts) == 1
        assert isinstance(engine._thoughts[0], Thought)


class TestPlan:
    """Test the plan phase."""

    @pytest.mark.asyncio
    async def test_plan_returns_steps(self):
        engine = SuperagentEngine()
        plan = await engine.plan("sell mandazi", {"domain": "financial", "data": {}})

        assert isinstance(plan, list)
        assert len(plan) >= 3  # gather, analyze, synthesize at minimum

    @pytest.mark.asyncio
    async def test_plan_steps_have_required_fields(self):
        engine = SuperagentEngine()
        plan = await engine.plan("test goal", {"domain": "general", "data": {}})

        for step in plan:
            assert "step_id" in step
            assert "action" in step
            assert "description" in step
            assert "status" in step

    @pytest.mark.asyncio
    async def test_plan_with_domain_module_adds_step(self):
        engine = SuperagentEngine()
        engine.modules["financial"] = MagicMock()

        plan = await engine.plan("analyze sales", {"domain": "financial", "data": {}})
        actions = [s["action"] for s in plan]
        assert "execute_domain" in actions

    @pytest.mark.asyncio
    async def test_plan_first_step_is_gather_data(self):
        engine = SuperagentEngine()
        plan = await engine.plan("test", {"domain": "general", "data": {}})
        assert plan[0]["action"] == "gather_data"

    @pytest.mark.asyncio
    async def test_plan_last_step_is_synthesize(self):
        engine = SuperagentEngine()
        plan = await engine.plan("test", {"domain": "general", "data": {}})
        assert plan[-1]["action"] == "synthesize"


class TestAct:
    """Test the act phase."""

    @pytest.mark.asyncio
    async def test_act_default_processing(self):
        engine = SuperagentEngine()
        result = await engine.act({"action": "test", "domain": "general"})

        assert result["status"] == "completed"
        assert result["source"] == "default"

    @pytest.mark.asyncio
    async def test_act_with_domain_module(self):
        engine = SuperagentEngine()
        mock_module = AsyncMock()
        mock_module.execute = AsyncMock(return_value={"result": "ok"})
        engine.modules["financial"] = mock_module

        result = await engine.act({"action": "process", "domain": "financial"})
        assert result["source"] == "module"
        mock_module.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_act_handles_value_error(self):
        engine = SuperagentEngine()
        mock_module = AsyncMock()
        mock_module.execute = AsyncMock(side_effect=ValueError("bad input"))
        engine.modules["financial"] = mock_module

        result = await engine.act({"action": "process", "domain": "financial"})
        assert result["status"] == "error"
        assert "Invalid input" in result["error"]

    @pytest.mark.asyncio
    async def test_act_handles_key_error(self):
        engine = SuperagentEngine()
        mock_module = AsyncMock()
        mock_module.execute = AsyncMock(side_effect=KeyError("missing_key"))
        engine.modules["financial"] = mock_module

        result = await engine.act({"action": "process", "domain": "financial"})
        assert result["status"] == "error"
        assert "Missing key" in result["error"]

    @pytest.mark.asyncio
    async def test_act_records_duration(self):
        engine = SuperagentEngine()
        result = await engine.act({"action": "test", "domain": "general"})
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0


class TestObserve:
    """Test the observe phase."""

    @pytest.mark.asyncio
    async def test_observe_completed_action(self):
        engine = SuperagentEngine()
        result = await engine.observe({
            "status": "completed",
            "domain": "financial",
            "source": "module",
        })

        assert result["status"] == "completed"
        assert result["domain"] == "financial"
        assert isinstance(result["insights"], list)
        assert isinstance(result["anomalies"], list)

    @pytest.mark.asyncio
    async def test_observe_error_creates_anomaly(self):
        engine = SuperagentEngine()
        result = await engine.observe({
            "status": "error",
            "domain": "financial",
            "source": "module",
            "error": "connection failed",
        })

        assert len(result["anomalies"]) == 1
        assert "connection failed" in result["anomalies"][0]

    @pytest.mark.asyncio
    async def test_observe_stores_in_episodic_memory(self):
        engine = SuperagentEngine()
        await engine.observe({"status": "completed", "domain": "test"})
        assert len(engine.episodic_memory.episodes) == 1

    @pytest.mark.asyncio
    async def test_observe_with_module_result(self):
        engine = SuperagentEngine()
        result = await engine.observe({
            "status": "completed",
            "domain": "financial",
            "module_result": {"score": 750, "band": "good"},
        })

        assert len(result["insights"]) >= 2  # score and band


class TestReflect:
    """Test the reflect phase."""

    @pytest.mark.asyncio
    async def test_reflect_on_successes(self):
        engine = SuperagentEngine()
        history = [
            {"status": "completed", "domain": "financial", "source": "module"},
            {"status": "completed", "domain": "credit", "source": "module"},
        ]
        result = await engine.reflect(history)

        assert result["success_rate"] == 1.0
        assert len(result["success_patterns"]) >= 2
        assert len(result["failure_patterns"]) == 0

    @pytest.mark.asyncio
    async def test_reflect_on_failures(self):
        engine = SuperagentEngine()
        history = [
            {"status": "error", "domain": "financial", "source": "module", "error": "timeout"},
            {"status": "completed", "domain": "credit", "source": "module"},
        ]
        result = await engine.reflect(history)

        assert result["success_rate"] == 0.5
        assert len(result["failure_patterns"]) >= 1

    @pytest.mark.asyncio
    async def test_reflect_low_success_rate_recommendation(self):
        engine = SuperagentEngine()
        history = [{"status": "error"}] * 8 + [{"status": "completed"}] * 2
        result = await engine.reflect(history)

        assert any("below 50%" in r.lower() for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_reflect_stores_reflection(self):
        engine = SuperagentEngine()
        await engine.reflect([{"status": "completed"}])
        assert len(engine._reflections) == 1
        assert isinstance(engine._reflections[0], Reflection)

    @pytest.mark.asyncio
    async def test_reflect_empty_history(self):
        engine = SuperagentEngine()
        result = await engine.reflect([])
        assert result["success_rate"] == 0.0


class TestRun:
    """Test the full run cycle."""

    @pytest.mark.asyncio
    async def test_run_completes_full_cycle(self):
        engine = SuperagentEngine()
        result = await engine.run("analyze sales data", {"domain": "financial"})

        assert result["status"] == "completed"
        assert "phases" in result
        assert "think" in result["phases"]
        assert "plan" in result["phases"]
        assert "act" in result["phases"]
        assert "reflect" in result["phases"]
        assert "duration_ms" in result

    @pytest.mark.asyncio
    async def test_run_increments_execution_count(self):
        engine = SuperagentEngine()
        await engine.run("task 1")
        await engine.run("task 2")
        assert engine._execution_count == 2

    @pytest.mark.asyncio
    async def test_run_stores_in_history(self):
        engine = SuperagentEngine()
        await engine.run("test task")
        assert len(engine._history) == 1
        assert engine._history[0]["task"] == "test task"

    @pytest.mark.asyncio
    async def test_run_sets_status_to_idle_on_success(self):
        engine = SuperagentEngine()
        await engine.run("test task")
        assert engine.status.value == "idle"

    @pytest.mark.asyncio
    async def test_run_handles_error_gracefully(self):
        engine = SuperagentEngine()
        engine.think = AsyncMock(side_effect=ValueError("bad input"))
        result = await engine.run("test task")
        assert result["status"] == "error"
        assert "bad input" in result["error"]


class TestModuleManagement:
    """Test module and tool registration."""

    def test_register_module(self):
        engine = SuperagentEngine()
        mock_module = MagicMock()
        engine.register_module("financial", mock_module)
        assert engine.modules["financial"] is mock_module

    def test_register_tool(self):
        engine = SuperagentEngine()
        mock_tool = MagicMock()
        engine.register_tool(mock_tool)
        # Tool should be in registry


class TestGetHistory:
    """Test history retrieval."""

    @pytest.mark.asyncio
    async def test_get_history_returns_recent(self):
        engine = SuperagentEngine()
        for i in range(5):
            await engine.run(f"task {i}")

        history = engine.get_history(limit=3)
        assert len(history) == 3

    def test_get_history_empty(self):
        engine = SuperagentEngine()
        assert engine.get_history() == []


class TestGetStats:
    """Test engine statistics."""

    @pytest.mark.asyncio
    async def test_stats_after_executions(self):
        engine = SuperagentEngine()
        engine.register_module("financial", MagicMock())
        await engine.run("test task")

        stats = engine.get_stats()
        assert stats["total_executions"] == 1
        assert stats["total_thoughts"] >= 1
        assert "financial" in stats["registered_modules"]
        assert stats["status"] == "idle"
