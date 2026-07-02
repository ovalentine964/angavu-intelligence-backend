"""
Formal Report Schemas — Bank, Government, and Insurance Presentable Reports.

These schemas define the structure of reports that can be presented to:
- Banks (Equity, KCB, Co-op) for loan applications
- Government (KRA) for tax compliance and business registration
- Insurance companies for business coverage

A mama mboga should be able to walk into Equity Bank with her
Msaidizi report and get a loan approved.
"""

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class CreditReadinessLevel(str, Enum):
    """Credit readiness classification."""
    READY = "ready"
    NEEDS_IMPROVEMENT = "needs_improvement"
    NOT_READY = "not_ready"


class RiskCategory(str, Enum):
    """Business risk classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComplianceLevel(str, Enum):
    """Tax compliance readiness."""
    COMPLIANT = "compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"


class FormalizationReadiness(str, Enum):
    """Business formalization readiness."""
    READY = "ready"
    PARTIALLY_READY = "partially_ready"
    NOT_READY = "not_ready"


class BusinessStructure(str, Enum):
    """Recommended business registration structure."""
    SOLE_PROPRIETORSHIP = "sole_proprietorship"
    PARTNERSHIP = "partnership"
    LIMITED_COMPANY = "limited_company"
    COOPERATIVE = "cooperative"


# ============================================================================
# Financial Statement Schemas
# ============================================================================

class IncomeStatement(BaseModel):
    """
    Income Statement (Profit & Loss).

    Standard financial statement showing revenue, costs, and profit
    over a period. Formatted for bank review.
    """
    period_start: date
    period_end: date

    # Revenue
    gross_revenue: float = Field(0, description="Total sales revenue in KES")
    returns_and_allowances: float = Field(0, description="Returns/refunds in KES")
    net_revenue: float = Field(0, description="Gross revenue minus returns")

    # Cost of Goods Sold
    opening_inventory: float = Field(0, description="Inventory value at period start")
    purchases: float = Field(0, description="Total purchases in KES")
    closing_inventory: float = Field(0, description="Inventory value at period end")
    cost_of_goods_sold: float = Field(0, description="Opening + Purchases - Closing")
    gross_profit: float = Field(0, description="Net revenue minus COGS")

    # Operating Expenses
    rent: float = Field(0, description="Rent/lease costs")
    transport: float = Field(0, description="Transport/delivery costs")
    utilities: float = Field(0, description="Electricity, water, phone")
    labor: float = Field(0, description="Employee/helper wages")
    licenses: float = Field(0, description="Permits and licenses")
    other_expenses: float = Field(0, description="Other operating expenses")
    total_operating_expenses: float = Field(0, description="Sum of all operating expenses")

    # Bottom Line
    operating_profit: float = Field(0, description="Gross profit minus operating expenses")
    interest_expense: float = Field(0, description="Loan interest payments")
    tax_provision: float = Field(0, description="Estimated tax")
    net_profit: float = Field(0, description="Final profit after all deductions")

    # Margins
    gross_margin_pct: float = Field(0, description="Gross profit as % of revenue")
    operating_margin_pct: float = Field(0, description="Operating profit as % of revenue")
    net_margin_pct: float = Field(0, description="Net profit as % of revenue")


class CashFlowStatement(BaseModel):
    """
    Cash Flow Statement.

    Shows cash inflows and outflows categorized by activity type.
    Banks use this to assess repayment capacity.
    """
    period_start: date
    period_end: date

    # Operating Activities
    cash_from_sales: float = Field(0, description="Cash received from customers")
    cash_from_mpesa: float = Field(0, description="M-Pesa receipts")
    cash_paid_suppliers: float = Field(0, description="Cash paid to suppliers")
    cash_paid_expenses: float = Field(0, description="Cash paid for expenses")
    cash_paid_wages: float = Field(0, description="Cash paid for wages")
    net_operating_cash: float = Field(0, description="Net cash from operations")

    # Investing Activities
    inventory_purchases: float = Field(0, description="Stock/equipment purchases")
    asset_purchases: float = Field(0, description="Fixed asset purchases")
    net_investing_cash: float = Field(0, description="Net cash from investing")

    # Financing Activities
    loans_received: float = Field(0, description="Loan proceeds received")
    loan_repayments: float = Field(0, description="Loan principal repaid")
    owner_drawings: float = Field(0, description="Owner withdrawals")
    owner_contributions: float = Field(0, description="Owner capital injected")
    net_financing_cash: float = Field(0, description="Net cash from financing")

    # Summary
    net_cash_change: float = Field(0, description="Total change in cash position")
    opening_cash: float = Field(0, description="Cash at period start")
    closing_cash: float = Field(0, description="Cash at period end")


class BalanceSheetApproximation(BaseModel):
    """
    Balance Sheet Approximation.

    Estimated from transaction data. Not a formal balance sheet,
    but gives banks a reasonable picture of business position.
    """
    as_of_date: date

    # Assets
    cash_and_mpesa: float = Field(0, description="Cash on hand + M-Pesa balance")
    inventory_value: float = Field(0, description="Current inventory at cost")
    accounts_receivable: float = Field(0, description="Outstanding credit sales")
    total_current_assets: float = Field(0, description="Sum of current assets")

    fixed_assets: float = Field(0, description="Equipment, furniture, etc.")
    total_assets: float = Field(0, description="Total business assets")

    # Liabilities
    accounts_payable: float = Field(0, description="Money owed to suppliers")
    short_term_debt: float = Field(0, description="Short-term loans")
    total_current_liabilities: float = Field(0, description="Sum of current liabilities")

    long_term_debt: float = Field(0, description="Long-term loans")
    total_liabilities: float = Field(0, description="Total business liabilities")

    # Equity
    owner_equity: float = Field(0, description="Assets minus liabilities")
    retained_earnings: float = Field(0, description="Accumulated profits")
    total_equity: float = Field(0, description="Total owner's equity")

    # Verification
    balance_check: float = Field(0, description="Should equal total_assets (A = L + E)")


# ============================================================================
# Business Metrics Schema
# ============================================================================

class BusinessPerformanceMetrics(BaseModel):
    """Key business performance metrics for institutional review."""

    # Growth
    revenue_growth_mom_pct: Optional[float] = Field(None, description="Month-over-month revenue growth %")
    revenue_growth_yoy_pct: Optional[float] = Field(None, description="Year-over-year revenue growth %")

    # Profitability
    avg_monthly_revenue: float = Field(0, description="Average monthly revenue in KES")
    avg_monthly_profit: float = Field(0, description="Average monthly profit in KES")
    profit_margin_trend: List[Dict[str, float]] = Field(
        default_factory=list,
        description="Monthly profit margin trend [{month, margin_pct}]",
    )

    # Operations
    avg_daily_transactions: float = Field(0, description="Average transactions per day")
    avg_transaction_value: float = Field(0, description="Average sale amount in KES")
    business_days_active: int = Field(0, description="Days with at least 1 transaction")
    total_days_in_period: int = Field(0, description="Total calendar days in period")
    operating_days_pct: float = Field(0, description="% of days business was active")

    # Products
    unique_products: int = Field(0, description="Number of distinct products")
    inventory_turnover: float = Field(0, description="COGS / Average inventory")
    top_product_concentration_pct: float = Field(0, description="% of revenue from top product")

    # Customers
    unique_customers: int = Field(0, description="Distinct customer identifiers")
    customer_retention_rate_pct: float = Field(0, description="% of returning customers")
    avg_customer_value: float = Field(0, description="Average revenue per customer")

    # Payment
    mpesa_pct: float = Field(0, description="% of transactions via M-Pesa")
    cash_pct: float = Field(0, description="% of transactions via cash")
    credit_pct: float = Field(0, description="% of transactions on credit")

    # Revenue stability
    coefficient_of_variation: float = Field(0, description="StdDev/Mean of daily revenue")
    revenue_stability_rating: str = Field("moderate", description="stable/moderate/volatile")


# ============================================================================
# Credit Assessment Schema
# ============================================================================

class CreditAssessment(BaseModel):
    """
    Credit assessment for bank loan applications.

    The Alama Score (300-850) is the primary metric, similar to
    a personal credit score but designed for informal businesses.
    """

    # Alama Score
    alama_score: int = Field(..., ge=300, le=850, description="Credit score 300-850")
    score_band: str = Field(..., description="excellent/good/fair/poor/very_poor")
    percentile: float = Field(0, description="Percentile rank among peers")

    # Readiness
    credit_readiness: CreditReadinessLevel
    readiness_score: float = Field(0, ge=0, le=100, description="Readiness score 0-100")

    # Loan recommendation
    recommended_loan_amount: float = Field(0, description="Recommended loan in KES")
    max_safe_loan_amount: float = Field(0, description="Maximum safe loan in KES")
    recommended_term_months: int = Field(12, description="Recommended repayment period")
    estimated_monthly_repayment: float = Field(0, description="Estimated monthly payment")
    debt_service_coverage_ratio: float = Field(0, description="Cash flow / Debt payment")

    # Risk
    risk_factors: List[str] = Field(default_factory=list)
    risk_category: RiskCategory = RiskCategory.MEDIUM
    default_probability_pct: float = Field(0, description="Estimated default probability %")

    # Score components
    activity_score: float = Field(0, description="Transaction activity score 0-100")
    stability_score: float = Field(0, description="Revenue stability score 0-100")
    growth_score: float = Field(0, description="Business growth score 0-100")
    consistency_score: float = Field(0, description="Operating consistency score 0-100")
    diversity_score: float = Field(0, description="Product diversity score 0-100")


# ============================================================================
# Verification Schema
# ============================================================================

class ReportVerification(BaseModel):
    """Report authenticity and data quality verification."""

    # Data quality
    total_transactions: int = Field(0, description="Total transactions recorded in period")
    data_quality_score: float = Field(0, ge=0, le=1, description="Data completeness/consistency 0-1")
    data_completeness_pct: float = Field(0, description="% of expected data points present")

    # Verification methods
    voice_verified: bool = Field(False, description="Voice recording verification")
    mpesa_verified: bool = Field(False, description="M-Pesa receipt cross-reference")
    inventory_verified: bool = Field(False, description="Inventory count verification")

    # Authenticity
    report_id: str = Field("", description="Unique report identifier")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = Field(None, description="Report expiry date")
    verification_url: str = Field("", description="URL for bank to verify authenticity")
    qr_code_data: str = Field("", description="QR code payload for verification")

    # Signatures
    data_hash: str = Field("", description="SHA-256 hash of report data for tamper detection")
    signature: str = Field("", description="Digital signature of report")


# ============================================================================
# Bank Report Schema
# ============================================================================

class BankReportData(BaseModel):
    """
    Complete bank-presentable business report.

    This is what a mama mboga prints and walks into Equity Bank with.
    """

    # Report metadata
    report_type: str = Field("bank", description="Report type identifier")
    report_id: str = Field("", description="Unique report ID")
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Business identification
    business_name: str = Field("", description="Business name")
    owner_name: str = Field("", description="Owner's name")
    business_type: str = Field("", description="Type of business")
    location: str = Field("", description="Business location")
    registration_number: Optional[str] = Field(None, description="Business registration number if registered")

    # Period
    period_start: date
    period_end: date
    period_months: int = Field(0, description="Number of months in period")

    # Executive Summary
    total_revenue: float = Field(0, description="Total revenue in period")
    total_expenses: float = Field(0, description="Total expenses in period")
    net_profit: float = Field(0, description="Net profit in period")
    business_health_score: float = Field(0, ge=0, le=100, description="Health score 0-100")
    health_grade: str = Field("", description="Health grade A+/A/B+/B/C/D/F")

    # Financial Statements
    income_statement: Optional[IncomeStatement] = None
    cash_flow: Optional[CashFlowStatement] = None
    balance_sheet: Optional[BalanceSheetApproximation] = None

    # Business Metrics
    metrics: Optional[BusinessPerformanceMetrics] = None

    # Credit Assessment
    credit_assessment: Optional[CreditAssessment] = None

    # Verification
    verification: Optional[ReportVerification] = None

    # Display
    language: str = Field("en", description="Report language (en/sw)")


# ============================================================================
# Government Report Schema
# ============================================================================

class TaxSummary(BaseModel):
    """Tax-related summary for KRA."""

    # Monthly revenue breakdown
    monthly_revenue: List[Dict[str, float]] = Field(
        default_factory=list,
        description="Monthly revenue [{month, revenue}]",
    )
    gross_revenue_ytd: float = Field(0, description="Year-to-date gross revenue")
    estimated_annual_revenue: float = Field(0, description="Projected annual revenue")

    # Tax estimates
    estimated_income_tax: float = Field(0, description="Estimated income tax obligation")
    estimated_vat: float = Field(0, description="Estimated VAT obligation (if applicable)")
    turnover_tax: float = Field(0, description="Turnover tax (1% for < KES 1M)")
    total_estimated_tax: float = Field(0, description="Total estimated tax obligation")

    # Compliance
    compliance_readiness: ComplianceLevel = ComplianceLevel.PARTIALLY_COMPLIANT
    compliance_score: float = Field(0, ge=0, le=100, description="Compliance readiness 0-100")
    recommended_tax_category: str = Field("", description="Suggested tax category")
    turnover_tax_eligible: bool = Field(False, description="Eligible for simplified turnover tax")

    # Missing items for compliance
    missing_items: List[str] = Field(default_factory=list)


class FormalizationReadinessData(BaseModel):
    """Business formalization assessment."""

    readiness_score: float = Field(0, ge=0, le=100, description="Formalization readiness 0-100")
    readiness_level: FormalizationReadiness = FormalizationReadiness.NOT_READY
    recommended_structure: BusinessStructure = BusinessStructure.SOLE_PROPRIETORSHIP

    # Required documents
    required_documents: List[str] = Field(default_factory=list)
    documents_ready: List[str] = Field(default_factory=list)
    documents_missing: List[str] = Field(default_factory=list)

    # Next steps
    next_steps: List[str] = Field(default_factory=list)
    estimated_cost_kes: float = Field(0, description="Estimated registration cost")


class GovernmentReportData(BaseModel):
    """
    Government (KRA) presentable report.

    For tax compliance, business registration, and
    government program applications.
    """
    report_type: str = Field("government", description="Report type identifier")
    report_id: str = Field("", description="Unique report ID")
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Business identification
    business_name: str = Field("")
    owner_name: str = Field("")
    business_type: str = Field("")
    location: str = Field("")
    id_number: Optional[str] = Field(None, description="Owner's national ID number")

    # Period
    period_start: date
    period_end: date

    # Financial Summary
    total_revenue: float = Field(0)
    total_expenses: float = Field(0)
    net_profit: float = Field(0)

    # Tax
    tax_summary: Optional[TaxSummary] = None

    # Formalization
    formalization: Optional[FormalizationReadinessData] = None

    # Transaction evidence
    total_transactions: int = Field(0)
    mpesa_transactions: int = Field(0, description="M-Pesa verified transactions")
    data_quality_score: float = Field(0)

    # Verification
    verification: Optional[ReportVerification] = None

    language: str = Field("en")


# ============================================================================
# Insurance Report Schema
# ============================================================================

class RiskProfile(BaseModel):
    """Business risk profile for insurance assessment."""

    # Business risk
    business_type: str = Field("")
    risk_category: RiskCategory = RiskCategory.MEDIUM
    risk_score: float = Field(0, ge=0, le=100, description="Risk score 0-100 (lower = safer)")

    # Revenue stability
    avg_monthly_revenue: float = Field(0)
    revenue_coefficient_of_variation: float = Field(0, description="CV of monthly revenue")
    revenue_stability: str = Field("moderate", description="stable/moderate/volatile")
    months_of_data: int = Field(0)

    # Location risk
    location: str = Field("")
    location_risk_factors: List[str] = Field(default_factory=list)

    # Claims history
    has_claims_history: bool = Field(False)
    claims_count: int = Field(0)

    # Coverage recommendation
    recommended_coverage_amount: float = Field(0, description="Recommended coverage in KES")
    recommended_premium_range: Tuple[float, float] = Field(
        default=(0, 0),
        description="Estimated premium range (min, max)",
    )
    coverage_types: List[str] = Field(
        default_factory=list,
        description="Recommended coverage types",
    )

    # Value at risk
    inventory_value_at_risk: float = Field(0, description="Current inventory value")
    monthly_revenue_at_risk: float = Field(0, description="Monthly revenue at risk")
    business_interruption_risk: str = Field("medium", description="low/medium/high")


class InsuranceReportData(BaseModel):
    """
    Insurance company presentable report.

    For business insurance applications — stock coverage,
    business interruption, liability.
    """
    report_type: str = Field("insurance", description="Report type identifier")
    report_id: str = Field("", description="Unique report ID")
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Business identification
    business_name: str = Field("")
    owner_name: str = Field("")
    business_type: str = Field("")
    location: str = Field("")
    business_age_months: int = Field(0)

    # Period
    period_start: date
    period_end: date

    # Financial summary
    total_revenue: float = Field(0)
    total_expenses: float = Field(0)
    net_profit: float = Field(0)
    avg_monthly_revenue: float = Field(0)

    # Risk Profile
    risk_profile: Optional[RiskProfile] = None

    # Business metrics
    total_transactions: int = Field(0)
    business_days_active: int = Field(0)
    unique_products: int = Field(0)
    data_quality_score: float = Field(0)

    # Verification
    verification: Optional[ReportVerification] = None

    language: str = Field("en")
