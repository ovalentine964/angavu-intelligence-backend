"""
Tests for SPC (Statistical Process Control): X-bar, R, p, c charts and acceptance sampling.
"""

import numpy as np
import pytest
from python.statistical.spc_full import (
    XbarChart,
    RChart,
    PChart,
    CChart,
    AcceptanceSampling,
)


class TestXbarChart:
    def test_in_control_process(self):
        """Stable process should be in control."""
        rng = np.random.RandomState(42)
        data = rng.normal(10, 0.5, 50)
        result = XbarChart.analyze(data, subgroup_size=5)
        assert result["in_control"] == True  # noqa: E712
        assert len(result["signals"]) == 0

    def test_out_of_control_detected(self):
        """Shifted subgroup should trigger signal."""
        data = np.array([
            10, 10, 10, 10, 10,
            10, 10, 10, 10, 10,
            50, 50, 50, 50, 50,
            10, 10, 10, 10, 10,
        ])
        result = XbarChart.analyze(data, subgroup_size=5)
        assert result["in_control"] == False  # noqa: E712
        assert 2 in result["signals"]

    def test_insufficient_data(self):
        """Fails with too few observations."""
        data = np.array([1, 2, 3, 4, 5])
        result = XbarChart.analyze(data, subgroup_size=5)
        assert "error" in result


class TestRChart:
    def test_stable_variability(self):
        """Low variability process should be in control."""
        rng = np.random.RandomState(42)
        data = rng.normal(10, 0.1, 50)
        result = RChart.analyze(data, subgroup_size=5)
        assert result["in_control"] == True  # noqa: E712

    def test_high_variability_detected(self):
        """High range subgroup should trigger signal."""
        data = np.array([
            10, 10, 10, 10, 10,
            1, 50, 5, 45, 25,
            10, 10, 10, 10, 10,
        ])
        result = RChart.analyze(data, subgroup_size=5)
        assert result["in_control"] == False  # noqa: E712


class TestPChart:
    def test_stable_defect_rate(self):
        """Stable ~5% defect rate should be in control."""
        n_insp = np.array([100, 100, 100, 100, 100, 100, 100, 100])
        n_nonconf = np.array([5, 4, 6, 5, 5, 4, 6, 5])
        result = PChart.analyze(n_insp, n_nonconf)
        assert result["in_control"] == True  # noqa: E712
        assert abs(result["p_bar"] - 0.05) < 0.01

    def test_spike_detected(self):
        """Defect spike should trigger signal."""
        n_insp = np.array([100, 100, 100, 100, 100])
        n_nonconf = np.array([5, 4, 50, 5, 4])
        result = PChart.analyze(n_insp, n_nonconf)
        assert result["in_control"] == False  # noqa: E712

    def test_mismatched_lengths(self):
        """Fails with mismatched array lengths."""
        result = PChart.analyze(np.array([100, 100]), np.array([5]))
        assert "error" in result


class TestCChart:
    def test_stable_defect_count(self):
        """Stable defect count should be in control."""
        data = np.array([3, 4, 3, 5, 4, 3, 4, 3, 5, 4])
        result = CChart.analyze(data)
        assert result["in_control"] == True  # noqa: E712

    def test_spike_detected(self):
        """Defect spike should trigger signal."""
        data = np.array([3, 4, 3, 4, 3, 50, 3, 4, 3, 4])
        result = CChart.analyze(data)
        assert result["in_control"] == False  # noqa: E712

    def test_insufficient_data(self):
        """Fails with < 5 subgroups."""
        data = np.array([1, 2, 3])
        result = CChart.analyze(data)
        assert "error" in result


class TestAcceptanceSampling:
    def test_single_sampling_perfect_quality(self):
        """Zero defects should always be accepted."""
        result = AcceptanceSampling.single_sampling(
            batch_size=1000, sample_size=50, accept_number=2, defect_rate=0.0
        )
        assert result["prob_acceptance"] == 1.0

    def test_single_sampling_high_defect_rate(self):
        """High defect rate should have low acceptance probability."""
        result = AcceptanceSampling.single_sampling(
            batch_size=1000, sample_size=50, accept_number=2, defect_rate=0.20
        )
        assert result["prob_acceptance"] < 0.1

    def test_single_sampling_oc_curve(self):
        """OC curve should decrease with increasing defect rate."""
        result = AcceptanceSampling.single_sampling(
            batch_size=1000, sample_size=50, accept_number=2, defect_rate=0.05
        )
        assert "oc_curve" in result
        assert result["prob_acceptance"] > 0

    def test_double_sampling(self):
        """Double sampling plan returns expected fields."""
        result = AcceptanceSampling.double_sampling(
            batch_size=1000, n1=30, c1=1, r1=3, n2=30, c2=4, defect_rate=0.05
        )
        assert result["plan_type"] == "double"
        assert result["asn"] >= 30

    def test_sequential_sampling(self):
        """Sequential plan returns boundaries."""
        result = AcceptanceSampling.sequential_sampling(
            batch_size=1000, accept_number=2, reject_number=5, defect_rate=0.05
        )
        assert result["plan_type"] == "sequential"
        assert len(result["boundaries"]) > 0
