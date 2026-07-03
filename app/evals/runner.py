"""
Eval Runner — Orchestrates full benchmark runs across categories and models.

Runs all eval categories, computes weighted composite scores,
generates comparison reports, and detects regressions.

Usage:
    runner = EvalRunner(harness)

    # Run all categories
    report = await runner.run_all()

    # Compare models
    comparison = await runner.compare_models(["qwen2.5-7b", "gemma3-1b"])

    # Check for regressions
    regressions = runner.detect_regressions(current_report, baseline_report)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.evals.categories import EVAL_CATEGORIES, get_all_weights
from app.evals.harness import EvalHarness, EvalSuite

logger = structlog.get_logger(__name__)


@dataclass
class EvalReport:
    """Full evaluation report across all categories."""
    model: str
    suites: Dict[str, EvalSuite] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    @property
    def weighted_score(self) -> float:
        """Compute weighted composite score across all categories."""
        weights = get_all_weights()
        total = 0.0
        weight_sum = 0.0
        for name, suite in self.suites.items():
            w = weights.get(name, 0.0)
            total += suite.avg_composite_score * w
            weight_sum += w
        return total / max(weight_sum, 0.001)

    @property
    def total_tasks(self) -> int:
        return sum(s.total_tasks for s in self.suites.values())

    @property
    def total_passed(self) -> int:
        return sum(s.passed_tasks for s in self.suites.values())

    @property
    def overall_pass_rate(self) -> float:
        return self.total_passed / max(self.total_tasks, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "weighted_score": round(self.weighted_score, 4),
            "total_tasks": self.total_tasks,
            "total_passed": self.total_passed,
            "overall_pass_rate": round(self.overall_pass_rate, 4),
            "duration_s": round((self.ended_at or time.time()) - self.started_at, 1),
            "categories": {
                name: suite.to_dict() for name, suite in self.suites.items()
            },
        }

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"═══ Eval Report: {self.model} ═══",
            f"Weighted Score: {self.weighted_score:.2%}",
            f"Tasks: {self.total_passed}/{self.total_tasks} passed ({self.overall_pass_rate:.1%})",
            "",
            "Category Breakdown:",
        ]
        weights = get_all_weights()
        for name, suite in self.suites.items():
            w = weights.get(name, 0)
            lines.append(
                f"  {name:25s} {suite.avg_composite_score:.2%} "
                f"(weight {w:.0%}, {suite.passed_tasks}/{suite.total_tasks} passed)"
            )
            for metric, avg in suite.metric_averages().items():
                lines.append(f"    └─ {metric}: {avg:.2%}")
        return "\n".join(lines)


class EvalRunner:
    """
    Orchestrates evaluation runs.

    Usage:
        runner = EvalRunner(harness)

        # Full benchmark
        report = await runner.run_all()

        # Save results
        runner.save_report(report, "reports/baseline.json")

        # Load and compare
        baseline = runner.load_report("reports/baseline.json")
        regressions = runner.detect_regressions(report, baseline)
    """

    def __init__(self, harness: EvalHarness, reports_dir: Optional[Path] = None):
        self._harness = harness
        self._reports_dir = reports_dir or Path(__file__).parent / "reports"
        self._logger = logger.bind(component="eval_runner")

    async def run_all(
        self,
        categories: Optional[List[str]] = None,
        max_tasks_per_category: Optional[int] = None,
    ) -> EvalReport:
        """Run all eval categories and produce a report."""
        target_categories = categories or list(EVAL_CATEGORIES.keys())
        model_name = "unknown"
        if self._harness._llm:
            model_name = getattr(self._harness._llm, "_model", "configured")

        report = EvalReport(model=model_name)
        self._logger.info("eval_run_start", model=model_name, categories=target_categories)

        for cat_name in target_categories:
            if cat_name not in EVAL_CATEGORIES:
                self._logger.warning("unknown_category", category=cat_name)
                continue

            suite = await self._harness.run_suite(
                cat_name, max_tasks=max_tasks_per_category
            )
            report.suites[cat_name] = suite

        report.ended_at = time.time()
        self._logger.info(
            "eval_run_complete",
            model=model_name,
            weighted_score=report.weighted_score,
            total_tasks=report.total_tasks,
        )
        return report

    async def compare_models(
        self,
        model_names: List[str],
        categories: Optional[List[str]] = None,
    ) -> Dict[str, EvalReport]:
        """
        Compare multiple models on the same eval suite.

        Note: This requires the harness to support model switching.
        For now, it runs with the configured model and labels results.
        """
        reports = {}
        for model_name in model_names:
            self._logger.info("eval_model_start", model=model_name)
            report = await self.run_all(categories=categories)
            report.model = model_name
            reports[model_name] = report
        return reports

    def detect_regressions(
        self,
        current: EvalReport,
        baseline: EvalReport,
        threshold: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        Detect score regressions between current and baseline reports.

        Returns list of regressions where score dropped by more than threshold.
        """
        regressions = []
        for name, current_suite in current.suites.items():
            if name not in baseline.suites:
                continue
            baseline_suite = baseline.suites[name]
            delta = current_suite.avg_composite_score - baseline_suite.avg_composite_score

            if delta < -threshold:
                regressions.append({
                    "category": name,
                    "baseline_score": round(baseline_suite.avg_composite_score, 4),
                    "current_score": round(current_suite.avg_composite_score, 4),
                    "delta": round(delta, 4),
                    "severity": "critical" if delta < -0.15 else "warning",
                })

        return regressions

    def save_report(self, report: EvalReport, filename: str) -> Path:
        """Save report to JSON file."""
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        path = self._reports_dir / filename
        with open(path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        self._logger.info("eval_report_saved", path=str(path))
        return path

    def load_report(self, filename: str) -> EvalReport:
        """Load a saved report from JSON."""
        path = self._reports_dir / filename
        with open(path) as f:
            data = json.load(f)

        # Reconstruct EvalReport from dict
        report = EvalReport(model=data["model"])
        report.started_at = data.get("started_at", 0)
        report.ended_at = data.get("ended_at")
        # Note: full deserialization of EvalSuite/EvalResult would be needed
        # for full round-trip. For now, store as dict for comparison.
        return report
