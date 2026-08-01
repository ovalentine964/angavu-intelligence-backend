"""Tests for time_series_models.py — ARIMA, SARIMA, ETS, structural breaks."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python', 'statistical'))

import numpy as np
import pytest
from time_series_models import ARIMAModel, SARIMAModel, ETSModel, StructuralBreakTests


class TestARIMA:
    def test_identify_returns_order(self):
        rng = np.random.default_rng(42)
        data = np.cumsum(rng.normal(0, 1, 100))  # random walk
        result = ARIMAModel.identify(data)
        assert "recommended_order" in result
        assert "best_aic" in result

    def test_fit_ar1(self):
        rng = np.random.default_rng(42)
        data = np.zeros(100)
        data[0] = rng.normal()
        for t in range(1, 100):
            data[t] = 0.7 * data[t - 1] + rng.normal(0, 0.5)
        result = ARIMAModel.fit(data, order=(1, 0, 0))
        assert "ar_coefficients" in result
        assert result["ar_coefficients"][0] > 0.3  # should detect positive AR(1)
        assert "forecasts" in result
        assert len(result["forecasts"]) > 0

    def test_fit_arma11(self):
        rng = np.random.default_rng(42)
        data = np.zeros(100)
        e = rng.normal(0, 0.5, 100)
        data[0] = e[0]
        for t in range(1, 100):
            data[t] = 0.6 * data[t - 1] + e[t] + 0.3 * e[t - 1]
        result = ARIMAModel.fit(data, order=(1, 0, 1))
        assert "ar_coefficients" in result
        assert "ma_coefficients" in result
        assert "aic" in result
        assert "bic" in result

    def test_fit_with_differencing(self):
        rng = np.random.default_rng(42)
        data = np.cumsum(rng.normal(0, 1, 100))  # I(1) series
        result = ARIMAModel.fit(data, order=(1, 1, 0))
        assert "forecasts" in result
        assert "ljung_box_p_value" in result

    def test_diagnose_returns_tests(self):
        rng = np.random.default_rng(42)
        residuals = rng.normal(0, 1, 100)
        result = ARIMAModel.diagnose(residuals)
        assert "ljung_box" in result
        assert "jarque_bera" in result
        assert "arch_test" in result
        assert "normality_ok" in result

    def test_confidence_intervals_widen(self):
        rng = np.random.default_rng(42)
        data = np.zeros(100)
        data[0] = rng.normal()
        for t in range(1, 100):
            data[t] = 0.5 * data[t - 1] + rng.normal(0, 1)
        result = ARIMAModel.fit(data, order=(1, 0, 0))
        ci = result["confidence_intervals"]
        # CI should widen: first narrower than last
        assert ci[-1][1] - ci[-1][0] > ci[0][1] - ci[0][0]

    def test_insufficient_data_returns_error(self):
        data = [1.0, 2.0, 3.0]
        result = ARIMAModel.fit(np.array(data), order=(2, 1, 1))
        assert "error" in result


class TestSARIMA:
    def test_sarima_fit_basic(self):
        rng = np.random.default_rng(42)
        # Create data with seasonal pattern
        t = np.arange(60)
        data = 50 + 0.5 * t + 10 * np.sin(2 * np.pi * t / 12) + rng.normal(0, 2, 60)
        result = SARIMAModel.fit(data, order=(1, 0, 0), seasonal_order=(1, 0, 0, 12))
        assert "forecasts" in result
        assert "ar_coefficients" in result
        assert "method" in result
        assert "SARIMA" in result["method"]

    def test_sarima_insufficient_data(self):
        data = np.array([1.0, 2.0, 3.0])
        result = SARIMAModel.fit(data, order=(1, 1, 1), seasonal_order=(1, 1, 1, 12))
        assert "error" in result


class TestETS:
    def test_ets_aan_fit(self):
        rng = np.random.default_rng(42)
        data = 100 + np.cumsum(rng.normal(0, 1, 50))
        result = ETSModel.fit(data, "AAN")
        assert "forecasts" in result
        assert "aic" in result
        assert result["method"] == "ETS(A,A,N)"

    def test_ets_ann_fit(self):
        rng = np.random.default_rng(42)
        data = 100 + rng.normal(0, 5, 50)
        result = ETSModel.fit(data, "ANN")
        assert "forecasts" in result

    def test_ets_auto_select(self):
        rng = np.random.default_rng(42)
        data = 100 + 0.5 * np.arange(30) + rng.normal(0, 2, 30)
        result = ETSModel.auto_select(data)
        assert "best_model" in result
        assert "n_models_tested" in result
        assert result["n_models_tested"] > 0


class TestStructuralBreaks:
    def test_chow_test_detects_break(self):
        rng = np.random.default_rng(42)
        # Create data with clear break at t=50
        y1 = 10 + 2 * np.arange(50) + rng.normal(0, 3, 50)
        y2 = 120 + 0.5 * np.arange(50) + rng.normal(0, 3, 50)
        y = np.concatenate([y1, y2])
        X = np.arange(100).reshape(-1, 1)
        result = StructuralBreakTests.chow_test(y, X, 50)
        assert "f_statistic" in result
        assert "p_value" in result
        assert result["structural_break"] is True  # should detect break

    def test_chow_test_no_break(self):
        rng = np.random.default_rng(42)
        # No break — homogeneous data
        y = 10 + 2 * np.arange(100) + rng.normal(0, 5, 100)
        X = np.arange(100).reshape(-1, 1)
        result = StructuralBreakTests.chow_test(y, X, 50)
        assert result["structural_break"] is False

    def test_cusum_test_basic(self):
        rng = np.random.default_rng(42)
        y = 10 + 2 * np.arange(50) + rng.normal(0, 2, 50)
        X = np.arange(50).reshape(-1, 1)
        result = StructuralBreakTests.cusum_test(y, X)
        assert "cusum_statistic" in result
        assert "break_detected" in result

    def test_bai_perron_basic(self):
        rng = np.random.default_rng(42)
        # One break at t=30
        y1 = 10 + 1 * np.arange(30) + rng.normal(0, 2, 30)
        y2 = 40 + 3 * np.arange(30) + rng.normal(0, 2, 30)
        y = np.concatenate([y1, y2])
        X = np.arange(60).reshape(-1, 1)
        result = StructuralBreakTests.bai_perron(y, X, max_breaks=2, min_segment=10)
        assert "n_breaks" in result
        assert "break_points" in result
