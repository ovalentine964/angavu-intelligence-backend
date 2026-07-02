"""
MCP Client — Connect to external MCP servers.

Allows Biashara Intelligence to call tools exposed by other MCP servers,
enabling agentic workflows where our backend can delegate to external
intelligence sources or services.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class MCPClientError(Exception):
    """MCP client error."""

    def __init__(self, message: str, code: int = -1, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MCPClient:
    """
    MCP client for connecting to external MCP servers.

    Supports HTTP/SSE transport for remote MCP servers.
    """

    def __init__(
        self,
        server_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._request_id = 0
        self._session: Optional[httpx.AsyncClient] = None
        self._initialized = False
        self._server_info: Optional[Dict[str, Any]] = None
        self._capabilities: Optional[Dict[str, Any]] = None

    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session."""
        if self._session is None or self._session.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._session

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a JSON-RPC request to the MCP server."""
        session = await self._get_session()
        req_id = self._next_id()

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        start = time.time()
        try:
            response = await session.post(
                f"{self.server_url}/mcp",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as e:
            raise MCPClientError(
                f"HTTP error {e.response.status_code}: {e.response.text}",
                code=e.response.status_code,
            )
        except httpx.RequestError as e:
            raise MCPClientError(f"Request failed: {str(e)}")

        elapsed = (time.time() - start) * 1000
        logger.debug(
            "mcp_client_request",
            method=method,
            elapsed_ms=round(elapsed, 1),
            status="ok" if "result" in result else "error",
        )

        if "error" in result:
            err = result["error"]
            raise MCPClientError(
                err.get("message", "Unknown error"),
                code=err.get("code", -1),
                data=err.get("data"),
            )

        return result.get("result", {})

    # ── Protocol Methods ────────────────────────────────────────────

    async def initialize(self) -> Dict[str, Any]:
        """Initialize connection with the remote MCP server."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {
                "name": "biashara-intelligence-client",
                "version": "1.0.0",
            },
        })
        self._initialized = True
        self._server_info = result.get("serverInfo")
        self._capabilities = result.get("capabilities")
        logger.info(
            "mcp_client_initialized",
            server=self._server_info,
        )
        return result

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List tools available on the remote server."""
        if not self._initialized:
            await self.initialize()
        result = await self._send_request("tools/list")
        return result.get("tools", [])

    async def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a tool on the remote MCP server.

        Args:
            name: Tool name to call.
            arguments: Tool arguments.

        Returns:
            Tool result dict with 'content' and optional 'isError'.
        """
        if not self._initialized:
            await self.initialize()

        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        return result

    async def ping(self) -> bool:
        """Ping the remote server."""
        try:
            await self._send_request("ping")
            return True
        except MCPClientError:
            return False

    # ── Lifecycle ───────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the client connection."""
        if self._session and not self._session.is_closed:
            await self._session.aclose()
            self._session = None
        self._initialized = False

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, *args):
        await self.close()


# ── Convenience ─────────────────────────────────────────────────────


async def call_external_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: Dict[str, Any],
    api_key: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    One-shot convenience function to call a tool on an external MCP server.

    Args:
        server_url: URL of the external MCP server.
        tool_name: Tool to call.
        arguments: Tool arguments.
        api_key: Optional API key for authentication.
        timeout: Request timeout in seconds.

    Returns:
        Tool result.
    """
    async with MCPClient(server_url, api_key=api_key, timeout=timeout) as client:
        return await client.call_tool(tool_name, arguments)
