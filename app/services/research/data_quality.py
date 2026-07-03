"""
Data Quality Framework — Statistical Process Control & Validation.

Implements:
- SPC control charts (X̄, R, p, c, EWMA, CUSUM) for incoming transaction data
  (STA 346: Statistical Quality Control)
- Outlier detection using non-parametric methods (STA 342: Non-parametric tests)
- Data validation rules based on economic theory (ECO 202/203: Economic Statistics)
- Acceptance sampling for data quality (STA 346)

References from Valentine's degree:
- STA 346: Shewhart control charts, CUSUM, EWMA, process capability
- STA 342: Non-parametric tests, IQR-based detection, Grubbs' test
- ECO 202: Data collection and cleaning standards
- ECO 203: Economic data validation
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class ControlChartType(str, Enum):
    """Types of control charts (STA 346)."""
    XBAR = "xbar"          # Mean chart
    R = "range"            # Range chart
    P = "proportion"       # Proportion defective
    C = "count"            # Count of defects
    EWMA = "ewma"         # Exponentially Weighted Moving Average
    CUSUM = "cusum"       # Cumulative Sum


class ValidationSeverity(str, Enum):
    """Severity of validation violations."""
    ERROR = "error"        # Must reject
    WARNING = "warning"    # Flag for review
    INFO = "info"          # Informational only


class OutlierMethod(str, Enum):
    """Outlier detection methods."""
    IQR = "iqr"                        # Interquartile Range (non-parametric)
    GRUBBS = "grubbs"                  # Grubbs' test for normal data
    MODIFIED_ZSCORE = "modified_zscore"  # Median Absolute Deviation
    ISOLATION_FOREST = "isolation_forest"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of a single validation check."""
    rule_name: str
    passed: bool
    severity: ValidationSeverity
    message: str
    field_name: Optional[str] = None
    value: Optional[Any] = None
    threshold: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule_name,
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "field": self.field_name,
            "value": self.value,
            "threshold": self.threshold,
        }


@dataclass
class ControlChartSignal:
    """Signal from a control chart indicating out-of-control condition."""
    chart_type: ControlChartType
    signal_type: str          # "point_beyond_limits", "run_above", "run_below", "trend"
    point_index: int
    value: float
    ucl: float
    lcl: float
    cl: float
    severity: str             # "warning" or "action"
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chart_type": self.chart_type.value,
            "signal_type": self.signal_type,
            "point_index": self.point_index,
            "value": round(self.value, 4),
            "ucl": round(self.ucl, 4),
            "lcl": round(self.lcl, 4),
            "cl": round(self.cl, 4),
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class OutlierResult:
    """Result of outlier detection."""
    index: int
    value: float
    method: OutlierMethod
    score: float              # How extreme (z-score, IQR distance, etc.)
    is_outlier: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "value": round(self.value, 4),
            "method": self.method.value,
            "score": round(self.score, 4),
            "is_outlier": self.is_outlier,
        }


@dataclass
class DataQualityReport:
    """Comprehensive data quality assessment."""
    timestamp: datetime
    total_records: int
    valid_records: int
    invalid_records: int
    quality_score: float              # 0-1
    validation_results: List[ValidationResult]
    outlier_results: List[OutlierResult]
    control_chart_signals: List[ControlChartSignal]
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "quality_score": round(self.quality_score, 4),
            "validation_summary": {
                "total_checks": len(self.validation_results),
                "passed": sum(1 for v in self.validation_results if v.passed),
                "failed": sum(1 for v in self.validation_results if not v.passed),
                "errors": sum(
                    1 for v in self.validation_results
                    if not v.passed and v.severity == ValidationSeverity.ERROR
                ),
            },
            "outlier_summary": {
                "total_checked": len(self.outlier_results),
                "outliers_detected": sum(1 for o in self.outlier_results if o.is_outlier),
            },
            "control_chart_signals": len(self.control_chart_signals),
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# SPC Control Charts (STA 346)
# ---------------------------------------------------------------------------

