"""
MCP server configuration.

Centralizes all MCP-related settings: server metadata, tool schemas,
authentication, and rate limiting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MCPToolParameter:
    """Schema for a single tool parameter."""

    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class MCPToolDefinition:
    """Full definition of an MCP tool."""

    name: str
    description: str
    parameters: List[MCPToolParameter] = field(default_factory=list)
    category: str = "general"

    def to_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema for MCP protocol."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: Dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class MCPServerConfig:
    """MCP server configuration."""

    name: str = "biashara-intelligence"
    version: str = "1.0.0"
    description: str = (
        "Angavu Intelligence MCP Server — exposes Kenya's informal economy "
        "intelligence products, worker data, and agent communication as "
        "standard MCP tools."
    )

    # Authentication
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    require_auth: bool = True

    # Rate limiting (per API key)
    rate_limit_per_minute: int = 120
    rate_limit_burst: int = 20

    # Server capabilities
    capabilities: Dict[str, Any] = field(default_factory=lambda: {
        "tools": {},
        "resources": {},
        "prompts": {},
    })

    @property
    def server_info(self) -> Dict[str, str]:
        return {"name": self.name, "version": self.version}


# Default configuration singleton
_default_config: Optional[MCPServerConfig] = None


def get_mcp_config() -> MCPServerConfig:
    """Get or create the default MCP configuration."""
    global _default_config
    if _default_config is None:
        _default_config = MCPServerConfig(
            require_auth=os.getenv("MCP_REQUIRE_AUTH", "true").lower() == "true",
            rate_limit_per_minute=int(os.getenv("MCP_RATE_LIMIT_PER_MINUTE", "120")),
        )
    return _default_config
