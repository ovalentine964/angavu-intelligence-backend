"""
Biashara Intelligence — DeerFlow Integration Layer.

This module bridges DeerFlow's agent harness (deerflow-harness) with
Biashara's existing intelligence services. It provides:

1. Tool loading: Wraps Biashara services as LangChain tools
2. Agent creation: Uses DeerFlow's create_deerflow_agent factory
3. Lead agent: Orchestrates domain-specific sub-agents
4. Middleware chain: Configures DeerFlow's 21+ middlewares for Biashara

Architecture:
    User Request
        ↓
    BiasharaLeadAgent (DeerFlow LeadAgent)
        ↓
    Domain Agent Router (research | credit | distribution | fmcg | health | dev)
        ↓
    Biashara Tools (soko_pulse | alama_score | distribution_gap | fmcg_intelligence | worker_intelligence)
        ↓
    Biashara Services (existing SQLAlchemy-backed services)

Key Design Decisions:
- USE DeerFlow's create_deerflow_agent, NOT custom agent code
- USE DeerFlow's middleware chain (summarization, memory, loop detection, etc.)
- USE DeerFlow's ThreadState for LangGraph state management
- USE DeerFlow's skill system for SKILL.md loading
- Bridge async Biashara services with DeerFlow's sync tool interface
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import yaml
from langchain.agents.middleware import AgentMiddleware

from app.biashara_tools import get_biashara_tools

logger = logging.getLogger(__name__)


# ── DeerFlow Component Imports ──────────────────────────────────────────────
# These imports are the ONLY way to access DeerFlow's agent infrastructure.
# Do NOT create custom agent classes — use the harness.

try:
    from deerflow.agents.factory import create_deerflow_agent
    from deerflow.agents.features import RuntimeFeatures
    from deerflow.agents.thread_state import ThreadState
    from deerflow.agents.middlewares.clarification_middleware import ClarificationMiddleware
    from deerflow.agents.middlewares.loop_detection_middleware import LoopDetectionMiddleware
    from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware
    from deerflow.agents.middlewares.summarization_middleware import DeerFlowSummarizationMiddleware
    from deerflow.agents.middlewares.title_middleware import TitleMiddleware
    from deerflow.agents.middlewares.todo_middleware import TodoMiddleware
    from deerflow.models import create_chat_model
    DEERFLOW_AVAILABLE = True
except ImportError:
    DEERFLOW_AVAILABLE = False
    logger.warning(
        "deerflow-harness not installed. Install with: "
        "pip install -e /path/to/biashara-deerflow/backend/packages/harness"
    )


# ── Configuration ───────────────────────────────────────────────────────────

BIASHARA_CONFIG_PATH = "config/biashara_agents.yaml"


def _load_biashara_config() -> dict:
    """Load Biashara agent configuration from YAML."""
    try:
        with open(BIASHARA_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Config not found at {BIASHARA_CONFIG_PATH}, using defaults")
        return {}


# ── Tool Loading ────────────────────────────────────────────────────────────

def get_deerflow_tools(groups: list[str] | None = None) -> list:
    """Load Biashara tools for DeerFlow agent binding.

    Args:
        groups: Optional tool group filter. If None, returns all Biashara tools.

    Returns:
        List of LangChain BaseTool instances.
    """
    tools = get_biashara_tools()

    if groups and "biashara" not in groups:
        logger.warning(f"Requested tool groups {groups} not available; Biashara tools require group 'biashara'")
        return []

    return tools


# ── Agent Creation (DeerFlow Factory) ───────────────────────────────────────

def create_biashara_agent(
    agent_name: str = "default",
    model_name: str = "deepseek-chat",
    system_prompt: str | None = None,
    plan_mode: bool = False,
    extra_middleware: list[AgentMiddleware] | None = None,
) -> Any:
    """Create a DeerFlow agent with Biashara tools.

    This is the PRIMARY entry point for creating Biashara agents.
    It uses DeerFlow's create_deerflow_agent factory — NOT custom code.

    Args:
        agent_name: Agent role name (research, credit, distribution, fmcg, health, development)
        model_name: DeepSeek model to use (deepseek-chat, deepseek-reasoner)
        system_prompt: Custom system prompt. If None, uses the agent's configured prompt.
        plan_mode: Enable TodoMiddleware for complex multi-step tasks.
        extra_middleware: Additional DeerFlow middlewares to inject.

    Returns:
        CompiledStateGraph (LangGraph agent) ready for invocation.
    """
    if not DEERFLOW_AVAILABLE:
        raise RuntimeError(
            "deerflow-harness is required. Install with: "
            "pip install -e /path/to/biashara-deerflow/backend/packages/harness"
        )

    config = _load_biashara_config()

    # Resolve model
    model = create_chat_model(name=model_name, thinking_enabled=False)

    # Load tools
    tools = get_deerflow_tools()

    # Resolve system prompt from config
    if system_prompt is None:
        agent_config = config.get("agents", {}).get(agent_name, {})
        system_prompt = agent_config.get("description", _default_system_prompt(agent_name))

    # Configure features for Biashara use case
    features = RuntimeFeatures(
        sandbox=False,           # No code sandbox needed
        summarization=False,     # Disable for now (needs model arg)
        auto_title=True,         # Auto-generate conversation titles
        memory=True,             # Enable conversation memory
        vision=False,            # No vision needed
        subagent=False,          # No sub-agents for domain agents
        loop_detection=True,     # Prevent infinite tool loops
        token_budget=False,      # No token budget for now
    )

    # Create agent using DeerFlow's factory
    agent = create_deerflow_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        features=features,
        extra_middleware=extra_middleware,
        plan_mode=plan_mode,
        state_schema=ThreadState,
        name=agent_name,
    )

    logger.info(f"Created Biashara DeerFlow agent: {agent_name} (model={model_name}, tools={len(tools)})")
    return agent


def create_biashara_lead_agent(
    model_name: str = "deepseek-reasoner",
    plan_mode: bool = True,
) -> Any:
    """Create the Biashara lead agent — the top-level orchestrator.

    The lead agent:
    - Routes queries to appropriate domain agents
    - Manages conversation context and memory
    - Handles multi-step research tasks with plan mode
    - Provides a unified interface for all Biashara intelligence

    Uses DeerFlow's create_deerflow_agent with full feature set.

    Args:
        model_name: Model for the lead agent (default: deepseek-reasoner for planning)
        plan_mode: Enable plan mode (recommended for complex queries)

    Returns:
        CompiledStateGraph (LangGraph agent) ready for invocation.
    """
    if not DEERFLOW_AVAILABLE:
        raise RuntimeError("deerflow-harness is required.")

    model = create_chat_model(name=model_name, thinking_enabled=True)
    tools = get_deerflow_tools()

    lead_system_prompt = _build_lead_system_prompt()

    features = RuntimeFeatures(
        sandbox=False,
        summarization=False,
        auto_title=True,
        memory=True,
        vision=False,
        subagent=False,
        loop_detection=True,
        token_budget=False,
    )

    agent = create_deerflow_agent(
        model=model,
        tools=tools,
        system_prompt=lead_system_prompt,
        features=features,
        plan_mode=plan_mode,
        state_schema=ThreadState,
        name="biashara-lead",
    )

    logger.info(f"Created Biashara Lead Agent (model={model_name}, tools={len(tools)}, plan_mode={plan_mode})")
    return agent


# ── BiasharaAgentFactory ────────────────────────────────────────────────────

class BiasharaAgentFactory:
    """Factory for creating and managing Biashara DeerFlow agents.

    Replaces the custom AgentFactory for DeerFlow-powered deployments.
    Maintains a registry of created agents for the FastAPI app lifecycle.
    """

    def __init__(self):
        self._agents: dict[str, Any] = {}
        self._lead_agent: Any = None

    def create_domain_agent(
        self,
        agent_name: str,
        model_name: str = "deepseek-chat",
        plan_mode: bool = False,
    ) -> Any:
        """Create a domain-specific agent and register it."""
        agent = create_biashara_agent(
            agent_name=agent_name,
            model_name=model_name,
            plan_mode=plan_mode,
        )
        self._agents[agent_name] = agent
        return agent

    def create_lead_agent(
        self,
        model_name: str = "deepseek-reasoner",
        plan_mode: bool = True,
    ) -> Any:
        """Create the lead orchestrator agent."""
        self._lead_agent = create_biashara_lead_agent(
            model_name=model_name,
            plan_mode=plan_mode,
        )
        return self._lead_agent

    def get_agent(self, agent_name: str) -> Any | None:
        """Get a registered agent by name."""
        return self._agents.get(agent_name)

    def get_lead_agent(self) -> Any | None:
        """Get the lead agent."""
        return self._lead_agent

    def list_agents(self) -> list[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    async def shutdown(self) -> None:
        """Shutdown all agents (no-op for LangGraph agents, but interface-compatible)."""
        self._agents.clear()
        self._lead_agent = None
        logger.info("BiasharaAgentFactory shutdown complete")


# ── System Prompts ──────────────────────────────────────────────────────────

def _default_system_prompt(agent_name: str) -> str:
    """Generate a default system prompt for a Biashara domain agent."""
    prompts = {
        "research": (
            "You are a market research specialist for Kenya's informal economy. "
            "Use the soko_pulse tool to analyze demand, prices, and trends for "
            "products in informal markets (dukas, kiosks, mama mbogas). "
            "Provide actionable insights backed by statistical analysis."
        ),
        "credit": (
            "You are a credit risk analyst for informal businesses in Kenya. "
            "Use the alama_score tool to compute credit scores (300-850), assess "
            "default risk, and recommend credit limits. Apply Heckman correction "
            "for selection bias when analyzing enhanced/full tier data."
        ),
        "distribution": (
            "You are a distribution strategist for FMCG companies in East Africa. "
            "Use the distribution_gap and fmcg_intelligence tools to identify "
            "underserved markets, optimize routes, and recommend expansion strategies."
        ),
        "fmcg": (
            "You are an FMCG intelligence analyst specializing in informal channels. "
            "Use the fmcg_intelligence tool to track sales in dukas, kiosks, and "
            "markets. Provide insights on route-to-market optimization and "
            "competitive positioning."
        ),
        "health": (
            "You are a health economics analyst for Kenya's informal economy. "
            "Use the worker_intelligence tool to assess business health scores, "
            "credit readiness, and worker segmentation data."
        ),
        "development": (
            "You are an African development intelligence analyst. Analyze GDP "
            "estimation, inflation tracking, tax base expansion, and business "
            "cycles for East African economies using Biashara intelligence tools."
        ),
    }
    return prompts.get(agent_name, (
        "You are a Biashara Intelligence agent. Use the available tools to "
        "analyze Kenya's informal economy and provide actionable insights."
    ))


def _build_lead_system_prompt() -> str:
    """Build the system prompt for the lead orchestrator agent."""
    return """You are the Biashara Intelligence Lead Agent — the primary orchestrator for Kenya's informal economy intelligence platform.