class SPCChart:
    """
    Statistical Process Control charts for monitoring data quality.

    Implements Shewhart X̄, R, p, c charts plus EWMA and CUSUM
    for detecting smaller shifts (STA 346: Statistical Quality Control).

    Control limits at ±3σ (Shewhart convention):
    - UCL = CL + 3σ
    - LCL = CL - 3σ
    - ARL₀ ≈ 370 (one false alarm per 370 points)
    """

    def __init__(
        self,
        chart_type: ControlChartType = ControlChartType.XBAR,
        window_size: int = 25,
        lambda_ewma: float = 0.2,
        cusum_k: float = 0.5,
        cusum_h: float = 5.0,
    ):
        self.chart_type = chart_type
        self.window_size = window_size
        self.lambda_ewma = lambda_ewma
        self.cusum_k = cusum_k
        self.cusum_h = cusum_h

        self._values: deque = deque(maxlen=window_size * 10)
        self._signals: List[ControlChartSignal] = []
        self._ewma_value: Optional[float] = None
        self._cusum_upper: float = 0.0
        self._cusum_lower: float = 0.0

    @property
    def signals(self) -> List[ControlChartSignal]:
        return list(self._signals)

    def update(self, value: float) -> Optional[ControlChartSignal]:
        """
        Add a new observation and check for out-of-control signals.

        Args:
            value: New data point

        Returns:
            ControlChartSignal if out-of-control, None otherwise
        """
        self._values.append(value)

        if len(self._values) < self.window_size:
            return None

        if self.chart_type == ControlChartType.XBAR:
            return self._check_xbar(value)
        elif self.chart_type == ControlChartType.P:
            return self._check_p(value)
        elif self.chart_type == ControlChartType.C:
            return self._check_c(value)
        elif self.chart_type == ControlChartType.EWMA:
            return self._check_ewma(value)
        elif self.chart_type == ControlChartType.CUSUM:
            return self._check_cusum(value)
        return None

    def compute_control_limits(
        self, values: Optional[List[float]] = None
    ) -> Dict[str, float]:
        """
        Compute control limits from data.

        Uses ±3σ convention from STA 346.
        """
        data = values or list(self._values)
        if not data:
            return {"cl": 0, "ucl": 0, "lcl": 0}

        arr = np.array(data)
        cl = float(np.mean(arr))
        std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0

        return {
            "cl": round(cl, 4),
            "ucl": round(cl + 3 * std, 4),
            "lcl": round(cl - 3 * std, 4),
            "std": round(std, 4),
            "n": len(data),
        }

    def _check_xbar(self, value: float) -> Optional[ControlChartSignal]:
        """Shewhart X̄ chart — detects large shifts (STA 346)."""
        limits = self.compute_control_limits()
        idx = len(self._values) - 1

        if value > limits["ucl"] or value < limits["lcl"]:
            signal = ControlChartSignal(
                chart_type=ControlChartType.XBAR,
                signal_type="point_beyond_limits",
                point_index=idx,
                value=value,
                ucl=limits["ucl"],
                lcl=limits["lcl"],
                cl=limits["cl"],
                severity="action",
                message=(
                    f"Point {value:.2f} beyond control limits "
                    f"[{limits['lcl']:.2f}, {limits['ucl']:.2f}]"
                ),
            )
            self._signals.append(signal)
            return signal

        # Run rules (Western Electric rules)
        signal = self._check_run_rules(value, limits, idx)
        if signal:
            self._signals.append(signal)
            return signal

        return None

    def _check_p(self, value: float) -> Optional[ControlChartSignal]:
        """p-chart for proportion defective (STA 346)."""
        recent = list(self._values)[-self.window_size:]
        p_bar = np.mean(recent)
        n = len(recent)
        if n < 2:
            return None

        std = math.sqrt(p_bar * (1 - p_bar) / max(n, 1))
        ucl = min(1.0, p_bar + 3 * std)
        lcl = max(0.0, p_bar - 3 * std)
        idx = len(self._values) - 1

        if value > ucl or value < lcl:
            signal = ControlChartSignal(
                chart_type=ControlChartType.P,
                signal_type="point_beyond_limits",
                point_index=idx,
                value=value,
                ucl=ucl,
                lcl=lcl,
                cl=p_bar,
                severity="action",
                message=f"Proportion {value:.4f} outside [{lcl:.4f}, {ucl:.4f}]",
            )
            self._signals.append(signal)
            return signal
        return None

    def _check_c(self, value: float) -> Optional[ControlChartSignal]:
        """c-chart for count of defects (STA 346)."""
        recent = list(self._values)[-self.window_size:]
        c_bar = np.mean(recent)
        std = math.sqrt(max(c_bar, 0))
        ucl = c_bar + 3 * std
        lcl = max(0, c_bar - 3 * std)
        idx = len(self._values) - 1

        if value > ucl or value < lcl:
            signal = ControlChartSignal(
                chart_type=ControlChartType.C,
                signal_type="point_beyond_limits",
                point_index=idx,
                value=value,
                ucl=ucl,
                lcl=lcl,
                cl=c_bar,
                severity="action",
                message=f"Count {value:.0f} outside [{lcl:.2f}, {ucl:.2f}]",
            )
            self._signals.append(signal)
            return signal
        return None

    def _check_ewma(self, value: float) -> Optional[ControlChartSignal]:
        """
        EWMA chart — detects small sustained shifts (STA 346).

        Z_t = λ * X_t + (1-λ) * Z_{t-1}
        """
        lam = self.lambda_ewma
        if self._ewma_value is None:
            self._ewma_value = value
            return None

        self._ewma_value = lam * value + (1 - lam) * self._ewma_value

        # Control limits for EWMA
        recent = list(self._values)[-self.window_size:]
        mu = np.mean(recent)
        sigma = np.std(recent, ddof=1) if len(recent) > 1 else 1.0
        n = len(self._values)

        ewma_std = sigma * math.sqrt(
            lam / (2 - lam) * (1 - (1 - lam) ** (2 * n))
        )
        ucl = mu + 3 * ewma_std
        lcl = mu - 3 * ewma_std
        idx = len(self._values) - 1

        if self._ewma_value > ucl or self._ewma_value < lcl:
            signal = ControlChartSignal(
                chart_type=ControlChartType.EWMA,
                signal_type="ewma_beyond_limits",
                point_index=idx,
                value=self._ewma_value,
                ucl=ucl,
                lcl=lcl,
                cl=mu,
                severity="action",
                message=(
                    f"EWMA {self._ewma_value:.4f} outside "
                    f"[{lcl:.4f}, {ucl:.4f}] — small shift detected"
                ),
            )
            self._signals.append(signal)
            return signal
        return None

    def _check_cusum(self, value: float) -> Optional[ControlChartSignal]:
        """
        CUSUM chart — accumulates deviations from target (STA 346).

        S_upper(t) = max(0, S_upper(t-1) + (X_t - μ₀)/σ₀ - k)
        S_lower(t) = min(0, S_lower(t-1) + (X_t - μ₀)/σ₀ + k)
        """
        recent = list(self._values)[-self.window_size:]
        mu = np.mean(recent)
        sigma = np.std(recent, ddof=1) if len(recent) > 1 else 1.0

        z = (value - mu) / max(sigma, 1e-10)
        self._cusum_upper = max(0, self._cusum_upper + z - self.cusum_k)
        self._cusum_lower = min(0, self._cusum_lower + z + self.cusum_k)
        idx = len(self._values) - 1

        if self._cusum_upper > self.cusum_h:
            signal = ControlChartSignal(
                chart_type=ControlChartType.CUSUM,
                signal_type="cusum_upper_breach",
                point_index=idx,
                value=self._cusum_upper,
                ucl=self.cusum_h,
                lcl=-self.cusum_h,
                cl=0,
                severity="action",
                message=(
                    f"CUSUM upper {self._cusum_upper:.4f} > h={self.cusum_h} "
                    f"— sustained upward shift detected"
                ),
            )
            self._signals.append(signal)
            self._cusum_upper = 0  # Reset after signal
            return signal

        if abs(self._cusum_lower) > self.cusum_h:
            signal = ControlChartSignal(
                chart_type=ControlChartType.CUSUM,
                signal_type="cusum_lower_breach",
                point_index=idx,
                value=self._cusum_lower,
                ucl=self.cusum_h,
                lcl=-self.cusum_h,
                cl=0,
                severity="action",
                message=(
                    f"CUSUM lower {self._cusum_lower:.4f} < -h={-self.cusum_h} "
                    f"— sustained downward shift detected"
                ),
            )
            self._signals.append(signal)
            self._cusum_lower = 0
            return signal
        return None

    def _check_run_rules(
        self, value: float, limits: Dict[str, float], idx: int
    ) -> Optional[ControlChartSignal]:
        """
        Western Electric run rules for detecting non-random patterns.

        Rules:
        1. 2 of 3 consecutive points beyond 2σ
        2. 4 of 5 consecutive points beyond 1σ
        3. 8 consecutive points on same side of center
        """
        recent = list(self._values)
        cl = limits["cl"]
        std = limits.get("std", 0)
        if std == 0:
            return None

        # Rule 3: 8 consecutive on same side
        if len(recent) >= 8:
            last_8 = recent[-8:]
            all_above = all(v > cl for v in last_8)
            all_below = all(v < cl for v in last_8)
            if all_above or all_below:
                side = "above" if all_above else "below"
                signal = ControlChartSignal(
                    chart_type=self.chart_type,
                    signal_type="run_same_side",
                    point_index=idx,
                    value=value,
                    ucl=limits["ucl"],
                    lcl=limits["lcl"],
                    cl=cl,
                    severity="warning",
                    message=f"8 consecutive points {side} center line",
                )
                return signal

        return None

    def get_status(self) -> Dict[str, Any]:
        """Get current chart status."""
        limits = self.compute_control_limits()
        return {
            "chart_type": self.chart_type.value,
            "n_observations": len(self._values),
            "control_limits": limits,
            "total_signals": len(self._signals),
            "recent_signals": [s.to_dict() for s in self._signals[-5:]],
        }


