"""
Eval Harness — Core evaluation engine.

Runs test cases through LLM and scores outputs against expected results.

Architecture:
    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │  Test Cases   │────▶│  LLM Service  │────▶│   Scorer     │
    │  (JSON data)  │     │  (inference)  │     │  (metrics)   │
    └──────────────┘     └──────────────┘     └──────────────┘
                                                    │
                                              ┌─────▼─────┐
                                              │  Results   │
                                              │  (JSON)    │
                                              └───────────┘

Each eval task:
1. Load test case (input + expected output + scoring rubric)
2. Send to LLM (or agent pipeline)
3. Score output against rubric using heuristics + optional LLM judge
4. Record result with metadata (model, latency, tokens)
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

from app.evals.categories import EvalCategory, MetricType, get_category

logger = structlog.get_logger(__name__)

# Path to eval data directory
EVAL_DATA_DIR = Path(__file__).parent / "data"


@dataclass
class EvalTask:
    """A single evaluation test case."""
    task_id: str
    category: str
    input_text: str
    expected_output: str
    rubric: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], category: str) -> "EvalTask":
        return cls(
            task_id=data.get("id", ""),
            category=category,
            input_text=data.get("input", ""),
            expected_output=data.get("expected_output", ""),
            rubric=data.get("rubric", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EvalResult:
    """Result of running a single eval task."""
    task_id: str
    category: str
    model: str = ""
    output: str = ""
    metric_scores: Dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0
    latency_ms: float = 0.0
    tokens_used: int = 0
    passed: bool = False
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "model": self.model,
            "output": self.output[:500],  # Truncate for storage
            "metric_scores": self.metric_scores,
            "composite_score": round(self.composite_score, 4),
            "latency_ms": round(self.latency_ms, 1),
            "tokens_used": self.tokens_used,
            "passed": self.passed,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class EvalSuite:
    """Results from running a full eval category."""
    category: str
    model: str
    results: List[EvalResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    @property
    def total_tasks(self) -> int:
        return len(self.results)

    @property
    def passed_tasks(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed_tasks / max(self.total_tasks, 1)

    @property
    def avg_composite_score(self) -> float:
        scores = [r.composite_score for r in self.results if r.error is None]
        return sum(scores) / max(len(scores), 1)

    @property
    def avg_latency_ms(self) -> float:
        latencies = [r.latency_ms for r in self.results if r.latency_ms > 0]
        return sum(latencies) / max(len(latencies), 1)

    def metric_averages(self) -> Dict[str, float]:
        """Average score per metric across all tasks."""
        metric_totals: Dict[str, List[float]] = {}
        for result in self.results:
            for metric, score in result.metric_scores.items():
                metric_totals.setdefault(metric, []).append(score)
        return {
            metric: sum(scores) / len(scores)
            for metric, scores in metric_totals.items()
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "model": self.model,
            "total_tasks": self.total_tasks,
            "passed_tasks": self.passed_tasks,
            "pass_rate": round(self.pass_rate, 4),
            "avg_composite_score": round(self.avg_composite_score, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "metric_averages": {k: round(v, 4) for k, v in self.metric_averages().items()},
            "duration_s": round((self.ended_at or time.time()) - self.started_at, 1),
        }


# Type for scoring functions
ScorerFunc = Callable[[str, str, Dict[str, Any]], Dict[str, float]]


def heuristic_scorer(output: str, expected: str, rubric: Dict[str, Any]) -> Dict[str, float]:
    """
    Heuristic scorer — no LLM required.

    Scores based on:
    - Length similarity
    - Keyword overlap
    - Format compliance
    - Presence of key elements from rubric
    """
    scores: Dict[str, float] = {}

    # Length similarity (penalize very short or very long outputs)
    expected_len = max(len(expected), 1)
    len_ratio = min(len(output), expected_len * 3) / expected_len
    length_score = 1.0 - abs(1.0 - len_ratio) * 0.5
    scores["length_similarity"] = max(0.0, min(1.0, length_score))

    # Keyword overlap
    expected_words = set(expected.lower().split())
    output_words = set(output.lower().split())
    if expected_words:
        overlap = len(expected_words & output_words) / len(expected_words)
        scores["keyword_overlap"] = round(overlap, 4)
    else:
        scores["keyword_overlap"] = 0.5

    # Rubric-based checks
    if rubric:
        required_elements = rubric.get("required_elements", [])
        if required_elements:
            found = sum(1 for elem in required_elements if elem.lower() in output.lower())
            scores["rubric_coverage"] = round(found / len(required_elements), 4)

        forbidden_elements = rubric.get("forbidden_elements", [])
        if forbidden_elements:
            violations = sum(1 for elem in forbidden_elements if elem.lower() in output.lower())
            scores["rubric_violations"] = round(violations / max(len(forbidden_elements), 1), 4)

        # Language check
        expected_lang = rubric.get("language", "")
        if expected_lang == "sw":
            # Simple Swahili detection: common Swahili words
            swahili_markers = {"ya", "na", "wa", "kwa", "ni", "la", "za", "katika", "kwenye", "pia"}
            found_sw = sum(1 for w in output.lower().split() if w in swahili_markers)
            scores["language_match"] = min(1.0, found_sw / 3) if found_sw > 0 else 0.0
        elif expected_lang == "en":
            scores["language_match"] = 1.0  # Default assumption

    return scores


class EvalHarness:
    """
    Core evaluation engine.

    Loads test cases, runs them through LLM/agent, scores outputs.

    Usage:
        harness = EvalHarness(llm_service=my_llm)

        # Run a single category
        suite = await harness.run_suite("business_reasoning")

        # Run with custom scorer
        suite = await harness.run_suite("business_reasoning", scorer=my_scorer)
    """

    def __init__(
        self,
        llm_service: Optional[Any] = None,
        agent_func: Optional[Callable[..., Coroutine[Any, Any, str]]] = None,
        scorer: Optional[ScorerFunc] = None,
        pass_threshold: float = 0.6,
    ):
        self._llm = llm_service
        self._agent_func = agent_func
        self._scorer = scorer or heuristic_scorer
        self._pass_threshold = pass_threshold
        self._logger = logger.bind(component="eval_harness")

    def load_tasks(self, category_name: str) -> List[EvalTask]:
        """Load test cases for a category from JSON file."""
        category = get_category(category_name)
        data_path = EVAL_DATA_DIR / category.data_file.replace("data/", "")

        if not data_path.exists():
            self._logger.warning("eval_data_missing", category=category_name, path=str(data_path))
            return []

        with open(data_path) as f:
            raw_tasks = json.load(f)

        tasks = [EvalTask.from_dict(t, category_name) for t in raw_tasks]
        self._logger.info("eval_tasks_loaded", category=category_name, count=len(tasks))
        return tasks

    async def run_task(self, task: EvalTask) -> EvalResult:
        """Run a single eval task and score the output."""
        start_time = time.time()
        result = EvalResult(task_id=task.task_id, category=task.category)

        try:
            # Generate output
            if self._agent_func:
                output = await self._agent_func(task.input_text)
            elif self._llm:
                from app.services.llm_service import LLMMessage
                response = await self._llm.complete(
                    messages=[LLMMessage(role="user", content=task.input_text)],
                )
                output = response.content if response.success else ""
                result.tokens_used = response.usage.get("total_tokens", 0)
                result.model = response.model
            else:
                # Dry run — score expected output against itself (baseline)
                output = task.expected_output
                result.model = "dry_run"

            result.output = output
            result.latency_ms = (time.time() - start_time) * 1000

            # Score
            category = get_category(task.category)
            raw_scores = self._scorer(output, task.expected_output, task.rubric)

            # Map raw scores to metric types
            metric_scores = {}
            for metric in category.metrics:
                # Try exact match, then partial match
                if metric.value in raw_scores:
                    metric_scores[metric.value] = raw_scores[metric.value]
                else:
                    # Use best available proxy
                    proxy_scores = [v for k, v in raw_scores.items() if v > 0]
                    metric_scores[metric.value] = sum(proxy_scores) / max(len(proxy_scores), 1) if proxy_scores else 0.0

            result.metric_scores = metric_scores
            result.composite_score = category.composite_score(metric_scores)
            result.passed = result.composite_score >= self._pass_threshold

        except Exception as exc:
            result.error = str(exc)
            result.latency_ms = (time.time() - start_time) * 1000
            self._logger.error("eval_task_failed", task_id=task.task_id, error=str(exc))

        return result

    async def run_suite(
        self,
        category_name: str,
        max_tasks: Optional[int] = None,
        concurrency: int = 5,
    ) -> EvalSuite:
        """Run all tasks in an eval category."""
        category = get_category(category_name)
        tasks = self.load_tasks(category_name)

        if max_tasks:
            tasks = tasks[:max_tasks]

        model_name = "unknown"
        if self._llm:
            model_name = getattr(self._llm, "_model", "configured")

        suite = EvalSuite(category=category_name, model=model_name)
        self._logger.info(
            "eval_suite_start",
            category=category_name,
            task_count=len(tasks),
            model=model_name,
        )

        # Run tasks with concurrency limit
        semaphore = asyncio.Semaphore(concurrency)

        async def run_with_limit(task: EvalTask) -> EvalResult:
            async with semaphore:
                return await self.run_task(task)

        results = await asyncio.gather(*[run_with_limit(t) for t in tasks])
        suite.results = list(results)
        suite.ended_at = time.time()

        self._logger.info(
            "eval_suite_complete",
            category=category_name,
            pass_rate=suite.pass_rate,
            avg_score=suite.avg_composite_score,
            avg_latency_ms=suite.avg_latency_ms,
        )

        return suite

    def set_pass_threshold(self, threshold: float) -> None:
        """Update the pass threshold (0.0–1.0)."""
        self._pass_threshold = max(0.0, min(1.0, threshold))
