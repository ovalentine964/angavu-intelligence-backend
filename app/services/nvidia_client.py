"""
NVIDIA NIM API Client — Free LLM inference and AI services.

Uses build.nvidia.com free endpoints for:
    - LLM inference (DeepSeek, Llama, Qwen, Nemotron)
    - Speech processing (Parakeet ASR, Chatterbox TTS)
    - Embedding generation (Nemotron Embed, BGE-M3)

API: OpenAI-compatible format
Base URL: https://integrate.api.nvidia.com/v1
Rate limit: ~1000 requests/day (free tier per endpoint)
No credit card required for prototyping.

Reference: nvidia-full-suite.md
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Default models — chosen for best free-tier value
DEFAULT_LLM_MODEL = "deepseek-ai/deepseek-v4-pro"
DEFAULT_FAST_LLM_MODEL = "deepseek-ai/deepseek-v4-flash"
DEFAULT_STT_MODEL = "nvidia/parakeet-ctc-1.1b-asr"
DEFAULT_TTS_MODEL = "nvidia/chatterbox-multilingual-tts"
DEFAULT_EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-1b-v2"
DEFAULT_VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"
DEFAULT_SAFETY_MODEL = "meta/llama-3.1-nemotron-safety-guard-8b-v3"
DEFAULT_TRANSLATE_MODEL = "nvidia/riva-translate-1.6b"

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 30  # Conservative per-endpoint limit
REQUEST_TIMEOUT_SECONDS = 120


@dataclass
class RateLimiter:
    """Simple sliding-window rate limiter for NIM endpoints."""

    max_requests: int = MAX_REQUESTS_PER_MINUTE
    window_seconds: float = 60.0
    _timestamps: List[float] = field(default_factory=list, repr=False)

    def can_proceed(self) -> bool:
        """Check if a request can proceed within rate limits."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        return len(self._timestamps) < self.max_requests

    def record(self) -> None:
        """Record a request timestamp."""
        self._timestamps.append(time.monotonic())

    async def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        while not self.can_proceed():
            if self._timestamps:
                wait_time = self._timestamps[0] + self.window_seconds - time.monotonic()
                if wait_time > 0:
                    logger.debug("nvidia_client.rate_limit_wait", wait_seconds=round(wait_time, 1))
                    await asyncio.sleep(wait_time)
            else:
                break


# ════════════════════════════════════════════════════════════════════
# NVIDIA NIM Client
# ════════════════════════════════════════════════════════════════════


