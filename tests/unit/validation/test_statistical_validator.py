"""Tests for StatisticalValidator — validates computed statistics."""


import pytest

from app.services.validation.statistical_validator import StatisticalValidator
from app.services.validation.validation_result import ErrorCode


@pytest.fixture
def validator():
    return StatisticalValidator()


# =====================================================================
# MEAN VALIDATION
# =====================================================================


class TestValidateMean:
    def test_valid_mean(self, validator):
        result = validator.validate_mean(50.0, sample_size=100)
        assert result.is_valid
        assert result.value == 50.0

    def test_valid_integer(self, validator):
        result = validator.validate_mean(50, sample_size=100)
        assert result.is_valid

    def test_nan_rejected(self, validator):
        result = validator.validate_mean(float("nan"), sample_size=100)
        assert not result.is_valid

    def test_inf_rejected(self, validator):
        result = validator.validate_mean(float("inf"), sample_size=100)
        assert not result.is_valid

    def test_none_rejected(self, validator):
        result = validator.validate_mean(None, sample_size=100)
        assert not result.is_valid

    def test_string_rejected(self, validator):
        result = validator.validate_mean("abc", sample_size=100)
        assert not result.is_valid

    def test_small_sample_warns(self, validator):
        result = validator.validate_mean(50.0, sample_size=3)
        assert result.is_valid
        assert result.has_warnings

    def test_below_min_sample(self, validator):
        result = validator.validate_mean(50.0, sample_size=2)
        assert result.is_valid  # Warning, not error
        assert result.has_warnings

    def test_below_min_value(self, validator):
        result = validator.validate_mean(-10.0, sample_size=50, min_value=0)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.STATISTIC_OUT_OF_RANGE

    def test_above_max_value(self, validator):
        result = validator.validate_mean(1_000_000.0, sample_size=50, max_value=100_000)
        assert not result.is_valid


# =====================================================================
# PERCENTAGE STAT VALIDATION
# =====================================================================


class TestValidatePercentageStat:
    def test_valid_percentage(self, validator):
        result = validator.validate_percentage_stat(75.0, sample_size=50)
        assert result.is_valid
        assert result.value == 75.0

    def test_over_100(self, validator):
        result = validator.validate_percentage_stat(150.0, sample_size=50)
        assert not result.is_valid

    def test_negative(self, validator):
        result = validator.validate_percentage_stat(-5.0, sample_size=50)
        assert not result.is_valid

    def test_ratio_mode_valid(self, validator):
        result = validator.validate_percentage_stat(0.75, sample_size=50, as_ratio=True)
        assert result.is_valid
        assert result.value == 0.75

    def test_ratio_mode_over_1(self, validator):
        result = validator.validate_percentage_stat(1.5, sample_size=50, as_ratio=True)
        assert not result.is_valid

    def test_k_anonymity_warning(self, validator):
        result = validator.validate_percentage_stat(50.0, sample_size=5)
        assert result.is_valid
        assert result.has_warnings
        assert any(
            w.code == ErrorCode.K_ANONYMITY_VIOLATION for w in result.warnings
        )

    def test_rounds_to_4_decimals(self, validator):
        result = validator.validate_percentage_stat(75.123456, sample_size=50)
        assert result.is_valid
        assert result.value == 75.1235


# =====================================================================
# GROWTH RATE VALIDATION
# =====================================================================


class TestValidateGrowthRate:
    def test_valid_growth(self, validator):
        result = validator.validate_growth_rate(15.5)
        assert result.is_valid
        assert result.value == 15.5

    def test_negative_growth(self, validator):
        result = validator.validate_growth_rate(-20.0)
        assert result.is_valid

    def test_zero_growth(self, validator):
        result = validator.validate_growth_rate(0.0)
        assert result.is_valid

    def test_too_negative(self, validator):
        result = validator.validate_growth_rate(-150.0)
        assert not result.is_valid

    def test_too_positive(self, validator):
        result = validator.validate_growth_rate(600.0)
        assert not result.is_valid

    def test_extreme_warns(self, validator):
        result = validator.validate_growth_rate(200.0)
        assert result.is_valid
        assert result.has_warnings

    def test_nan(self, validator):
        result = validator.validate_growth_rate(float("nan"))
        assert not result.is_valid


# =====================================================================
# CONFIDENCE INTERVAL VALIDATION
# =====================================================================


class TestValidateConfidenceInterval:
    def test_valid_ci(self, validator):
        result = validator.validate_confidence_interval(10.0, 20.0, 15.0)
        assert result.is_valid

    def test_lower_gt_upper(self, validator):
        result = validator.validate_confidence_interval(20.0, 10.0, 15.0)
        assert not result.is_valid

    def test_estimate_outside_ci(self, validator):
        result = validator.validate_confidence_interval(10.0, 20.0, 25.0)
        assert not result.is_valid

    def test_estimate_on_boundary(self, validator):
        result = validator.validate_confidence_interval(10.0, 20.0, 10.0)
        assert result.is_valid

    def test_nan_in_ci(self, validator):
        result = validator.validate_confidence_interval(float("nan"), 20.0, 15.0)
        assert not result.is_valid


# =====================================================================
# k-ANONYMITY VALIDATION
# =====================================================================


class TestValidateKAnonymity:
    def test_valid_group(self, validator):
        result = validator.validate_k_anonymity(50)
        assert result.is_valid

    def test_too_small(self, validator):
        result = validator.validate_k_anonymity(3)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.K_ANONYMITY_VIOLATION

    def test_custom_k(self, validator):
        result = validator.validate_k_anonymity(20, k=25)
        assert not result.is_valid

    def test_close_to_threshold_warns(self, validator):
        result = validator.validate_k_anonymity(15)
        assert result.is_valid
        assert result.has_warnings


# =====================================================================
# AGGREGATE VALIDATION
# =====================================================================


class TestValidateAggregate:
    def test_valid_sum(self, validator):
        result = validator.validate_aggregate(50000.0, "sum", sample_size=100)
        assert result.is_valid

    def test_sum_too_large(self, validator):
        result = validator.validate_aggregate(2_000_000_000.0, "sum", sample_size=100)
        assert not result.is_valid

    def test_valid_count(self, validator):
        result = validator.validate_aggregate(100, "count", sample_size=100)
        assert result.is_valid

    def test_negative_count(self, validator):
        result = validator.validate_aggregate(-5, "count", sample_size=100)
        assert not result.is_valid

    def test_fractional_count(self, validator):
        result = validator.validate_aggregate(5.5, "count", sample_size=100)
        assert not result.is_valid

    def test_nan(self, validator):
        result = validator.validate_aggregate(float("nan"), "sum", sample_size=100)
        assert not result.is_valid
