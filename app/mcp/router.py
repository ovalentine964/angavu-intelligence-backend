"""
MCP Router — API endpoints for MCP protocol.

Provides REST endpoints for MCP tool discovery and execution.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/mcp", tags=["MCP Protocol"])


class ToolCallRequest(BaseModel):
    """Request to execute an MCP tool."""
    name: str
    arguments: dict[str, Any] = {}


@router.get("/health")
async def mcp_health():
    """MCP server health check."""
    from app.mcp.server import get_mcp_server
    server = get_mcp_server()
    return server.get_health()


@router.get("/tools")
async def list_tools():
    """List all available MCP tools."""
    from app.mcp.server import get_mcp_server
    server = get_mcp_server()
    return {"tools": server.list_tools()}


@router.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    """Execute an MCP tool."""
    from app.mcp.server import get_mcp_server
    server = get_mcp_server()
    result = await server.execute_tool(request.name, request.arguments)
    return {"result": result}
