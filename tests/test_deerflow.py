"""
Tests for DeerFlow V2 Integration Layer.

Tests:
- DAGTaskPlanner: decomposition, re-planning, DAG validation
- CapabilityRouter: capability matching, scoring, routing
- SubAgentDelegator: delegation, timeout, error handling
- CheckpointProgressTracker: checkpoint save/restore, progress reporting
- MultiStrategyAggregator: all aggregation strategies
- DeerFlowOrchestrator: goal loop, cancellation, status
- ToolRegistry: registration, lookup, execution
- BiasharaTool: base tool execution, timeout, validation
- ThreadState: serialization, message management
- StatePersistence: save/load, checkpoint management
"""

import asyncio
import os
import time
from unittest.mock import MagicMock

import pytest

# Set required env vars before importing app modules
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-32")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-testing-32c")
os.environ.setdefault("OPENWA_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("APP_ENV", "test")

from app.agents.base import AgentEvent, BiasharaAgent, EventType

# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


class MockAgent(BiasharaAgent):
    """Mock agent for testing."""
    name = "MockAgent"
    role = "Test agent"
    capabilities = ["test_capability", "data_collection", "analysis"]

    async def observe(self, event):
        return {"event": event}

    async def think(self, context):
        return {"action": "test", "confidence": 0.9}

    async def act(self, decision):
        return {"result": "success", "data": {"key": "value"}}

    async def reflect(self, result):
        pass


class FailingAgent(BiasharaAgent):
    """Agent that always fails."""
    name = "FailingAgent"
    role = "Always fails"
    capabilities = ["failure"]

    async def observe(self, event):
        return {"event": event}

    async def think(self, context):
        return {"action": "fail"}

    async def act(self, decision):
        raise RuntimeError("Intentional failure")

    async def reflect(self, result):
        pass


class SlowAgent(BiasharaAgent):
    """Agent that takes a long time."""
    name = "SlowAgent"
    role = "Very slow"
    capabilities = ["slow"]

    async def observe(self, event):
        return {"event": event}

    async def think(self, context):
        return {"action": "wait"}

    async def act(self, decision):
        await asyncio.sleep(100)  # Very slow
        return {"result": "done"}

    async def reflect(self, result):
        pass


# ════════════════════════════════════════════════════════════════════
# Task Planner Tests
# ════════════════════════════════════════════════════════════════════


class TestDAGTaskPlanner:
    """Test DAG task planner."""

    @pytest.mark.asyncio
    async def test_plan_creates_subtasks(self):
        """Planner should create sub-tasks from a goal."""
        from app.deerflow.task_planner import DAGTaskPlanner

        planner = DAGTaskPlanner()
        subtasks = await planner.plan(
            goal="Test goal",
            context={"key": "value"},
            available_agents=["agent1"],
        )

        assert len(subtasks) >= 1
        assert subtasks[0].name == "execute_goal"

    @pytest.mark.asyncio
    async def test_intelligence_planner_creates_dag(self):
        """Intelligence planner should create a proper DAG."""
        from app.deerflow.task_planner import IntelligencePlanner

        planner = IntelligencePlanner()
        subtasks = await planner.plan(
            goal="Generate intelligence",
            context={"worker_id": "w123", "worker_type": "farmer"},
            available_agents=["agent1"],
        )

        assert len(subtasks) == 6
        names = [s.name for s in subtasks]
        assert "collect_transactions" in names
        assert "collect_market_data" in names
        assert "analyze_data" in names
        assert "generate_forecast" in names
        assert "generate_report" in names
        assert "validate_quality" in names

    @pytest.mark.asyncio
    async def test_replan_retries_on_failure(self):
        """Re-plan should retry if attempts < max_retries."""
        from app.deerflow.task_planner import DAGTaskPlanner, SubTask, SubTaskStatus

        planner = DAGTaskPlanner()

        # Create a task with a failed subtask
        subtask = SubTask(
            name="test_task",
            action="test",
            attempts=1,
            max_retries=3,
            status=SubTaskStatus.FAILED,
            error="test error",
        )

        task = MagicMock()
        task.task_id = "test"
        task.subtasks = [subtask]

        new_subtasks = await planner.replan(task, subtask, {})
        assert subtask.status == SubTaskStatus.PENDING
        assert subtask.error is None

    @pytest.mark.asyncio
    async def test_replan_skips_exhausted_retries(self):
        """Re-plan should skip if retries exhausted and no dependents."""
        from app.deerflow.task_planner import DAGTaskPlanner, SubTask, SubTaskStatus

        planner = DAGTaskPlanner()

        subtask = SubTask(
            name="test_task",
            action="test",
            attempts=3,
            max_retries=3,
            status=SubTaskStatus.FAILED,
        )

        task = MagicMock()
        task.task_id = "test"
        task.subtasks = [subtask]

        new_subtasks = await planner.replan(task, subtask, {})
        assert subtask.status == SubTaskStatus.SKIPPED


# ════════════════════════════════════════════════════════════════════
# Capability Router Tests
# ════════════════════════════════════════════════════════════════════


class TestCapabilityRouter:
    """Test capability-based routing."""

    def test_register_agent(self):
        """Should register agent capabilities."""
        from app.deerflow.sub_agent_delegator import CapabilityRouter

        router = CapabilityRouter()
        agent = MockAgent()
        router.register_agent(agent)

        assert "MockAgent" in router._agent_capabilities

    def test_route_by_capability(self):
        """Should route to agent with matching capability."""
        from app.deerflow.sub_agent_delegator import CapabilityRouter
        from app.deerflow.task_planner import SubTask

        router = CapabilityRouter()
        router.register_agent(MockAgent())

        subtask = SubTask(
            name="test",
            action="collect_data",
            required_capabilities=["data_collection"],
        )

        result = router.route(subtask)
        assert result == "MockAgent"

    def test_route_fallback(self):
        """Should fall back to first available agent."""
        from app.deerflow.sub_agent_delegator import CapabilityRouter
        from app.deerflow.task_planner import SubTask

        router = CapabilityRouter()
        router.register_agent(MockAgent())

        subtask = SubTask(
            name="test",
            action="unknown_action",
            required_capabilities=["nonexistent"],
        )

        result = router.route(subtask)
        assert result == "MockAgent"

    def test_record_result_updates_metrics(self):
        """Should track execution metrics."""
        from app.deerflow.sub_agent_delegator import CapabilityRouter

        router = CapabilityRouter()
        router.register_agent(MockAgent())

        router.record_result("MockAgent", True, 100.0)
        router.record_result("MockAgent", False, 200.0)

        metrics = router.get_metrics()
        assert metrics["MockAgent"]["total"] == 2
        assert metrics["MockAgent"]["successes"] == 1
        assert metrics["MockAgent"]["failures"] == 1


# ════════════════════════════════════════════════════════════════════
# Sub-Agent Delegator Tests
# ════════════════════════════════════════════════════════════════════


class TestSubAgentDelegator:
    """Test sub-agent delegation."""

    @pytest.mark.asyncio
    async def test_delegate_success(self):
        """Should delegate and return success result."""
        from app.deerflow.sub_agent_delegator import SubAgentDelegator
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        delegator = SubAgentDelegator()
        agent = MockAgent()
        agent.set_event_bus(MagicMock())
        delegator.register_agent(agent)

        subtask = SubTask(name="test", action="test", timeout_seconds=5.0)
        event = AgentEvent(
            event_type=EventType.INTELLIGENCE_REQUESTED,
            source="test",
            payload={"action": "test"},
        )

        result = await delegator.delegate(subtask, event)
        assert subtask.status == SubTaskStatus.COMPLETED
        assert subtask.assigned_agent == "MockAgent"

    @pytest.mark.asyncio
    async def test_delegate_no_agent(self):
        """Should fail when no agent available."""
        from app.deerflow.sub_agent_delegator import SubAgentDelegator
        from app.deerflow.task_planner import SubTask

        delegator = SubAgentDelegator()
        subtask = SubTask(name="test", action="test")
        event = AgentEvent(
            event_type=EventType.INTELLIGENCE_REQUESTED,
            source="test",
            payload={},
        )

        result = await delegator.delegate(subtask, event)
        assert not result.success
        assert "No agent available" in result.error

    @pytest.mark.asyncio
    async def test_delegate_timeout(self):
        """Should timeout on slow agents."""
        from app.deerflow.sub_agent_delegator import SubAgentDelegator
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        delegator = SubAgentDelegator()
        agent = SlowAgent()
        agent.set_event_bus(MagicMock())
        delegator.register_agent(agent)

        subtask = SubTask(name="test", action="test", timeout_seconds=0.1)
        event = AgentEvent(
            event_type=EventType.INTELLIGENCE_REQUESTED,
            source="test",
            payload={},
        )

        result = await delegator.delegate(subtask, event)
        assert subtask.status == SubTaskStatus.FAILED
        assert "Timed out" in subtask.error


# ════════════════════════════════════════════════════════════════════
# Progress Tracker Tests
# ════════════════════════════════════════════════════════════════════


class TestCheckpointProgressTracker:
    """Test checkpoint-based progress tracking."""

    def test_save_checkpoint(self):
        """Should save checkpoint with task state."""
        from app.deerflow.progress_tracker import CheckpointProgressTracker
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        tracker = CheckpointProgressTracker()

        task = MagicMock()
        task.task_id = "test_task"
        task.status = MagicMock()
        task.status.value = "executing"
        task.subtasks = [
            SubTask(name="st1", status=SubTaskStatus.COMPLETED),
            SubTask(name="st2", status=SubTaskStatus.RUNNING),
        ]
        task.aggregated_result = {"key": "value"}
        task.checkpoints = []
        task.goal_state = MagicMock()
        task.goal_state.objective = "test"
        task.goal_state.status = "active"
        task.goal_state.continuation_count = 0
        task.goal_state.max_continuations = 8
        task.goal_state.no_progress_count = 0

        checkpoint = tracker.save_checkpoint(task)
        assert checkpoint.task_id == "test_task"
        assert len(task.checkpoints) == 1

    def test_restore_checkpoint(self):
        """Should restore task state from checkpoint."""
        from app.deerflow.progress_tracker import CheckpointProgressTracker
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        tracker = CheckpointProgressTracker()

        # Create task with checkpoint
        subtask = SubTask(name="st1", subtask_id="st1_id")
        task = MagicMock()
        task.task_id = "test_task"
        task.subtasks = [subtask]
        task.aggregated_result = None
        task.checkpoints = []
        task.goal_state = MagicMock()
        task.goal_state.objective = "test"
        task.goal_state.status = "active"
        task.goal_state.continuation_count = 0
        task.goal_state.max_continuations = 8
        task.goal_state.no_progress_count = 0

        # Save checkpoint
        tracker.save_checkpoint(task)

        # Modify subtask
        subtask.status = SubTaskStatus.FAILED

        # Restore
        success = tracker.restore_checkpoint(task)
        assert success

    def test_progress_report(self):
        """Should generate progress report."""
        from app.deerflow.progress_tracker import CheckpointProgressTracker
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        tracker = CheckpointProgressTracker()

        task = MagicMock()
        task.task_id = "test_task"
        task.goal = "Test goal"
        task.status = MagicMock()
        task.status.value = "executing"
        task.progress_pct = 50.0
        task.subtasks = [
            SubTask(name="st1", status=SubTaskStatus.COMPLETED),
            SubTask(name="st2", status=SubTaskStatus.RUNNING),
            SubTask(name="st3", status=SubTaskStatus.PENDING),
        ]
        task.checkpoints = []
        task.started_at = time.time()
        task.completed_at = None
        task.error = None
        task.goal_state = MagicMock()
        task.goal_state.continuation_count = 0
        task.goal_state.can_continue.return_value = True

        tracker.register_task(task)
        report = tracker.get_progress_report("test_task")

        assert report is not None
        assert report["task_id"] == "test_task"
        assert report["subtasks"]["completed"] == 1
        assert report["subtasks"]["running"] == 1
        assert report["subtasks"]["pending"] == 1


# ════════════════════════════════════════════════════════════════════
# Result Aggregator Tests
# ════════════════════════════════════════════════════════════════════


class TestMultiStrategyAggregator:
    """Test multi-strategy result aggregation."""

    def test_sequential_merge(self):
        """Should merge results sequentially."""
        from app.deerflow.result_aggregator import MultiStrategyAggregator
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        aggregator = MultiStrategyAggregator()

        task = MagicMock()
        task.task_id = "test"
        task.subtasks = [
            SubTask(
                name="st1",
                subtask_id="id1",
                status=SubTaskStatus.COMPLETED,
                result={"data": {"price": 100}},
                started_at=time.time() - 10,
                completed_at=time.time(),
            ),
            SubTask(
                name="st2",
                subtask_id="id2",
                status=SubTaskStatus.COMPLETED,
                result={"data": {"trend": "up"}},
                started_at=time.time() - 5,
                completed_at=time.time(),
            ),
        ]

        result = aggregator.aggregate(task, strategy="sequential")
        assert "merged_data" in result
        assert "_metadata" in result
        assert result["_metadata"]["successful"] == 2

    def test_highest_confidence(self):
        """Should pick highest confidence result."""
        from app.deerflow.result_aggregator import MultiStrategyAggregator
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        aggregator = MultiStrategyAggregator()

        task = MagicMock()
        task.task_id = "test"
        task.subtasks = [
            SubTask(
                name="st1",
                subtask_id="id1",
                status=SubTaskStatus.COMPLETED,
                result={"data": {"confidence": 0.6, "verdict": "low"}},
            ),
            SubTask(
                name="st2",
                subtask_id="id2",
                status=SubTaskStatus.COMPLETED,
                result={"data": {"confidence": 0.9, "verdict": "high"}},
            ),
        ]

        result = aggregator.aggregate(task, strategy="highest_confidence")
        assert result["selected_subtask"] == "id2"
        assert result["confidence"] == 0.9

    def test_handles_failures(self):
        """Should include errors in aggregated result."""
        from app.deerflow.result_aggregator import MultiStrategyAggregator
        from app.deerflow.task_planner import SubTask, SubTaskStatus

        aggregator = MultiStrategyAggregator()

        task = MagicMock()
        task.task_id = "test"
        task.subtasks = [
            SubTask(
                name="st1",
                subtask_id="id1",
                status=SubTaskStatus.COMPLETED,
                result={"data": {"key": "value"}},
            ),
            SubTask(
                name="st2",
                subtask_id="id2",
                status=SubTaskStatus.FAILED,
                error="test error",
                attempts=3,
            ),
        ]

        result = aggregator.aggregate(task, strategy="sequential")
        assert result["_metadata"]["failed"] == 1
        assert "id2" in result["errors"]


# ════════════════════════════════════════════════════════════════════
# Tool Registry Tests
# ════════════════════════════════════════════════════════════════════


class TestToolRegistry:
    """Test tool registry."""

    def test_register_tool(self):
        """Should register a tool."""
        from app.deerflow.tools.registry import ToolRegistry
        from app.deerflow.tools.wrappers import SokoPulseTool

        registry = ToolRegistry()
        registry.register(SokoPulseTool())

        assert "soko_pulse" in registry.get_tool_names()

    def test_find_by_capability(self):
        """Should find tools by capability."""
        from app.deerflow.tools.registry import ToolRegistry
        from app.deerflow.tools.wrappers import AlamaScoreTool, SokoPulseTool

        registry = ToolRegistry()
        registry.register(SokoPulseTool())
        registry.register(AlamaScoreTool())

        tools = registry.find_by_capability("price_forecasting")
        assert len(tools) == 1
        assert tools[0].name == "soko_pulse"

    def test_get_nonexistent_tool(self):
        """Should return None for nonexistent tool."""
        from app.deerflow.tools.registry import ToolRegistry

        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """Should execute a tool and track metrics."""
        from app.deerflow.tools.registry import ToolRegistry
        from app.deerflow.tools.wrappers import SokoPulseTool

        registry = ToolRegistry()
        registry.register(SokoPulseTool())

        result = await registry.execute("soko_pulse", market="Gikomba", product="rice")
        assert result.success
        assert result.tool_name == "soko_pulse"

        metrics = registry.get_metrics("soko_pulse")
        assert metrics["total_executions"] == 1

    def test_list_tools(self):
        """Should list all tools with metadata."""
        from app.deerflow.tools.registry import ToolRegistry
        from app.deerflow.tools.wrappers import SokoPulseTool

        registry = ToolRegistry()
        registry.register(SokoPulseTool())

        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "soko_pulse"


# ════════════════════════════════════════════════════════════════════
# BiasharaTool Tests
# ════════════════════════════════════════════════════════════════════


class TestBiasharaTool:
    """Test base tool class."""

    @pytest.mark.asyncio
    async def test_tool_execute_success(self):
        """Should execute successfully."""
        from app.deerflow.tools.wrappers import SokoPulseTool

        tool = SokoPulseTool()
        result = await tool.execute(market="Gikomba", product="rice")

        assert result.success
        assert result.tool_name == "soko_pulse"
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_tool_timeout(self):
        """Should timeout on slow execution."""
        from app.deerflow.tools.base import BiasharaTool

        class TimeoutTool(BiasharaTool):
            @property
            def name(self): return "timeout"
            @property
            def description(self): return "Times out"
            @property
            def timeout_seconds(self): return 0.1

            async def _execute(self, **kwargs):
                await asyncio.sleep(100)

        tool = TimeoutTool()
        result = await tool.execute()
        assert not result.success
        assert "timed out" in result.error.lower()

    def test_tool_to_dict(self):
        """Should serialize tool metadata."""
        from app.deerflow.tools.wrappers import SokoPulseTool

        tool = SokoPulseTool()
        d = tool.to_dict()

        assert d["name"] == "soko_pulse"
        assert "description" in d
        assert "capabilities" in d


# ════════════════════════════════════════════════════════════════════
# Thread State Tests
# ════════════════════════════════════════════════════════════════════


class TestThreadState:
    """Test thread state management."""

    def test_add_message(self):
        """Should add messages to thread."""
        from app.deerflow.state.thread_state import ThreadState

        state = ThreadState()
        msg = state.add_message("user", "Hello")

        assert len(state.messages) == 1
        assert state.messages[0].role == "user"
        assert state.messages[0].content == "Hello"

    def test_add_tool_call(self):
        """Should track tool calls."""
        from app.deerflow.state.thread_state import ThreadState

        state = ThreadState()
        call = state.add_tool_call("soko_pulse", {"market": "Gikomba"})

        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "soko_pulse"

    def test_serialize_deserialize(self):
        """Should round-trip through serialization."""
        from app.deerflow.state.thread_state import ThreadState

        state = ThreadState(thread_id="test123")
        state.add_message("user", "Hello")
        state.add_message("assistant", "Hi there!")
        state.set_goal("Test goal")

        serialized = state.serialize()
        restored = ThreadState.deserialize(serialized)

        assert restored.thread_id == "test123"
        assert len(restored.messages) == 2
        assert restored.goal["objective"] == "Test goal"

    def test_biashara_thread_state(self):
        """Should extend with Biashara fields."""
        from app.deerflow.state.thread_state import BiasharaThreadState

        state = BiasharaThreadState()
        state.set_worker_context("w123", "farmer", "Nakuru")
        state.set_market_context("Wakulima", ["maize", "beans"])

        assert state.worker_id == "w123"
        assert state.worker_type == "farmer"
        assert state.market_name == "Wakulima"

        serialized = state.serialize()
        restored = BiasharaThreadState.deserialize(serialized)

        assert restored.worker_id == "w123"
        assert restored.market_name == "Wakulima"


# ════════════════════════════════════════════════════════════════════
# State Persistence Tests
# ════════════════════════════════════════════════════════════════════


class TestStatePersistence:
    """Test state persistence layer."""

    def test_save_and_load(self):
        """Should save and load state."""
        from app.deerflow.state.persistence import StatePersistence
        from app.deerflow.state.thread_state import ThreadState

        persistence = StatePersistence()
        state = ThreadState(thread_id="test_thread")
        state.add_message("user", "Hello")

        persistence.save(state)
        restored = persistence.load("test_thread")

        assert restored is not None
        assert restored.thread_id == "test_thread"
        assert len(restored.messages) == 1

    def test_load_nonexistent(self):
        """Should return None for nonexistent thread."""
        from app.deerflow.state.persistence import StatePersistence

        persistence = StatePersistence()
        result = persistence.load("nonexistent")
        assert result is None

    def test_list_checkpoints(self):
        """Should list checkpoints for a thread."""
        from app.deerflow.state.persistence import StatePersistence
        from app.deerflow.state.thread_state import ThreadState

        persistence = StatePersistence()
        state = ThreadState(thread_id="test_thread")

        persistence.save(state)
        persistence.save(state)

        checkpoints = persistence.list_checkpoints("test_thread")
        assert len(checkpoints) == 2

    def test_delete_thread(self):
        """Should delete all checkpoints for a thread."""
        from app.deerflow.state.persistence import StatePersistence
        from app.deerflow.state.thread_state import ThreadState

        persistence = StatePersistence()
        state = ThreadState(thread_id="test_thread")

        persistence.save(state)
        assert persistence.delete_thread("test_thread")

        restored = persistence.load("test_thread")
        assert restored is None


# ════════════════════════════════════════════════════════════════════
# State Reducer Tests
# ════════════════════════════════════════════════════════════════════


class TestReducers:
    """Test state reducers."""

    def test_merge_messages_deduplicates(self):
        """Should deduplicate messages by ID."""
        from app.deerflow.state.reducers import merge_messages

        existing = [
            {"message_id": "1", "content": "Hello"},
            {"message_id": "2", "content": "World"},
        ]
        new = [
            {"message_id": "2", "content": "World"},
            {"message_id": "3", "content": "New"},
        ]

        merged = merge_messages(existing, new)
        assert len(merged) == 3

    def test_merge_metadata_update(self):
        """Should update existing keys."""
        from app.deerflow.state.reducers import merge_metadata

        existing = {"a": 1, "b": 2}
        new = {"b": 3, "c": 4}

        merged = merge_metadata(existing, new, strategy="update")
        assert merged == {"a": 1, "b": 3, "c": 4}

    def test_merge_metadata_keep(self):
        """Should keep existing keys."""
        from app.deerflow.state.reducers import merge_metadata

        existing = {"a": 1, "b": 2}
        new = {"b": 3, "c": 4}

        merged = merge_metadata(existing, new, strategy="keep")
        assert merged == {"a": 1, "b": 2, "c": 4}

    def test_reduce_state(self):
        """Should apply appropriate reducers per field."""
        from app.deerflow.state.reducers import reduce_state

        current = {
            "messages": [{"message_id": "1", "content": "Hello"}],
            "metadata": {"key": "old"},
        }
        updates = {
            "messages": [{"message_id": "2", "content": "World"}],
            "metadata": {"key": "new"},
        }

        result = reduce_state(current, updates)
        assert len(result["messages"]) == 2
        assert result["metadata"]["key"] == "new"


# ════════════════════════════════════════════════════════════════════
# DeerFlow Orchestrator Tests
# ════════════════════════════════════════════════════════════════════


class TestDeerFlowOrchestrator:
    """Test the main DeerFlow orchestrator."""

    @pytest.mark.asyncio
    async def test_execute_simple_goal(self):
        """Should execute a simple goal."""
        from app.deerflow.orchestrator import DeerFlowOrchestrator, TaskStatus

        orchestrator = DeerFlowOrchestrator()
        agent = MockAgent()
        agent.set_event_bus(MagicMock())
        orchestrator.register_agent(agent)

        task = await orchestrator.execute(
            goal="Test goal",
            context={"key": "value"},
            timeout_seconds=10.0,
        )

        assert task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        assert task.goal == "Test goal"

    @pytest.mark.asyncio
    async def test_register_agents(self):
        """Should register multiple agents."""
        from app.deerflow.orchestrator import DeerFlowOrchestrator

        orchestrator = DeerFlowOrchestrator()
        agents = [MockAgent(), FailingAgent()]
        for a in agents:
            a.set_event_bus(MagicMock())
        orchestrator.register_agents(agents)

        status = orchestrator.get_status()
        assert len(status["registered_agents"]) == 2

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """Should cancel a running task."""
        from app.deerflow.orchestrator import DeerFlowOrchestrator

        orchestrator = DeerFlowOrchestrator()
        # We can't easily test cancellation without a running task
        # but we can test that cancel_task returns False for unknown tasks
        result = await orchestrator.cancel_task("nonexistent")
        assert result is False

    def test_get_status(self):
        """Should return orchestrator status."""
        from app.deerflow.orchestrator import DeerFlowOrchestrator

        orchestrator = DeerFlowOrchestrator()
        status = orchestrator.get_status()

        assert "name" in status
        assert "registered_agents" in status
        assert "active_tasks" in status


# ════════════════════════════════════════════════════════════════════
# Integration Test
# ════════════════════════════════════════════════════════════════════


class TestDeerFlowIntegration:
    """Integration tests for the full DeerFlow stack."""

    @pytest.mark.asyncio
    async def test_full_stack(self):
        """Should work end-to-end with all components."""
        from app.deerflow.orchestrator import DeerFlowOrchestrator
        from app.deerflow.state import BiasharaThreadState, StatePersistence
        from app.deerflow.tools.wrappers import create_default_registry

        # Create orchestrator
        orchestrator = DeerFlowOrchestrator()

        # Register agents
        agent = MockAgent()
        agent.set_event_bus(MagicMock())
        orchestrator.register_agent(agent)

        # Create tool registry
        registry = create_default_registry()
        assert len(registry.get_tool_names()) >= 5

        # Create state persistence
        persistence = StatePersistence()
        state = BiasharaThreadState(thread_id="integration_test")
        state.set_worker_context("w123", "farmer")
        persistence.save(state)

        # Execute a task
        task = await orchestrator.execute(
            goal="Analyze farm business",
            context={"worker_id": "w123", "worker_type": "farmer"},
            timeout_seconds=10.0,
        )

        # Verify
        assert task.task_id is not None
        assert task.goal == "Analyze farm business"

        # Load state
        restored = persistence.load("integration_test")
        assert restored is not None
        assert restored.worker_id == "w123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
