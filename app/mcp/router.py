"""
MCP API Router — FastAPI endpoints for MCP protocol.

Provides HTTP endpoints that bridge FastAPI with the MCP server:
- POST /mcp — JSON-RPC endpoint (full MCP protocol)
- POST /mcp/tools/call — Direct tool call shortcut
- GET  /mcp/tools/list — List available tools
- GET  /mcp/health — MCP server health
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_buyer_from_api_key
from app.db.database import get_db
from app.mcp.server import get_mcp_server
from app.models.buyer import Buyer

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP"])


# ── Request/Response Schemas ────────────────────────────────────────


class MCPJsonRpcRequest(BaseModel):
    """MCP JSON-RPC request."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class MCPToolCallRequest(BaseModel):
    """Direct tool call request (simplified)."""

    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class MCPToolCallResponse(BaseModel):
    """Tool call response."""

    tool_name: str
    result: Any
    is_error: bool = False
    metadata: dict[str, Any] | None = None


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("")
async def mcp_jsonrpc(
    request: MCPJsonRpcRequest,
    http_request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Full MCP JSON-RPC endpoint.

    Implements the MCP protocol over HTTP. Supports:
    - initialize: Capability negotiation
    - tools/list: Enumerate tools
    - tools/call: Execute tools
    - ping: Health check

    Requires authentication via API key (same as intelligence products).
    """
    server = get_mcp_server()

    # Extract app_state if available
    app_state = getattr(http_request.app, "state", None)

    result = await server.handle_request(
        request=request.model_dump(exclude_none=True),
        buyer_id=str(buyer.id),
        db=db,
        app_state=app_state,
    )

    # Handle notifications (no response)
    if result.get("_ack"):
        return {"status": "ok"}

    return result


@router.post("/tools/call", response_model=MCPToolCallResponse)
async def call_tool(
    req: MCPToolCallRequest,
    http_request: Request,
    buyer: Buyer = Depends(get_buyer_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Direct tool call endpoint.

    Simplified endpoint for calling MCP tools without full JSON-RPC
    wrapping. Useful for quick integrations and testing.

    **Authentication:** Same API key as intelligence products.
    """
    server = get_mcp_server()
    app_state = getattr(http_request.app, "state", None)

    # Build a JSON-RPC request internally
    rpc_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": req.tool_name,
            "arguments": req.arguments,
        },
    }

    result = await server.handle_request(
        request=rpc_request,
        buyer_id=str(buyer.id),
        db=db,
        app_state=app_state,
    )

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"].get("message", "Tool call failed"),
        )

    tool_result = result.get("result", {})

    return MCPToolCallResponse(
        tool_name=req.tool_name,
        result=tool_result.get("content", []),
        is_error=tool_result.get("isError", False),
        metadata=tool_result.get("metadata"),
    )


@router.get("/tools/list")
async def list_tools(
    buyer: Buyer = Depends(get_buyer_from_api_key),
):
    """
    List all available MCP tools.

    Returns tool names, descriptions, and categories.
    No database access required.
    """
    server = get_mcp_server()
    return {
        "tools": server.get_tools_summary(),
        "total": len(server.get_tools_summary()),
        "categories": list(set(t["category"] for t in server.get_tools_summary())),
    }


@router.get("/health")
async def mcp_health():
    """
    MCP server health check.

    Returns server status, tool count, and uptime.
    Does not require authentication.
    """
    server = get_mcp_server()
    return server.get_health()
