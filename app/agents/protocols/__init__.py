"""
Agent Protocols — MCP and A2A integration for Angavu Intelligence.

Implements:
- MCP (Model Context Protocol): Tool sharing and context between agents
- A2A (Agent-to-Agent Protocol): Cross-agent task delegation and discovery
"""

from app.agents.protocols.mcp import MCPClient, MCPServer, MCPTool, MCPResource
from app.agents.protocols.a2a import (
    A2AAgentCard,
    A2ATask,
    A2AMessage,
    A2AClient,
    A2AServer,
)

__all__ = [
    "MCPClient",
    "MCPServer",
    "MCPTool",
    "MCPResource",
    "A2AAgentCard",
    "A2ATask",
    "A2AMessage",
    "A2AClient",
    "A2AServer",
]
