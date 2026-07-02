"""
Domain-Specific Intelligence Agents — Tier 2 of the 16-agent architecture.

Each domain agent provides specialized analytics, recommendations, and
intelligence for a specific informal worker type:

    TransportAgent    → boda boda, matatu, tuk-tuk, taxi
    RetailAgent       → mama mboga, dukawallah, mitumba, market traders
    AgricultureAgent  → farmers, fish traders, food processors
    ServiceAgent      → hairdressers, barbers, mechanics, tailors
    DigitalAgent      → M-Pesa agents, social media sellers, gig workers
    ManufacturingAgent → jua kali, furniture makers, welders, brick makers

Domain agents are activated per worker type and loaded on-demand
to conserve memory on 2GB devices.
"""

from app.services.agents.transport_agent import TransportAgent
from app.services.agents.retail_agent import RetailAgent
from app.services.agents.agriculture_agent import AgricultureAgent
from app.services.agents.service_agent import ServiceAgent
from app.services.agents.digital_agent import DigitalAgent
from app.services.agents.manufacturing_agent import ManufacturingAgent

__all__ = [
    "TransportAgent",
    "RetailAgent",
    "AgricultureAgent",
    "ServiceAgent",
    "DigitalAgent",
    "ManufacturingAgent",
]
