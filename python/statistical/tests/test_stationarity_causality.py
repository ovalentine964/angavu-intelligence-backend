"""Tests for stationarity_causality.py — KPSS, Granger causality, CIs, bootstrap."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python', 'statistical'))

import numpy as np
import pytest
from stationarity_causality import (
    KPSS_test, GrangerCausalityTest, ConfidenceIntervals, BootstrapBCa
)


class TestKPSS:
    def test_stationary_series_not_rejected(self):
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, size=200)  # stationary
        result = KPSS_test.test(data, regression="c")
        assert result["is_stationary"] is True

    def test_random_walk_rejected(self):
        rng = np.random.default_rng(42)
        data = np.cumsum(rng.normal(0, 1, size=200))  # random walk
        result = KPSS_test.test(data, regression="c")
        assert result["is_stationary"] is False

    def test_critical_values_present(self):
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, size=100)
        result = KPSS_test.test(data)
        assert "5%" in result["critical_values"]
        assert "1%" in result["critical_values"]


class TestGrangerCausality:
    def test_causal_relationship_detected(self):
        rng = np.random.default_rng(42)
        # X causes Y: Y_t = 0.8 * Y_{t-1} + 0.5 * X_{t-1} + noise
        T = 200
        x = rng.normal(0, 1, T)
        y = np.zeros(T)
        for t in range(1, T):
            y[t] = 0.8 * y[t-1] + 0.5 * x[t-1] + rng.normal(0, 0.5)
        result = GrangerCausalityTest.test(x, y, max_lag=2)
        assert result["granger_causes"] is True

    def test_no_causality_when_independent(self):
        rng = np.random.default_rng(42)
        x = rng.normal(0, 1, 200)
        y = rng.normal(0, 1, 200)
        result = GrangerCausalityTest.test(x, y, max_lag=2)
        assert result["granger_causes"] is False

    def test_pairwise_matrix(self):
        rng = np.random.default_rng(42)
        variables = {
            "A": rng.normal(0, 1, 100),
            "B": rng.normal(0, 1, 100),
        }
        result = GrangerCausalityTest.pairwise_causality_matrix(variables, max_lag=2)
        assert "p_values" in result
        assert "causal_edges" in result


class TestConfidenceIntervals:
    def test_mean_ci_contains_true_mean(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 15, size=50)
        result = ConfidenceIntervals.mean_ci(data, confidence=0.95)
        assert result["ci_lower"] < 100 < result["ci_upper"]

    def test_proportion_ci(self):
        result = ConfidenceIntervals.proportion_ci(50, 100, confidence=0.95)
        assert 0.4 < result["ci_lower"] < 0.5
        assert 0.5 < result["ci_upper"] < 0.6

    def test_variance_ci(self):
        rng = np.random.default_rng(42)
        data = rng.normal(0, 5, size=100)
        result = ConfidenceIntervals.variance_ci(data, confidence=0.95)
        assert result["ci_lower"] < 25 < result["ci_upper"]  # true var = 25

    def test_bootstrap_ci(self):
        rng = np.random.default_rng(42)
        data = rng.normal(50, 10, size=50)
        result = ConfidenceIntervals.mean_ci(data, confidence=0.95, method="bootstrap")
        assert result["ci_lower"] < 50 < result["ci_upper"]


class TestBootstrapBCa:
    def test_bca_ci_contains_true_mean(self):
        rng = np.random.default_rng(42)
        data = rng.normal(50, 10, size=100)
        result = BootstrapBCa.bca_ci(data, np.mean, confidence=0.95, n_bootstrap=5000)
        assert result["ci_lower"] < 50 < result["ci_upper"]
        assert result["method"] == "BCa"
