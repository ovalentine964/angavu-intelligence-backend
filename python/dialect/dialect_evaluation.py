"""
Dialect Evaluation — Evaluate STT/TTS quality per dialect.

Provides comprehensive evaluation metrics for dialect models:
- Word Error Rate (WER) with bootstrap confidence intervals
- Character Error Rate (CER)
- Intent classification accuracy
- Entity extraction F1
- Code-switch detection accuracy
- Pronunciation adaptation effectiveness

Academic basis:
- Bootstrap (STA 341): Confidence intervals on all metrics
- Cross-validation: Model comparison and selection
- Non-parametric tests: Wilcoxon signed-rank for paired comparisons
"""

import json
import logging
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EvaluationSample:
    """A single evaluation sample."""
    sample_id: str
    reference: str  # Ground truth transcript
    hypothesis: str  # STT output
    dialect_code: str
    language: str
    intent_ref: Optional[str] = None
    intent_hyp: Optional[str] = None
    entities_ref: list = field(default_factory=list)
    entities_hyp: list = field(default_factory=list)
    asr_confidence: float = 0.0
    audio_duration_sec: float = 0.0


@dataclass
class DialectEvaluationReport:
    """Comprehensive evaluation report for a dialect."""
    dialect_code: str
    n_samples: int

    # STT metrics
    wer: float
    wer_ci95: tuple  # (lower, upper)
    cer: float
    cer_ci95: tuple

    # Intent metrics
    intent_accuracy: float
    intent_accuracy_ci95: tuple

    # Entity metrics
    entity_precision: float
    entity_recall: float
    entity_f1: float

    # Code-switch metrics
    code_switch_accuracy: float

    # Breakdown
    wer_by_language: dict = field(default_factory=dict)
    wer_by_confidence_bucket: dict = field(default_factory=dict)
    intent_confusion_matrix: dict = field(default_factory=dict)

    # Worst performing samples
    worst_wer_samples: list = field(default_factory=list)

    timestamp: float = 0.0