class NVIDIAClient:
    """
    NVIDIA NIM API client for free LLM inference.

    Uses build.nvidia.com free endpoints for:
    - LLM inference (DeepSeek, Llama, Qwen, Nemotron)
    - Speech processing (Parakeet ASR, Chatterbox TTS)
    - Embedding generation (Nemotron Embed)

    Rate limit: ~1000 requests/day (free tier)
    No credit card required.

    Usage:
        client = NVIDIAClient(api_key="nvapi-...")
        response = await client.chat_completion([
            {"role": "user", "content": "Hello"}
        ])
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = NIM_BASE_URL,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._rate_limiter = RateLimiter()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── LLM Inference ─────────────────────────────────────────────

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_LLM_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        top_p: float = 1.0,
        stream: bool = False,
    ) -> str:
        """
        Free LLM inference via NVIDIA NIM.

        Supports all NIM-hosted models:
            - DeepSeek V4 Pro/Flash (coding, reasoning)
            - Llama 3.3/4 (general purpose, multilingual)
            - Qwen 3.5 (vision, chat, RAG)
            - Nemotron 3 (agentic, tool calling)

        Args:
            messages: Chat messages in OpenAI format
            model: NIM model ID
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum response tokens
            top_p: Nucleus sampling parameter
            stream: Whether to stream the response (not yet supported)

        Returns:
            Assistant response text
        """
        await self._rate_limiter.wait_if_needed()

        client = await self._get_client()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream,
        }

        logger.info(
            "nvidia_client.chat_completion",
            model=model,
            message_count=len(messages),
        )

        self._rate_limiter.record()
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        logger.info(
            "nvidia_client.chat_completion_done",
            model=model,
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
        )

        return content

    # ── Speech-to-Text ────────────────────────────────────────────

    async def speech_to_text(
        self,
        audio_path: str,
        model: str = DEFAULT_STT_MODEL,
        language: Optional[str] = None,
    ) -> str:
        """
        Free STT via NVIDIA NIM.

        Uses Parakeet ASR models:
            - parakeet-ctc-1.1b: English, record-setting accuracy
            - parakeet-rnnt-1.1b-multilingual: 25 languages
            - canary-1b: STT + translation

        Args:
            audio_path: Path to audio file (wav, mp3, flac)
            model: NIM ASR model ID
            language: Optional language hint

        Returns:
            Transcribed text
        """
        await self._rate_limiter.wait_if_needed()

        client = await self._get_client()

        logger.info("nvidia_client.speech_to_text", model=model, audio_path=audio_path)

        with open(audio_path, "rb") as audio_file:
            files = {"file": (audio_path, audio_file, "audio/wav")}
            data = {"model": model}
            if language:
                data["language"] = language

            self._rate_limiter.record()
            response = await client.post(
                "/audio/transcriptions",
                files=files,
                data=data,
            )

        response.raise_for_status()
        result = response.json()
        text = result.get("text", "")

        logger.info(
            "nvidia_client.speech_to_text_done",
            model=model,
            text_length=len(text),
        )

        return text

    # ── Text-to-Speech ────────────────────────────────────────────

    async def text_to_speech(
        self,
        text: str,
        language: str = "en",
        model: str = DEFAULT_TTS_MODEL,
        voice: Optional[str] = None,
    ) -> bytes:
        """
        Free TTS via NVIDIA NIM.

        Uses Chatterbox Multilingual TTS (23 languages).
        Natural expressive voices for voice agents.

        Args:
            text: Text to synthesize
            language: Language code (en, sw, etc.)
            model: NIM TTS model ID
            voice: Optional voice preset name

        Returns:
            Audio bytes (wav format)
        """
        await self._rate_limiter.wait_if_needed()

        client = await self._get_client()
        payload: Dict[str, Any] = {
            "model": model,
            "input": text,
            "language": language,
        }
        if voice:
            payload["voice"] = voice

        logger.info(
            "nvidia_client.text_to_speech",
            model=model,
            text_length=len(text),
            language=language,
        )

        self._rate_limiter.record()
        response = await client.post("/audio/speech", json=payload)
        response.raise_for_status()

        audio_bytes = response.content

        logger.info(
            "nvidia_client.text_to_speech_done",
            model=model,
            audio_size_bytes=len(audio_bytes),
        )

        return audio_bytes

    # ── Embeddings ────────────────────────────────────────────────

    async def get_embeddings(
        self,
        texts: List[str],
        model: str = DEFAULT_EMBEDDING_MODEL,
        input_type: str = "passage",
    ) -> List[List[float]]:
        """
        Free embedding generation via NVIDIA NIM.

        Uses Nemotron Embed 1b v2:
            - Multilingual (26 languages)
            - Long-document QA retrieval
            - Dense embeddings for RAG pipelines

        Args:
            texts: List of texts to embed
            model: NIM embedding model ID
            input_type: "passage" for documents, "query" for search

        Returns:
            List of embedding vectors (one per input text)
        """
        await self._rate_limiter.wait_if_needed()

        client = await self._get_client()
        payload = {
            "model": model,
            "input": texts,
            "input_type": input_type,
        }

        logger.info(
            "nvidia_client.get_embeddings",
            model=model,
            text_count=len(texts),
        )

        self._rate_limiter.record()
        response = await client.post("/embeddings", json=payload)
        response.raise_for_status()

        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]

        logger.info(
            "nvidia_client.get_embeddings_done",
            model=model,
            embedding_count=len(embeddings),
            dimension=len(embeddings[0]) if embeddings else 0,
        )

        return embeddings

    # ── Translation ───────────────────────────────────────────────

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        model: str = DEFAULT_TRANSLATE_MODEL,
    ) -> str:
        """
        Free neural machine translation via NVIDIA NIM.

        Uses Riva Translate 1.6b (36 languages).

        Args:
            text: Text to translate
            source_language: Source language code
            target_language: Target language code
            model: NIM translation model ID

        Returns:
            Translated text
        """
        messages = [
            {
                "role": "system",
                "content": (
                    f"Translate the following text from {source_language} "
                    f"to {target_language}. Output only the translation."
                ),
            },
            {"role": "user", "content": text},
        ]

        return await self.chat_completion(
            messages=messages,
            model=model,
            temperature=0.1,  # Low temp for translation accuracy
        )

    # ── Safety / Content Moderation ───────────────────────────────

    async def check_safety(
        self,
        text: str,
        model: str = DEFAULT_SAFETY_MODEL,
    ) -> Dict[str, Any]:
        """
        Check text for safety issues via NVIDIA NIM.

        Uses NemoGuard safety models for:
        - Content safety moderation
        - Topic control
        - Jailbreak detection
        - PII detection

        Args:
            text: Text to check
            model: NIM safety model ID

        Returns:
            Safety assessment with categories and scores
        """
        messages = [
            {
                "role": "user",
                "content": (
                    f"Assess the following text for safety issues. "
                    f"Categories: violence, hate, sexual, self-harm, "
                    f"pii, jailbreak. Text: {text}"
                ),
            },
        ]

        response = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=0.0,
        )

        return {"assessment": response, "model": model}

    # ── Vision ────────────────────────────────────────────────────

    async def analyze_image(
        self,
        image_url: str,
        prompt: str,
        model: str = DEFAULT_VISION_MODEL,
    ) -> str:
        """
        Analyze an image using vision-language models via NVIDIA NIM.

        Uses Llama 3.2 Vision for:
        - Document OCR and understanding
        - Chart/graph analysis
        - Visual Q&A

        Args:
            image_url: URL or base64 data URI of image
            prompt: Question/instruction about the image
            model: NIM vision model ID

        Returns:
            Analysis text
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ]

        return await self.chat_completion(
            messages=messages,
            model=model,
            temperature=0.3,
        )

    # ── Batch Processing ──────────────────────────────────────────

    async def batch_chat(
        self,
        batch: List[List[Dict[str, str]]],
        model: str = DEFAULT_FAST_LLM_MODEL,
        concurrency: int = 5,
    ) -> List[str]:
        """
        Process multiple chat completions concurrently.

        Uses fast models (DeepSeek V4 Flash) for batch processing.
        Respects rate limits via semaphore.

        Args:
            batch: List of message lists (one per request)
            model: NIM model ID
            concurrency: Max concurrent requests

        Returns:
            List of responses (same order as input)
        """
        semaphore = asyncio.Semaphore(concurrency)
        results: List[Optional[str]] = [None] * len(batch)

        async def _process_one(index: int, messages: List[Dict[str, str]]) -> None:
            async with semaphore:
                results[index] = await self.chat_completion(
                    messages=messages,
                    model=model,
                )

        tasks = [
            _process_one(i, messages) for i, messages in enumerate(batch)
        ]
        await asyncio.gather(*tasks)

        return [r or "" for r in results]
