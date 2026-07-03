"""
Formal Reports — Bank, Government, and Insurance Presentable Reports.

Generates professional business reports from Msaidizi transaction data
that can be presented to formal institutions:

- **BankReport**: For loan applications (Equity, KCB, Co-op Bank)
- **GovernmentReport**: For KRA tax compliance and business registration
- **InsuranceReport**: For insurance coverage applications

A mama mboga should be able to walk into Equity Bank with her
Msaidizi report and get a loan approved.

Data Sources:
- Transaction records (sales, purchases, expenses)
- Alama Score (credit scoring service)
- Health Score (business health calculator)
- M-Pesa receipts (payment verification)
- Inventory records (stock valuation)

Statistical Foundation:
- Revenue projections: geometric mean growth with confidence intervals
- Risk assessment: coefficient of variation, standard deviation
- Credit scoring: Alama Score (300-850) with Heckman correction
- Tax estimation: Kenya tax bands (turnover tax, income tax)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, Inventory
from app.models.user import User
from app.config import get_settings
from app.schemas.formal_report import (
    BalanceSheetApproximation,
    BankReportData,
    BusinessPerformanceMetrics,
    BusinessStructure,
    CashFlowStatement,
    ComplianceLevel,
    CreditAssessment,
    CreditReadinessLevel,
    FormalizationReadiness,
    FormalizationReadinessData,
    GovernmentReportData,
    IncomeStatement,
    InsuranceReportData,
    ReportVerification,
    RiskCategory,
    RiskProfile,
    TaxSummary,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Kenya tax rates (2024/2025)
TURNOVER_TAX_RATE = 0.01  # 1% for businesses with turnover < KES 1M/month
TURNOVER_TAX_THRESHOLD_MONTHLY = 1_000_000  # KES per month

# Income tax bands (individual/sole proprietor)
INCOME_TAX_BANDS = [
    (24_000, 0.10),    # First KES 24,000 at 10%
    (32_333, 0.25),    # Next KES 32,333 at 25%
    (500_000, 0.30),   # Next KES 500,000 at 30%
    (417_667, 0.325),  # Next KES 417,667 at 32.5%
    (float("inf"), 0.35),  # Above at 35%
]
PERSONAL_RELIEF = 2_400  # Monthly personal relief

# Business registration costs (approximate)
REGISTRATION_COSTS = {
    BusinessStructure.SOLE_PROPRIETORSHIP: 1_000,
    BusinessStructure.PARTNERSHIP: 5_000,
    BusinessStructure.LIMITED_COMPANY: 10_000,
    BusinessStructure.COOPERATIVE: 15_000,
}

# Business type risk categories for insurance
BUSINESS_TYPE_RISK = {
    "food_vendor": RiskCategory.LOW,
    "mama_mboga": RiskCategory.LOW,
    "dukawallah": RiskCategory.LOW,
    "clothing_vendor": RiskCategory.MEDIUM,
    "electronics_vendor": RiskCategory.HIGH,
    "boda_boda": RiskCategory.HIGH,
    "tailor": RiskCategory.LOW,
    "hairdresser": RiskCategory.LOW,
    "carpenter": RiskCategory.MEDIUM,
    "mechanic": RiskCategory.HIGH,
    "restaurant": RiskCategory.MEDIUM,
    "butcher": RiskCategory.MEDIUM,
    "pharmacy": RiskCategory.LOW,
    "hardware_store": RiskCategory.MEDIUM,
}

# Insurance coverage types by business type
COVERAGE_TYPES = {
    RiskCategory.LOW: ["stock_coverage", "business_interruption"],
    RiskCategory.MEDIUM: ["stock_coverage", "business_interruption", "general_liability"],
    RiskCategory.HIGH: ["stock_coverage", "business_interruption", "general_liability", "theft_coverage"],
}


# ============================================================================
# Helper Functions
# ============================================================================

def _generate_report_id(prefix: str) -> str:
    """Generate a unique report ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"MSD-{prefix.upper()}-{ts}-{short_uuid}".upper()


def _compute_data_hash(data: dict) -> str:
    """Compute SHA-256 hash of report data for tamper detection."""
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _estimate_monthly_revenues(
    transactions: List[Transaction],
    period_start: date,
    period_end: date,
) -> List[Dict[str, float]]:
    """Compute monthly revenue breakdown from transactions."""
    monthly: Dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.transaction_type == "SALE":
            month_key = t.timestamp.strftime("%Y-%m")
            monthly[month_key] += t.amount

    result = []
    current = date(period_start.year, period_start.month, 1)
    end = date(period_end.year, period_end.month, 1)
    while current <= end:
        key = current.strftime("%Y-%m")
        result.append({"month": key, "revenue": round(monthly.get(key, 0), 2)})
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return result


def _compute_revenue_stability(daily_revenues: List[float]) -> Tuple[float, str]:
    """Compute coefficient of variation and stability rating."""
    if not daily_revenues or len(daily_revenues) < 2:
        return 0.0, "moderate"
    mean = np.mean(daily_revenues)
    if mean == 0:
        return 0.0, "volatile"
    cv = float(np.std(daily_revenues) / mean)
    if cv < 0.3:
        rating = "stable"
    elif cv < 0.7:
        rating = "moderate"
    else:
        rating = "volatile"
    return round(cv, 3), rating


def _estimate_kenya_income_tax(annual_profit: float) -> float:
    """Estimate annual income tax for a sole proprietor in Kenya."""
    if annual_profit <= 0:
        return 0.0

    tax = 0.0
    remaining = annual_profit
    for band_amount, rate in INCOME_TAX_BANDS:
        taxable = min(remaining, band_amount * 12)  # Bands are monthly
        tax += taxable * rate
        remaining -= taxable
        if remaining <= 0:
            break

    # Apply personal relief
    tax = max(0, tax - PERSONAL_RELIEF * 12)
    return round(tax, 2)


# ============================================================================
# BankReport
# ============================================================================

