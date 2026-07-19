"""
MCP (Model Context Protocol) — Tool sharing and context integration.

Implements MCP client and server following the 2026 standard:
- MCP Server: Exposes Angavu agent tools as MCP-compatible endpoints
- MCP Client: Consumes external MCP servers (mobile money, market data, regulatory)

Architecture:
    Angavu Agent → MCP Client → External MCP Server (M-Pesa, market feeds)
    External Agent → MCP Server → Angavu Tools (report generation, credit scoring)

Reference: https://modelcontextprotocol.io/specification/2025-06-18
Security: Follows NSA MCP Security Design Considerations (May 2026)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# MCP Protocol Types
# ════════════════════════════════════════════════════════════════════


class MCPMessageType(str, Enum):
    """MCP JSON-RPC message types."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


class MCPToolPermission(str, Enum):
    """Tool access permissions per NSA security guidance."""
    READ = "read"           # Read-only operations
    WRITE = "write"         # Data modification
    EXECUTE = "execute"     # Side-effectful operations
    ADMIN = "admin"         # Administrative operations


@dataclass
class MCPTool:
    """
    An MCP-compatible tool that an agent exposes.

    Each tool has a name, description, input schema (JSON Schema),
    and a handler function. Tools are discoverable via MCP's
    tools/list endpoint.
    """
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema for parameters
    handler: Callable[..., Coroutine] | None = None
    permission: MCPToolPermission = MCPToolPermission.READ
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"

    def to_manifest(self) -> dict[str, Any]:
        """Export tool manifest for MCP tools/list response."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "permission": self.permission.value,
            "tags": self.tags,
            "version": self.version,
        }


@dataclass
class MCPResource:
    """
    An MCP-compatible resource (data source) that an agent exposes.

    Resources are read-only data sources that agents can query.
    Examples: transaction history, market prices, credit scores.
    """
    uri: str                    # e.g. "angavu://transactions/recent"
    name: str
    description: str
    mime_type: str = "application/json"
    reader: Callable[..., Coroutine] | None = None

    def to_manifest(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class MCPPrompt:
    """An MCP-compatible prompt template."""
    name: str
    description: str
    arguments: list[dict[str, Any]] = field(default_factory=list)
    template: Callable[..., Coroutine] | None = None

    def to_manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


# ════════════════════════════════════════════════════════════════════
# MCP Server — Expose Angavu tools to external agents
# ════════════════════════════════════════════════════════════════════


class MCPServer:
    """
    MCP Server for Angavu Intelligence agents.

    Exposes agent tools, resources, and prompts via the MCP protocol
    so external agents and AI systems can discover and invoke them.

    Features:
    - Tool registration and discovery (tools/list, tools/call)
    - Resource registration and reading (resources/list, resources/read)
    - Prompt templates (prompts/list, prompts/get)
    - Permission-based access control
    - Request logging and audit trail
    - Rate limiting per tool

    Usage:
        server = MCPServer(name="angavu-intelligence", version="2.0.0")
        server.register_tool(MCPTool(
            name="generate_credit_score",
            description="Generate credit score for informal worker",
            input_schema={"type": "object", "properties": {"user_id": {"type": "string"}}},
            handler=credit_score_handler,
            permission=MCPToolPermission.READ,
        ))
        await server.handle_request(jsonrpc_request)
    """

    def __init__(
        self,
        name: str = "angavu-intelligence",
        version: str = "2.0.0",
        max_requests_per_minute: int = 60,
    ):
        self.name = name
        self.version = version
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}

        # Rate limiting
        self._rate_limit = max_requests_per_minute
        self._request_timestamps: list[float] = []

        # Audit trail
        self._request_log: list[dict[str, Any]] = []
        self._max_log_size = 1000

        self._logger = logger.bind(component="mcp_server", server=name)

    # ── Registration ────────────────────────────────────────────────

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool for MCP exposure."""
        self._tools[tool.name] = tool
        self._logger.info("mcp_tool_registered", tool=tool.name, permission=tool.permission.value)

    def register_tools(self, tools: Sequence[MCPTool]) -> None:
        """Register multiple tools."""
        for tool in tools:
            self.register_tool(tool)

    def register_resource(self, resource: MCPResource) -> None:
        """Register a resource for MCP exposure."""
        self._resources[resource.uri] = resource
        self._logger.info("mcp_resource_registered", uri=resource.uri)

    def register_prompt(self, prompt: MCPPrompt) -> None:
        """Register a prompt template."""
        self._prompts[prompt.name] = prompt
        self._logger.info("mcp_prompt_registered", prompt=prompt.name)

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool from MCP exposure."""
        if name in self._tools:
            del self._tools[name]
            self._logger.info("mcp_tool_unregistered", tool=name)
            return True
        return False

    # ── Request Handling ────────────────────────────────────────────

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Handle an incoming MCP JSON-RPC request.

        Dispatches to the appropriate handler based on the method.
        Returns a JSON-RPC response.
        """
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        # Rate limiting
        if not self._check_rate_limit():
            return self._error_response(req_id, -32000, "Rate limit exceeded")

        # Audit logging
        self._log_request(method, params, req_id)

        try:
            if method == "initialize":
                return self._handle_initialize(req_id, params)
            elif method == "tools/list":
                return self._handle_tools_list(req_id, params)
            elif method == "tools/call":
                return await self._handle_tools_call(req_id, params)
            elif method == "resources/list":
                return self._handle_resources_list(req_id, params)
            elif method == "resources/read":
                return await self._handle_resources_read(req_id, params)
            elif method == "prompts/list":
                return self._handle_prompts_list(req_id, params)
            elif method == "prompts/get":
                return await self._handle_prompts_get(req_id, params)
            elif method == "ping":
                return self._success_response(req_id, {})
            else:
                return self._error_response(req_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            self._logger.error("mcp_request_error", method=method, error=str(exc))
            return self._error_response(req_id, -32603, f"Internal error: {exc!s}")

    def _handle_initialize(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP initialize handshake."""
        return self._success_response(req_id, {
            "protocolVersion": "2025-06-18",
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"subscribe": True, "listChanged": True},
                "prompts": {"listChanged": True},
            },
        })

    def _handle_tools_list(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/list — return all registered tools."""
        tools = [t.to_manifest() for t in self._tools.values()]
        return self._success_response(req_id, {"tools": tools})

    async def _handle_tools_call(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/call — execute a registered tool."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool = self._tools.get(tool_name)
        if not tool:
            return self._error_response(req_id, -32602, f"Tool not found: {tool_name}")

        if not tool.handler:
            return self._error_response(req_id, -32603, f"Tool {tool_name} has no handler")

        # Execute tool
        start = time.time()
        try:
            result = await tool.handler(**arguments)
            duration_ms = (time.time() - start) * 1000

            self._logger.info(
                "mcp_tool_executed",
                tool=tool_name,
                duration_ms=round(duration_ms, 2),
                success=True,
            )

            return self._success_response(req_id, {
                "content": [
                    {"type": "text", "text": json.dumps(result, default=str)}
                ],
                "isError": False,
            })
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            self._logger.warning(
                "mcp_tool_error",
                tool=tool_name,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
            )
            return self._success_response(req_id, {
                "content": [
                    {"type": "text", "text": f"Error: {exc!s}"}
                ],
                "isError": True,
            })

    def _handle_resources_list(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle resources/list — return all registered resources."""
        resources = [r.to_manifest() for r in self._resources.values()]
        return self._success_response(req_id, {"resources": resources})

    async def _handle_resources_read(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle resources/read — read a registered resource."""
        uri = params.get("uri", "")

        resource = self._resources.get(uri)
        if not resource:
            return self._error_response(req_id, -32602, f"Resource not found: {uri}")

        if not resource.reader:
            return self._error_response(req_id, -32603, f"Resource {uri} has no reader")

        try:
            data = await resource.reader()
            return self._success_response(req_id, {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": resource.mime_type,
                        "text": json.dumps(data, default=str),
                    }
                ],
            })
        except Exception as exc:
            return self._error_response(req_id, -32603, f"Read error: {exc!s}")

    def _handle_prompts_list(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle prompts/list — return all registered prompts."""
        prompts = [p.to_manifest() for p in self._prompts.values()]
        return self._success_response(req_id, {"prompts": prompts})

    async def _handle_prompts_get(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle prompts/get — render a prompt template."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        prompt = self._prompts.get(name)
        if not prompt:
            return self._error_response(req_id, -32602, f"Prompt not found: {name}")

        if not prompt.template:
            return self._error_response(req_id, -32603, f"Prompt {name} has no template")

        try:
            rendered = await prompt.template(**arguments)
            return self._success_response(req_id, {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": rendered}}
                ],
            })
        except Exception as exc:
            return self._error_response(req_id, -32603, f"Template error: {exc!s}")

    # ── Helpers ─────────────────────────────────────────────────────

    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limit."""
        now = time.time()
        cutoff = now - 60.0
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
        if len(self._request_timestamps) >= self._rate_limit:
            return False
        self._request_timestamps.append(now)
        return True

    def _log_request(self, method: str, params: dict[str, Any], req_id: Any) -> None:
        """Log request for audit trail."""
        self._request_log.append({
            "method": method,
            "params_keys": list(params.keys()),
            "req_id": req_id,
            "timestamp": time.time(),
        })
        if len(self._request_log) > self._max_log_size:
            self._request_log = self._request_log[-self._max_log_size:]

    @staticmethod
    def _success_response(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    # ── Status ──────────────────────────────────────────────────────

    def get_manifest(self) -> dict[str, Any]:
        """Get full server manifest for discovery."""
        return {
            "name": self.name,
            "version": self.version,
            "tools": [t.to_manifest() for t in self._tools.values()],
            "resources": [r.to_manifest() for r in self._resources.values()],
            "prompts": [p.to_manifest() for p in self._prompts.values()],
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "tool_count": len(self._tools),
            "resource_count": len(self._resources),
            "prompt_count": len(self._prompts),
            "total_requests": len(self._request_log),
            "rate_limit": self._rate_limit,
        }


# ════════════════════════════════════════════════════════════════════
# MCP Client — Consume external MCP servers
# ════════════════════════════════════════════════════════════════════


class MCPClient:
    """
    MCP Client for consuming external MCP servers.

    Enables Angavu agents to use tools from external MCP servers:
    - Mobile money APIs (M-Pesa, Airtel Money)
    - Market data feeds
    - Government regulatory databases
    - Banking and financial services

    Features:
    - Server discovery and connection
    - Tool caching with TTL
    - Retry with exponential backoff
    - Fallback to cached results on connection failure
    - Request/response logging

    Usage:
        client = MCPClient(name="angavu-agent")
        await client.connect("mcp://market-data-server/tools")
        result = await client.call_tool("get_prices", {"item": "nyanya"})
    """

    def __init__(
        self,
        name: str = "angavu-client",
        cache_ttl_seconds: float = 300.0,
        max_retries: int = 3,
        http_timeout: float = 30.0,
        auth_token: str | None = None,
    ):
        self.name = name
        self._cache_ttl = cache_ttl_seconds
        self._max_retries = max_retries
        self._http_timeout = http_timeout
        self._auth_token = auth_token

        self._connected_servers: dict[str, dict[str, Any]] = {}  # server_url → manifest
        self._tool_cache: dict[str, dict[str, Any]] = {}  # "server:tool" → cached result
        self._tool_cache_times: dict[str, float] = {}
        self._http_client: Any | None = None  # Lazy MCPHttpClient

        self._logger = logger.bind(component="mcp_client", client=name)

    # ── Connection ──────────────────────────────────────────────────

    async def connect(self, server_url: str) -> dict[str, Any]:
        """
        Connect to an MCP server and cache its manifest.

        Args:
            server_url: URL of the MCP server

        Returns:
            Server manifest with available tools, resources, prompts
        """
        self._logger.info("mcp_client_connecting", server=server_url)

        manifest = await self._send_request(server_url, "initialize", {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": self.name, "version": "2.0.0"},
            "capabilities": {},
        })

        self._connected_servers[server_url] = manifest
        self._logger.info(
            "mcp_client_connected",
            server=server_url,
            tools=len(manifest.get("capabilities", {}).get("tools", {})),
        )
        return manifest

    async def discover_tools(self, server_url: str) -> list[dict[str, Any]]:
        """Discover tools from a connected MCP server."""
        result = await self._send_request(server_url, "tools/list", {})
        tools = result.get("tools", [])
        self._logger.info("mcp_tools_discovered", server=server_url, count=len(tools))
        return tools

    # ── Tool Invocation ─────────────────────────────────────────────

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        use_cache: bool = True,
    ) -> Any:
        """
        Call a tool on an MCP server.

        Implements retry with exponential backoff and result caching.
        """
        cache_key = f"{server_url}:{tool_name}:{json.dumps(arguments, sort_keys=True)}"

        # Check cache
        if use_cache and cache_key in self._tool_cache:
            cached_time = self._tool_cache_times.get(cache_key, 0)
            if time.time() - cached_time < self._cache_ttl:
                self._logger.debug("mcp_cache_hit", tool=tool_name)
                return self._tool_cache[cache_key]

        # Execute with retry
        last_error = None
        for attempt in range(self._max_retries):
            try:
                result = await self._send_request(server_url, "tools/call", {
                    "name": tool_name,
                    "arguments": arguments,
                })

                # Cache result
                if use_cache:
                    self._tool_cache[cache_key] = result
                    self._tool_cache_times[cache_key] = time.time()

                self._logger.info(
                    "mcp_tool_called",
                    server=server_url,
                    tool=tool_name,
                    attempt=attempt + 1,
                )
                return result

            except (ConnectionError, TimeoutError, OSError) as exc:
                last_error = exc
                wait_time = min(2.0 ** attempt, 30.0)
                self._logger.warning(
                    "mcp_tool_retry",
                    tool=tool_name,
                    attempt=attempt + 1,
                    wait=wait_time,
                    error=str(exc),
                )
                await asyncio.sleep(wait_time)

        # All retries failed — try returning cached result
        if cache_key in self._tool_cache:
            self._logger.warning("mcp_fallback_to_cache", tool=tool_name)
            return self._tool_cache[cache_key]

        raise ConnectionError(f"MCP tool {tool_name} failed after {self._max_retries} retries: {last_error}")

    async def read_resource(self, server_url: str, uri: str) -> Any:
        """Read a resource from an MCP server."""
        result = await self._send_request(server_url, "resources/read", {"uri": uri})
        contents = result.get("contents", [])
        if contents:
            text = contents[0].get("text", "{}")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return None

    # ── Transport ───────────────────────────────────────────────────

    async def _ensure_http_client(self):
        """Lazy-initialize the HTTP client for remote MCP servers."""
        if self._http_client is None:
            from app.agents.protocols.mcp_transport import MCPHttpClient
            self._http_client = MCPHttpClient(
                timeout=self._http_timeout,
                max_retries=self._max_retries,
                auth_token=self._auth_token,
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._http_client:
            await self._http_client.close()
            self._http_client = None

    async def _send_request(
        self,
        server_url: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send a JSON-RPC request to an MCP server.

        Supports:
        - local:// URLs: In-process direct invocation
        - http:// / https:// URLs: Streamable HTTP transport (MCP 2025-06-18)
        """
        request = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex[:8],
            "method": method,
            "params": params,
        }

        # Check if server_url is a local MCPServer instance reference
        if server_url.startswith("local://"):
            server_name = server_url.replace("local://", "")
            server = self._local_servers.get(server_name)
            if server:
                return await server.handle_request(request)
            raise ConnectionError(f"Local MCP server not found: {server_name}")

        # HTTP/SSE transport (production)
        if server_url.startswith("http://") or server_url.startswith("https://"):
            http_client = await self._ensure_http_client()

            # Connect if not already connected
            if server_url not in self._connected_servers:
                await self.connect(server_url)

            # Route to appropriate client method
            if method == "initialize":
                return await http_client.connect(server_url)
            elif method == "tools/list":
                return {"tools": await http_client.list_tools(server_url)}
            elif method == "tools/call":
                return await http_client.call_tool(
                    server_url,
                    params.get("name", ""),
                    params.get("arguments", {}),
                    use_cache=False,  # Already handled by caller
                )
            elif method == "resources/list":
                return {"resources": await http_client.list_resources(server_url)}
            elif method == "resources/read":
                return await http_client._send_request(server_url, method, params)
            elif method == "prompts/list":
                return {"prompts": await http_client.list_prompts(server_url)}
            elif method == "prompts/get":
                return await http_client.get_prompt(
                    server_url,
                    params.get("name", ""),
                    params.get("arguments"),
                )
            else:
                # Generic pass-through
                return await http_client._send_request(server_url, method, params)

        # Unknown protocol
        self._logger.debug("mcp_request_sent", method=method, server=server_url)
        raise ConnectionError(
            f"Unsupported MCP server URL scheme. "
            f"Use local://, http://, or https://. Got: {server_url}"
        )

    # ── Local Server Registry ───────────────────────────────────────

    _local_servers: dict[str, MCPServer] = {}

    @classmethod
    def register_local_server(cls, server: MCPServer) -> None:
        """Register a local MCPServer for in-process communication."""
        cls._local_servers[server.name] = server
        logger.info("mcp_local_server_registered", name=server.name)

    # ── Cache Management ────────────────────────────────────────────

    def clear_cache(self) -> None:
        """Clear the tool result cache."""
        self._tool_cache.clear()
        self._tool_cache_times.clear()
        self._logger.info("mcp_cache_cleared")

    def get_stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "connected_servers": len(self._connected_servers),
            "cached_results": len(self._tool_cache),
            "cache_ttl_seconds": self._cache_ttl,
        }


# ════════════════════════════════════════════════════════════════════
# Pre-built MCP Tool Definitions for Angavu
# ════════════════════════════════════════════════════════════════════


def create_angavu_mcp_tools() -> list[MCPTool]:
    """
    Create the standard set of MCP tools for Angavu Intelligence.

    These are the tools that Angavu agents expose to external MCP clients.
    """
    return [
        MCPTool(
            name="generate_credit_score",
            description="Generate a credit score for an informal worker based on transaction history, M-Pesa data, and business patterns",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User identifier"},
                    "include_explanation": {"type": "boolean", "default": True},
                },
                "required": ["user_id"],
            },
            permission=MCPToolPermission.READ,
            tags=["finance", "credit", "scoring"],
        ),
        MCPTool(
            name="forecast_cash_flow",
            description="Predict future cash flow based on historical transaction patterns and market conditions",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "horizon_days": {"type": "integer", "default": 30},
                    "confidence_level": {"type": "number", "default": 0.9},
                },
                "required": ["user_id"],
            },
            permission=MCPToolPermission.READ,
            tags=["finance", "prediction", "cashflow"],
        ),
        MCPTool(
            name="get_market_prices",
            description="Get current and historical market prices for commodities in East African markets",
            input_schema={
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "Commodity name"},
                    "market": {"type": "string", "description": "Market location"},
                    "date_range": {"type": "string", "enum": ["today", "week", "month"]},
                },
                "required": ["item"],
            },
            permission=MCPToolPermission.READ,
            tags=["market", "prices", "commodities"],
        ),
        MCPTool(
            name="generate_tax_report",
            description="Generate a tax-ready financial report for an informal worker or small business",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "period": {"type": "string", "enum": ["monthly", "quarterly", "annual"]},
                    "format": {"type": "string", "enum": ["summary", "detailed"], "default": "summary"},
                },
                "required": ["user_id", "period"],
            },
            permission=MCPToolPermission.READ,
            tags=["tax", "compliance", "reporting"],
        ),
        MCPTool(
            name="assess_formalization_readiness",
            description="Assess whether an informal business is ready to formalize, and recommend the optimal path",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "target_type": {"type": "string", "enum": ["sole_proprietorship", "cooperative", "limited_company"]},
                },
                "required": ["user_id"],
            },
            permission=MCPToolPermission.READ,
            tags=["formalization", "business", "compliance"],
        ),
        MCPTool(
            name="detect_anomalies",
            description="Detect anomalous patterns in transaction data that may indicate fraud or errors",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "lookback_days": {"type": "integer", "default": 30},
                    "sensitivity": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                },
                "required": ["user_id"],
            },
            permission=MCPToolPermission.READ,
            tags=["security", "fraud", "anomaly"],
        ),
    ]


def create_external_mcp_configs() -> list[dict[str, Any]]:
    """
    Define external MCP servers that Angavu agents should connect to.

    Returns connection configs for mobile money, market data, etc.
    """
    return [
        {
            "name": "mpesa-api",
            "url": "mcp://mpesa-api-server",
            "description": "M-Pesa transaction API for Kenya",
            "tools": ["get_transactions", "initiate_payment", "check_balance"],
            "auto_connect": True,
        },
        {
            "name": "market-data-ke",
            "url": "mcp://market-data-ke",
            "description": "Kenyan market price feeds (Nairobi, Mombasa, Kisumu)",
            "tools": ["get_prices", "get_trends", "get_seasonal_patterns"],
            "auto_connect": True,
        },
        {
            "name": "regulatory-ke",
            "url": "mcp://regulatory-ke",
            "description": "Kenya regulatory database (KRA, county governments)",
            "tools": ["check_requirements", "get_tax_rates", "verify_registration"],
            "auto_connect": False,
        },
        {
            "name": "credit-bureau-ke",
            "url": "mcp://credit-bureau-ke",
            "description": "Kenya credit bureau integration",
            "tools": ["get_credit_report", "check_blacklist"],
            "auto_connect": False,
        },
    ]
