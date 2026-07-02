"""
Biashara Intelligence — Multi-Agent Runtime

Transforms the monolithic service layer into a true multi-agent system.

Agents:
    TransactionProcessor  — Cleans and structures raw M-Pesa / POS data
    IntelligenceGenerator — Runs Soko Pulse, Alama Score, econometrics
    ReportGenerator       — Produces WhatsApp-native reports for workers
    SelfEvolution         — Learns from worker feedback, drives product evolution

Infrastructure:
    EventBus    — Redis Streams for inter-agent communication
    AgentTracer — Observability for every agent decision
    BiasharaAgent — Base class with observe / think / act / reflect lifecycle
"""

from app.agents.base import BiasharaAgent
from app.agents.event_bus import EventBus
from app.agents.observability import AgentTracer
from app.agents.implementations import (
    TransactionProcessorAgent,
    IntelligenceGeneratorAgent,
    ReportGeneratorAgent,
    SelfEvolutionAgent,
)

__all__ = [
    "BiasharaAgent",
    "EventBus",
    "AgentTracer",
    "TransactionProcessorAgent",
    "IntelligenceGeneratorAgent",
    "ReportGeneratorAgent",
    "SelfEvolutionAgent",
]
