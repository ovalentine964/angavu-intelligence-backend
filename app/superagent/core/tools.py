"""
Tool Registry and Execution

Centralized tool management for the superagent.
Replaces the scattered tool implementations across agents.
"""

from typing import Any, Callable, Optional


class Tool:
    """A tool that the superagent can use."""

    def __init__(self, name: str, description: str, func: Callable, schema: Optional[dict] = None):
        self.name = name
        self.description = description
        self.func = func
        self.schema = schema or {}

    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given arguments."""
        return await self.func(**kwargs)


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self.tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.tools.get(name)

    def list_tools(self) -> list[dict]:
        """List all available tools with their descriptions."""
        return [
            {"name": t.name, "description": t.description, "schema": t.schema}
            for t in self.tools.values()
        ]
