"""
Self-Evaluation Middleware — Quality gate between agent output and downstream publication.

After an agent produces output (act phase), this middleware evaluates
the output quality BEFORE it's published to downstream agents.

Two evaluation modes:
1. Rule-based (cheap, fast) — schema validation, range checks, format checks
2. LLM-based (expensive, thorough) — semantic quality, coherence, completeness

If quality score < threshold, the agent re-processes with a refined prompt
incorporating the evaluation feedback. This closes the Reflexion gap:
Reflexion critiques within a task; SelfEvaluation critiques the output
before it propagates to other agents.

Loop budget guards:
- max_iterations: max re-processing attempts (default: 3)
- max_tokens_per_loop: total token budget for one evaluation loop
- max_cost_per_loop: USD budget for one evaluation loop

Integration:
    evaluator = SelfEvaluationMiddleware()
    evaluator.register_agent("IntelligenceGenerator", rules=[...], threshold=0.8)
    # In BiasharaAgent._handle_event_inner(), after act() and before publish:
    result = await evaluator.evaluate_and_refine(agent, event, result)

Feature flag: Set agent's _self_evaluation to None to disable (default).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

from app.agents.base import AgentEvent

if TYPE_CHECKING:
    from app.agents.base import AgentResult, BiasharaAgent

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Evaluation Result
# ════════════════════════════════════════════════════════════════════


class EvaluationVerdict(StrEnum):
    """Verdict of the evaluation."""
    PASS = "pass"                      # Quality acceptable, publish downstream
    REFINE = "refine"                  # Quality below threshold, re-process with feedback
    REJECT = "reject"                  # Quality too low, don't publish (dead letter)
    BUDGET_EXCEEDED = "budget_exceeded"  # Loop budget exhausted, publish with warning


@dataclass
class EvaluationResult:
    """Result of evaluating an agent's output."""
    evaluation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    verdict: EvaluationVerdict = EvaluationVerdict.PASS
    score: float = 1.0                  # 0.0 - 1.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    refined_prompt_hint: str = ""       # Feedback for re-processing
    evaluation_mode: str = "rule"       # "rule" | "llm" | "hybrid"
    tokens_used: int = 0                # Tokens consumed by evaluation
    cost_usd: float = 0.0              # Cost of evaluation
    latency_ms: float = 0.0
    iteration: int = 1                  # Which iteration this is

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "verdict": self.verdict.value,
            "score": round(self.score, 4),
            "issues": self.issues,
            "suggestions": self.suggestions,
            "evaluation_mode": self.evaluation_mode,
            "tokens_used": self.tokens_used,
            "cost_usd": round(self.cost_usd, 8),
            "latency_ms": round(self.latency_ms, 2),
            "iteration": self.iteration,
        }


# ════════════════════════════════════════════════════════════════════
# Rule-Based Evaluators
# ════════════════════════════════════════════════════════════════════


@dataclass
class RuleResult:
    """Result of a single rule check."""
    passed: bool
    rule_name: str
    message: str = ""
    severity: str = "error"  # "error" | "warning"


class EvaluationRule:
    """
    Base class for rule-based evaluation rules.

    Rules are cheap (no LLM calls), fast (< 1ms), and deterministic.
    They check structural validity, range constraints, format, etc.
    """

    def __init__(self, name: str, severity: str = "error"):
        self.name = name
        self.severity = severity

    def evaluate(self, output: dict[str, Any], context: dict[str, Any]) -> RuleResult:
        """Evaluate the output against this rule. Override in subclasses."""
        raise NotImplementedError


class NonEmptyOutputRule(EvaluationRule):
    """Output must have non-empty data."""

    def __init__(self):
        super().__init__("non_empty_output", severity="error")

    def evaluate(self, output: dict[str, Any], context: dict[str, Any]) -> RuleResult:
        data = output.get("data")
        if data is None or (isinstance(data, str) and len(data.strip()) == 0):
            return RuleResult(False, self.name, "Output data is empty", self.severity)
        if isinstance(data, dict) and len(data) == 0:
            return RuleResult(False, self.name, "Output data is empty dict", self.severity)
        return RuleResult(True, self.name)


