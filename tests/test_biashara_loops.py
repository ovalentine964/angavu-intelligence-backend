"""
Tests for Biashara Loop Systems.

Tests each loop with sample data and verifies integration with
DeerFlow's goal system patterns:
- GoalState lifecycle (active → completed)
- Evaluation (satisfied/blocker/reason)
- Continuation limits
- No-progress detection
- Reflexion (for loan loop)
- PlanExecute (for intelligence loop)
- LoopDetection patterns
"""

from __future__ import annotations

import sys
import time
import types

import pytest

# Avoid triggering full app.agents.__init__ import chain which pulls in
# services with pre-existing issues. Stub out the package init.
# We need app.agents.base and app.agents.loops.core to load without
# going through app.agents.__init__ or app.agents.loops.__init__.
if "app.agents" not in sys.modules:
    _agents_pkg = types.ModuleType("app.agents")
    _agents_pkg.__path__ = []
    sys.modules["app.agents"] = _agents_pkg

# Stub app.agents.loops package to avoid its __init__ triggering the full
# app.agents import chain (services, DB, etc.).
if "app.agents.loops" not in sys.modules:
    _loops_pkg = types.ModuleType("app.agents.loops")
    _loops_pkg.__path__ = []
    sys.modules["app.agents.loops"] = _loops_pkg

# Restore the loops package module with core's exports
import app.agents.loops.core as _core_mod
from app.agents.base import AgentEvent, EventType
from app.agents.loops.core import (
    EventStore,
    ExecutionPlan,
    PlanStep,
    ReActTrace,
)

sys.modules["app.agents.loops"].core = _core_mod
for name in ["Critique", "EventStore", "ExecutionPlan", "PlanStep",
             "ReActTrace", "SupervisedExecution", "SupervisionPolicy",
             "ReActAgent", "ReflexionAgent", "PlanExecuteAgent",
             "EventSourcedAgent", "SupervisorAgent", "ReasoningStep"]:
    if hasattr(_core_mod, name):
        setattr(sys.modules["app.agents.loops"], name, getattr(_core_mod, name))
from app.loops.config import (
    BiasharaLoopConfig,
    EvaluationMode,
    LoopPhaseConfig,
    LoopType,
    get_all_loop_configs,
    get_enabled_loop_configs,
    get_loop_config,
    register_loop_config,
)
from app.loops.goal_loop import (
    GoalLoopState,
    GoalProgressLoop,
)
from app.loops.intelligence_loop import (
    IntelligenceLoop,
    IntelligenceLoopState,
)
from app.loops.loan_loop import (
    Loan,
    LoanLoop,
    LoanLoopState,
)
from app.loops.tithe_loop import (
    TitheLoop,
    TitheLoopState,
)

# ════════════════════════════════════════════════════════════════════
# Config Tests
# ════════════════════════════════════════════════════════════════════


