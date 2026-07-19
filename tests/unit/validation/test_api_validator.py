"""Tests for ApiValidator — validates all incoming API requests."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.validation.api_validator import ApiValidator
from app.services.validation.validation_result import ErrorCode


@pytest.fixture
def validator():
    return ApiValidator()


# =====================================================================
# AMOUNT VALIDATION
# =====================================================================


class TestValidateAmount:
    def test_valid_amount(self, validator):
        result = validator.validate_amount(500.0)
        assert result.is_valid
        assert result.value == 500.0

    def test_valid_integer(self, validator):
        result = validator.validate_amount(100)
        assert result.is_valid
        assert result.value == 100.0

    def test_rounds_to_two_decimals(self, validator):
        result = validator.validate_amount(100.999)
        assert result.is_valid
        assert result.value == 101.0

    def test_none_returns_error(self, validator):
        result = validator.validate_amount(None)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.MISSING_FIELD

    def test_string_returns_error(self, validator):
        result = validator.validate_amount("abc")
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.AMOUNT_INVALID

    def test_nan_returns_error(self, validator):
        result = validator.validate_amount(float("nan"))
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.AMOUNT_NAN

    def test_inf_returns_error(self, validator):
        result = validator.validate_amount(float("inf"))
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.AMOUNT_NAN

    def test_negative_returns_error(self, validator):
        result = validator.validate_amount(-100)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.AMOUNT_NEGATIVE

    def test_negative_allowed(self, validator):
        result = validator.validate_amount(-50, allow_negative=True)
        assert result.is_valid
        assert result.value == -50.0

    def test_zero_returns_error(self, validator):
        result = validator.validate_amount(0)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.AMOUNT_ZERO

    def test_zero_allowed(self, validator):
        result = validator.validate_amount(0, allow_zero=True)
        assert result.is_valid

    def test_too_large(self, validator):
        result = validator.validate_amount(2_000_000)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.AMOUNT_TOO_LARGE

    def test_max_boundary(self, validator):
        result = validator.validate_amount(1_000_000.0)
        assert result.is_valid

    def test_custom_field_name(self, validator):
        result = validator.validate_amount(None, field_name="price")
        assert "price" in result.errors[0].message

    def test_string_number_parses(self, validator):
        result = validator.validate_amount("500.50")
        assert result.is_valid
        assert result.value == 500.50


# =====================================================================
# PERCENTAGE VALIDATION
# =====================================================================


class TestValidatePercentage:
    def test_valid_percentage(self, validator):
        result = validator.validate_percentage(75.0)
        assert result.is_valid
        assert result.value == 75.0

    def test_zero(self, validator):
        result = validator.validate_percentage(0)
        assert result.is_valid

    def test_hundred(self, validator):
        result = validator.validate_percentage(100)
        assert result.is_valid

    def test_over_100(self, validator):
        result = validator.validate_percentage(150)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.PERCENTAGE_OUT_OF_RANGE

    def test_negative(self, validator):
        result = validator.validate_percentage(-5)
        assert not result.is_valid

    def test_ratio_mode_valid(self, validator):
        result = validator.validate_percentage(0.75, as_ratio=True)
        assert result.is_valid
        assert result.value == 0.75

    def test_ratio_mode_over_1(self, validator):
        result = validator.validate_percentage(1.5, as_ratio=True)
        assert not result.is_valid

    def test_nan(self, validator):
        result = validator.validate_percentage(float("nan"))
        assert not result.is_valid

    def test_inf(self, validator):
        result = validator.validate_percentage(float("inf"))
        assert not result.is_valid


# =====================================================================
# M-PESA VALIDATION
# =====================================================================


class TestValidateMpesa:
    def test_valid_amount(self, validator):
        result = validator.validate_mpesa_amount("500")
        assert result.is_valid
        assert result.value == 500

    def test_max_amount(self, validator):
        result = validator.validate_mpesa_amount("999999")
        assert result.is_valid

    def test_over_max(self, validator):
        result = validator.validate_mpesa_amount("1000000")
        assert not result.is_valid

    def test_non_digits(self, validator):
        result = validator.validate_mpesa_amount("abc")
        assert not result.is_valid

    def test_valid_phone(self, validator):
        result = validator.validate_mpesa_phone("0712345678")
        assert result.is_valid
        assert result.value == "254712345678"

    def test_phone_with_254(self, validator):
        result = validator.validate_mpesa_phone("254712345678")
        assert result.is_valid
        assert result.value == "254712345678"

    def test_phone_with_plus(self, validator):
        result = validator.validate_mpesa_phone("+254712345678")
        assert result.is_valid
        assert result.value == "254712345678"

    def test_invalid_phone(self, validator):
        result = validator.validate_mpesa_phone("12345")
        assert not result.is_valid

    def test_valid_code(self, validator):
        result = validator.validate_mpesa_code("QHJ4GR7K2L")
        assert result.is_valid
        assert result.value == "QHJ4GR7K2L"

    def test_code_lowercase_normalized(self, validator):
        result = validator.validate_mpesa_code("qhj4gr7k2l")
        assert result.is_valid
        assert result.value == "QHJ4GR7K2L"

    def test_invalid_code(self, validator):
        result = validator.validate_mpesa_code("short")
        assert not result.is_valid


# =====================================================================
# DATE VALIDATION
# =====================================================================


class TestValidateDate:
    def test_valid_datetime(self, validator):
        dt = datetime(2025, 6, 1, tzinfo=UTC)
        result = validator.validate_date(dt)
        assert result.is_valid

    def test_valid_iso_string(self, validator):
        result = validator.validate_date("2025-06-01")
        assert result.is_valid

    def test_valid_iso_datetime(self, validator):
        result = validator.validate_date("2025-06-01T12:00:00Z")
        assert result.is_valid

    def test_none_returns_error(self, validator):
        result = validator.validate_date(None)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.MISSING_FIELD

    def test_invalid_string(self, validator):
        result = validator.validate_date("not-a-date")
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.DATE_INVALID

    def test_future_date_rejected(self, validator):
        future = datetime.now(UTC) + timedelta(days=30)
        result = validator.validate_date(future)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.DATE_FUTURE

    def test_future_date_allowed(self, validator):
        future = datetime.now(UTC) + timedelta(days=30)
        result = validator.validate_date(future, allow_future=True)
        assert result.is_valid

    def test_too_old(self, validator):
        old = datetime(2020, 1, 1, tzinfo=UTC)
        result = validator.validate_date(old, max_age_days=30)
        assert not result.is_valid
        assert result.errors[0].code == ErrorCode.DATE_TOO_OLD

    def test_unix_timestamp(self, validator):
        result = validator.validate_date(1717200000)
        assert result.is_valid


# =====================================================================
# DATE RANGE VALIDATION
# =====================================================================


class TestValidateDateRange:
    def test_valid_range(self, validator):
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 6, 1, tzinfo=UTC)
        result = validator.validate_date_range(start, end)
        assert result.is_valid

    def test_end_before_start(self, validator):
        start = datetime(2025, 6, 1, tzinfo=UTC)
        end = datetime(2025, 1, 1, tzinfo=UTC)
        result = validator.validate_date_range(start, end)
        assert not result.is_valid

    def test_range_too_large(self, validator):
        start = datetime(2020, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 1, tzinfo=UTC)
        result = validator.validate_date_range(start, end, max_range_days=365)
        assert not result.is_valid


# =====================================================================
# TRANSACTION VALIDATION
# =====================================================================


class TestValidateTransaction:
    def test_valid_transaction(self, validator):
        tx = {
            "type": "SALE",
            "item": "Maize flour",
            "amount": 250.0,
            "date": "2025-06-01",
            "payment_method": "mpesa",
            "mpesa_code": "QHJ4GR7K2L",
        }
        result = validator.validate_transaction(tx)
        assert result.is_valid

    def test_missing_type(self, validator):
        tx = {"amount": 100}
        result = validator.validate_transaction(tx)
        assert not result.is_valid

    def test_missing_amount(self, validator):
        tx = {"type": "SALE"}
        result = validator.validate_transaction(tx)
        assert not result.is_valid

    def test_invalid_type(self, validator):
        tx = {"type": "INVALID", "amount": 100, "item": "test"}
        result = validator.validate_transaction(tx)
        assert not result.is_valid

    def test_all_valid_types(self, validator):
        for tx_type in ["SALE", "PURCHASE", "EXPENSE", "WITHDRAWAL", "DEPOSIT", "FEE", "REFUND", "OTHER"]:
            tx = {"type": tx_type, "amount": 100, "item": "test"}
            result = validator.validate_transaction(tx)
            assert result.is_valid, f"Type {tx_type} should be valid"


# =====================================================================
# BATCH VALIDATION
# =====================================================================


class TestValidateBatch:
    def test_valid_batch(self, validator):
        txs = [
            {"type": "SALE", "amount": 100, "item": "Item A"},
            {"type": "PURCHASE", "amount": 200, "item": "Item B"},
        ]
        results, valid = validator.validate_transactions_batch(txs)
        assert len(valid) == 2

    def test_batch_too_large(self, validator):
        txs = [{"type": "SALE", "amount": 100, "item": "x"}] * 1001
        results, valid = validator.validate_transactions_batch(txs)
        assert len(valid) == 0
        assert not results[0].is_valid

    def test_partial_valid(self, validator):
        txs = [
            {"type": "SALE", "amount": 100, "item": "Item A"},
            {"type": "INVALID", "amount": 200, "item": "Item B"},
        ]
        results, valid = validator.validate_transactions_batch(txs)
        assert len(valid) == 1
