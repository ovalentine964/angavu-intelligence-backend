"""
Gemini API configuration and rate limiting.
Feature-flagged: set GEMINI_ENABLED=true to activate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GeminiConfig:
    """Configuration for Gemini 3.5 Flash cloud reasoning."""

    enabled: bool = field(
        default_factory=lambda: os.getenv("GEMINI_ENABLED", "false").lower() == "true"
    )
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    model: str = "gemini-2.0-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Rate limits (free tier: 15 RPM, 1M tokens/day)
    requests_per_minute: int = 15
    tokens_per_day: int = 1_000_000
    max_tokens_per_query: int = 8192
    temperature: float = 0.3  # Low for financial accuracy

    # Cost controls
    max_queries_per_user_per_day: int = 20
    max_cost_per_user_per_month_usd: float = 0.50
    cost_per_million_input_tokens: float = 0.075
    cost_per_million_output_tokens: float = 0.30

    # Timeouts
    connect_timeout_seconds: int = 5
    read_timeout_seconds: int = 30
    max_retries: int = 2

    # Feature flags
    function_calling_enabled: bool = True
    streaming_enabled: bool = True


_config: GeminiConfig | None = None


def get_gemini_config() -> GeminiConfig:
    global _config
    if _config is None:
        _config = GeminiConfig()
    return _config
