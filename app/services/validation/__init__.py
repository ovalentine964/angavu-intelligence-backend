"""
Validation Layer for Angavu Intelligence Backend.

Validates ALL inputs and outputs before they reach users or buyers.
In financial software serving vulnerable workers, a wrong number
can cause panic. This module prevents that.

Three layers:
1. API Input Validation — Validate all incoming requests
2. Statistical Output Validation — Validate all computed numbers
3. Intelligence Product Validation — Validate all reports before delivery

All error messages in Swahili where they reach workers directly.
"""

from .api_validator import ApiValidator
from .intelligence_validator import IntelligenceValidator
from .statistical_validator import StatisticalValidator
from .validation_result import ValidationError, ValidationResult

__all__ = [
    "ApiValidator",
    "IntelligenceValidator",
    "StatisticalValidator",
    "ValidationError",
    "ValidationResult",
]
