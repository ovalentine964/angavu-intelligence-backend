"""
Validation result types shared across all validators.

In financial software, every validation result must:
1. Carry the safe/corrected value (never return None for display)
2. Include a human-readable message (Swahili for workers, English for buyers)
3. Include machine-readable error codes for API responses
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def parse_date(value: Any) -> Optional[datetime]:
    """Parse various date formats into a timezone-aware UTC datetime.

    Accepts:
    - datetime objects (naive assumed UTC)
    - Unix timestamps (int/float)
    - ISO format strings and common date/time patterns

    Returns None if parsing fails.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, ValueError):
            return None

    if isinstance(value, str):
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


class ErrorSeverity(str, Enum):
    """Severity of validation issue."""
    INFO = "info"         # FYI, probably fine
    WARNING = "warning"   # Check this
    ERROR = "error"       # Invalid, must fix
    CRITICAL = "critical" # Dangerous, block immediately


class ErrorCode(str, Enum):
    """Machine-readable error codes for API responses."""
    # Amount errors
    AMOUNT_NEGATIVE = "amount_negative"
    AMOUNT_ZERO = "amount_zero"
    AMOUNT_TOO_LARGE = "amount_too_large"
    AMOUNT_NAN = "amount_nan"
    AMOUNT_INVALID = "amount_invalid"

    # Percentage errors
    PERCENTAGE_OUT_OF_RANGE = "percentage_out_of_range"

    # Date errors
    DATE_FUTURE = "date_future"
    DATE_TOO_OLD = "date_too_old"
    DATE_INVALID = "date_invalid"

    # M-Pesa errors
    MPESA_AMOUNT_INVALID = "mpesa_amount_invalid"
    MPESA_PHONE_INVALID = "mpesa_phone_invalid"
    MPESA_CODE_INVALID = "mpesa_code_invalid"

    # Transaction errors
    MISSING_FIELD = "missing_field"
    DUPLICATE_TRANSACTION = "duplicate_transaction"
    PRICE_SPIKE = "price_spike"

    # Statistical errors
    INSUFFICIENT_DATA = "insufficient_data"
    STATISTIC_OUT_OF_RANGE = "statistic_out_of_range"
    CONFIDENCE_TOO_LOW = "confidence_too_low"
    K_ANONYMITY_VIOLATION = "k_anonymity_violation"

    # Intelligence product errors
    QUALITY_SCORE_LOW = "quality_score_low"
    STALE_DATA = "stale_data"
    COVERAGE_LOW = "coverage_low"

    # General
    INVALID_INPUT = "invalid_input"
    INTERNAL_ERROR = "internal_error"


@dataclass
class ValidationError:
    """Single validation error with context."""
    code: ErrorCode
    message: str              # Human-readable (English for API, Swahili for workers)
    message_sw: str = ""      # Swahili translation (when reaching workers)
    severity: ErrorSeverity = ErrorSeverity.ERROR
    field: str = ""           # Which field failed
    value: Any = None         # The invalid value (sanitized)
    details: str = ""         # Technical details for logging

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API response."""
        result = {
            "code": self.code.value,
            "message": self.message,
            "severity": self.severity.value,
        }
        if self.field:
            result["field"] = self.field
        if self.message_sw:
            result["message_sw"] = self.message_sw
        return result


@dataclass
class ValidationResult:
    """
    Result of validation with safe value and error context.

    Design: ALWAYS carries a safe value. The caller can always
    use get_value() to get something displayable, even if invalid.
    """
    is_valid: bool
    value: Any                             # The validated (or corrected) value
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def has_issues(self) -> bool:
        return self.has_errors or self.has_warnings

    def get_value(self) -> Any:
        """Get the safe value regardless of validation state."""
        return self.value

    def get_messages(self) -> List[str]:
        """Get all error/warning messages."""
        return [e.message for e in self.errors + self.warnings]

    def get_messages_sw(self) -> List[str]:
        """Get Swahili messages for worker-facing display."""
        msgs = []
        for e in self.errors + self.warnings:
            msgs.append(e.message_sw or e.message)
        return msgs

    def get_error_codes(self) -> List[str]:
        """Get machine-readable error codes."""
        return [e.code.value for e in self.errors]

    def to_api_response(self) -> Dict[str, Any]:
        """Format for API error response."""
        if self.is_valid:
            return {"valid": True, "value": self.value}

        return {
            "valid": False,
            "value": self.value,  # Still include safe value
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }

    @classmethod
    def valid(cls, value: Any) -> ValidationResult:
        """Create a valid result."""
        return cls(is_valid=True, value=value)

    @classmethod
    def invalid(
        cls,
        value: Any,
        code: ErrorCode,
        message: str,
        message_sw: str = "",
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        field: str = "",
    ) -> ValidationResult:
        """Create an invalid result with one error."""
        error = ValidationError(
            code=code,
            message=message,
            message_sw=message_sw,
            severity=severity,
            field=field,
            value=value,
        )
        return cls(is_valid=False, value=value, errors=[error])

    @classmethod
    def warning(
        cls,
        value: Any,
        code: ErrorCode,
        message: str,
        message_sw: str = "",
    ) -> ValidationResult:
        """Create a valid result with a warning."""
        warn = ValidationError(
            code=code,
            message=message,
            message_sw=message_sw,
            severity=ErrorSeverity.WARNING,
        )
        return cls(is_valid=True, value=value, warnings=[warn])
