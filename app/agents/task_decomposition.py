"""
Task Decomposition — Break complex tasks into parallel/sequential sub-tasks.

Analyzes a complex task and produces an execution plan with:
- Dependency graph (DAG) of sub-tasks
- Parallel execution where dependencies allow
- Sequential execution where order matters
- Resource allocation hints
- Estimated complexity per sub-task

Integrates with SubAgentOrchestrator for execution.

Architecture:
    Complex Task
         │
         ▼
    ┌──────────────────┐
    │ TaskDecomposer   │ ← Analyze task, identify sub-tasks
    └──────┬───────────┘
           ▼
    ┌──────────────────┐
    │ DependencyGraph  │ ← Build DAG of dependencies
    └──────┬───────────┘
           ▼
    ┌──────────────────┐
    │ ExecutionPlan    │ ← Schedule parallel/sequential batches
    └──────┬───────────┘
           ▼
    SubAgentOrchestrator.spawn() × N
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple

import structlog

from app.agents.subagent import (
    SubAgentOrchestrator,
    SubAgentPriority,
    SubAgentResult,
    SubAgentStatus,
    SubAgentTask,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════


class TaskComplexity(str, Enum):
    """Estimated complexity of a sub-task."""
    TRIVIAL = "trivial"      # < 1s
    SIMPLE = "simple"        # 1-10s
    MODERATE = "moderate"    # 10-60s
    COMPLEX = "complex"      # 1-5 min
    INTENSIVE = "intensive"  # > 5 min


class DecompositionStrategy(str, Enum):
    """Strategy for decomposing a task."""
    PARALLEL = "parallel"        # All sub-tasks run in parallel
    SEQUENTIAL = "sequential"    # Sub-tasks run in order
    DAG = "dag"                  # Dependency-based execution
    FAN_OUT = "fan_out"          # Same task to multiple agents, first wins
    PIPELINE = "pipeline"        # Output of one feeds into next


@dataclass
class SubTaskDefinition:
    """
    Definition of a sub-task produced by decomposition.

    This is a template — the TaskDecomposer produces these,
    and the SubAgentOrchestrator turns them into SubAgentTasks.
    """
    subtask_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = ""
    description: str = ""
    handler_name: str = ""       # Name of handler to use
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)  # subtask_ids
    complexity: TaskComplexity = TaskComplexity.MODERATE
    priority: SubAgentPriority = SubAgentPriority.NORMAL
    timeout_seconds: float = 60.0
    can_parallelize: bool = True
    estimated_duration_ms: float = 0.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize sub-task definition to dictionary."""
        return {
            "subtask_id": self.subtask_id,
            "name": self.name,
            "description": self.description,
            "handler_name": self.handler_name,
            "depends_on": self.depends_on,
            "complexity": self.complexity.value,
            "priority": self.priority.value,
            "timeout_seconds": self.timeout_seconds,
            "can_parallelize": self.can_parallelize,
            "tags": self.tags,
        }


@dataclass
class DecompositionPlan:
    """
    A complete decomposition plan for a complex task.

    Contains the DAG of sub-tasks and execution schedule.
    """
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_name: str = ""
    strategy: DecompositionStrategy = DecompositionStrategy.DAG
    subtasks: List[SubTaskDefinition] = field(default_factory=list)
    execution_batches: List[List[str]] = field(default_factory=list)  # Ordered batches of subtask_ids
    created_at: float = field(default_factory=time.time)

    @property
    def total_subtasks(self) -> int:
        """Total number of sub-tasks in this plan."""
        return len(self.subtasks)

    @property
    def parallelism(self) -> float:
        """Average parallelism (subtasks / batches)."""
        if not self.execution_batches:
            return 1.0
        return len(self.subtasks) / len(self.execution_batches)

    def get_subtask(self, subtask_id: str) -> Optional[SubTaskDefinition]:
        """Find a sub-task definition by its ID."""
        for st in self.subtasks:
            if st.subtask_id == subtask_id:
                return st
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_name": self.task_name,
            "strategy": self.strategy.value,
            "total_subtasks": self.total_subtasks,
            "parallelism": round(self.parallelism, 2),
            "execution_batches": self.execution_batches,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "created_at": self.created_at,
        }


