"""
Eval Categories — Define what we measure and how.

Categories align with Angavu's core value proposition:
business reasoning, language quality, data extraction, planning, error recovery.

Each category defines:
- tasks: number of test cases
- metrics: what to measure (each scored 0.0–1.0)
- weight: importance in composite score
- description: what this category tests
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MetricType(str, Enum):
    """Types of metrics we can compute."""
    ACCURACY = "accuracy"               # Correctness of output
    CULTURAL_FIT = "cultural_fit"       # Culturally appropriate for East African context
    ACTIONABILITY = "actionability"     # Can the user act on this advice?
    SWAHILI_FLUENCY = "swahili_fluency" # Quality of Swahili output
    GRAMMAR = "grammar"                 # Grammatical correctness
    NATURALNESS = "naturalness"         # Does it sound human?
    CODE_SWITCH = "code_switch_handling" # Handles Swahili/English/Sheng mixing
    EXTRACTION_ACCURACY = "extraction_accuracy" # Structured data extraction correctness
    FIELD_COVERAGE = "field_coverage"   # How many fields were extracted
    HALLUCINATION_RATE = "hallucination_rate" # Invented data that doesn't exist
    STEP_COHERENCE = "step_coherence"   # Multi-step plan logical flow
    DEPENDENCY_CORRECTNESS = "dependency_correctness" # Task dependency ordering
    REALISM = "realism"                 # Is the plan achievable?
    COMPLETENESS = "completeness"       # Does it cover all aspects?
    ERROR_DETECTION = "error_detection" # Can it spot errors?
    RECOVERY_QUALITY = "recovery_quality" # Quality of error recovery
    DOOM_LOOP_AVOIDANCE = "doom_loop_avoidance" # Avoids retrying same failed approach


@dataclass
class EvalCategory:
    """Definition of an evaluation category."""
    name: str
    description: str
    metrics: list[MetricType]
    weight: float  # 0.0–1.0, relative importance
    task_count: int  # Number of test cases in this category
    data_file: str = ""  # Path to test data JSON

    def composite_score(self, metric_scores: dict[str, float]) -> float:
        """Compute weighted composite score from individual metric scores."""
        if not self.metrics:
            return 0.0
        # Equal weight per metric within category
        metric_weight = 1.0 / len(self.metrics)
        total = 0.0
        for metric in self.metrics:
            score = metric_scores.get(metric.value, 0.0)
            total += score * metric_weight
        return total


# ════════════════════════════════════════════════════════════════════
# The 5 Core Eval Categories
# ════════════════════════════════════════════════════════════════════

EVAL_CATEGORIES: dict[str, EvalCategory] = {
    "business_reasoning": EvalCategory(
        name="business_reasoning",
        description=(
            "Given a micro-entrepreneur's situation (transaction history, "
            "inventory, market conditions), generate accurate, actionable "
            "business advice in Swahili or English."
        ),
        metrics=[
            MetricType.ACCURACY,
            MetricType.CULTURAL_FIT,
            MetricType.ACTIONABILITY,
            MetricType.SWAHILI_FLUENCY,
        ],
        weight=0.30,
        task_count=50,
        data_file="data/business_scenarios.json",
    ),
    "language_quality": EvalCategory(
        name="language_quality",
        description=(
            "Evaluate Swahili, English, and Sheng text quality. "
            "Tests grammar, naturalness, code-switching, and dialect accuracy."
        ),
        metrics=[
            MetricType.GRAMMAR,
            MetricType.NATURALNESS,
            MetricType.CODE_SWITCH,
        ],
        weight=0.25,
        task_count=100,
        data_file="data/language_samples.json",
    ),
    "data_extraction": EvalCategory(
        name="data_extraction",
        description=(
            "From raw M-Pesa transaction descriptions (free-text, inconsistent "
            "formatting), extract structured business data."
        ),
        metrics=[
            MetricType.EXTRACTION_ACCURACY,
            MetricType.FIELD_COVERAGE,
            MetricType.HALLUCINATION_RATE,
        ],
        weight=0.20,
        task_count=200,
        data_file="data/mpesa_transactions.json",
    ),
    "planning_coherence": EvalCategory(
        name="planning_coherence",
        description=(
            "Generate multi-step business plans from user intent. "
            "Tests logical flow, dependency ordering, realism, completeness."
        ),
        metrics=[
            MetricType.STEP_COHERENCE,
            MetricType.DEPENDENCY_CORRECTNESS,
            MetricType.REALISM,
            MetricType.COMPLETENESS,
        ],
        weight=0.15,
        task_count=30,
        data_file="data/planning_tasks.json",
    ),
    "error_recovery": EvalCategory(
        name="error_recovery",
        description=(
            "Given intentionally broken or ambiguous scenarios, detect errors "
            "and recover gracefully. Tests doom-loop avoidance."
        ),
        metrics=[
            MetricType.ERROR_DETECTION,
            MetricType.RECOVERY_QUALITY,
            MetricType.DOOM_LOOP_AVOIDANCE,
        ],
        weight=0.10,
        task_count=40,
        data_file="data/error_scenarios.json",
    ),
}


def get_category(name: str) -> EvalCategory:
    """Get an eval category by name."""
    if name not in EVAL_CATEGORIES:
        raise ValueError(f"Unknown eval category: {name}. Available: {list(EVAL_CATEGORIES.keys())}")
    return EVAL_CATEGORIES[name]


def get_all_weights() -> dict[str, float]:
    """Get weight distribution across categories (should sum to 1.0)."""
    return {name: cat.weight for name, cat in EVAL_CATEGORIES.items()}
