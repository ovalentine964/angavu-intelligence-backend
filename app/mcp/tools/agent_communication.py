"""
MCP Agent Communication Tools.

Exposes multi-agent system as MCP-compatible tools:
- dispatch_task: Send a task to a domain agent
- get_agent_status: Check agent health/status
- get_agent_results: Retrieve agent task results
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from app.mcp.config import MCPToolDefinition, MCPToolParameter

logger = structlog.get_logger(__name__)


# ── In-memory task store (replace with Redis in production) ─────────

_task_store: Dict[str, Dict[str, Any]] = {}


# ── Tool Definitions ────────────────────────────────────────────────

dispatch_task_tool = MCPToolDefinition(
    name="dispatch_task",
    description=(
        "Dispatch a task to a Angavu Intelligence domain agent. "
        "Available agents: TransactionProcessor, IntelligenceGenerator, "
        "ReportGenerator, SelfEvolution, and domain agents (Transport, "
        "Retail, Agriculture, Service, Digital, Manufacturing). "
        "Returns a task ID for tracking."
    ),
    parameters=[
        MCPToolParameter(
            name="agent_name",
            type="string",
            description="Target agent name",
            required=True,
            enum=[
                "TransactionProcessor",
                "IntelligenceGenerator",
                "ReportGenerator",
                "SelfEvolution",
                "TransportAgent",
                "RetailAgent",
                "AgricultureAgent",
                "ServiceAgent",
                "DigitalAgent",
                "ManufacturingAgent",
            ],
        ),
        MCPToolParameter(
            name="task_type",
            type="string",
            description="Type of task to execute",
            required=True,
        ),
        MCPToolParameter(
            name="payload",
            type="object",
            description="Task payload/parameters",
            required=True,
        ),
        MCPToolParameter(
            name="priority",
            type="string",
            description="Task priority",
            required=False,
            default="normal",
            enum=["low", "normal", "high", "urgent"],
        ),
        MCPToolParameter(
            name="timeout_seconds",
            type="number",
            description="Maximum time to wait for task completion",
            required=False,
            default=30,
        ),
    ],
    category="agent_communication",
)

get_agent_status_tool = MCPToolDefinition(
    name="get_agent_status",
    description=(
        "Check the status and health of Angavu Intelligence agents. "
        "Returns agent state (idle/busy/error), uptime, tasks processed, "
        "and current workload."
    ),
    parameters=[
        MCPToolParameter(
            name="agent_name",
            type="string",
            description="Agent to check, or 'all' for all agents",
            required=False,
            default="all",
        ),
    ],
    category="agent_communication",
)

get_agent_results_tool = MCPToolDefinition(
    name="get_agent_results",
    description=(
        "Retrieve results from a previously dispatched agent task. "
        "Returns the task output, execution time, and any errors."
    ),
    parameters=[
        MCPToolParameter(
            name="task_id",
            type="string",
            description="Task ID returned by dispatch_task",
            required=True,
        ),
    ],
    category="agent_communication",
)

# Registry
AGENT_TOOLS = [
    dispatch_task_tool,
    get_agent_status_tool,
    get_agent_results_tool,
]


# ── Tool Handlers ───────────────────────────────────────────────────


async def handle_agent_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    requester_id: str,
    app_state: Any = None,
) -> Dict[str, Any]:
    """
    Dispatch an agent communication tool call.

    Args:
        tool_name: One of the agent tool names.
        arguments: Tool call arguments.
        requester_id: Authenticated requester ID.
        app_state: FastAPI app.state for accessing live agents.

    Returns:
        Tool result dictionary.
    """
    start = time.time()

    try:
        if tool_name == "dispatch_task":
            result = await _dispatch_task(arguments, requester_id, app_state)
        elif tool_name == "get_agent_status":
            result = await _get_agent_status(arguments, app_state)
        elif tool_name == "get_agent_results":
            result = await _get_agent_results(arguments)
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown agent tool: {tool_name}"}],
            }

        elapsed = time.time() - start
        logger.info(
            "mcp_agent_tool_executed",
            tool=tool_name,
            requester_id=requester_id,
            elapsed_ms=round(elapsed * 1000, 1),
        )

        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
            "metadata": {
                "tool": tool_name,
                "requester_id": requester_id,
                "elapsed_ms": round(elapsed * 1000, 1),
            },
        }

    except Exception as e:
        logger.error("mcp_agent_tool_error", tool=tool_name, error=str(e), exc_info=True)
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Tool execution error: {str(e)}"}],
        }


async def _dispatch_task(
    args: Dict[str, Any], requester_id: str, app_state: Any
) -> Dict[str, Any]:
    """Dispatch a task to an agent via the EventBus."""
    agent_name = args["agent_name"]
    task_type = args["task_type"]
    payload = args["payload"]
    priority = args.get("priority", "normal")

    task_id = str(uuid.uuid4())

    # Store task as pending
    _task_store[task_id] = {
        "task_id": task_id,
        "agent_name": agent_name,
        "task_type": task_type,
        "status": "dispatched",
        "priority": priority,
        "dispatched_at": datetime.utcnow().isoformat(),
        "requester_id": requester_id,
        "result": None,
        "error": None,
    }

    # Publish to EventBus if available
    if app_state and hasattr(app_state, "event_bus"):
        from app.agents.base import AgentEvent, EventType

        event = AgentEvent(
            event_type=EventType.INTELLIGENCE_REQUESTED,
            source=f"MCP:{requester_id}",
            payload={
                "task_id": task_id,
                "agent_name": agent_name,
                "task_type": task_type,
                "data": payload,
                "priority": priority,
            },
        )
        await app_state.event_bus.publish(event)
        _task_store[task_id]["status"] = "published"
    else:
        _task_store[task_id]["status"] = "queued"
        _task_store[task_id]["note"] = "EventBus not available; task queued for processing"

    logger.info(
        "mcp_task_dispatched",
        task_id=task_id,
        agent=agent_name,
        task_type=task_type,
    )

    return {
        "task_id": task_id,
        "agent_name": agent_name,
        "status": _task_store[task_id]["status"],
        "message": f"Task dispatched to {agent_name}. Use get_agent_results with task_id to retrieve results.",
    }


async def _get_agent_status(
    args: Dict[str, Any], app_state: Any
) -> Dict[str, Any]:
    """Get status of one or all agents."""
    agent_name = args.get("agent_name", "all")

    if app_state and hasattr(app_state, "agents"):
        agents = app_state.agents
        if agent_name == "all":
            statuses = {}
            for name, agent in agents.items():
                statuses[name] = {
                    "status": agent.status.value,
                    "name": agent.name,
                    "tier": agent.tier,
                }
            return {
                "agents": statuses,
                "total": len(statuses),
                "event_bus_mode": (
                    app_state.event_bus.get_stats()["mode"]
                    if hasattr(app_state, "event_bus")
                    else "unknown"
                ),
            }
        else:
            # Find by partial name match
            matched = None
            for name, agent in agents.items():
                if agent_name.lower() in name.lower():
                    matched = agent
                    break
            if matched:
                return {
                    "agent_name": matched.name,
                    "status": matched.status.value,
                    "tier": matched.tier,
                }
            return {"error": f"Agent not found: {agent_name}"}

    return {
        "agents": {},
        "note": "Agent system not initialized",
    }


async def _get_agent_results(args: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve results for a dispatched task."""
    task_id = args["task_id"]

    if task_id not in _task_store:
        return {
            "isError": True,
            "error": f"Task not found: {task_id}",
        }

    task = _task_store[task_id]
    return {
        "task_id": task_id,
        "agent_name": task["agent_name"],
        "task_type": task["task_type"],
        "status": task["status"],
        "dispatched_at": task["dispatched_at"],
        "result": task.get("result"),
        "error": task.get("error"),
    }
