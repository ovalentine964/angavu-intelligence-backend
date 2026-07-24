"""
Protocol Transport Routes — A2A HTTP/SSE + MCP Streamable HTTP.

Registers protocol-related API routes on the FastAPI application.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter


def register_protocol_routes(app: Any, prefix: str = "/api/v1") -> None:
    """Register protocol transport routes on the FastAPI app."""
    router = APIRouter(prefix="/protocols", tags=["Agent Protocols"])

    @router.get("/health")
    async def protocol_health():
        return {
            "status": "ok",
            "protocols": {
                "a2a_http": "available",
                "mcp_streamable_http": "available",
            },
        }

    @router.get("/a2a/status")
    async def a2a_status():
        return {
            "protocol": "a2a",
            "transport": "http_sse",
            "status": "available",
        }

    app.include_router(router)
