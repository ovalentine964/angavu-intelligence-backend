"""
Worker Reports Package — Msaidizi / Angavu Intelligence.

5 report types for WhatsApp delivery to informal workers:
  1. DailyReport    — End-of-day snapshot
  2. WeeklyReport   — Weekly trends & patterns
  3. MonthlyReport  — Monthly health check
  4. SemiAnnualReport — 6-month strategic review
  5. AnnualReport   — Comprehensive annual picture
"""

from .formal_reports import (
    BankReport,
    GovernmentReport,
    InsuranceReport,
)
from .worker_reports import (
    AnnualReport,
    CustomerData,
    DailyReport,
    InventoryStatus,
    MonthlyReport,
    PriceData,
    ReportFactory,
    SemiAnnualReport,
    TransactionSummary,
    WeeklyReport,
    WorkerProfile,
    WorkerReport,
)

__all__ = [
    "AnnualReport",
    "BankReport",
    "CustomerData",
    "DailyReport",
    "GovernmentReport",
    "InsuranceReport",
    "InventoryStatus",
    "MonthlyReport",
    "PriceData",
    "ReportFactory",
    "SemiAnnualReport",
    "TransactionSummary",
    "WeeklyReport",
    "WorkerProfile",
    "WorkerReport",
]
