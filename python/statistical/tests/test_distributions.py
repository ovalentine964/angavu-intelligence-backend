"""Tests for distributions.py — MLE fitting, MGF, CLT, GOF, parametric bootstrap."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python', 'statistical'))

import numpy as np
import pytest
from distributions import (
    DistributionFitter, MomentGeneratingFunction, CentralLimitTheorem,
    GoodnessOfFit, ParametricBootstrap
)


class TestDistributionFitter:
    def test_fit_normal_known_data(self):
        rng = np.random.default_rng(42)
        data = rng.normal(5.0, 2.0, size=500)
        result = DistributionFitter.fit_normal(data)
        assert abs(result.parameters["mu"] - 5.0) < 0.5
        assert abs(result.parameters["sigma"] - 2.0) < 0.5
        assert result.goodness_of_fit == "good"

    def test_fit_exponential(self):
        rng = np.random.default_rng(42)
        data = rng.exponential(3.0, size=1000)
        result = DistributionFitter.fit_exponential(data)
        assert abs(result.parameters["lambda"] - 1/3.0) < 0.1

    def test_fit_best_returns_lowest_aic(self):
        rng = np.random.default_rng(42)
        data = rng.normal(10, 3, size=200)
        result = DistributionFitter.fit_best(data)
        assert result.distribution in ["normal", "lognormal"]
        assert result.aic < 0

    def test_fit_gamma(self):
        rng = np.random.default_rng(42)
        data = rng.gamma(2.0, scale=3.0, size=500)
        result = DistributionFitter.fit_gamma(data)
        assert abs(result.parameters["alpha"] - 2.0) < 1.0


class TestMGF:
    def test_normal_mgf_at_zero_is_one(self):
        assert MomentGeneratingFunction.normal_mgf(0, 5, 2) == 1.0

    def test_normal_mgf_first_moment(self):
        # M'(0) = μ for Normal
        mu, sigma = 3.0, 2.0
        dt = 1e-6
        m0 = MomentGeneratingFunction.normal_mgf(0, mu, sigma)
        m_dt = MomentGeneratingFunction.normal_mgf(dt, mu, sigma)
        first_moment = (m_dt - m0) / dt
        assert abs(first_moment - mu) < 0.01

    def test_poisson_mgf(self):
        lam = 3.0
        # M(0) = 1
        assert abs(MomentGeneratingFunction.poisson_mgf(0, lam) - 1.0) < 1e-10
        # M'(0) = λ (mean)
        dt = 1e-6
        m0 = MomentGeneratingFunction.poisson_mgf(0, lam)
        m_dt = MomentGeneratingFunction.poisson_mgf(dt, lam)
        first_moment = (m_dt - m0) / dt
        assert abs(first_moment - lam) < 0.01

    def test_exponential_mgf_undefined_beyond_lambda(self):
        assert MomentGeneratingFunction.exponential_mgf(2.0, 1.0) is None
        assert MomentGeneratingFunction.exponential_mgf(0.5, 1.0) is not None


class TestCLT:
    def test_sampling_distribution_converges(self):
        rng = np.random.default_rng(42)
        # Exponential is far from normal
        population = rng.exponential(5.0, size=100000)
        result = CentralLimitTheorem.sampling_distribution(population, sample_size=50, n_samples=5000)
        assert result["clt_holds"] is True
        assert abs(result["sampling_se"] - result["theoretical_se"]) / result["theoretical_se"] < 0.3

    def test_clt_ci_width_decreases_with_n(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 15, size=100)
        ci_small = CentralLimitTheorem.clt_confidence_interval(data[:20])
        ci_large = CentralLimitTheorem.clt_confidence_interval(data)
        assert ci_large["margin_of_error"] < ci_small["margin_of_error"]


class TestGoodnessOfFit:
    def test_chi_squared_good_fit(self):
        observed = np.array([50, 50, 50, 50, 50])
        expected = np.array([50, 50, 50, 50, 50])
        result = GoodnessOfFit.chi_squared_test(observed, expected)
        assert result["good_fit"] is True
        assert result["chi_squared"] < 1.0

    def test_ks_test_normal_data(self):
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, size=500)
        result = GoodnessOfFit.kolmogorov_smirnov_test(data, "norm")
        assert result["good_fit"] is True

    def test_anderson_darling_normal(self):
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, size=200)
        result = GoodnessOfFit.anderson_darling_test(data)
        assert result["is_normal_5pct"] is True


class TestParametricBootstrap:
    def test_bootstrap_ci_contains_true_mean(self):
        rng = np.random.default_rng(42)
        data = rng.normal(50, 10, size=100)
        result = ParametricBootstrap.bootstrap_ci(data, np.mean, "normal", n_bootstrap=5000)
        assert result["ci_lower"] < 50 < result["ci_upper"]

    def test_bootstrap_ci_narrows_with_more_data(self):
        rng = np.random.default_rng(42)
        small = rng.normal(50, 10, size=20)
        large = rng.normal(50, 10, size=200)
        ci_small = ParametricBootstrap.bootstrap_ci(small, np.mean, "normal", n_bootstrap=5000)
        ci_large = ParametricBootstrap.bootstrap_ci(large, np.mean, "normal", n_bootstrap=5000)
        width_small = ci_small["ci_upper"] - ci_small["ci_lower"]
        width_large = ci_large["ci_upper"] - ci_large["ci_lower"]
        assert width_large < width_small
