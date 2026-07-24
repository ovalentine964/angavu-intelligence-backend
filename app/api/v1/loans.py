"""
Loan Manager API — v1 Endpoints.

Dedicated loan management endpoints for Africa's informal economy workers.

Endpoints:
- POST /loans/record          — Record a new loan with purpose verification
- POST /loans/{id}/repayment  — Record a repayment with behavioral nudges
- GET  /loans/{id}            — Get loan details with ROI and risk
- GET  /loans/{id}/risk       — Analyze default risk (Polars-based)
- GET  /loans/{id}/purpose    — Verify loan purpose alignment
- GET  /loans/{id}/schedule   — Generate repayment schedule

Design principles:
- Async/await throughout
- Behavioral economics nudges in every response
- Swahili + English bilingual responses
- Alama Score integration
- Purpose verification (research: <8% default with verification)
"""

import datetime as _dt
from datetime import date
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services import loan_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/loans", tags=["Loan Manager"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request/Response Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class LoanRecordRequest(BaseModel):
    """Request to record a new loan."""

    user_id: UUID = Field(..., description="Worker's UUID")
    amount: float = Field(..., gt=0, description="Loan principal amount")
    purpose: str = Field(
        ...,
        description="Purpose category: Business, Personal, Emergency, Education",
        examples=["Business"],
    )
    lender: str = Field(
        ...,
        description="Loan source: M-Shwari, KCB M-Pesa, chama, bank, manual",
        examples=["M-Shwari"],
    )
    interest_rate: float = Field(
        ..., ge=0,
        description="Interest rate as decimal (0.15 = 15%)",
        examples=[0.15],
    )
    start_date: _dt.date = Field(..., description="Loan disbursement date")
    end_date: _dt.date = Field(..., description="Expected full repayment date")
    purpose_subcategory: str | None = Field(
        None,
        description="Subcategory: stock, equipment, medical, school_fees, etc.",
    )
    purpose_description: str | None = Field(
        None,
        description="Free-text description of intended use",
    )
    repayment_frequency: str = Field(
        "weekly",
        description="daily, weekly, biweekly, monthly",
        examples=["weekly"],
    )
    commitment_text: str | None = Field(
        None,
        description="Written commitment pledge (behavioral nudge)",
        examples=["Nitalipa KSh 500 kila Jumatatu"],
    )
    accountability_partner_id: UUID | None = Field(
        None,
        description="Optional accountability partner UUID",
    )
    currency: str = Field("KES", max_length=3, description="ISO currency code")


class RepaymentRequest(BaseModel):
    """Request to record a repayment."""

    amount: float = Field(..., gt=0, description="Repayment amount")
    repayment_date: _dt.date = Field(..., description="Date of repayment")
    method: str = Field(
        "manual",
        description="Payment method: manual, mpesa, cash, auto_set_aside, chama",
    )
    notes: str | None = Field(None, description="Optional notes")
    nudge_type: str | None = Field(
        None,
        description="Nudge that prompted this repayment",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# POST /loans/record — Record a new loan
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/record")
async def record_loan(
    request: LoanRecordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a new loan with purpose verification and behavioral nudges.

    Automatically:
    - Calculates total due and suggested payments
    - Creates purpose verification record
    - Runs initial default risk assessment
    - Prompts commitment device if not provided

    Returns loan details, schedule, risk assessment, and Swahili/English messages.
    """
    try:
        result = await loan_service.record_loan(
            db=db,
            user_id=request.user_id,
            amount=request.amount,
            purpose=request.purpose,
            lender=request.lender,
            interest_rate=request.interest_rate,
            start_date=request.start_date,
            end_date=request.end_date,
            purpose_subcategory=request.purpose_subcategory,
            purpose_description=request.purpose_description,
            repayment_frequency=request.repayment_frequency,
            commitment_text=request.commitment_text,
            accountability_partner_id=request.accountability_partner_id,
            currency=request.currency,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("loan_record_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record loan")


# ═══════════════════════════════════════════════════════════════════════════════
# POST /loans/{loan_id}/repayment — Record repayment
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{loan_id}/repayment")
async def record_repayment(
    loan_id: UUID,
    request: RepaymentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a repayment toward a loan.

    Updates streak tracking, detects completion, generates behavioral
    nudges (streak protection, almost-done, social proof), and
    calculates Alama Score impact.
    """
    try:
        result = await loan_service.record_repayment(
            db=db,
            loan_id=loan_id,
            amount=request.amount,
            date=request.repayment_date,
            method=request.method,
            notes=request.notes,
            nudge_type=request.nudge_type,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("repayment_record_failed", loan_id=str(loan_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record repayment")


# ═══════════════════════════════════════════════════════════════════════════════
# GET /loans/{loan_id} — Get loan details
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{loan_id}")
async def get_loan_details(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive loan details including ROI, risk, and behavioral data.

    Returns financial status, ROI tracking (Business loans), risk assessment,
    repayment streak/history, behavioral nudges, and voice summaries.
    """
    try:
        result = await loan_service.get_loan_status(
            db=db,
            loan_id=loan_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("loan_status_failed", loan_id=str(loan_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get loan details")


# ═══════════════════════════════════════════════════════════════════════════════
# GET /loans/{loan_id}/risk — Get default risk
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{loan_id}/risk")
async def get_default_risk(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze default risk for a loan using Polars-based analysis.

    Uses Polars DataFrames for portfolio-level risk aggregation,
    repayment pattern analysis, and behavioral feature extraction.

    Returns risk score, level, Alama Score impact, and recommended actions.
    """
    try:
        # Get the loan to find user_id
        from sqlalchemy import select

        from app.models.loan import Loan

        result = await db.execute(select(Loan).where(Loan.id == loan_id))
        loan = result.scalar_one_or_none()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        risk_result = await loan_service.get_default_risk(
            db=db,
            user_id=loan.user_id,
        )
        return risk_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("risk_analysis_failed", loan_id=str(loan_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to analyze default risk")


# ═══════════════════════════════════════════════════════════════════════════════
# GET /loans/{loan_id}/purpose — Purpose verification
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{loan_id}/purpose")
async def get_purpose_verification(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify loan purpose alignment and track ROI.

    Research shows default rate drops to <8% with purpose verification.
    Returns verification status, ROI tracking (Business loans),
    drift detection, and accountability nudges.
    """
    try:
        result = await loan_service.get_purpose_verification(
            db=db,
            loan_id=loan_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("purpose_verification_failed", loan_id=str(loan_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to verify loan purpose")


# ═══════════════════════════════════════════════════════════════════════════════
# GET /loans/{loan_id}/schedule — Repayment schedule
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{loan_id}/schedule")
async def get_repayment_schedule(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate repayment schedule with multiple options.

    Provides daily, weekly, biweekly, and monthly payment plans
    with behavioral nudge context, loss aversion framing,
    and end-effect motivation for each option.
    """
    try:
        result = await loan_service.get_repayment_schedule(
            db=db,
            loan_id=loan_id,
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("schedule_failed", loan_id=str(loan_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate repayment schedule")
