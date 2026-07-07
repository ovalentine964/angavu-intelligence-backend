"""
Financial Agent Templates — Pre-built agents for informal economy tasks.

Inspired by Anthropic's 10 financial agent templates (May 2026),
adapted for East African informal economy context.
"""

from app.agents.templates.financial import (
    FinancialAgent,
    CreditScoringAgent,
    CashFlowForecastAgent,
    MarketAnalysisAgent,
    TaxComplianceAgent,
    FormalizationAgent,
    AnomalyDetectionAgent,
    SupplierMatchingAgent,
    InventoryOptimizationAgent,
    FinancialHealthAgent,
    RegulatoryIntelligenceAgent,
    create_all_financial_agents,
    get_financial_agent_mcp_tools,
)

__all__ = [
    "FinancialAgent",
    "CreditScoringAgent",
    "CashFlowForecastAgent",
    "MarketAnalysisAgent",
    "TaxComplianceAgent",
    "FormalizationAgent",
    "AnomalyDetectionAgent",
    "SupplierMatchingAgent",
    "InventoryOptimizationAgent",
    "FinancialHealthAgent",
    "RegulatoryIntelligenceAgent",
    "create_all_financial_agents",
    "get_financial_agent_mcp_tools",
]
