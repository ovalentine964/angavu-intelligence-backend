"""
Referral Commission Engine — Match workers to financial products and track commissions.

Revenue model:
  - Loan referrals: 1-3% commission on disbursed amount
  - Insurance referrals: 10-25% of first-year premium
  - Savings product referrals: flat fee per activated account
  - Equipment financing: 2-5% of financed amount

This engine:
  1. Matches workers to suitable financial products based on their profile
  2. Generates referral links/tracking codes
  3. Tracks referral lifecycle (click → application → approval → disbursement)
  4. Calculates and records commissions
  5. Generates commission reports for settlement
"""

from .commission import CommissionTracker
from .engine import ReferralEngine
from .models import (
    Commission,
    CommissionReport,
    CommissionStatus,
    CommissionType,
    FinancialPartner,
    ProductMatch,
    Referral,
    ReferralStatus,
    ReferralSummary,
)

__all__ = [
    "Commission",
    "CommissionReport",
    "CommissionStatus",
    "CommissionTracker",
    "CommissionType",
    "FinancialPartner",
    "ProductMatch",
    "Referral",
    "ReferralEngine",
    "ReferralStatus",
    "ReferralSummary",
]