# ---------------------------------------------------------------------------
# Outlier Detection (STA 342: Non-parametric methods)
# ---------------------------------------------------------------------------

class OutlierDetector:
    """
    Outlier detection using non-parametric methods.

    From STA 342 (Test of Hypothesis — Non-Parametric Tests):
    - IQR method: Robust, no distributional assumptions
    - Modified Z-score: Uses median absolute deviation (MAD)
    - Grubbs' test: For normally distributed data

    Non-parametric methods are preferred because:
    - No distributional assumptions (STA 342 §7.6)
    - Robust to the very outliers they detect
    - Asymptotic relative efficiency ≈ 0.955 vs parametric (STA 342)
    """

    @staticmethod
    def detect_iqr(
        values: List[float],
        multiplier: float = 1.5,
    ) -> List[OutlierResult]:
        """
        IQR-based outlier detection (non-parametric, STA 342).

        Outlier if: value < Q1 - multiplier*IQR or value > Q3 + multiplier*IQR
        Extreme outlier if multiplier = 3.0
        """
        if len(values) < 4:
            return [
                OutlierResult(
                    index=i, value=v, method=OutlierMethod.IQR,
                    score=0, is_outlier=False,
                )
                for i, v in enumerate(values)
            ]

        arr = np.array(values)
        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr

        results = []
        for i, v in enumerate(values):
            if iqr > 0:
                score = max(
                    (lower - v) / iqr if v < lower else 0,
                    (v - upper) / iqr if v > upper else 0,
                )
            else:
                score = 0
            results.append(OutlierResult(
                index=i,
                value=v,
                method=OutlierMethod.IQR,
                score=score,
                is_outlier=v < lower or v > upper,
            ))
        return results

    @staticmethod
    def detect_modified_zscore(
        values: List[float],
        threshold: float = 3.5,
    ) -> List[OutlierResult]:
        """
        Modified Z-score using Median Absolute Deviation (MAD).

        More robust than standard z-score because median is not
        affected by outliers. From STA 342 non-parametric methods.

        Modified Z = 0.6745 * (x - median) / MAD
        """
        if len(values) < 3:
            return [
                OutlierResult(
                    index=i, value=v, method=OutlierMethod.MODIFIED_ZSCORE,
                    score=0, is_outlier=False,
                )
                for i, v in enumerate(values)
            ]

        arr = np.array(values)
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median)))

        if mad == 0:
            # Fallback to standard deviation
            mad = float(np.std(arr)) * 0.6745

        if mad == 0:
            return [
                OutlierResult(
                    index=i, value=v, method=OutlierMethod.MODIFIED_ZSCORE,
                    score=0, is_outlier=False,
                )
                for i, v in enumerate(values)
            ]

        results = []
        for i, v in enumerate(values):
            modified_z = 0.6745 * (v - median) / mad
            results.append(OutlierResult(
                index=i,
                value=v,
                method=OutlierMethod.MODIFIED_ZSCORE,
                score=abs(modified_z),
                is_outlier=abs(modified_z) > threshold,
            ))
        return results

    @staticmethod
    def detect_grubbs(
        values: List[float],
        alpha: float = 0.05,
    ) -> List[OutlierResult]:
        """
        Grubbs' test for outliers (parametric, assumes normality).

        H₀: There are no outliers in the data
        H₁: There is exactly one outlier

        Test statistic: G = max|Xᵢ - X̄| / S
        Critical value from t-distribution.
        """
        from scipy import stats as sp_stats

        if len(values) < 3:
            return [
                OutlierResult(
                    index=i, value=v, method=OutlierMethod.GRUBBS,
                    score=0, is_outlier=False,
                )
                for i, v in enumerate(values)
            ]

        arr = np.array(values)
        n = len(arr)
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))

        if std == 0:
            return [
                OutlierResult(
                    index=i, value=v, method=OutlierMethod.GRUBBS,
                    score=0, is_outlier=False,
                )
                for i, v in enumerate(values)
            ]

        # Critical value
        t_crit = sp_stats.t.ppf(1 - alpha / (2 * n), n - 2)
        g_crit = ((n - 1) / math.sqrt(n)) * math.sqrt(
            t_crit ** 2 / (n - 2 + t_crit ** 2)
        )

        results = []
        for i, v in enumerate(values):
            g_stat = abs(v - mean) / std
            results.append(OutlierResult(
                index=i,
                value=v,
                method=OutlierMethod.GRUBBS,
                score=g_stat,
                is_outlier=g_stat > g_crit,
            ))
        return results


