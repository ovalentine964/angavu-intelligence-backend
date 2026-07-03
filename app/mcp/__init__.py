"""
MCP (Model Context Protocol) integration for Angavu Intelligence.

Exposes intelligence products, worker data, and agent communication
as MCP-compatible tools for LLM agents and external integrations.
"""

from app.mcp.server import MCPServer, get_mcp_server

__all__ = ["MCPServer", "get_mcp_server"]
