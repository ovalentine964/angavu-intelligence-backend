"""
Tests for API v1 route structure.

Tests that route modules exist and have proper structure.
Uses importlib to handle missing optional dependencies gracefully.
"""

import importlib
import os
import pytest


# All v1 route module names
V1_MODULES = [
    "agents", "ai_chat", "auth", "autonomous", "channels",
    "dashboard", "finance", "gateway", "goals", "infra",
    "intelligence", "loans", "market", "mindset", "social",
    "tithe", "transactions", "users", "whatsapp_connection", "worker",
]


class TestV1RouteFilesExist:
    """Test that all v1 route files exist on disk."""

    def test_v1_directory_exists(self):
        v1_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "app", "api", "v1"
        )
        assert os.path.isdir(v1_path), f"v1 directory not found at {v1_path}"

    @pytest.mark.parametrize("module_name", V1_MODULES)
    def test_v1_module_file_exists(self, module_name):
        v1_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "app", "api", "v1", f"{module_name}.py"
        )
        assert os.path.isfile(v1_path), f"{module_name}.py not found"

    def test_v1_init_exists(self):
        v1_init = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "app", "api", "v1", "__init__.py"
        )
        assert os.path.isfile(v1_init)


class TestV1RouteModuleStructure:
    """Test that v1 route modules have expected structure by reading source."""

    @pytest.mark.parametrize("module_name", V1_MODULES)
    def test_module_has_router_definition(self, module_name):
        """Each v1 module should define a router (APIRouter)."""
        v1_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "app", "api", "v1", f"{module_name}.py"
        )
        with open(v1_path, "r") as f:
            content = f.read()

        assert "router" in content.lower() or "APIRouter" in content, \
            f"{module_name}.py should define a router"

    @pytest.mark.parametrize("module_name", V1_MODULES)
    def test_module_has_fastapi_imports(self, module_name):
        """Each v1 module should import from fastapi."""
        v1_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "app", "api", "v1", f"{module_name}.py"
        )
        with open(v1_path, "r") as f:
            content = f.read()

        assert "fastapi" in content.lower() or "APIRouter" in content, \
            f"{module_name}.py should use FastAPI"


class TestV1RouteEndpoints:
    """Test that key route files have expected endpoint decorators."""

    ENDPOINT_FILES = {
        "finance": ["@router"],
        "transactions": ["@router"],
        "intelligence": ["@router"],
        "loans": ["@router"],
        "goals": ["@router"],
        "dashboard": ["@router"],
    }

    @pytest.mark.parametrize("module_name,decorators", ENDPOINT_FILES.items())
    def test_module_has_endpoints(self, module_name, decorators):
        v1_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "app", "api", "v1", f"{module_name}.py"
        )
        with open(v1_path, "r") as f:
            content = f.read()

        for decorator in decorators:
            assert decorator in content, \
                f"{module_name}.py should have {decorator} decorator"
