"""
MCP Server — Model Context Protocol implementation.

Provides a lightweight MCP server for tool registration
and execution, enabling LLM agents to discover and use tools.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class MCPTool:
    """A tool registered with the MCP server."""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., Coroutine[Any, Any, Any]] | None = None


class MCPServer:
    """
    Lightweight MCP server for tool management.

    Provides tool registration, discovery, and execution
    for LLM agent integration.
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._request_count = 0

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool with the MCP server."""
        self._tools[name] = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema or {},
            handler=handler,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]

    async def execute_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Tool '{name}' not found"}
        if not tool.handler:
            return {"error": f"Tool '{name}' has no handler"}
        self._request_count += 1
        return await tool.handler(**arguments)

    def get_health(self) -> dict[str, Any]:
        """Get MCP server health status."""
        return {
            "status": "ok",
            "tools_registered": len(self._tools),
            "total_requests": self._request_count,
        }


# Global singleton
_mcp_server: MCPServer | None = None


def get_mcp_server() -> MCPServer:
    """Get the global MCP server instance."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server
