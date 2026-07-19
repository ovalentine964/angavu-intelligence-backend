"""
A2A (Agent-to-Agent Protocol) — Cross-agent task delegation and discovery.

Implements the A2A protocol standard (donated to Linux Foundation by Google Cloud)
for interoperable agent communication. Enables Angavu agents to:
- Discover and advertise capabilities to external agents
- Delegate tasks to specialized external agents
- Track task status across agent boundaries
- Communicate securely with third-party financial service agents

Architecture:
    Angavu Agent → A2A Client → External A2A Agent (tax compliance, credit bureau)
    External Agent → A2A Server → Angavu Agent (report generation, market analysis)

Reference: https://github.com/google/A2A (v1.0, 2026)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# A2A Protocol Types
# ════════════════════════════════════════════════════════════════════


class A2ATaskState(str, Enum):
    """A2A task lifecycle states."""
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


class A2AMessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"


class A2APartType(str, Enum):
    TEXT = "text"
    FILE = "file"
    DATA = "data"
    ARTIFACT = "artifact"


@dataclass
class A2APart:
    """A part of an A2A message (text, file, data, or artifact)."""
    type: A2APartType
    text: str | None = None
    data: dict[str, Any] | None = None
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type.value}
        if self.text is not None:
            d["text"] = self.text
        if self.data is not None:
            d["data"] = self.data
        if self.mime_type is not None:
            d["mimeType"] = self.mime_type
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> A2APart:
        return cls(
            type=A2APartType(data.get("type", "text")),
            text=data.get("text"),
            data=data.get("data"),
            mime_type=data.get("mimeType"),
        )


@dataclass
class A2AMessage:
    """A message in the A2A protocol."""
    role: A2AMessageRole
    parts: list[A2APart]
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "parts": [p.to_dict() for p in self.parts],
            "messageId": self.message_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> A2AMessage:
        return cls(
            role=A2AMessageRole(data["role"]),
            parts=[A2APart.from_dict(p) for p in data.get("parts", [])],
            message_id=data.get("messageId", uuid.uuid4().hex[:12]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class A2AArtifact:
    """An artifact produced by an A2A task (file, data, report)."""
    artifact_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    parts: list[A2APart] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "name": self.name,
            "description": self.description,
            "parts": [p.to_dict() for p in self.parts],
        }


@dataclass
class A2ATaskStatus:
    """Status of an A2A task."""
    state: A2ATaskState
    message: A2AMessage | None = None
    progress: float | None = None  # 0.0 - 1.0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"state": self.state.value, "updatedAt": self.updated_at}
        if self.message:
            d["message"] = self.message.to_dict()
        if self.progress is not None:
            d["progress"] = self.progress
        return d


@dataclass
class A2ATask:
    """A task in the A2A protocol."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    session_id: str | None = None
    status: A2ATaskStatus = field(default_factory=lambda: A2ATaskStatus(state=A2ATaskState.SUBMITTED))
    history: list[A2AMessage] = field(default_factory=list)
    artifacts: list[A2AArtifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "sessionId": self.session_id,
            "status": self.status.to_dict(),
            "history": [m.to_dict() for m in self.history],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "metadata": self.metadata,
        }


# ════════════════════════════════════════════════════════════════════
# Agent Card — Discovery and capability advertisement
# ════════════════════════════════════════════════════════════════════


@dataclass
class A2ACapability:
    """A capability that an A2A agent can perform."""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "tags": self.tags,
        }


@dataclass
class A2AAgentCard:
    """
    Agent Card — the A2A discovery document.

    Describes an agent's identity, capabilities, and endpoint
    so other agents can discover and delegate tasks to it.
    """
    agent_id: str
    name: str
    description: str
    url: str = ""                   # A2A endpoint URL
    version: str = "1.0.0"
    capabilities: list[A2ACapability] = field(default_factory=list)
    authentication: dict[str, Any] | None = None
    default_input_modes: list[str] = field(default_factory=lambda: ["text"])
    default_output_modes: list[str] = field(default_factory=lambda: ["text"])
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agentId": self.agent_id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "defaultInputModes": self.default_input_modes,
            "defaultOutputModes": self.default_output_modes,
            "metadata": self.metadata,
        }

    def has_capability(self, name: str) -> bool:
        return any(c.name == name for c in self.capabilities)

    def find_capability(self, name: str) -> A2ACapability | None:
        for c in self.capabilities:
            if c.name == name:
                return c
        return None


