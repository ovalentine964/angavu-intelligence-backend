"""
Superagent Core Engine

The central reasoning engine that replaces the multi-agent swarm.
Single agent, multiple capabilities, unified memory.

Implements the full think-plan-act-observe-reflect cycle with
integration to the tool registry, memory system, and domain modules.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

import structlog

from app.agents.base import AgentEvent, AgentResult, AgentStatus, BiasharaAgent, EventType
from app.superagent.core.memory import EpisodicMemory, SemanticMemory, WorkingMemory
from app.superagent.core.tools import Tool, ToolRegistry

logger = structlog.get_logger(__name__)


@dataclass
class Thought:
    """A reasoning thought produced during the think phase."""
    thought_id: str
    reasoning: str
    confidence: float
    domain: str
    factors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    step_id: str
    action: str
    description: str
    tool_name: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    result: dict[str, Any] | None = None


@dataclass
class Reflection:
    """A reflection on execution history."""
    reflection_id: str
    summary: str
    lessons: list[str]
    success_patterns: list[str]
    failure_patterns: list[str]
    recommendations: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class SuperagentEngine(BiasharaAgent):
    """
    Central reasoning engine for the Angavu intelligence system.

    Replaces the previous 33+ agent classes and 6 swarm directories
    with a single, more capable agent architecture.

    Architecture:
    - Single reasoning loop (think → plan → act → observe → reflect)
    - Domain modules loaded as needed (financial, credit, learning)
    - Unified working memory with episodic and semantic components
    - Self-improvement through outcome tracking
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="SuperagentEngine", description="Unified intelligence engine")
        self.config = config or {}

        # Memory systems
        self.working_memory = WorkingMemory()
        self.episodic_memory = EpisodicMemory()
        self.semantic_memory = SemanticMemory()

        # Tool registry
        self.tool_registry = ToolRegistry()

        # Domain modules loaded on demand
        self.modules: dict[str, Any] = {}

        # Execution history
        self._history: list[dict[str, Any]] = []
        self._thoughts: list[Thought] = []
        self._reflections: list[Reflection] = []
        self._execution_count = 0

    async def think(self, context: dict) -> dict:
        """
        Reason about the current state and determine next action.

        Analyzes the context using working memory and domain knowledge
        to produce a reasoned assessment of the situation.

        Args:
            context: Current context including request data, history, etc.

        Returns:
            Dict with reasoning, confidence, domain classification, and factors.
        """
        thought_id = str(uuid.uuid4())[:8]
        request_type = context.get("type", "unknown")
        domain = context.get("domain", "general")
        data = context.get("data", {})

        # Analyze context factors
        factors = []
        confidence = 0.7

        # Check working memory for relevant context
        memory_context = self.working_memory.get_context()
        if memory_context:
            factors.append("has_prior_context")
            confidence = min(confidence + 0.1, 1.0)

        # Check episodic memory for similar past situations
        if self.episodic_memory.episodes:
            factors.append(f"has_{len(self.episodic_memory.episodes)}_episodes")
            confidence = min(confidence + 0.05, 1.0)

        # Domain-specific reasoning
        if domain in self.modules:
            module = self.modules[domain]
            if hasattr(module, "analyze"):
                try:
                    analysis = await module.analyze(data)
                    factors.append(f"domain_analysis_{domain}")
                    confidence = min(confidence + 0.1, 1.0)
                except Exception as e:
                    logger.warning("domain_analysis_failed", domain=domain, error=str(e))

        # Determine action type based on request
        recommended_action = "process"
        if request_type in ("query", "analysis"):
            recommended_action = "analyze"
        elif request_type in ("create", "update"):
            recommended_action = "execute"
        elif request_type in ("report", "summary"):
            recommended_action = "aggregate"

        reasoning = (
            f"Request type '{request_type}' in domain '{domain}' "
            f"suggests '{recommended_action}' action. "
            f"Confidence: {confidence:.0%}. "
            f"Factors: {', '.join(factors) if factors else 'none'}."
        )

        thought = Thought(
            thought_id=thought_id,
            reasoning=reasoning,
            confidence=confidence,
            domain=domain,
            factors=factors,
        )
        self._thoughts.append(thought)

        # Store in working memory
        self.working_memory.add({
            "type": "thought",
            "thought_id": thought_id,
            "reasoning": reasoning,
            "domain": domain,
        })

        logger.info(
            "think_complete",
            thought_id=thought_id,
            domain=domain,
            confidence=confidence,
            action=recommended_action,
        )

        return {
            "thought_id": thought_id,
            "reasoning": reasoning,
            "confidence": confidence,
            "domain": domain,
            "recommended_action": recommended_action,
            "factors": factors,
        }

    async def plan(self, goal: str, context: dict) -> list[dict]:
        """
        Decompose a goal into actionable steps.

        Creates an execution plan with ordered steps, each potentially
        backed by a specific tool or domain module.

        Args:
            goal: The goal to achieve.
            context: Context including domain, data, and constraints.

        Returns:
            List of plan steps, each with action, description, and tool info.
        """
        domain = context.get("domain", "general")
        data = context.get("data", {})
        plan_id = str(uuid.uuid4())[:8]

        steps: list[PlanStep] = []

        # Step 1: Gather data
        steps.append(PlanStep(
            step_id=f"{plan_id}_1",
            action="gather_data",
            description=f"Gather relevant data for: {goal}",
            tool_name=None,
            params={"domain": domain, "data_keys": list(data.keys()) if isinstance(data, dict) else []},
        ))

        # Step 2: Analyze
        steps.append(PlanStep(
            step_id=f"{plan_id}_2",
            action="analyze",
            description=f"Analyze gathered data for domain: {domain}",
            tool_name=f"{domain}_analysis" if domain in self.modules else None,
            params={"domain": domain},
        ))

        # Step 3: Domain-specific execution
        if domain in self.modules:
            steps.append(PlanStep(
                step_id=f"{plan_id}_3",
                action="execute_domain",
                description=f"Execute {domain} domain logic",
                tool_name=domain,
                params={"domain": domain, "goal": goal},
            ))

        # Step 4: Synthesize results
        steps.append(PlanStep(
            step_id=f"{plan_id}_4",
            action="synthesize",
            description="Synthesize results and generate response",
            params={"goal": goal},
        ))

        plan_dicts = [
            {
                "step_id": s.step_id,
                "action": s.action,
                "description": s.description,
                "tool_name": s.tool_name,
                "params": s.params,
                "status": s.status,
            }
            for s in steps
        ]

        logger.info("plan_created", plan_id=plan_id, goal=goal, steps=len(steps))
        return plan_dicts

    async def act(self, action: dict) -> dict:
        """
        Execute an action and return the result.

        Dispatches to the appropriate tool or domain module
        based on the action specification.

        Args:
            action: Action specification with action type, params, etc.

        Returns:
            Dict with execution results.
        """
        action_type = action.get("action", "unknown")
        domain = action.get("domain", "general")
        params = action.get("params", {})

        start = time.time()
        result: dict[str, Any] = {
            "action": action_type,
            "domain": domain,
            "status": "completed",
        }

        try:
            # Try tool registry first
            tool_name = action.get("tool_name")
            if tool_name:
                tool = self.tool_registry.get(tool_name)
                if tool:
                    tool_result = await tool.execute(**params)
                    result["tool_result"] = tool_result
                    result["source"] = "tool"
                    return result

            # Try domain module
            if domain in self.modules:
                module = self.modules[domain]
                if hasattr(module, "execute"):
                    module_result = await module.execute(action)
                    result["module_result"] = module_result
                    result["source"] = "module"
                    return result

            # Default processing
            result["source"] = "default"
            result["message"] = f"No handler for action '{action_type}' in domain '{domain}'"

        except ValueError as e:
            result["status"] = "error"
            result["error"] = f"Invalid input: {str(e)}"
            logger.error("act_value_error", action=action_type, error=str(e))
        except KeyError as e:
            result["status"] = "error"
            result["error"] = f"Missing key: {str(e)}"
            logger.error("act_key_error", action=action_type, error=str(e))
        except ConnectionError as e:
            result["status"] = "error"
            result["error"] = f"Connection failed: {str(e)}"
            logger.error("act_connection_error", action=action_type, error=str(e))
        except TimeoutError as e:
            result["status"] = "error"
            result["error"] = f"Timeout: {str(e)}"
            logger.error("act_timeout", action=action_type, error=str(e))

        duration_ms = (time.time() - start) * 1000
        result["duration_ms"] = round(duration_ms, 2)
        return result

    async def observe(self, result: dict) -> dict:
        """
        Process the result of an action.

        Analyzes the action result, extracts key observations,
        and updates working memory.

        Args:
            result: The result from the act() phase.

        Returns:
            Dict with observations and extracted insights.
        """
        status = result.get("status", "unknown")
        domain = result.get("domain", "general")
        source = result.get("source", "unknown")

        observations = {
            "status": status,
            "domain": domain,
            "source": source,
            "insights": [],
            "anomalies": [],
        }

        # Check for errors
        if status == "error":
            error = result.get("error", "unknown error")
            observations["anomalies"].append(f"Error in {source}: {error}")

        # Extract domain-specific observations
        if "module_result" in result:
            module_result = result["module_result"]
            if isinstance(module_result, dict):
                for key, value in module_result.items():
                    if key not in ("status", "module"):
                        observations["insights"].append(f"{key}: {value}")

        if "tool_result" in result:
            observations["insights"].append(f"Tool execution produced result from {source}")

        # Store observation in working memory
        self.working_memory.add({
            "type": "observation",
            "status": status,
            "domain": domain,
            "insights": observations["insights"],
        })

        # Store in episodic memory
        await self.episodic_memory.store({
            "type": "action_result",
            "result": result,
            "observations": observations,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        logger.info(
            "observe_complete",
            status=status,
            domain=domain,
            insights=len(observations["insights"]),
            anomalies=len(observations["anomalies"]),
        )

        return observations

    async def reflect(self, history: list[dict]) -> dict:
        """
        Reflect on execution history and extract learnings.

        Analyzes patterns across multiple executions to identify
        what works, what doesn't, and how to improve.

        Args:
            history: List of past execution results.

        Returns:
            Dict with reflection insights, patterns, and recommendations.
        """
        reflection_id = str(uuid.uuid4())[:8]

        success_count = sum(1 for h in history if h.get("status") == "completed")
        error_count = sum(1 for h in history if h.get("status") == "error")
        total = len(history)

        success_rate = success_count / max(total, 1)

        # Identify patterns
        success_patterns = []
        failure_patterns = []

        for h in history:
            domain = h.get("domain", "unknown")
            source = h.get("source", "unknown")
            if h.get("status") == "completed":
                success_patterns.append(f"{domain}/{source}")
            else:
                failure_patterns.append(f"{domain}/{source}: {h.get('error', 'unknown')}")

        # Deduplicate patterns
        success_patterns = list(set(success_patterns))[:10]
        failure_patterns = list(set(failure_patterns))[:10]

        # Generate recommendations
        recommendations = []
        if success_rate < 0.5:
            recommendations.append("Success rate is below 50%. Review error patterns and adjust approach.")
        if error_count > 0:
            recommendations.append(f"Address {error_count} errors by improving error handling.")
        if not recommendations:
            recommendations.append("Performance is satisfactory. Continue current approach.")

        summary = (
            f"Reflected on {total} executions: {success_count} successful, "
            f"{error_count} errors. Success rate: {success_rate:.0%}."
        )

        reflection = Reflection(
            reflection_id=reflection_id,
            summary=summary,
            lessons=[f"Success rate: {success_rate:.0%}"],
            success_patterns=success_patterns,
            failure_patterns=failure_patterns,
            recommendations=recommendations,
        )
        self._reflections.append(reflection)

        # Update semantic memory with learnings
        if success_patterns:
            await self.semantic_memory.add_fact(
                "system", "has_success_patterns", success_patterns
            )

        logger.info(
            "reflect_complete",
            reflection_id=reflection_id,
            success_rate=success_rate,
            patterns=len(success_patterns),
        )

        return {
            "reflection_id": reflection_id,
            "summary": summary,
            "success_rate": success_rate,
            "lessons": reflection.lessons,
            "success_patterns": success_patterns,
            "failure_patterns": failure_patterns,
            "recommendations": recommendations,
        }

    async def run(self, task: str, context: Optional[dict] = None) -> dict:
        """
        Main execution loop. Takes a task and runs the
        think-plan-act-observe-reflect cycle until completion.

        Args:
            task: The task description or goal.
            context: Optional context for the task.

        Returns:
            Dict with full execution results including all cycle phases.
        """
        self._execution_count += 1
        self.status = AgentStatus.RUNNING
        start = time.time()

        ctx = context or {}
        ctx.setdefault("type", "task")
        ctx.setdefault("task", task)

        cycle_results = {
            "execution_id": self._execution_count,
            "task": task,
            "started_at": datetime.now(UTC).isoformat(),
            "phases": {},
        }

        try:
            # Phase 1: Think
            thought = await self.think(ctx)
            cycle_results["phases"]["think"] = thought

            # Phase 2: Plan
            plan = await self.plan(task, ctx)
            cycle_results["phases"]["plan"] = {"steps": plan, "count": len(plan)}

            # Phase 3: Execute plan steps
            step_results = []
            for step in plan:
                step_result = await self.act(step)
                step_results.append(step_result)

                # Phase 4: Observe each step
                observation = await self.observe(step_result)
                step["observation"] = observation

            cycle_results["phases"]["act"] = {
                "steps_executed": len(step_results),
                "results": step_results,
            }

            # Phase 5: Reflect on the full execution
            reflection = await self.reflect(step_results)
            cycle_results["phases"]["reflect"] = reflection

            # Store in history
            cycle_results["status"] = "completed"
            cycle_results["duration_ms"] = round((time.time() - start) * 1000, 2)
            self._history.append(cycle_results)

            self.status = AgentStatus.IDLE
            logger.info(
                "run_complete",
                execution_id=self._execution_count,
                task=task,
                duration_ms=cycle_results["duration_ms"],
                steps=len(plan),
            )

            return cycle_results

        except ValueError as e:
            self.status = AgentStatus.ERROR
            cycle_results["status"] = "error"
            cycle_results["error"] = f"Value error: {str(e)}"
            cycle_results["duration_ms"] = round((time.time() - start) * 1000, 2)
            logger.error("run_failed", execution_id=self._execution_count, error=str(e))
            return cycle_results
        except ConnectionError as e:
            self.status = AgentStatus.ERROR
            cycle_results["status"] = "error"
            cycle_results["error"] = f"Connection error: {str(e)}"
            cycle_results["duration_ms"] = round((time.time() - start)  * 1000, 2)
            logger.error("run_connection_failed", execution_id=self._execution_count, error=str(e))
            return cycle_results
        except TimeoutError as e:
            self.status = AgentStatus.ERROR
            cycle_results["status"] = "error"
            cycle_results["error"] = f"Timeout: {str(e)}"
            cycle_results["duration_ms"] = round((time.time() - start) * 1000, 2)
            logger.error("run_timeout", execution_id=self._execution_count, error=str(e))
            return cycle_results

    # ── Module Management ──────────────────────────────────────────

    def register_module(self, name: str, module: Any) -> None:
        """Register a domain module."""
        self.modules[name] = module
        logger.info("module_registered", name=name)

    def register_tool(self, tool: Tool) -> None:
        """Register a tool."""
        self.tool_registry.register(tool)

    def get_history(self, limit: int = 20) -> list[dict]:
        """Get recent execution history."""
        return self._history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get engine statistics."""
        return {
            "total_executions": self._execution_count,
            "total_thoughts": len(self._thoughts),
            "total_reflections": len(self._reflections),
            "registered_modules": list(self.modules.keys()),
            "registered_tools": self.tool_registry.list_tools(),
            "status": self.status.value,
        }
