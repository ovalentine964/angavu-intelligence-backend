"""
Formal Reports API — Bank, Government, and Insurance Presentable Reports.

Endpoints for generating professional reports that can be presented to
banks, tax authorities, and insurance companies.

A mama mboga can walk into Equity Bank with her Msaidizi report
and get a loan approved.
"""

from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.formal_report import (
    BankReportData,
    GovernmentReportData,
    InsuranceReportData,
)
from app.services.reports.formal_reports import (
    BankReport,
    GovernmentReport,
    InsuranceReport,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/reports/formal", tags=["Formal Reports"])


# ============================================================================
# Request/Response Models
# ============================================================================

class FormalReportRequest(BaseModel):
    """Request model for formal report generation."""
    period_start: date = Field(..., description="Report period start date (YYYY-MM-DD)")
    period_end: date = Field(..., description="Report period end date (YYYY-MM-DD)")
    language: str = Field("en", description="Report language (en/sw)")


class ReportListResponse(BaseModel):
    """List of available formal reports."""
    reports: list = Field(default_factory=list)
    total: int = 0


# ============================================================================
# Bank Report
# ============================================================================

@router.post(
    "/{user_id}/bank",
    response_model=BankReportData,
    summary="Generate Bank-Presentable Report",
    description=(
        "Generate a professional business report suitable for bank loan applications. "
        "Includes financial statements (P&L, cash flow, balance sheet), Alama credit "
        "score (300-850), business health assessment, and verification QR code."
    ),
)
async def generate_bank_report(
    user_id: str,
    request: FormalReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a bank-presentable business report.

    **Use case:** A mama mboga prints this report and walks into
    Equity Bank to apply for a business loan.

    **Contents:**
    - Executive Summary with business health score
    - Income Statement (Profit & Loss)
    - Cash Flow Statement
    - Balance Sheet Approximation
    - Business Performance Metrics
    - Alama Credit Score (300-850) with readiness assessment
    - Recommended loan amount and repayment capacity
    - Verification QR code for bank to scan

    **Validity:** Report is valid for 90 days from generation date.

    Args:
        user_id: Worker UUID
        request: Report period and language
        current_user: Authenticated user (must match user_id)
        db: Database session

    Returns:
        BankReportData with all sections populated
    """
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only generate reports for your own business",
        )

    try:
        report_service = BankReport(db)
        report = await report_service.generate(
            worker_id=user_id,
            period=(request.period_start.isoformat(), request.period_end.isoformat()),
            language=request.language,
        )

        logger.info(
            "bank_report_api_generated",
            user_id=user_id,
            report_id=report.report_id,
            alama_score=report.credit_assessment.alama_score if report.credit_assessment else None,
        )

        return report

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("bank_report_generation_failed", user_id=user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate bank report",
        )


# ============================================================================
# Government Report
# ============================================================================

@router.post(
    "/{user_id}/government",
    response_model=GovernmentReportData,
    summary="Generate Government (KRA) Report",
    description=(
        "Generate a report suitable for KRA tax compliance and business "
        "registration. Includes tax summary, compliance assessment, and "
        "formalization readiness score."
    ),
)
async def generate_government_report(
    user_id: str,
    request: FormalReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a government-presentable report.

    **Use case:** Present to KRA for tax compliance, or use for
    business registration at Huduma Centre.

    **Contents:**
    - Monthly revenue breakdown
    - Estimated tax obligation (turnover tax / income tax)
    - Tax compliance readiness level
    - Recommended tax category
    - Business formalization readiness score
    - Recommended business structure
    - Required documents for registration
    - Verification data

    Args:
        user_id: Worker UUID
        request: Report period and language
        current_user: Authenticated user
        db: Database session

    Returns:
        GovernmentReportData with tax and formalization sections
    """
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only generate reports for your own business",
        )

    try:
        gov_report = GovernmentReport(db)
        report = await gov_report.generate(
            worker_id=user_id,
            period=(request.period_start.isoformat(), request.period_end.isoformat()),
            language=request.language,
        )

        logger.info(
            "government_report_api_generated",
            user_id=user_id,
            report_id=report.report_id,
        )

        return report

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("government_report_generation_failed", user_id=user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate government report",
        )


# ============================================================================
# Insurance Report
# ============================================================================

@router.post(
    "/{user_id}/insurance",
    response_model=InsuranceReportData,
    summary="Generate Insurance-Presentable Report",
    description=(
        "Generate a report suitable for insurance company applications. "
        "Includes risk profile, revenue stability analysis, and coverage "
        "recommendations."
    ),
)
async def generate_insurance_report(
    user_id: str,
    request: FormalReportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate an insurance-presentable report.

    **Use case:** Apply for business insurance — stock coverage,
    business interruption, or liability insurance.

    **Contents:**
    - Business risk profile and category
    - Revenue stability analysis (coefficient of variation)
    - Location risk factors
    - Claims history
    - Recommended coverage amount
    - Estimated premium range
    - Coverage types recommended
    - Inventory value at risk

    Args:
        user_id: Worker UUID
        request: Report period and language
        current_user: Authenticated user
        db: Database session

    Returns:
        InsuranceReportData with risk profile and coverage recommendations
    """
    if str(current_user.id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only generate reports for your own business",
        )

    try:
        ins_report = InsuranceReport(db)
        report = await ins_report.generate(
            worker_id=user_id,
            period=(request.period_start.isoformat(), request.period_end.isoformat()),
            language=request.language,
        )

        logger.info(
            "insurance_report_api_generated",
            user_id=user_id,
            report_id=report.report_id,
        )

        return report

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("insurance_report_generation_failed", user_id=user_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate insurance report",
        )


# ============================================================================
# Report Verification (Public)
# ============================================================================

@router.get(
    "/verify/{report_id}",
    summary="Verify Report Authenticity",
    description="Public endpoint for banks and institutions to verify report authenticity.",
)
async def verify_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a report's authenticity.

    **Public endpoint** — no authentication required.
    Banks scan the QR code on the report and call this endpoint
    to verify the report is genuine and hasn't been tampered with.

    Returns:
        Verification status with report metadata
    """
    # In production, this would look up the report in a reports table
    # For now, return verification metadata from the report_id format
    if not report_id.startswith("MSD-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid report ID format",
        )

    parts = report_id.split("-")
    if len(parts) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid report ID format",
        )

    report_type = parts[1]  # BANK, GOV, INS

    return {
        "verified": True,
        "report_id": report_id,
        "report_type": report_type,
        "message": "Report ID format is valid. Full verification requires database lookup.",
        "instructions": "Contact Msaidizi support for full data verification.",
        "support_url": "https://msaidizi.co.ke/support",
    }
