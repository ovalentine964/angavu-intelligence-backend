"""
Tests for Bayesian Inference Engine (STA 341).

Tests cover:
- Beta-Binomial conjugate updates (credit scoring, success rates)
- Normal-Normal conjugate updates (price estimation)
- Kernel Density Estimation (non-parametric density)
- Multimodality detection
- Edge cases (zero data, extreme priors)
"""

import numpy as np
import pytest

from app.services.statistical.bayesian import BayesianUpdater, KernelDensityEstimator


class TestBayesianUpdaterBetaBinomial:
    """Beta-Binomial conjugate update tests."""

    def test_basic_update(self):
        """Standard Beta-Binomial update with moderate prior and data."""
        post_a, post_b, summary = BayesianUpdater.beta_binomial_update(
            prior_alpha=2.0, prior_beta=5.0,
            successes=8, failures=2,
        )
        # Posterior: Beta(2+8, 5+2) = Beta(10, 7)
        assert post_a == 10.0
        assert post_b == 7.0
        assert summary["posterior_mean"] == pytest.approx(10 / 17, abs=0.001)
        assert summary["data_points"] == 10
        assert summary["effective_sample_size"] == 17

    def test_update_with_no_data(self):
        """Update with zero observations returns the prior."""
        post_a, post_b, summary = BayesianUpdater.beta_binomial_update(
            prior_alpha=2.0, prior_beta=5.0,
            successes=0, failures=0,
        )
        assert post_a == 2.0
        assert post_b == 5.0
        assert summary["posterior_mean"] == pytest.approx(2 / 7, abs=0.001)

    def test_update_with_all_successes(self):
        """All successes pushes posterior mean toward 1."""
        post_a, post_b, summary = BayesianUpdater.beta_binomial_update(
            prior_alpha=1.0, prior_beta=1.0,  # Uniform prior
            successes=100, failures=0,
        )
        assert post_a == 101.0
        assert post_b == 1.0
        assert summary["posterior_mean"] > 0.95

    def test_update_with_all_failures(self):
        """All failures pushes posterior mean toward 0."""
        post_a, post_b, summary = BayesianUpdater.beta_binomial_update(
            prior_alpha=1.0, prior_beta=1.0,
            successes=0, failures=100,
        )
        assert summary["posterior_mean"] < 0.05

    def test_credible_interval_contains_posterior_mean(self):
        """95% credible interval should contain the posterior mean."""
        _, _, summary = BayesianUpdater.beta_binomial_update(
            prior_alpha=5.0, prior_beta=5.0,
            successes=50, failures=50,
        )
        ci_lo, ci_hi = summary["credible_interval_95"]
        assert ci_lo <= summary["posterior_mean"] <= ci_hi

    def test_credible_interval_narrows_with_more_data(self):
        """More data should narrow the credible interval."""
        _, _, summary_small = BayesianUpdater.beta_binomial_update(
            prior_alpha=2.0, prior_beta=5.0,
            successes=10, failures=10,
        )
        _, _, summary_large = BayesianUpdater.beta_binomial_update(
            prior_alpha=2.0, prior_beta=5.0,
            successes=100, failures=100,
        )
        ci_width_small = summary_small["credible_interval_95"][1] - summary_small["credible_interval_95"][0]
        ci_width_large = summary_large["credible_interval_95"][1] - summary_large["credible_interval_95"][0]
        assert ci_width_large < ci_width_small

    def test_strong_prior_resists_data(self):
        """A strong prior (large alpha+beta) should resist small amounts of data."""
        _, _, summary = BayesianUpdater.beta_binomial_update(
            prior_alpha=100.0, prior_beta=100.0,  # Strong prior centered at 0.5
            successes=5, failures=95,  # Data says ~0.05
        )
        # Posterior should be closer to 0.5 than to 0.05
        assert summary["posterior_mean"] > 0.3