class EditDistance:
    """
    Computes edit distance (Levenshtein) for WER/CER calculation.
    """

    @staticmethod
    def word_error_rate(reference: list[str], hypothesis: list[str]) -> float:
        """Compute Word Error Rate."""
        if not reference:
            return 0.0 if not hypothesis else 1.0

        # Dynamic programming
        n = len(reference)
        m = len(hypothesis)
        dp = [[0] * (m + 1) for _ in range(n + 1)]

        for i in range(n + 1):
            dp[i][0] = i
        for j in range(m + 1):
            dp[0][j] = j

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if reference[i - 1] == hypothesis[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = min(
                        dp[i - 1][j] + 1,      # deletion
                        dp[i][j - 1] + 1,      # insertion
                        dp[i - 1][j - 1] + 1   # substitution
                    )

        return dp[n][m] / n

    @staticmethod
    def character_error_rate(reference: str, hypothesis: str) -> float:
        """Compute Character Error Rate."""
        ref_chars = list(reference)
        hyp_chars = list(hypothesis)
        return EditDistance.word_error_rate(ref_chars, hyp_chars)


class BootstrapConfidenceInterval:
    """
    Bootstrap confidence interval estimation.
    
    Academic basis: Bootstrap method (STA 341)
    """

    @staticmethod
    def compute(data: list[float], statistic_fn=None,
                n_bootstraps: int = 2000, alpha: float = 0.05,
                seed: int = 42) -> tuple:
        """
        Compute bootstrap CI for a statistic.
        
        Args:
            data: Observed data
            statistic_fn: Function to compute statistic (default: mean)
            n_bootstraps: Number of bootstrap resamples
            alpha: Significance level (0.05 for 95% CI)
            seed: Random seed for reproducibility
        
        Returns:
            (lower, upper) confidence interval
        """
        if statistic_fn is None:
            statistic_fn = np.mean

        if len(data) < 2:
            stat = statistic_fn(data)
            return (stat, stat)

        rng = np.random.RandomState(seed)
        bootstrap_stats = []

        for _ in range(n_bootstraps):
            sample = rng.choice(data, size=len(data), replace=True)
            bootstrap_stats.append(statistic_fn(sample))

        bootstrap_stats.sort()
        lower_idx = int((alpha / 2) * n_bootstraps)
        upper_idx = int((1 - alpha / 2) * n_bootstraps) - 1

        return (
            bootstrap_stats[max(0, lower_idx)],
            bootstrap_stats[min(len(bootstrap_stats) - 1, upper_idx)]
        )


class NonparametricTests:
    """
    Non-parametric statistical tests for model comparison.
    
    Academic basis: Non-parametric methods (no distributional assumptions)
    """

    @staticmethod
    def wilcoxon_signed_rank(x: list[float], y: list[float]) -> dict:
        """
        Wilcoxon signed-rank test for paired samples.
        Tests H0: median(x - y) = 0.
        
        Returns test statistic and approximate p-value.
        """
        differences = [a - b for a, b in zip(x, y)]
        differences = [d for d in differences if d != 0]

        if not differences:
            return {"statistic": 0.0, "p_value": 1.0, "significant": False}

        n = len(differences)
        abs_diff = [abs(d) for d in differences]
        ranks = np.argsort(np.argsort(abs_diff)) + 1  # Rank

        # Signed ranks
        signed_ranks = []
        for d, r in zip(differences, ranks):
            signed_ranks.append(r if d > 0 else -r)

        # W+ statistic
        w_plus = sum(r for r in signed_ranks if r > 0)

        # Normal approximation for large samples
        if n > 20:
            mean_w = n * (n + 1) / 4
            std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
            z = (w_plus - mean_w) / std_w
            # Two-tailed p-value
            from scipy import stats
            p_value = 2 * (1 - stats.norm.cdf(abs(z)))
        else:
            # Exact distribution for small samples (simplified)
            p_value = 0.5  # Placeholder

        return {
            "statistic": float(w_plus),
            "p_value": float(p_value),
            "significant": p_value < 0.05
        }

    @staticmethod
    def bootstrap_hypothesis_test(x: list[float], y: list[float],
                                   n_bootstraps: int = 1000) -> dict:
        """
        Bootstrap hypothesis test: H0: mean(x) = mean(y).
        """
        rng = np.random.RandomState(42)
        observed_diff = np.mean(x) - np.mean(y)

        # Pool the data
        pooled = x + y
        n_x = len(x)

        count = 0
        for _ in range(n_bootstraps):
            sample = rng.choice(pooled, size=len(pooled), replace=True)
            boot_x = sample[:n_x]
            boot_y = sample[n_x:]
            boot_diff = np.mean(boot_x) - np.mean(boot_y)
            if abs(boot_diff) >= abs(observed_diff):
                count += 1

        p_value = count / n_bootstraps

        return {
            "observed_difference": float(observed_diff),
            "p_value": float(p_value),
            "significant": p_value < 0.05
        }


class DialectEvaluator:
    """
    Comprehensive evaluator for dialect STT/TTS models.
    """

    def __init__(self):
        self.edit_distance = EditDistance()
        self.bootstrap = BootstrapConfidenceInterval()
        self.nonparam = NonparametricTests()

    def evaluate(self, samples: list[EvaluationSample],
                 n_bootstraps: int = 2000) -> DialectEvaluationReport:
        """
        Run full evaluation on a set of samples.
        
        Returns comprehensive report with bootstrap CIs.
        """
        if not samples:
            return DialectEvaluationReport(
                dialect_code="unknown", n_samples=0,
                wer=0, wer_ci95=(0, 0), cer=0, cer_ci95=(0, 0),
                intent_accuracy=0, intent_accuracy_ci95=(0, 0),
                entity_precision=0, entity_recall=0, entity_f1=0,
                code_switch_accuracy=0
            )

        dialect_code = samples[0].dialect_code

        # WER computation
        wer_scores = []
        for sample in samples:
            ref_words = sample.reference.lower().split()
            hyp_words = sample.hypothesis.lower().split()
            wer = self.edit_distance.word_error_rate(ref_words, hyp_words)
            wer_scores.append(min(1.0, wer))

        wer_mean = float(np.mean(wer_scores))
        wer_ci = self.bootstrap.compute(wer_scores, n_bootstraps=n_bootstraps)

        # CER computation
        cer_scores = []
        for sample in samples:
            cer = self.edit_distance.character_error_rate(
                sample.reference.lower(), sample.hypothesis.lower()
            )
            cer_scores.append(min(1.0, cer))

        cer_mean = float(np.mean(cer_scores))
        cer_ci = self.bootstrap.compute(cer_scores, n_bootstraps=n_bootstraps)

        # Intent accuracy
        intent_correct = []
        for sample in samples:
            if sample.intent_ref and sample.intent_hyp:
                intent_correct.append(1.0 if sample.intent_ref == sample.intent_hyp else 0.0)

        intent_acc = float(np.mean(intent_correct)) if intent_correct else 0.0
        intent_ci = self.bootstrap.compute(intent_correct, n_bootstraps=n_bootstraps) if intent_correct else (0, 0)

        # Entity metrics
        entity_p, entity_r, entity_f = self._compute_entity_metrics(samples)

        # Code-switch accuracy
        cs_accuracy = self._compute_code_switch_accuracy(samples)

        # WER by language
        wer_by_lang = self._compute_wer_by_group(samples, lambda s: s.language)

        # WER by confidence bucket
        wer_by_conf = self._compute_wer_by_confidence(samples)

        # Intent confusion matrix
        intent_cm = self._compute_intent_confusion_matrix(samples)

        # Worst samples
        worst_indices = np.argsort(wer_scores)[-10:][::-1]
        worst_samples = [
            {
                "id": samples[i].sample_id,
                "reference": samples[i].reference[:100],
                "hypothesis": samples[i].hypothesis[:100],
                "wer": wer_scores[i],
                "language": samples[i].language
            }
            for i in worst_indices
        ]

        return DialectEvaluationReport(
            dialect_code=dialect_code,
            n_samples=len(samples),
            wer=wer_mean,
            wer_ci95=wer_ci,
            cer=cer_mean,
            cer_ci95=cer_ci,
            intent_accuracy=intent_acc,
            intent_accuracy_ci95=intent_ci,
            entity_precision=entity_p,
            entity_recall=entity_r,
            entity_f1=entity_f,
            code_switch_accuracy=cs_accuracy,
            wer_by_language=wer_by_lang,
            wer_by_confidence_bucket=wer_by_conf,
            intent_confusion_matrix=intent_cm,
            worst_wer_samples=worst_samples,
            timestamp=float(len(samples))  # placeholder
        )

    def compare_models(self, samples_a: list[EvaluationSample],
                       samples_b: list[EvaluationSample],
                       label_a: str = "Model A",
                       label_b: str = "Model B") -> dict:
        """
        Compare two models using paired evaluation.
        Uses Wilcoxon signed-rank test (non-parametric).
        """
        # Compute per-sample WER for both models
        wer_a = []
        wer_b = []

        # Match samples by ID
        b_by_id = {s.sample_id: s for s in samples_b}
        for sample_a in samples_a:
            sample_b = b_by_id.get(sample_a.sample_id)
            if sample_b is None:
                continue

            ref_words = sample_a.reference.lower().split()
            wer_a.append(self.edit_distance.word_error_rate(
                ref_words, sample_a.hypothesis.lower().split()
            ))
            wer_b.append(self.edit_distance.word_error_rate(
                ref_words, sample_b.hypothesis.lower().split()
            ))

        if not wer_a:
            return {"error": "No matched samples"}

        # Wilcoxon test
        wilcoxon = self.nonparam.wilcoxon_signed_rank(wer_a, wer_b)

        # Bootstrap test
        bootstrap_test = self.nonparam.bootstrap_hypothesis_test(wer_a, wer_b)

        return {
            f"{label_a}_mean_wer": float(np.mean(wer_a)),
            f"{label_b}_mean_wer": float(np.mean(wer_b)),
            "improvement": float(np.mean(wer_a) - np.mean(wer_b)),
            "wilcoxon": wilcoxon,
            "bootstrap_test": bootstrap_test,
            "n_paired_samples": len(wer_a)
        }

    # ── Private helpers ──────────────────────────────────────

    def _compute_entity_metrics(self, samples: list[EvaluationSample]) -> tuple:
        """Compute entity-level precision, recall, F1."""
        tp, fp, fn = 0, 0, 0

        for sample in samples:
            ref_set = set(
                (e.get("start", 0), e.get("end", 0), e.get("type", ""))
                for e in sample.entities_ref
            )
            hyp_set = set(
                (e.get("start", 0), e.get("end", 0), e.get("type", ""))
                for e in sample.entities_hyp
            )

            tp += len(ref_set & hyp_set)
            fp += len(hyp_set - ref_set)
            fn += len(ref_set - hyp_set)

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)

        return float(precision), float(recall), float(f1)

    def _compute_code_switch_accuracy(self, samples: list[EvaluationSample]) -> float:
        """Compute code-switch detection accuracy (simplified)."""
        correct = 0
        total = 0
        for sample in samples:
            if sample.language in ("sheng", "code-switch"):
                # Check if the model correctly handles code-switched input
                if sample.intent_ref == sample.intent_hyp:
                    correct += 1
                total += 1
        return correct / max(total, 1)

    def _compute_wer_by_group(self, samples: list[EvaluationSample],
                               group_fn) -> dict:
        """Compute mean WER grouped by a function."""
        groups = defaultdict(list)
        for sample in samples:
            ref_words = sample.reference.lower().split()
            hyp_words = sample.hypothesis.lower().split()
            wer = self.edit_distance.word_error_rate(ref_words, hyp_words)
            groups[group_fn(sample)].append(min(1.0, wer))

        return {k: float(np.mean(v)) for k, v in groups.items()}

    def _compute_wer_by_confidence(self, samples: list[EvaluationSample]) -> dict:
        """Compute WER bucketed by ASR confidence."""
        buckets = {"low": [], "medium": [], "high": []}
        for sample in samples:
            ref_words = sample.reference.lower().split()
            hyp_words = sample.hypothesis.lower().split()
            wer = self.edit_distance.word_error_rate(ref_words, hyp_words)

            if sample.asr_confidence < 0.5:
                buckets["low"].append(min(1.0, wer))
            elif sample.asr_confidence < 0.8:
                buckets["medium"].append(min(1.0, wer))
            else:
                buckets["high"].append(min(1.0, wer))

        return {k: float(np.mean(v)) if v else 0.0 for k, v in buckets.items()}

    def _compute_intent_confusion_matrix(self, samples: list[EvaluationSample]) -> dict:
        """Compute intent confusion matrix."""
        cm = defaultdict(lambda: defaultdict(int))
        for sample in samples:
            if sample.intent_ref and sample.intent_hyp:
                cm[sample.intent_ref][sample.intent_hyp] += 1
        return {k: dict(v) for k, v in cm.items()}


