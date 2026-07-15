"""
A2A HTTP/SSE Transport — Production network layer for Agent-to-Agent Protocol.

Implements:
- A2AHttpClient: Async HTTP client for sending tasks to external A2A agents
- A2AHttpServer: FastAPI router exposing A2A server endpoints
- SSE streaming for long-running task status updates
- Task status polling with exponential backoff

Protocol flow:
    1. Client discovers agent via /.well-known/agent.json
    2. Client POSTs JSON-RPC task to agent endpoint
    3. Server returns task ID immediately (async execution)
    4. Client polls via tasks/get or subscribes via SSE stream

Reference: https://github.com/google/A2A (v1.0, 2026)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Callable, Coroutine, Dict, List, Optional

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agents.protocols.a2a import (
    A2AAgentCard,
    A2ACapability,
    A2AMessage,
    A2AMessageRole,
    A2APart,
    A2APartType,
    A2AServer,
    A2ATask,
    A2ATaskState,
    A2ATaskStatus,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# A2A HTTP Client — Send tasks to external agents over the network
# ════════════════════════════════════════════════════════════════════


class A2AHttpClient:
    """
    Async HTTP client for A2A protocol communication.

    Sends JSON-RPC requests to external A2A agents and receives
    responses via direct HTTP or SSE streaming.

    Features:
    - Agent discovery via /.well-known/agent.json
    - Task submission via HTTP POST (tasks/send)
    - Task polling via HTTP POST (tasks/get)
    - SSE subscription for streaming updates (tasks/sendSubscribe)
    - Automatic retry with exponential backoff
    - Request timeouts and cancellation

    Usage:
        client = A2AHttpClient(timeout=30.0, max_retries=3)
        card = await client.discover_agent("https://tax-agent.example.com")
        task = await client.send_task(card, message="File my tax return", capability="file_return")
        status = await client.get_task_status(card, task_id=task.task_id)
        async for update in client.stream_task_updates(card, task_id=task.task_id):
            print(update)
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        auth_token: Optional[str] = None,
    ):
        self._timeout = timeout
        self._max_retries = max_retries
        self._auth_token = auth_token
        self._client: Optional[httpx.AsyncClient] = None
        self._discovered_agents: Dict[str, A2AAgentCard] = {}

        self._logger = logger.bind(component="a2a_http_client")

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
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

    # ── Discovery ───────────────────────────────────────────────────

    async def discover_agent(self, base_url: str) -> A2AAgentCard:
        """
        Discover an A2A agent by fetching its Agent Card.

        Fetches from https://<host>/.well-known/agent.json

        Args:
            base_url: Base URL of the agent (e.g. "https://tax-agent.example.com")

        Returns:
            A2AAgentCard with agent metadata and capabilities
        """
        base_url = base_url.rstrip("/")
        well_known_url = f"{base_url}/.well-known/agent.json"

        client = await self._get_client()
        response = await self._send_with_retry(
            client.get,
            well_known_url,
        )
        data = response.json()

        # Parse capabilities
        capabilities = []
        for cap_data in data.get("capabilities", []):
            capabilities.append(A2ACapability(
                name=cap_data.get("name", ""),
                description=cap_data.get("description", ""),
                input_schema=cap_data.get("inputSchema", {}),
                output_schema=cap_data.get("outputSchema", {}),
                tags=cap_data.get("tags", []),
            ))

        card = A2AAgentCard(
            agent_id=data.get("agentId", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            url=data.get("url", base_url),
            version=data.get("version", "1.0.0"),
            capabilities=capabilities,
            authentication=data.get("authentication"),
            default_input_modes=data.get("defaultInputModes", ["text"]),
            default_output_modes=data.get("defaultOutputModes", ["text"]),
            metadata=data.get("metadata", {}),
        )

        self._discovered_agents[card.agent_id] = card
        self._logger.info(
            "a2a_agent_discovered",
            agent_id=card.agent_id,
            name=card.name,
            url=well_known_url,
            capabilities=[c.name for c in capabilities],
        )
        return card

    # ── Task Operations ─────────────────────────────────────────────

    async def send_task(
        self,
        agent_card: A2AAgentCard,
        message: str,
        capability: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> A2ATask:
        """
        Send a task to an external A2A agent via HTTP POST.

        Args:
            agent_card: Target agent's card (from discover_agent)
            message: Text message describing the task
            capability: Specific capability to invoke
            data: Structured data payload
            metadata: Additional metadata

        Returns:
            A2ATask with initial status from the server
        """
        # Build message parts
        parts = [A2APart(type=A2APartType.TEXT, text=message)]
        if data:
            parts.append(A2APart(type=A2APartType.DATA, data=data))

        task_message = A2AMessage(role=A2AMessageRole.USER, parts=parts)

        # Build JSON-RPC request
        task_metadata = metadata or {}
        if capability:
            task_metadata["capability"] = capability

        request = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex[:8],
            "method": "tasks/send",
            "params": {
                "id": uuid.uuid4().hex[:16],
                "message": task_message.to_dict(),
                "metadata": task_metadata,
            },
        }

        # Send HTTP POST
        endpoint = agent_card.url or f"https://{agent_card.agent_id}"
        response = await self._post_jsonrpc(endpoint, request)
        result = response.get("result", {})

        # Parse response into A2ATask
        task = A2ATask(
            task_id=result.get("id", request["params"]["id"]),
            session_id=result.get("sessionId"),
            status=A2ATaskStatus(
                state=A2ATaskState(result.get("status", {}).get("state", "submitted")),
            ),
            history=[task_message],
            metadata=task_metadata,
        )

        self._logger.info(
            "a2a_task_sent",
            task_id=task.task_id,
            target=agent_card.name,
            capability=capability,
            state=task.status.state.value,
        )
        return task

    async def get_task_status(
        self,
        agent_card: A2AAgentCard,
        task_id: str,
    ) -> A2ATask:
        """
        Poll task status from an external A2A agent.

        Args:
            agent_card: Target agent's card
            task_id: ID of the task to check

        Returns:
            A2ATask with current status
        """
        request = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex[:8],
            "method": "tasks/get",
            "params": {"id": task_id},
        }

        endpoint = agent_card.url or f"https://{agent_card.agent_id}"
        response = await self._post_jsonrpc(endpoint, request)
        result = response.get("result", {})

        return A2ATask(
            task_id=result.get("id", task_id),
            session_id=result.get("sessionId"),
            status=A2ATaskStatus(
                state=A2ATaskState(result.get("status", {}).get("state", "submitted")),
                progress=result.get("status", {}).get("progress"),
            ),
            metadata=result.get("metadata", {}),
        )

    async def cancel_task(
        self,
        agent_card: A2AAgentCard,
        task_id: str,
    ) -> A2ATask:
        """
        Cancel a running task on an external A2A agent.

        Args:
            agent_card: Target agent's card
            task_id: ID of the task to cancel

        Returns:
            A2ATask with canceled status
        """
        request = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex[:8],
            "method": "tasks/cancel",
            "params": {"id": task_id},
        }

        endpoint = agent_card.url or f"https://{agent_card.agent_id}"
        response = await self._post_jsonrpc(endpoint, request)
        result = response.get("result", {})

        return A2ATask(
            task_id=result.get("id", task_id),
            status=A2ATaskStatus(
                state=A2ATaskState(result.get("status", {}).get("state", "canceled")),
            ),
        )

    # ── SSE Streaming ───────────────────────────────────────────────

    async def stream_task_updates(
        self,
        agent_card: A2AAgentCard,
        task_id: str,
        timeout: float = 300.0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Subscribe to task updates via Server-Sent Events.

        Yields task status updates as they arrive from the server.
        The stream ends when the task reaches a terminal state
        (completed, failed, canceled).

        Args:
            agent_card: Target agent's card
            task_id: ID of the task to stream
            timeout: Maximum time to wait for updates (seconds)

        Yields:
            Dict with task status updates
        """
        endpoint = agent_card.url or f"https://{agent_card.agent_id}"
        sse_url = f"{endpoint.rstrip('/')}/a2a/tasks/{task_id}/stream"

        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        client = await self._get_client()
        start_time = time.time()

        try:
            async with client.stream("GET", sse_url, headers=headers, timeout=httpx.Timeout(timeout)) as response:
                response.raise_for_status()
                event_type = None
                data_buffer = ""

                async for line in response.aiter_lines():
                    # Check timeout
                    if time.time() - start_time > timeout:
                        self._logger.warning("a2a_sse_timeout", task_id=task_id)
                        break

                    line = line.strip()

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_buffer += line[5:].strip()
                    elif line == "":
                        # Empty line = end of SSE event
                        if data_buffer:
                            try:
                                update = json.loads(data_buffer)
                                update["_event_type"] = event_type or "message"
                                yield update

                                # Stop on terminal state
                                state = update.get("status", {}).get("state", "")
                                if state in ("completed", "failed", "canceled"):
                                    return
                            except json.JSONDecodeError:
                                self._logger.warning(
                                    "a2a_sse_parse_error",
                                    data=data_buffer[:200],
                                )
                            finally:
                                event_type = None
                                data_buffer = ""

        except httpx.TimeoutException:
            self._logger.warning("a2a_sse_connection_timeout", task_id=task_id)
        except httpx.HTTPStatusError as exc:
            self._logger.error(
                "a2a_sse_http_error",
                task_id=task_id,
                status=exc.response.status_code,
            )
            raise

    # ── Internal Helpers ────────────────────────────────────────────

    async def _post_jsonrpc(
        self,
        endpoint: str,
        request: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send a JSON-RPC POST request with retry logic."""
        endpoint = endpoint.rstrip("/")
        client = await self._get_client()
        response = await self._send_with_retry(
            client.post,
            endpoint,
            json=request,
        )
        data = response.json()

        # Check for JSON-RPC error
        if "error" in data:
            error = data["error"]
            raise A2ATransportError(
                code=error.get("code", -1),
                message=error.get("message", "Unknown error"),
            )

        return data

    async def _send_with_retry(
        self,
        method: Callable,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Execute an HTTP request with exponential backoff retry."""
        last_error = None
        for attempt in range(self._max_retries):
            try:
                response = await method(url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < self._max_retries - 1:
                    # Don't retry on 4xx client errors (except 429)
                    if isinstance(exc, httpx.HTTPStatusError):
                        status = exc.response.status_code
                        if 400 <= status < 500 and status != 429:
                            raise
                        # Respect Retry-After header
                        retry_after = exc.response.headers.get("Retry-After")
                        if retry_after:
                            wait = min(float(retry_after), 60.0)
                        else:
                            wait = min(2.0 ** attempt, 30.0)
                    else:
                        wait = min(2.0 ** attempt, 30.0)

                    self._logger.warning(
                        "a2a_retry",
                        url=url,
                        attempt=attempt + 1,
                        wait=wait,
                        error=str(exc),
                    )
                    await asyncio.sleep(wait)

        raise A2ATransportError(
            code=-1,
            message=f"Request failed after {self._max_retries} retries: {last_error}",
        )


# ════════════════════════════════════════════════════════════════════
# A2A HTTP Server — FastAPI router for A2A endpoints
# ════════════════════════════════════════════════════════════════════


# ── Pydantic Schemas ────────────────────────────────────────────────


class A2AJsonRpcRequest(BaseModel):
    """A2A JSON-RPC request envelope."""
    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class A2ATaskSendParams(BaseModel):
    """Parameters for tasks/send."""
    id: Optional[str] = None
    sessionId: Optional[str] = None
    message: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class A2ATaskGetParams(BaseModel):
    """Parameters for tasks/get."""
    id: str


class A2ATaskCancelParams(BaseModel):
    """Parameters for tasks/cancel."""
    id: str


# ── Router Factory ──────────────────────────────────────────────────


def create_a2a_router(
    a2a_server: A2AServer,
    auth_handler: Optional[Callable[..., Coroutine]] = None,
) -> APIRouter:
    """
    Create a FastAPI router with A2A protocol endpoints.

    Mounts the following endpoints:
    - GET  /.well-known/agent.json  — Agent Card discovery
    - POST /a2a                     — JSON-RPC endpoint (tasks/send, tasks/get, tasks/cancel)
    - GET  /a2a/tasks/{task_id}/stream — SSE stream for task updates
    - GET  /a2a/health              — A2A server health
    - GET  /a2a/stats               — A2A server statistics

    Args:
        a2a_server: The A2AServer instance to handle requests
        auth_handler: Optional async callable for request authentication

    Returns:
        FastAPI APIRouter ready to be mounted
    """
    router = APIRouter(tags=["A2A"])
    _logger = logger.bind(component="a2a_http_server")

    # ── Agent Card Discovery ────────────────────────────────────────

    @router.get("/.well-known/agent.json")
    async def agent_card():
        """
        A2A Agent Card discovery endpoint.

        Returns the agent's identity, capabilities, and endpoint URL.
        External agents fetch this to discover what this agent can do.
        """
        return a2a_server.agent_card.to_dict()

    # ── JSON-RPC Endpoint ───────────────────────────────────────────

    @router.post("/a2a")
    async def a2a_jsonrpc(request: A2AJsonRpcRequest):
        """
        A2A JSON-RPC endpoint.

        Handles all A2A protocol methods:
        - tasks/send: Submit a new task for async execution
        - tasks/get: Poll task status
        - tasks/cancel: Cancel a running task
        - agent/card: Get agent card (alternative to .well-known)

        Request body is a JSON-RPC 2.0 envelope.
        """
        rpc_request = {
            "jsonrpc": request.jsonrpc,
            "id": request.id,
            "method": request.method,
            "params": request.params or {},
        }

        _logger.info(
            "a2a_rpc_received",
            method=request.method,
            id=request.id,
        )

        result = await a2a_server.handle_request(rpc_request)

        # Check for errors
        if "error" in result:
            error = result["error"]
            status_code = 400 if error.get("code", 0) >= -32099 else 500
            return JSONResponse(status_code=status_code, content=result)

        return result

    # ── SSE Stream ──────────────────────────────────────────────────

    @router.get("/a2a/tasks/{task_id}/stream")
    async def task_stream(task_id: str, request: Request):
        """
        Server-Sent Events stream for task status updates.

        Clients subscribe to receive real-time updates as a task
        progresses through its lifecycle (submitted → working → completed).

        The stream ends when the task reaches a terminal state
        (completed, failed, canceled) or the client disconnects.

        SSE format:
            event: task_update
            data: {"id": "...", "status": {"state": "working", "progress": 0.5}}
        """
        task = a2a_server._tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        async def event_generator() -> AsyncIterator[str]:
            """Generate SSE events for task status updates."""
            last_state = None
            last_progress = None
            heartbeat_interval = 15.0  # Send heartbeat every 15s
            last_heartbeat = time.time()
            max_duration = 600.0  # Max 10 minutes
            start = time.time()

            while True:
                # Check client disconnect
                if await request.is_disconnected():
                    _logger.info("a2a_sse_client_disconnected", task_id=task_id)
                    break

                # Check timeout
                if time.time() - start > max_duration:
                    _logger.warning("a2a_sse_max_duration", task_id=task_id)
                    break

                # Get current task state
                current_task = a2a_server._tasks.get(task_id)
                if not current_task:
                    break

                current_state = current_task.status.state.value
                current_progress = current_task.status.progress

                # Send update if state changed
                if current_state != last_state or current_progress != last_progress:
                    update_data = json.dumps({
                        "id": task_id,
                        "status": current_task.status.to_dict(),
                        "artifacts": [a.to_dict() for a in current_task.artifacts],
                    })
                    yield f"event: task_update\ndata: {update_data}\n\n"
                    last_state = current_state
                    last_progress = current_progress

                # Terminal state — end stream
                if current_state in ("completed", "failed", "canceled"):
                    yield f"event: task_end\ndata: {json.dumps({'id': task_id, 'state': current_state})}\n\n"
                    break

                # Heartbeat to keep connection alive
                if time.time() - last_heartbeat >= heartbeat_interval:
                    yield f"event: heartbeat\ndata: {json.dumps({'time': time.time()})}\n\n"
                    last_heartbeat = time.time()

                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    # ── Health & Stats ──────────────────────────────────────────────

    @router.get("/a2a/health")
    async def a2a_health():
        """A2A server health check."""
        return {
            "status": "ok",
            "agent": a2a_server.agent_card.name,
            "version": a2a_server.agent_card.version,
            "capabilities": [c.name for c in a2a_server.agent_card.capabilities],
        }

    @router.get("/a2a/stats")
    async def a2a_stats():
        """A2A server statistics."""
        return a2a_server.get_stats()

    @router.get("/a2a/tasks")
    async def list_tasks(limit: int = 20):
        """List recent A2A tasks."""
        return {"tasks": a2a_server.get_tasks(limit=limit)}

    return router


# ════════════════════════════════════════════════════════════════════
# Error Types
# ════════════════════════════════════════════════════════════════════


class A2ATransportError(Exception):
    """Error in A2A transport layer."""

    def __init__(self, code: int = -1, message: str = "Unknown error"):
        self.code = code
        self.message = message
        super().__init__(f"A2A Error [{code}]: {message}")
