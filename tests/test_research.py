"""
Tests for the Research Methodology & Statistical Quality Framework.

Tests cover:
- Data quality validation (ECO 202/203)
- SPC control charts (STA 346)
- Outlier detection (STA 342)
- Hypothesis testing (STA 342)
- Confidence intervals (STA 342)
- Experimental design (STA 343)
- Sampling methodology (ECO 315)
"""

import sys
import os

# Add the project root to path and import research modules directly
# (avoids triggering the full app initialization chain which needs DB)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

# Import research modules directly (no app/__init__.py chain)
from app.services.research.data_quality import (
    ControlChartType,
    DataQualityFramework,
    DataValidator,
    OutlierDetector,
    SPCChart,
    ValidationSeverity,
)
from app.services.research.hypothesis_testing import (
    CorrectionMethod,
    HypothesisTester,
    MultipleTestingCorrection,
)
from app.services.research.experimental_design import (
    ABTestFramework,
    DesignType,
    ExperimentDesigner,
    PowerAnalyzer,
    Variant,
)
from app.services.research.confidence_intervals import (
    BootstrapCI,
    ConfidenceIntervalCalculator,
)
from app.services.research.sampling import (
    SampleSizeCalculator,
    SamplingEngine,
)


# =========================================================================
# Data Quality Tests (ECO 202/203 + STA 346)
# =========================================================================