@dataclass
class DecompositionResult:
    """Result of executing a decomposition plan."""
    plan: DecompositionPlan
    results: Dict[str, SubAgentResult] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    success: bool = False
    failed_subtasks: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        successes = sum(1 for r in self.results.values() if r.success)
        return successes / len(self.results)

    def get_aggregated_data(self) -> Dict[str, Any]:
        """Aggregate data from all successful sub-task results."""
        aggregated = {}
        for subtask_id, result in self.results.items():
            if result.success and result.data:
                aggregated[subtask_id] = result.data
        return aggregated

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan.plan_id,
            "total_subtasks": self.plan.total_subtasks,
            "completed": len(self.results),
            "success_rate": round(self.success_rate, 3),
            "total_duration_ms": round(self.total_duration_ms, 1),
            "success": self.success,
            "failed_subtasks": self.failed_subtasks,
        }


# ════════════════════════════════════════════════════════════════════
# TaskDecomposer
# ════════════════════════════════════════════════════════════════════


class TaskDecomposer:
    """
    Decomposes complex tasks into a DAG of sub-tasks.

    The decomposer analyzes the task, identifies independent
    sub-tasks, determines dependencies, and produces an execution
    plan that maximizes parallelism.

    Features:
    - Dependency graph construction
    - Topological sorting for execution order
    - Parallel batch identification
    - Complexity estimation
    - Re-planning on sub-task failure
    - Handler registry for sub-task execution

    Usage:
        decomposer = TaskDecomposer()
        decomposer.register_handler("analyze_market", market_handler)
        decomposer.register_handler("check_inventory", inventory_handler)

        plan = decomposer.decompose(
            task_name="order_fulfillment",
            description="Process an order from receipt to delivery",
        )

        # Execute via SubAgentOrchestrator
        result = await decomposer.execute(plan, orchestrator)
    """

    def __init__(self):
        self._handlers: Dict[str, Callable[..., Coroutine]] = {}
        self._handler_metadata: Dict[str, Dict[str, Any]] = {}
        self._custom_decomposers: Dict[str, Callable] = {}

        self._logger = logger.bind(component="task_decomposer")

    # ── Handler Registration ────────────────────────────────────────

    def register_handler(
        self,
        name: str,
        handler: Callable[..., Coroutine],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a handler for sub-task execution."""
        self._handlers[name] = handler
        self._handler_metadata[name] = metadata or {}
        self._logger.debug("handler_registered", name=name)

    def register_decomposer(
        self,
        task_type: str,
        decomposer_fn: Callable[..., List[SubTaskDefinition]],
    ) -> None:
        """Register a custom decomposition function for a task type."""
        self._custom_decomposers[task_type] = decomposer_fn

    # ── Decomposition ───────────────────────────────────────────────

    def decompose(
        self,
        task_name: str,
        description: str = "",
        strategy: DecompositionStrategy = DecompositionStrategy.DAG,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> DecompositionPlan:
        """
        Decompose a complex task into sub-tasks.

        If a custom decomposer is registered for the task_name,
        it will be used. Otherwise, uses a default heuristic.

        Args:
            task_name: Name/type of the task
            description: Task description
            strategy: Decomposition strategy
            parameters: Task parameters

        Returns:
            DecompositionPlan with sub-tasks and execution schedule
        """
        self._logger.info("decomposing_task", task_name=task_name, strategy=strategy.value)

        # Check for custom decomposer
        if task_name in self._custom_decomposers:
            subtasks = self._custom_decomposers[task_name](**parameters or {})
        else:
            subtasks = self._default_decompose(task_name, description, parameters or {})

        plan = DecompositionPlan(
            task_name=task_name,
            strategy=strategy,
            subtasks=subtasks,
        )

        # Build execution schedule
        plan.execution_batches = self._build_execution_schedule(subtasks, strategy)

        self._logger.info(
            "decomposition_complete",
            task_name=task_name,
            subtasks=len(subtasks),
            batches=len(plan.execution_batches),
            parallelism=round(plan.parallelism, 2),
        )

        return plan

    def _default_decompose(
        self,
        task_name: str,
        description: str,
        parameters: Dict[str, Any],
    ) -> List[SubTaskDefinition]:
        """
        Default decomposition heuristic.

        Creates sub-tasks based on available handlers and common patterns.
        Override register_decomposer() for domain-specific decomposition.
        """
        subtasks = []

        # Find relevant handlers based on task name
        relevant_handlers = []
        for handler_name in self._handlers:
            # Simple keyword matching
            if any(kw in task_name.lower() for kw in handler_name.lower().split("_")):
                relevant_handlers.append(handler_name)

        # If no keyword match, use all registered handlers
        if not relevant_handlers:
            relevant_handlers = list(self._handlers.keys())[:5]  # Cap at 5

        for i, handler_name in enumerate(relevant_handlers):
            subtasks.append(SubTaskDefinition(
                name=handler_name,
                description=f"Execute {handler_name} for {task_name}",
                handler_name=handler_name,
                parameters=parameters,
                complexity=TaskComplexity.MODERATE,
                can_parallelize=True,
            ))

        return subtasks

    # ── Execution Schedule ──────────────────────────────────────────

    def _build_execution_schedule(
        self,
        subtasks: List[SubTaskDefinition],
        strategy: DecompositionStrategy,
    ) -> List[List[str]]:
        """
        Build an execution schedule from sub-tasks.

        For DAG strategy, performs topological sort to find
        parallel execution batches.
        """
        if strategy == DecompositionStrategy.PARALLEL:
            # All sub-tasks in one batch
            return [[st.subtask_id for st in subtasks]]

        if strategy == DecompositionStrategy.SEQUENTIAL:
            # One sub-task per batch
            return [[st.subtask_id] for st in subtasks]

        if strategy == DecompositionStrategy.FAN_OUT:
            # All sub-tasks in one batch (first result wins)
            return [[st.subtask_id for st in subtasks]]

        if strategy == DecompositionStrategy.PIPELINE:
            # Sequential, each depending on previous
            batches = []
            for st in subtasks:
                batches.append([st.subtask_id])
            return batches

        # DAG strategy — topological sort
        return self._topological_batches(subtasks)

    def _topological_batches(
        self,
        subtasks: List[SubTaskDefinition],
    ) -> List[List[str]]:
        """
        Topological sort into parallel execution batches.

        Sub-tasks with no unmet dependencies go in the first batch.
        Once those complete, sub-tasks whose dependencies are all
        met go in the next batch, etc.
        """
        # Build adjacency
        id_to_task = {st.subtask_id: st for st in subtasks}
        remaining = set(st.subtask_id for st in subtasks)
        completed: Set[str] = set()
        batches: List[List[str]] = []

        while remaining:
            # Find tasks whose dependencies are all completed
            batch = []
            for task_id in remaining:
                task = id_to_task[task_id]
                deps_met = all(dep in completed for dep in task.depends_on)
                if deps_met:
                    batch.append(task_id)

            if not batch:
                # Circular dependency — break by adding remaining as a batch
                self._logger.warning("circular_dependency_detected", remaining=list(remaining))
                batch = list(remaining)

            batches.append(batch)
            completed.update(batch)
            remaining -= set(batch)

        return batches

    # ── Execution ───────────────────────────────────────────────────

    async def execute(
        self,
        plan: DecompositionPlan,
        orchestrator: SubAgentOrchestrator,
        fail_fast: bool = False,
    ) -> DecompositionResult:
        """
        Execute a decomposition plan using the SubAgentOrchestrator.

        Executes sub-tasks in batch order. Within each batch,
        sub-tasks run in parallel. Waits for all in a batch
        before proceeding to the next.

        Args:
            plan: The decomposition plan to execute
            orchestrator: SubAgentOrchestrator for spawning sub-agents
            fail_fast: If True, stop on first failure

        Returns:
            DecompositionResult with all sub-task results
        """
        start_time = time.time()
        all_results: Dict[str, SubAgentResult] = {}
        failed: List[str] = []

        self._logger.info(
            "executing_plan",
            plan_id=plan.plan_id,
            batches=len(plan.execution_batches),
        )

        for batch_idx, batch in enumerate(plan.execution_batches):
            self._logger.info(
                "executing_batch",
                batch_idx=batch_idx,
                subtasks=batch,
            )

            # Spawn all sub-tasks in this batch
            task_ids = []
            for subtask_id in batch:
                subtask = plan.get_subtask(subtask_id)
                if not subtask:
                    continue

                handler = self._handlers.get(subtask.handler_name)
                if not handler:
                    self._logger.warning(
                        "handler_not_found",
                        handler_name=subtask.handler_name,
                    )
                    all_results[subtask_id] = SubAgentResult(
                        task_id=subtask_id,
                        status=SubAgentStatus.FAILED,
                        error=f"Handler not found: {subtask.handler_name}",
                    )
                    failed.append(subtask_id)
                    continue

                # Inject results from dependencies into parameters
                params = dict(subtask.parameters)
                for dep_id in subtask.depends_on:
                    dep_result = all_results.get(dep_id)
                    if dep_result and dep_result.success:
                        params[f"dep_{dep_id}"] = dep_result.data

                task_id = orchestrator.spawn(
                    name=subtask.name,
                    handler=handler,
                    parameters=params,
                    timeout_seconds=subtask.timeout_seconds,
                    priority=subtask.priority,
                    tags=subtask.tags,
                )
                task_ids.append((subtask_id, task_id))

            # Wait for all in this batch
            for subtask_id, task_id in task_ids:
                result = await orchestrator.wait_for(task_id)
                all_results[subtask_id] = result

                if not result.success:
                    failed.append(subtask_id)
                    if fail_fast:
                        return DecompositionResult(
                            plan=plan,
                            results=all_results,
                            total_duration_ms=(time.time() - start_time) * 1000,
                            success=False,
                            failed_subtasks=failed,
                        )

        total_ms = (time.time() - start_time) * 1000
        success = len(failed) == 0

        self._logger.info(
            "plan_execution_complete",
            plan_id=plan.plan_id,
            success=success,
            failed=len(failed),
            total_ms=round(total_ms, 1),
        )

        return DecompositionResult(
            plan=plan,
            results=all_results,
            total_duration_ms=total_ms,
            success=success,
            failed_subtasks=failed,
        )

    # ── Re-planning ─────────────────────────────────────────────────

    def replan_on_failure(
        self,
        original_plan: DecompositionPlan,
        failed_subtasks: List[str],
        results: Dict[str, SubAgentResult],
    ) -> DecompositionPlan:
        """
        Re-plan after sub-task failures.

        Creates a new plan that:
        - Removes completed sub-tasks
        - Keeps failed sub-tasks for retry
        - Adjusts dependencies
        """
        remaining = []
        for subtask in original_plan.subtasks:
            sid = subtask.subtask_id
            if sid in results and results[sid].success:
                continue  # Already completed — skip
            remaining.append(subtask)

        new_plan = DecompositionPlan(
            task_name=original_plan.task_name + " (retry)",
            strategy=original_plan.strategy,
            subtasks=remaining,
        )
        new_plan.execution_batches = self._build_execution_schedule(
            remaining, original_plan.strategy
        )

        self._logger.info(
            "replan_created",
            original_subtasks=len(original_plan.subtasks),
            remaining_subtasks=len(remaining),
        )

        return new_plan

    # ── Query ───────────────────────────────────────────────────────

    def get_registered_handlers(self) -> List[str]:
        """List registered handler names."""
        return list(self._handlers.keys())

    def get_handler_metadata(self, name: str) -> Dict[str, Any]:
        """Get metadata for a handler."""
        return self._handler_metadata.get(name, {})


# ════════════════════════════════════════════════════════════════════
# Pre-built Decomposition Patterns for Angavu
# ════════════════════════════════════════════════════════════════════


def create_financial_task_decomposer() -> TaskDecomposer:
    """
    Create a TaskDecomposer pre-configured for Angavu financial tasks.

    Includes handlers for common financial decomposition patterns:
    - Order fulfillment (market → inventory → delivery)
    - Credit assessment (transactions → score → recommendation)
    - Market analysis (prices → trends → opportunities)
    - Financial health check (income → expenses → report)
    """
    decomposer = TaskDecomposer()

    # Register common handlers
    decomposer.register_handler(
        "analyze_market",
        _mock_handler("market_analysis"),
        {"description": "Analyze market prices and trends", "complexity": "moderate"},
    )
    decomposer.register_handler(
        "check_inventory",
        _mock_handler("inventory_check"),
        {"description": "Check current inventory levels", "complexity": "simple"},
    )
    decomposer.register_handler(
        "assess_credit",
        _mock_handler("credit_assessment"),
        {"description": "Assess creditworthiness", "complexity": "moderate"},
    )
    decomposer.register_handler(
        "generate_report",
        _mock_handler("report_generation"),
        {"description": "Generate financial report", "complexity": "simple"},
    )
    decomposer.register_handler(
        "detect_anomalies",
        _mock_handler("anomaly_detection"),
        {"description": "Detect anomalies in data", "complexity": "moderate"},
    )

    # Register domain-specific decomposers
    decomposer.register_decomposer(
        "order_fulfillment",
        _decompose_order_fulfillment,
    )
    decomposer.register_decomposer(
        "credit_assessment",
        _decompose_credit_assessment,
    )
    decomposer.register_decomposer(
        "market_analysis",
        _decompose_market_analysis,
    )

    return decomposer


async def _mock_handler(domain: str, **kwargs: Any) -> Dict[str, Any]:
    """Mock handler for testing. In production, replaced with real handlers."""
    return {"domain": domain, "status": "completed", "data": kwargs}


def _decompose_order_fulfillment(**params: Any) -> List[SubTaskDefinition]:
    """Decompose an order fulfillment task."""
    market = SubTaskDefinition(
        name="analyze_market",
        description="Analyze current market prices for the order items",
        handler_name="analyze_market",
        parameters=params,
        complexity=TaskComplexity.MODERATE,
        can_parallelize=True,
    )
    inventory = SubTaskDefinition(
        name="check_inventory",
        description="Check warehouse inventory for order items",
        handler_name="check_inventory",
        parameters=params,
        complexity=TaskComplexity.SIMPLE,
        can_parallelize=True,
    )
    # Report depends on both market and inventory
    report = SubTaskDefinition(
        name="generate_report",
        description="Generate order fulfillment report",
        handler_name="generate_report",
        parameters=params,
        depends_on=[market.subtask_id, inventory.subtask_id],
        complexity=TaskComplexity.SIMPLE,
        can_parallelize=False,
    )
    return [market, inventory, report]


def _decompose_credit_assessment(**params: Any) -> List[SubTaskDefinition]:
    """Decompose a credit assessment task."""
    anomalies = SubTaskDefinition(
        name="detect_anomalies",
        description="Scan transactions for anomalies",
        handler_name="detect_anomalies",
        parameters=params,
        complexity=TaskComplexity.MODERATE,
        can_parallelize=True,
    )
    credit = SubTaskDefinition(
        name="assess_credit",
        description="Generate credit score",
        handler_name="assess_credit",
        parameters=params,
        depends_on=[anomalies.subtask_id],
        complexity=TaskComplexity.MODERATE,
    )
    report = SubTaskDefinition(
        name="generate_report",
        description="Generate credit assessment report",
        handler_name="generate_report",
        parameters=params,
        depends_on=[credit.subtask_id],
        complexity=TaskComplexity.SIMPLE,
    )
    return [anomalies, credit, report]


def _decompose_market_analysis(**params: Any) -> List[SubTaskDefinition]:
    """Decompose a market analysis task."""
    market = SubTaskDefinition(
        name="analyze_market",
        description="Analyze current market conditions",
        handler_name="analyze_market",
        parameters=params,
        complexity=TaskComplexity.MODERATE,
        can_parallelize=True,
    )
    anomalies = SubTaskDefinition(
        name="detect_anomalies",
        description="Detect market anomalies and opportunities",
        handler_name="detect_anomalies",
        parameters=params,
        complexity=TaskComplexity.MODERATE,
        can_parallelize=True,
    )
    report = SubTaskDefinition(
        name="generate_report",
        description="Generate market analysis report",
        handler_name="generate_report",
        parameters=params,
        depends_on=[market.subtask_id, anomalies.subtask_id],
        complexity=TaskComplexity.SIMPLE,
    )
    return [market, anomalies, report]
