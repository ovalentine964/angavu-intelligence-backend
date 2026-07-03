"""
LLM Service — Abstract provider interface for Angavu Intelligence.

Provides a unified interface for LLM inference supporting:
- Local GGUF models via llama.cpp HTTP server (default: Qwen 2.5 7B Q4_K_M)
- OpenAI-compatible APIs (Groq, DeepSeek, NVIDIA NIM, etc.)

Designed for Oracle Cloud free tier: 4 OCPU, 24GB RAM.
Qwen 2.5 7B Q4_K_M uses ~5GB VRAM/RAM, leaving room for the rest of the stack.

Architecture:
    ┌─────────────────┐
    │  Agent Loop      │
    │  (ReAct/Reflexion)│
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │   LLMService     │  ← This module
    │  (unified API)   │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  LLMProvider     │  ← Abstract interface
    │  (strategy)      │
    └───┬─────────┬───┘
        │         │
   ┌────▼───┐ ┌──▼──────────┐
   │ Local  │ │ OpenAI API  │
   │ llama  │ │ compatible  │
   └────────┘ └─────────────┘
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════


class LLMRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class LLMMessage:
    """A single message in a conversation."""
    role: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMCompletion:
    """Result of an LLM inference call."""
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: Dict[str, int] = field(default_factory=dict)  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str = ""  # "stop", "length", "error"
    latency_ms: float = 0.0
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    cached: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content[:500] if self.content else "",
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "cached": self.cached,
            "error": self.error,
        }


@dataclass
class LLMConfig:
    """Configuration for an LLM inference request."""
    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    stop: List[str] = field(default_factory=list)
    stream: bool = False
    timeout_seconds: float = 60.0


# ════════════════════════════════════════════════════════════════════
# Abstract Provider Interface
# ════════════════════════════════════════════════════════════════════


class LLMProvider(ABC):
    """
    Abstract LLM provider interface.

    Implement this for each inference backend:
    - LocalGGUFProvider: llama.cpp HTTP server
    - OpenAICompatibleProvider: any OpenAI-compatible API
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging/metrics."""
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is currently reachable."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None,
    ) -> LLMCompletion:
        """Generate a completion from a list of messages."""
        ...

    async def health_check(self) -> Dict[str, Any]:
        """Check provider health. Override for custom health checks."""
        return {
            "provider": self.name,
            "available": self.is_available,
        }


# ════════════════════════════════════════════════════════════════════
# Local GGUF Provider (llama.cpp HTTP server)
# ════════════════════════════════════════════════════════════════════


class LocalGGUFProvider(LLMProvider):
    """
    Provider for local GGUF models served via llama.cpp HTTP server.

    Default config targets Qwen 2.5 7B Q4_K_M on Oracle Cloud free tier.
    llama.cpp server runs as a separate container (see deploy/oracle/).

    Endpoint: http://llama-cpp:8080/completion
    Chat endpoint: http://llama-cpp:8080/v1/chat/completions
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        model_path: str = "",
        timeout: float = 60.0,
    ):
        self._host = host
        self._port = port
        self._model_path = model_path
        self._timeout = timeout
        self._base_url = f"http://{host}:{port}"
        self._client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None
        self._last_check: float = 0
        self._logger = logger.bind(provider="local_gguf")

    @property
    def name(self) -> str:
        return "local_gguf"

    @property
    def is_available(self) -> bool:
        # Cache availability check for 30s
        if self._available is not None and (time.time() - self._last_check) < 30:
            return self._available
        return self._available or False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
            )
        return self._client

    async def health_check(self) -> Dict[str, Any]:
        """Check if llama.cpp server is running and model is loaded."""
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            data = resp.json()
            self._available = resp.status_code == 200
            self._last_check = time.time()
            return {
                "provider": self.name,
                "available": self._available,
                "model_loaded": data.get("model_loaded", False),
                "slots_idle": data.get("slots_idle", 0),
                "slots_processing": data.get("slots_processing", 0),
                "base_url": self._base_url,
            }
        except Exception as exc:
            self._available = False
            self._last_check = time.time()
            return {
                "provider": self.name,
                "available": False,
                "error": str(exc),
                "base_url": self._base_url,
            }

    async def complete(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None,
    ) -> LLMCompletion:
        """
        Generate completion using llama.cpp's OpenAI-compatible chat endpoint.

        Falls back to /completion endpoint if chat endpoint is unavailable.
        """
        cfg = config or LLMConfig()
        start = time.time()

        try:
            client = await self._get_client()

            # Use OpenAI-compatible chat completions endpoint
            payload = {
                "model": self._model_path or "qwen2.5-7b-q4_k_m",
                "messages": [m.to_dict() for m in messages],
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "top_p": cfg.top_p,
                "repeat_penalty": cfg.repeat_penalty,
                "stream": False,
            }
            if cfg.stop:
                payload["stop"] = cfg.stop

            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            choice = data.get("choices", [{}])[0]
            usage = data.get("usage", {})

            self._available = True
            self._last_check = time.time()

            return LLMCompletion(
                content=choice.get("message", {}).get("content", ""),
                model=data.get("model", self._model_path),
                provider=self.name,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                finish_reason=choice.get("finish_reason", "stop"),
                latency_ms=(time.time() - start) * 1000,
            )

        except httpx.ConnectError as exc:
            self._available = False
            self._last_check = time.time()
            return LLMCompletion(
                error=f"Connection refused: {exc}",
                provider=self.name,
                latency_ms=(time.time() - start) * 1000,
            )
        except httpx.TimeoutException as exc:
            return LLMCompletion(
                error=f"Timeout after {cfg.timeout_seconds}s: {exc}",
                provider=self.name,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            self._logger.error("local_gguf_error", error=str(exc))
            return LLMCompletion(
                error=str(exc),
                provider=self.name,
                latency_ms=(time.time() - start) * 1000,
            )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ════════════════════════════════════════════════════════════════════
# OpenAI-Compatible Provider (Groq, DeepSeek, NVIDIA NIM, etc.)
# ════════════════════════════════════════════════════════════════════


class OpenAICompatibleProvider(LLMProvider):
    """
    Provider for any OpenAI-compatible API.

    Supports: Groq, DeepSeek, NVIDIA NIM, OpenRouter, etc.
    Configured via base_url and api_key.
    """

    def __init__(
        self,
        name: str = "openai_compatible",
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = 60.0,
    ):
        self._name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None
        self._last_check: float = 0
        self._logger = logger.bind(provider=name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_available(self) -> bool:
        if self._available is not None and (time.time() - self._last_check) < 60:
            return self._available
        return bool(self._base_url and self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
            )
        return self._client

    async def health_check(self) -> Dict[str, Any]:
        """Check if the API is reachable by listing models."""
        try:
            client = await self._get_client()
            resp = await client.get("/models")
            self._available = resp.status_code == 200
            self._last_check = time.time()
            return {
                "provider": self.name,
                "available": self._available,
                "base_url": self._base_url,
                "model": self._model,
                "status_code": resp.status_code,
            }
        except Exception as exc:
            self._available = False
            self._last_check = time.time()
            return {
                "provider": self.name,
                "available": False,
                "error": str(exc),
                "base_url": self._base_url,
            }

    async def complete(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None,
    ) -> LLMCompletion:
        cfg = config or LLMConfig()
        start = time.time()

        try:
            client = await self._get_client()

            payload = {
                "model": self._model,
                "messages": [m.to_dict() for m in messages],
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "top_p": cfg.top_p,
                "stream": False,
            }
            if cfg.stop:
                payload["stop"] = cfg.stop

            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            choice = data.get("choices", [{}])[0]
            usage = data.get("usage", {})

            self._available = True
            self._last_check = time.time()

            return LLMCompletion(
                content=choice.get("message", {}).get("content", ""),
                model=data.get("model", self._model),
                provider=self.name,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                finish_reason=choice.get("finish_reason", "stop"),
                latency_ms=(time.time() - start) * 1000,
            )

        except httpx.HTTPStatusError as exc:
            self._logger.error("api_error", status=exc.response.status_code, body=exc.response.text[:500])
            return LLMCompletion(
                error=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                provider=self.name,
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            self._logger.error("provider_error", error=str(exc))
            return LLMCompletion(
                error=str(exc),
                provider=self.name,
                latency_ms=(time.time() - start) * 1000,
            )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ════════════════════════════════════════════════════════════════════
# LLM Service — Unified Interface with Fallback
# ════════════════════════════════════════════════════════════════════


class LLMService:
    """
    Unified LLM service with provider fallback and health monitoring.

    Usage:
        service = LLMService.from_settings()
        result = await service.complete([
            LLMMessage(role="system", content="You are a business advisor."),
            LLMMessage(role="user", content="How should I price mandazi?"),
        ])

    The service tries providers in order:
    1. Local GGUF (Qwen 2.5 7B) — free, fast, private
    2. OpenAI-compatible API — fallback when local is unavailable

    Provider selection is automatic based on health checks.
    """

    def __init__(
        self,
        providers: Optional[List[LLMProvider]] = None,
        default_config: Optional[LLMConfig] = None,
    ):
        self._providers = providers or []
        self._default_config = default_config or LLMConfig()
        self._request_count = 0
        self._error_count = 0
        self._logger = logger.bind(component="llm_service")

    @classmethod
    def from_settings(cls) -> "LLMService":
        """
        Create LLMService from application settings.

        Reads config from app.config.Settings:
        - LLM_HOST, LLM_PORT, LLM_MODEL_PATH → LocalGGUFProvider
        - GROQ_API_KEY → Groq provider
        - DEEPSEEK_API_KEY → DeepSeek provider
        - NVIDIA_NIM_BASE_URL, NVIDIA_NIM_API_KEY → NVIDIA NIM provider
        """
        settings = get_settings()
        providers: List[LLMProvider] = []

        # 1. Local GGUF (primary — Qwen 2.5 7B on Oracle Cloud)
        local_provider = LocalGGUFProvider(
            host=settings.LLM_HOST,
            port=settings.LLM_PORT,
            model_path=settings.LLM_MODEL_PATH,
            timeout=settings.LLM_TIMEOUT,
        )
        providers.append(local_provider)

        # 2. Groq (fast inference, free tier)
        if settings.GROQ_API_KEY:
            providers.append(OpenAICompatibleProvider(
                name="groq",
                base_url="https://api.groq.com/openai/v1",
                api_key=settings.GROQ_API_KEY,
                model="llama-3.1-70b-versatile",
                timeout=30.0,
            ))

        # 3. DeepSeek (affordable, good quality)
        if settings.DEEPSEEK_API_KEY:
            providers.append(OpenAICompatibleProvider(
                name="deepseek",
                base_url="https://api.deepseek.com/v1",
                api_key=settings.DEEPSEEK_API_KEY,
                model="deepseek-chat",
                timeout=60.0,
            ))

        # 4. NVIDIA NIM (enterprise, if configured)
        if settings.NVIDIA_NIM_API_KEY and settings.NVIDIA_NIM_BASE_URL:
            providers.append(OpenAICompatibleProvider(
                name="nvidia_nim",
                base_url=settings.NVIDIA_NIM_BASE_URL,
                api_key=settings.NVIDIA_NIM_API_KEY,
                model="meta/llama-3.1-70b-instruct",
                timeout=60.0,
            ))

        default_config = LLMConfig(
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            timeout_seconds=settings.LLM_TIMEOUT,
        )

        cls._logger = logger.bind(component="llm_service")
        cls._logger.info(
            "llm_service_initialized",
            providers=[p.name for p in providers],
            primary=providers[0].name if providers else "none",
        )

        return cls(providers=providers, default_config=default_config)

    async def complete(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None,
        preferred_provider: Optional[str] = None,
    ) -> LLMCompletion:
        """
        Generate a completion, trying providers in order with fallback.

        Args:
            messages: Conversation messages
            config: Override default LLM config for this request
            preferred_provider: Try this provider first (by name)

        Returns:
            LLMCompletion with the result from the first successful provider
        """
        self._request_count += 1
        cfg = config or self._default_config

        # Build provider order (preferred first, then default order)
        providers = list(self._providers)
        if preferred_provider:
            for i, p in enumerate(providers):
                if p.name == preferred_provider:
                    providers.insert(0, providers.pop(i))
                    break

        # Try each provider
        last_error = None
        for provider in providers:
            if not provider.is_available:
                self._logger.debug("provider_unavailable", provider=provider.name)
                continue

            self._logger.debug("trying_provider", provider=provider.name)
            result = await provider.complete(messages, cfg)

            if result.success:
                self._logger.info(
                    "llm_completion_success",
                    provider=provider.name,
                    tokens=result.usage.get("total_tokens", 0),
                    latency_ms=result.latency_ms,
                )
                return result

            last_error = result.error
            self._logger.warning(
                "provider_failed",
                provider=provider.name,
                error=result.error,
            )

        # All providers failed
        self._error_count += 1
        self._logger.error(
            "all_providers_failed",
            tried=[p.name for p in providers],
            last_error=last_error,
        )
        return LLMCompletion(
            error=f"All LLM providers failed. Last error: {last_error}",
            provider="none",
        )

    async def complete_text(
        self,
        prompt: str,
        system_prompt: str = "",
        config: Optional[LLMConfig] = None,
    ) -> str:
        """
        Simplified interface: returns just the text content.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            config: Override default config

        Returns:
            Generated text, or empty string on failure
        """
        messages = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=prompt))

        result = await self.complete(messages, config)
        return result.content if result.success else ""

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all providers."""
        results = {}
        for provider in self._providers:
            results[provider.name] = await provider.health_check()

        return {
            "providers": results,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(1, self._request_count),
            "available_providers": [
                p.name for p in self._providers if p.is_available
            ],
        }

    async def close(self) -> None:
        """Clean up all provider connections."""
        for provider in self._providers:
            try:
                await provider.close()
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "providers": [p.name for p in self._providers],
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(1, self._request_count),
        }


# ════════════════════════════════════════════════════════════════════
# Singleton for FastAPI Dependency Injection
# ════════════════════════════════════════════════════════════════════

_llm_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """
    Get or create the singleton LLMService instance.

    Use as a FastAPI dependency:
        @router.post("/advice")
        async def get_advice(llm: LLMService = Depends(get_llm_service)):
            ...
    """
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = LLMService.from_settings()
    return _llm_service_instance


async def close_llm_service() -> None:
    """Shutdown hook — close LLM service connections."""
    global _llm_service_instance
    if _llm_service_instance:
        await _llm_service_instance.close()
        _llm_service_instance = None
