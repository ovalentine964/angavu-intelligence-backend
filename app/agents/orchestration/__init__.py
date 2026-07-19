"""
Swarm 6: MCP & Always-On Agents for Angavu Intelligence Backend.

Components:
    - AlwaysOnMarketMonitor: watches prices, alerts on changes
    - AlwaysOnPolicyMonitor: watches government/regulatory changes
    - MCPSwarmRouter: routes tasks to correct swarm by domain
    - SelfImprovingAgent: agents that learn from feedback loops
    - EventBusIntegration: Redis Streams wiring for always-on agents
"""

from .always_on_market_monitor import AlwaysOnMarketMonitor, MarketScout, MarketRanker
from .always_on_policy_monitor import AlwaysOnPolicyMonitor, PolicyRadar, PolicyRanker
from .mcp_swarm_router import MCPSwarmRouter, DomainClassifier, SwarmRoute
from .self_improving_agent import SelfImprovingAgent, FeedbackAnalyzer, SkillMutator

__all__ = [
    "AlwaysOnMarketMonitor",
    "MarketScout",
    "MarketRanker",
    "AlwaysOnPolicyMonitor",
    "PolicyRadar",
    "PolicyRanker",
    "MCPSwarmRouter",
    "DomainClassifier",
    "SwarmRoute",
    "SelfImprovingAgent",
    "FeedbackAnalyzer",
    "SkillMutator",
]
