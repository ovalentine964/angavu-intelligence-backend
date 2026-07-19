"""
Operations Agent — Autonomous invoicing, expense tracking, and finance.

Manages the financial operations of Angavu Intelligence:
    - Invoice generation and tracking
    - Expense categorization and reporting
    - Revenue recognition
    - Cash flow monitoring
    - Financial reporting for the founder
    - Budget alerts and cost optimization

Finance rules:
    - All invoices over $500 require founder approval
    - Monthly financial summary by 1st of each month
    - Expense alerts when budget utilization > 80%
    - Cash flow projection updated weekly
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.agents.base import AgentDecision, AgentResult, EventType
from app.autonomous.agents.base import AutonomousAgent
from app.autonomous.config import AgentConfig

logger = structlog.get_logger(__name__)


class OperationsAgent(AutonomousAgent):
    """
    Autonomous operations agent for Angavu Intelligence / Msaidizi.

    Handles the full operations lifecycle:
    1. Invoice Management — generate, send, track, follow up
    2. Expense Tracking — categorize, report, alert on overruns
    3. Revenue Recognition — track subscriptions and one-time payments
    4. Cash Flow Monitoring — daily balance checks, projections
    5. Financial Reporting — weekly/monthly summaries for founder
    """

    CONFIG_NAME = "operations_agent"
    SUBSCRIBED_EVENTS = [
        EventType.TRANSACTION_PROCESSED,
        EventType.BATCH_PROCESSED,
        EventType.REPORT_DELIVERED,
    ]

    def __init__(self, config: AgentConfig | None = None):
        super().__init__(
            name="OperationsAgent",
            role="Autonomous Operations — invoicing, expenses, finance",
            capabilities=[
                "invoice_generation",
                "expense_tracking",
                "revenue_recognition",
                "cash_flow_monitoring",
                "financial_reporting",
                "budget_management",
            ],
            config=config,
        )

        # Financial state
        self._invoices: dict[str, dict[str, Any]] = {}
        self._expenses: list[dict[str, Any]] = []
        self._revenue_records: list[dict[str, Any]] = []
        self._budget: dict[str, float] = {
            "monthly_total": 5000.0,    # $5k/month operating budget
            "infra": 1000.0,
            "llm_api": 2000.0,
            "marketing": 1000.0,
            "tools": 500.0,
            "misc": 500.0,
        }
        self._spent_this_month: dict[str, float] = dict.fromkeys(self._budget, 0.0)

        # Approval thresholds
        self._approval_threshold_usd = 500.0

        # Register tools
        self.tools.register("generate_invoice", self._generate_invoice, "Create and send invoice")
        self.tools.register("track_expense", self._track_expense, "Record and categorize expense")
        self.tools.register("check_cash_flow", self._check_cash_flow, "Check current cash position")

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Analyze context and decide what operations action to take.

        Decision logic:
        - Transaction processed → check if invoice needed
        - Batch processed → generate financial summary
        - Report delivered → update revenue records
        - Budget threshold → alert founder
        """
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")

        # Check budget alerts first
        budget_alert = self._check_budget_alerts()
        if budget_alert:
            return AgentDecision(
                action="budget_alert",
                parameters=budget_alert,
                confidence=0.95,
                reasoning="Budget threshold exceeded",
            )

        # Check for overdue invoices
        overdue = self._get_overdue_invoices()
        if overdue:
            return AgentDecision(
                action="follow_up_invoice",
                parameters={"invoices": overdue[:3]},
                confidence=0.9,
                reasoning=f"{len(overdue)} overdue invoice(s)",
            )

        if event_type == EventType.TRANSACTION_PROCESSED.value:
            payload = event_data.get("payload", {})
            if payload.get("type") == "subscription_payment":
                return AgentDecision(
                    action="record_revenue",
                    parameters={"payment": payload},
                    confidence=0.9,
                    reasoning="Subscription payment received",
                )
            if payload.get("requires_invoice"):
                amount = payload.get("amount_usd", 0)
                if amount > self._approval_threshold_usd:
                    return AgentDecision(
                        action="request_approval",
                        parameters={
                            "action": "generate_invoice",
                            "amount": amount,
                            "client": payload.get("client"),
                        },
                        confidence=0.85,
                        reasoning=f"Invoice ${amount} exceeds approval threshold",
                    )
                return AgentDecision(
                    action="generate_invoice",
                    parameters={"transaction": payload},
                    confidence=0.9,
                    reasoning="Invoice generation triggered",
                )

        if event_type == EventType.BATCH_PROCESSED.value:
            return AgentDecision(
                action="generate_summary",
                parameters={"batch": event_data.get("payload", {})},
                confidence=0.8,
                reasoning="Batch processed — update financial records",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.5,
            reasoning="No operations action needed",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the operations action."""
        action = decision.action
        params = decision.parameters
        start = time.time()

        try:
            if action == "generate_invoice":
                result_data = await self._generate_invoice(params.get("transaction", {}))
            elif action == "record_revenue":
                result_data = await self._record_revenue(params.get("payment", {}))
            elif action == "follow_up_invoice":
                result_data = await self._follow_up_invoices(params.get("invoices", []))
            elif action == "budget_alert":
                result_data = await self._handle_budget_alert(params)
            elif action == "request_approval":
                result_data = await self._request_approval(params)
            elif action == "generate_summary":
                result_data = await self._generate_summary(params.get("batch", {}))
            elif action == "idle":
                result_data = {"status": "idle"}
            else:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )

            return AgentResult(
                success=True,
                data=result_data,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as exc:
            self._logger.error("operations_action_failed", action=action, error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    # ── Operations Functions ────────────────────────────────────────

    async def _generate_invoice(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Generate and send an invoice."""
        invoice_id = f"INV-{int(time.time())}"
        amount = transaction.get("amount_usd", 0)
        client = transaction.get("client", "Unknown")

        invoice = {
            "invoice_id": invoice_id,
            "client": client,
            "amount_usd": amount,
            "currency": transaction.get("currency", "USD"),
            "description": transaction.get("description", "Msaidizi subscription"),
            "status": "sent",
            "created_at": time.time(),
            "due_date": time.time() + 30 * 86400,  # Net 30
            "transaction_ref": transaction.get("id"),
        }

        self._invoices[invoice_id] = invoice
        self._logger.info(
            "invoice_generated",
            invoice_id=invoice_id,
            client=client,
            amount=amount,
        )

        return invoice

    async def _record_revenue(self, payment: dict[str, Any]) -> dict[str, Any]:
        """Record a revenue entry."""
        record = {
            "revenue_id": f"REV-{int(time.time())}",
            "amount_usd": payment.get("amount_usd", 0),
            "source": payment.get("source", "subscription"),
            "client": payment.get("client"),
            "recorded_at": time.time(),
        }
        self._revenue_records.append(record)

        # Match to invoice if possible
        invoice_ref = payment.get("invoice_id")
        if invoice_ref and invoice_ref in self._invoices:
            self._invoices[invoice_ref]["status"] = "paid"
            self._invoices[invoice_ref]["paid_at"] = time.time()

        self._logger.info(
            "revenue_recorded",
            amount=record["amount_usd"],
            source=record["source"],
        )

        return record

    async def _follow_up_invoices(self, invoices: list[dict[str, Any]]) -> dict[str, Any]:
        """Follow up on overdue invoices."""
        results = []
        for inv in invoices:
            inv_id = inv.get("invoice_id", "unknown")
            self._logger.info("invoice_follow_up", invoice_id=inv_id)
            results.append({
                "invoice_id": inv_id,
                "action": "reminder_sent",
                "timestamp": time.time(),
            })
        return {"follow_ups_sent": len(results), "results": results}

    async def _handle_budget_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Handle a budget threshold alert."""
        category = alert.get("category", "unknown")
        spent = alert.get("spent", 0)
        budget = alert.get("budget", 0)
        utilization = (spent / budget * 100) if budget else 0

        if self._escalation:
            await self._escalation.escalate(
                trigger_name="cost_overrun",
                agent_name=self.name,
                summary=f"Budget alert: {category} at {utilization:.0f}% (${spent:.0f}/${budget:.0f})",
                details=alert,
            )

        return {
            "alert_type": "budget_threshold",
            "category": category,
            "utilization_pct": round(utilization, 1),
            "action": "founder_notified",
        }

    async def _request_approval(self, params: dict[str, Any]) -> dict[str, Any]:
        """Request founder approval for high-value actions."""
        if self._escalation:
            await self._escalation.escalate(
                trigger_name="financial_action",
                agent_name=self.name,
                summary=f"Approval needed: {params.get('action')} for ${params.get('amount', 0)}",
                details=params,
            )
        return {"status": "approval_requested", "params": params}

    async def _generate_summary(self, batch: dict[str, Any]) -> dict[str, Any]:
        """Generate a financial summary from batch data."""
        total_revenue = sum(r.get("amount_usd", 0) for r in self._revenue_records)
        total_expenses = sum(e.get("amount_usd", 0) for e in self._expenses)
        total_invoiced = sum(
            inv.get("amount_usd", 0) for inv in self._invoices.values()
            if inv.get("status") in ("sent", "overdue")
        )

        return {
            "period": "current_month",
            "total_revenue_usd": round(total_revenue, 2),
            "total_expenses_usd": round(total_expenses, 2),
            "net_income_usd": round(total_revenue - total_expenses, 2),
            "outstanding_invoices_usd": round(total_invoiced, 2),
            "invoice_count": len(self._invoices),
            "expense_count": len(self._expenses),
        }

    def _check_budget_alerts(self) -> dict[str, Any] | None:
        """Check if any budget category is over threshold."""
        for category, budget in self._budget.items():
            spent = self._spent_this_month.get(category, 0)
            if budget > 0 and spent / budget > 0.8:
                return {
                    "category": category,
                    "spent": spent,
                    "budget": budget,
                    "utilization": spent / budget,
                }
        return None

    def _get_overdue_invoices(self) -> list[dict[str, Any]]:
        """Get invoices past their due date."""
        now = time.time()
        return [
            inv for inv in self._invoices.values()
            if inv.get("status") == "sent" and inv.get("due_date", 0) < now
        ]

    async def _check_cash_flow(self) -> dict[str, Any]:
        """Check current cash flow position."""
        revenue = sum(r.get("amount_usd", 0) for r in self._revenue_records)
        expenses = sum(e.get("amount_usd", 0) for e in self._expenses)
        return {
            "total_revenue": round(revenue, 2),
            "total_expenses": round(expenses, 2),
            "net_cash_flow": round(revenue - expenses, 2),
            "outstanding_invoiced": sum(
                inv.get("amount_usd", 0) for inv in self._invoices.values()
                if inv.get("status") in ("sent", "overdue")
            ),
        }
