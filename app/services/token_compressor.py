"""
Token Compressor — Prompt compression for cost optimization.

Reduces token count before sending to models by:
- Removing redundant context
- Summarizing long conversation histories
- Compressing repeated patterns
- Trimming system prompts

Inspired by OmniRoute's token compression feature.

Usage:
    compressor = TokenCompressor()
    compressed = compressor.compress(messages, max_tokens=2000)
    stats = compressor.get_stats()
"""

from __future__ import annotations

import re
import hashlib
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Rough token estimation (words * 1.3 for English, * 1.5 for mixed)
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough approximation)."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: List[Dict[str, str]]) -> int:
    """Estimate total tokens in a message list."""
    total = 0
    for msg in messages:
        total += 4  # message overhead
        total += estimate_tokens(msg.get("role", ""))
        total += estimate_tokens(msg.get("content", ""))
    return total


class CompressionStats:
    """Tracks compression performance over time."""

    def __init__(self):
        self.total_compressions: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self._ratios: Deque[float] = deque(maxlen=100)

    @property
    def avg_ratio(self) -> float:
        if not self._ratios:
            return 1.0
        return sum(self._ratios) / len(self._ratios)

    @property
    def tokens_saved(self) -> int:
        return max(0, self.total_input_tokens - self.total_output_tokens)

    def record(self, input_tokens: int, output_tokens: int):
        self.total_compressions += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        if input_tokens > 0:
            self._ratios.append(output_tokens / input_tokens)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_compressions": self.total_compressions,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "tokens_saved": self.tokens_saved,
            "avg_compression_ratio": round(self.avg_ratio, 3),
        }


