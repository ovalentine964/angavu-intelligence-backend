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

from app.evals.harness import EvalHarness, EvalResult, EvalSuite
from app.evals.categories import EvalCategory, EVAL_CATEGORIES
from app.evals.runner import EvalRunner, EvalReport

__all__ = [
    "EvalHarness",
    "EvalResult",
    "EvalSuite",
    "EvalCategory",
    "EVAL_CATEGORIES",
    "EvalRunner",
    "EvalReport",
]
