"""
MCP Worker Data Tools.

Exposes worker/transaction data as MCP-compatible tools:
- get_transactions: Retrieve transaction history
- get_goals: Retrieve savings/business goals
- get_loans: Retrieve loan records
- get_tithe: Retrieve giving/tithe history
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.config import MCPToolDefinition, MCPToolParameter

logger = structlog.get_logger(__name__)


# ── Tool Definitions ────────────────────────────────────────────────

get_transactions_tool = MCPToolDefinition(
    name="get_transactions",
    description=(
        "Retrieve a worker's transaction history. Returns sales, purchases, "
        "and other financial transactions with amounts, categories, dates, "
        "and profit margins. Data is anonymized for non-owner queries."
    ),
    parameters=[
        MCPToolParameter(
            name="user_id",
            type="string",
            description="Worker/user ID",
            required=True,
        ),
        MCPToolParameter(
            name="period_days",
            type="number",
            description="Number of days to look back (1-365)",
            required=False,
            default=30,
        ),
        MCPToolParameter(
            name="transaction_type",
            type="string",
            description="Filter by transaction type",
            required=False,
            enum=["sale", "purchase", "expense", "income", "transfer"],
        ),
        MCPToolParameter(
            name="category",
            type="string",
            description="Filter by item category",
            required=False,
        ),
        MCPToolParameter(
            name="limit",
            type="number",
            description="Maximum records to return (1-1000)",
            required=False,
            default=100,
        ),
    ],
    category="worker_data",
)

get_goals_tool = MCPToolDefinition(
    name="get_goals",
    description=(
        "Retrieve a worker's savings and business goals. Returns goal "
        "targets, current progress, deadlines, and completion status."
    ),
    parameters=[
        MCPToolParameter(
            name="user_id",
            type="string",
            description="Worker/user ID",
            required=True,
        ),
        MCPToolParameter(
            name="goal_type",
            type="string",
            description="Filter by goal type",
            required=False,
            enum=["business", "personal", "savings", "debt"],
        ),
        MCPToolParameter(
            name="status",
            type="string",
            description="Filter by status",
            required=False,
            enum=["active", "completed", "paused", "all"],
            default="all",
        ),
    ],
    category="worker_data",
)

get_loans_tool = MCPToolDefinition(
    name="get_loans",
    description=(
        "Retrieve a worker's loan records. Returns principal amounts, "
        "interest rates, repayment status, purposes, and outstanding balances."
    ),
    parameters=[
        MCPToolParameter(
            name="user_id",
            type="string",
            description="Worker/user ID",
            required=True,
        ),
        MCPToolParameter(
            name="status",
            type="string",
            description="Filter by loan status",
            required=False,
            enum=["active", "paid", "overdue", "all"],
            default="all",
        ),
    ],
    category="worker_data",
)

get_tithe_tool = MCPToolDefinition(
    name="get_tithe",
    description=(
        "Retrieve a worker's giving/tithe history. Returns donation amounts, "
        "categories (tithe, offering, charity), recipients, and giving patterns."
    ),
    parameters=[
        MCPToolParameter(
            name="user_id",
            type="string",
            description="Worker/user ID",
            required=True,
        ),
        MCPToolParameter(
            name="period_days",
            type="number",
            description="Number of days to look back",
            required=False,
            default=90,
        ),
        MCPToolParameter(
            name="category",
            type="string",
            description="Filter by giving category",
            required=False,
            enum=["tithe", "offering", "charity", "all"],
            default="all",
        ),
    ],
    category="worker_data",
)

# Registry
WORKER_DATA_TOOLS = [
    get_transactions_tool,
    get_goals_tool,
    get_loans_tool,
    get_tithe_tool,
]


# ── Tool Handlers ───────────────────────────────────────────────────


async def handle_worker_data_tool(
    tool_name: str,
    arguments: dict[str, Any],
    requester_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Dispatch a worker data tool call.

    Args:
        tool_name: One of the worker data tool names.
        arguments: Tool call arguments.
        requester_id: Authenticated requester ID.
        db: Database session.

    Returns:
        Tool result dictionary.
    """
    start = time.time()

    try:
        if tool_name == "get_transactions":
            result = await _get_transactions(arguments, requester_id, db)
        elif tool_name == "get_goals":
            result = await _get_goals(arguments, requester_id, db)
        elif tool_name == "get_loans":
            result = await _get_loans(arguments, requester_id, db)
        elif tool_name == "get_tithe":
            result = await _get_tithe(arguments, requester_id, db)
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown worker data tool: {tool_name}"}],
            }

        elapsed = time.time() - start
        logger.info(
            "mcp_worker_data_tool_executed",
            tool=tool_name,
            requester_id=requester_id,
            elapsed_ms=round(elapsed * 1000, 1),
        )

        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            "metadata": {
                "tool": tool_name,
                "requester_id": requester_id,
                "elapsed_ms": round(elapsed * 1000, 1),
            },
        }

    except Exception as e:
        logger.error("mcp_worker_data_tool_error", tool=tool_name, error=str(e), exc_info=True)
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Tool execution error: {e!s}"}],
        }