class TestBiasharaLoopConfig:
    """Test loop configuration system."""

    def test_default_configs_registered(self):
        """All four default configs should be registered on import."""
        configs = get_all_loop_configs()
        assert "tithe_tracking" in configs
        assert "goal_progress" in configs
        assert "loan_management" in configs
        assert "intelligence_generation" in configs
        assert len(configs) == 4

    def test_enabled_configs(self):
        """All default configs should be enabled."""
        enabled = get_enabled_loop_configs()
        assert len(enabled) == 4

    def test_tithe_config(self):
        """Tithe tracking config should have correct structure."""
        config = get_loop_config("tithe_tracking")
        assert config is not None
        assert config.loop_type == LoopType.GOAL
        assert len(config.phases) == 3
        assert config.phases[0].name == "record"
        assert config.phases[1].name == "analyze"
        assert config.phases[2].name == "encourage"
        assert config.evaluation.mode == EvaluationMode.COMPLETION

    def test_goal_config(self):
        """Goal progress config should use ReAct pattern."""
        config = get_loop_config("goal_progress")
        assert config is not None
        assert config.loop_type == LoopType.REACT
        assert len(config.phases) == 3

    def test_loan_config(self):
        """Loan management config should use Reflexion pattern."""
        config = get_loop_config("loan_management")
        assert config is not None
        assert config.loop_type == LoopType.REFLEXION
        assert config.phases[1].retry_count == 2  # verify phase retries

    def test_intelligence_config(self):
        """Intelligence config should use PlanExecute pattern."""
        config = get_loop_config("intelligence_generation")
        assert config is not None
        assert config.loop_type == LoopType.PLAN_EXECUTE
        assert len(config.phases) == 3

    def test_to_goal_objective(self):
        """Config should produce a valid goal objective string."""
        config = get_loop_config("tithe_tracking")
        objective = config.to_goal_objective()
        assert "tithe_tracking" in objective
        assert "record" in objective
        assert "analyze" in objective
        assert "encourage" in objective

    def test_custom_config_registration(self):
        """Should be able to register custom configs."""
        custom = BiasharaLoopConfig(
            feature_name="test_feature",
            description="Test feature",
            loop_type=LoopType.GOAL,
            phases=[
                LoopPhaseConfig(name="step1", description="Step 1"),
            ],
        )
        register_loop_config(custom)
        assert get_loop_config("test_feature") is not None

    def test_disabled_config_excluded(self):
        """Disabled configs should be excluded from enabled list."""
        custom = BiasharaLoopConfig(
            feature_name="disabled_feature",
            description="Disabled",
            loop_type=LoopType.GOAL,
            phases=[LoopPhaseConfig(name="step1", description="Step 1")],
            enabled=False,
        )
        register_loop_config(custom)
        assert "disabled_feature" not in get_enabled_loop_configs()
        assert "disabled_feature" in get_all_loop_configs()


# ════════════════════════════════════════════════════════════════════
# EventStore Tests
# ════════════════════════════════════════════════════════════════════


class TestEventStore:
    """Test the event store for audit trail."""

    def test_append_and_query(self):
        store = EventStore()
        store.append("test.event", "test_source", {"key": "value"})
        assert store.count() == 1

        events = store.query(event_type="test.event")
        assert len(events) == 1
        assert events[0].source == "test_source"

    def test_query_by_source(self):
        store = EventStore()
        store.append("a", "source1", {})
        store.append("b", "source2", {})
        store.append("a", "source1", {})

        events = store.query(source="source1")
        assert len(events) == 2

    def test_query_with_limit(self):
        store = EventStore()
        for i in range(10):
            store.append("test", "src", {"i": i})

        events = store.query(limit=5)
        assert len(events) == 5

    def test_replay(self):
        store = EventStore()
        store.append("a", "src", {"v": 1})
        store.append("b", "src", {"v": 2})
        store.append("a", "src", {"v": 3})

        replayed = store.replay(event_type="a")
        assert len(replayed) == 2

    def test_count_by_type(self):
        store = EventStore()
        store.append("a", "src", {})
        store.append("a", "src", {})
        store.append("b", "src", {})

        assert store.count("a") == 2
        assert store.count("b") == 1
        assert store.count() == 3


# ════════════════════════════════════════════════════════════════════
# Tithe Loop Tests
# ════════════════════════════════════════════════════════════════════


class TestTitheLoopState:
    """Test tithe loop state management."""

    def test_initial_state(self):
        state = TitheLoopState(worker_id="w1")
        assert not state.is_satisfied()
        assert state.get_blocker() == "missing_evidence"
        assert state.continuation_count == 0

    def test_record_progress(self):
        state = TitheLoopState(worker_id="w1")
        changed = state.record_progress("record", {"amount": 500})
        assert changed is True
        assert state.payment_recorded is True

    def test_all_phases_complete(self):
        state = TitheLoopState(worker_id="w1")
        state.record_progress("record", {})
        state.record_progress("analyze", {})
        state.record_progress("encourage", {})
        assert state.is_satisfied()
        assert state.get_blocker() == "none"

    def test_to_goal_state(self):
        state = TitheLoopState(worker_id="w1")
        gs = state.to_goal_state()
        assert gs["status"] == "active"
        assert gs["continuation_count"] == 0
        assert gs["last_evaluation"]["satisfied"] is False

    def test_goal_state_completed(self):
        state = TitheLoopState(worker_id="w1")
        state.record_progress("record", {})
        state.record_progress("analyze", {})
        state.record_progress("encourage", {})
        gs = state.to_goal_state()
        assert gs["status"] == "completed"
        assert gs["last_evaluation"]["satisfied"] is True


