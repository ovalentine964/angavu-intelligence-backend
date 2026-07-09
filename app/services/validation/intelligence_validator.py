"""
Intelligence Product Validator — Validates reports before delivery.

Every intelligence product (report, insight, recommendation) that leaves
the system gets validated here. Catches low-quality, stale, or misleading
content before it reaches buyers.

Validates:
- Report quality scores
- Data freshness / staleness
- Geographic and demographic coverage
- Insight confidence levels
- Formatting and completeness

Per SECURITY_ARCHITECTURE.md and intelligence product standards.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from .validation_result import (
    ErrorCode,
    ErrorSeverity,
    ValidationError,
    ValidationResult,
    parse_date,
)

logger = structlog.get_logger(__name__)


class IntelligenceValidator:
    """
    Validates intelligence products before delivery to buyers.

    Ensures intelligence products:
    1. Meet minimum quality thresholds
    2. Are based on fresh data (not stale)
    3. Have sufficient geographic/demographic coverage
    4. Don't mislead with low-confidence claims
    5. Are properly formatted and complete

    Usage:
        validator = IntelligenceValidator()
        result = validator.validate_report(report_dict)
        if not result.is_valid:
            # Block delivery, log issue
            logger.warning("Report blocked", errors=result.errors)
    """

    # === THRESHOLDS ===
    MIN_QUALITY_SCORE = 60.0               # Minimum quality score (0-100)
    MIN_CONFIDENCE_SCORE = 0.7             # Minimum confidence (0-1)
    MAX_DATA_AGE_DAYS = 30                 # Data older than this is stale
    MAX_DATA_AGE_DAYS_CRITICAL = 90        # Absolutely stale
    MIN_COVERAGE_PERCENT = 30.0            # Minimum geographic coverage %
    MIN_SAMPLE_SIZE = 10                   # Minimum data points for a report
    MAX_INSIGHTS_PER_REPORT = 50           # Prevent bloated reports

    # =====================================================================
    # QUALITY SCORE VALIDATION
    # =====================================================================

    def validate_quality_score(
        self,
        score: Any,
        field_name: str = "quality_score",
    ) -> ValidationResult:
        """
        Validate a quality score.

        Args:
            score: Quality score (0-100)
            field_name: Field name for errors
        """
        try:
            score = float(score)
        except (TypeError, ValueError):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.QUALITY_SCORE_LOW,
                message=f"{field_name} must be a number",
                message_sw="Alama ya ubora si sahihi",
                field=field_name,
            )

        if math.isnan(score) or math.isinf(score):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.QUALITY_SCORE_LOW,
                message=f"{field_name} is not a valid number",
                message_sw="Alama ya ubora si sahihi",
                field=field_name,
            )

        score = max(0.0, min(100.0, score))

        if score < self.MIN_QUALITY_SCORE:
            return ValidationResult.invalid(
                value=score,
                code=ErrorCode.QUALITY_SCORE_LOW,
                message=f"Quality score {score:.1f} below minimum ({self.MIN_QUALITY_SCORE})",
                message_sw=f"Alama ya ubora ({score:.0f}) ni ndogo sana (min {self.MIN_QUALITY_SCORE:.0f})",
                severity=ErrorSeverity.ERROR,
                field=field_name,
            )

        warnings = []
        if score < self.MIN_QUALITY_SCORE * 1.25:
            warnings.append(ValidationError(
                code=ErrorCode.QUALITY_SCORE_LOW,
                message=f"Quality score {score:.1f} is marginal — consider enriching data",
                message_sw="Alama ya ubora ni ya kati — ongeza datai",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            ))

        return ValidationResult(is_valid=True, value=round(score, 1), warnings=warnings)

    # =====================================================================
    # DATA FRESHNESS VALIDATION
    # =====================================================================

    def validate_data_freshness(
        self,
        data_date: Any,
        field_name: str = "data_date",
    ) -> ValidationResult:
        """
        Validate that data is fresh enough for an intelligence product.

        Args:
            data_date: Date of the most recent data (datetime or ISO string)
            field_name: Field name for errors
        """
        dt = self._parse_date(data_date)
        if dt is None:
            return ValidationResult.invalid(
                value=datetime.now(timezone.utc),
                code=ErrorCode.DATE_INVALID,
                message=f"Invalid date for {field_name}",
                message_sw="Tarehe si sahihi",
                field=field_name,
            )

        now = datetime.now(timezone.utc)
        age_days = (now - dt).days

        if age_days > self.MAX_DATA_AGE_DAYS_CRITICAL:
            return ValidationResult.invalid(
                value=dt,
                code=ErrorCode.STALE_DATA,
                message=f"Data is critically stale ({age_days} days old, max {self.MAX_DATA_AGE_DAYS_CRITICAL})",
                message_sw=f"Datai ni ya zamani sana (siku {age_days})",
                severity=ErrorSeverity.CRITICAL,
                field=field_name,
            )

        if age_days > self.MAX_DATA_AGE_DAYS:
            return ValidationResult.invalid(
                value=dt,
                code=ErrorCode.STALE_DATA,
                message=f"Data is stale ({age_days} days old, max {self.MAX_DATA_AGE_DAYS})",
                message_sw=f"Datai ni ya zamani (siku {age_days})",
                severity=ErrorSeverity.ERROR,
                field=field_name,
            )

        warnings = []
        if age_days > self.MAX_DATA_AGE_DAYS * 0.75:
            warnings.append(ValidationError(
                code=ErrorCode.STALE_DATA,
                message=f"Data is {age_days} days old — approaching staleness threshold",
                message_sw=f"Datai ni ya siku {age_days} — inakaribia kukoma",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            ))

        return ValidationResult(is_valid=True, value=dt, warnings=warnings)

    # =====================================================================
    # COVERAGE VALIDATION
    # =====================================================================

    def validate_coverage(
        self,
        coverage_pct: Any,
        field_name: str = "coverage",
    ) -> ValidationResult:
        """
        Validate geographic or demographic coverage percentage.

        Args:
            coverage_pct: Coverage percentage (0-100)
            field_name: Field name for errors
        """
        try:
            coverage = float(coverage_pct)
        except (TypeError, ValueError):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.COVERAGE_LOW,
                message=f"{field_name} must be a number",
                message_sw="Ufuniko si sahihi",
                field=field_name,
            )

        if math.isnan(coverage) or math.isinf(coverage):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.COVERAGE_LOW,
                message=f"{field_name} is not a valid number",
                message_sw="Ufuniko si sahihi",
                field=field_name,
            )

        coverage = max(0.0, min(100.0, coverage))

        if coverage < self.MIN_COVERAGE_PERCENT:
            return ValidationResult.invalid(
                value=coverage,
                code=ErrorCode.COVERAGE_LOW,
                message=f"Coverage {coverage:.1f}% below minimum ({self.MIN_COVERAGE_PERCENT}%)",
                message_sw=f"Ufuniko ({coverage:.0f}%) ni mdogo sana (min {self.MIN_COVERAGE_PERCENT:.0f}%)",
                severity=ErrorSeverity.ERROR,
                field=field_name,
            )

        warnings = []
        if coverage < self.MIN_COVERAGE_PERCENT * 1.5:
            warnings.append(ValidationError(
                code=ErrorCode.COVERAGE_LOW,
                message=f"Coverage {coverage:.1f}% is marginal — limited geographic representation",
                message_sw="Ufuniko ni wa kati — uwakilishi mdogo wa kijiografia",
                severity=ErrorSeverity.WARNING,
                field=field_name,
            ))

        return ValidationResult(is_valid=True, value=round(coverage, 1), warnings=warnings)

    # =====================================================================
    # CONFIDENCE VALIDATION
    # =====================================================================

    def validate_confidence(
        self,
        confidence: Any,
        field_name: str = "confidence",
    ) -> ValidationResult:
        """
        Validate a confidence score for an insight or recommendation.

        Args:
            confidence: Confidence score (0-1)
            field_name: Field name for errors
        """
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.CONFIDENCE_TOO_LOW,
                message=f"{field_name} must be a number",
                message_sw="Ujasiri si sahihi",
                field=field_name,
            )

        if math.isnan(conf) or math.isinf(conf):
            return ValidationResult.invalid(
                value=0.0,
                code=ErrorCode.CONFIDENCE_TOO_LOW,
                message=f"{field_name} is not a valid number",
                message_sw="Ujasiri si sahihi",
                field=field_name,
            )

        conf = max(0.0, min(1.0, conf))

        if conf < self.MIN_CONFIDENCE_SCORE:
            return ValidationResult.invalid(
                value=conf,
                code=ErrorCode.CONFIDENCE_TOO_LOW,
                message=f"Confidence {conf:.2f} below minimum ({self.MIN_CONFIDENCE_SCORE})",
                message_sw=f"Ujasiri ({conf:.2f}) ni mdogo sana (min {self.MIN_CONFIDENCE_SCORE})",
                severity=ErrorSeverity.ERROR,
                field=field_name,
            )

        return ValidationResult.valid(round(conf, 3))

    # =====================================================================
    # INSIGHT VALIDATION
    # =====================================================================

    def validate_insight(
        self,
        insight: Dict[str, Any],
        field_name: str = "insight",
    ) -> ValidationResult:
        """
        Validate a single insight within a report.

        Args:
            insight: Dict with keys: title, description, confidence, data_points
            field_name: Field name for errors
        """
        errors = []
        warnings = []

        # Required fields
        if not insight.get("title"):
            errors.append(ValidationError(
                code=ErrorCode.MISSING_FIELD,
                message="Insight title is required",
                message_sw="Kichwa cha ufahamu kinahitajika",
                field=f"{field_name}.title",
            ))

        if not insight.get("description"):
            errors.append(ValidationError(
                code=ErrorCode.MISSING_FIELD,
                message="Insight description is required",
                message_sw="Maelezo ya ufahamu yanahitajika",
                field=f"{field_name}.description",
            ))

        # Confidence
        if "confidence" in insight:
            conf_result = self.validate_confidence(
                insight["confidence"], f"{field_name}.confidence"
            )
            errors.extend(conf_result.errors)
            warnings.extend(conf_result.warnings)

        # Data points backing the insight
        data_points = insight.get("data_points", insight.get("sample_size", 0))
        if isinstance(data_points, (int, float)) and data_points < self.MIN_SAMPLE_SIZE:
            warnings.append(ValidationError(
                code=ErrorCode.INSUFFICIENT_DATA,
                message=f"Insight backed by only {data_points} data points (min {self.MIN_SAMPLE_SIZE})",
                message_sw=f"Ufahamu una datai chache tu ({data_points})",
                severity=ErrorSeverity.WARNING,
                field=f"{field_name}.data_points",
            ))

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, value=insight, errors=errors, warnings=warnings)

    # =====================================================================
    # FULL REPORT VALIDATION
    # =====================================================================

    def validate_report(
        self,
        report: Dict[str, Any],
    ) -> ValidationResult:
        """
        Validate a complete intelligence report before delivery.

        Args:
            report: Dict with keys: quality_score, data_date, coverage,
                    insights (list), sample_size, etc.
        """
        errors = []
        warnings = []
        validated = {}

        # Quality score
        if "quality_score" in report:
            qs_result = self.validate_quality_score(report["quality_score"])
            validated["quality_score"] = qs_result.value
            errors.extend(qs_result.errors)
            warnings.extend(qs_result.warnings)
        else:
            errors.append(ValidationError(
                code=ErrorCode.MISSING_FIELD,
                message="quality_score is required",
                message_sw="Alama ya ubora inahitajika",
                field="quality_score",
            ))

        # Data freshness
        if "data_date" in report:
            fresh_result = self.validate_data_freshness(report["data_date"])
            validated["data_date"] = fresh_result.value
            errors.extend(fresh_result.errors)
            warnings.extend(fresh_result.warnings)
        else:
            errors.append(ValidationError(
                code=ErrorCode.MISSING_FIELD,
                message="data_date is required to assess freshness",
                message_sw="Tarehe ya datai inahitajika",
                field="data_date",
            ))

        # Coverage
        if "coverage" in report:
            cov_result = self.validate_coverage(report["coverage"])
            validated["coverage"] = cov_result.value
            errors.extend(cov_result.errors)
            warnings.extend(cov_result.warnings)

        # Insights
        insights = report.get("insights", [])
        if len(insights) > self.MAX_INSIGHTS_PER_REPORT:
            errors.append(ValidationError(
                code=ErrorCode.INVALID_INPUT,
                message=f"Too many insights ({len(insights)} > {self.MAX_INSIGHTS_PER_REPORT})",
                message_sw="Ufahamu mwingi sana",
                field="insights",
            ))
        else:
            for i, insight in enumerate(insights):
                insight_result = self.validate_insight(insight, f"insights[{i}]")
                errors.extend(insight_result.errors)
                warnings.extend(insight_result.warnings)

        validated["insights"] = insights

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            value=validated if validated else report,
            errors=errors,
            warnings=warnings,
        )

    # =====================================================================
    # HELPERS
    # =====================================================================

    def _parse_date(self, value: Any) -> Optional[datetime]:
        """Parse various date formats into datetime. Delegates to shared utility."""
        return parse_date(value)
