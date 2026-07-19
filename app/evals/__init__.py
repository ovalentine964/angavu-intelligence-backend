"""
Angavu Intelligence — Evaluation Framework.

Unit tests for AI: benchmarks, quality metrics, and regression detection
for agent outputs across models.

Usage:
    from app.evals import EvalHarness, EvalRunner, EvalCategory

    harness = EvalHarness(llm_service)
    results = await harness.run_suite("business_reasoning")
    runner = EvalRunner(harness)
    report = await runner.run_all()
"""

from app.evals.categories import EVAL_CATEGORIES, EvalCategory
from app.evals.harness import EvalHarness, EvalResult, EvalSuite
from app.evals.runner import EvalReport, EvalRunner

__all__ = [
    "EVAL_CATEGORIES",
    "EvalCategory",
    "EvalHarness",
    "EvalReport",
    "EvalResult",
    "EvalRunner",
    "EvalSuite",
]
