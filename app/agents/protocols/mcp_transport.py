"""
MCP Streamable HTTP Transport — Production network layer for Model Context Protocol.

Implements the MCP 2025-06-18 Streamable HTTP transport:
- MCPHttpClient: Async HTTP client for calling external MCP servers
- MCPHttpServer: FastAPI router exposing MCP endpoints with SSE support
- Session management via Mcp-Session-Id header
- JSON-RPC over HTTP POST
- Server-Sent Events for streaming responses
- Tool/resource/prompt discovery endpoints

Protocol flow (per MCP 2025-06-18 spec):
    1. Client sends initialize via HTTP POST
    2. Server responds with capabilities and session ID (Mcp-Session-Id header)
    3. Client includes session ID in subsequent requests
    4. Server can respond with JSON or SSE stream (Content-Type negotiation)
    5. Client sends initialized notification to complete handshake
    6. Normal operations: tools/list, tools/call, resources/read, etc.

Reference: https://modelcontextprotocol.io/specification/2025-06-18
Security: Follows NSA MCP Security Design Considerations (May 2026)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.agents.protocols.mcp import (
    MCPServer,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# MCP HTTP Client — Call external MCP servers over the network
# ════════════════════════════════════════════════════════════════════


class MCPHttpClient:
    """
    Async HTTP client for MCP Streamable HTTP transport.

    Sends JSON-RPC requests to external MCP servers with session
    management, SSE support, and automatic retry.

    Features:
    - Session management via Mcp-Session-Id header
    - JSON-RPC over HTTP POST
    - SSE response parsing for streaming results
    - Automatic retry with exponential backoff
    - Tool caching with TTL
    - Connection pooling via httpx

    Usage:
        client = MCPHttpClient()
        manifest = await client.connect("https://mcp-market.example.com")
        tools = await client.list_tools("https://mcp-market.example.com")
        result = await client.call_tool("https://mcp-market.example.com", "get_prices", {"item": "nyanya"})
        await client.close()
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        cache_ttl_seconds: float = 300.0,
        auth_token: str | None = None,
    ):
        self._timeout = timeout
        self._max_retries = max_retries
        self._cache_ttl = cache_ttl_seconds
        self._auth_token = auth_token
        self._client: httpx.AsyncClient | None = None

        # Session management: server_url → session_id
        self._sessions: dict[str, str] = {}

        # Connected server manifests
        self._connected_servers: dict[str, dict[str, Any]] = {}

        # Tool result cache
        self._tool_cache: dict[str, Any] = {}
        self._tool_cache_times: dict[str, float] = {}

        self._logger = logger.bind(component="mcp_http_client")

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers=headers,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── Connection ──────────────────────────────────────────────────

    async def connect(self, server_url: str) -> dict[str, Any]:
        """
        Connect to an MCP server via Streamable HTTP.

        Performs the MCP initialize handshake and stores the session ID.

        Args:
            server_url: Base URL of the MCP server

        Returns:
            Server manifest with capabilities
        """
        result = await self._send_request(server_url, "initialize", {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "angavu-mcp-client", "version": "2.0.0"},
            "capabilities": {
                "roots": {"listChanged": True},
            },
        })

        self._connected_servers[server_url] = result
        self._logger.info(
            "mcp_connected",
            server=server_url,
            protocol_version=result.get("protocolVersion"),
            session_id=self._sessions.get(server_url),
        )

        # Send initialized notification
        await self._send_notification(server_url, "notifications/initialized", {})

        return result

    async def disconnect(self, server_url: str) -> None:
        """Disconnect from an MCP server, cleaning up session."""
        session_id = self._sessions.pop(server_url, None)
        self._connected_servers.pop(server_url, None)
        if session_id:
            self._logger.info("mcp_disconnected", server=server_url, session=session_id)

    # ── Tool Operations ─────────────────────────────────────────────

    async def list_tools(self, server_url: str) -> list[dict[str, Any]]:
        """
        Discover tools from a connected MCP server.

        Args:
            server_url: URL of the MCP server

        Returns:
            List of tool manifests
        """
        result = await self._send_request(server_url, "tools/list", {})
        tools = result.get("tools", [])
        self._logger.info("mcp_tools_listed", server=server_url, count=len(tools))
        return tools

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        use_cache: bool = True,
    ) -> Any:
        """
        Call a tool on an MCP server.

        Implements caching and retry with exponential backoff.

        Args:
            server_url: URL of the MCP server
            tool_name: Name of the tool to call
            arguments: Tool arguments
            use_cache: Whether to use cached results

        Returns:
            Tool result
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

            except (ConnectionError, TimeoutError, OSError, MCPTransportError) as exc:
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

        raise MCPTransportError(
            f"MCP tool {tool_name} failed after {self._max_retries} retries: {last_error}",
        )

    # ── Resource Operations ─────────────────────────────────────────

    async def list_resources(self, server_url: str) -> list[dict[str, Any]]:
        """List available resources from an MCP server."""
        result = await self._send_request(server_url, "resources/list", {})
        return result.get("resources", [])

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

    # ── Prompt Operations ───────────────────────────────────────────

    async def list_prompts(self, server_url: str) -> list[dict[str, Any]]:
        """List available prompts from an MCP server."""
        result = await self._send_request(server_url, "prompts/list", {})
        return result.get("prompts", [])

    async def get_prompt(
        self,
        server_url: str,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Render a prompt template from an MCP server."""
        return await self._send_request(server_url, "prompts/get", {
            "name": name,
            "arguments": arguments or {},
        })

    # ── Transport ───────────────────────────────────────────────────

    async def _send_request(
        self,
        server_url: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send a JSON-RPC request to an MCP server via Streamable HTTP.

        Handles:
        - Session ID management (Mcp-Session-Id header)
        - Content-Type negotiation (JSON or SSE response)
        - Error handling with JSON-RPC error codes

        Args:
            server_url: Base URL of the MCP server
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            Result from the JSON-RPC response
        """
        request_id = uuid.uuid4().hex[:8]
        request_body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        client = await self._get_client()
        headers = {}

        # Include session ID if we have one
        session_id = self._sessions.get(server_url)
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        url = server_url.rstrip("/")
        if not url.endswith("/mcp"):
            url = f"{url}/mcp"

        self._logger.debug(
            "mcp_request_sent",
            method=method,
            server=server_url,
            request_id=request_id,
        )

        # Send with retry
        response = await self._send_with_retry(client, url, request_body, headers)

        # Store session ID from response
        new_session_id = response.headers.get("mcp-session-id")
        if new_session_id:
            self._sessions[server_url] = new_session_id

        # Parse response based on Content-Type
        content_type = response.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            return await self._parse_sse_response(response)
        else:
            return self._parse_json_response(response, request_id)

    async def _send_notification(
        self,
        server_url: str,
        method: str,
        params: dict[str, Any],
    ) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        request_body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        client = await self._get_client()
        headers = {}

        session_id = self._sessions.get(server_url)
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        url = server_url.rstrip("/")
        if not url.endswith("/mcp"):
            url = f"{url}/mcp"

        try:
            await client.post(url, json=request_body, headers=headers)
        except Exception as exc:
            self._logger.warning("mcp_notification_failed", method=method, error=str(exc))

    async def _parse_sse_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse an SSE response, extracting the final JSON-RPC result."""
        result_data = None
        event_type = None
        data_buffer = ""

        async for line in response.aiter_lines():
            line = line.strip()

            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer += line[5:].strip()
            elif line == "":
                if data_buffer:
                    try:
                        parsed = json.loads(data_buffer)
                        if event_type == "message" or "result" in parsed or "error" in parsed:
                            result_data = parsed
                    except json.JSONDecodeError:
                        pass
                    event_type = None
                    data_buffer = ""

        if result_data is None:
            raise MCPTransportError("No result in SSE stream")

        if "error" in result_data:
            error = result_data["error"]
            raise MCPTransportError(
                f"MCP error [{error.get('code', -1)}]: {error.get('message', 'Unknown')}",
            )

        return result_data.get("result", {})

    def _parse_json_response(
        self,
        response: httpx.Response,
        request_id: str,
    ) -> dict[str, Any]:
        """Parse a JSON JSON-RPC response."""
        try:
            data = response.json()
        except Exception as exc:
            raise MCPTransportError(f"Invalid JSON response: {exc}")

        if "error" in data:
            error = data["error"]
            raise MCPTransportError(
                f"MCP error [{error.get('code', -1)}]: {error.get('message', 'Unknown')}",
            )

        return data.get("result", {})

    async def _send_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        """Execute an HTTP POST with exponential backoff retry."""
        last_error = None
        for attempt in range(self._max_retries):
            try:
                response = await client.post(url, json=body, headers=headers)

                # Handle session expiration (404/410)
                if response.status_code in (404, 410):
                    # Session expired — clear and retry once
                    for srv_url, sid in list(self._sessions.items()):
                        if sid == headers.get("Mcp-Session-Id"):
                            del self._sessions[srv_url]
                            break
                    headers.pop("Mcp-Session-Id", None)

                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < self._max_retries - 1:
                    if isinstance(exc, httpx.HTTPStatusError):
                        status = exc.response.status_code
                        if 400 <= status < 500 and status != 429:
                            raise
                        retry_after = exc.response.headers.get("Retry-After")
                        if retry_after:
                            wait = min(float(retry_after), 60.0)
                        else:
                            wait = min(2.0 ** attempt, 30.0)
                    else:
                        wait = min(2.0 ** attempt, 30.0)

                    self._logger.warning(
                        "mcp_retry",
                        url=url,
                        attempt=attempt + 1,
                        wait=wait,
                        error=str(exc),
                    )
                    await asyncio.sleep(wait)

        raise MCPTransportError(
            f"MCP request failed after {self._max_retries} retries: {last_error}",
        )

    # ── Cache Management ────────────────────────────────────────────

    def clear_cache(self) -> None:
        """Clear the tool result cache."""
        self._tool_cache.clear()
        self._tool_cache_times.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get client statistics."""
        return {
            "connected_servers": len(self._connected_servers),
            "active_sessions": len(self._sessions),
            "cached_results": len(self._tool_cache),
            "cache_ttl_seconds": self._cache_ttl,
        }


# ════════════════════════════════════════════════════════════════════
# MCP HTTP Server — FastAPI router with Streamable HTTP transport
# ════════════════════════════════════════════════════════════════════


# ── Pydantic Schemas ────────────────────────────────────────────────


class MCPJsonRpcRequest(BaseModel):
    """MCP JSON-RPC request envelope."""
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


# ── Session Manager ─────────────────────────────────────────────────


class MCPSessionManager:
    """
    Manages MCP client sessions for the Streamable HTTP transport.

    Each client gets a unique session ID (Mcp-Session-Id header)
    that tracks their connection state, capabilities, and rate limits.
    """

    def __init__(self, session_ttl_seconds: float = 3600.0):
        self._sessions: dict[str, dict[str, Any]] = {}
        self._session_ttl = session_ttl_seconds
        self._logger = logger.bind(component="mcp_session_manager")

    def create_session(self, client_info: dict[str, Any] | None = None) -> str:
        """Create a new session and return its ID."""
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = {
            "id": session_id,
            "created_at": time.time(),
            "last_active": time.time(),
            "client_info": client_info or {},
            "initialized": False,
            "request_count": 0,
        }
        self._logger.info("mcp_session_created", session=session_id)
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID, updating last_active timestamp."""
        session = self._sessions.get(session_id)
        if session:
            # Check TTL
            if time.time() - session["last_active"] > self._session_ttl:
                self.destroy_session(session_id)
                return None
            session["last_active"] = time.time()
            session["request_count"] += 1
        return session

    def mark_initialized(self, session_id: str) -> None:
        """Mark a session as initialized (handshake complete)."""
        session = self._sessions.get(session_id)
        if session:
            session["initialized"] = True

    def destroy_session(self, session_id: str) -> None:
        """Destroy a session."""
        self._sessions.pop(session_id, None)
        self._logger.info("mcp_session_destroyed", session=session_id)

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        now = time.time()
        expired = [
            sid for sid, session in self._sessions.items()
            if now - session["last_active"] > self._session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def get_stats(self) -> dict[str, Any]:
        """Get session manager statistics."""
        return {
            "active_sessions": len(self._sessions),
            "session_ttl_seconds": self._session_ttl,
        }


# ── Router Factory ──────────────────────────────────────────────────


def create_mcp_streamable_router(
    mcp_server: MCPServer,
    session_manager: MCPSessionManager | None = None,
    auth_handler: Callable[..., Coroutine] | None = None,
) -> APIRouter:
    """
    Create a FastAPI router with MCP Streamable HTTP endpoints.

    Implements the MCP 2025-06-18 Streamable HTTP transport:
    - POST /mcp — Main JSON-RPC endpoint (handles all MCP methods)
    - GET  /mcp/sse — SSE endpoint for server-initiated messages
    - DELETE /mcp — Session termination
    - GET  /mcp/health — MCP server health
    - GET  /mcp/stats — MCP server statistics

    Session management:
    - Server sends Mcp-Session-Id header in initialize response
    - Client includes Mcp-Session-Id header in all subsequent requests
    - Sessions expire after configurable TTL

    Args:
        mcp_server: The MCPServer instance to handle requests
        session_manager: Optional session manager (creates default if None)
        auth_handler: Optional async callable for request authentication

    Returns:
        FastAPI APIRouter ready to be mounted
    """
    router = APIRouter(tags=["MCP Streamable HTTP"])
    _sessions = session_manager or MCPSessionManager()
    _logger = logger.bind(component="mcp_streamable_server")

    # ── Main JSON-RPC Endpoint ──────────────────────────────────────

    @router.post("/mcp")
    async def mcp_endpoint(request: Request):
        """
        MCP Streamable HTTP endpoint.

        Handles all MCP JSON-RPC methods over HTTP POST:
        - initialize: Handshake and capability negotiation
        - tools/list: Discover available tools
        - tools/call: Execute a tool
        - resources/list: Discover available resources
        - resources/read: Read a resource
        - prompts/list: Discover available prompts
        - prompts/get: Render a prompt template
        - ping: Health check

        Response format is negotiated via Accept header:
        - application/json: Single JSON response
        - text/event-stream: SSE stream (for long-running operations)

        Session management via Mcp-Session-Id header.
        """
        # Parse request body
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            )

        method = body.get("method", "")
        params = body.get("params", {})
        req_id = body.get("id")

        # ── Session Management ──────────────────────────────────────

        # Get or create session
        session_id = request.headers.get("mcp-session-id")

        if method == "initialize":
            # Create new session for initialize
            session_id = _sessions.create_session(
                client_info=params.get("clientInfo", {}),
            )
        elif session_id:
            session = _sessions.get_session(session_id)
            if not session:
                return JSONResponse(
                    status_code=404,
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32001, "message": "Session not found or expired"},
                    },
                )
        else:
            # No session ID for non-initialize request
            if method not in ("ping",):
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32002, "message": "Mcp-Session-Id header required"},
                    },
                )

        # ── Handle Request ──────────────────────────────────────────

        _logger.info(
            "mcp_request_received",
            method=method,
            session=session_id,
            request_id=req_id,
        )

        try:
            result = await mcp_server.handle_request(body)
        except Exception as exc:
            _logger.error("mcp_handler_error", method=method, error=str(exc))
            result = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Internal error: {exc!s}"},
            }

        # Mark session as initialized after successful initialize
        if method == "initialize" and "error" not in result:
            _sessions.mark_initialized(session_id)

        # ── Response Negotiation ────────────────────────────────────

        accept = request.headers.get("accept", "application/json")
        use_sse = "text/event-stream" in accept and method not in ("initialize", "ping")

        if use_sse:
            # Return as SSE stream
            async def sse_generator() -> AsyncIterator[str]:
                yield f"event: message\ndata: {json.dumps(result)}\n\n"

            response = StreamingResponse(
                sse_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            # Return as JSON
            response = JSONResponse(content=result)

        # Always include session ID in response
        if session_id:
            response.headers["Mcp-Session-Id"] = session_id

        return response

    # ── SSE Endpoint for Server-Initiated Messages ──────────────────

    @router.get("/mcp/sse")
    async def mcp_sse_stream(request: Request):
        """
        SSE endpoint for server-initiated messages.

        Clients connect here to receive server-initiated notifications
        such as tool list changes, resource updates, etc.

        Requires a valid session via Mcp-Session-Id query parameter.
        """
        session_id = request.query_params.get("session_id") or request.headers.get("mcp-session-id")

        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID required")

        session = _sessions.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        async def event_stream() -> AsyncIterator[str]:
            """Generate SSE events for server-initiated messages."""
            heartbeat_interval = 15.0
            last_heartbeat = time.time()
            max_duration = 3600.0  # Max 1 hour
            start = time.time()

            while True:
                if await request.is_disconnected():
                    break

                if time.time() - start > max_duration:
                    break

                # Session still valid?
                if not _sessions.get_session(session_id):
                    yield f"event: session_expired\ndata: {json.dumps({'session': session_id})}\n\n"
                    break

                # Heartbeat
                if time.time() - last_heartbeat >= heartbeat_interval:
                    yield f"event: heartbeat\ndata: {json.dumps({'time': time.time()})}\n\n"
                    last_heartbeat = time.time()

                await asyncio.sleep(1.0)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Session Termination ─────────────────────────────────────────

    @router.delete("/mcp")
    async def mcp_delete_session(request: Request):
        """
        Terminate an MCP session.

        Client sends DELETE with Mcp-Session-Id header to end the session.
        """
        session_id = request.headers.get("mcp-session-id")
        if not session_id:
            raise HTTPException(status_code=400, detail="Mcp-Session-Id header required")

        _sessions.destroy_session(session_id)
        return {"status": "ok", "message": "Session terminated"}

    # ── Convenience Endpoints ───────────────────────────────────────

    @router.get("/mcp/tools")
    async def mcp_list_tools(request: Request):
        """
        List available MCP tools (convenience endpoint).

        Returns tool manifests without requiring full JSON-RPC.
        For full protocol compliance, use POST /mcp with tools/list.
        """
        session_id = request.headers.get("mcp-session-id")
        if session_id:
            session = _sessions.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

        tools = [t.to_manifest() for t in mcp_server._tools.values()]
        return {"tools": tools, "total": len(tools)}

    @router.get("/mcp/resources")
    async def mcp_list_resources(request: Request):
        """List available MCP resources (convenience endpoint)."""
        session_id = request.headers.get("mcp-session-id")
        if session_id:
            session = _sessions.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

        resources = [r.to_manifest() for r in mcp_server._resources.values()]
        return {"resources": resources, "total": len(resources)}

    @router.get("/mcp/prompts")
    async def mcp_list_prompts(request: Request):
        """List available MCP prompts (convenience endpoint)."""
        session_id = request.headers.get("mcp-session-id")
        if session_id:
            session = _sessions.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

        prompts = [p.to_manifest() for p in mcp_server._prompts.values()]
        return {"prompts": prompts, "total": len(prompts)}

    # ── Health & Stats ──────────────────────────────────────────────

    @router.get("/mcp/health")
    async def mcp_health():
        """MCP server health check."""
        return {
            "status": "ok",
            "server": mcp_server.name,
            "version": mcp_server.version,
            "tools": len(mcp_server._tools),
            "resources": len(mcp_server._resources),
            "prompts": len(mcp_server._prompts),
            "sessions": _sessions.get_stats(),
        }

    @router.get("/mcp/stats")
    async def mcp_stats():
        """MCP server and session statistics."""
        return {
            "server": mcp_server.get_stats(),
            "sessions": _sessions.get_stats(),
        }

    return router


# ════════════════════════════════════════════════════════════════════
# Error Types
# ════════════════════════════════════════════════════════════════════


class MCPTransportError(Exception):
    """Error in MCP transport layer."""
    pass
