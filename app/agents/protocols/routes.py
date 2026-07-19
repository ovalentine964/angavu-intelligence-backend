"""
Protocol Route Registration — Wire A2A and MCP transport routers into FastAPI.

This module provides a single function to create and mount all protocol
transport routers (A2A HTTP/SSE, MCP Streamable HTTP) onto the FastAPI app.

Usage in main.py lifespan:
    from app.agents.protocols.routes import register_protocol_routes
    register_protocol_routes(app)
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from app.agents.protocols.a2a import (
    A2AServer,
    create_angavu_agent_card,
)
from app.agents.protocols.a2a_transport import create_a2a_router
from app.agents.protocols.mcp import MCPServer
from app.agents.protocols.mcp_transport import (
    MCPSessionManager,
    create_mcp_streamable_router,
)

logger = structlog.get_logger(__name__)


def register_protocol_routes(
    app: FastAPI,
    a2a_server: A2AServer | None = None,
    mcp_server: MCPServer | None = None,
    prefix: str = "/api/v1",
) -> None:
    """
    Register A2A and MCP protocol transport routers on the FastAPI app.

    Creates default servers if not provided, then mounts:
    - A2A router at {prefix}/a2a/*
    - MCP Streamable HTTP router at {prefix}/mcp-streamable/*

    Args:
        app: FastAPI application instance
        a2a_server: Optional A2AServer instance (creates default if None)
        mcp_server: Optional MCPServer instance (creates default if None)
        prefix: URL prefix for API versioning
    """
    # ── A2A Server & Router ─────────────────────────────────────────

    if a2a_server is None:
        agent_card = create_angavu_agent_card()
        a2a_server = A2AServer(agent_card=agent_card)
        logger.info("a2a_server_created", agent=agent_card.name)

    a2a_router = create_a2a_router(a2a_server)
    app.include_router(a2a_router, prefix=prefix)
    app.state.a2a_server = a2a_server

    logger.info(
        "a2a_routes_registered",
        prefix=f"{prefix}/a2a",
        capabilities=[c.name for c in a2a_server.agent_card.capabilities],
    )

    # ── MCP Streamable HTTP Router ──────────────────────────────────

    if mcp_server is None:
        mcp_server = MCPServer()
        logger.info("mcp_server_created")

    session_manager = MCPSessionManager()
    mcp_streamable_router = create_mcp_streamable_router(mcp_server, session_manager)
    # Mount under /protocol/mcp to avoid collision with existing /mcp router
    app.include_router(mcp_streamable_router, prefix=f"{prefix}/protocol")
    app.state.mcp_session_manager = session_manager

    logger.info(
        "mcp_streamable_routes_registered",
        prefix=f"{prefix}/protocol/mcp",
        tools=len(mcp_server._tools),
    )

    logger.info(
        "protocol_routes_ready",
        a2a_endpoints=[
            f"GET  {prefix}/.well-known/agent.json",
            f"POST {prefix}/a2a",
            f"GET  {prefix}/a2a/tasks/{{id}}/stream",
            f"GET  {prefix}/a2a/health",
            f"GET  {prefix}/a2a/stats",
            f"GET  {prefix}/a2a/tasks",
        ],
        mcp_endpoints=[
            f"POST   {prefix}/protocol/mcp",
            f"GET    {prefix}/protocol/mcp/sse",
            f"DELETE {prefix}/protocol/mcp",
            f"GET    {prefix}/protocol/mcp/tools",
            f"GET    {prefix}/protocol/mcp/resources",
            f"GET    {prefix}/protocol/mcp/prompts",
            f"GET    {prefix}/protocol/mcp/health",
            f"GET    {prefix}/protocol/mcp/stats",
        ],
    )
