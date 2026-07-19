"""
Tests for the Eval Framework.

Tests the harness, categories, runner, and scorer in isolation.
No LLM required — uses heuristic scorer and dry-run mode.
"""

from __future__ import annotations

import asyncio
import json

# Ensure app package is importable
import sys
import types
from pathlib import Path

import pytest

if "app.agents" not in sys.modules:
    _agents_pkg = types.ModuleType("app.agents")
    _agents_pkg.__path__ = []
    sys.modules["app.agents"] = _agents_pkg

if "app.agents.loops" not in sys.modules:
    _loops_pkg = types.ModuleType("app.agents.loops")
    _loops_pkg.__path__ = []
    sys.modules["app.agents.loops"] = _loops_pkg

from app.evals.categories import (
    EVAL_CATEGORIES,
    EvalCategory,
    MetricType,
    get_all_weights,
    get_category,
)
from app.evals.harness import (
    EvalHarness,
    EvalResult,
    EvalSuite,
    EvalTask,
    heuristic_scorer,
)
from app.evals.runner import EvalReport, EvalRunner

# ════════════════════════════════════════════════════════════════════
# Category Tests
# ════════════════════════════════════════════════════════════════════


class TestEvalCategories:
    """Test category definitions."""

    def test_all_categories_exist(self):
        expected = {"business_reasoning", "language_quality", "data_extraction",
                    "planning_coherence", "error_recovery"}
        assert set(EVAL_CATEGORIES.keys()) == expected

    def test_weights_sum_to_one(self):
        weights = get_all_weights()
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"

    def test_get_category_valid(self):
        cat = get_category("business_reasoning")
        assert cat.name == "business_reasoning"
        assert cat.weight == 0.30
        assert len(cat.metrics) == 4

    def test_get_category_invalid(self):
        with pytest.raises(ValueError, match="Unknown eval category"):
            get_category("nonexistent")

    def test_composite_score_calculation(self):
        cat = get_category("business_reasoning")
        # Perfect scores
        perfect = {m.value: 1.0 for m in cat.metrics}
        assert cat.composite_score(perfect) == 1.0

        # Zero scores
        zeros = {m.value: 0.0 for m in cat.metrics}
        assert cat.composite_score(zeros) == 0.0

        # Mixed scores
        mixed = {m.value: 0.5 for m in cat.metrics}
        assert abs(cat.composite_score(mixed) - 0.5) < 0.001


# ════════════════════════════════════════════════════════════════════
# Harness Tests
# ════════════════════════════════════════════════════════════════════


class TestEvalHarness:
    """Test the evaluation harness."""

    def test_load_tasks(self):
        harness = EvalHarness()
        tasks = harness.load_tasks("business_reasoning")
        assert len(tasks) > 0
        assert all(isinstance(t, EvalTask) for t in tasks)
        assert tasks[0].task_id != ""

    def test_task_from_dict(self):
        data = {
            "id": "test_001",
            "input": "What is 2+2?",
            "expected_output": "4",
            "rubric": {"accuracy_check": "4"},
        }
        task = EvalTask.from_dict(data, "test_category")
        assert task.task_id == "test_001"
        assert task.input_text == "What is 2+2?"
        assert task.category == "test_category"

    def test_heuristic_scorer_perfect_match(self):
        output = "Your profit is KSh 3,000"
        expected = "Your profit is KSh 3,000"
        rubric = {"required_elements": ["3,000"], "language": "en"}
        scores = heuristic_scorer(output, expected, rubric)
        assert scores["keyword_overlap"] > 0.8
        assert scores.get("rubric_coverage", 0) == 1.0

    def test_heuristic_scorer_poor_match(self):
        output = "I don't know"
        expected = "Your profit is KSh 3,000"
        rubric = {"required_elements": ["3,000"], "language": "en"}
        scores = heuristic_scorer(output, expected, rubric)
        assert scores["keyword_overlap"] < 0.3

    def test_heuristic_scorer_swahili_detection(self):
        output = "Faida yako ni KSh 3,000 kwa wiki hii"
        expected = "Faida"
        rubric = {"language": "sw"}
        scores = heuristic_scorer(output, expected, rubric)
        assert scores.get("language_match", 0) > 0

    def test_heuristic_scorer_forbidden_elements(self):
        output = "Sijui, hii ni ngumu sana"
        expected = "Answer"
        rubric = {"forbidden_elements": ["sijui"]}
        scores = heuristic_scorer(output, expected, rubric)
        assert scores.get("rubric_violations", 0) > 0

    def test_dry_run_mode(self):
        """Test harness without LLM (dry run)."""
        harness = EvalHarness()
        task = EvalTask(
            task_id="dry_001",
            category="business_reasoning",
            input_text="Test input",
            expected_output="Test output",
            rubric={},
        )
        result = asyncio.get_event_loop().run_until_complete(harness.run_task(task))
        assert isinstance(result, EvalResult)
        assert result.model == "dry_run"
        assert result.error is None