class TestTitheLoop:
    """Test the tithe tracking loop agent."""

    @pytest.fixture
    def loop(self):
        return TitheLoop()

    @pytest.mark.asyncio
    async def test_record_phase(self, loop):
        """Test recording a tithe payment."""
        event = AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="mpesa_webhook",
            payload={
                "worker_id": "w123",
                "amount": 500,
                "type": "tithe",
            },
        )
        result = await loop.handle_event(event)
        assert result.success is True
        assert result.data["phase"] == "record"
        assert result.data["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_full_cycle(self, loop):
        """Test complete record → analyze → encourage cycle."""
        event = AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="mpesa_webhook",
            payload={
                "worker_id": "w456",
                "amount": 1000,
                "type": "tithe",
            },
        )

        # First call: record
        result1 = await loop.handle_event(event)
        assert result1.success is True
        assert result1.data["phase"] == "record"

        # Second call: analyze
        result2 = await loop.handle_event(event)
        assert result2.success is True
        assert result2.data["phase"] == "analyze"

        # Third call: encourage
        result3 = await loop.handle_event(event)
        assert result3.success is True
        assert result3.data["phase"] == "encourage"

        # Verify loop is complete
        state = loop.get_state("w456")
        assert state is not None
        assert state["status"] == "completed"
        assert state["last_evaluation"]["satisfied"] is True

    @pytest.mark.asyncio
    async def test_max_continuations(self, loop):
        """Test that loop stops at max continuations."""
        # Force high continuation count
        state = loop._get_or_create_state("w_max")
        state.continuation_count = 10  # Exceed max

        event = AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="test",
            payload={"worker_id": "w_max", "amount": 100},
        )
        result = await loop.handle_event(event)
        assert result.data.get("status") == "force_completed"

    def test_state_management(self, loop):
        """Test state get/reset."""
        loop._get_or_create_state("w_test")
        assert loop.get_state("w_test") is not None

        loop.reset_state("w_test")
        assert loop.get_state("w_test") is None


# ════════════════════════════════════════════════════════════════════
# Goal Progress Loop Tests
# ════════════════════════════════════════════════════════════════════


class TestGoalLoopState:
    """Test goal loop state management."""

    def test_initial_state(self):
        state = GoalLoopState(goal_id="g1", worker_id="w1")
        assert not state.is_satisfied()
        assert state.get_blocker() == "missing_evidence"

    def test_progress_tracking(self):
        state = GoalLoopState(goal_id="g1", worker_id="w1")
        state.record_progress("track", {"amount": 500})
        state.record_progress("predict", {"on_track": True})
        state.record_progress("nudge", {"type": "on_track"})
        assert state.is_satisfied()


