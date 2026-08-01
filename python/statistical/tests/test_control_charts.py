"""Tests for control_charts.py — CUSUM, EWMA, Process Capability."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python', 'statistical'))

import numpy as np
import pytest
from control_charts import CUSUMChart, EWMAChart, ProcessCapability


class TestCUSUM:
    def test_in_control_data_no_signals(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 5, size=100)
        result = CUSUMChart.analyze(data, target=100, sigma=5)
        assert result["in_control"] is True
        assert len(result["signals_upper"]) == 0
        assert len(result["signals_lower"]) == 0

    def test_shift_detected(self):
        rng = np.random.default_rng(42)
        # In-control for 50 points, then shift up by 2σ
        data = np.concatenate([
            rng.normal(100, 5, size=50),
            rng.normal(110, 5, size=50)  # 2σ shift
        ])
        result = CUSUMChart.analyze(data, target=100, sigma=5)
        assert len(result["signals_upper"]) > 0

    def test_arl_present(self):
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, size=100)
        result = CUSUMChart.analyze(data)
        assert "arl0_in_control" in result
        assert result["arl0_in_control"] > 0


class TestEWMA:
    def test_in_control_no_signals(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 5, size=200)
        result = EWMAChart.analyze(data, target=100, sigma=5, lambda_param=0.2)
        assert result["in_control"] is True

    def test_ewma_smooths_data(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 10, size=50)
        result = EWMAChart.analyze(data, lambda_param=0.1)
        # EWMA should be smoother than raw data
        ewma = np.array(result["ewma"])
        assert np.std(np.diff(ewma)) < np.std(np.diff(data))

    def test_lambda_affects_smoothness(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 10, size=100)
        result_smooth = EWMAChart.analyze(data, lambda_param=0.1)
        result_rough = EWMAChart.analyze(data, lambda_param=0.5)
        ewma_smooth = np.array(result_smooth["ewma"])
        ewma_rough = np.array(result_rough["ewma"])
        # Lower lambda = smoother
        assert np.std(np.diff(ewma_smooth)) < np.std(np.diff(ewma_rough))


class TestProcessCapability:
    def test_capable_process(self):
        rng = np.random.default_rng(42)
        # Process with mean=100, sd=2, spec 90-110
        data = rng.normal(100, 2, size=200)
        result = ProcessCapability.analyze(data, usl=110, lsl=90)
        assert result["cp"] > 1.33  # capable
        assert result["cpk"] > 1.0

    def test_incapable_process(self):
        rng = np.random.default_rng(42)
        # Process with mean=100, sd=8, spec 90-110
        data = rng.normal(100, 8, size=200)
        result = ProcessCapability.analyze(data, usl=110, lsl=90)
        assert result["cpk"] < 1.0  # not capable

    def test_off_center_process(self):
        rng = np.random.default_rng(42)
        # Process centered at 105 instead of 100, spec 90-110
        data = rng.normal(105, 2, size=200)
        result = ProcessCapability.analyze(data, usl=110, lsl=90)
        assert result["cp"] > result["cpk"]  # cpk < cp due to off-center

    def test_six_sigma_level(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 1, size=500)
        result = ProcessCapability.analyze(data, usl=106, lsl=94)
        assert result["sigma_level"] >= 4.0

    def test_ppm_estimation(self):
        rng = np.random.default_rng(42)
        data = rng.normal(100, 2, size=200)
        result = ProcessCapability.analyze(data, usl=110, lsl=90)
        assert result["ppm_defect_rate"] < 1000  # should be low for capable process
