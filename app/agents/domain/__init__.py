"""
Domain Agents (Tier 2) — Industry-specific intelligence agents.

Each domain agent specializes in a specific industry vertical:
    Agriculture    — Crop prices, weather, supply chain
    Retail         — Inventory, pricing, customer behavior
    Transport      — Route optimization, fleet management
    Digital        — E-commerce, digital payments
    Manufacturing  — Production, quality, supply chain
    Service        — Hospitality, healthcare, education
"""

from app.agents.domain.agriculture import AgricultureDomainAgent
from app.agents.domain.base import ECO_FRAMEWORK, STA_FRAMEWORK, DomainAgent
from app.agents.domain.digital import DigitalDomainAgent
from app.agents.domain.manufacturing import ManufacturingDomainAgent
from app.agents.domain.retail import RetailDomainAgent
from app.agents.domain.service import ServiceDomainAgent
from app.agents.domain.transport import TransportDomainAgent

__all__ = [
    "ECO_FRAMEWORK",
    "STA_FRAMEWORK",
    "AgricultureDomainAgent",
    "DigitalDomainAgent",
    "DomainAgent",
    "ManufacturingDomainAgent",
    "RetailDomainAgent",
    "ServiceDomainAgent",
    "TransportDomainAgent",
]