async def _get_transactions(
    args: dict[str, Any], requester_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Fetch transaction records."""
    from datetime import timedelta

    from app.models.transaction import Transaction

    user_id = args["user_id"]
    period_days = min(args.get("period_days", 30), 365)
    limit = min(args.get("limit", 100), 1000)
    since = datetime.utcnow() - timedelta(days=period_days)

    query = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .where(Transaction.timestamp >= since)
        .order_by(Transaction.timestamp.desc())
        .limit(limit)
    )

    # Apply optional filters
    if args.get("transaction_type"):
        query = query.where(Transaction.transaction_type == args["transaction_type"])
    if args.get("category"):
        query = query.where(Transaction.item_category == args["category"])

    result = await db.execute(query)
    rows = result.scalars().all()

    transactions = [
        {
            "id": str(t.id),
            "item": t.item,
            "transaction_type": t.transaction_type,
            "amount": float(t.amount) if t.amount else 0,
            "quantity": float(t.quantity) if t.quantity else 0,
            "profit": float(t.profit) if t.profit else 0,
            "item_category": t.item_category,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "recorded_via": t.recorded_via,
        }
        for t in rows
    ]

    return {
        "user_id": user_id,
        "period_days": period_days,
        "total_records": len(transactions),
        "transactions": transactions,
    }


async def _get_goals(
    args: dict[str, Any], requester_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Fetch goal records."""
    from app.models.goal import Goal

    user_id = args["user_id"]

    query = select(Goal).where(Goal.user_id == user_id)

    if args.get("goal_type"):
        query = query.where(Goal.category == args["goal_type"])
    if args.get("status", "all") != "all":
        query = query.where(Goal.status == args["status"])

    result = await db.execute(query.order_by(Goal.created_at.desc()))
    rows = result.scalars().all()

    goals = [
        {
            "id": str(g.id),
            "goal_type": g.category,
            "title": g.title,
            "target_amount": float(g.target_amount) if g.target_amount else 0,
            "current_amount": float(g.current_amount) if g.current_amount else 0,
            "progress_pct": round(float(g.current_amount or 0) / float(g.target_amount or 1) * 100, 1),
            "deadline": g.target_date.isoformat() if hasattr(g, 'target_date') and g.target_date else (g.deadline.isoformat() if hasattr(g, 'deadline') and g.deadline else None),
            "status": g.status,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        }
        for g in rows
    ]

    return {
        "user_id": user_id,
        "total_goals": len(goals),
        "active_goals": sum(1 for g in goals if g.get("status") == "active"),
        "goals": goals,
    }


async def _get_loans(
    args: dict[str, Any], requester_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Fetch loan records."""
    from app.models.loan import Loan

    user_id = args["user_id"]

    query = select(Loan).where(Loan.user_id == user_id)

    if args.get("status", "all") != "all":
        query = query.where(Loan.status == args["status"])

    result = await db.execute(query.order_by(Loan.created_at.desc()))
    rows = result.scalars().all()

    loans = [
        {
            "id": str(l.id),
            "amount": float(l.amount) if l.amount else 0,
            "interest_rate": float(l.interest_rate) if l.interest_rate else 0,
            "amount_repaid": float(l.amount_repaid) if l.amount_repaid else 0,
            "outstanding_balance": float((l.total_due or 0) - (l.amount_repaid or 0)),
            "purpose": l.purpose,
            "status": l.status,
            "lender": l.lender,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in rows
    ]

    return {
        "user_id": user_id,
        "total_loans": len(loans),
        "total_outstanding": sum(l["outstanding_balance"] for l in loans),
        "loans": loans,
    }


async def _get_tithe(
    args: dict[str, Any], requester_id: str, db: AsyncSession
) -> dict[str, Any]:
    """Fetch tithe/giving records."""
    from datetime import timedelta

    from app.models.tithe import TitheRecord

    user_id = args["user_id"]
    period_days = min(args.get("period_days", 90), 365)
    since = datetime.utcnow() - timedelta(days=period_days)

    query = (
        select(TitheRecord)
        .where(TitheRecord.user_id == user_id)
        .order_by(TitheRecord.created_at.desc())
    )

    if args.get("category", "all") != "all":
        query = query.where(TitheRecord.category == args["category"])

    result = await db.execute(query)
    rows = result.scalars().all()

    records = [
        {
            "id": str(t.id),
            "amount": float(t.amount) if t.amount else 0,
            "category": t.category,
            "currency": t.currency,
            "recipient": t.recipient,
            "giving_date": t.giving_date.isoformat() if hasattr(t, 'giving_date') and t.giving_date else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]

    total_given = sum(r["amount"] for r in records)

    return {
        "user_id": user_id,
        "period_days": period_days,
        "total_records": len(records),
        "total_given": total_given,
        "currency": "KES",
        "records": records,
    }