# ---------------------------------------------------------------------------
# Data Validation (ECO 202/203: Economic Statistics)
# ---------------------------------------------------------------------------

class DataValidator:
    """
    Data validation rules based on economic theory and statistical standards.

    From ECO 202 (Economic Statistics):
    - Prices must be positive (economic theory: prices reflect scarcity)
    - Quantities must be non-negative
    - Revenue = price × quantity (accounting identity)

    From ECO 203 (Advanced Economic Statistics):
    - Time series consistency checks
    - Cross-sectional consistency
    - Outlier flagging for data cleaning

    From STA 245 (Social & Economic Statistics for National Planning):
    - Official statistics standards
    - Data quality dimensions (accuracy, timeliness, comparability)
    """

    # Economic theory validation rules
    RULES = {
        "positive_price": {
            "description": "Unit prices must be positive (ECO 202: price theory)",
            "severity": ValidationSeverity.ERROR,
        },
        "non_negative_quantity": {
            "description": "Quantities must be non-negative",
            "severity": ValidationSeverity.ERROR,
        },
        "non_negative_amount": {
            "description": "Transaction amounts must be non-negative",
            "severity": ValidationSeverity.ERROR,
        },
        "revenue_consistency": {
            "description": "amount ≈ unit_price × quantity (accounting identity)",
            "severity": ValidationSeverity.WARNING,
        },
        "reasonable_price_range": {
            "description": "Prices within expected range for product category",
            "severity": ValidationSeverity.WARNING,
        },
        "valid_timestamp": {
            "description": "Timestamps must be in the past and not too old",
            "severity": ValidationSeverity.ERROR,
        },
        "valid_confidence_score": {
            "description": "Confidence scores must be between 0 and 1",
            "severity": ValidationSeverity.ERROR,
        },
        "valid_geohash": {
            "description": "Location geohash must be valid format",
            "severity": ValidationSeverity.WARNING,
        },
        "valid_payment_method": {
            "description": "Payment method must be from allowed set",
            "severity": ValidationSeverity.ERROR,
        },
        "valid_transaction_type": {
            "description": "Transaction type must be SALE, PURCHASE, or EXPENSE",
            "severity": ValidationSeverity.ERROR,
        },
    }

    # Expected price ranges per product category (KES)
    # Based on Kenya market data (ECO 202/203: economic statistics)
    PRICE_RANGES = {
        "food": (1, 50000),       # Food items: 1 KES to 50,000 KES
        "household": (5, 20000),  # Household items
        "health": (10, 100000),   # Health products
        "transport": (10, 50000), # Transport services
        "clothing": (50, 100000), # Clothing items
        "electronics": (100, 5000000),  # Electronics
        "beauty": (10, 50000),    # Beauty products
        "agriculture": (1, 1000000),    # Agricultural products
        "services": (10, 500000),       # Services
        "rent": (500, 500000),    # Rent payments
        "other": (1, 1000000),    # Catch-all
    }

    VALID_PAYMENT_METHODS = {"mpesa", "cash", "credit", "bank", "other"}
    VALID_TRANSACTION_TYPES = {"SALE", "PURCHASE", "EXPENSE"}

    @classmethod
    def validate_transaction(
        cls, txn: Dict[str, Any]
    ) -> List[ValidationResult]:
        """
        Validate a single transaction record.

        Applies economic theory rules (ECO 202/203) and
        data quality standards (STA 245).
        """
        results = []

        # 1. Positive price check (ECO 202: price theory)
        unit_price = txn.get("unit_price")
        if unit_price is not None and unit_price < 0:
            results.append(ValidationResult(
                rule_name="positive_price",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Negative unit price: {unit_price} KES",
                field_name="unit_price",
                value=unit_price,
            ))
        elif unit_price is not None:
            results.append(ValidationResult(
                rule_name="positive_price",
                passed=True,
                severity=ValidationSeverity.ERROR,
                message="OK",
                field_name="unit_price",
                value=unit_price,
            ))

        # 2. Non-negative quantity
        quantity = txn.get("quantity")
        if quantity is not None and quantity < 0:
            results.append(ValidationResult(
                rule_name="non_negative_quantity",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Negative quantity: {quantity}",
                field_name="quantity",
                value=quantity,
            ))

        # 3. Non-negative amount
        amount = txn.get("amount")
        if amount is not None and amount < 0:
            results.append(ValidationResult(
                rule_name="non_negative_amount",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Negative amount: {amount}",
                field_name="amount",
                value=amount,
            ))

        # 4. Revenue consistency (accounting identity)
        if (
            unit_price is not None
            and quantity is not None
            and amount is not None
            and unit_price > 0
            and quantity > 0
        ):
            expected = unit_price * quantity
            tolerance = max(expected * 0.01, 1.0)  # 1% tolerance or 1 KES
            if abs(amount - expected) > tolerance:
                results.append(ValidationResult(
                    rule_name="revenue_consistency",
                    passed=False,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Amount {amount} ≠ price×qty "
                        f"{expected:.2f} (diff: {abs(amount - expected):.2f})"
                    ),
                    field_name="amount",
                    value=amount,
                    threshold=tolerance,
                ))

        # 5. Price range check (ECO 203: economic data validation)
        category = txn.get("item_category", "other")
        if unit_price is not None and unit_price > 0:
            price_range = cls.PRICE_RANGES.get(category, (1, 1000000))
            if unit_price < price_range[0] or unit_price > price_range[1]:
                results.append(ValidationResult(
                    rule_name="reasonable_price_range",
                    passed=False,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Price {unit_price} KES outside expected range "
                        f"{price_range} for {category}"
                    ),
                    field_name="unit_price",
                    value=unit_price,
                ))

        # 6. Timestamp validation
        timestamp = txn.get("timestamp")
        if timestamp is not None:
            now = datetime.now(timezone.utc)
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    results.append(ValidationResult(
                        rule_name="valid_timestamp",
                        passed=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Invalid timestamp format: {timestamp}",
                        field_name="timestamp",
                    ))
                    timestamp = None

            if timestamp is not None:
                if timestamp > now:
                    results.append(ValidationResult(
                        rule_name="valid_timestamp",
                        passed=False,
                        severity=ValidationSeverity.ERROR,
                        message="Timestamp is in the future",
                        field_name="timestamp",
                    ))

        # 7. Confidence score range
        confidence = txn.get("confidence_score")
        if confidence is not None and (confidence < 0 or confidence > 1):
            results.append(ValidationResult(
                rule_name="valid_confidence_score",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Confidence score {confidence} outside [0, 1]",
                field_name="confidence_score",
                value=confidence,
            ))

        # 8. Payment method
        payment = txn.get("payment_method")
        if payment is not None and payment not in cls.VALID_PAYMENT_METHODS:
            results.append(ValidationResult(
                rule_name="valid_payment_method",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Invalid payment method: {payment}",
                field_name="payment_method",
                value=payment,
            ))

        # 9. Transaction type
        txn_type = txn.get("transaction_type")
        if txn_type is not None and txn_type not in cls.VALID_TRANSACTION_TYPES:
            results.append(ValidationResult(
                rule_name="valid_transaction_type",
                passed=False,
                severity=ValidationSeverity.ERROR,
                message=f"Invalid transaction type: {txn_type}",
                field_name="transaction_type",
                value=txn_type,
            ))

        return results

    @classmethod
    def validate_batch(
        cls, transactions: List[Dict[str, Any]]
    ) -> Tuple[List[ValidationResult], float]:
        """
        Validate a batch of transactions.

        Returns:
            Tuple of (all validation results, pass rate)
        """
        all_results = []
        for txn in transactions:
            all_results.extend(cls.validate_transaction(txn))

        total = len(all_results)
        passed = sum(1 for r in all_results if r.passed)
        pass_rate = passed / total if total > 0 else 1.0

        return all_results, pass_rate


