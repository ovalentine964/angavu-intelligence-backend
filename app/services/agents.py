"""
Domain Agents — Worker-type-specific intelligence agents.

Each agent specializes in a particular informal economy sector,
providing tailored insights and recommendations based on transaction data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class BaseDomainAgent(ABC):
    """Base class for domain-specific agents."""

    name: str = "BaseAgent"
    tier: int = 2
    role: str = "Domain intelligence agent"
    worker_types: list[str] = []

    @abstractmethod
    async def get_insights(
        self, transactions: list[dict], period_days: int = 30
    ) -> list[dict]:
        """Generate domain-specific insights from transactions."""
        ...

    @abstractmethod
    async def get_recommendations(
        self, transactions: list[dict], period_days: int = 30
    ) -> list[dict]:
        """Generate actionable recommendations."""
        ...

    def _basic_stats(self, transactions: list[dict]) -> dict:
        """Calculate basic transaction statistics."""
        if not transactions:
            return {"total_transactions": 0, "total_revenue": 0, "avg_transaction": 0}

        amounts = [t.get("amount", 0) for t in transactions if t.get("amount")]
        total = sum(amounts)
        return {
            "total_transactions": len(transactions),
            "total_revenue": total,
            "avg_transaction": total / max(len(amounts), 1),
            "period_days": max(1, len(set(
                str(t.get("timestamp", ""))[:10] for t in transactions if t.get("timestamp")
            ))),
        }


class TransportAgent(BaseDomainAgent):
    """Agent for transport sector (boda boda, matatu, tuk-tuk)."""
    name = "TransportAgent"
    role = "Transport sector intelligence — fuel costs, route optimization, fare analysis"
    worker_types = ["transport"]

    async def get_insights(self, transactions, period_days=30):
        stats = self._basic_stats(transactions)
        fuel_txns = [t for t in transactions if "fuel" in str(t.get("item", "")).lower()]
        return [{
            "type": "transport_overview",
            "period_days": period_days,
            "stats": stats,
            "fuel_transactions": len(fuel_txns),
            "fuel_cost": sum(t.get("amount", 0) for t in fuel_txns),
        }]

    async def get_recommendations(self, transactions, period_days=30):
        return [{"type": "general", "recommendation": "Track fuel expenses separately for better cost analysis.", "priority": "medium"}]


class RetailAgent(BaseDomainAgent):
    """Agent for retail sector (duka, mama mboga, kiosk)."""
    name = "RetailAgent"
    role = "Retail intelligence — inventory, pricing, customer patterns"
    worker_types = ["trader", "retail"]

    async def get_insights(self, transactions, period_days=30):
        stats = self._basic_stats(transactions)
        categories = {}
        for t in transactions:
            cat = t.get("item_category", "unknown")
            categories[cat] = categories.get(cat, 0) + t.get("amount", 0)
        return [{
            "type": "retail_overview",
            "period_days": period_days,
            "stats": stats,
            "top_categories": sorted(categories.items(), key=lambda x: -x[1])[:5],
        }]

    async def get_recommendations(self, transactions, period_days=30):
        return [{"type": "general", "recommendation": "Focus on top-selling categories to maximize revenue.", "priority": "medium"}]


class AgricultureAgent(BaseDomainAgent):
    """Agent for agriculture sector (farmers, produce sellers)."""
    name = "AgricultureAgent"
    role = "Agriculture intelligence — seasonal patterns, crop pricing, supply chain"
    worker_types = ["agriculture"]

    async def get_insights(self, transactions, period_days=30):
        stats = self._basic_stats(transactions)
        return [{
            "type": "agriculture_overview",
            "period_days": period_days,
            "stats": stats,
        }]

    async def get_recommendations(self, transactions, period_days=30):
        return [{"type": "general", "recommendation": "Track seasonal price patterns for better selling decisions.", "priority": "medium"}]


class ServiceAgent(BaseDomainAgent):
    """Agent for service sector (salon, repair, laundry)."""
    name = "ServiceAgent"
    role = "Service sector intelligence — customer retention, pricing, capacity"
    worker_types = ["service"]

    async def get_insights(self, transactions, period_days=30):
        stats = self._basic_stats(transactions)
        return [{
            "type": "service_overview",
            "period_days": period_days,
            "stats": stats,
        }]

    async def get_recommendations(self, transactions, period_days=30):
        return [{"type": "general", "recommendation": "Focus on repeat customers to build a stable revenue base.", "priority": "medium"}]


class DigitalAgent(BaseDomainAgent):
    """Agent for digital services (M-Pesa agents, cyber cafes)."""
    name = "DigitalAgent"
    role = "Digital services intelligence — transaction volume, commission tracking"
    worker_types = ["digital"]

    async def get_insights(self, transactions, period_days=30):
        stats = self._basic_stats(transactions)
        return [{
            "type": "digital_overview",
            "period_days": period_days,
            "stats": stats,
        }]

    async def get_recommendations(self, transactions, period_days=30):
        return [{"type": "general", "recommendation": "Track commission income separately from float movements.", "priority": "medium"}]


class ManufacturingAgent(BaseDomainAgent):
    """Agent for manufacturing sector (jua kali, artisans)."""
    name = "ManufacturingAgent"
    role = "Manufacturing intelligence — material costs, production efficiency"
    worker_types = ["manufacturing"]

    async def get_insights(self, transactions, period_days=30):
        stats = self._basic_stats(transactions)
        return [{
            "type": "manufacturing_overview",
            "period_days": period_days,
            "stats": stats,
        }]

    async def get_recommendations(self, transactions, period_days=30):
        return [{"type": "general", "recommendation": "Track raw material costs to improve profit margins.", "priority": "medium"}]