class TokenCompressor:
    """
    Compresses prompts and conversation histories to reduce token usage.

    Strategies:
    1. Deduplication — remove repeated content
    2. History summarization — summarize old messages
    3. System prompt trimming — remove verbose instructions
    4. Context window management — keep most relevant messages
    5. Whitespace normalization — reduce unnecessary whitespace
    """

    def __init__(self):
        self.stats = CompressionStats()

    def compress(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        preserve_system: bool = True,
        preserve_recent: int = 4,
        summarize_old: bool = True,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """
        Compress a message list to fit within max_tokens.

        Args:
            messages: List of {role, content} messages
            max_tokens: Target maximum token count
            preserve_system: Keep system message intact
            preserve_recent: Number of recent messages to keep verbatim
            summarize_old: Whether to summarize old messages

        Returns:
            (compressed_messages, compression_info)
        """
        input_tokens = estimate_messages_tokens(messages)

        if input_tokens <= max_tokens:
            return messages, {
                "compressed": False,
                "input_tokens": input_tokens,
                "output_tokens": input_tokens,
                "ratio": 1.0,
                "strategy": "none",
            }

        # Strategy 1: Normalize whitespace first
        normalized = self._normalize_whitespace(messages)
        norm_tokens = estimate_messages_tokens(normalized)

        if norm_tokens <= max_tokens:
            self.stats.record(input_tokens, norm_tokens)
            return normalized, {
                "compressed": True,
                "input_tokens": input_tokens,
                "output_tokens": norm_tokens,
                "ratio": round(norm_tokens / input_tokens, 3),
                "strategy": "whitespace_normalization",
            }

        # Strategy 2: Deduplicate
        deduped = self._deduplicate(normalized)
        dedup_tokens = estimate_messages_tokens(deduped)

        if dedup_tokens <= max_tokens:
            self.stats.record(input_tokens, dedup_tokens)
            return deduped, {
                "compressed": True,
                "input_tokens": input_tokens,
                "output_tokens": dedup_tokens,
                "ratio": round(dedup_tokens / input_tokens, 3),
                "strategy": "deduplication",
            }

        # Strategy 3: Trim old conversation history
        trimmed = self._trim_history(deduped, max_tokens, preserve_system, preserve_recent)
        trim_tokens = estimate_messages_tokens(trimmed)

        if trim_tokens <= max_tokens:
            self.stats.record(input_tokens, trim_tokens)
            return trimmed, {
                "compressed": True,
                "input_tokens": input_tokens,
                "output_tokens": trim_tokens,
                "ratio": round(trim_tokens / input_tokens, 3),
                "strategy": "history_trimming",
            }

        # Strategy 4: Summarize old messages + keep recent
        if summarize_old:
            summarized = self._summarize_old(trimmed, max_tokens, preserve_system, preserve_recent)
            sum_tokens = estimate_messages_tokens(summarized)
            self.stats.record(input_tokens, sum_tokens)
            return summarized, {
                "compressed": True,
                "input_tokens": input_tokens,
                "output_tokens": sum_tokens,
                "ratio": round(sum_tokens / input_tokens, 3),
                "strategy": "summarization",
            }

        # Strategy 5: Aggressive truncation
        final = self._aggressive_truncate(trimmed, max_tokens, preserve_system)
        final_tokens = estimate_messages_tokens(final)
        self.stats.record(input_tokens, final_tokens)
        return final, {
            "compressed": True,
            "input_tokens": input_tokens,
            "output_tokens": final_tokens,
            "ratio": round(final_tokens / input_tokens, 3),
            "strategy": "aggressive_truncation",
        }

    def _normalize_whitespace(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Remove excessive whitespace and normalize formatting."""
        result = []
        for msg in messages:
            content = msg.get("content", "")
            # Collapse multiple newlines
            content = re.sub(r"\n{3,}", "\n\n", content)
            # Collapse multiple spaces
            content = re.sub(r" {2,}", " ", content)
            # Strip leading/trailing whitespace per line
            lines = [line.strip() for line in content.split("\n")]
            content = "\n".join(lines).strip()
            result.append({"role": msg["role"], "content": content})
        return result

    def _deduplicate(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Remove duplicate or near-duplicate messages."""
        seen_hashes = set()
        result = []
        for msg in messages:
            content = msg.get("content", "").strip()
            # Hash for exact dedup
            h = hashlib.md5(content.encode()).hexdigest()
            if h not in seen_hashes:
                seen_hashes.add(h)
                result.append(msg)
        return result

    def _trim_history(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        preserve_system: bool,
        preserve_recent: int,
    ) -> List[Dict[str, str]]:
        """Keep system prompt + most recent messages, drop oldest middle messages."""
        system_msgs = []
        other_msgs = []

        for msg in messages:
            if preserve_system and msg["role"] == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)

        # Always keep the most recent messages
        recent = other_msgs[-preserve_recent:] if preserve_recent > 0 else []
        older = other_msgs[:-preserve_recent] if preserve_recent > 0 else other_msgs

        # Budget remaining tokens for older messages
        system_tokens = estimate_messages_tokens(system_msgs)
        recent_tokens = estimate_messages_tokens(recent)
        remaining_budget = max_tokens - system_tokens - recent_tokens

        # Keep as many old messages as fit
        kept_old = []
        used = 0
        # Keep from newest-old to oldest-old
        for msg in reversed(older):
            msg_tokens = estimate_messages_tokens([msg])
            if used + msg_tokens <= remaining_budget:
                kept_old.insert(0, msg)
                used += msg_tokens
            else:
                break

        return system_msgs + kept_old + recent

    def _summarize_old(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        preserve_system: bool,
        preserve_recent: int,
    ) -> List[Dict[str, str]]:
        """
        Replace old messages with a summary placeholder.

        Since we can't call another model here, we create a condensed
        representation by extracting key points.
        """
        system_msgs = []
        other_msgs = []

        for msg in messages:
            if preserve_system and msg["role"] == "system":
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)

        recent = other_msgs[-preserve_recent:] if preserve_recent > 0 else []
        older = other_msgs[:-preserve_recent] if preserve_recent > 0 else []

        if not older:
            return messages

        # Build a compressed summary of older messages
        summary_parts = []
        for msg in older:
            content = msg.get("content", "")
            # Take first sentence or first 100 chars
            first_line = content.split("\n")[0][:150]
            summary_parts.append(f"[{msg['role']}]: {first_line}")

        summary_text = "Previous conversation summary:\n" + "\n".join(summary_parts[-10:])
        summary_msg = {"role": "system", "content": summary_text}

        result = system_msgs + [summary_msg] + recent

        # If still over budget, truncate the summary
        if estimate_messages_tokens(result) > max_tokens:
            budget_for_summary = max_tokens - estimate_messages_tokens(system_msgs) - estimate_messages_tokens(recent)
            budget_for_summary = max(100, budget_for_summary)
            truncated = summary_text[:budget_for_summary * CHARS_PER_TOKEN]
            summary_msg = {"role": "system", "content": truncated + "..."}
            result = system_msgs + [summary_msg] + recent

        return result

    def _aggressive_truncate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        preserve_system: bool,
    ) -> List[Dict[str, str]]:
        """Last resort: aggressively truncate messages to fit."""
        result = []
        used = 0

        # Process in order, keeping as much as possible
        for msg in messages:
            msg_tokens = estimate_messages_tokens([msg])
            if used + msg_tokens <= max_tokens:
                result.append(msg)
                used += msg_tokens
            else:
                # Try to fit a truncated version
                remaining = max_tokens - used
                if remaining > 20:
                    chars = remaining * CHARS_PER_TOKEN
                    truncated_content = msg.get("content", "")[:chars] + "..."
                    result.append({"role": msg["role"], "content": truncated_content})
                break

        return result

    def compress_text(self, text: str, max_tokens: int = 2000) -> Tuple[str, Dict[str, Any]]:
        """Compress a single text string."""
        input_tokens = estimate_tokens(text)
        if input_tokens <= max_tokens:
            return text, {"compressed": False, "input_tokens": input_tokens, "output_tokens": input_tokens}

        # Normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        if estimate_tokens(text) <= max_tokens:
            output_tokens = estimate_tokens(text)
            self.stats.record(input_tokens, output_tokens)
            return text, {"compressed": True, "input_tokens": input_tokens, "output_tokens": output_tokens, "strategy": "whitespace"}

        # Truncate to max
        chars = max_tokens * CHARS_PER_TOKEN
        compressed = text[:chars] + "..."
        output_tokens = estimate_tokens(compressed)
        self.stats.record(input_tokens, output_tokens)
        return compressed, {"compressed": True, "input_tokens": input_tokens, "output_tokens": output_tokens, "strategy": "truncation"}

    def get_stats(self) -> Dict[str, Any]:
        return self.stats.to_dict()


# Singleton
_compressor: Optional[TokenCompressor] = None


def get_token_compressor() -> TokenCompressor:
    global _compressor
    if _compressor is None:
        _compressor = TokenCompressor()
    return _compressor
