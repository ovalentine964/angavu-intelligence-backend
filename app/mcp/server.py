"""
MCP Server — Main MCP protocol handler.

Implements the JSON-RPC based Model Context Protocol server:
- tools/list: Enumerate available tools
- tools/call: Execute a tool with arguments
- initialize: Server capability negotiation
- ping: Health check

Supports both stdio (for local MCP clients) and HTTP/SSE (for remote).
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.config import MCPServerConfig, MCPToolDefinition, get_mcp_config
from app.mcp.tools.intelligence import INTELLIGENCE_TOOLS, handle_intelligence_tool
from app.mcp.tools.worker_data import WORKER_DATA_TOOLS, handle_worker_data_tool
from app.mcp.tools.agent_communication import AGENT_TOOLS, handle_agent_tool

logger = structlog.get_logger(__name__)


class MCPServer:
    """
    MCP (Model Context Protocol) server for Biashara Intelligence.

    Handles JSON-RPC requests per the MCP specification and dispatches
    tool calls to the appropriate service layers.
    """

    def __init__(self, config: Optional[MCPServerConfig] = None):
        self.config = config or get_mcp_config()
        self._tools: Dict[str, MCPToolDefinition] = {}
        self._initialized = False
        self._request_count = 0
        self._error_count = 0
        self._start_time = time.time()

        # Register all tools
        self._register_tools()

    def _register_tools(self) -> None:
        """Register all tool definitions."""
        for tool in INTELLIGENCE_TOOLS:
            self._tools[tool.name] = tool
        for tool in WORKER_DATA_TOOLS:
            self._tools[tool.name] = tool
        for tool in AGENT_TOOLS:
            self._tools[tool.name] = tool
        logger.info("mcp_tools_registered", count=len(self._tools))

    # ── Protocol Methods ────────────────────────────────────────────

    async def handle_request(
        self,
        request: Dict[str, Any],
        buyer_id: str,
        db: AsyncSession,
        app_state: Any = None,
    ) -> Dict[str, Any]:
        """
        Handle an MCP JSON-RPC request.

        Args:
            request: JSON-RPC request dict with method, params, id.
            buyer_id: Authenticated buyer/requester ID.
            db: Database session.
            app_state: FastAPI app.state for agent access.

        Returns:
            JSON-RPC response dict.
        """
        self._request_count += 1
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "notifications/initialized":
                # Client acknowledgment — no response needed
                return {"_ack": True}
            elif method == "tools/list":
                result = await self._handle_tools_list(params)
            elif method == "tools/call":
                result = await self._handle_tools_call(params, buyer_id, db, app_state)
            elif method == "ping":
                result = {"status": "pong"}
            else:
                return self._error_response(req_id, -32601, f"Method not found: {method}")

            return self._success_response(req_id, result)

        except Exception as e:
            self._error_count += 1
            logger.error("mcp_request_error", method=method, error=str(e), exc_info=True)
            return self._error_response(req_id, -32603, f"Internal error: {str(e)}")

    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize handshake."""
        self._initialized = True
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": self.config.server_info,
        }

    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all available tools."""
        tools = [tool.to_schema() for tool in self._tools.values()]
        return {"tools": tools}

    async def _handle_tools_call(
        self,
        params: Dict[str, Any],
        buyer_id: str,
        db: AsyncSession,
        app_state: Any = None,
    ) -> Dict[str, Any]:
        """Execute a tool call."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            }

        tool_def = self._tools[tool_name]

        # Dispatch to the correct handler based on category
        if tool_def.category == "intelligence":
            return await handle_intelligence_tool(tool_name, arguments, buyer_id, db)
        elif tool_def.category == "worker_data":
            return await handle_worker_data_tool(tool_name, arguments, buyer_id, db)
        elif tool_def.category == "agent_communication":
            return await handle_agent_tool(tool_name, arguments, buyer_id, app_state)
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"No handler for category: {tool_def.category}"}],
            }

    # ── Response Helpers ────────────────────────────────────────────

    def _success_response(self, req_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error_response(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    # ── Health / Stats ──────────────────────────────────────────────

    def get_health(self) -> Dict[str, Any]:
        """Return server health status."""
        uptime = time.time() - self._start_time
        return {
            "status": "ok",
            "server": self.config.server_info,
            "initialized": self._initialized,
            "tools_registered": len(self._tools),
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "uptime_seconds": round(uptime, 1),
            "categories": list(set(t.category for t in self._tools.values())),
        }

    def get_tools_summary(self) -> List[Dict[str, str]]:
        """Return a summary of all tools (name + description)."""
        return [
            {"name": t.name, "description": t.description, "category": t.category}
            for t in self._tools.values()
        ]


# ── Singleton ───────────────────────────────────────────────────────

_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """Get or create the singleton MCP server."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server
