"""
Agents Domain — /api/v1/agents/*

Aggregates:
    - Agent Router              (app.api.agent_router)
    - Agent Loops               (app.api.agent_loops)
    - Model Router / Inference  (app.api.model_router)
    - Agent Harness             (app.api.harness)
    - MCP Protocol              (app.mcp.router)
"""

from fastapi import APIRouter

from app.api.agent_loops import router as _loops
from app.api.agent_router import router as _agents
from app.api.harness import router as _harness
from app.api.model_router import router as _model
from app.mcp.router import router as _mcp

agents_router = APIRouter(tags=["Agents"])
agents_router.include_router(_agents)
agents_router.include_router(_loops)
agents_router.include_router(_model)
agents_router.include_router(_harness)
agents_router.include_router(_mcp)