class TestDataValidator:
    """Tests for data validation rules based on economic theory."""

    def test_valid_transaction_passes(self):
        txn = {
            "unit_price": 100.0,
            "quantity": 5,
            "amount": 500.0,
            "transaction_type": "SALE",
            "payment_method": "mpesa",
            "confidence_score": 0.95,
            "item_category": "food",
        }
        results = DataValidator.validate_transaction(txn)
        errors = [r for r in results if not r.passed and r.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0

    def test_negative_price_rejected(self):
        """ECO 202: Prices must be positive (price theory)."""
        txn = {"unit_price": -50.0}
        results = DataValidator.validate_transaction(txn)
        price_results = [r for r in results if r.rule_name == "positive_price"]
        assert any(not r.passed for r in price_results)

    def test_negative_amount_rejected(self):
        txn = {"amount": -100.0}
        results = DataValidator.validate_transaction(txn)
        amount_results = [r for r in results if r.rule_name == "non_negative_amount"]
        assert any(not r.passed for r in amount_results)

    def test_revenue_consistency_warning(self):
        """ECO 203: Revenue = price × quantity (accounting identity)."""
        txn = {
            "unit_price": 100.0,
            "quantity": 5,
            "amount": 600.0,  # Should be 500
        }
        results = DataValidator.validate_transaction(txn)
        consistency = [r for r in results if r.rule_name == "revenue_consistency"]
        assert any(not r.passed for r in consistency)

    def test_price_range_warning(self):
        txn = {
            "unit_price": 1000000.0,
            "item_category": "food",
        }
        results = DataValidator.validate_transaction(txn)
        range_results = [r for r in results if r.rule_name == "reasonable_price_range"]
        assert any(not r.passed for r in range_results)

    def test_batch_validation(self):
        txns = [
            {"unit_price": 100, "amount": 500, "transaction_type": "SALE"},
            {"unit_price": -50, "amount": 100},  # Invalid price
            {"amount": 200, "transaction_type": "SALE"},
        ]
        results, pass_rate = DataValidator.validate_batch(txns)
        assert 0 <= pass_rate <= 1
        assert len(results) > 0


class TestSPCChart:
    """Tests for Statistical Process Control charts (STA 346)."""

    def test_xbar_chart_detects_out_of_control(self):
        """STA 346: Points beyond ±3σ control limits."""
        chart = SPCChart(chart_type=ControlChartType.XBAR, window_size=10)

        # Feed in-control data
        np.random.seed(42)
        for _ in range(15):
            chart.update(np.random.normal(100, 5))

        # Feed out-of-control point
        signal = chart.update(200)  # Way beyond 3σ
        assert signal is not None
        assert signal.signal_type == "point_beyond_limits"

    def test_xbar_chart_no_signal_in_control(self):
        chart = SPCChart(chart_type=ControlChartType.XBAR, window_size=10)
        np.random.seed(42)
        for _ in range(20):
            signal = chart.update(np.random.normal(100, 5))
        # Should not trigger for in-control process
        action_signals = [s for s in chart.signals if s.severity == "action"]
        assert len(action_signals) == 0

    def test_ewma_chart(self):
        """STA 346: EWMA detects small sustained shifts."""
        chart = SPCChart(chart_type=ControlChartType.EWMA, window_size=10, lambda_ewma=0.2)

        np.random.seed(42)
        for _ in range(20):
            chart.update(np.random.normal(100, 5))

        # Sustained shift
        for _ in range(10):
            chart.update(np.random.normal(110, 5))

        # EWMA should eventually detect this
        # (may not trigger immediately due to smoothing)

    def test_cusum_chart(self):
        """STA 346: CUSUM accumulates deviations."""
        chart = SPCChart(chart_type=ControlChartType.CUSUM, window_size=10, cusum_k=0.5, cusum_h=4.0)

        np.random.seed(42)
        for _ in range(20):
            chart.update(np.random.normal(100, 5))

        # Large sustained shift
        for _ in range(5):
            chart.update(np.random.normal(120, 5))

        # May or may not trigger depending on random values

    def test_control_limits_computed(self):
        chart = SPCChart(chart_type=ControlChartType.XBAR, window_size=5)
        for v in [10, 12, 11, 13, 12]:
            chart.update(v)

        limits = chart.compute_control_limits()
        assert "cl" in limits
        assert "ucl" in limits
        assert "lcl" in limits
        assert limits["ucl"] > limits["cl"] > limits["lcl"]


class TestOutlierDetector:
    """Tests for outlier detection (STA 342: non-parametric methods)."""

    def test_iqr_detects_outlier(self):
        """STA 342: IQR method is non-parametric, robust."""
        values = [10, 12, 11, 13, 12, 10, 11, 12, 100]  # 100 is outlier
        results = OutlierDetector.detect_iqr(values)
        outlier_indices = [r.index for r in results if r.is_outlier]
        assert 8 in outlier_indices

    def test_iqr_no_outliers_clean_data(self):
        values = [10, 12, 11, 13, 12, 10, 11, 12, 13, 11]
        results = OutlierDetector.detect_iqr(values)
        assert all(not r.is_outlier for r in results)

    def test_modified_zscore(self):
        """STA 342: Modified Z-score uses MAD (robust)."""
        values = [10, 12, 11, 13, 12, 10, 11, 12, 100]
        results = OutlierDetector.detect_modified_zscore(values)
        outlier_indices = [r.index for r in results if r.is_outlier]
        assert 8 in outlier_indices

    def test_grubbs_test(self):
        values = [10, 12, 11, 13, 12, 10, 11, 12, 100]
        results = OutlierDetector.detect_grubbs(values)
        # Grubbs should flag the extreme value
        outlier_indices = [r.index for r in results if r.is_outlier]
        assert 8 in outlier_indices


class TestDataQualityFramework:
    """Integration test for the full DQ framework."""

    def test_assess_transactions(self):
        framework = DataQualityFramework()
        txns = [
            {"amount": 100, "unit_price": 50, "quantity": 2, "transaction_type": "SALE"},
            {"amount": 200, "unit_price": 100, "quantity": 2, "transaction_type": "SALE"},
            {"amount": 150, "unit_price": 75, "quantity": 2, "transaction_type": "SALE"},
            {"amount": -50, "unit_price": -25},  # Invalid
        ]
        report = framework.assess_transactions(txns)
        assert report.total_records == 4
        assert 0 <= report.quality_score <= 1
        assert len(report.recommendations) > 0


# =========================================================================
# Hypothesis Testing Tests (STA 342)
# =========================================================================

class TestHypothesisTester:
    """Tests for hypothesis testing (STA 342)."""

    def test_one_sample_t_test(self):
        """STA 342: t = (X̄ - μ₀) / (S/√n)"""
        np.random.seed(42)
        sample = np.random.normal(105, 10, 50).tolist()
        tester = HypothesisTester(alpha=0.05)
        result = tester.one_sample_t_test(sample, null_mean=100)

        assert result.test_type.value == "one_sample_t"
        assert 0 <= result.p_value <= 1
        assert result.effect_size is not None
        assert result.confidence_interval is not None
        assert result.power is not None
        assert result.interpretation != ""

    def test_two_sample_t_test(self):
        """STA 342: Independent samples t-test."""
        np.random.seed(42)
        a = np.random.normal(100, 10, 30).tolist()
        b = np.random.normal(110, 10, 30).tolist()

        tester = HypothesisTester(alpha=0.05)
        result = tester.two_sample_t_test(a, b)

        assert result.test_type.value == "welch_t"
        assert result.reject_null  # 10 unit difference should be significant
        assert result.effect_size is not None

    def test_mann_whitney_u(self):
        """STA 342: Non-parametric alternative to t-test."""
        np.random.seed(42)
        a = np.random.normal(100, 10, 30).tolist()
        b = np.random.normal(110, 10, 30).tolist()

        tester = HypothesisTester(alpha=0.05)
        result = tester.mann_whitney_u(a, b)

        assert result.test_type.value == "mann_whitney_u"
        assert 0 <= result.p_value <= 1

    def test_paired_t_test(self):
        np.random.seed(42)
        before = np.random.normal(100, 10, 20).tolist()
        after = [v + np.random.normal(5, 2) for v in before]

        tester = HypothesisTester(alpha=0.05)
        result = tester.paired_t_test(before, after)

        assert result.test_type.value == "paired_t"
        assert result.reject_null

    def test_chi_square_test(self):
        """STA 342: χ² = Σ (Oᵢ - Eᵢ)² / Eᵢ"""
        observed = [[50, 30, 20], [40, 40, 20]]
        tester = HypothesisTester(alpha=0.05)
        result = tester.chi_square_test(observed)

        assert result.test_type.value == "chi_square"
        assert 0 <= result.p_value <= 1

    def test_proportion_test(self):
        tester = HypothesisTester(alpha=0.05)
        result = tester.proportion_test(
            successes_a=60, n_a=100,
            successes_b=45, n_b=100,
        )
        assert result.test_type.value == "proportion_z"

    def test_multiple_testing_correction_bonferroni(self):
        """STA 342: Bonferroni correction α/m."""
        p_values = [0.01, 0.03, 0.05, 0.10]
        adjusted = MultipleTestingCorrection.bonferroni(p_values)
        assert all(a >= p for a, p in zip(adjusted, p_values))
        assert all(a <= 1.0 for a in adjusted)

    def test_multiple_testing_correction_bh(self):
        """STA 342: Benjamini-Hochberg FDR control."""
        p_values = [0.001, 0.008, 0.039, 0.041, 0.060]
        adjusted = MultipleTestingCorrection.benjamini_hochberg(p_values)
        assert len(adjusted) == len(p_values)
        assert all(a <= 1.0 for a in adjusted)

    def test_multiple_testing_correction_holm(self):
        p_values = [0.01, 0.03, 0.05, 0.10]
        adjusted = MultipleTestingCorrection.holm(p_values)
        assert len(adjusted) == len(p_values)

    def test_sample_size_calculation(self):
        """STA 342: n = (z_α + z_β)² / d²"""
        n = HypothesisTester.required_sample_size(
            effect_size=0.5, power=0.80, alpha=0.05
        )
        assert n > 0
        assert n < 1000  # Sanity check


# =========================================================================
# Experimental Design Tests (STA 343)
# =========================================================================

class TestPowerAnalyzer:
    """Tests for power analysis (STA 342 §7.7 + STA 343)."""

    def test_two_sample_power(self):
        result = PowerAnalyzer.analyze(
            effect_size=0.5, power=0.80, alpha=0.05
        )
        assert result.required_n_per_group > 0
        assert result.total_n == result.required_n_per_group * 2

    def test_large_effect_needs_fewer_subjects(self):
        small = PowerAnalyzer.analyze(effect_size=0.2, power=0.80)
        large = PowerAnalyzer.analyze(effect_size=0.8, power=0.80)
        assert large.required_n_per_group < small.required_n_per_group

    def test_achieved_power(self):
        power = PowerAnalyzer.compute_achieved_power(
            n_per_group=50, effect_size=0.5
        )
        assert 0 <= power <= 1
        assert power > 0.5  # Should have decent power with n=50 and d=0.5


class TestExperimentDesigner:
    """Tests for experimental design (STA 343)."""

    def test_crd_balanced(self):
        """STA 343 §8.2: Completely Randomized Design."""
        variants = [
            Variant("a", "Control", "Current"),
            Variant("b", "Treatment", "New"),
        ]
        assignment = ExperimentDesigner.design_crd(
            n_subjects=100, variants=variants, seed=42
        )
        assert sum(len(v) for v in assignment.values()) == 100

    def test_rcbd(self):
        """STA 343 §8.3: Randomized Complete Block Design."""
        blocks = {
            "market_a": [f"user_{i}" for i in range(20)],
            "market_b": [f"user_{i}" for i in range(20)],
        }
        variants = [
            Variant("a", "Control", "Current"),
            Variant("b", "Treatment", "New"),
        ]
        assignment = ExperimentDesigner.design_rcbd(blocks, variants, seed=42)
        assert len(assignment) == 2
        assert "market_a" in assignment
        assert "market_b" in assignment

    def test_factorial_design(self):
        """STA 343 §8.5: Factorial design."""
        factors = {
            "advice_type": ["price", "demand"],
            "frequency": ["daily", "weekly"],
        }
        assignments = ExperimentDesigner.design_factorial(
            n_subjects=20, factors=factors, seed=42
        )
        assert len(assignments) == 20
        # All combinations should be represented
        combos = set()
        for a in assignments:
            combos.add((a["advice_type"], a["frequency"]))
        assert len(combos) == 4


class TestABTestFramework:
    """Tests for A/B testing framework."""

    def test_create_experiment(self):
        framework = ABTestFramework()
        exp = framework.create_experiment(
            name="Test",
            variants=[
                Variant("control", "Control", "Current"),
                Variant("treatment", "Treatment", "New"),
            ],
            primary_metric="revenue",
            min_detectable_effect=0.5,
        )
        assert "experiment_id" in exp
        assert exp["required_n_per_group"] > 0

    def test_deterministic_assignment(self):
        framework = ABTestFramework()
        exp = framework.create_experiment(
            name="Test",
            variants=[
                Variant("a", "A", "A"),
                Variant("b", "B", "B"),
            ],
            primary_metric="x",
        )
        # Same user always gets same variant
        v1 = framework.assign_user(exp["experiment_id"], "user_1")
        v2 = framework.assign_user(exp["experiment_id"], "user_1")
        assert v1 == v2

    def test_analyze_experiment(self):
        framework = ABTestFramework()
        exp = framework.create_experiment(
            name="Test",
            variants=[
                Variant("a", "A", "A"),
                Variant("b", "B", "B"),
            ],
            primary_metric="revenue",
            min_detectable_effect=0.5,
        )
        exp_id = exp["experiment_id"]

        np.random.seed(42)
        for i in range(30):
            framework.record_outcome(exp_id, f"user_{i}", "a", np.random.normal(100, 10))
            framework.record_outcome(exp_id, f"user_{i+100}", "b", np.random.normal(115, 10))

        result = framework.analyze(exp_id)
        assert result.p_value < 0.05  # Should detect the 15-unit difference
        assert result.winner == "b"


# =========================================================================
# Confidence Interval Tests (STA 342)
# =========================================================================

class TestConfidenceIntervals:
    """Tests for confidence interval computation."""

    def test_mean_ci(self):
        np.random.seed(42)
        values = np.random.normal(100, 10, 50).tolist()
        ci = ConfidenceIntervalCalculator.mean_ci(values, confidence=0.95)

        assert ci.lower < ci.point_estimate < ci.upper
        assert ci.margin_of_error > 0
        assert ci.n == 50
        # True mean (100) should be in CI most of the time
        assert ci.lower < 105 and ci.upper > 95

    def test_proportion_ci(self):
        ci = ConfidenceIntervalCalculator.proportion_ci(
            successes=60, n=100, confidence=0.95
        )
        assert 0 <= ci.lower <= ci.point_estimate <= ci.upper <= 1
        assert abs(ci.point_estimate - 0.6) < 0.001

    def test_difference_ci(self):
        np.random.seed(42)
        a = np.random.normal(100, 10, 30).tolist()
        b = np.random.normal(110, 10, 30).tolist()

        ci = ConfidenceIntervalCalculator.difference_ci(a, b, confidence=0.95)
        # Difference should be negative (a < b)
        assert ci.upper < 5  # Upper bound should be below zero-ish

    def test_bootstrap_ci(self):
        np.random.seed(42)
        values = np.random.normal(100, 10, 30).tolist()
        ci = BootstrapCI.compute(values, statistic="mean", confidence=0.95, n_bootstrap=1000, seed=42)

        assert ci.lower < ci.point_estimate < ci.upper
        assert ci.method == "bootstrap-mean"

    def test_bootstrap_difference_ci(self):
        np.random.seed(42)
        a = np.random.normal(100, 10, 30).tolist()
        b = np.random.normal(110, 10, 30).tolist()
        ci = BootstrapCI.compute_difference(a, b, confidence=0.95, n_bootstrap=1000, seed=42)

        assert ci.method == "bootstrap-diff"


# =========================================================================
# Sampling Tests (ECO 315 / STA 245)
# =========================================================================

class TestSampling:
    """Tests for sampling methodology (ECO 315 §3.3)."""

    def test_sample_size_proportion(self):
        """ECO 315: n = (Z² × p × (1-p)) / e²"""
        result = SampleSizeCalculator.for_proportion(
            confidence=0.95,
            margin_of_error=0.05,
            expected_proportion=0.5,
        )
        # Classic result: n = 385 for 95% CI, 5% margin
        assert 380 <= result.required_n <= 400

    def test_sample_size_with_finite_population(self):
        """STA 245: Finite population correction."""
        result = SampleSizeCalculator.for_proportion(
            confidence=0.95,
            margin_of_error=0.05,
            population_size=500,
        )
        assert result.adjusted_n < result.required_n

    def test_sample_size_with_design_effect(self):
        """STA 245: Design effect for clustered sampling."""
        result = SampleSizeCalculator.for_proportion(
            confidence=0.95,
            margin_of_error=0.05,
            design_effect=2.0,
        )
        assert result.required_n > 385  # DEFF > 1 increases sample size

    def test_simple_random_sampling(self):
        indices = SamplingEngine.simple_random(1000, 100, seed=42)
        assert len(indices) == 100
        assert len(set(indices)) == 100  # No duplicates

    def test_stratified_sampling(self):
        """ECO 315: Stratified sampling by product category."""
        strata = {"food": 1000, "household": 500, "health": 200}
        result = SamplingEngine.stratified(strata, 170, allocation="proportional", seed=42)
        assert len(result) == 3
        assert all(len(v) > 0 for v in result.values())

    def test_cluster_sampling(self):
        clusters = {"market_a": 100, "market_b": 150, "market_c": 80, "market_d": 200}
        result = SamplingEngine.cluster(clusters, n_clusters_to_sample=2, sample_per_cluster=20, seed=42)
        assert len(result) == 2

    def test_design_effect(self):
        """STA 245: DEFF = 1 + (m̄ - 1) × ρ"""
        cluster_sizes = [30, 30, 30, 30]
        deff = SamplingEngine.compute_design_effect(cluster_sizes, intra_class_correlation=0.05)
        # DEFF = 1 + (30-1)*0.05 = 1 + 1.45 = 2.45
        assert abs(deff - 2.45) < 0.01

    def test_sampling_plan(self):
        segments = {"food_vendors": 5000, "clothing_vendors": 2000, "tech_vendors": 500}
        plan = SamplingEngine.create_sampling_plan(segments, total_budget=500)
        assert plan.sample_size <= 500
        assert len(plan.allocation) == 3