# ════════════════════════════════════════════════════════════════════
# Runner Tests
# ════════════════════════════════════════════════════════════════════


class TestEvalRunner:
    """Test the evaluation runner."""

    def test_report_weighted_score(self):
        report = EvalReport(model="test")
        # Add mock suites
        cat1 = EvalCategory("cat1", "test", [MetricType.ACCURACY], 0.6, 10)
        cat2 = EvalCategory("cat2", "test", [MetricType.ACCURACY], 0.4, 10)

        suite1 = EvalSuite(category="cat1", model="test")
        suite1.results = [
            EvalResult(task_id="1", category="cat1", composite_score=0.8, passed=True),
            EvalResult(task_id="2", category="cat1", composite_score=0.9, passed=True),
        ]

        suite2 = EvalSuite(category="cat2", model="test")
        suite2.results = [
            EvalResult(task_id="3", category="cat2", composite_score=0.5, passed=False),
        ]

        report.suites = {"cat1": suite1, "cat2": suite2}
        # Expected: 0.6 * 0.85 + 0.4 * 0.5 = 0.51 + 0.2 = 0.71
        assert abs(report.weighted_score - 0.71) < 0.01

    def test_detect_regressions(self):
        runner = EvalRunner(harness=EvalHarness())

        baseline = EvalReport(model="v1")
        baseline.suites["cat1"] = EvalSuite(category="cat1", model="v1")
        baseline.suites["cat1"].results = [
            EvalResult(task_id="1", category="cat1", composite_score=0.9, passed=True),
        ]

        current = EvalReport(model="v2")
        current.suites["cat1"] = EvalSuite(category="cat1", model="v2")
        current.suites["cat1"].results = [
            EvalResult(task_id="1", category="cat1", composite_score=0.7, passed=True),
        ]

        regressions = runner.detect_regressions(current, baseline, threshold=0.05)
        assert len(regressions) == 1
        assert regressions[0]["category"] == "cat1"
        assert regressions[0]["severity"] == "critical"  # delta < -0.15

    def test_report_summary(self):
        report = EvalReport(model="test-model")
        suite = EvalSuite(category="business_reasoning", model="test")
        suite.results = [
            EvalResult(task_id="1", category="business_reasoning",
                      metric_scores={"accuracy": 0.8, "cultural_fit": 0.9},
                      composite_score=0.85, passed=True),
        ]
        report.suites = {"business_reasoning": suite}

        summary = report.summary()
        assert "test-model" in summary
        assert "business_reasoning" in summary


# ════════════════════════════════════════════════════════════════════
# Data File Tests
# ════════════════════════════════════════════════════════════════════


class TestEvalData:
    """Test that eval data files are valid."""

    def test_business_scenarios_file_exists(self):
        data_path = Path(__file__).parent.parent / "app" / "evals" / "data" / "business_scenarios.json"
        assert data_path.exists(), f"Missing: {data_path}"

    def test_business_scenarios_valid_json(self):
        data_path = Path(__file__).parent.parent / "app" / "evals" / "data" / "business_scenarios.json"
        with open(data_path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) >= 5, "Need at least 5 test scenarios"

    def test_business_scenarios_have_required_fields(self):
        data_path = Path(__file__).parent.parent / "app" / "evals" / "data" / "business_scenarios.json"
        with open(data_path) as f:
            data = json.load(f)
        for item in data:
            assert "id" in item, f"Missing 'id' in {item}"
            assert "input" in item, f"Missing 'input' in {item}"
            assert "expected_output" in item, f"Missing 'expected_output' in {item}"
            assert len(item["input"]) > 10, f"Input too short for {item['id']}"
