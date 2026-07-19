"""
Financial Agent Templates — Pre-built agents for informal economy tasks.

Inspired by Anthropic's 10 financial agent templates (May 2026),
adapted for East African informal economy context.
"""

from app.agents.templates.financial import (
    AnomalyDetectionAgent,
    CashFlowForecastAgent,
    CreditScoringAgent,
    FinancialAgent,
    FinancialHealthAgent,
    FormalizationAgent,
    InventoryOptimizationAgent,
    MarketAnalysisAgent,
    RegulatoryIntelligenceAgent,
    SupplierMatchingAgent,
    TaxComplianceAgent,
    create_all_financial_agents,
    get_financial_agent_mcp_tools,
)

__all__ = [
    "AnomalyDetectionAgent",
    "CashFlowForecastAgent",
    "CreditScoringAgent",
    "FinancialAgent",
    "FinancialHealthAgent",
    "FormalizationAgent",
    "InventoryOptimizationAgent",
    "MarketAnalysisAgent",
    "RegulatoryIntelligenceAgent",
    "SupplierMatchingAgent",
    "TaxComplianceAgent",
    "create_all_financial_agents",
    "get_financial_agent_mcp_tools",
]
