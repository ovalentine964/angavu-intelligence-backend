"""
Tests for advanced non-parametric methods: Sign test, Runs test, Mood's median,
non-parametric CIs, and non-parametric effect sizes.
"""

import numpy as np
import pytest
from python.statistical.nonparametric_advanced import (
    SignTest,
    RunsTest,
    MoodsMedianTest,
    NonparametricCI,
    NonparametricEffectSize,
)


class TestSignTest:
    def test_one_sample_significant_shift(self):
        """Sign test detects clear positive shift."""
        data = np.array([10, 12, 14, 16, 18, 20, 22, 24, 26, 28])
        result = SignTest.one_sample(data, hypothesized_median=0.0)
        assert result["n_positive"] == 10
        assert result["n_negative"] == 0
        assert result["significant_at_05"] == True  # noqa: E712

    def test_one_sample_no_shift(self):
        """Sign test does not reject when median is correct."""
        data = np.array([1, -1, 2, -2, 3, -3, 4, -4, 5, -5])
        result = SignTest.one_sample(data, hypothesized_median=0.0)
        assert result["n_positive"] == 5
        assert result["n_negative"] == 5
        assert result["significant_at_05"] == False  # noqa: E712

    def test_paired_sign_test(self):
        """Paired sign test with clear difference."""
        s1 = np.array([10, 12, 14, 16, 18, 20, 22, 24, 26, 28])
        s2 = np.array([5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
        result = SignTest.paired(s1, s2)
        assert result["n_positive"] == 10
        assert result["significant_at_05"] == True  # noqa: E712
        assert "median_difference" in result

    def test_insufficient_data(self):
        """Sign test fails with too few observations."""
        data = np.array([1, 2, 3])
        result = SignTest.one_sample(data)
        assert "error" in result


class TestRunsTest:
    def test_random_sequence(self):
        """Random sequence should not reject H0."""
        rng = np.random.RandomState(42)
        data = rng.normal(0, 1, 100)
        result = RunsTest.test(data)
        assert result["significant_at_05"] == False  # noqa: E712

    def test_monotone_sequence_detected(self):
        """Monotonically increasing sequence has few runs."""
        data = np.arange(1, 21, dtype=float)
        result = RunsTest.test(data)
        assert result["significant_at_05"] == True  # noqa: E712
        assert result["observed_runs"] < result["expected_runs"]

    def test_alternating_sequence_detected(self):
        """Alternating sequence has too many runs."""
        data = np.array([1, 10, 2, 9, 3, 8, 4, 7, 5, 6, 1, 10, 2, 9, 3, 8])
        result = RunsTest.test(data)
        assert result["significant_at_05"] == True  # noqa: E712

    def test_insufficient_data(self):
        """Runs test fails with < 10 observations."""
        data = np.array([1, 2, 3, 4, 5])
        result = RunsTest.test(data)
        assert "error" in result


class TestMoodsMedianTest:
    def test_different_medians(self):
        """Mood's test detects different medians."""
        g1 = np.array([1, 2, 3, 4, 5, 6])
        g2 = np.array([10, 11, 12, 13, 14, 15])
        result = MoodsMedianTest.test(g1, g2)
        assert result["significant_at_05"] == True  # noqa: E712

    def test_same_medians(self):
        """Mood's test does not reject when medians are same."""
        g1 = np.array([5, 6, 7, 8, 9])
        g2 = np.array([5, 6, 7, 8, 9])
        g3 = np.array([5, 6, 7, 8, 9])
        result = MoodsMedianTest.test(g1, g2, g3)
        assert result["significant_at_05"] == False  # noqa: E712

    def test_three_groups(self):
        """Mood's test with 3 groups, 2 similar, 1 different."""
        g1 = np.array([1, 2, 3, 4, 5])
        g2 = np.array([2, 3, 4, 5, 6])
        g3 = np.array([20, 21, 22, 23, 24])
        result = MoodsMedianTest.test(g1, g2, g3)
        assert result["significant_at_05"] == True  # noqa: E712
        assert "contingency_table" in result


class TestNonparametricCI:
    def test_bootstrap_ci_percentile(self):
        """Percentile bootstrap CI for mean."""
        rng = np.random.RandomState(42)
        data = rng.normal(10, 2, 100)
        result = NonparametricCI.bootstrap_ci(data, np.mean, method="percentile")
        assert result["ci_lower"] < 10 < result["ci_upper"]

    def test_bootstrap_ci_bca(self):
        """BCa bootstrap CI for median."""
        rng = np.random.RandomState(42)
        data = rng.exponential(5, 100)
        result = NonparametricCI.bootstrap_ci(data, np.median, method="bca")
        assert result["ci_lower"] < np.median(data) < result["ci_upper"]

    def test_median_ci_exact(self):
        """Exact CI for median."""
        data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        result = NonparametricCI.median_ci(data, method="exact")
        assert result["ci_lower"] <= np.median(data) <= result["ci_upper"]

    def test_insufficient_data(self):
        """CI fails with too few observations."""
        data = np.array([1, 2, 3])
        result = NonparametricCI.bootstrap_ci(data, np.mean)
        assert "error" in result


class TestNonparametricEffectSize:
    def test_cliffs_delta_large_effect(self):
        """Cliff's delta detects large dominance."""
        s1 = np.array([10, 11, 12, 13, 14, 15])
        s2 = np.array([1, 2, 3, 4, 5, 6])
        result = NonparametricEffectSize.cliffs_delta(s1, s2)
        assert result["delta"] > 0.8
        assert result["magnitude"] == "large"

    def test_cliffs_delta_no_effect(self):
        """Cliff's delta near 0 for overlapping samples."""
        rng = np.random.RandomState(42)
        s1 = rng.normal(0, 1, 50)
        s2 = rng.normal(0, 1, 50)
        result = NonparametricEffectSize.cliffs_delta(s1, s2)
        assert abs(result["delta"]) < 0.3

    def test_rank_biserial(self):
        """Rank-biserial correlation for clearly different groups."""
        s1 = np.array([10, 11, 12, 13, 14, 15])
        s2 = np.array([1, 2, 3, 4, 5, 6])
        result = NonparametricEffectSize.rank_biserial_correlation(s1, s2)
        assert result["r"] > 0.8
        assert result["p_superiority"] > 0.9

    def test_vargha_delaney_a(self):
        """Vargha-Delaney A for identical distributions."""
        rng = np.random.RandomState(42)
        s1 = rng.normal(0, 1, 50)
        s2 = rng.normal(0, 1, 50)
        result = NonparametricEffectSize.vargha_delaney_a(s1, s2)
        assert abs(result["A"] - 0.5) < 0.3

    def test_cliffs_delta_insufficient_data(self):
        """Cliff's delta fails with < 3 per group."""
        s1 = np.array([1, 2])
        s2 = np.array([3, 4])
        result = NonparametricEffectSize.cliffs_delta(s1, s2)
        assert "error" in result