class TestGoalProgressLoop:
    """Test the goal progress loop agent."""

    @pytest.fixture
    def loop(self):
        return GoalProgressLoop()

    @pytest.mark.asyncio
    async def test_track_phase(self, loop):
        """Test recording a goal contribution."""
        event = AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="mpesa_webhook",
            payload={
                "goal_id": "g123",
                "worker_id": "w123",
                "amount": 2000,
                "target_amount": 10000,
                "goal_name": "School Fees",
            },
        )
        result = await loop.handle_event(event)
        assert result.success is True
        assert result.data["phase"] == "track"

    @pytest.mark.asyncio
    async def test_full_cycle(self, loop):
        """Test complete track → predict → nudge cycle."""
        event = AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="test",
            payload={
                "goal_id": "g456",
                "worker_id": "w456",
                "amount": 3000,
                "target_amount": 10000,
                "goal_name": "Business Expansion",
            },
        )

        result1 = await loop.handle_event(event)
        assert result1.data["phase"] == "track"

        result2 = await loop.handle_event(event)
        assert result2.data["phase"] == "predict"

        result3 = await loop.handle_event(event)
        assert result3.data["phase"] == "nudge"

        state = loop.get_state("g456")
        assert state["status"] == "completed"


# ════════════════════════════════════════════════════════════════════
# Loan Loop Tests
# ════════════════════════════════════════════════════════════════════


class TestLoanLoopState:
    """Test loan loop state management."""

    def test_initial_state(self):
        state = LoanLoopState(loan_id="l1", worker_id="w1")
        assert not state.is_satisfied()
        assert state.get_blocker() == "missing_evidence"

    def test_full_progress(self):
        state = LoanLoopState(loan_id="l1", worker_id="w1")
        state.record_progress("record", {})
        state.record_progress("verify", {})
        state.record_progress("alert", {})
        assert state.is_satisfied()
        assert state.get_blocker() == "none"


class TestLoanDataTypes:
    """Test loan data types."""

    def test_loan_total_paid(self):
        loan = Loan(
            loan_id="l1",
            worker_id="w1",
            principal=10000,
            outstanding_balance=7000,
            payments=[{"amount": 2000}, {"amount": 1000}],
        )
        assert loan.total_paid == 3000
        assert loan.payment_count == 2

    def test_loan_overdue(self):
        loan = Loan(
            loan_id="l1",
            worker_id="w1",
            principal=10000,
            outstanding_balance=5000,
            due_date="2020-01-01T00:00:00+00:00",
        )
        assert loan.is_overdue is True
        assert loan.days_overdue > 0


class TestLoanLoop:
    """Test the loan management loop agent."""

    @pytest.fixture
    def loop(self):
        return LoanLoop()

    @pytest.mark.asyncio
    async def test_record_phase(self, loop):
        """Test recording a loan payment."""
        event = AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="mpesa_webhook",
            payload={
                "loan_id": "l789",
                "worker_id": "w789",
                "amount": 2000,
                "type": "repayment",
                "principal": 10000,
                "outstanding_balance": 8000,
            },
        )
        result = await loop.handle_event(event)
        assert result.success is True
        assert result.data["phase"] == "record"

    @pytest.mark.asyncio
    async def test_full_cycle(self, loop):
        """Test complete record → verify → alert cycle."""
        event = AgentEvent(
            event_type=EventType.TRANSACTION_RECEIVED,
            source="test",
            payload={
                "loan_id": "l999",
                "worker_id": "w999",
                "amount": 3000,
                "type": "repayment",
                "principal": 10000,
                "outstanding_balance": 7000,
            },
        )

        result1 = await loop.handle_event(event)
        assert result1.data["phase"] == "record"

        result2 = await loop.handle_event(event)
        assert result2.data["phase"] == "verify"

        result3 = await loop.handle_event(event)
        assert result3.data["phase"] == "alert"

        state = loop.get_state("l999")
        assert state["status"] == "completed"

    @pytest.mark.asyncio
    async def test_overdue_alert(self, loop):
        """Test that overdue loans generate warning alerts."""
        # Create a state with an overdue loan
        state = loop._get_or_create_state("l_overdue", "w_overdue")
        state.payment_recorded = True
        state.verification_complete = True
        state.loan = Loan(
            loan_id="l_overdue",
            worker_id="w_overdue",
            principal=10000,
            outstanding_balance=8000,
            due_date="2020-01-01T00:00:00+00:00",
        )

        result = await loop._alert_phase("l_overdue", "w_overdue", state)
        assert result["success"] is True
        assert result["alert"]["alert_type"] in ("overdue", "default_warning")


