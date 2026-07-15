"""
Agent Protocols — MCP and A2A integration for Angavu Intelligence.

Implements:
- MCP (Model Context Protocol): Tool sharing and context between agents
  - Streamable HTTP transport (2025-06-18 spec)
  - Session management, SSE streaming
- A2A (Agent-to-Agent Protocol): Cross-agent task delegation and discovery
  - HTTP/SSE transport for network communication
  - Task lifecycle management (submit, poll, cancel, stream)
"""

from app.agents.protocols.mcp import MCPClient, MCPServer, MCPTool, MCPResource
from app.agents.protocols.mcp_transport import (
    MCPHttpClient,
    MCPSessionManager,
    create_mcp_streamable_router,
    MCPTransportError,
)
from app.agents.protocols.a2a import (
    A2AAgentCard,
    A2ATask,
    A2AMessage,
    A2AClient,
    A2AServer,
)
from app.agents.protocols.a2a_transport import (
    A2AHttpClient,
    A2ATransportError,
    create_a2a_router,
)

__all__ = [
    # Core protocol types
    "MCPClient",
    "MCPServer",
    "MCPTool",
    "MCPResource",
    "A2AAgentCard",
    "A2ATask",
    "A2AMessage",
    "A2AClient",
    "A2AServer",
    # HTTP transport
    "MCPHttpClient",
    "MCPSessionManager",
    "create_mcp_streamable_router",
    "MCPTransportError",
    "A2AHttpClient",
    "A2ATransportError",
    "create_a2a_router",
]