def evaluate_dialect(samples: list[dict], dialect_code: str) -> dict:
    """Factory function for dialect evaluation."""
    eval_samples = [
        EvaluationSample(
            sample_id=s.get("id", ""),
            reference=s.get("reference", ""),
            hypothesis=s.get("hypothesis", ""),
            dialect_code=dialect_code,
            language=s.get("language", "sw"),
            intent_ref=s.get("intent_ref"),
            intent_hyp=s.get("intent_hyp"),
            entities_ref=s.get("entities_ref", []),
            entities_hyp=s.get("entities_hyp", []),
            asr_confidence=s.get("asr_confidence", 0.7)
        )
        for s in samples
    ]

    evaluator = DialectEvaluator()
    report = evaluator.evaluate(eval_samples)

    return {
        "dialect_code": report.dialect_code,
        "n_samples": report.n_samples,
        "wer": report.wer,
        "wer_ci95": report.wer_ci95,
        "cer": report.cer,
        "cer_ci95": report.cer_ci95,
        "intent_accuracy": report.intent_accuracy,
        "entity_f1": report.entity_f1,
        "code_switch_accuracy": report.code_switch_accuracy,
        "wer_by_language": report.wer_by_language,
        "worst_samples": report.worst_wer_samples
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            samples = json.load(f)
        dialect = sys.argv[2] if len(sys.argv) > 2 else "sw-KE-urban"
        result = evaluate_dialect(samples, dialect)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python dialect_evaluation.py <samples.json> [dialect_code]")
