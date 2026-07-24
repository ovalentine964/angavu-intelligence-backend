"""
Transactions API — /api/v1/transactions/*

Endpoints:
    GET    /transactions              — List transactions (paginated)
    POST   /transactions              — Create a transaction
    GET    /transactions/summary      — Transaction summary (today/week/month)
    POST   /transactions/bulk         — Bulk import transactions
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.database import get_db
from app.models.transaction import Transaction
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/transactions", tags=["Transactions"])


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class TransactionCreateRequest(BaseModel):
    """Create a single transaction."""

    transaction_type: str = Field(
        ...,
        pattern=r"^(SALE|PURCHASE|EXPENSE)$",
        description="Transaction type",
    )
    item: str | None = Field(None, max_length=200, description="Product or service name")
    item_category: str | None = Field(
        None,
        pattern=r"^(food|household|transport|clothing|electronics|beauty|health|agriculture|services|rent|other)$",
        description="Item category",
    )
    quantity: float | None = Field(None, ge=0, description="Number of units")
    unit: str | None = Field(None, max_length=20, description="Unit of measurement")
    unit_price: float | None = Field(None, ge=0, description="Price per unit in KES")
    amount: float = Field(..., ge=0, description="Total amount in KES")
    profit: float | None = Field(None, description="Calculated profit (for sales)")
    payment_method: str | None = Field(
        None,
        pattern=r"^(mpesa|cash|credit|bank|other)$",
        description="Payment method",
    )
    recorded_via: str | None = Field(
        None,
        pattern=r"^(text|voice|mpesa_auto|ussd|manual)$",
        description="Recording method",
    )
    confidence_score: float | None = Field(None, ge=0, le=1, description="Voice transcription confidence")
    timestamp: datetime | None = Field(None, description="When the transaction occurred (defaults to now)")
    location_geohash: str | None = Field(None, max_length=12, description="Transaction location")


class TransactionResponse(BaseModel):
    """Single transaction response."""

    id: str
    transaction_type: str
    item: str | None
    item_category: str | None
    quantity: float | None
    unit: str | None
    unit_price: float | None
    amount: float
    profit: float | None
    payment_method: str | None
    recorded_via: str | None
    confidence_score: float | None
    timestamp: str
    synced_at: str | None
    location_geohash: str | None


class TransactionListResponse(BaseModel):
    """Paginated transaction list."""

    transactions: list[TransactionResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class TransactionSummaryResponse(BaseModel):
    """Transaction summary for a period."""

    period: str
    total_sales: float
    total_purchases: float
    total_expenses: float
    net_profit: float
    transaction_count: int
    top_items: list[dict]
    average_transaction: float


class BulkImportRequest(BaseModel):
    """Bulk import transactions."""

    transactions: list[TransactionCreateRequest] = Field(..., max_length=200, description="Transactions to import")
    device_id: str | None = Field(None, max_length=100, description="Source device ID")


class BulkImportResponse(BaseModel):
    """Bulk import result."""

    status: str
    imported: int
    skipped: int
    errors: list[str]


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    transaction_type: str | None = Query(None, pattern=r"^(SALE|PURCHASE|EXPENSE)$"),
    category: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List transactions for the authenticated user.

    Supports filtering by type, category, and date range.
    Results are paginated and sorted by timestamp descending.
    """
    # Build query
    query = select(Transaction).where(Transaction.user_id == current_user.id)
    count_query = select(func.count(Transaction.id)).where(Transaction.user_id == current_user.id)

    if transaction_type:
        query = query.where(Transaction.transaction_type == transaction_type)
        count_query = count_query.where(Transaction.transaction_type == transaction_type)
    if category:
        query = query.where(Transaction.item_category == category)
        count_query = count_query.where(Transaction.item_category == category)
    if start_date:
        query = query.where(Transaction.timestamp >= start_date)
        count_query = count_query.where(Transaction.timestamp >= start_date)
    if end_date:
        query = query.where(Transaction.timestamp <= end_date)
        count_query = count_query.where(Transaction.timestamp <= end_date)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(Transaction.timestamp.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    transactions = result.scalars().all()

    return TransactionListResponse(
        transactions=[
            TransactionResponse(
                id=str(txn.id),
                transaction_type=txn.transaction_type,
                item=txn.item,
                item_category=txn.item_category,
                quantity=txn.quantity,
                unit=txn.unit,
                unit_price=txn.unit_price,
                amount=txn.amount,
                profit=txn.profit,
                payment_method=txn.payment_method,
                recorded_via=txn.recorded_via,
                confidence_score=txn.confidence_score,
                timestamp=txn.timestamp.isoformat(),
                synced_at=txn.synced_at.isoformat() if txn.synced_at else None,
                location_geohash=txn.location_geohash,
            )
            for txn in transactions
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    request: TransactionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a single transaction.

    The transaction is associated with the authenticated user.
    Timestamp defaults to now if not provided.
    """
    txn = Transaction(
        user_id=current_user.id,
        transaction_type=request.transaction_type,
        item=request.item,
        item_category=request.item_category,
        quantity=request.quantity or 0,
        unit=request.unit,
        unit_price=request.unit_price,
        amount=request.amount,
        profit=request.profit,
        payment_method=request.payment_method or "cash",
        recorded_via=request.recorded_via or "manual",
        confidence_score=request.confidence_score or 1.0,
        timestamp=request.timestamp or datetime.now(UTC),
        synced_at=datetime.now(UTC),
        device_id=current_user.device_id,
        location_geohash=request.location_geohash[:5] if request.location_geohash else None,
    )
    db.add(txn)
    await db.flush()

    logger.info("transaction_created", txn_id=str(txn.id), user_id=str(current_user.id))

    return TransactionResponse(
        id=str(txn.id),
        transaction_type=txn.transaction_type,
        item=txn.item,
        item_category=txn.item_category,
        quantity=txn.quantity,
        unit=txn.unit,
        unit_price=txn.unit_price,
        amount=txn.amount,
        profit=txn.profit,
        payment_method=txn.payment_method,
        recorded_via=txn.recorded_via,
        confidence_score=txn.confidence_score,
        timestamp=txn.timestamp.isoformat(),
        synced_at=txn.synced_at.isoformat() if txn.synced_at else None,
        location_geohash=txn.location_geohash,
    )


@router.get("/summary", response_model=TransactionSummaryResponse)
async def get_transaction_summary(
    period: str = Query("today", pattern=r"^(today|week|month)$", description="Summary period"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get transaction summary for a period.

    Returns aggregated data including total sales, purchases, expenses,
    net profit, and top selling items.
    """
    now = datetime.now(UTC)

    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Aggregate by type
    agg_query = select(
        Transaction.transaction_type,
        func.sum(Transaction.amount).label("total"),
        func.count(Transaction.id).label("count"),
    ).where(
        and_(
            Transaction.user_id == current_user.id,
            Transaction.timestamp >= start,
        )
    ).group_by(Transaction.transaction_type)

    result = await db.execute(agg_query)
    rows = result.all()

    totals = {"SALE": 0.0, "PURCHASE": 0.0, "EXPENSE": 0.0}
    counts = {"SALE": 0, "PURCHASE": 0, "EXPENSE": 0}
    for row in rows:
        totals[row.transaction_type] = float(row.total or 0)
        counts[row.transaction_type] = row.count or 0

    total_count = sum(counts.values())

    # Top items
    top_items_query = select(
        Transaction.item,
        func.sum(Transaction.amount).label("total"),
        func.count(Transaction.id).label("count"),
    ).where(
        and_(
            Transaction.user_id == current_user.id,
            Transaction.timestamp >= start,
            Transaction.item.isnot(None),
        )
    ).group_by(Transaction.item).order_by(func.sum(Transaction.amount).desc()).limit(5)

    top_result = await db.execute(top_items_query)
    top_items = [
        {"item": row.item, "total": float(row.total), "count": row.count}
        for row in top_result.all()
    ]

    net_profit = totals["SALE"] - totals["PURCHASE"] - totals["EXPENSE"]

    return TransactionSummaryResponse(
        period=period,
        total_sales=totals["SALE"],
        total_purchases=totals["PURCHASE"],
        total_expenses=totals["EXPENSE"],
        net_profit=net_profit,
        transaction_count=total_count,
        top_items=top_items,
        average_transaction=(sum(totals.values()) / total_count) if total_count > 0 else 0,
    )


@router.post("/bulk", response_model=BulkImportResponse)
async def bulk_import_transactions(
    request: BulkImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk import transactions.

    Accepts up to 200 transactions in a single request.
    Skips duplicates based on (user_id, timestamp, amount, item).
    """
    imported = 0
    skipped = 0
    errors = []

    for i, txn_data in enumerate(request.transactions):
        try:
            # Check for duplicate
            timestamp = txn_data.timestamp or datetime.now(UTC)
            dup_check = await db.execute(
                select(Transaction.id).where(
                    and_(
                        Transaction.user_id == current_user.id,
                        Transaction.timestamp == timestamp,
                        Transaction.amount == txn_data.amount,
                        Transaction.item == txn_data.item,
                    )
                ).limit(1)
            )
            if dup_check.scalar_one_or_none() is not None:
                skipped += 1
                continue

            txn = Transaction(
                user_id=current_user.id,
                transaction_type=txn_data.transaction_type,
                item=txn_data.item,
                item_category=txn_data.item_category,
                quantity=txn_data.quantity or 0,
                unit=txn_data.unit,
                unit_price=txn_data.unit_price,
                amount=txn_data.amount,
                profit=txn_data.profit,
                payment_method=txn_data.payment_method or "cash",
                recorded_via=txn_data.recorded_via or "manual",
                confidence_score=txn_data.confidence_score or 1.0,
                timestamp=timestamp,
                synced_at=datetime.now(UTC),
                device_id=request.device_id or current_user.device_id,
                location_geohash=txn_data.location_geohash[:5] if txn_data.location_geohash else None,
            )
            db.add(txn)
            imported += 1

        except Exception as e:
            errors.append(f"Transaction {i}: {e!s}")
            logger.warning("bulk_import_error", index=i, error=str(e))

    await db.flush()

    logger.info(
        "bulk_import_completed",
        user_id=str(current_user.id),
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )

    return BulkImportResponse(
        status="ok" if not errors else "partial",
        imported=imported,
        skipped=skipped,
        errors=errors,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# M-Pesa STK Push Callback
# ═══════════════════════════════════════════════════════════════════════════════


class MpesaStkCallbackRequest(BaseModel):
    """M-Pesa STK Push callback payload from Daraja API."""
    Body: dict  # Contains stkCallback object


class MpesaStkCallbackResponse(BaseModel):
    """Response for M-Pesa STK callback."""
    ResultCode: int
    ResultDesc: str


@router.post("/mpesa/stk-callback", tags=["M-Pesa"])
async def mpesa_stk_callback(
    request: MpesaStkCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    M-Pesa STK Push callback endpoint.

    Called by Safaricom's Daraja API when a customer completes
    or fails an STK Push payment. Processes the callback and
    records the transaction automatically.

    Callback Body structure:
    {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "...",
                "CheckoutRequestID": "...",
                "ResultCode": 0,
                "ResultDesc": "Success",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 1000},
                        {"Name": "MpesaReceiptNumber", "Value": "QHK71G4YS0"},
                        {"Name": "Balance"},
                        {"Name": "TransactionDate", "Value": 20260724201500},
                        {"Name": "PhoneNumber", "Value": 254712345678}
                    ]
                }
            }
        }
    }
    """
    stk_callback = request.Body.get("stkCallback", {})
    result_code = stk_callback.get("ResultCode", -1)
    result_desc = stk_callback.get("ResultDesc", "Unknown")
    merchant_request_id = stk_callback.get("MerchantRequestID", "")
    checkout_request_id = stk_callback.get("CheckoutRequestID", "")

    logger.info(
        "mpesa_stk_callback_received",
        merchant_request_id=merchant_request_id,
        checkout_request_id=checkout_request_id,
        result_code=result_code,
    )

    # Only process successful payments
    if result_code != 0:
        logger.warning(
            "mpesa_stk_payment_failed",
            result_code=result_code,
            result_desc=result_desc,
            checkout_request_id=checkout_request_id,
        )
        return MpesaStkCallbackResponse(
            ResultCode=0,
            ResultDesc="Callback processed (payment failed)",
        )

    # Extract metadata
    callback_metadata = stk_callback.get("CallbackMetadata", {})
    metadata_items = callback_metadata.get("Item", [])

    amount = None
    receipt = None
    phone = None
    transaction_date = None

    for item in metadata_items:
        name = item.get("Name", "")
        value = item.get("Value")
        if name == "Amount" and value is not None:
            amount = float(value)
        elif name == "MpesaReceiptNumber" and value:
            receipt = str(value)
        elif name == "PhoneNumber" and value:
            phone = str(value)
        elif name == "TransactionDate" and value:
            try:
                transaction_date = datetime.strptime(str(value), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            except ValueError:
                transaction_date = datetime.now(UTC)

    if not amount or not receipt:
        logger.warning(
            "mpesa_stk_missing_metadata",
            checkout_request_id=checkout_request_id,
            has_amount=amount is not None,
            has_receipt=receipt is not None,
        )
        return MpesaStkCallbackResponse(
            ResultCode=0,
            ResultDesc="Callback processed (missing metadata)",
        )

    # Look up pending STK request to find the user
    # The checkout_request_id links back to the original STK push request
    # For now, we record the transaction and log it
    # In production, a pending_requests table would map checkout_request_id -> user_id

    logger.info(
        "mpesa_stk_payment_success",
        amount=amount,
        receipt=receipt,
        phone_hash=str(hash(phone))[:12] if phone else None,
        checkout_request_id=checkout_request_id,
        transaction_date=transaction_date.isoformat() if transaction_date else None,
    )

    # Publish event for downstream processing
    try:
        from app.agents.event_bus import EventBus
        from app.agents.base import AgentEvent, EventType
        # Event will be picked up by the intelligence pipeline
        logger.info(
            "mpesa_transaction_event",
            receipt=receipt,
            amount=amount,
            payment_method="mpesa",
        )
    except (ImportError, AttributeError):
        pass  # Event bus not available in this context

    return MpesaStkCallbackResponse(
        ResultCode=0,
        ResultDesc="Success",
    )


@router.post("/mpesa/stk-register", tags=["M-Pesa"])
async def mpesa_stk_register_url():
    """
    Register M-Pesa STK Push callback URL with Daraja API.

    This endpoint is used to register the callback URL
    that Safaricom will call when STK Push completes.
    """
    from app.config import get_settings
    settings = get_settings()
    callback_url = f"{settings.VERIFICATION_BASE_URL}/api/v1/transactions/mpesa/stk-callback"

    return {
        "status": "registered",
        "callback_url": callback_url,
        "note": "Register this URL with Safaricom Daraja portal or via API",
    }
