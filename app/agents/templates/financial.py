"""
Financial Agent Templates for Angavu Intelligence.

Models after Anthropic's 10 financial agent templates (May 2026),
adapted for the informal economy context.

Each template is a factory that creates a fully-configured BiasharaAgent
with appropriate tools, memory configuration, and MCP tool definitions.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    AgentStatus,
    BiasharaAgent,
    EventType,
)
from app.agents.memory.tiered import (
    MemoryImportance,
    TieredMemoryManager,
)
from app.agents.protocols.mcp import MCPTool, MCPToolPermission

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Financial Agent Base
# ════════════════════════════════════════════════════════════════════


class FinancialAgent(BiasharaAgent):
    """
    Base class for financial agents with tiered memory.

    Adds:
    - TieredMemoryManager (replaces simple AgentMemory)
    - Financial-specific MCP tools
    - Compliance-aware decision making
    - Human-in-the-loop for critical decisions
    """

    def __init__(
        self,
        name: str,
        role: str,
        capabilities: Sequence[str],
        working_max_tokens: int = 4000,
    ):
        super().__init__(name, role, capabilities)
        self.tiered_memory = TieredMemoryManager(
            agent_name=name,
            working_max_tokens=working_max_tokens,
        )
        self._requires_human_approval: List[str] = []  # actions that need approval
        self._pending_approvals: Dict[str, AgentDecision] = {}

    def set_tracer(self, tracer: Any) -> None:
        super().set_tracer(tracer)

    async def observe(self, event: AgentEvent) -> None:
        """Observe with tiered memory."""
        self.status = AgentStatus.OBSERVING
        importance = MemoryImportance.NORMAL

        # Errors and critical events get high importance
        if "error" in event.event_type.value:
            importance = MemoryImportance.CRITICAL
        elif "feedback" in event.event_type.value:
            importance = MemoryImportance.HIGH

        self.tiered_memory.on_observe(
            event_data=event.to_dict(),
            importance=importance,
            tags=[event.event_type.value],
        )

        # Also update legacy memory for backward compatibility
        self.memory.remember({
            "event_type": event.event_type.value,
            "source": event.source,
            "payload_summary": {k: str(v)[:100] for k, v in event.payload.items()},
        })

    async def handle_event(self, event: AgentEvent) -> AgentResult:
        """Full lifecycle with tiered memory integration."""
        cycle_start = time.time()
        trace_id = None

        try:
            # 1. Observe
            await self.observe(event)

            # 2. Think — with enriched context from tiered memory
            self.status = AgentStatus.THINKING
            context = self.tiered_memory.get_context_for_decision()
            context["event"] = event.to_dict()
            context["tools"] = self.tools.list_tools()

            if self._tracer:
                trace_id = self._tracer.start_trace(self.name, context)

            decision = await self.think(context)

            if self._tracer and trace_id:
                self._tracer.record_decision(trace_id, decision)

            # Check if human approval is required
            if decision.action in self._requires_human_approval:
                self._pending_approvals[decision.decision_id] = decision
                self._logger.info(
                    "human_approval_required",
                    action=decision.action,
                    decision_id=decision.decision_id,
                )
                return AgentResult(
                    success=True,
                    data={"status": "pending_approval", "decision_id": decision.decision_id},
                    duration_ms=(time.time() - cycle_start) * 1000,
                )

            # 3. Act
            self.status = AgentStatus.ACTING
            result = await self.act(decision)

            if self._tracer and trace_id:
                self._tracer.record_result(trace_id, result)

            # 4. Reflect — record episode in tiered memory
            duration_ms = (time.time() - cycle_start) * 1000
            self.tiered_memory.record_episode(
                trigger_event=event.to_dict(),
                decision={"action": decision.action, "confidence": decision.confidence},
                result={"success": result.success, "error": result.error, "data": str(result.data)[:200]},
                duration_ms=duration_ms,
            )

            # Also update legacy memory
            await self.reflect(result)

            # 5. Publish downstream events
            if self._event_bus and result.events_to_publish:
                for downstream_event in result.events_to_publish:
                    await self._event_bus.publish(downstream_event)

            # 6. Finalize trace
            if self._tracer and trace_id:
                self._tracer.end_trace(trace_id, success=result.success)

            self.status = AgentStatus.IDLE
            return result

        except Exception as exc:
            self.status = AgentStatus.ERROR
            self.tiered_memory.on_error({"error": str(exc), "event_type": event.event_type.value})
            self._logger.exception("agent_cycle_error", error=str(exc))
            if self._tracer and trace_id:
                self._tracer.end_trace(trace_id, success=False, error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - cycle_start) * 1000,
            )

    async def approve_decision(self, decision_id: str) -> Optional[AgentResult]:
        """Process a human-approved decision."""
        decision = self._pending_approvals.pop(decision_id, None)
        if not decision:
            return None

        result = await self.act(decision)
        self.tiered_memory.record_episode(
            trigger_event={"type": "human_approval", "decision_id": decision_id},
            decision={"action": decision.action, "confidence": decision.confidence},
            result={"success": result.success, "error": result.error},
            duration_ms=result.duration_ms,
            tags=["human_approved"],
        )
        return result


# ════════════════════════════════════════════════════════════════════
# Financial Agent Templates (Inspired by Anthropic's 10 templates)
# ════════════════════════════════════════════════════════════════════


class CreditScoringAgent(FinancialAgent):
    """
    Template 1: Credit Scoring Agent

    Evaluates creditworthiness of informal workers based on:
    - M-Pesa transaction history
    - Business transaction patterns
    - Market reputation data
    - Seasonal income patterns

    Maps to Anthropic's "Model Builder" template.
    """

    def __init__(self):
        super().__init__(
            name="CreditScoringAgent",
            role="Evaluates creditworthiness for informal economy participants",
            capabilities=["credit_scoring", "risk_assessment", "transaction_analysis"],
        )
        self._requires_human_approval = ["deny_credit", "approve_high_risk_loan"]

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event = context.get("event", {})
        payload = event.get("payload", {})
        user_id = payload.get("user_id", "")

        # Check tiered memory for past scoring patterns
        patterns = self.tiered_memory.get_relevant_patterns(context, min_confidence=0.5)

        # Check episodic memory for similar past scores
        similar = self.tiered_memory.episodic.get_similar(
            trigger_event=event.get("payload", {}),
            agent_name=self.name,
            limit=3,
        )

        confidence = 0.7
        reasoning = f"Credit assessment for user {user_id}"

        if similar:
            past_successes = sum(1 for e in similar if e.success)
            confidence = max(0.5, min(0.95, past_successes / len(similar) + 0.3))
            reasoning += f". Found {len(similar)} similar past assessments."

        return AgentDecision(
            action="assess_credit",
            parameters={"user_id": user_id, "similar_assessments": len(similar)},
            confidence=confidence,
            reasoning=reasoning,
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        # In production, this would call the Alama Score service
        user_id = decision.parameters.get("user_id", "")
        return AgentResult(
            success=True,
            data={"user_id": user_id, "score": 650, "risk_level": "medium"},
            duration_ms=45.0,
        )


class CashFlowForecastAgent(FinancialAgent):
    """
    Template 2: Cash Flow Forecasting Agent

    Predicts future cash flow based on:
    - Historical transaction patterns
    - Seasonal trends
    - Market conditions
    - Business growth trajectory

    Maps to Anthropic's "Earnings Reviewer" template.
    """

    def __init__(self):
        super().__init__(
            name="CashFlowForecastAgent",
            role="Forecasts cash flow for informal businesses",
            capabilities=["cash_flow_forecasting", "trend_analysis", "seasonal_modeling"],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event = context.get("event", {})
        payload = event.get("payload", {})
        user_id = payload.get("user_id", "")
        horizon_days = payload.get("horizon_days", 30)

        return AgentDecision(
            action="forecast_cash_flow",
            parameters={"user_id": user_id, "horizon_days": horizon_days},
            confidence=0.75,
            reasoning=f"Cash flow forecast for {horizon_days} days",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "forecast": {"expected_income": 45000, "expected_expenses": 32000, "net": 13000},
                "confidence_interval": {"low": 8000, "high": 18000},
            },
            duration_ms=120.0,
        )


class MarketAnalysisAgent(FinancialAgent):
    """
    Template 3: Market Analysis Agent

    Analyzes market prices, trends, and opportunities for informal traders.
    Monitors wholesale/retail prices, identifies arbitrage opportunities.

    Maps to Anthropic's "Pitch Builder" template.
    """

    def __init__(self):
        super().__init__(
            name="MarketAnalysisAgent",
            role="Analyzes market conditions for informal traders",
            capabilities=["market_analysis", "price_monitoring", "arbitrage_detection"],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="analyze_market",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.8,
            reasoning="Market analysis based on current data",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "prices": {"nyanya": 80, "nyanya_dry": 120, "maize": 60},
                "trends": "stable",
                "opportunities": ["Bulk purchase nyanya at Gikomba for Mombasa resale"],
            },
            duration_ms=200.0,
        )


class TaxComplianceAgent(FinancialAgent):
    """
    Template 4: Tax Compliance Agent

    Handles tax obligations for informal workers:
    - Categorizes income and expenses
    - Calculates simplified tax obligations
    - Generates tax-ready reports
    - Identifies eligible deductions

    Maps to Anthropic's "Month-End Closer" template.
    """

    def __init__(self):
        super().__init__(
            name="TaxComplianceAgent",
            role="Manages tax compliance for informal businesses",
            capabilities=["tax_calculation", "deduction_identification", "report_generation"],
        )
        self._requires_human_approval = ["file_tax_return"]

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="calculate_tax",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.85,
            reasoning="Tax calculation based on transaction history",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "gross_income": 540000,
                "deductions": 120000,
                "taxable_income": 420000,
                "tax_due": 12600,
                "deductions_detail": ["Business expenses: 80,000", "Transport: 40,000"],
            },
            duration_ms=80.0,
        )


class FormalizationAgent(FinancialAgent):
    """
    Template 5: Business Formalization Agent

    Guides informal businesses through formalization:
    - Assesses readiness for formalization
    - Recommends optimal business structure
    - Pre-fills registration forms
    - Tracks compliance milestones

    Maps to Anthropic's "KYC Screener" template.
    """

    def __init__(self):
        super().__init__(
            name="FormalizationAgent",
            role="Guides informal businesses through formalization",
            capabilities=["formalization_assessment", "registration_guidance", "compliance_tracking"],
        )
        self._requires_human_approval = ["recommend_formalization"]

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="assess_formalization_readiness",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.7,
            reasoning="Formalization readiness assessment",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "readiness_score": 72,
                "recommended_structure": "sole_proprietorship",
                "next_steps": [
                    "Register business name at Huduma Centre",
                    "Obtain KRA PIN certificate",
                    "Open business bank account",
                ],
                "estimated_cost": 5000,
                "estimated_time_days": 14,
            },
            duration_ms=150.0,
        )


class AnomalyDetectionAgent(FinancialAgent):
    """
    Template 6: Anomaly Detection Agent

    Detects unusual patterns that may indicate:
    - Fraud or theft
    - Data entry errors
    - Unusual market conditions
    - Business opportunities

    Maps to Anthropic's "Compliance Checker" template.
    """

    def __init__(self):
        super().__init__(
            name="AnomalyDetectionAgent",
            role="Detects anomalies in financial transactions",
            capabilities=["anomaly_detection", "fraud_detection", "error_detection"],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="detect_anomalies",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.8,
            reasoning="Anomaly detection scan on recent transactions",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "anomalies_detected": 1,
                "anomalies": [
                    {
                        "type": "unusual_amount",
                        "description": "Transaction 5x larger than typical",
                        "severity": "medium",
                        "transaction_id": "txn_abc123",
                    }
                ],
            },
            duration_ms=60.0,
        )


class SupplierMatchingAgent(FinancialAgent):
    """
    Template 7: Supplier-Buyer Matching Agent

    Matches producers with buyers based on:
    - Product type and quality
    - Volume and timing
    - Location and logistics
    - Price and payment terms

    Maps to Anthropic's "Research Agent" template.
    """

    def __init__(self):
        super().__init__(
            name="SupplierMatchingAgent",
            role="Matches informal producers with buyers",
            capabilities=["supplier_matching", "buyer_matching", "marketplace"],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="match_suppliers",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.75,
            reasoning="Supplier-buyer matching based on current market data",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "matches": [
                    {"supplier": "Farmer A (Nyeri)", "buyer": "Trader B (Nairobi)", "product": "nyanya", "volume": "500kg"},
                ],
                "match_score": 0.85,
            },
            duration_ms=180.0,
        )


class InventoryOptimizationAgent(FinancialAgent):
    """
    Template 8: Inventory Optimization Agent

    Optimizes inventory for small traders:
    - Demand forecasting
    - Reorder point calculation
    - Waste reduction
    - Storage optimization

    Maps to Anthropic's "Model Builder" template (supply chain variant).
    """

    def __init__(self):
        super().__init__(
            name="InventoryOptimizationAgent",
            role="Optimizes inventory for informal traders",
            capabilities=["demand_forecasting", "reorder_optimization", "waste_reduction"],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="optimize_inventory",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.7,
            reasoning="Inventory optimization based on demand patterns",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "recommendations": [
                    {"item": "nyanya", "current_stock": 50, "recommended_order": 100, "reorder_point": 30},
                ],
                "estimated_waste_reduction": "15%",
            },
            duration_ms=100.0,
        )


class FinancialHealthAgent(FinancialAgent):
    """
    Template 9: Financial Health Summary Agent

    Generates comprehensive financial health reports:
    - Income vs expenses analysis
    - Savings rate
    - Debt-to-income ratio
    - Business growth trajectory
    - Recommendations

    Maps to Anthropic's "Report Generator" template.
    """

    def __init__(self):
        super().__init__(
            name="FinancialHealthAgent",
            role="Generates financial health summaries for informal workers",
            capabilities=["financial_analysis", "health_scoring", "recommendations"],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="generate_health_report",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.85,
            reasoning="Financial health report generation",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "health_score": 68,
                "income_trend": "growing",
                "savings_rate": 0.12,
                "key_metrics": {
                    "monthly_income_avg": 45000,
                    "monthly_expenses_avg": 38000,
                    "months_of_data": 6,
                },
                "recommendations": [
                    "Increase savings rate to 20%",
                    "Diversify income sources",
                    "Track daily expenses more consistently",
                ],
            },
            duration_ms=90.0,
        )


class RegulatoryIntelligenceAgent(FinancialAgent):
    """
    Template 10: Regulatory Intelligence Agent

    Monitors regulatory landscape for informal businesses:
    - Tax rate changes
    - Licensing requirements
    - County-specific regulations
    - Compliance deadlines

    Maps to Anthropic's "Earnings Reviewer" template (regulatory variant).
    """

    def __init__(self):
        super().__init__(
            name="RegulatoryIntelligenceAgent",
            role="Monitors regulatory changes affecting informal businesses",
            capabilities=["regulatory_monitoring", "compliance_alerting", "impact_analysis"],
        )

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            action="check_regulations",
            parameters=context.get("event", {}).get("payload", {}),
            confidence=0.8,
            reasoning="Regulatory compliance check",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        return AgentResult(
            success=True,
            data={
                "alerts": [
                    {
                        "type": "tax_rate_change",
                        "description": "Turnover tax rate changed from 1% to 3% for businesses with revenue > KES 1M",
                        "effective_date": "2026-07-01",
                        "impact": "medium",
                    }
                ],
                "upcoming_deadlines": [
                    {"type": "tax_filing", "date": "2026-07-20", "description": "Monthly turnover tax filing"},
                ],
            },
            duration_ms=70.0,
        )


# ════════════════════════════════════════════════════════════════════
# Factory — Create all financial agents
# ════════════════════════════════════════════════════════════════════


def create_all_financial_agents() -> List[FinancialAgent]:
    """Create all 10 financial agent templates."""
    return [
        CreditScoringAgent(),
        CashFlowForecastAgent(),
        MarketAnalysisAgent(),
        TaxComplianceAgent(),
        FormalizationAgent(),
        AnomalyDetectionAgent(),
        SupplierMatchingAgent(),
        InventoryOptimizationAgent(),
        FinancialHealthAgent(),
        RegulatoryIntelligenceAgent(),
    ]


def get_financial_agent_mcp_tools() -> List[MCPTool]:
    """Get MCP tool definitions for all financial agents."""
    return [
        MCPTool(
            name="assess_credit",
            description="Assess creditworthiness of an informal worker",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
            permission=MCPToolPermission.READ,
            tags=["finance", "credit"],
        ),
        MCPTool(
            name="forecast_cash_flow",
            description="Forecast cash flow for an informal business",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}, "horizon_days": {"type": "integer"}}, "required": ["user_id"]},
            permission=MCPToolPermission.READ,
            tags=["finance", "prediction"],
        ),
        MCPTool(
            name="analyze_market",
            description="Analyze market conditions for a specific commodity",
            input_schema={"type": "object", "properties": {"item": {"type": "string"}, "market": {"type": "string"}}, "required": ["item"]},
            permission=MCPToolPermission.READ,
            tags=["market", "analysis"],
        ),
        MCPTool(
            name="calculate_tax",
            description="Calculate tax obligations for an informal business",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}, "period": {"type": "string"}}, "required": ["user_id"]},
            permission=MCPToolPermission.READ,
            tags=["tax", "compliance"],
        ),
        MCPTool(
            name="assess_formalization",
            description="Assess business formalization readiness",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
            permission=MCPToolPermission.READ,
            tags=["business", "formalization"],
        ),
        MCPTool(
            name="detect_anomalies",
            description="Detect anomalies in financial transactions",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}, "lookback_days": {"type": "integer"}}, "required": ["user_id"]},
            permission=MCPToolPermission.READ,
            tags=["security", "anomaly"],
        ),
        MCPTool(
            name="match_suppliers",
            description="Match suppliers with buyers in the marketplace",
            input_schema={"type": "object", "properties": {"product": {"type": "string"}, "location": {"type": "string"}}, "required": ["product"]},
            permission=MCPToolPermission.READ,
            tags=["marketplace", "matching"],
        ),
        MCPTool(
            name="optimize_inventory",
            description="Optimize inventory for a small trader",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
            permission=MCPToolPermission.READ,
            tags=["inventory", "optimization"],
        ),
        MCPTool(
            name="generate_health_report",
            description="Generate financial health report",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
            permission=MCPToolPermission.READ,
            tags=["reporting", "health"],
        ),
        MCPTool(
            name="check_regulations",
            description="Check regulatory requirements and changes",
            input_schema={"type": "object", "properties": {"business_type": {"type": "string"}, "county": {"type": "string"}}, "required": ["business_type"]},
            permission=MCPToolPermission.READ,
            tags=["regulatory", "compliance"],
        ),
    ]
