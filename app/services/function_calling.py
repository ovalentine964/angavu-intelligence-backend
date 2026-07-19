"""
Financial function calling for Gemini integration.
Backed by SQLAlchemy (works with both SQLite and PostgreSQL).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select

from app.models.transaction import Transaction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Tool Definitions (Gemini function declarations)
# ════════════════════════════════════════════════════════════════════

FINANCIAL_TOOLS = [
    {
        "name": "get_transaction_summary",
        "description": "Get summary of transactions for a time period, optionally filtered by category.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period: today, yesterday, week, month, year",
                    "enum": ["today", "yesterday", "week", "month", "year"],
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter: stock, sales, expenses, transport, food, rent",
                },
            },
            "required": ["period"],
        },
    },
    {
        "name": "analyze_cash_flow",
        "description": "Analyze income vs expenses for a date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "compare_periods",
        "description": "Compare financial metrics between two time periods.",
        "parameters": {
            "type": "object",
            "properties": {
                "current_start": {
                    "type": "string",
                    "description": "Current period start (YYYY-MM-DD)",
                },
                "current_end": {"type": "string", "description": "Current period end (YYYY-MM-DD)"},
                "previous_start": {
                    "type": "string",
                    "description": "Previous period start (YYYY-MM-DD)",
                },
                "previous_end": {
                    "type": "string",
                    "description": "Previous period end (YYYY-MM-DD)",
                },
            },
            "required": ["current_start", "current_end", "previous_start", "previous_end"],
        },
    },
    {
        "name": "predict_expenses",
        "description": "Predict upcoming expenses based on historical patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "horizon_days": {
                    "type": "integer",
                    "description": "Prediction horizon in days (7, 14, 30)",
                },
            },
            "required": ["horizon_days"],
        },
    },
    {
        "name": "check_credit_readiness",
        "description": "Assess financial readiness for credit or loan based on transaction history.",
        "parameters": {"type": "object", "properties": {}},
    },
]


# ════════════════════════════════════════════════════════════════════
# Function Executor (SQLAlchemy-backed)
# ════════════════════════════════════════════════════════════════════


class FunctionExecutor:
    """
    Executes financial functions backed by SQLAlchemy.

    Works with both SQLite (on-device/dev) and PostgreSQL (production).
    Each function queries real transaction data and returns
    structured JSON that Gemini can reason over.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def execute(self, function_name: str, args: dict[str, Any], user_id: str = "") -> str:
        """Execute a financial function and return JSON result."""
        try:
            result = await self._dispatch(function_name, args, user_id)
            logger.info("function_call.success", function=function_name)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.error("function_call.error", function=function_name, error=str(e))
            return json.dumps({"error": str(e), "function": function_name})

    async def _dispatch(
        self, function_name: str, args: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        """Route function call to handler."""
        handlers = {
            "get_transaction_summary": self._get_transaction_summary,
            "analyze_cash_flow": self._analyze_cash_flow,
            "compare_periods": self._compare_periods,
            "predict_expenses": self._predict_expenses,
            "check_credit_readiness": self._check_credit_readiness,
        }
        handler = handlers.get(function_name)
        if not handler:
            return {"error": f"Unknown function: {function_name}"}
        return await handler(user_id=user_id, **args)

    def _period_to_dates(self, period: str) -> tuple[datetime, datetime]:
        """Convert period string to start/end dates."""
        end_date = datetime.now()
        start_date = {
            "today": end_date.replace(hour=0, minute=0, second=0, microsecond=0),
            "yesterday": (end_date - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
            "week": end_date - timedelta(days=7),
            "month": end_date - timedelta(days=30),
            "year": end_date - timedelta(days=365),
        }.get(period, end_date - timedelta(days=30))
        return start_date, end_date

    async def _get_transaction_summary(
        self, period: str, user_id: str, category: str | None = None
    ) -> dict[str, Any]:
        """Get transaction summary for a period."""
        start_date, end_date = self._period_to_dates(period)

        # Base query
        query = (
            select(
                Transaction.transaction_type,
                func.sum(Transaction.amount).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.timestamp >= start_date,
                Transaction.timestamp <= end_date,
            )
            .group_by(Transaction.transaction_type)
        )

        if category:
            query = query.where(Transaction.item_category == category)

        result = await self._db.execute(query)
        rows = result.all()

        income = sum(r.total for r in rows if r.transaction_type == "SALE")
        expenses = sum(r.total for r in rows if r.transaction_type in ("PURCHASE", "EXPENSE"))
        total_count = sum(r.count for r in rows)

        return {
            "period": period,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "total_income": float(income),
            "total_expenses": float(expenses),
            "net": float(income - expenses),
            "transaction_count": total_count,
        }

    async def _analyze_cash_flow(
        self, start_date: str, end_date: str, user_id: str
    ) -> dict[str, Any]:
        """Analyze income vs expenses."""
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        query = (
            select(
                Transaction.transaction_type,
                Transaction.item_category,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.timestamp >= start,
                Transaction.timestamp <= end,
            )
            .group_by(Transaction.transaction_type, Transaction.item_category)
        )

        result = await self._db.execute(query)
        rows = result.all()

        income_sources = {}
        expense_categories = {}
        total_income = 0.0
        total_expenses = 0.0

        for r in rows:
            if r.transaction_type == "SALE":
                income_sources[r.item_category or "other"] = float(r.total)
                total_income += float(r.total)
            else:
                expense_categories[r.item_category or "other"] = float(r.total)
                total_expenses += float(r.total)

        days = max((end - start).days, 1)

        return {
            "start": start_date,
            "end": end_date,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_cash_flow": total_income - total_expenses,
            "income_sources": income_sources,
            "expense_categories": expense_categories,
            "daily_average_income": round(total_income / days, 2),
            "daily_average_expenses": round(total_expenses / days, 2),
        }

    async def _compare_periods(
        self,
        current_start: str,
        current_end: str,
        previous_start: str,
        previous_end: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Compare two periods."""
        cur = await self._analyze_cash_flow(current_start, current_end, user_id)
        prev = await self._analyze_cash_flow(previous_start, previous_end, user_id)

        income_change = (
            ((cur["total_income"] - prev["total_income"]) / prev["total_income"] * 100)
            if prev["total_income"] > 0
            else 0
        )
        expense_change = (
            ((cur["total_expenses"] - prev["total_expenses"]) / prev["total_expenses"] * 100)
            if prev["total_expenses"] > 0
            else 0
        )

        return {
            "current": {
                "start": current_start,
                "end": current_end,
                "income": cur["total_income"],
                "expenses": cur["total_expenses"],
            },
            "previous": {
                "start": previous_start,
                "end": previous_end,
                "income": prev["total_income"],
                "expenses": prev["total_expenses"],
            },
            "income_change_pct": round(income_change, 1),
            "expense_change_pct": round(expense_change, 1),
            "net_change_pct": round(income_change - expense_change, 1),
        }

    async def _predict_expenses(self, horizon_days: int, user_id: str) -> dict[str, Any]:
        """Predict upcoming expenses based on historical patterns."""
        # Simple average-based prediction
        end = datetime.now()
        start = end - timedelta(days=90)

        query = (
            select(
                Transaction.item_category,
                func.sum(Transaction.amount).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.transaction_type.in_(["PURCHASE", "EXPENSE"]),
                Transaction.timestamp >= start,
                Transaction.timestamp <= end,
            )
            .group_by(Transaction.item_category)
        )

        result = await self._db.execute(query)
        rows = result.all()

        daily_by_cat = {}
        for r in rows:
            daily_by_cat[r.item_category or "other"] = round(float(r.total) / 90, 2)

        predicted = {cat: round(daily * horizon_days, 2) for cat, daily in daily_by_cat.items()}
        total = sum(predicted.values())

        return {
            "horizon_days": horizon_days,
            "predicted_total": round(total, 2),
            "predicted_by_category": predicted,
            "confidence": "medium" if len(rows) > 5 else "low",
            "based_on_days_of_history": 90,
        }

    async def _check_credit_readiness(self, user_id: str) -> dict[str, Any]:
        """Assess credit readiness based on transaction history."""
        end = datetime.now()
        start = end - timedelta(days=90)

        query = (
            select(
                Transaction.transaction_type,
                func.sum(Transaction.amount).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.timestamp >= start,
                Transaction.timestamp <= end,
            )
            .group_by(Transaction.transaction_type)
        )

        result = await self._db.execute(query)
        rows = result.all()

        income = sum(float(r.total) for r in rows if r.transaction_type == "SALE")
        expenses = sum(
            float(r.total) for r in rows if r.transaction_type in ("PURCHASE", "EXPENSE")
        )
        total_count = sum(r.count for r in rows)

        monthly_income = income / 3
        savings_rate = ((income - expenses) / income * 100) if income > 0 else 0
        expense_ratio = (expenses / income * 100) if income > 0 else 100

        # Simple readiness assessment
        if total_count < 30:
            readiness = "insufficient_data"
            recommendations = ["Record more transactions to build your financial profile"]
        elif savings_rate > 20:
            readiness = "ready"
            recommendations = [
                "Strong financial position. Consider applying for a small business loan."
            ]
        elif savings_rate > 0:
            readiness = "almost_ready"
            recommendations = [
                "Reduce expenses to improve your savings rate",
                "Track all transactions consistently",
            ]
        else:
            readiness = "not_ready"
            recommendations = [
                "Focus on increasing sales",
                "Reduce non-essential expenses",
                "Build a consistent income stream",
            ]

        return {
            "bfs_score": min(100, max(0, int(savings_rate + 30))),
            "readiness_level": readiness,
            "monthly_income_avg": round(monthly_income, 2),
            "income_stability": min(100, max(0, int(total_count / 3))),
            "expense_ratio": round(expense_ratio, 1),
            "savings_rate": round(savings_rate, 1),
            "recommendations": recommendations,
        }