# ---------------------------------------------------------------------------
# EWMA Analyzer with Optimal λ Selection (STA 346)
# ---------------------------------------------------------------------------


class EWMAAnalyzer:
    """
    EWMA Control Chart with optimal smoothing parameter selection.

    From STA 346 (Statistical Quality Control):

    EWMA statistic:
        Z_t = λ X_t + (1 - λ) Z_{t-1}

    Control limits (time-varying, exact):
        UCL_t = μ₀ + L √(λ / (2 - λ) × (1 - (1-λ)^(2t))) σ
        LCL_t = μ₀ - L √(λ / (2 - λ) × (1 - (1-λ)^(2t))) σ

    Steady-state limits (t → ∞):
        UCL = μ₀ + L √(λ / (2 - λ)) σ
        LCL = μ₀ - L √(λ / (2 - λ)) σ

    Optimal λ selection:
        λ is chosen to minimize ARL₁ (average run length under shift δ)
        for a given ARL₀ (in-control ARL). Approximate optimal values:
        - Small shifts (δ < 0.5σ): λ ≈ 0.05–0.10
        - Medium shifts (0.5σ < δ < 1.5σ): λ ≈ 0.10–0.25
        - Large shifts (δ > 1.5σ): λ ≈ 0.25–0.40 (use Shewhart instead)

    Use case: Detect gradual quality drift in data feeds (e.g., slow
    price drift, incremental data corruption, systematic measurement bias).
    """

    def __init__(
        self,
        target_mean: Optional[float] = None,
        target_std: Optional[float] = None,
        lambda_: Optional[float] = None,
        L: float = 3.0,
    ):
        """
        Args:
            target_mean: In-control mean μ₀ (estimated from data if None)
            target_std: In-control std σ (estimated from data if None)
            lambda_: Smoothing parameter λ ∈ (0, 1]. If None, auto-select.
            L: Control limit width in σ units (default: 3.0)
        """
        self.target_mean = target_mean
        self.target_std = target_std
        self.lambda_ = lambda_
        self.L = L

        self._ewma_value: Optional[float] = None
        self._values: List[float] = []
        self._ewma_history: List[float] = []
        self._signals: List[ControlChartSignal] = []

    @property
    def signals(self) -> List[ControlChartSignal]:
        return list(self._signals)

    @staticmethod
    def optimal_lambda(
        delta: float,
        L: float = 3.0,
        ARL0_target: float = 370.0,
    ) -> Dict[str, Any]:
        """
        Select optimal λ for detecting a shift of size δ.

        Uses numerical search over λ ∈ [0.01, 0.50] to find λ that
        minimizes ARL₁ (average run length under shift δ) while
        maintaining desired ARL₀ (in-control ARL).

        ARL₁ approximation based on signal probability:
            P(signal | shift δ) ≈ 1 - Φ(L√(λ/(2-λ)) - δ/√(λ/(2-λ)))
            ARL₁ = 1 / P(signal)

        Args:
            delta: Shift size in σ units (e.g., 0.5 means 0.5σ shift)
            L: Control limit width
            ARL0_target: Desired in-control ARL (default: 370 ≈ 3σ limits)

        Returns:
            Dict with optimal λ, expected ARL₁, and analysis
        """
        if delta <= 0:
            return {
                "optimal_lambda": 0.1,
                "ARL1": ARL0_target,
                "message": "No shift to detect; default λ=0.1",
            }

        best_lambda = 0.1
        best_ARL1 = ARL0_target

        candidates = []
        for lam_100 in range(1, 51):  # λ from 0.01 to 0.50
            lam = lam_100 / 100.0
            ewma_factor = math.sqrt(lam / (2 - lam))
            threshold = L * ewma_factor
            noncentrality = delta / ewma_factor if ewma_factor > 0 else 0
            p_signal = 1 - sp_stats.norm.cdf(threshold - noncentrality)
            p_signal = max(p_signal, 1e-10)
            ARL1 = 1.0 / p_signal

            candidates.append({
                "lambda": round(lam, 2),
                "ARL1": round(ARL1, 1),
                "ewma_factor": round(ewma_factor, 4),
                "p_signal": round(p_signal, 6),
            })

            if ARL1 < best_ARL1:
                best_ARL1 = ARL1
                best_lambda = lam

        candidates.sort(key=lambda x: x["ARL1"])

        return {
            "optimal_lambda": best_lambda,
            "ARL1": round(best_ARL1, 1),
            "ARL0_target": ARL0_target,
            "delta_sigma": delta,
            "L": L,
            "message": (
                f"λ={best_lambda} minimizes ARL₁={best_ARL1:.0f} "
                f"for detecting {delta}σ shift"
            ),
            "top_5_candidates": candidates[:5],
        }

    @staticmethod
    def select_lambda_for_shift_size(
        small_shift: bool = True,
        medium_shift: bool = False,
    ) -> Dict[str, Any]:
        """
        Quick λ selection based on expected shift magnitude.

        Rules of thumb from STA 346 (Montgomery):
        - Small shifts (0.25σ–0.50σ): λ = 0.05–0.10
        - Medium shifts (0.50σ–1.50σ): λ = 0.10–0.25
        - Large shifts (>1.50σ): λ = 0.25–0.40 or use Shewhart
        """
        if small_shift:
            lam = 0.05
            rationale = "Small shift detection (λ=0.05): high sensitivity to gradual drift"
            typical_delta = "0.25σ–0.50σ"
        elif medium_shift:
            lam = 0.20
            rationale = "Medium shift detection (λ=0.20): balanced sensitivity"
            typical_delta = "0.50σ–1.50σ"
        else:
            lam = 0.40
            rationale = "Large shift detection (λ=0.40): faster response"
            typical_delta = ">1.50σ (consider Shewhart instead)"

        return {
            "recommended_lambda": lam,
            "rationale": rationale,
            "typical_detectable_shift": typical_delta,
            "L_recommended": 3.0,
            "note": "For mixed shifts, use λ=0.10–0.15 as compromise",
        }

    def update(self, value: float) -> Optional[ControlChartSignal]:
        """
        Process a new observation through the EWMA chart.

        Updates: Z_t = λ X_t + (1-λ) Z_{t-1}
        Control limits: μ₀ ± L √(λ/(2-λ) × (1-(1-λ)^(2t))) σ
        """
        self._values.append(value)
        n = len(self._values)

        # Estimate target parameters from first batch if not set
        calibration_size = 25
        if self.target_mean is None and n >= calibration_size:
            self.target_mean = float(np.mean(self._values[:calibration_size]))
        if self.target_std is None and n >= calibration_size:
            self.target_std = float(np.std(self._values[:calibration_size], ddof=1))

        if self.target_mean is None or self.target_std is None:
            self._ewma_value = value
            self._ewma_history.append(value)
            return None

        if self.lambda_ is None:
            self.lambda_ = 0.10

        lam = self.lambda_
        mu0 = self.target_mean
        sigma = self.target_std

        # Update EWMA: Z_t = λ X_t + (1-λ) Z_{t-1}
        if self._ewma_value is None:
            self._ewma_value = value
        else:
            self._ewma_value = lam * value + (1 - lam) * self._ewma_value

        self._ewma_history.append(self._ewma_value)

        # Time-varying control limits (exact)
        ewma_var_factor = (lam / (2 - lam)) * (1 - (1 - lam) ** (2 * n))
        ewma_std = sigma * math.sqrt(max(ewma_var_factor, 0))
        ucl = mu0 + self.L * ewma_std
        lcl = mu0 - self.L * ewma_std

        if self._ewma_value > ucl or self._ewma_value < lcl:
            direction = "above" if self._ewma_value > ucl else "below"
            signal = ControlChartSignal(
                chart_type=ControlChartType.EWMA,
                signal_type=f"ewma_beyond_limits_{direction}",
                point_index=n - 1,
                value=self._ewma_value,
                ucl=ucl,
                lcl=lcl,
                cl=mu0,
                severity="action",
                message=(
                    f"EWMA Z_{n}={self._ewma_value:.4f} {direction} "
                    f"control limits [{lcl:.4f}, {ucl:.4f}] "
                    f"(λ={lam}, L={self.L})"
                ),
            )
            self._signals.append(signal)
            return signal

        return None

    def get_status(self) -> Dict[str, Any]:
        """Get current EWMA chart status."""
        n = len(self._values)
        mu = self.target_mean
        sigma = self.target_std
        lam = self.lambda_

        limits = None
        if mu is not None and sigma is not None and lam is not None:
            ewma_var_factor = (lam / (2 - lam)) * (1 - (1 - lam) ** (2 * max(n, 1)))
            ewma_std = sigma * math.sqrt(max(ewma_var_factor, 0))
            limits = {
                "ucl": round(mu + self.L * ewma_std, 4),
                "lcl": round(mu - self.L * ewma_std, 4),
                "cl": round(mu, 4),
            }

        return {
            "n_observations": n,
            "lambda": lam,
            "L": self.L,
            "target_mean": round(mu, 4) if mu else None,
            "target_std": round(sigma, 4) if sigma else None,
            "current_ewma": round(self._ewma_value, 4) if self._ewma_value else None,
            "control_limits": limits,
            "total_signals": len(self._signals),
            "recent_signals": [s.to_dict() for s in self._signals[-5:]],
        }