# ════════════════════════════════════════════════════════════════════
# Intelligence Loop Tests
# ════════════════════════════════════════════════════════════════════


class TestIntelligenceLoopState:
    """Test intelligence loop state management."""

    def test_initial_state(self):
        state = IntelligenceLoopState(request_id="r1", worker_id="w1")
        assert not state.is_satisfied()
        assert state.get_blocker() == "missing_evidence"

    def test_full_progress(self):
        state = IntelligenceLoopState(request_id="r1", worker_id="w1")
        state.record_progress("collect", {})
        state.record_progress("analyze", {})
        state.record_progress("deliver", {})
        assert state.is_satisfied()


class TestIntelligenceLoop:
    """Test the intelligence generation loop agent."""

    @pytest.fixture
    def loop(self):
        return IntelligenceLoop()

    @pytest.mark.asyncio
    async def test_plan_creation(self, loop):
        """Test that the plan is created with correct steps."""
        event = AgentEvent(
            event_type=EventType.INTELLIGENCE_REQUESTED,
            source="api",
            payload={
                "worker_id": "w123",
                "products": ["market_intelligence", "price_forecast"],
                "request_id": "r123",
            },
        )
        result = await loop.handle_event(event)
        assert result.success is True

        # Verify plan was created
        state = loop.get_state("r123")
        assert state is not None

    @pytest.mark.asyncio
    async def test_plan_steps(self, loop):
        """Test that plan steps have correct dependencies."""
        plan = await loop._create_plan(
            "Generate intelligence",
            {
                "event": {
                    "payload": {
                        "worker_id": "w1",
                        "products": ["market_intelligence", "price_forecast", "credit_score"],
                        "request_id": "r1",
                    }
                }
            },
        )

        assert len(plan.steps) == 6  # collect + 3 products + format + deliver

        # Check dependencies
        collect_step = next(s for s in plan.steps if s.step_id == "collect_data")
        assert len(collect_step.dependencies) == 0

        market_step = next(s for s in plan.steps if s.step_id == "generate_market_intelligence")
        assert "collect_data" in market_step.dependencies

        format_step = next(s for s in plan.steps if s.step_id == "format_report")
        assert "generate_market_intelligence" in format_step.dependencies
        assert "generate_price_forecast" in format_step.dependencies
        assert "generate_credit_score" in format_step.dependencies

    @pytest.mark.asyncio
    async def test_step_execution(self, loop):
        """Test individual step execution."""
        result = await loop._step_collect("w1", "r1", None)
        assert result["success"] is True
        assert result["new_data"] is True

    @pytest.mark.asyncio
    async def test_product_generation(self, loop):
        """Test product generation steps."""
        for product in ["market_intelligence", "price_forecast", "credit_score"]:
            result = await loop._step_generate(product, "w1", "r1", None)
            assert result["success"] is True
            assert result["product"] == product


# ════════════════════════════════════════════════════════════════════
# DeerFlow Integration Tests
# ════════════════════════════════════════════════════════════════════


