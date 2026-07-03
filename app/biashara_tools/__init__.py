"""
Angavu Intelligence — DeerFlow Tool Registration.

Registers all Angavu intelligence services as DeerFlow-compatible
LangChain tools. Each tool wraps an existing Biashara service and
returns JSON-serialized results.

Usage:
    from app.biashara_tools import get_biashara_tools
    tools = get_biashara_tools()
"""

from app.biashara_tools.soko_pulse import soko_pulse_tool
from app.biashara_tools.alama_score import alama_score_tool
from app.biashara_tools.distribution_gap import distribution_gap_tool
from app.biashara_tools.fmcg_intelligence import fmcg_intelligence_tool
from app.biashara_tools.worker_intelligence import worker_intelligence_tool

__all__ = [
    "soko_pulse_tool",
    "alama_score_tool",
    "distribution_gap_tool",
    "fmcg_intelligence_tool",
    "worker_intelligence_tool",
    "get_biashara_tools",
]


def get_biashara_tools():
    """Return all Angavu tools as a list for agent binding."""
    return [
        soko_pulse_tool,
        alama_score_tool,
        distribution_gap_tool,
        fmcg_intelligence_tool,
        worker_intelligence_tool,
    ]
