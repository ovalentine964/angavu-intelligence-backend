"""
Research Swarm (Swarm 6) — Market research, competitive intelligence.

Agents:
    MarketResearchAgent  — Trend analysis, competitor tracking
    UserInsightAgent     — User behavior analysis, retention patterns
    InnovationAgent      — Feature ideation based on user needs
"""

from app.agents.research.market_research import MarketResearchAgent
from app.agents.research.user_insight import UserInsightAgent
from app.agents.research.innovation import InnovationAgent

__all__ = [
    "MarketResearchAgent",
    "UserInsightAgent",
    "InnovationAgent",
]
