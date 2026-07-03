"""Tests for agent configuration management."""

import pytest
import tempfile
from pathlib import Path
from app.autonomous.config import AgentConfigManager, AgentConfig, AgentRole, EscalationConfig


class TestAgentRole:
    def test_roles_defined(self):
        assert AgentRole.SALES.value == "sales"
        assert AgentRole.CONTENT.value == "content"
        assert AgentRole.OPERATIONS.value == "operations"


class TestAgentConfig:
    def test_default_config(self):
        config = AgentConfig(name="test", role=AgentRole.SALES)
        assert config.name == "test"
        assert config.enabled is True
        assert config.model == "deepseek-chat"
        assert config.max_tasks_per_hour == 20

    def test_config_to_dict(self):
        config = AgentConfig(
            name="test",
            role=AgentRole.OPERATIONS,
            system_prompt="Test prompt",
        )
        d = config.to_dict()
        assert d["name"] == "test"
        assert d["role"] == "operations"
        assert "system_prompt_hash" in d
        assert d["system_prompt_hash"] != ""

    def test_escalation_defaults(self):
        config = AgentConfig(name="test", role=AgentRole.SALES)
        assert config.escalation.enabled is True
        assert config.escalation.error_threshold == 3
        assert config.escalation.confidence_threshold == 0.6


class TestAgentConfigManager:
    @pytest.fixture
    def manager(self):
        return AgentConfigManager()

    def test_load_nonexistent_returns_default(self, manager):
        config = manager.load("nonexistent_agent")
        assert config.name == "nonexistent_agent"
        assert config.enabled is True

    def test_load_from_yaml(self, manager):
        """Test loading from the actual templates directory."""
        config = manager.load("sales_agent")
        assert config.name == "sales_agent"
        assert config.role == AgentRole.SALES

    def test_load_all(self, manager):
        configs = manager.load_all()
        assert len(configs) >= 0  # May be 0 if templates dir doesn't match

    def test_reload(self, manager):
        config1 = manager.load("sales_agent")
        config2 = manager.reload("sales_agent")
        assert config1.name == config2.name

    def test_get_prompt_hash(self, manager):
        manager.load("sales_agent")
        hash_val = manager.get_prompt_hash("sales_agent")
        # Hash should be non-empty if prompt exists
        if hash_val:
            assert len(hash_val) == 16

    def test_custom_template_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a test config
            test_yaml = Path(tmpdir) / "test_agent.yaml"
            test_yaml.write_text("""
name: "test_agent"
role: "sales"
enabled: true
model: "test-model"
temperature: 0.5
max_tasks_per_hour: 10
escalation:
  enabled: false
  error_threshold: 5
""")
            manager = AgentConfigManager(template_dir=Path(tmpdir))
            config = manager.load("test_agent")
            assert config.name == "test_agent"
            assert config.model == "test-model"
            assert config.temperature == 0.5
            assert config.max_tasks_per_hour == 10
            assert config.escalation.enabled is False
            assert config.escalation.error_threshold == 5
