"""
Outcome-Based Pricing Engine — Angavu Intelligence.

Enables value-aligned pricing where workers pay only when Msaidizi
recommendations demonstrably improve their business outcomes.

Core modules:
- baseline:     30-day baseline measurement for business metrics
- tracker:      Outcome tracking engine (detect when outcomes happen)
- attribution:  Causal attribution (did our recommendation cause the outcome?)
- billing:      Invoice generation when outcomes are verified
- consent:      Worker consent management (granular, revocable)
- models:       SQLAlchemy ORM models
- api:          FastAPI endpoints
"""

from app.services.outcome.models import (
    Baseline,
    BaselineMetric,
    Invoice,
    InvoiceStatus,
    MetricType,
    Outcome,
    OutcomeStatus,
    OutcomeType,
    WorkerConsent,
)
from app.services.outcome.baseline import BaselineEngine
from app.services.outcome.tracker import OutcomeTracker
from app.services.outcome.attribution import AttributionEngine
from app.services.outcome.billing import BillingEngine
from app.services.outcome.consent import ConsentManager

__all__ = [
    "AttributionEngine",
    "Baseline",
    "BaselineEngine",
    "BaselineMetric",
    "BillingEngine",
    "ConsentManager",
    "Invoice",
    "InvoiceStatus",
    "MetricType",
    "Outcome",
    "OutcomeStatus",
    "OutcomeTracker",
    "OutcomeType",
    "WorkerConsent",
]