class SchemaValidationRule(EvaluationRule):
    """Output must conform to expected schema fields."""

    def __init__(self, required_fields: list[str]):
        super().__init__("schema_validation", severity="error")
        self._required_fields = required_fields

    def evaluate(self, output: dict[str, Any], context: dict[str, Any]) -> RuleResult:
        data = output.get("data", {})
        if not isinstance(data, dict):
            return RuleResult(True, self.name)  # Skip if not dict

        missing = [f for f in self._required_fields if f not in data]
        if missing:
            return RuleResult(
                False, self.name,
                f"Missing required fields: {missing}",
                self.severity,
            )
        return RuleResult(True, self.name)


class RangeCheckRule(EvaluationRule):
    """A numeric field must be within range."""

    def __init__(self, field_name: str, min_val: float, max_val: float):
        super().__init__(f"range_check_{field_name}", severity="error")
        self._field = field_name
        self._min = min_val
        self._max = max_val

    def evaluate(self, output: dict[str, Any], context: dict[str, Any]) -> RuleResult:
        data = output.get("data", {})
        if not isinstance(data, dict):
            return RuleResult(True, self.name)

        value = data.get(self._field)
        if value is not None and isinstance(value, (int, float)):
            if not (self._min <= value <= self._max):
                return RuleResult(
                    False, self.name,
                    f"{self._field}={value} outside [{self._min}, {self._max}]",
                    self.severity,
                )
        return RuleResult(True, self.name)


class OutputLengthRule(EvaluationRule):
    """Output string content must meet minimum length."""

    def __init__(self, min_length: int = 10, content_field: str = "content"):
        super().__init__("output_length", severity="warning")
        self._min_length = min_length
        self._content_field = content_field

    def evaluate(self, output: dict[str, Any], context: dict[str, Any]) -> RuleResult:
        data = output.get("data", {})
        if not isinstance(data, dict):
            return RuleResult(True, self.name)

        content = data.get(self._content_field, "")
        if isinstance(content, str) and len(content.strip()) < self._min_length:
            return RuleResult(
                False, self.name,
                f"Content length {len(content)} < minimum {self._min_length}",
                self.severity,
            )
        return RuleResult(True, self.name)


class ConfidenceThresholdRule(EvaluationRule):
    """Agent's confidence must exceed minimum."""

    def __init__(self, min_confidence: float = 0.5):
        super().__init__("confidence_threshold", severity="warning")
        self._min_confidence = min_confidence

    def evaluate(self, output: dict[str, Any], context: dict[str, Any]) -> RuleResult:
        confidence = output.get("confidence") or context.get("confidence", 1.0)
        if confidence < self._min_confidence:
            return RuleResult(
                False, self.name,
                f"Confidence {confidence:.2f} < minimum {self._min_confidence:.2f}",
                self.severity,
            )
        return RuleResult(True, self.name)


class NoErrorRule(EvaluationRule):
    """Output must not contain error indicators."""

    def __init__(self):
        super().__init__("no_error", severity="error")

    def evaluate(self, output: dict[str, Any], context: dict[str, Any]) -> RuleResult:
        if output.get("error"):
            return RuleResult(False, self.name, f"Error present: {output['error']}", self.severity)
        data = output.get("data", {})
        if isinstance(data, dict) and data.get("error"):
            return RuleResult(False, self.name, f"Data contains error: {data['error']}", self.severity)
        return RuleResult(True, self.name)


# ════════════════════════════════════════════════════════════════════
# LLM-Based Evaluator
# ════════════════════════════════════════════════════════════════════


