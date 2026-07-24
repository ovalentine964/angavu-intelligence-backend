"""
Protocol Transport Routes — A2A HTTP/SSE + MCP Streamable HTTP.

Registers protocol routes on the FastAPI app for agent-to-agent
communication and MCP tool access.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, FastAPI

logger = structlog.get_logger(__name__)


def register_protocol_routes(app: FastAPI, prefix: str = "/api/v1") -> None:
    """Register protocol transport routes on the FastAPI app."""
    router = APIRouter(prefix="/protocols", tags=["Agent Protocols"])

    @router.get("/health")
    async def protocols_health():
        return {
            "status": "ok",
            "protocols": ["a2a-http", "mcp-streamable-http"],
        }

    @router.get("/a2a/status")
    async def a2a_status():
        return {
            "protocol": "a2a",
            "transport": "http-sse",
            "status": "available",
        }

    app.include_router(router, prefix=prefix)
    logger.info("protocol_routes_registered")
