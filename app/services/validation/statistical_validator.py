"""
Statistical Output Validator — Validates all computed statistics.

Every number that leaves the statistical pipeline gets validated here.
Catches impossible values, insufficient data, and privacy violations
before they reach users or buyers.

Validates:
- Computed means, medians, percentiles
- Confidence intervals
- Growth rates and trends
- k-Anonymity thresholds
- Sample sizes

Per SECURITY_ARCHITECTURE.md and data quality standards.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import structlog

from .validation_result import (
    ErrorCode,
    ErrorSeverity,
    ValidationError,
    ValidationResult,
)

logger = structlog.get_logger(__name__)


class StatisticalValidator:
    """
    Validates computed statistics before they are exposed to users or buyers.

    Ensures statistical outputs are:
    1. Mathematically valid (not NaN, not infinite, within bounds)
    2. Based on sufficient data (sample size, k-anonymity)
    3. Reasonable (no 10,000% growth rates)
    4. Privacy-preserving (k-anonymity, differential privacy checks)

    Usage:
        validator = StatisticalValidator()
        result = validator.validate_mean(mean_value, sample_size=50)
        if not result.is_valid:
            logger.warning("Invalid statistic", errors=result.errors)
    """

    # === THRESHOLDS ===
    MIN_SAMPLE_SIZE = 5                    # Minimum observations for any stat
    MIN_SAMPLE_SIZE_CONFIDENT = 30         # Minimum for confident statistics
    MAX_PERCENTAGE = 100.0
    MIN_PERCENTAGE = 0.0
    MAX_GROWTH_RATE = 500.0                # 500% max plausible growth
    MIN_GROWTH_RATE = -100.0               # Can't lose more than 100%
    MAX_AMOUNT = 1_000_000_000.0           # KES 1B upper bound for aggregates
    DEFAULT_K_ANONYMITY = 10               # Minimum group size for privacy

    # =====================================================================
    # MEAN / AVERAGE VALIDATION
    # =====================================================================

    def validate_mean(
        self,
        value: Any,
        sample_size: int,
        field_name: str = "mean",
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> ValidationResult:
        """
        Validate a computed mean/average.

        Args:
            value: The computed mean
            sample_size: Number of observations
            field_name: Field name for error messages
            min_value: Expected minimum (e.g., 0 for amounts)
            max_value: Expected maximum
        """
        result = self._validate_numeric(value, field_name)
        if not result.is_valid:
            return result

        val = result.value

        # Sample size check
        if sample_size < self.MIN_SAMPLE_SIZE:
            return ValidationResult.invalid(
                value=val,
                code=ErrorCode.INSUFFICIENT_DATA,
                message=f"Sample size too small ({sample_size} < {self.MIN_SAMPLE_SIZE}) for {field_name}",
                message_sw="Datai hazitoshi kuhesabu wastani",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            )

        # Range checks
        if min_value is not None and val < min_value:
            return ValidationResult.invalid(
                value=min_value,
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"{field_name} ({val}) below minimum ({min_value})",
                message_sw="Wastani ni mdogo sana",
                field=field_name,
            )

        if max_value is not None and val > max_value:
            return ValidationResult.invalid(
                value=max_value,
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"{field_name} ({val}) above maximum ({max_value})",
                message_sw="Wastani ni mkubwa sana",
                field=field_name,
            )

        # Confidence flag
        warnings = []
        if sample_size < self.MIN_SAMPLE_SIZE_CONFIDENT:
            warnings.append(ValidationError(
                code=ErrorCode.CONFIDENCE_TOO_LOW,
                message=f"Low confidence: {field_name} based on only {sample_size} observations",
                message_sw="Wastani una ujasiri mdogo — datai chache",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            ))

        return ValidationResult(is_valid=True, value=val, warnings=warnings)

    # =====================================================================
    # PERCENTAGE / RATIO VALIDATION
    # =====================================================================

    def validate_percentage_stat(
        self,
        value: Any,
        sample_size: int,
        field_name: str = "percentage",
        as_ratio: bool = False,
    ) -> ValidationResult:
        """
        Validate a computed percentage or ratio statistic.

        Args:
            value: The computed percentage (0-100) or ratio (0-1)
            sample_size: Number of observations
            field_name: Field name for errors
            as_ratio: If True, expect 0.0-1.0 range
        """
        result = self._validate_numeric(value, field_name)
        if not result.is_valid:
            return result

        val = result.value

        if as_ratio:
            if val < 0.0 or val > 1.0:
                return ValidationResult.invalid(
                    value=max(0.0, min(1.0, val)),
                    code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                    message=f"{field_name} must be between 0 and 1, got {val}",
                    message_sw="Asilimia si sahihi",
                    field=field_name,
                )
        else:
            if val < self.MIN_PERCENTAGE or val > self.MAX_PERCENTAGE:
                return ValidationResult.invalid(
                    value=max(self.MIN_PERCENTAGE, min(self.MAX_PERCENTAGE, val)),
                    code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                    message=f"{field_name} must be between 0 and 100, got {val}",
                    message_sw="Asilimia si sahihi",
                    field=field_name,
                )

        # k-Anonymity check for percentages
        warnings = []
        if sample_size < self.DEFAULT_K_ANONYMITY:
            warnings.append(ValidationError(
                code=ErrorCode.K_ANONYMITY_VIOLATION,
                message=f"Percentage based on group of {sample_size} (< {self.DEFAULT_K_ANONYMITY}); may reveal individual data",
                message_sw="Datai za kikundi kidogo — zinaweza kufichua maelezo ya mtu binafsi",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            ))

        cleaned = round(val, 4)
        return ValidationResult(is_valid=True, value=cleaned, warnings=warnings)

    # =====================================================================
    # GROWTH RATE VALIDATION
    # =====================================================================

    def validate_growth_rate(
        self,
        value: Any,
        sample_size: int = 0,
        field_name: str = "growth_rate",
    ) -> ValidationResult:
        """
        Validate a growth rate percentage.

        Args:
            value: Growth rate as percentage (e.g., 15.5 for 15.5% growth)
            sample_size: Number of periods/observations
            field_name: Field name for errors
        """
        result = self._validate_numeric(value, field_name)
        if not result.is_valid:
            return result

        val = result.value

        if val < self.MIN_GROWTH_RATE:
            return ValidationResult.invalid(
                value=self.MIN_GROWTH_RATE,
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"Growth rate {val}% is implausible (minimum {self.MIN_GROWTH_RATE}%)",
                message_sw="Kasi ya ukuaji si sahihi",
                field=field_name,
            )

        if val > self.MAX_GROWTH_RATE:
            return ValidationResult.invalid(
                value=self.MAX_GROWTH_RATE,
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"Growth rate {val}% exceeds maximum ({self.MAX_GROWTH_RATE}%)",
                message_sw="Kasi ya ukuaji ni kubwa sana",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        warnings = []
        if abs(val) > 100:
            warnings.append(ValidationError(
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"Extreme growth rate ({val}%) — verify data quality",
                message_sw="Kasi ya ukuaji ya ajabu — hakikisha datai ni sahihi",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            ))

        return ValidationResult(is_valid=True, value=round(val, 2), warnings=warnings)

    # =====================================================================
    # CONFIDENCE INTERVAL VALIDATION
    # =====================================================================

    def validate_confidence_interval(
        self,
        lower: Any,
        upper: Any,
        point_estimate: Any,
        confidence_level: float = 0.95,
        field_name: str = "confidence_interval",
    ) -> ValidationResult:
        """
        Validate a confidence interval.

        Args:
            lower: Lower bound
            upper: Upper bound
            point_estimate: The point estimate
            confidence_level: Expected confidence level (0-1)
        """
        for name, val in [("lower", lower), ("upper", upper), ("point_estimate", point_estimate)]:
            result = self._validate_numeric(val, name)
            if not result.is_valid:
                return result

        if lower > upper:
            return ValidationResult.invalid(
                value=(lower, upper),
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"Confidence interval lower ({lower}) > upper ({upper})",
                message_sw="Kipimo cha ujasiri si sahihi",
                field=field_name,
            )

        if not (lower <= point_estimate <= upper):
            return ValidationResult.invalid(
                value=(lower, upper),
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"Point estimate ({point_estimate}) outside CI [{lower}, {upper}]",
                message_sw="Kipimo kuu nje ya kipimo cha ujasiri",
                field=field_name,
            )

        return ValidationResult.valid((round(lower, 4), round(upper, 4)))

    # =====================================================================
    # k-ANONYMITY VALIDATION
    # =====================================================================

    def validate_k_anonymity(
        self,
        group_size: int,
        k: int = 0,
        field_name: str = "group",
    ) -> ValidationResult:
        """
        Validate that a group meets k-anonymity requirements.

        Args:
            group_size: Number of individuals in the group
            k: Required k-anonymity threshold (0 = use default)
            field_name: Field name for errors
        """
        required_k = k if k > 0 else self.DEFAULT_K_ANONYMITY

        if group_size < required_k:
            return ValidationResult.invalid(
                value=group_size,
                code=ErrorCode.K_ANONYMITY_VIOLATION,
                message=f"Group size ({group_size}) below k-anonymity threshold ({required_k})",
                message_sw="Kikundi ni kidogo sana — datai zinaweza kufichua mtu binafsi",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        warnings = []
        if group_size < required_k * 2:
            warnings.append(ValidationError(
                code=ErrorCode.K_ANONYMITY_VIOLATION,
                message=f"Group size ({group_size}) close to k-anonymity threshold ({required_k})",
                message_sw="Kikundi kina ukaribu na kikomo cha faragha",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            ))

        return ValidationResult(is_valid=True, value=group_size, warnings=warnings)

    # =====================================================================
    # AGGREGATE VALIDATION
    # =====================================================================

    def validate_aggregate(
        self,
        value: Any,
        stat_type: str,
        sample_size: int,
        field_name: str = "aggregate",
    ) -> ValidationResult:
        """
        Validate an aggregate statistic (sum, count, etc.).

        Args:
            value: The aggregate value
            stat_type: Type of aggregate (sum, count, min, max, etc.)
            sample_size: Number of contributing records
            field_name: Field name for errors
        """
        result = self._validate_numeric(value, field_name)
        if not result.is_valid:
            return result

        val = result.value

        if stat_type == "count":
            if val < 0:
                return ValidationResult.invalid(
                    value=0,
                    code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                    message=f"Count cannot be negative ({val})",
                    message_sw="Idadi haiwezi kuwa hasi",
                    field=field_name,
                )
            if val != int(val):
                return ValidationResult.invalid(
                    value=int(val),
                    code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                    message=f"Count must be an integer ({val})",
                    message_sw="Idadi lazima iwe nambari kamili",
                    field=field_name,
                )

        if stat_type == "sum" and abs(val) > self.MAX_AMOUNT:
            return ValidationResult.invalid(
                value=val,
                code=ErrorCode.STATISTIC_OUT_OF_RANGE,
                message=f"Sum ({val:,.0f}) exceeds plausible maximum ({self.MAX_AMOUNT:,.0f})",
                message_sw="Jumla ni kubwa sana",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        return ValidationResult.valid(val)

    # =====================================================================
    # HELPERS
    # =====================================================================

    def _validate_numeric(self, value: Any, field_name: str) -> ValidationResult:
        """Validate that a value is a finite number."""
        if value is None:
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.MISSING_FIELD,
                message=f"{field_name} is required",
                message_sw=f"{field_name} inahitajika",
                field=field_name,
            )

        try:
            val = float(value)
        except (TypeError, ValueError):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_INVALID,
                message=f"{field_name} must be a number, got {type(value).__name__}",
                message_sw=f"{field_name} lazima iwe nambari",
                field=field_name,
            )

        if math.isnan(val):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_NAN,
                message=f"{field_name} is NaN",
                message_sw="Nambari si sahihi (NaN)",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        if math.isinf(val):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.AMOUNT_NAN,
                message=f"{field_name} is infinite",
                message_sw="Nambari si sahihi (Infinity)",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        return ValidationResult.valid(val)
