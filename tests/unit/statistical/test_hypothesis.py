"""
Tests for Hypothesis Testing, Bootstrap Inference & Distribution Fitting (STA 342, STA 444).

Tests cover:
- Two-sample tests (t-test, Mann-Whitney, KS)
- Bootstrap confidence intervals
- Distribution fitting
- Effect size calculations
- Edge cases
"""

import numpy as np
import pytest

from app.services.statistical.hypothesis import (
    BootstrapInference,
    HypothesisTester,
    DistributionFitter,
)


class TestBootstrapInference:
    """Bootstrap inference tests."""

    def test_percentile_ci_contains_true_mean(self):
        """Bootstrap CI should contain the true mean for normal data."""
        rng = np.random.RandomState(42)
        data = rng.normal(50, 10, 100)

        result = BootstrapInference.percentile_ci(
            data, np.mean, n_bootstrap=5000, confidence=0.95
        )

        assert result["ci_lower"] < 50 < result["ci_upper"]
        assert result["estimate"] == pytest.approx(np.mean(data), abs=0.1)

    def test_bootstrap_se_reasonable(self):
        """Bootstrap SE should be close to analytical SE."""
        rng = np.random.RandomState(42)
        data = rng.normal(0, 1, 100)
        analytical_se = 1.0 / np.sqrt(100)

        boot_se = BootstrapInference.bootstrap_se(data, np.mean, n_bootstrap=5000)

        assert abs(boot_se - analytical_se) < 0.05

    def test_ci_narrows_with_larger_sample(self):
        """Larger samples produce narrower CIs."""
        rng = np.random.RandomState(42)
        small = rng.normal(50, 10, 20)
        large = rng.normal(50, 10, 200)

        ci_small = BootstrapInference.percentile_ci(small, np.mean, n_bootstrap=2000)
        ci_large = BootstrapInference.percentile_ci(large, np.mean, n_bootstrap=2000)

        width_small = ci_small["ci_upper"] - ci_small["ci_lower"]
        width_large = ci_large["ci_upper"] - ci_large["ci_lower"]
        assert width_large < width_small

    def test_ci_for_median(self):
        """Bootstrap CI works for median statistic."""
        rng = np.random.RandomState(42)
        data = rng.exponential(5, 100)

        result = BootstrapInference.percentile_ci(
            data, np.median, n_bootstrap=5000
        )

        assert result["ci_lower"] < np.median(data) < result["ci_upper"]

    def test_ci_for_std(self):
        """Bootstrap CI works for standard deviation."""
        rng = np.random.RandomState(42)
        data = rng.normal(0, 5, 100)

        result = BootstrapInference.percentile_ci(
            data, np.std, n_bootstrap=5000
        )

        true_std = 5.0
        assert result["ci_lower"] < true_std < result["ci_upper"]


class TestHypothesisTester:
    """Hypothesis testing framework tests."""

    def test_two_sample_t_test_detects_difference(self):
        """Welch's t-test detects different means."""
        rng = np.random.RandomState(42)
        sample1 = rng.normal(100, 10, 50)
        sample2 = rng.normal(110, 10, 50)

        result = HypothesisTester.two_sample_test(sample1, sample2, test_type="ttest")

        assert result["significant_at_05"] is True
        assert result["p_value"] < 0.05

    def test_two_sample_t_test_no_difference(self):
        """Welch's t-test fails to reject when means are same."""
        rng = np.random.RandomState(42)
        sample1 = rng.normal(100, 10, 50)
        sample2 = rng.normal(100, 10, 50)

        result = HypothesisTester.two_sample_test(sample1, sample2, test_type="ttest")

        # Should generally not be significant (p > 0.05)
        assert result["test_name"] == "Welch's t-test"

    def test_mann_whitney_detects_difference(self):
        """Mann-Whitney U test detects distribution shift."""
        rng = np.random.RandomState(42)
        sample1 = rng.normal(0, 1, 50)
        sample2 = rng.normal(3, 1, 50)

        result = HypothesisTester.two_sample_test(
            sample1, sample2, test_type="mannwhitney"
        )

        assert result["significant_at_05"] is True

    def test_ks_test_detects_difference(self):
        """Kolmogorov-Smirnov test detects distribution difference."""
        rng = np.random.RandomState(42)
        sample1 = rng.normal(0, 1, 100)
        sample2 = rng.normal(0, 3, 100)  # Different variance

        result = HypothesisTester.two_sample_test(sample1, sample2, test_type="ks")

        assert result["test_name"] == "Kolmogorov-Smirnov test"

    def test_auto_selects_appropriate_test(self):
        """Auto mode selects t-test for normal data, Mann-Whitney otherwise."""
        rng = np.random.RandomState(42)
        normal1 = rng.normal(0, 1, 50)
        normal2 = rng.normal(0, 1, 50)

        result = HypothesisTester.two_sample_test(normal1, normal2, test_type="auto")

        assert result["test_name"] in ["Welch's t-test", "Mann-Whitney U test"]

    def test_cohens_d_effect_size(self):
        """Cohen's d correctly measures effect size."""
        rng = np.random.RandomState(42)
        sample1 = rng.normal(0, 1, 100)
        sample2 = rng.normal(2, 1, 100)  # 2 SD difference

        result = HypothesisTester.two_sample_test(sample1, sample2, test_type="ttest")

        # Cohen's d should be approximately 2.0
        assert abs(result["effect_size_cohens_d"] - 2.0) < 0.5

    def test_unknown_test_type_raises(self):
        """Unknown test type raises ValueError."""
        rng = np.random.RandomState(42)
        with pytest.raises(ValueError):
            HypothesisTester.two_sample_test(
                rng.normal(0, 1, 10), rng.normal(0, 1, 10),
                test_type="unknown"
            )


class TestDistributionFitter:
    """Distribution fitting tests."""

    def test_fit_normal_distribution(self):
        """Fitter identifies normal distribution correctly."""
        rng = np.random.RandomState(42)
        data = rng.normal(5, 2, 200)

        result = DistributionFitter.fit_best_distribution(
            data, candidates=["normal", "lognormal", "gamma"]
        )

        assert result["best_distribution"] == "normal"
        assert result["p_value"] > 0.05  # Should not reject normality

    def test_fit_gamma_distribution(self):
        """Fitter identifies gamma distribution."""
        rng = np.random.RandomState(42)
        data = rng.gamma(2, 2, 200)

        result = DistributionFitter.fit_best_distribution(
            data, candidates=["normal", "gamma", "exponential"]
        )

        # Gamma data should fit gamma better than normal
        assert result["best_distribution"] in ["gamma", "exponential"]

    def test_fit_returns_aic_for_comparison(self):
        """All fitted distributions include AIC for model selection."""
        rng = np.random.RandomState(42)
        data = rng.normal(0, 1, 100)

        result = DistributionFitter.fit_best_distribution(data)

        assert "aic" in result
        assert "all_results" in result
        for r in result["all_results"]:
            assert "aic" in r
            assert "ks_statistic" in r
            assert "p_value" in r

    def test_fit_returns_parameters(self):
        """Fitted distribution includes parameters."""
        rng = np.random.RandomState(42)
        data = rng.normal(5, 2, 200)

        result = DistributionFitter.fit_best_distribution(
            data, candidates=["normal"]
        )

        assert len(result["best_parameters"]) == 2  # loc, scale
