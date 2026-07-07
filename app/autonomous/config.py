"""
Agent Configuration Management — Centralized config for all autonomous agents.

Loads agent configurations from YAML templates, validates them,
and provides runtime config access with version control.

Features:
    - YAML-based agent configuration templates
    - Runtime config overrides (env vars)
    - Prompt version control (git-tracked)
    - Per-agent config validation
    - Hot-reload support for development
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import yaml

logger = structlog.get_logger(__name__)

# Default template directory
_TEMPLATE_DIR = Path(__file__).parent / "templates"


class AgentRole(str, Enum):
    SALES = "sales"
    CONTENT = "content"
    OPERATIONS = "operations"


@dataclass
class EscalationConfig:
    """Escalation settings for an agent."""
    enabled: bool = True
    error_threshold: int = 3           # consecutive errors before escalate
    confidence_threshold: float = 0.6  # below this → escalate
    cost_threshold_usd: float = 10.0   # per-task cost ceiling
    time_threshold_seconds: int = 300  # task timeout → escalate
    channels: List[str] = field(default_factory=lambda: ["telegram", "email"])


@dataclass
class AgentConfig:
    """Configuration for a single autonomous agent."""
    name: str
    role: AgentRole
    enabled: bool = True
    description: str = ""

    # LLM settings
    model: str = "qwen-0.5b-fl-sw"  # On-device model (zero-cost strategy)
    temperature: float = 0.3
    max_tokens: int = 2048
    system_prompt: str = ""
    prompt_version: str = "v1"

    # Operational limits
    max_tasks_per_hour: int = 20
    max_cost_per_day_usd: float = 50.0
    retry_attempts: int = 2
    retry_delay_seconds: int = 5

    # Escalation
    escalation: EscalationConfig = field(default_factory=EscalationConfig)

    # Tools this agent can use
    tools: List[str] = field(default_factory=list)

    # Custom parameters
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "enabled": self.enabled,
            "description": self.description,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system_prompt_hash": hashlib.md5(
                self.system_prompt.encode()
            ).hexdigest()[:12] if self.system_prompt else "",
            "prompt_version": self.prompt_version,
            "max_tasks_per_hour": self.max_tasks_per_hour,
            "max_cost_per_day_usd": self.max_cost_per_day_usd,
            "tools": self.tools,
            "escalation": {
                "enabled": self.escalation.enabled,
                "error_threshold": self.escalation.error_threshold,
                "confidence_threshold": self.escalation.confidence_threshold,
            },
        }


class AgentConfigManager:
    """
    Manages agent configurations from YAML templates.

    Usage:
        manager = AgentConfigManager()
        config = manager.load("sales_agent")
        all_configs = manager.load_all()
    """

    def __init__(self, template_dir: Optional[Path] = None):
        self._template_dir = template_dir or _TEMPLATE_DIR
        self._configs: Dict[str, AgentConfig] = {}
        self._logger = logger.bind(component="config_manager")

    def load(self, agent_name: str) -> AgentConfig:
        """Load a single agent's configuration from YAML."""
        if agent_name in self._configs:
            return self._configs[agent_name]

        template_path = self._template_dir / f"{agent_name}.yaml"
        if not template_path.exists():
            self._logger.warning("config_not_found", agent=agent_name, path=str(template_path))
            return self._default_config(agent_name)

        try:
            with open(template_path) as f:
                raw = yaml.safe_load(f) or {}
            config = self._parse_config(agent_name, raw)
            self._configs[agent_name] = config
            self._logger.info(
                "config_loaded",
                agent=agent_name,
                prompt_version=config.prompt_version,
            )
            return config
        except Exception as exc:
            self._logger.error("config_load_failed", agent=agent_name, error=str(exc))
            return self._default_config(agent_name)

    def load_all(self) -> Dict[str, AgentConfig]:
        """Load all agent configurations from the template directory."""
        configs = {}
        if not self._template_dir.exists():
            self._logger.warning("template_dir_missing", path=str(self._template_dir))
            return configs

        for yaml_file in sorted(self._template_dir.glob("*.yaml")):
            if yaml_file.name == "agent_config.yaml":
                continue  # Skip the template file itself
            agent_name = yaml_file.stem
            configs[agent_name] = self.load(agent_name)

        self._logger.info("all_configs_loaded", count=len(configs))
        return configs

    def reload(self, agent_name: str) -> AgentConfig:
        """Force reload a configuration (for hot-reload in dev)."""
        self._configs.pop(agent_name, None)
        return self.load(agent_name)

    def get_prompt_hash(self, agent_name: str) -> str:
        """Get hash of current prompt for version tracking."""
        config = self._configs.get(agent_name)
        if not config or not config.system_prompt:
            return ""
        return hashlib.sha256(config.system_prompt.encode()).hexdigest()[:16]

    def _parse_config(self, agent_name: str, raw: Dict[str, Any]) -> AgentConfig:
        """Parse raw YAML dict into AgentConfig."""
        escalation_raw = raw.get("escalation", {})
        escalation = EscalationConfig(
            enabled=escalation_raw.get("enabled", True),
            error_threshold=escalation_raw.get("error_threshold", 3),
            confidence_threshold=escalation_raw.get("confidence_threshold", 0.6),
            cost_threshold_usd=escalation_raw.get("cost_threshold_usd", 10.0),
            time_threshold_seconds=escalation_raw.get("time_threshold_seconds", 300),
            channels=escalation_raw.get("channels", ["telegram", "email"]),
        )

        return AgentConfig(
            name=raw.get("name", agent_name),
            role=AgentRole(raw.get("role", agent_name.split("_")[0])),
            enabled=raw.get("enabled", True),
            description=raw.get("description", ""),
            model=raw.get("model", "qwen-0.5b-fl-sw"),  # On-device model (zero-cost)
            temperature=raw.get("temperature", 0.3),
            max_tokens=raw.get("max_tokens", 2048),
            system_prompt=raw.get("system_prompt", ""),
            prompt_version=raw.get("prompt_version", "v1"),
            max_tasks_per_hour=raw.get("max_tasks_per_hour", 20),
            max_cost_per_day_usd=raw.get("max_cost_per_day_usd", 50.0),
            retry_attempts=raw.get("retry_attempts", 2),
            retry_delay_seconds=raw.get("retry_delay_seconds", 5),
            escalation=escalation,
            tools=raw.get("tools", []),
            params=raw.get("params", {}),
        )

    def _default_config(self, agent_name: str) -> AgentConfig:
        """Return a default config when YAML is missing."""
        role_str = agent_name.split("_")[0] if "_" in agent_name else "operations"
        try:
            role = AgentRole(role_str)
        except ValueError:
            role = AgentRole.OPERATIONS

        return AgentConfig(
            name=agent_name,
            role=role,
            description=f"Default config for {agent_name}",
        )