# ---------------------------------------------------------------------------
# EWMA Control Chart — Batch Compute (STA 346)
# ---------------------------------------------------------------------------

class EWMAChart:
    """
    Exponentially Weighted Moving Average control chart (batch mode).

    Z_t = λ × X_t + (1 - λ) × Z_{t-1}
    Control limits (exact, time-varying):
        UCL_t = μ₀ + L × √(λ / (2 - λ) × (1 - (1 - λ)^(2t))) × σ
        LCL_t = μ₀ - L × √(λ / (2 - λ) × (1 - (1 - λ)^(2t))) × σ
    Steady-state limits (t → ∞):
        UCL = μ₀ + L × √(λ / (2 - λ)) × σ
        LCL = μ₀ - L × √(λ / (2 - λ)) × σ

    Detects small sustained shifts that Shewhart charts miss.
    Optimal for shifts of 0.25σ–1.50σ (STA 346: Montgomery).

    References:
    - Lucas, J.M. & Saccucci, M.S. (1990). Exponentially weighted
      moving average control schemes: Properties and enhancements.
      JQT, 22(1), 1-12.
    - Montgomery, D.C. (2020). Statistical Quality Control. 8th ed.
    """

    def __init__(self):
        pass

    def compute(self, data: list, lambda_: float = 0.2, L: float = 3.0) -> dict:
        """
        Compute EWMA statistics and control limits for a batch of data.

        Args:
            data: List of numeric observations
            lambda_: Smoothing parameter λ ∈ (0, 1].
                     Small λ (0.05–0.10): sensitive to small shifts.
                     Large λ (0.25–0.40): faster response to large shifts.
            L: Control limit width in σ units (default 3.0 ≈ ARL₀ ≈ 370)

        Returns:
            Dict with EWMA values, control limits, signals, and diagnostics.
        """
        if not data:
            return {
                "error": "Empty data",
                "ewma_values": [],
                "control_limits": {"ucl": [], "lcl": [], "cl": None},
                "signals": [],
            }

        arr = np.array(data, dtype=float)
        n = len(arr)

        # In-control parameters (estimated from data)
        mu0 = float(np.mean(arr))
        sigma = float(np.std(arr, ddof=1)) if n > 1 else 0.0

        if sigma < 1e-15:
            return {
                "n": n,
                "lambda": lambda_,
                "L": L,
                "mu0": round(mu0, 6),
                "sigma": 0.0,
                "ewma_values": [round(mu0, 6)] * n,
                "control_limits": {
                    "ucl": [round(mu0, 6)] * n,
                    "lcl": [round(mu0, 6)] * n,
                    "cl": round(mu0, 6),
                },
                "signals": [],
                "current_ewma": round(mu0, 6),
                "steady_state_ucl": round(mu0, 6),
                "steady_state_lcl": round(mu0, 6),
            }

        # Compute EWMA values: Z_t = λ X_t + (1-λ) Z_{t-1}
        ewma_values = np.zeros(n)
        ewma_values[0] = arr[0]
        for t in range(1, n):
            ewma_values[t] = lambda_ * arr[t] + (1 - lambda_) * ewma_values[t - 1]

        # Time-varying control limits (exact formula)
        ucl = np.zeros(n)
        lcl = np.zeros(n)
        for t in range(1, n + 1):
            ewma_var_factor = (lambda_ / (2 - lambda_)) * (1 - (1 - lambda_) ** (2 * t))
            ewma_std = sigma * math.sqrt(max(ewma_var_factor, 0))
            ucl[t - 1] = mu0 + L * ewma_std
            lcl[t - 1] = mu0 - L * ewma_std

        # Steady-state limits
        ss_factor = math.sqrt(lambda_ / (2 - lambda_))
        steady_ucl = mu0 + L * sigma * ss_factor
        steady_lcl = mu0 - L * sigma * ss_factor

        # Detect signals (EWMA beyond control limits)
        signals = []
        for t in range(n):
            if ewma_values[t] > ucl[t]:
                signals.append({
                    "index": t,
                    "ewma_value": round(float(ewma_values[t]), 6),
                    "ucl": round(float(ucl[t]), 6),
                    "lcl": round(float(lcl[t]), 6),
                    "direction": "above",
                    "message": (
                        f"EWMA Z_{t+1}={ewma_values[t]:.4f} above "
                        f"UCL={ucl[t]:.4f} — upward shift detected"
                    ),
                })
            elif ewma_values[t] < lcl[t]:
                signals.append({
                    "index": t,
                    "ewma_value": round(float(ewma_values[t]), 6),
                    "ucl": round(float(ucl[t]), 6),
                    "lcl": round(float(lcl[t]), 6),
                    "direction": "below",
                    "message": (
                        f"EWMA Z_{t+1}={ewma_values[t]:.4f} below "
                        f"LCL={lcl[t]:.4f} — downward shift detected"
                    ),
                })

        return {
            "n": n,
            "lambda": lambda_,
            "L": L,
            "mu0": round(mu0, 6),
            "sigma": round(sigma, 6),
            "ewma_values": [round(float(v), 6) for v in ewma_values],
            "control_limits": {
                "ucl": [round(float(v), 6) for v in ucl],
                "lcl": [round(float(v), 6) for v in lcl],
                "cl": round(mu0, 6),
            },
            "steady_state_ucl": round(steady_ucl, 6),
            "steady_state_lcl": round(steady_lcl, 6),
            "signals": signals,
            "n_signals": len(signals),
            "current_ewma": round(float(ewma_values[-1]), 6),
            "process_in_control": len(signals) == 0,
        }