## Your Role
You coordinate specialized intelligence tools to answer complex questions about Kenya's informal economy (dukas, kiosks, mama mbogas, informal traders).

## Available Tools

### 1. `soko_pulse` — FMCG Demand Forecasting
- Demand trends, price intelligence, seasonal patterns
- Parameters: product_category, product_name, region, tier, lookback_days

### 2. `alama_score` — Credit Scoring
- Transaction-based credit scores (300-850) for informal businesses
- Parameters: business_id, lookback_days, query_tier

### 3. `distribution_gap` — Distribution Gap Analysis
- Identifies underserved markets and expansion opportunities
- Parameters: product_category, region, tier

### 4. `fmcg_intelligence` — FMCG Channel Intelligence
- Informal channel sales, route optimization, competitive pricing
- Parameters: query_type, company, product_category, region

### 5. `worker_intelligence` — Worker/Business Health
- Health scores, credit readiness, segmentation, benchmarks
- Parameters: query_type, worker_id, business_type, region

## Decision Framework

1. **Simple queries**: Use the single most relevant tool
2. **Complex queries**: Use multiple tools and synthesize results
3. **Ambiguous queries**: Use `ask_clarification` to understand the user's intent
4. **Multi-step research**: Create a plan with `write_todos` and execute systematically

## Response Style
- Lead with the key insight (bottom-line up front)
- Support with data from tools
- Provide actionable recommendations
- Use Kenyan context (KSh, local markets, cultural factors)
- Be concise but thorough

## Data Privacy
All data is k-anonymized (k≥10) and differentially private. Never expose individual trader identities.
"""