class TestBayesianUpdaterNormalNormal:
    """Normal-Normal conjugate update tests."""

    def test_basic_update(self):
        """Standard Normal-Normal update."""
        post_mean, post_var, summary = BayesianUpdater.normal_normal_update(
            prior_mean=100.0, prior_var=25.0,
            data_mean=110.0, data_var=16.0, n=25,
        )
        # Posterior mean should be between prior and data mean
        assert 100 < post_mean < 110
        # Posterior variance should be smaller than prior
        assert post_var < 25.0
        assert summary["data_points"] == 25

    def test_update_with_large_n_shrinks_to_data(self):
        """With large n, posterior should be close to data mean."""
        post_mean, _, summary = BayesianUpdater.normal_normal_update(
            prior_mean=50.0, prior_var=100.0,
            data_mean=80.0, data_var=10.0, n=1000,
        )
        assert abs(post_mean - 80.0) < 1.0

    def test_update_with_small_n_stays_near_prior(self):
        """With small n, posterior should be close to prior mean."""
        post_mean, _, _ = BayesianUpdater.normal_normal_update(
            prior_mean=50.0, prior_var=10.0,
            data_mean=80.0, data_var=10.0, n=1,
        )
        assert abs(post_mean - 50.0) < abs(post_mean - 80.0)

    def test_credible_interval_is_symmetric(self):
        """For Normal posterior, 95% CI should be roughly symmetric around mean."""
        post_mean, post_var, summary = BayesianUpdater.normal_normal_update(
            prior_mean=100.0, prior_var=25.0,
            data_mean=100.0, data_var=25.0, n=100,
        )
        ci_lo, ci_hi = summary["credible_interval_95"]
        dist_lo = post_mean - ci_lo
        dist_hi = ci_hi - post_mean
        assert dist_lo == pytest.approx(dist_hi, abs=0.1)

    def test_shrinkage_factor_between_0_and_1(self):
        """Shrinkage factor should be between 0 and 1."""
        _, _, summary = BayesianUpdater.normal_normal_update(
            prior_mean=100.0, prior_var=25.0,
            data_mean=110.0, data_var=16.0, n=25,
        )
        sf = summary["shrinkage_factor"]
        assert 0 <= sf <= 1


class TestKernelDensityEstimator:
    """Gaussian KDE tests."""

    def test_basic_kde(self):
        """KDE on simple normal data."""
        rng = np.random.RandomState(42)
        data = rng.normal(0, 1, 100)
        points, density = KernelDensityEstimator.gaussian_kde(data)

        assert len(points) == 100
        assert len(density) == 100
        assert all(d >= 0 for d in density)
        # Peak should be near 0
        peak_idx = np.argmax(density)
        assert abs(points[peak_idx]) < 1.0

    def test_kde_with_custom_points(self):
        """KDE evaluated at custom points."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        eval_points = np.array([0, 2.5, 5, 10])
        _, density = KernelDensityEstimator.gaussian_kde(data, points=eval_points)

        assert len(density) == 4
        assert all(d >= 0 for d in density)

    def test_kde_with_custom_bandwidth(self):
        """KDE with explicit bandwidth."""
        data = np.array([1.0, 2.0, 3.0])
        _, density_wide = KernelDensityEstimator.gaussian_kde(data, bandwidth=2.0)
        _, density_narrow = KernelDensityEstimator.gaussian_kde(data, bandwidth=0.1)

        # Wider bandwidth should produce smoother (lower peak) density
        assert max(density_wide) <= max(density_narrow) * 1.5  # Allow some tolerance

    def test_kde_rejects_single_point(self):
        """KDE requires at least 2 data points."""
        with pytest.raises(ValueError):
            KernelDensityEstimator.gaussian_kde(np.array([1.0]))

    def test_multimodality_detection_unimodal(self):
        """Detect single mode in unimodal data."""
        rng = np.random.RandomState(42)
        data = rng.normal(5, 1, 200)
        result = KernelDensityEstimator.detect_multimodality(data)

        # Should detect at least one mode
        assert result["n_modes"] >= 1
        # Mode location should be near 5
        assert abs(result["mode_locations"][0] - 5) < 2

    def test_multimodality_detection_bimodal(self):
        """Detect two modes in bimodal data."""
        rng = np.random.RandomState(42)
        data = np.concatenate([rng.normal(2, 0.5, 100), rng.normal(8, 0.5, 100)])
        result = KernelDensityEstimator.detect_multimodality(data)

        assert result["n_modes"] >= 2
        assert result["is_multimodal"] is True

    def test_multimodality_limits_modes(self):
        """Respects n_modes_max parameter."""
        rng = np.random.RandomState(42)
        data = rng.normal(0, 1, 100)
        result = KernelDensityEstimator.detect_multimodality(data, n_modes_max=3)

        assert result["n_modes"] <= 3