class LLMEvaluator:
    """
    LLM-based quality evaluation for complex domains.

    Uses a lightweight model to evaluate output quality when
    rule-based checks are insufficient (e.g., coherence, relevance,
    completeness of intelligence reports).

    Cost: ~$0.0001 per evaluation (uses cloud_cheap tier).
    """

    EVALUATION_PROMPT = """You are a quality evaluator for an AI agent system.

Evaluate the following agent output for quality. Score 0.0-1.0.

CONTEXT:
- Agent: {agent_name}
- Task: {task_description}
- Event type: {event_type}

OUTPUT TO EVALUATE:
{output_json}

EVALUATE FOR:
1. Completeness — does the output address the task fully?
2. Coherence — is the output logically consistent?
3. Relevance — is the output on-topic?
4. Actionability — can downstream agents use this output?

Respond in JSON:
{{"score": 0.0-1.0, "issues": ["..."], "suggestions": ["..."]}}"""

    def __init__(self, inference_harness: Any | None = None):
        self._harness = inference_harness
        self._logger = logger.bind(component="llm_evaluator")

    async def evaluate(
        self,
        agent_name: str,
        output: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[float, list[str], list[str], int]:
        """
        Evaluate output quality using LLM.

        Returns: (score, issues, suggestions, tokens_used)
        """
        if not self._harness:
            # No harness available — return neutral score
            return 0.7, [], ["LLM evaluator not available"], 0

        prompt = self.EVALUATION_PROMPT.format(
            agent_name=agent_name,
            task_description=context.get("task", "unknown"),
            event_type=context.get("event_type", "unknown"),
            output_json=json.dumps(output, indent=2, default=str)[:2000],
        )

        try:
            result = await self._harness.infer(
                prompt=prompt,
                user_id=f"evaluator_{agent_name}",
                task_type="quality_evaluation",
                expect_json=True,
                max_tokens=256,
                temperature=0.1,  # Low temp for consistent scoring
                complexity="low",
            )

            if not result.success:
                self._logger.warning("llm_eval_failed", error=result.error)
                return 0.5, [f"Evaluation failed: {result.error}"], [], 0

            # Parse response
            try:
                parsed = json.loads(result.output)
                score = float(parsed.get("score", 0.5))
                issues = parsed.get("issues", [])
                suggestions = parsed.get("suggestions", [])
                tokens = result.input_tokens + result.output_tokens
                return score, issues, suggestions, tokens
            except (json.JSONDecodeError, ValueError) as e:
                self._logger.warning("llm_eval_parse_error", error=str(e))
                return 0.5, ["Failed to parse evaluation response"], [], result.input_tokens + result.output_tokens

        except Exception as exc:
            self._logger.error("llm_eval_exception", error=str(exc))
            return 0.5, [str(exc)], [], 0


# ════════════════════════════════════════════════════════════════════
# Self-Evaluation Middleware
# ════════════════════════════════════════════════════════════════════


@dataclass
class AgentEvaluationConfig:
    """Per-agent evaluation configuration."""
    agent_name: str
    quality_threshold: float = 0.7          # Minimum score to pass
    rejection_threshold: float = 0.3        # Below this = reject (don't publish)
    max_iterations: int = 3                 # Max re-processing attempts
    max_tokens_per_loop: int = 2000         # Token budget per evaluation loop
    max_cost_per_loop_usd: float = 0.01     # USD budget per evaluation loop
    enable_llm_evaluation: bool = False     # Use LLM for quality check
    llm_evaluation_threshold: float = 0.5   # Score below this triggers LLM eval
    rules: list[EvaluationRule] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "quality_threshold": self.quality_threshold,
            "rejection_threshold": self.rejection_threshold,
            "max_iterations": self.max_iterations,
            "max_tokens_per_loop": self.max_tokens_per_loop,
            "max_cost_per_loop_usd": self.max_cost_per_loop_usd,
            "enable_llm_evaluation": self.enable_llm_evaluation,
            "rule_count": len(self.rules),
        }