class DataQualityFramework:
    """
    Comprehensive data quality framework for Angavu Intelligence.

    Integrates:
    - SPC control charts (STA 346) for monitoring data streams
    - Outlier detection (STA 342) for identifying anomalies
    - Validation rules (ECO 202/203) for enforcing data integrity
    - Acceptance sampling (STA 346) for batch quality assessment

    Usage:
        framework = DataQualityFramework()

        # Validate incoming transactions
        report = framework.assess_transactions(transactions)

        # Monitor data stream quality
        for txn in transaction_stream:
            framework.update_monitoring(txn)
    """

    def __init__(self):
        # SPC charts for different metrics
        self.amount_chart = SPCChart(
            chart_type=ControlChartType.XBAR, window_size=30
        )
        self.volume_chart = SPCChart(
            chart_type=ControlChartType.C, window_size=30
        )
        self.error_rate_chart = SPCChart(
            chart_type=ControlChartType.P, window_size=30
        )
        self.price_ewma_chart = SPCChart(
            chart_type=ControlChartType.EWMA, window_size=30
        )

        self.outlier_detector = OutlierDetector()
        self._transaction_count = 0
        self._error_count = 0

    def assess_transactions(
        self,
        transactions: List[Dict[str, Any]],
    ) -> DataQualityReport:
        """
        Comprehensive quality assessment of a transaction batch.

        Combines validation, outlier detection, and SPC analysis.
        """
        # Validation (ECO 202/203)
        validation_results, pass_rate = DataValidator.validate_batch(transactions)

        # Outlier detection on amounts (STA 342: non-parametric)
        amounts = [
            t.get("amount", 0) for t in transactions
            if t.get("amount") is not None
        ]
        outlier_results = []
        if amounts:
            outlier_results = OutlierDetector.detect_iqr(amounts)

        # SPC analysis
        signals = []
        for t in transactions:
            amount = t.get("amount", 0)
            if amount is not None:
                signal = self.amount_chart.update(amount)
                if signal:
                    signals.append(signal)

        # Compute quality score
        error_violations = sum(
            1 for v in validation_results
            if not v.passed and v.severity == ValidationSeverity.ERROR
        )
        warning_violations = sum(
            1 for v in validation_results
            if not v.passed and v.severity == ValidationSeverity.WARNING
        )
        outlier_count = sum(1 for o in outlier_results if o.is_outlier)

        total_checks = len(validation_results) or 1
        quality_score = max(0, 1.0 - (
            error_violations * 0.1
            + warning_violations * 0.02
            + outlier_count * 0.05
        ) / total_checks)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            validation_results, outlier_results, signals
        )

        invalid_count = sum(
            1 for v in validation_results
            if not v.passed and v.severity == ValidationSeverity.ERROR
        )

        return DataQualityReport(
            timestamp=datetime.now(timezone.utc),
            total_records=len(transactions),
            valid_records=len(transactions) - min(invalid_count, len(transactions)),
            invalid_records=min(invalid_count, len(transactions)),
            quality_score=quality_score,
            validation_results=validation_results,
            outlier_results=outlier_results,
            control_chart_signals=signals,
            recommendations=recommendations,
        )

    def update_monitoring(
        self, transaction: Dict[str, Any]
    ) -> List[ControlChartSignal]:
        """
        Update SPC monitoring with a new transaction.

        Returns any control chart signals generated.
        """
        self._transaction_count += 1
        signals = []

        amount = transaction.get("amount", 0)
        if amount is not None:
            signal = self.amount_chart.update(amount)
            if signal:
                signals.append(signal)

        # Track error rate
        results = DataValidator.validate_transaction(transaction)
        has_error = any(
            not r.passed and r.severity == ValidationSeverity.ERROR
            for r in results
        )
        if has_error:
            self._error_count += 1

        error_rate = self._error_count / max(self._transaction_count, 1)
        self.error_rate_chart.update(error_rate)

        # Price monitoring with EWMA
        unit_price = transaction.get("unit_price")
        if unit_price is not None and unit_price > 0:
            price_signal = self.price_ewma_chart.update(unit_price)
            if price_signal:
                signals.append(price_signal)

        return signals

    def _generate_recommendations(
        self,
        validation_results: List[ValidationResult],
        outlier_results: List[OutlierResult],
        signals: List[ControlChartSignal],
    ) -> List[str]:
        """Generate actionable recommendations."""
        recs = []

        errors = [
            v for v in validation_results
            if not v.passed and v.severity == ValidationSeverity.ERROR
        ]
        if errors:
            error_types = set(v.rule_name for v in errors)
            recs.append(
                f"Fix {len(errors)} data errors across {len(error_types)} rule types: "
                f"{', '.join(error_types)}"
            )

        outliers = [o for o in outlier_results if o.is_outlier]
        if outliers:
            recs.append(
                f"Investigate {len(outliers)} outlier transactions — "
                f"may indicate data entry errors or unusual business activity"
            )

        if signals:
            action_signals = [s for s in signals if s.severity == "action"]
            if action_signals:
                recs.append(
                    f"SPC charts detected {len(action_signals)} out-of-control signals — "
                    f"data generation process may have shifted"
                )

        if not recs:
            recs.append("Data quality is within acceptable limits")

        return recs

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status across all charts."""
        return {
            "transaction_count": self._transaction_count,
            "error_count": self._error_count,
            "error_rate": (
                self._error_count / max(self._transaction_count, 1)
            ),
            "charts": {
                "amount": self.amount_chart.get_status(),
                "volume": self.volume_chart.get_status(),
                "error_rate": self.error_rate_chart.get_status(),
                "price_ewma": self.price_ewma_chart.get_status(),
            },
        }
