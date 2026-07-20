"""
Backward-compatibility shim.

Canonical definitions are now in app.models.intelligence_products.
This module re-exports them so existing imports continue to work.
"""

from app.models.intelligence_products import (  # noqa: F401
    DataAccessLog,
    IntelligenceProduct,
)