class SelfEvaluationMiddleware:
    """
    Quality gate between agent output and downstream event publication.

    Flow:
    1. Agent produces output (act phase completes)
    2. Rule-based evaluation runs (< 1ms, free)
    3. If score < threshold AND LLM eval enabled → LLM evaluation (~$0.0001)
    4. If score >= threshold → PASS → publish downstream
    5. If score < threshold → REFINE → re-process with feedback hint
    6. If max iterations reached → BUDGET_EXCEEDED → publish with warning
    7. If score < rejection_threshold → REJECT → dead letter queue

    Budget guards:
    - max_iterations prevents infinite loops
    - max_tokens_per_loop prevents runaway token usage
    - max_cost_per_loop_usd prevents runaway cost

    Feature flag: Agents not registered (no config) pass through unchanged.
    """

    def __init__(self, inference_harness: Any | None = None):
        self._configs: dict[str, AgentEvaluationConfig] = {}
        self._llm_evaluator = LLMEvaluator(inference_harness)
        self._evaluation_history: list[dict[str, Any]] = []
        self._max_history = 5000
        self._logger = logger.bind(component="self_evaluation")

        # Aggregate metrics
        self._total_evaluations: int = 0
        self._total_refines: int = 0
        self._total_rejects: int = 0
        self._total_budget_exceeded: int = 0

    def register_agent(
        self,
        agent_name: str,
        quality_threshold: float = 0.7,
        rejection_threshold: float = 0.3,
        max_iterations: int = 3,
        max_tokens_per_loop: int = 2000,
        max_cost_per_loop_usd: float = 0.01,
        enable_llm_evaluation: bool = False,
        rules: list[EvaluationRule] | None = None,
    ) -> None:
        """Register an agent for self-evaluation with custom config."""
        config = AgentEvaluationConfig(
            agent_name=agent_name,
            quality_threshold=quality_threshold,
            rejection_threshold=rejection_threshold,
            max_iterations=max_iterations,
            max_tokens_per_loop=max_tokens_per_loop,
            max_cost_per_loop_usd=max_cost_per_loop_usd,
            enable_llm_evaluation=enable_llm_evaluation,
            rules=rules or [],
        )
        self._configs[agent_name] = config
        self._logger.info(
            "agent_registered_for_evaluation",
            agent=agent_name,
            threshold=quality_threshold,
            rules=len(config.rules),
            llm_eval=enable_llm_evaluation,
        )

    def register_default_rules(self, agent_name: str) -> None:
        """Register a sensible default rule set for an agent."""
        default_rules = [
            NonEmptyOutputRule(),
            NoErrorRule(),
            ConfidenceThresholdRule(min_confidence=0.3),
        ]
        config = self._configs.get(agent_name)
        if config:
            config.rules.extend(default_rules)
        else:
            self.register_agent(agent_name, rules=default_rules)

    async def evaluate_and_refine(
        self,
        agent: BiasharaAgent,
        event: AgentEvent,
        result: AgentResult,
    ) -> AgentResult:
        """
        Evaluate agent output and refine if needed.

        This is the main entry point. Call after act() and before publish.

        Returns the original result if quality is acceptable, or a refined
        result if re-processing improved quality. Returns the last result
        if budget is exhausted.
        """
        config = self._configs.get(agent.name)
        if not config:
            # No evaluation configured for this agent — pass through
            return result

        total_tokens_used = 0
        total_cost_usd = 0.0

        for iteration in range(1, config.max_iterations + 1):
            # Budget check
            if total_tokens_used >= config.max_tokens_per_loop:
                self._logger.warning(
                    "evaluation_token_budget_exceeded",
                    agent=agent.name,
                    tokens_used=total_tokens_used,
                    max_tokens=config.max_tokens_per_loop,
                    iteration=iteration,
                )
                self._total_budget_exceeded += 1
                result.metadata = result.metadata or {}
                result.metadata["evaluation"] = {
                    "verdict": EvaluationVerdict.BUDGET_EXCEEDED.value,
                    "iterations": iteration - 1,
                    "tokens_used": total_tokens_used,
                }
                return result

            if total_cost_usd >= config.max_cost_per_loop_usd:
                self._logger.warning(
                    "evaluation_cost_budget_exceeded",
                    agent=agent.name,
                    cost_usd=total_cost_usd,
                    max_cost=config.max_cost_per_loop_usd,
                )
                self._total_budget_exceeded += 1
                result.metadata = result.metadata or {}
                result.metadata["evaluation"] = {
                    "verdict": EvaluationVerdict.BUDGET_EXCEEDED.value,
                    "iterations": iteration - 1,
                    "cost_usd": total_cost_usd,
                }
                return result

            # Evaluate
            eval_result = await self._evaluate(
                agent, event, result, config, iteration,
            )

            total_tokens_used += eval_result.tokens_used
            total_cost_usd += eval_result.cost_usd
            self._total_evaluations += 1

            # Export evaluation metrics to Prometheus
            self._export_evaluation_metrics(agent.name, eval_result)

            # Record history
            self._record_evaluation(agent.name, event, eval_result)

            # Decision
            if eval_result.verdict == EvaluationVerdict.PASS:
                result.metadata = result.metadata or {}
                result.metadata["evaluation"] = eval_result.to_dict()
                return result

            if eval_result.verdict == EvaluationVerdict.REJECT:
                self._total_rejects += 1
                result.success = False
                result.error = f"Quality rejected: {'; '.join(eval_result.issues)}"
                result.metadata = result.metadata or {}
                result.metadata["evaluation"] = eval_result.to_dict()
                return result

            # REFINE — re-process with feedback
            if iteration < config.max_iterations:
                self._total_refines += 1
                self._logger.info(
                    "evaluation_refining",
                    agent=agent.name,
                    iteration=iteration,
                    score=eval_result.score,
                    issues=eval_result.issues,
                )

                # Inject evaluation feedback into event metadata
                refined_event = self._create_refined_event(
                    event, eval_result, iteration,
                )

                # Re-process
                try:
                    result = await agent._handle_event_inner(refined_event)
                except Exception as exc:
                    self._logger.error(
                        "refine_reprocess_failed",
                        agent=agent.name,
                        iteration=iteration,
                        error=str(exc),
                    )
                    break

        # Max iterations reached — return last result with warning
        self._logger.warning(
            "evaluation_max_iterations",
            agent=agent.name,
            iterations=config.max_iterations,
        )
        result.metadata = result.metadata or {}
        result.metadata["evaluation"] = {
            "verdict": EvaluationVerdict.BUDGET_EXCEEDED.value,
            "iterations": config.max_iterations,
            "tokens_used": total_tokens_used,
            "cost_usd": total_cost_usd,
        }
        return result

    async def _evaluate(
        self,
        agent: BiasharaAgent,
        event: AgentEvent,
        result: AgentResult,
        config: AgentEvaluationConfig,
        iteration: int,
    ) -> EvaluationResult:
        """Run evaluation pipeline: rules → (optional) LLM."""
        start_time = time.time()
        issues: list[str] = []
        suggestions: list[str] = []
        total_tokens = 0

        # Stage 1: Rule-based evaluation
        rule_score = 1.0
        output_data = {
            "data": result.data,
            "error": result.error,
            "success": result.success,
            "confidence": getattr(result, "confidence", None),
        }
        context = {
            "event_type": event.event_type.value,
            "source": event.source,
            "task": f"{event.event_type.value}:{event.source}",
        }

        for rule in config.rules:
            rule_result = rule.evaluate(output_data, context)
            if not rule_result.passed:
                if rule_result.severity == "error":
                    rule_score -= 0.3
                else:
                    rule_score -= 0.1
                issues.append(f"[{rule.name}] {rule_result.message}")

        rule_score = max(0.0, min(1.0, rule_score))

        # If rules pass with high score, skip LLM eval
        if rule_score >= config.quality_threshold and not config.enable_llm_evaluation:
            return EvaluationResult(
                verdict=EvaluationVerdict.PASS,
                score=rule_score,
                issues=issues,
                evaluation_mode="rule",
                iteration=iteration,
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Stage 2: LLM-based evaluation (if enabled and score is borderline)
        llm_score = None
        if config.enable_llm_evaluation and rule_score < config.quality_threshold:
            llm_score, llm_issues, llm_suggestions, tokens = await self._llm_evaluator.evaluate(
                agent.name, output_data, context,
            )
            total_tokens += tokens
            issues.extend(llm_issues)
            suggestions.extend(llm_suggestions)

        # Compute final score
        if llm_score is not None:
            # Weighted average: rules 40%, LLM 60%
            final_score = 0.4 * rule_score + 0.6 * llm_score
        else:
            final_score = rule_score

        # Determine verdict
        if final_score >= config.quality_threshold:
            verdict = EvaluationVerdict.PASS
        elif final_score < config.rejection_threshold:
            verdict = EvaluationVerdict.REJECT
        else:
            verdict = EvaluationVerdict.REFINE

        # Build refinement hint
        refined_hint = ""
        if verdict == EvaluationVerdict.REFINE:
            refined_hint = (
                f"Previous output scored {final_score:.2f} (threshold: {config.quality_threshold}). "
                f"Issues: {'; '.join(issues)}. "
                f"Suggestions: {'; '.join(suggestions)}. "
                f"Please address these issues and re-generate."
            )

        return EvaluationResult(
            verdict=verdict,
            score=final_score,
            issues=issues,
            suggestions=suggestions,
            refined_prompt_hint=refined_hint,
            evaluation_mode="hybrid" if llm_score is not None else "rule",
            tokens_used=total_tokens,
            cost_usd=total_tokens * 0.0000001,  # Approximate
            latency_ms=(time.time() - start_time) * 1000,
            iteration=iteration,
        )

    def _create_refined_event(
        self,
        original_event: AgentEvent,
        eval_result: EvaluationResult,
        iteration: int,
    ) -> AgentEvent:
        """Create a refined event with evaluation feedback injected."""
        enriched_metadata = {
            **original_event.metadata,
            "self_evaluation_feedback": {
                "iteration": iteration,
                "previous_score": eval_result.score,
                "issues": eval_result.issues,
                "suggestions": eval_result.suggestions,
                "refined_hint": eval_result.refined_prompt_hint,
            },
        }
        return AgentEvent(
            event_type=original_event.event_type,
            source=original_event.source,
            payload=original_event.payload,
            event_id=original_event.event_id,
            timestamp=original_event.timestamp,
            correlation_id=original_event.correlation_id,
            metadata=enriched_metadata,
        )

    def _record_evaluation(
        self,
        agent_name: str,
        event: AgentEvent,
        eval_result: EvaluationResult,
    ) -> None:
        """Record evaluation in history."""
        self._evaluation_history.append({
            "agent": agent_name,
            "event_type": event.event_type.value,
            "evaluation": eval_result.to_dict(),
            "timestamp": time.time(),
        })
        if len(self._evaluation_history) > self._max_history:
            self._evaluation_history = self._evaluation_history[-self._max_history:]

    def _export_evaluation_metrics(
        self,
        agent_name: str,
        eval_result: EvaluationResult,
    ) -> None:
        """Export evaluation metrics to Prometheus if available."""
        try:
            from app.infrastructure.metrics import PROMETHEUS_AVAILABLE
            if not PROMETHEUS_AVAILABLE:
                return

            from prometheus_client import Counter, Histogram

            from app.infrastructure.metrics import _registry

            # Lazy-init metrics (avoid circular import at module level)
            if not hasattr(self, '_prom_score_hist'):
                self._prom_score_hist = Histogram(
                    "angavu_evaluation_score",
                    "Evaluation quality scores",
                    ["agent_name"],
                    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
                    registry=_registry,
                )
                self._prom_iter_hist = Histogram(
                    "angavu_evaluation_iterations",
                    "Number of evaluation iterations per agent call",
                    ["agent_name"],
                    buckets=[1, 2, 3, 4, 5],
                    registry=_registry,
                )
                self._prom_verdict_counter = Counter(
                    "angavu_evaluation_verdicts_total",
                    "Total evaluation verdicts",
                    ["agent_name", "verdict"],
                    registry=_registry,
                )

            self._prom_score_hist.labels(agent_name=agent_name).observe(eval_result.score)
            self._prom_iter_hist.labels(agent_name=agent_name).observe(eval_result.iteration)
            self._prom_verdict_counter.labels(
                agent_name=agent_name,
                verdict=eval_result.verdict.value,
            ).inc()

        except Exception:
            # Metrics export is best-effort
            pass

    # ── Monitoring ──────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get evaluation statistics."""
        return {
            "total_evaluations": self._total_evaluations,
            "total_refines": self._total_refines,
            "total_rejects": self._total_rejects,
            "total_budget_exceeded": self._total_budget_exceeded,
            "registered_agents": list(self._configs.keys()),
            "recent_evaluations": self._evaluation_history[-10:],
        }

    def get_agent_stats(self, agent_name: str) -> dict[str, Any]:
        """Get evaluation stats for a specific agent."""
        agent_evals = [
            e for e in self._evaluation_history
            if e["agent"] == agent_name
        ]
        if not agent_evals:
            return {"agent": agent_name, "evaluations": 0}

        scores = [e["evaluation"]["score"] for e in agent_evals]
        return {
            "agent": agent_name,
            "evaluations": len(agent_evals),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "refines": sum(1 for e in agent_evals if e["evaluation"]["verdict"] == "refine"),
            "rejects": sum(1 for e in agent_evals if e["evaluation"]["verdict"] == "reject"),
        }


# ════════════════════════════════════════════════════════════════════
# Singleton
# ════════════════════════════════════════════════════════════════════

_self_evaluation: SelfEvaluationMiddleware | None = None


def get_self_evaluation() -> SelfEvaluationMiddleware:
    """Get the singleton SelfEvaluationMiddleware."""
    global _self_evaluation
    if _self_evaluation is None:
        _self_evaluation = SelfEvaluationMiddleware()
    return _self_evaluation


def create_self_evaluation(
    inference_harness: Any | None = None,
) -> SelfEvaluationMiddleware:
    """Create a SelfEvaluationMiddleware with optional LLM support."""
    return SelfEvaluationMiddleware(inference_harness)
