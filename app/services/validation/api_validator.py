"""
API Input Validator — Validates all incoming API requests.

Every number that enters the system gets validated here.
Catches bad data before it pollutes the database.

Validates:
- Transaction amounts (KES)
- M-Pesa amounts, phone numbers, codes
- Date ranges
- User inputs
- Statistical parameters

All error messages available in English (API) and Swahili (worker-facing).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from .validation_result import (
    ErrorCode,
    ErrorSeverity,
    ValidationError,
    ValidationResult,
)

logger = structlog.get_logger(__name__)


class ApiValidator:
    """
    Validates all API inputs for the Angavu Intelligence backend.

    Usage:
        validator = ApiValidator()
        result = validator.validate_amount(500.0)
        if not result.is_valid:
            return result.to_api_response()
    """

    # === THRESHOLDS ===
    MAX_TRANSACTION_AMOUNT = 1_000_000.0  # KES 1M max for informal workers
    MAX_MPESA_AMOUNT = 999_999.0          # M-Pesa per-transaction limit
    MIN_AMOUNT = 0.01                      # KES 0.01 minimum
    MAX_PERCENTAGE = 100.0
    MIN_PERCENTAGE = 0.0
    MPESA_MAX_DIGITS = 7

    # === REGEX ===
    MPESA_AMOUNT_RE = re.compile(r"^(0|[1-9]\d{0,6})$")
    MPESA_PHONE_RE = re.compile(r"^(?:254|\+254|0)?(7\d{8})$")
    MPESA_CODE_RE = re.compile(r"^[A-Z0-9]{10}$")

    # App launch date (earliest plausible transaction)
    APP_LAUNCH_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # =====================================================================
    # AMOUNT VALIDATION
    # =====================================================================

    def validate_amount(
        self,
        amount: Any,
        field_name: str = "amount",
        allow_zero: bool = False,
        allow_negative: bool = False,
    ) -> ValidationResult:
        """
        Validate a monetary amount.

        Args:
            amount: The amount to validate (any type)
            field_name: Name of the field for error messages
            allow_zero: Whether zero is acceptable
            allow_negative: Whether negative amounts are OK (e.g., overdraft)

        Returns:
            ValidationResult with safe value
        """
        # Type check
        if amount is None:
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.MISSING_FIELD,
                message=f"{field_name} is required",
                message_sw=f"{self._swahili_field(field_name)} inahitajika",
                field=field_name,
            )

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_INVALID,
                message=f"{field_name} must be a number",
                message_sw=f"{self._swahili_field(field_name)} lazima iwe nambari",
                field=field_name,
            )

        # NaN / Infinity
        if math.isnan(amount) or math.isinf(amount):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_NAN,
                message=f"{field_name} is not a valid number (NaN/Infinity)",
                message_sw="Nambari si sahihi",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        # Negative
        if amount < 0 and not allow_negative:
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_NEGATIVE,
                message=f"{field_name} cannot be negative",
                message_sw=f"{self._swahili_field(field_name)} haliwezi kuwa hasi",
                field=field_name,
            )

        # Zero
        if amount == 0 and not allow_zero:
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_ZERO,
                message=f"{field_name} cannot be zero",
                message_sw=f"{self._swahili_field(field_name)} haliwezi kuwa sifuri",
                field=field_name,
            )

        # Too large
        if amount > self.MAX_TRANSACTION_AMOUNT:
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_TOO_LARGE,
                message=f"{field_name} exceeds maximum (KES {self.MAX_TRANSACTION_AMOUNT:,.0f})",
                message_sw=f"{self._swahili_field(field_name)} ni kubwa sana — hakikisha ni sahihi",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        # Round to 2 decimal places (kill floating point drift)
        cleaned = round(amount, 2)
        return ValidationResult.valid(cleaned)

    # =====================================================================
    # PERCENTAGE VALIDATION
    # =====================================================================

    def validate_percentage(
        self,
        value: Any,
        field_name: str = "percentage",
        as_ratio: bool = False,
    ) -> ValidationResult:
        """
        Validate a percentage value.

        Args:
            value: The percentage (0-100) or ratio (0.0-1.0)
            field_name: Field name for errors
            as_ratio: If True, expect 0.0-1.0 range
        """
        try:
            value = float(value)
        except (TypeError, ValueError):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_INVALID,
                message=f"{field_name} must be a number",
                field=field_name,
            )

        if math.isnan(value) or math.isinf(value):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_NAN,
                message=f"{field_name} is not a valid number",
                field=field_name,
            )

        if as_ratio:
            if value < 0.0 or value > 1.0:
                corrected = max(0.0, min(1.0, value))
                return ValidationResult.invalid(
                    value=corrected,
                    code=ErrorCode.PERCENTAGE_OUT_OF_RANGE,
                    message=f"{field_name} must be between 0 and 1",
                    message_sw=f"{self._swahili_field(field_name)} lazima iwe kati ya 0 na 1",
                    field=field_name,
                )
        else:
            if value < self.MIN_PERCENTAGE or value > self.MAX_PERCENTAGE:
                corrected = max(self.MIN_PERCENTAGE, min(self.MAX_PERCENTAGE, value))
                return ValidationResult.invalid(
                    value=corrected,
                    code=ErrorCode.PERCENTAGE_OUT_OF_RANGE,
                    message=f"{field_name} must be between 0 and 100",
                    message_sw=f"{self._swahili_field(field_name)} lazima iwe kati ya 0 na 100",
                    field=field_name,
                )

        return ValidationResult.valid(round(value, 4))

    # =====================================================================
    # M-PESA VALIDATION
    # =====================================================================

    def validate_mpesa_amount(self, amount_str: str) -> ValidationResult:
        """
        Validate an M-Pesa amount string.
        M-Pesa uses integer amounts only, max 7 digits.
        """
        if not isinstance(amount_str, str):
            amount_str = str(amount_str)

        amount_str = amount_str.strip()

        if not self.MPESA_AMOUNT_RE.match(amount_str):
            return ValidationResult.invalid(
                value=0,
                code=ErrorCode.MPESA_AMOUNT_INVALID,
                message="M-Pesa amount must be digits only (max 7 digits)",
                message_sw="Kiasi cha M-Pesa si sahihi — tumia nambari tu",
            )

        amount = int(amount_str)

        if amount > self.MAX_MPESA_AMOUNT:
            return ValidationResult.invalid(
                value=0,
                code=ErrorCode.AMOUNT_TOO_LARGE,
                message=f"M-Pesa amount exceeds max (KES {self.MAX_MPESA_AMOUNT:,.0f})",
                message_sw=f"Kiasi cha M-Pesa ni kikubwa sana (max KES {self.MAX_MPESA_AMOUNT:,.0f})",
            )

        return ValidationResult.valid(amount)

    def validate_mpesa_phone(self, phone: str) -> ValidationResult:
        """
        Validate and normalize an M-Pesa phone number.
        Returns normalized format: 2547XXXXXXXX
        """
        if not isinstance(phone, str):
            return ValidationResult.invalid(
                value="",
                code=ErrorCode.MPESA_PHONE_INVALID,
                message="Phone number must be a string",
                message_sw="Nambari ya simu si sahihi",
            )

        cleaned = re.sub(r"[\s\-]", "", phone.strip())
        match = self.MPESA_PHONE_RE.match(cleaned)

        if not match:
            return ValidationResult.invalid(
                value="",
                code=ErrorCode.MPESA_PHONE_INVALID,
                message="Invalid M-Pesa phone number",
                message_sw="Nambari ya simu si sahihi — mfano: 0712345678",
            )

        normalized = f"254{match.group(1)}"
        return ValidationResult.valid(normalized)

    def validate_mpesa_code(self, code: str) -> ValidationResult:
        """Validate an M-Pesa transaction code (10 alphanumeric chars)."""
        if not isinstance(code, str):
            return ValidationResult.invalid(
                value="",
                code=ErrorCode.MPESA_CODE_INVALID,
                message="Transaction code must be a string",
                message_sw="Msimbo wa muamala si sahihi",
            )

        cleaned = code.strip().upper()

        if not self.MPESA_CODE_RE.match(cleaned):
            return ValidationResult.invalid(
                value="",
                code=ErrorCode.MPESA_CODE_INVALID,
                message="M-Pesa code must be 10 alphanumeric characters",
                message_sw="Msimbo wa M-Pesa lazima ziwe herufi na nambari 10",
            )

        return ValidationResult.valid(cleaned)

    # =====================================================================
    # DATE VALIDATION
    # =====================================================================

    def validate_date(
        self,
        date_value: Any,
        field_name: str = "date",
        allow_future: bool = False,
        max_age_days: int = 365,
    ) -> ValidationResult:
        """
        Validate a date/datetime.

        Args:
            date_value: datetime, ISO string, or Unix timestamp
            field_name: Field name for errors
            allow_future: Whether future dates are OK
            max_age_days: Maximum age in days
        """
        if date_value is None:
            return ValidationResult.invalid(
                value=datetime.now(timezone.utc),
                code=ErrorCode.MISSING_FIELD,
                message=f"{field_name} is required",
                message_sw=f"Tarehe inahitajika",
                field=field_name,
            )

        # Parse various input types
        dt = self._parse_date(date_value)
        if dt is None:
            return ValidationResult.invalid(
                value=datetime.now(timezone.utc),
                code=ErrorCode.DATE_INVALID,
                message=f"Invalid date format for {field_name}",
                message_sw="Muundo wa tarehe si sahihi",
                field=field_name,
            )

        now = datetime.now(timezone.utc)

        # Future check
        if not allow_future and dt > now:
            return ValidationResult.invalid(
                value=now,
                code=ErrorCode.DATE_FUTURE,
                message=f"{field_name} cannot be in the future",
                message_sw="Tarehe haiwezi kuwa ya baadaye",
                field=field_name,
            )

        # Too old check
        age_days = (now - dt).days
        if age_days > max_age_days:
            return ValidationResult.invalid(
                value=dt,
                code=ErrorCode.DATE_TOO_OLD,
                message=f"{field_name} is too old ({age_days} days)",
                message_sw="Tarehe ni ya zamani sana",
                field=field_name,
            )

        return ValidationResult.valid(dt)

    def validate_date_range(
        self,
        start: Any,
        end: Any,
        max_range_days: int = 365,
    ) -> ValidationResult:
        """Validate a date range (start < end, reasonable span)."""
        start_result = self.validate_date(start, "start_date")
        end_result = self.validate_date(end, "end_date", allow_future=True)

        if not start_result.is_valid:
            return start_result
        if not end_result.is_valid:
            return end_result

        start_dt = start_result.value
        end_dt = end_result.value

        if end_dt < start_dt:
            return ValidationResult.invalid(
                value=(start_dt, end_dt),
                code=ErrorCode.DATE_INVALID,
                message="End date must be after start date",
                message_sw="Tarehe ya mwisho lazima iwe baada ya ya kwanza",
            )

        range_days = (end_dt - start_dt).days
        if range_days > max_range_days:
            return ValidationResult.invalid(
                value=(start_dt, end_dt),
                code=ErrorCode.DATE_INVALID,
                message=f"Date range too large ({range_days} days, max {max_range_days})",
                message_sw="Kipindi kirefu sana",
            )

        return ValidationResult.valid((start_dt, end_dt))

    # =====================================================================
    # TRANSACTION VALIDATION
    # =====================================================================

    def validate_transaction(self, tx: Dict[str, Any]) -> ValidationResult:
        """
        Validate a complete transaction object.

        Args:
            tx: Transaction dict with keys: type, item, amount, date, etc.

        Returns:
            ValidationResult with validated/normalized transaction
        """
        errors = []
        warnings = []
        cleaned = {}

        # Required fields
        required = ["type", "amount"]
        for field in required:
            if field not in tx or tx[field] is None:
                errors.append(ValidationError(
                    code=ErrorCode.MISSING_FIELD,
                    message=f"{field} is required",
                    message_sw=f"{self._swahili_field(field)} inahitajika",
                    severity=ErrorSeverity.ERROR,
                    field=field,
                ))

        # Amount
        if "amount" in tx:
            amount_result = self.validate_amount(tx["amount"], "amount")
            cleaned["amount"] = amount_result.value
            errors.extend(amount_result.errors)
            warnings.extend(amount_result.warnings)

        # Type
        valid_types = {"SALE", "PURCHASE", "EXPENSE", "WITHDRAWAL", "DEPOSIT", "FEE", "REFUND", "OTHER"}
        tx_type = str(tx.get("type", "")).upper()
        if tx_type not in valid_types:
            errors.append(ValidationError(
                code=ErrorCode.INVALID_INPUT,
                message=f"Invalid transaction type: {tx_type}",
                message_sw="Aina ya muamala si sahihi",
                field="type",
            ))
        cleaned["type"] = tx_type

        # Item
        item = str(tx.get("item", "")).strip()
        if not item:
            errors.append(ValidationError(
                code=ErrorCode.MISSING_FIELD,
                message="item is required",
                message_sw="Jina la bidhaa linahitajika",
                field="item",
            ))
        cleaned["item"] = item

        # Date
        if "date" in tx:
            date_result = self.validate_date(tx["date"], "date")
            cleaned["date"] = date_result.value
            errors.extend(date_result.errors)

        # Payment method
        valid_methods = {"cash", "mpesa", "credit", "bank", "other"}
        method = str(tx.get("payment_method", "cash")).lower()
        if method not in valid_methods:
            warnings.append(ValidationError(
                code=ErrorCode.INVALID_INPUT,
                message=f"Unknown payment method: {method}",
                message_sw="Njia ya malipo haijulikani",
                severity=ErrorSeverity.WARNING,
                field="payment_method",
            ))
        cleaned["payment_method"] = method

        # M-Pesa specific validation
        if method == "mpesa" and "mpesa_code" in tx:
            code_result = self.validate_mpesa_code(tx["mpesa_code"])
            cleaned["mpesa_code"] = code_result.value
            errors.extend(code_result.errors)

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            value=cleaned if cleaned else tx,
            errors=errors,
            warnings=warnings,
        )

    # =====================================================================
    # BULK VALIDATION
    # =====================================================================

    def validate_transactions_batch(
        self,
        transactions: List[Dict[str, Any]],
        max_batch_size: int = 1000,
    ) -> Tuple[List[ValidationResult], List[Dict[str, Any]]]:
        """
        Validate a batch of transactions.

        Returns:
            Tuple of (validation_results, valid_transactions)
        """
        if len(transactions) > max_batch_size:
            error_result = ValidationResult.invalid(
                value=[],
                code=ErrorCode.INVALID_INPUT,
                message=f"Batch too large ({len(transactions)} > {max_batch_size})",
                message_sw="Miamala mingi sana",
            )
            return [error_result], []

        results = []
        valid_txs = []

        for i, tx in enumerate(transactions):
            result = self.validate_transaction(tx)
            results.append(result)
            if result.is_valid:
                valid_txs.append(result.value)

        return results, valid_txs

    # =====================================================================
    # HELPERS
    # =====================================================================

    def _parse_date(self, value: Any) -> Optional[datetime]:
        """Parse various date formats into datetime."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        if isinstance(value, (int, float)):
            # Unix timestamp
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (OSError, ValueError):
                return None

        if isinstance(value, str):
            # Try ISO format
            for fmt in [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]:
                try:
                    dt = datetime.strptime(value, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue

        return None

    def _swahili_field(self, field: str) -> str:
        """Translate common field names to Swahili."""
        translations = {
            "amount": "Kiasi",
            "balance": "Salio",
            "price": "Bei",
            "quantity": "Idadi",
            "date": "Tarehe",
            "item": "Bidhaa",
            "phone": "Nambari ya simu",
            "percentage": "Asilimia",
            "type": "Aina",
        }
        return translations.get(field.lower(), field)