class BankReport:
    """
    Bank-presentable business report from Msaidizi data.

    Format: Professional structured data that can be rendered as PDF
    with company letterhead, charts, financial statements, and
    verification QR code.

    A mama mboga can walk into Equity Bank with this report
    and get a loan approved.

    Usage:
        report_service = BankReport(db)
        report = await report_service.generate(worker_id="...", period=("2026-01-01", "2026-06-30"))
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(
        self,
        worker_id: str,
        period: Tuple[str, str],
        language: str = "en",
    ) -> BankReportData:
        """
        Generate a bank-presentable report.

        Args:
            worker_id: User UUID string
            period: (start_date, end_date) as ISO date strings
            language: Report language ("en" or "sw")

        Returns:
            BankReportData with all sections populated
        """
        period_start = date.fromisoformat(period[0])
        period_end = date.fromisoformat(period[1])

        # Fetch user
        user = await self._get_user(worker_id)
        if not user:
            raise ValueError(f"Worker not found: {worker_id}")

        # Fetch transactions
        transactions = await self._get_transactions(
            user.id, period_start, period_end
        )

        # Fetch inventory
        inventory_items = await self._get_inventory(user.id)

        # Build report sections
        report_id = _generate_report_id("BANK")

        # Financial statements
        income_stmt = self._build_income_statement(
            transactions, period_start, period_end
        )
        cash_flow = self._build_cash_flow_statement(
            transactions, period_start, period_end
        )
        balance_sheet = self._build_balance_sheet(
            transactions, inventory_items, period_end
        )

        # Business metrics
        metrics = self._compute_business_metrics(
            transactions, period_start, period_end, inventory_items
        )

        # Credit assessment
        credit = await self._compute_credit_assessment(
            user, transactions, period_start, period_end, metrics
        )

        # Health score
        health_score, health_grade = self._compute_health_score(metrics, credit)

        # Verification
        verification = self._build_verification(
            report_id, transactions, period_start, period_end
        )

        # Period months
        period_months = max(1, (period_end - period_start).days // 30)

        report = BankReportData(
            report_type="bank",
            report_id=report_id,
            generated_at=datetime.now(timezone.utc),
            business_name=self._decrypt_field(user, "business_name") or f"{user.business_type or 'Business'}",
            owner_name=self._decrypt_field(user, "owner_name") or "Business Owner",
            business_type=user.business_type or "general",
            location=user.location_name or user.location_geohash or "Kenya",
            registration_number=None,
            period_start=period_start,
            period_end=period_end,
            period_months=period_months,
            total_revenue=income_stmt.net_revenue,
            total_expenses=income_stmt.total_operating_expenses + income_stmt.cost_of_goods_sold,
            net_profit=income_stmt.net_profit,
            business_health_score=health_score,
            health_grade=health_grade,
            income_statement=income_stmt,
            cash_flow=cash_flow,
            balance_sheet=balance_sheet,
            metrics=metrics,
            credit_assessment=credit,
            verification=verification,
            language=language,
        )

        logger.info(
            "bank_report_generated",
            worker_id=worker_id,
            report_id=report_id,
            revenue=income_stmt.net_revenue,
            alama_score=credit.alama_score if credit else None,
        )

        return report

    async def _get_user(self, worker_id: str) -> Optional[User]:
        """Fetch user by ID."""
        try:
            uid = uuid.UUID(worker_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(User).where(User.id == uid)
        )
        return result.scalar_one_or_none()

    async def _get_transactions(
        self,
        user_id: uuid.UUID,
        start: date,
        end: date,
    ) -> List[Transaction]:
        """Fetch transactions for the period."""
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.timestamp >= datetime.combine(start, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(end, datetime.max.time()),
                )
            )
        )
        return list(result.scalars().all())

    async def _get_inventory(self, user_id: uuid.UUID) -> List[Inventory]:
        """Fetch current inventory."""
        result = await self.db.execute(
            select(Inventory).where(Inventory.user_id == user_id)
        )
        return list(result.scalars().all())

    def _decrypt_field(self, user: User, field_name: str) -> Optional[str]:
        """
        Decrypt an encrypted user field.

        In production, this uses the encryption service.
        For now, return None if decryption isn't available.
        """
        # In production: decrypt user.name_encrypted, etc.
        # The encrypted fields store AES-256 ciphertext
        # For report generation, we work with what we have
        if field_name == "owner_name" and user.name_encrypted:
            # Would decrypt in production
            return None
        return None

    def _build_income_statement(
        self,
        transactions: List[Transaction],
        period_start: date,
        period_end: date,
    ) -> IncomeStatement:
        """Build Income Statement (P&L) from transactions."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        gross_revenue = sum(t.amount for t in sales)
        total_purchases = sum(t.amount for t in purchases)

        # COGS approximation
        cost_of_goods_sold = total_purchases
        gross_profit = gross_revenue - cost_of_goods_sold

        # Categorize operating expenses
        expense_categories: Dict[str, float] = defaultdict(float)
        for t in expenses:
            cat = t.item_category or "other"
            expense_categories[cat] += t.amount

        rent = expense_categories.get("rent", 0)
        transport = expense_categories.get("transport", 0)
        utilities = sum(
            expense_categories.get(k, 0)
            for k in ("utilities", "electricity", "water", "phone")
        )
        labor = expense_categories.get("labor", 0) + expense_categories.get("services", 0)
        licenses = expense_categories.get("licenses", 0)
        other_expenses = sum(
            v for k, v in expense_categories.items()
            if k not in ("rent", "transport", "utilities", "electricity",
                         "water", "phone", "labor", "services", "licenses")
        )

        total_operating_expenses = (
            rent + transport + utilities + labor + licenses + other_expenses
        )
        operating_profit = gross_profit - total_operating_expenses
        net_profit = operating_profit  # No interest/tax from raw transactions

        # Margins
        gross_margin = (gross_profit / gross_revenue * 100) if gross_revenue > 0 else 0
        operating_margin = (operating_profit / gross_revenue * 100) if gross_revenue > 0 else 0
        net_margin = (net_profit / gross_revenue * 100) if gross_revenue > 0 else 0

        return IncomeStatement(
            period_start=period_start,
            period_end=period_end,
            gross_revenue=round(gross_revenue, 2),
            returns_and_allowances=0,
            net_revenue=round(gross_revenue, 2),
            opening_inventory=0,
            purchases=round(total_purchases, 2),
            closing_inventory=0,
            cost_of_goods_sold=round(cost_of_goods_sold, 2),
            gross_profit=round(gross_profit, 2),
            rent=round(rent, 2),
            transport=round(transport, 2),
            utilities=round(utilities, 2),
            labor=round(labor, 2),
            licenses=round(licenses, 2),
            other_expenses=round(other_expenses, 2),
            total_operating_expenses=round(total_operating_expenses, 2),
            operating_profit=round(operating_profit, 2),
            interest_expense=0,
            tax_provision=0,
            net_profit=round(net_profit, 2),
            gross_margin_pct=round(gross_margin, 1),
            operating_margin_pct=round(operating_margin, 1),
            net_margin_pct=round(net_margin, 1),
        )

    def _build_cash_flow_statement(
        self,
        transactions: List[Transaction],
        period_start: date,
        period_end: date,
    ) -> CashFlowStatement:
        """Build Cash Flow Statement from transactions."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        # Operating activities
        cash_from_sales = sum(t.amount for t in sales)
        cash_from_mpesa = sum(
            t.amount for t in sales if t.payment_method == "mpesa"
        )
        cash_paid_suppliers = sum(t.amount for t in purchases)
        cash_paid_expenses = sum(t.amount for t in expenses)
        cash_paid_wages = sum(
            t.amount for t in expenses
            if (t.item_category or "") in ("labor", "services")
        )
        net_operating_cash = (
            cash_from_sales - cash_paid_suppliers - cash_paid_expenses
        )

        # Investing activities (purchases = inventory investment)
        inventory_purchases = cash_paid_suppliers
        net_investing_cash = -inventory_purchases

        # Financing activities (limited data from transactions)
        net_financing_cash = 0

        # Summary
        net_cash_change = net_operating_cash + net_investing_cash + net_financing_cash

        return CashFlowStatement(
            period_start=period_start,
            period_end=period_end,
            cash_from_sales=round(cash_from_sales, 2),
            cash_from_mpesa=round(cash_from_mpesa, 2),
            cash_paid_suppliers=round(cash_paid_suppliers, 2),
            cash_paid_expenses=round(cash_paid_expenses, 2),
            cash_paid_wages=round(cash_paid_wages, 2),
            net_operating_cash=round(net_operating_cash, 2),
            inventory_purchases=round(inventory_purchases, 2),
            asset_purchases=0,
            net_investing_cash=round(net_investing_cash, 2),
            loans_received=0,
            loan_repayments=0,
            owner_drawings=0,
            owner_contributions=0,
            net_financing_cash=0,
            net_cash_change=round(net_cash_change, 2),
            opening_cash=0,
            closing_cash=round(max(net_cash_change, 0), 2),
        )

    def _build_balance_sheet(
        self,
        transactions: List[Transaction],
        inventory_items: List[Inventory],
        as_of_date: date,
    ) -> BalanceSheetApproximation:
        """Build Balance Sheet approximation from available data."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        # Assets
        total_revenue = sum(t.amount for t in sales)
        total_purchases = sum(t.amount for t in purchases)
        total_expenses = sum(t.amount for t in expenses)

        # Cash approximation: revenue - purchases - expenses
        cash_and_mpesa = max(total_revenue - total_purchases - total_expenses, 0)

        # Inventory value
        inventory_value = sum(
            (item.current_stock or 0) * (item.avg_cost or 0)
            for item in inventory_items
        )

        # Accounts receivable: credit sales not yet collected
        credit_sales = sum(
            t.amount for t in sales if t.payment_method == "credit"
        )
        accounts_receivable = credit_sales

        total_current_assets = cash_and_mpesa + inventory_value + accounts_receivable
        total_assets = total_current_assets  # No fixed assets data

        # Liabilities (limited — estimated from credit purchases)
        credit_purchases = sum(
            t.amount for t in purchases if t.payment_method == "credit"
        )
        accounts_payable = credit_purchases
        total_current_liabilities = accounts_payable
        total_liabilities = total_current_liabilities

        # Equity
        owner_equity = total_assets - total_liabilities
        retained_earnings = total_revenue - total_purchases - total_expenses

        return BalanceSheetApproximation(
            as_of_date=as_of_date,
            cash_and_mpesa=round(cash_and_mpesa, 2),
            inventory_value=round(inventory_value, 2),
            accounts_receivable=round(accounts_receivable, 2),
            total_current_assets=round(total_current_assets, 2),
            fixed_assets=0,
            total_assets=round(total_assets, 2),
            accounts_payable=round(accounts_payable, 2),
            short_term_debt=0,
            total_current_liabilities=round(total_current_liabilities, 2),
            long_term_debt=0,
            total_liabilities=round(total_liabilities, 2),
            owner_equity=round(owner_equity, 2),
            retained_earnings=round(retained_earnings, 2),
            total_equity=round(owner_equity, 2),
            balance_check=round(total_assets, 2),
        )

    def _compute_business_metrics(
        self,
        transactions: List[Transaction],
        period_start: date,
        period_end: date,
        inventory_items: List[Inventory],
    ) -> BusinessPerformanceMetrics:
        """Compute key business metrics from transactions."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        total_days = max(1, (period_end - period_start).days)
        total_revenue = sum(t.amount for t in sales)
        total_purchases = sum(t.amount for t in purchases)
        total_expenses = sum(t.amount for t in expenses)
        net_profit = total_revenue - total_purchases - total_expenses

        # Daily breakdown
        daily_rev: Dict[str, float] = defaultdict(float)
        daily_count: Dict[str, int] = defaultdict(int)
        active_days = set()
        for t in sales:
            day_key = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day_key] += t.amount
            daily_count[day_key] += 1
            active_days.add(day_key)

        daily_revenues = list(daily_rev.values())
        operating_days = len(active_days)

        # Monthly breakdown
        monthly_rev: Dict[str, float] = defaultdict(float)
        monthly_profit: Dict[str, float] = defaultdict(float)
        for t in sales:
            mk = t.timestamp.strftime("%Y-%m")
            monthly_rev[mk] += t.amount
        for t in purchases:
            mk = t.timestamp.strftime("%Y-%m")
            monthly_profit[mk] -= t.amount
        for t in expenses:
            mk = t.timestamp.strftime("%Y-%m")
            monthly_profit[mk] -= t.amount
        for mk, rev in monthly_rev.items():
            monthly_profit[mk] += rev

        num_months = max(1, len(monthly_rev))
        avg_monthly_revenue = total_revenue / num_months
        avg_monthly_profit = sum(monthly_profit.values()) / max(1, len(monthly_profit))

        # Profit margin trend
        profit_margin_trend = []
        for mk in sorted(monthly_rev.keys()):
            rev = monthly_rev[mk]
            profit = monthly_profit.get(mk, 0)
            margin = (profit / rev * 100) if rev > 0 else 0
            profit_margin_trend.append({"month": mk, "margin_pct": round(margin, 1)})

        # Growth rates
        sorted_months = sorted(monthly_rev.keys())
        revenue_growth_mom = None
        revenue_growth_yoy = None
        if len(sorted_months) >= 2:
            last = monthly_rev[sorted_months[-1]]
            prev = monthly_rev[sorted_months[-2]]
            if prev > 0:
                revenue_growth_mom = round((last - prev) / prev * 100, 1)
        if len(sorted_months) >= 13:
            last = monthly_rev[sorted_months[-1]]
            yoy = monthly_rev[sorted_months[-13]]
            if yoy > 0:
                revenue_growth_yoy = round((last - yoy) / yoy * 100, 1)

        # Transaction metrics
        avg_daily_txns = len(sales) / max(operating_days, 1)
        avg_txn_value = total_revenue / max(len(sales), 1)

        # Product metrics
        unique_items = len(set(t.item for t in sales if t.item))
        product_revenue: Dict[str, float] = defaultdict(float)
        for t in sales:
            if t.item:
                product_revenue[t.item] += t.amount
        top_product_concentration = 0
        if product_revenue and total_revenue > 0:
            top_product_concentration = round(
                max(product_revenue.values()) / total_revenue * 100, 1
            )

        # Inventory turnover
        cogs = total_purchases
        avg_inventory = sum(
            (i.current_stock or 0) * (i.avg_cost or 0) for i in inventory_items
        )
        inventory_turnover = round(cogs / max(avg_inventory, 1), 2) if avg_inventory > 0 else 0

        # Customer metrics
        unique_customers = len(set(
            t.customer_phone_hash for t in sales if t.customer_phone_hash
        ))
        # Customer retention: customers with >1 transaction
        customer_visits: Dict[str, int] = defaultdict(int)
        for t in sales:
            if t.customer_phone_hash:
                customer_visits[t.customer_phone_hash] += 1
        returning = sum(1 for v in customer_visits.values() if v > 1)
        retention_rate = (
            round(returning / max(len(customer_visits), 1) * 100, 1)
            if customer_visits else 0
        )
        avg_customer_value = (
            total_revenue / max(unique_customers, 1) if unique_customers > 0 else 0
        )

        # Payment mix
        mpesa_count = sum(1 for t in sales if t.payment_method == "mpesa")
        cash_count = sum(1 for t in sales if t.payment_method == "cash")
        credit_count = sum(1 for t in sales if t.payment_method == "credit")
        total_count = max(len(sales), 1)

        # Revenue stability
        cv, stability_rating = _compute_revenue_stability(daily_revenues)

        return BusinessPerformanceMetrics(
            revenue_growth_mom_pct=revenue_growth_mom,
            revenue_growth_yoy_pct=revenue_growth_yoy,
            avg_monthly_revenue=round(avg_monthly_revenue, 2),
            avg_monthly_profit=round(avg_monthly_profit, 2),
            profit_margin_trend=profit_margin_trend,
            avg_daily_transactions=round(avg_daily_txns, 1),
            avg_transaction_value=round(avg_txn_value, 2),
            business_days_active=operating_days,
            total_days_in_period=total_days,
            operating_days_pct=round(operating_days / total_days * 100, 1),
            unique_products=unique_items,
            inventory_turnover=inventory_turnover,
            top_product_concentration_pct=top_product_concentration,
            unique_customers=unique_customers,
            customer_retention_rate_pct=retention_rate,
            avg_customer_value=round(avg_customer_value, 2),
            mpesa_pct=round(mpesa_count / total_count * 100, 1),
            cash_pct=round(cash_count / total_count * 100, 1),
            credit_pct=round(credit_count / total_count * 100, 1),
            coefficient_of_variation=cv,
            revenue_stability_rating=stability_rating,
        )

    async def _compute_credit_assessment(
        self,
        user: User,
        transactions: List[Transaction],
        period_start: date,
        period_end: date,
        metrics: BusinessPerformanceMetrics,
    ) -> CreditAssessment:
        """
        Compute credit assessment using Alama Score components.

        Uses the same scoring methodology as AlamaScoreService but
        optimized for report generation (no caching, direct computation).
        """
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        total_days = max(1, (period_end - period_start).days)
        total_revenue = sum(t.amount for t in sales)

        # Daily metrics
        daily_rev: Dict[str, float] = defaultdict(float)
        active_days = set()
        for t in sales:
            day_key = t.timestamp.strftime("%Y-%m-%d")
            daily_rev[day_key] += t.amount
            active_days.add(day_key)
        daily_revenues = list(daily_rev.values())
        operating_days = len(active_days)

        # Component scores
        txn_per_day = len(sales) / max(total_days, 1)
        activity_score = min(100, round(txn_per_day * 10, 1))

        if daily_revenues and len(daily_revenues) > 1:
            cv = float(np.std(daily_revenues) / max(np.mean(daily_revenues), 1))
            stability_score = max(0, min(100, round((1 - min(cv, 1)) * 100, 1)))
        else:
            stability_score = 50

        # Growth
        mid = len(sales) // 2
        first_rev = sum(t.amount for t in sales[:mid])
        second_rev = sum(t.amount for t in sales[mid:])
        if first_rev > 0:
            growth_pct = (second_rev - first_rev) / first_rev * 100
            growth_score = min(100, max(0, round(50 + growth_pct, 1)))
        else:
            growth_score = 50

        consistency_score = min(100, round(operating_days / max(total_days, 1) * 100, 1))

        unique_categories = len(set(t.item_category for t in sales if t.item_category))
        unique_items = len(set(t.item for t in sales if t.item))
        diversity_score = min(100, round(unique_categories * 15 + unique_items * 3, 1))

        # Composite score (300-850)
        weighted = (
            activity_score * 0.25
            + stability_score * 0.25
            + growth_score * 0.15
            + consistency_score * 0.20
            + diversity_score * 0.15
        )
        alama_score = max(300, min(850, int(300 + (weighted / 100) * 550)))

        # Score band
        if alama_score >= 750:
            score_band = "excellent"
        elif alama_score >= 650:
            score_band = "good"
        elif alama_score >= 550:
            score_band = "fair"
        elif alama_score >= 450:
            score_band = "poor"
        else:
            score_band = "very_poor"

        # Risk factors
        risk_factors = []
        if activity_score < 30:
            risk_factors.append("Low business activity")
        if stability_score < 40:
            risk_factors.append("Revenue instability")
        if growth_score < 30:
            risk_factors.append("Declining business")
        if consistency_score < 50:
            risk_factors.append("Irregular operating hours")
        if metrics.coefficient_of_variation > 0.8:
            risk_factors.append("High revenue volatility")
        if not risk_factors:
            risk_factors.append("No significant risk factors")

        # Default probability
        score_normalized = (alama_score - 300) / 550
        default_prob = round(1 / (1 + np.exp(5 * (score_normalized - 0.4))) * 100, 1)

        # Readiness
        readiness_score = round(
            (alama_score - 300) / 550 * 100, 1
        )
        if alama_score >= 650 and consistency_score >= 60:
            readiness = CreditReadinessLevel.READY
        elif alama_score >= 500:
            readiness = CreditReadinessLevel.NEEDS_IMPROVEMENT
        else:
            readiness = CreditReadinessLevel.NOT_READY

        # Loan recommendation
        avg_daily_rev = total_revenue / max(total_days, 1)
        monthly_profit = (
            metrics.avg_monthly_profit if metrics.avg_monthly_profit > 0
            else avg_daily_rev * 30 * 0.2
        )
        recommended_loan = round(monthly_profit * 6, -3)  # 6 months of profit
        max_safe_loan = round(monthly_profit * 12, -3)  # 12 months of profit
        if readiness == CreditReadinessLevel.NOT_READY:
            recommended_loan = 0
            max_safe_loan = 0

        # DSCR
        monthly_repayment = round(recommended_loan / 12 * 1.15, 2) if recommended_loan > 0 else 0
        dscr = round(monthly_profit / max(monthly_repayment, 1), 2) if monthly_repayment > 0 else 0

        # Risk category
        if alama_score >= 700 and len(risk_factors) <= 1:
            risk_cat = RiskCategory.LOW
        elif alama_score >= 500:
            risk_cat = RiskCategory.MEDIUM
        else:
            risk_cat = RiskCategory.HIGH

        # Percentile (simplified — in production uses peer data)
        percentile = round((alama_score - 300) / 550 * 100, 1)

        return CreditAssessment(
            alama_score=alama_score,
            score_band=score_band,
            percentile=percentile,
            credit_readiness=readiness,
            readiness_score=readiness_score,
            recommended_loan_amount=recommended_loan,
            max_safe_loan_amount=max_safe_loan,
            recommended_term_months=12,
            estimated_monthly_repayment=monthly_repayment,
            debt_service_coverage_ratio=dscr,
            risk_factors=risk_factors,
            risk_category=risk_cat,
            default_probability_pct=default_prob,
            activity_score=activity_score,
            stability_score=stability_score,
            growth_score=growth_score,
            consistency_score=consistency_score,
            diversity_score=diversity_score,
        )

    def _compute_health_score(
        self,
        metrics: BusinessPerformanceMetrics,
        credit: CreditAssessment,
    ) -> Tuple[float, str]:
        """Compute business health score from metrics and credit assessment."""
        score = 0

        # Profitability (25%)
        if metrics.profit_margin_trend:
            latest_margin = metrics.profit_margin_trend[-1].get("margin_pct", 0)
        else:
            latest_margin = 0
        if latest_margin >= 30:
            score += 25
        elif latest_margin >= 20:
            score += 20
        elif latest_margin >= 10:
            score += 15
        elif latest_margin > 0:
            score += 8

        # Growth (25%)
        growth = metrics.revenue_growth_mom_pct
        if growth is not None:
            if growth >= 10:
                score += 25
            elif growth >= 5:
                score += 20
            elif growth >= 0:
                score += 15
            elif growth >= -10:
                score += 8
            else:
                score += 3
        else:
            score += 12  # Neutral if no comparison data

        # Consistency (20%)
        if metrics.operating_days_pct >= 80:
            score += 20
        elif metrics.operating_days_pct >= 60:
            score += 15
        elif metrics.operating_days_pct >= 40:
            score += 10
        else:
            score += 5

        # Diversity (15%)
        if metrics.unique_products >= 5:
            score += 15
        elif metrics.unique_products >= 3:
            score += 12
        elif metrics.unique_products >= 2:
            score += 8
        else:
            score += 3

        # Data quality (15%)
        if metrics.avg_daily_transactions >= 5:
            score += 15
        elif metrics.avg_daily_transactions >= 3:
            score += 12
        elif metrics.avg_daily_transactions >= 1:
            score += 8
        else:
            score += 3

        health_score = min(100, max(0, float(score)))

        if health_score >= 90:
            grade = "A+"
        elif health_score >= 80:
            grade = "A"
        elif health_score >= 70:
            grade = "B+"
        elif health_score >= 60:
            grade = "B"
        elif health_score >= 50:
            grade = "C+"
        elif health_score >= 40:
            grade = "C"
        elif health_score >= 30:
            grade = "D"
        else:
            grade = "F"

        return health_score, grade

    def _build_verification(
        self,
        report_id: str,
        transactions: List[Transaction],
        period_start: date,
        period_end: date,
    ) -> ReportVerification:
        """Build report verification data."""
        total_txns = len(transactions)
        mpesa_verified = any(t.mpesa_receipt for t in transactions)
        voice_verified = any(t.recorded_via == "voice" for t in transactions)

        # Data quality score
        fields_populated = 0
        fields_total = 0
        for t in transactions:
            fields_total += 6  # item, amount, type, timestamp, payment_method, quantity
            if t.item:
                fields_populated += 1
            if t.amount > 0:
                fields_populated += 1
            if t.transaction_type:
                fields_populated += 1
            if t.timestamp:
                fields_populated += 1
            if t.payment_method:
                fields_populated += 1
            if t.quantity and t.quantity > 0:
                fields_populated += 1
        data_quality = round(fields_populated / max(fields_total, 1), 2)

        # Data hash for tamper detection
        txn_data = [
            {"id": str(t.id), "amount": t.amount, "type": t.transaction_type,
             "ts": t.timestamp.isoformat() if t.timestamp else None}
            for t in transactions
        ]
        data_hash = _compute_data_hash({"report_id": report_id, "transactions": txn_data})

        # QR code data (verification URL)
        _settings = get_settings()
        verification_url = f"{_settings.VERIFICATION_BASE_URL}/report/{report_id}"
        qr_data = json.dumps({
            "report_id": report_id,
            "hash": data_hash[:16],
            "txns": total_txns,
            "period": f"{period_start.isoformat()}_{period_end.isoformat()}",
        })

        return ReportVerification(
            total_transactions=total_txns,
            data_quality_score=data_quality,
            data_completeness_pct=round(data_quality * 100, 1),
            voice_verified=voice_verified,
            mpesa_verified=mpesa_verified,
            inventory_verified=False,
            report_id=report_id,
            generated_at=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=90),
            verification_url=verification_url,
            qr_code_data=qr_data,
            data_hash=data_hash,
            signature="",  # Would be RSA-signed in production
        )


# ============================================================================
# GovernmentReport
# ============================================================================

class GovernmentReport:
    """
    Government (KRA) presentable report.

    Generates tax summaries, compliance assessments, and
    formalization readiness for government agencies.

    Usage:
        gov_report = GovernmentReport(db)
        report = await gov_report.generate(worker_id="...", period=("2026-01-01", "2026-06-30"))
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(
        self,
        worker_id: str,
        period: Tuple[str, str],
        language: str = "en",
    ) -> GovernmentReportData:
        """
        Generate a government-presentable report.

        Args:
            worker_id: User UUID string
            period: (start_date, end_date) as ISO date strings
            language: Report language

        Returns:
            GovernmentReportData with tax summary and formalization assessment
        """
        period_start = date.fromisoformat(period[0])
        period_end = date.fromisoformat(period[1])

        user = await self._get_user(worker_id)
        if not user:
            raise ValueError(f"Worker not found: {worker_id}")

        transactions = await self._get_transactions(
            user.id, period_start, period_end
        )

        report_id = _generate_report_id("GOV")

        # Build tax summary
        tax_summary = self._build_tax_summary(
            transactions, period_start, period_end
        )

        # Build formalization assessment
        formalization = self._build_formalization(user, transactions)

        # Financial summary
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]
        total_revenue = sum(t.amount for t in sales)
        total_expenses_amount = sum(t.amount for t in expenses) + sum(t.amount for t in purchases)
        net_profit = total_revenue - total_expenses_amount

        # M-Pesa transactions count
        mpesa_txns = sum(1 for t in transactions if t.mpesa_receipt)

        # Data quality
        data_quality = self._compute_data_quality(transactions)

        verification = self._build_verification(report_id, transactions, period_start, period_end)

        report = GovernmentReportData(
            report_type="government",
            report_id=report_id,
            generated_at=datetime.now(timezone.utc),
            business_name=self._get_business_name(user),
            owner_name="Business Owner",
            business_type=user.business_type or "general",
            location=user.location_name or "Kenya",
            period_start=period_start,
            period_end=period_end,
            total_revenue=round(total_revenue, 2),
            total_expenses=round(total_expenses_amount, 2),
            net_profit=round(net_profit, 2),
            tax_summary=tax_summary,
            formalization=formalization,
            total_transactions=len(transactions),
            mpesa_transactions=mpesa_txns,
            data_quality_score=data_quality,
            verification=verification,
            language=language,
        )

        logger.info(
            "government_report_generated",
            worker_id=worker_id,
            report_id=report_id,
            revenue=total_revenue,
            tax_estimate=tax_summary.total_estimated_tax if tax_summary else 0,
        )

        return report

    async def _get_user(self, worker_id: str) -> Optional[User]:
        try:
            uid = uuid.UUID(worker_id)
        except ValueError:
            return None
        result = await self.db.execute(select(User).where(User.id == uid))
        return result.scalar_one_or_none()

    async def _get_transactions(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> List[Transaction]:
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.timestamp >= datetime.combine(start, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(end, datetime.max.time()),
                )
            )
        )
        return list(result.scalars().all())

    def _get_business_name(self, user: User) -> str:
        return f"{user.business_type or 'Business'}".replace("_", " ").title()

    def _build_tax_summary(
        self,
        transactions: List[Transaction],
        period_start: date,
        period_end: date,
    ) -> TaxSummary:
        """Build tax summary with KRA-specific calculations."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]

        total_revenue = sum(t.amount for t in sales)
        total_deductions = sum(t.amount for t in purchases) + sum(t.amount for t in expenses)
        net_profit = total_revenue - total_deductions

        # Monthly breakdown
        monthly_revenue = _estimate_monthly_revenues(transactions, period_start, period_end)

        # Period in months
        months = max(1, (period_end - period_start).days // 30)
        annual_revenue_estimate = total_revenue / months * 12

        # Tax calculations
        annual_profit_estimate = net_profit / months * 12

        # Turnover tax (1% for businesses with monthly turnover < KES 1M)
        avg_monthly_revenue = total_revenue / max(months, 1)
        turnover_tax_eligible = avg_monthly_revenue < TURNOVER_TAX_THRESHOLD_MONTHLY
        if turnover_tax_eligible:
            turnover_tax = round(total_revenue * TURNOVER_TAX_RATE, 2)
        else:
            turnover_tax = 0

        # Income tax
        income_tax = _estimate_kenya_income_tax(max(annual_profit_estimate, 0))

        # VAT (if revenue > KES 5M annually)
        vat_threshold = 5_000_000
        estimated_vat = 0
        if annual_revenue_estimate > vat_threshold:
            estimated_vat = round(total_revenue * 0.16, 2)  # 16% VAT

        total_tax = turnover_tax + income_tax / 12 * months + estimated_vat

        # Compliance readiness
        if turnover_tax_eligible:
            recommended_category = "Turnover Tax (Simplified)"
            compliance_score = 80
            compliance = ComplianceLevel.COMPLIANT
        elif annual_profit_estimate > 0:
            recommended_category = "Income Tax (Individual)"
            compliance_score = 60
            compliance = ComplianceLevel.PARTIALLY_COMPLIANT
        else:
            recommended_category = "Not yet taxable"
            compliance_score = 40
            compliance = ComplianceLevel.NON_COMPLIANT

        # Missing items
        missing = []
        mpesa_verified = any(t.mpesa_receipt for t in sales)
        if not mpesa_verified:
            missing.append("M-Pesa statement backup for revenue verification")
        if not any(t.recorded_via == "voice" for t in transactions):
            missing.append("Voice-recorded transaction evidence")
        if len(sales) < 30:
            missing.append("More transaction records for reliable tax base")

        return TaxSummary(
            monthly_revenue=monthly_revenue,
            gross_revenue_ytd=round(total_revenue, 2),
            estimated_annual_revenue=round(annual_revenue_estimate, 2),
            estimated_income_tax=round(income_tax / 12 * months, 2),
            estimated_vat=estimated_vat,
            turnover_tax=turnover_tax,
            total_estimated_tax=round(total_tax, 2),
            compliance_readiness=compliance,
            compliance_score=compliance_score,
            recommended_tax_category=recommended_category,
            turnover_tax_eligible=turnover_tax_eligible,
            missing_items=missing,
        )

    def _build_formalization(
        self, user: User, transactions: List[Transaction]
    ) -> FormalizationReadinessData:
        """Assess business formalization readiness."""
        score = 0
        documents_ready = []
        documents_missing = []
        next_steps = []

        # Has consistent transaction data (30 points)
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        if len(sales) >= 100:
            score += 30
            documents_ready.append("Transaction history (100+ records)")
        elif len(sales) >= 30:
            score += 20
            documents_ready.append("Transaction history (30+ records)")
        else:
            score += 10
            documents_missing.append("Insufficient transaction history")

        # Has business location (20 points)
        if user.location_geohash:
            score += 20
            documents_ready.append("Business location verified")
        else:
            score += 5
            documents_missing.append("Business location documentation")

        # Has M-Pesa records (20 points)
        mpesa_count = sum(1 for t in transactions if t.mpesa_receipt)
        if mpesa_count >= 10:
            score += 20
            documents_ready.append("M-Pesa transaction records")
        elif mpesa_count > 0:
            score += 10
        else:
            documents_missing.append("M-Pesa/bank statements")

        # Business type identified (15 points)
        if user.business_type and user.business_type != "other":
            score += 15
            documents_ready.append("Business type identified")
        else:
            score += 5
            documents_missing.append("Business type classification")

        # Active business (15 points)
        if user.is_active:
            score += 15
        else:
            score += 5

        score = min(100, score)

        # Readiness level
        if score >= 70:
            readiness = FormalizationReadiness.READY
        elif score >= 40:
            readiness = FormalizationReadiness.PARTIALLY_READY
        else:
            readiness = FormalizationReadiness.NOT_READY

        # Recommended structure
        if len(sales) > 500 and user.business_type in ("restaurant", "hardware_store"):
            structure = BusinessStructure.LIMITED_COMPANY
        elif len(sales) > 200:
            structure = BusinessStructure.PARTNERSHIP
        else:
            structure = BusinessStructure.SOLE_PROPRIETORSHIP

        # Standard required documents
        required_docs = [
            "National ID / Passport",
            "KRA PIN Certificate",
            "Business name reservation (BRS)",
            "Location details / utility bill",
            "Business permit from county government",
        ]

        # Next steps
        if readiness == FormalizationReadiness.READY:
            next_steps = [
                "Visit your nearest Huduma Centre for business registration",
                f"Register as {structure.value.replace('_', ' ')}",
                "Apply for a KRA PIN if you don't have one",
                "Get a county business permit",
            ]
        elif readiness == FormalizationReadiness.PARTIALLY_READY:
            next_steps = [
                "Continue recording transactions in Msaidizi",
                "Build up M-Pesa transaction history",
                "Ensure you have a valid national ID",
                "Collect location documentation",
            ]
        else:
            next_steps = [
                "Start recording all business transactions",
                "Use M-Pesa for payments to build a record",
                "Keep your business operating consistently",
                "Register for a KRA PIN at the nearest KRA office",
            ]

        # Registration cost
        estimated_cost = REGISTRATION_COSTS.get(structure, 5_000)
        # Add county permit
        estimated_cost += 5_000  # Approximate county business permit

        return FormalizationReadinessData(
            readiness_score=score,
            readiness_level=readiness,
            recommended_structure=structure,
            required_documents=required_docs,
            documents_ready=documents_ready,
            documents_missing=documents_missing,
            next_steps=next_steps,
            estimated_cost_kes=estimated_cost,
        )

    def _compute_data_quality(self, transactions: List[Transaction]) -> float:
        if not transactions:
            return 0.0
        fields_populated = 0
        fields_total = 0
        for t in transactions:
            fields_total += 6
            if t.item:
                fields_populated += 1
            if t.amount > 0:
                fields_populated += 1
            if t.transaction_type:
                fields_populated += 1
            if t.timestamp:
                fields_populated += 1
            if t.payment_method:
                fields_populated += 1
            if t.quantity and t.quantity > 0:
                fields_populated += 1
        return round(fields_populated / max(fields_total, 1), 2)

    def _build_verification(
        self, report_id: str, transactions: List[Transaction],
        period_start: date, period_end: date,
    ) -> ReportVerification:
        """Build verification data for government report."""
        total_txns = len(transactions)
        data_hash = _compute_data_hash({
            "report_id": report_id,
            "txns": total_txns,
            "period": f"{period_start}_{period_end}",
        })
        _settings = get_settings()
        verification_url = f"{_settings.VERIFICATION_BASE_URL}/report/{report_id}"
        qr_data = json.dumps({
            "report_id": report_id,
            "hash": data_hash[:16],
            "txns": total_txns,
        })
        return ReportVerification(
            total_transactions=total_txns,
            data_quality_score=self._compute_data_quality(transactions),
            data_completeness_pct=round(self._compute_data_quality(transactions) * 100, 1),
            voice_verified=any(t.recorded_via == "voice" for t in transactions),
            mpesa_verified=any(t.mpesa_receipt for t in transactions),
            inventory_verified=False,
            report_id=report_id,
            generated_at=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=90),
            verification_url=verification_url,
            qr_code_data=qr_data,
            data_hash=data_hash,
            signature="",
        )


# ============================================================================
# InsuranceReport
# ============================================================================

class InsuranceReport:
    """
    Insurance company presentable report.

    Generates risk profiles and coverage recommendations
    for business insurance applications.

    Usage:
        ins_report = InsuranceReport(db)
        report = await ins_report.generate(worker_id="...", period=("2026-01-01", "2026-06-30"))
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(
        self,
        worker_id: str,
        period: Tuple[str, str],
        language: str = "en",
    ) -> InsuranceReportData:
        """
        Generate an insurance-presentable report.

        Args:
            worker_id: User UUID string
            period: (start_date, end_date) as ISO date strings
            language: Report language

        Returns:
            InsuranceReportData with risk profile and coverage recommendations
        """
        period_start = date.fromisoformat(period[0])
        period_end = date.fromisoformat(period[1])

        user = await self._get_user(worker_id)
        if not user:
            raise ValueError(f"Worker not found: {worker_id}")

        transactions = await self._get_transactions(
            user.id, period_start, period_end
        )
        inventory_items = await self._get_inventory(user.id)

        report_id = _generate_report_id("INS")

        # Financial summary
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        purchases = [t for t in transactions if t.transaction_type == "PURCHASE"]
        expenses = [t for t in transactions if t.transaction_type == "EXPENSE"]
        total_revenue = sum(t.amount for t in sales)
        total_expenses_amount = sum(t.amount for t in expenses) + sum(t.amount for t in purchases)
        net_profit = total_revenue - total_expenses_amount

        months = max(1, (period_end - period_start).days // 30)
        avg_monthly_rev = total_revenue / months

        # Active days
        active_days = len(set(
            t.timestamp.strftime("%Y-%m-%d") for t in sales
        ))

        # Unique products
        unique_products = len(set(t.item for t in sales if t.item))

        # Risk profile
        risk_profile = self._build_risk_profile(
            user, transactions, inventory_items, period_start, period_end
        )

        # Data quality
        data_quality = self._compute_data_quality(transactions)

        verification = self._build_verification(report_id, transactions, period_start, period_end)

        report = InsuranceReportData(
            report_type="insurance",
            report_id=report_id,
            generated_at=datetime.now(timezone.utc),
            business_name=self._get_business_name(user),
            owner_name="Business Owner",
            business_type=user.business_type or "general",
            location=user.location_name or "Kenya",
            business_age_months=months,  # Approximation from data period
            period_start=period_start,
            period_end=period_end,
            total_revenue=round(total_revenue, 2),
            total_expenses=round(total_expenses_amount, 2),
            net_profit=round(net_profit, 2),
            avg_monthly_revenue=round(avg_monthly_rev, 2),
            risk_profile=risk_profile,
            total_transactions=len(transactions),
            business_days_active=active_days,
            unique_products=unique_products,
            data_quality_score=data_quality,
            verification=verification,
            language=language,
        )

        logger.info(
            "insurance_report_generated",
            worker_id=worker_id,
            report_id=report_id,
            risk_category=risk_profile.risk_category if risk_profile else None,
        )

        return report

    async def _get_user(self, worker_id: str) -> Optional[User]:
        try:
            uid = uuid.UUID(worker_id)
        except ValueError:
            return None
        result = await self.db.execute(select(User).where(User.id == uid))
        return result.scalar_one_or_none()

    async def _get_transactions(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> List[Transaction]:
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.timestamp >= datetime.combine(start, datetime.min.time()),
                    Transaction.timestamp <= datetime.combine(end, datetime.max.time()),
                )
            )
        )
        return list(result.scalars().all())

    async def _get_inventory(self, user_id: uuid.UUID) -> List[Inventory]:
        result = await self.db.execute(
            select(Inventory).where(Inventory.user_id == user_id)
        )
        return list(result.scalars().all())

    def _get_business_name(self, user: User) -> str:
        return f"{user.business_type or 'Business'}".replace("_", " ").title()

    def _build_risk_profile(
        self,
        user: User,
        transactions: List[Transaction],
        inventory_items: List[Inventory],
        period_start: date,
        period_end: date,
    ) -> RiskProfile:
        """Build risk profile for insurance assessment."""
        sales = [t for t in transactions if t.transaction_type == "SALE"]
        total_revenue = sum(t.amount for t in sales)
        months = max(1, (period_end - period_start).days // 30)
        avg_monthly_rev = total_revenue / months

        # Revenue stability
        monthly_rev: Dict[str, float] = defaultdict(float)
        for t in sales:
            mk = t.timestamp.strftime("%Y-%m")
            monthly_rev[mk] += t.amount
        monthly_values = list(monthly_rev.values())

        if monthly_values and len(monthly_values) > 1:
            cv = float(np.std(monthly_values) / max(np.mean(monthly_values), 1))
        else:
            cv = 0.0

        if cv < 0.3:
            stability = "stable"
        elif cv < 0.7:
            stability = "moderate"
        else:
            stability = "volatile"

        # Business type risk
        biz_type = user.business_type or "other"
        risk_category = BUSINESS_TYPE_RISK.get(biz_type, RiskCategory.MEDIUM)

        # Risk score (0-100, lower = safer)
        risk_score = 0
        if risk_category == RiskCategory.LOW:
            risk_score += 20
        elif risk_category == RiskCategory.MEDIUM:
            risk_score += 50
        else:
            risk_score += 80

        # Adjust for revenue stability
        if stability == "stable":
            risk_score -= 10
        elif stability == "volatile":
            risk_score += 15

        risk_score = max(0, min(100, risk_score))

        # Location risk factors
        location_risks = []
        location = user.location_name or ""
        if any(area in location.lower() for area in ("cbd", "central", "downtown")):
            location_risks.append("High-traffic urban area")
        if any(area in location.lower() for area in ("market", "gikomba", "toi", "kamukunji")):
            location_risks.append("Market area — higher foot traffic but fire risk")
        if not location_risks:
            location_risks.append("Standard location risk")

        # Inventory value at risk
        inventory_value = sum(
            (i.current_stock or 0) * (i.avg_cost or 0)
            for i in inventory_items
        )

        # Coverage recommendation
        # Based on inventory value + 3 months revenue
        recommended_coverage = round(inventory_value + avg_monthly_rev * 3, -3)

        # Premium estimate (1-3% of coverage for low-risk, 3-8% for high-risk)
        if risk_category == RiskCategory.LOW:
            premium_rate_low = 0.01
            premium_rate_high = 0.03
        elif risk_category == RiskCategory.MEDIUM:
            premium_rate_low = 0.03
            premium_rate_high = 0.05
        else:
            premium_rate_low = 0.05
            premium_rate_high = 0.08

        premium_min = round(recommended_coverage * premium_rate_low, -2)
        premium_max = round(recommended_coverage * premium_rate_high, -2)

        # Coverage types
        coverage_types = COVERAGE_TYPES.get(risk_category, ["stock_coverage"])

        # Business interruption risk
        if stability == "stable" and risk_category == RiskCategory.LOW:
            interruption_risk = "low"
        elif stability == "volatile" or risk_category == RiskCategory.HIGH:
            interruption_risk = "high"
        else:
            interruption_risk = "medium"

        return RiskProfile(
            business_type=biz_type,
            risk_category=risk_category,
            risk_score=risk_score,
            avg_monthly_revenue=round(avg_monthly_rev, 2),
            revenue_coefficient_of_variation=cv,
            revenue_stability=stability,
            months_of_data=months,
            location=user.location_name or "Kenya",
            location_risk_factors=location_risks,
            has_claims_history=False,
            claims_count=0,
            recommended_coverage_amount=recommended_coverage,
            recommended_premium_range=(premium_min, premium_max),
            coverage_types=coverage_types,
            inventory_value_at_risk=round(inventory_value, 2),
            monthly_revenue_at_risk=round(avg_monthly_rev, 2),
            business_interruption_risk=interruption_risk,
        )

    def _compute_data_quality(self, transactions: List[Transaction]) -> float:
        if not transactions:
            return 0.0
        fields_populated = 0
        fields_total = 0
        for t in transactions:
            fields_total += 6
            if t.item:
                fields_populated += 1
            if t.amount > 0:
                fields_populated += 1
            if t.transaction_type:
                fields_populated += 1
            if t.timestamp:
                fields_populated += 1
            if t.payment_method:
                fields_populated += 1
            if t.quantity and t.quantity > 0:
                fields_populated += 1
        return round(fields_populated / max(fields_total, 1), 2)

    def _build_verification(
        self, report_id: str, transactions: List[Transaction],
        period_start: date, period_end: date,
    ) -> ReportVerification:
        total_txns = len(transactions)
        data_hash = _compute_data_hash({
            "report_id": report_id,
            "txns": total_txns,
        })
        return ReportVerification(
            total_transactions=total_txns,
            data_quality_score=self._compute_data_quality(transactions),
            data_completeness_pct=round(self._compute_data_quality(transactions) * 100, 1),
            voice_verified=any(t.recorded_via == "voice" for t in transactions),
            mpesa_verified=any(t.mpesa_receipt for t in transactions),
            inventory_verified=False,
            report_id=report_id,
            generated_at=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=90),
            verification_url=f"{get_settings().VERIFICATION_BASE_URL}/report/{report_id}",
            qr_code_data=json.dumps({"report_id": report_id, "hash": data_hash[:16]}),
            data_hash=data_hash,
            signature="",
        )