# ════════════════════════════════════════════════════════════════════
# A2A Server — Accept tasks from external agents
# ════════════════════════════════════════════════════════════════════


class A2AServer:
    """
    A2A Server for Angavu Intelligence agents.

    Accepts task requests from external agents, dispatches them
    to the appropriate Angavu agent, and returns results.

    Features:
    - Agent Card publication (/.well-known/agent.json)
    - Task lifecycle management (submit, status, cancel)
    - Streaming task updates via SSE
    - Authentication and authorization
    - Audit logging
    """

    def __init__(self, agent_card: A2AAgentCard):
        self.agent_card = agent_card
        self._tasks: dict[str, A2ATask] = {}
        self._task_handlers: dict[str, Callable[..., Coroutine]] = {}
        self._auth_handler: Callable[..., Coroutine] | None = None

        self._logger = logger.bind(component="a2a_server", agent=agent_card.name)

    # ── Handler Registration ────────────────────────────────────────

    def register_handler(self, capability_name: str, handler: Callable[..., Coroutine]) -> None:
        """Register a handler for a specific capability."""
        self._task_handlers[capability_name] = handler
        self._logger.info("a2a_handler_registered", capability=capability_name)

    def set_auth_handler(self, handler: Callable[..., Coroutine]) -> None:
        """Set authentication handler for incoming requests."""
        self._auth_handler = handler

    # ── Request Handling ────────────────────────────────────────────

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Handle an incoming A2A request.

        Routes to the appropriate handler based on the method:
        - tasks/send: Submit a new task
        - tasks/sendSubscribe: Submit and stream updates
        - tasks/get: Get task status
        - tasks/cancel: Cancel a task
        """
        method = request.get("method", "")
        params = request.get("params", {})

        # Authenticate
        if self._auth_handler:
            auth_result = await self._auth_handler(request)
            if not auth_result:
                return {"error": {"code": 401, "message": "Unauthorized"}}

        if method == "tasks/send":
            return await self._handle_task_send(params)
        elif method == "tasks/get":
            return self._handle_task_get(params)
        elif method == "tasks/cancel":
            return await self._handle_task_cancel(params)
        elif method == "agent/card":
            return {"result": self.agent_card.to_dict()}
        else:
            return {"error": {"code": -32601, "message": f"Unknown method: {method}"}}

    async def _handle_task_send(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/send — submit a new task."""
        task_id = params.get("id", uuid.uuid4().hex[:16])
        message_data = params.get("message", {})
        metadata = params.get("metadata", {})

        # Create task
        task = A2ATask(
            task_id=task_id,
            session_id=params.get("sessionId"),
            metadata=metadata,
        )

        # Parse initial message
        if message_data:
            msg = A2AMessage.from_dict(message_data)
            task.history.append(msg)

        self._tasks[task_id] = task

        # Find handler based on capability tags in metadata
        capability = metadata.get("capability", "")
        handler = self._task_handlers.get(capability)

        if not handler:
            # Try to find handler from message content
            if task.history:
                text = task.history[0].parts[0].text if task.history[0].parts else ""
                for cap_name, cap_handler in self._task_handlers.items():
                    if cap_name.lower() in text.lower():
                        handler = cap_handler
                        break

        if handler:
            # Execute asynchronously
            task.status = A2ATaskStatus(state=A2ATaskState.WORKING, progress=0.0)
            asyncio.create_task(self._execute_task(task, handler))
        else:
            task.status = A2ATaskStatus(
                state=A2ATaskState.FAILED,
                message=A2AMessage(
                    role=A2AMessageRole.AGENT,
                    parts=[A2APart(type=A2APartType.TEXT, text=f"No handler for capability: {capability}")],
                ),
            )

        self._logger.info("a2a_task_received", task_id=task_id, capability=capability)
        return {"result": task.to_dict()}

    async def _execute_task(self, task: A2ATask, handler: Callable[..., Coroutine]) -> None:
        """Execute a task asynchronously."""
        try:
            # Extract parameters from message
            params = {}
            if task.history:
                for part in task.history[0].parts:
                    if part.data:
                        params.update(part.data)
                    elif part.text:
                        params["text"] = part.text

            result = await handler(**params)

            # Create result artifact
            artifact = A2AArtifact(
                name="result",
                description="Task result",
                parts=[A2APart(
                    type=A2APartType.DATA if isinstance(result, dict) else A2APartType.TEXT,
                    text=json.dumps(result, default=str) if isinstance(result, dict) else str(result),
                    data=result if isinstance(result, dict) else None,
                )],
            )

            task.artifacts.append(artifact)
            task.status = A2ATaskStatus(
                state=A2ATaskState.COMPLETED,
                progress=1.0,
                message=A2AMessage(
                    role=A2AMessageRole.AGENT,
                    parts=[A2APart(type=A2APartType.TEXT, text="Task completed successfully")],
                ),
            )

            self._logger.info("a2a_task_completed", task_id=task.task_id)

        except Exception as exc:
            task.status = A2ATaskStatus(
                state=A2ATaskState.FAILED,
                message=A2AMessage(
                    role=A2AMessageRole.AGENT,
                    parts=[A2APart(type=A2APartType.TEXT, text=f"Task failed: {exc!s}")],
                ),
            )
            self._logger.error("a2a_task_failed", task_id=task.task_id, error=str(exc))

    def _handle_task_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/get — get task status."""
        task_id = params.get("id", "")
        task = self._tasks.get(task_id)
        if not task:
            return {"error": {"code": -32001, "message": f"Task not found: {task_id}"}}
        return {"result": task.to_dict()}

    async def _handle_task_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tasks/cancel — cancel a task."""
        task_id = params.get("id", "")
        task = self._tasks.get(task_id)
        if not task:
            return {"error": {"code": -32001, "message": f"Task not found: {task_id}"}}

        task.status = A2ATaskStatus(
            state=A2ATaskState.CANCELED,
            message=A2AMessage(
                role=A2AMessageRole.AGENT,
                parts=[A2APart(type=A2APartType.TEXT, text="Task canceled by request")],
            ),
        )
        return {"result": task.to_dict()}

    # ── Status ──────────────────────────────────────────────────────

    def get_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent tasks."""
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in tasks[:limit]]

    def get_stats(self) -> dict[str, Any]:
        states = {}
        for task in self._tasks.values():
            state = task.status.state.value
            states[state] = states.get(state, 0) + 1
        return {
            "agent": self.agent_card.name,
            "total_tasks": len(self._tasks),
            "tasks_by_state": states,
            "registered_handlers": list(self._task_handlers.keys()),
        }


# ════════════════════════════════════════════════════════════════════
# A2A Client — Delegate tasks to external agents
# ════════════════════════════════════════════════════════════════════


class A2AClient:
    """
    A2A Client for delegating tasks to external agents.

    Enables Angavu agents to discover and delegate tasks to
    external A2A-compatible agents (tax compliance, credit scoring, etc.).

    Features:
    - Agent discovery via /.well-known/agent.json
    - Task submission and polling
    - Streaming task updates
    - Multi-agent delegation (parallel and sequential)
    """

    def __init__(
        self,
        agent_name: str = "angavu-client",
        http_timeout: float = 30.0,
        http_max_retries: int = 3,
        auth_token: str | None = None,
    ):
        self.agent_name = agent_name
        self._http_timeout = http_timeout
        self._http_max_retries = http_max_retries
        self._auth_token = auth_token
        self._discovered_agents: dict[str, A2AAgentCard] = {}
        self._active_tasks: dict[str, dict[str, Any]] = {}

        self._logger = logger.bind(component="a2a_client", agent=agent_name)

    # ── Discovery ───────────────────────────────────────────────────

    async def discover_agent(self, url: str | A2AAgentCard) -> A2AAgentCard:
        """
        Discover an agent by fetching its Agent Card.

        Fetches from https://<host>/.well-known/agent.json
        For local agents, accepts direct AgentCard objects.
        """
        if isinstance(url, A2AAgentCard):
            card = url
        else:
            # Use HTTP transport for remote discovery
            from app.agents.protocols.a2a_transport import A2AHttpClient
            http_client = A2AHttpClient(
                timeout=self._http_timeout,
                max_retries=self._http_max_retries,
                auth_token=self._auth_token,
            )
            try:
                card = await http_client.discover_agent(url)
            finally:
                await http_client.close()

        self._discovered_agents[card.agent_id] = card
        self._logger.info(
            "a2a_agent_discovered",
            agent_id=card.agent_id,
            name=card.name,
            capabilities=[c.name for c in card.capabilities],
        )
        return card

    def register_agent(self, card: A2AAgentCard) -> None:
        """Register a known agent directly."""
        self._discovered_agents[card.agent_id] = card

    # ── Task Delegation ─────────────────────────────────────────────

    async def send_task(
        self,
        target_agent_id: str,
        message: str,
        capability: str | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> A2ATask:
        """
        Send a task to an external A2A agent.

        Args:
            target_agent_id: ID of the target agent
            message: Text message describing the task
            capability: Specific capability to invoke
            data: Structured data payload
            metadata: Additional metadata

        Returns:
            A2ATask with initial status
        """
        card = self._discovered_agents.get(target_agent_id)
        if not card:
            raise ValueError(f"Agent not discovered: {target_agent_id}")

        # Build message
        parts = [A2APart(type=A2APartType.TEXT, text=message)]
        if data:
            parts.append(A2APart(type=A2APartType.DATA, data=data))

        task_message = A2AMessage(
            role=A2AMessageRole.USER,
            parts=parts,
        )

        # Build request
        task_metadata = metadata or {}
        if capability:
            task_metadata["capability"] = capability

        task_id = uuid.uuid4().hex[:16]
        request = {
            "method": "tasks/send",
            "params": {
                "id": task_id,
                "message": task_message.to_dict(),
                "metadata": task_metadata,
            },
        }

        self._logger.info(
            "a2a_task_sent",
            task_id=task_id,
            target=target_agent_id,
            capability=capability,
        )

        # Store active task
        self._active_tasks[task_id] = {
            "target_agent": target_agent_id,
            "sent_at": time.time(),
            "request": request,
        }

        # Send task via HTTP transport if agent has a URL
        if card.url:
            from app.agents.protocols.a2a_transport import A2AHttpClient
            http_client = A2AHttpClient(
                timeout=self._http_timeout,
                max_retries=self._http_max_retries,
                auth_token=self._auth_token,
            )
            try:
                task = await http_client.send_task(
                    agent_card=card,
                    message=message,
                    capability=capability,
                    data=data,
                    metadata=task_metadata,
                )
                # Update task_id to match what we stored
                task.task_id = task_id
                task.history = [task_message]
                return task
            finally:
                await http_client.close()

        # Fallback for agents without URL (local-only)
        return A2ATask(
            task_id=task_id,
            status=A2ATaskStatus(state=A2ATaskState.SUBMITTED),
            history=[task_message],
            metadata=task_metadata,
        )

    async def send_task_to_server(
        self,
        server: A2AServer,
        message: str,
        capability: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> A2ATask:
        """Send a task directly to a local A2AServer instance."""
        parts = [A2APart(type=A2APartType.TEXT, text=message)]
        if data:
            parts.append(A2APart(type=A2APartType.DATA, data=data))

        task_message = A2AMessage(role=A2AMessageRole.USER, parts=parts)
        task_id = uuid.uuid4().hex[:16]

        metadata = {}
        if capability:
            metadata["capability"] = capability

        request = {
            "method": "tasks/send",
            "params": {
                "id": task_id,
                "message": task_message.to_dict(),
                "metadata": metadata,
            },
        }

        response = await server.handle_request(request)
        result = response.get("result", {})

        self._logger.info(
            "a2a_task_delegated_locally",
            task_id=task_id,
            server=server.agent_card.name,
            state=result.get("status", {}).get("state"),
        )

        # Parse response into A2ATask
        task = A2ATask(
            task_id=task_id,
            status=A2ATaskStatus(
                state=A2ATaskState(result.get("status", {}).get("state", "submitted")),
            ),
            history=[task_message],
            metadata=metadata,
        )

        # Wait for completion if task was executed synchronously
        if task.status.state == A2ATaskState.WORKING:
            for _ in range(100):  # Max 10 seconds
                await asyncio.sleep(0.1)
                get_response = await server.handle_request({
                    "method": "tasks/get",
                    "params": {"id": task_id},
                })
                task_result = get_response.get("result", {})
                state = task_result.get("status", {}).get("state", "")
                if state in ("completed", "failed", "canceled"):
                    task.status = A2ATaskStatus(state=A2ATaskState(state))
                    task.artifacts = [
                        A2AArtifact(
                            name=a.get("name", ""),
                            parts=[A2APart.from_dict(p) for p in a.get("parts", [])],
                        )
                        for a in task_result.get("artifacts", [])
                    ]
                    break

        return task

    async def poll_task(
        self,
        target_agent_id: str,
        task_id: str,
    ) -> A2ATask:
        """
        Poll task status from an external agent.

        Args:
            target_agent_id: ID of the target agent
            task_id: ID of the task to check

        Returns:
            A2ATask with current status
        """
        card = self._discovered_agents.get(target_agent_id)
        if not card:
            raise ValueError(f"Agent not discovered: {target_agent_id}")

        from app.agents.protocols.a2a_transport import A2AHttpClient
        http_client = A2AHttpClient(
            timeout=self._http_timeout,
            max_retries=self._http_max_retries,
            auth_token=self._auth_token,
        )
        try:
            return await http_client.get_task_status(card, task_id)
        finally:
            await http_client.close()

    async def cancel_task(
        self,
        target_agent_id: str,
        task_id: str,
    ) -> A2ATask:
        """
        Cancel a task on an external agent.

        Args:
            target_agent_id: ID of the target agent
            task_id: ID of the task to cancel

        Returns:
            A2ATask with canceled status
        """
        card = self._discovered_agents.get(target_agent_id)
        if not card:
            raise ValueError(f"Agent not discovered: {target_agent_id}")

        from app.agents.protocols.a2a_transport import A2AHttpClient
        http_client = A2AHttpClient(
            timeout=self._http_timeout,
            max_retries=self._http_max_retries,
            auth_token=self._auth_token,
        )
        try:
            return await http_client.cancel_task(card, task_id)
        finally:
            await http_client.close()

    # ── Parallel Delegation ─────────────────────────────────────────

    async def delegate_parallel(
        self,
        tasks: list[dict[str, Any]],
        timeout_seconds: float = 30.0,
    ) -> list[A2ATask]:
        """
        Delegate multiple tasks to different agents in parallel.

        Args:
            tasks: List of {"server": A2AServer, "message": str, "capability": str}

        Returns:
            List of completed A2ATasks
        """
        coroutines = [
            self.send_task_to_server(
                server=t["server"],
                message=t["message"],
                capability=t.get("capability"),
                data=t.get("data"),
            )
            for t in tasks
        ]

        results = await asyncio.gather(*coroutines, return_exceptions=True)

        final = []
        for r in results:
            if isinstance(r, Exception):
                final.append(A2ATask(
                    status=A2ATaskStatus(
                        state=A2ATaskState.FAILED,
                        message=A2AMessage(
                            role=A2AMessageRole.AGENT,
                            parts=[A2APart(type=A2APartType.TEXT, text=str(r))],
                        ),
                    )
                ))
            else:
                final.append(r)

        return final

    # ── Status ──────────────────────────────────────────────────────

    def get_discovered_agents(self) -> list[dict[str, Any]]:
        return [card.to_dict() for card in self._discovered_agents.values()]

    def get_stats(self) -> dict[str, Any]:
        return {
            "client": self.agent_name,
            "discovered_agents": len(self._discovered_agents),
            "active_tasks": len(self._active_tasks),
        }


# ════════════════════════════════════════════════════════════════════
# Pre-built A2A Agent Cards for Angavu
# ════════════════════════════════════════════════════════════════════


def create_angavu_agent_card() -> A2AAgentCard:
    """Create the A2A Agent Card for Angavu Intelligence."""
    return A2AAgentCard(
        agent_id="angavu-intelligence",
        name="Angavu Intelligence",
        description="AI CFO platform for informal economy workers in East Africa. Provides credit scoring, cash flow forecasting, market analysis, tax compliance, and business formalization guidance.",
        url="https://api.angavu.ai/a2a",
        version="2.0.0",
        capabilities=[
            A2ACapability(
                name="credit_scoring",
                description="Generate credit scores for informal workers based on transaction history and business patterns",
                tags=["finance", "credit"],
            ),
            A2ACapability(
                name="cash_flow_forecasting",
                description="Predict future cash flow based on historical patterns",
                tags=["finance", "prediction"],
            ),
            A2ACapability(
                name="market_analysis",
                description="Analyze market prices, trends, and opportunities for informal traders",
                tags=["market", "analysis"],
            ),
            A2ACapability(
                name="tax_compliance",
                description="Generate tax reports and compliance documents for small businesses",
                tags=["tax", "compliance"],
            ),
            A2ACapability(
                name="formalization_guidance",
                description="Guide informal businesses through formalization process",
                tags=["business", "formalization"],
            ),
            A2ACapability(
                name="anomaly_detection",
                description="Detect anomalous patterns in financial transactions",
                tags=["security", "fraud"],
            ),
            A2ACapability(
                name="report_generation",
                description="Generate financial health reports and business summaries",
                tags=["reporting"],
            ),
        ],
        default_input_modes=["text", "data"],
        default_output_modes=["text", "data"],
        metadata={
            "region": "East Africa",
            "languages": ["en", "sw"],
            "currencies": ["KES", "UGX", "TZS"],
        },
    )


def create_external_a2a_agents() -> list[A2AAgentCard]:
    """Define external A2A agents that Angavu should integrate with."""
    return [
        A2AAgentCard(
            agent_id="kra-tax-agent",
            name="KRA Tax Compliance Agent",
            description="Kenya Revenue Authority tax filing and compliance agent",
            capabilities=[
                A2ACapability(name="file_return", description="File tax return", tags=["tax"]),
                A2ACapability(name="check_status", description="Check filing status", tags=["tax"]),
            ],
        ),
        A2AAgentCard(
            agent_id="crb-credit-agent",
            name="Credit Reference Bureau Agent",
            description="Kenya CRB credit report and scoring agent",
            capabilities=[
                A2ACapability(name="get_report", description="Get credit report", tags=["credit"]),
                A2ACapability(name="check_listing", description="Check blacklisting status", tags=["credit"]),
            ],
        ),
        A2AAgentCard(
            agent_id="mpesa-agent",
            name="M-Pesa Business Agent",
            description="Safaricom M-Pesa API for business transactions",
            capabilities=[
                A2ACapability(name="get_statement", description="Get M-Pesa statement", tags=["finance"]),
                A2ACapability(name="initiate_payment", description="Initiate M-Pesa payment", tags=["finance"]),
            ],
        ),
    ]