class TestDeerFlowIntegration:
    """Test integration with DeerFlow's goal system patterns."""

    def test_goal_state_format(self):
        """Loop states should produce valid DeerFlow GoalState format."""
        state = TitheLoopState(worker_id="w1")
        gs = state.to_goal_state()

        # Required GoalState fields
        assert "objective" in gs
        assert "status" in gs
        assert "continuation_count" in gs
        assert "max_continuations" in gs
        assert "no_progress_count" in gs
        assert "max_no_progress_continuations" in gs
        assert "last_evaluation" in gs

        # GoalEvaluation fields
        eval_ = gs["last_evaluation"]
        assert "satisfied" in eval_
        assert "blocker" in eval_
        assert isinstance(eval_["satisfied"], bool)
        assert eval_["blocker"] in (
            "none", "missing_evidence", "needs_user_input",
            "run_failed", "external_wait", "goal_not_met_yet",
        )

    def test_continuation_limits_match_deerflow(self):
        """Continuation limits should align with DeerFlow defaults."""
        from app.loops.goal_loop import GoalLoopState
        from app.loops.intelligence_loop import IntelligenceLoopState
        from app.loops.loan_loop import LoanLoopState
        from app.loops.tithe_loop import TitheLoopState

        # All states should have reasonable continuation limits
        for state_cls in [TitheLoopState, GoalLoopState, LoanLoopState, IntelligenceLoopState]:
            state = state_cls(**{k: "test" for k in state_cls.__dataclass_fields__ if k in ("worker_id", "goal_id", "loan_id", "request_id")})
            assert state.max_continuations <= 8  # DeerFlow DEFAULT_MAX_GOAL_CONTINUATIONS
            assert state.max_no_progress <= 2   # DeerFlow DEFAULT_MAX_NO_PROGRESS_CONTINUATIONS

    def test_blocker_values_match_deerflow(self):
        """Blocker values should match DeerFlow's GoalBlocker literals."""
        valid_blockers = {"none", "missing_evidence", "needs_user_input", "run_failed", "external_wait", "goal_not_met_yet"}

        state = TitheLoopState(worker_id="w1")
        assert state.get_blocker() in valid_blockers

        state.record_progress("record", {})
        assert state.get_blocker() in valid_blockers

    def test_evidence_tracking(self):
        """Evidence should be tracked for goal evaluation."""
        state = TitheLoopState(worker_id="w1")
        state.record_progress("record", {"amount": 500})
        state.record_progress("analyze", {"score": 0.8})

        assert "payment_recorded" in state.evidence
        assert "analysis_complete" in state.evidence
        assert state.evidence["payment_recorded"]["amount"] == 500

    def test_no_progress_detection(self):
        """No-progress counter should increment when no new progress."""
        state = TitheLoopState(worker_id="w1")
        state.record_progress("record", {})

        # Recording same phase again should not count as progress
        changed = state.record_progress("record", {})
        assert changed is False

    def test_event_store_integration(self):
        """EventStore should work alongside loop execution."""
        store = EventStore()

        # Simulate loop events
        store.append("loop.tithe.record", "TitheLoop", {"worker_id": "w1"})
        store.append("loop.tithe.analyze", "TitheLoop", {"worker_id": "w1"})
        store.append("loop.tithe.encourage", "TitheLoop", {"worker_id": "w1"})

        events = store.query(event_type="loop.tithe.record")
        assert len(events) == 1

        total = store.count()
        assert total == 3

    def test_react_trace_integration(self):
        """ReAct traces should be creatable for debugging."""
        trace = ReActTrace(trace_id="test123")
        trace.add_step(
            thought="Processing tithe payment",
            action="record_payment",
            observation="Payment recorded: KES 500",
        )
        trace.completed_at = time.time()

        d = trace.to_dict()
        assert d["trace_id"] == "test123"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["thought"] == "Processing tithe payment"

    def test_execution_plan_integration(self):
        """ExecutionPlan should support dependency resolution."""
        plan = ExecutionPlan(
            goal="Generate intelligence",
            steps=[
                PlanStep(step_id="a", description="Step A", action="a"),
                PlanStep(step_id="b", description="Step B", action="b", dependencies=["a"]),
                PlanStep(step_id="c", description="Step C", action="c", dependencies=["a"]),
                PlanStep(step_id="d", description="Step D", action="d", dependencies=["b", "c"]),
            ],
        )

        # Initially, only A is ready
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "a"

        # After A completes, B and C are ready
        plan.steps[0].status = "completed"
        ready = plan.get_ready_steps()
        assert len(ready) == 2
        ready_ids = {s.step_id for s in ready}
        assert ready_ids == {"b", "c"}

        # After B and C complete, D is ready
        plan.steps[1].status = "completed"
        plan.steps[2].status = "completed"
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "d"
