"""
Compression utilities using zstd.

zstd (Zstandard) provides 60-70% compression on JSON transaction data,
reducing sync payloads from ~17KB to ~5KB per user per day.

This is critical for devices on 2G/3G connections where bandwidth
is extremely limited.
"""

import json
from typing import Any, Dict, Optional

import zstandard as zstd


def compress_payload(
    data: Dict[str, Any],
    level: int = 3,
) -> bytes:
    """
    Compress a dictionary payload using zstd.

    Args:
        data: Dictionary to compress (will be JSON-serialized)
        level: Compression level (1-22, default 3 for speed/compression balance)
               1 = fastest, 22 = best compression, 3 = good balance

    Returns:
        Compressed bytes
    """
    json_bytes = json.dumps(data, default=str).encode("utf-8")
    cctx = zstd.ZstdCompressor(level=level)
    return cctx.compress(json_bytes)


def decompress_payload(compressed: bytes) -> Dict[str, Any]:
    """
    Decompress a zstd-compressed payload back to a dictionary.

    Args:
        compressed: Compressed bytes

    Returns:
        Decompressed dictionary

    Raises:
        zstd.ZstdError: If decompression fails
        json.JSONDecodeError: If decompressed data isn't valid JSON
    """
    dctx = zstd.ZstdDecompressor()
    json_bytes = dctx.decompress(compressed)
    return json.loads(json_bytes.decode("utf-8"))


def compress_json_string(
    json_str: str,
    level: int = 3,
) -> bytes:
    """
    Compress a JSON string directly.

    Args:
        json_str: JSON string to compress
        level: Compression level

    Returns:
        Compressed bytes
    """
    cctx = zstd.ZstdCompressor(level=level)
    return cctx.compress(json_str.encode("utf-8"))


def decompress_to_string(compressed: bytes) -> str:
    """
    Decompress bytes back to a string.

    Args:
        compressed: Compressed bytes

    Returns:
        Decompressed string
    """
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(compressed).decode("utf-8")


def estimate_compression_ratio(data: Dict[str, Any]) -> float:
    """
    Estimate the compression ratio for a given payload.

    Useful for pre-flight checks to decide whether compression
    is worthwhile (small payloads may not benefit).

    Args:
        data: Dictionary to estimate compression for

    Returns:
        Estimated compression ratio (0.0-1.0, lower = more compression)
    """
    json_bytes = json.dumps(data, default=str).encode("utf-8")
    original_size = len(json_bytes)

    if original_size < 100:
        return 1.0  # Too small to benefit

    cctx = zstd.ZstdCompressor(level=3)
    compressed = cctx.compress(json_bytes)
    compressed_size = len(compressed)

    return compressed_size / original_size


def get_compression_level_for_network(network_type: Optional[str]) -> int:
    """
    Get recommended compression level based on network type.

    Slower networks get higher compression (more CPU, less bandwidth).
    Fast networks get lower compression (less CPU, acceptable bandwidth).

    Args:
        network_type: Network type string (wifi, mobile_2g, mobile_3g, etc.)

    Returns:
        Recommended zstd compression level (1-22)
    """
    levels = {
        "wifi": 1,           # Fast network, minimize CPU
        "mobile_5g": 3,      # Fast mobile, balanced
        "mobile_4g": 5,      # Good mobile, favor compression
        "mobile_3g": 10,     # Slow mobile, high compression
        "mobile_2g": 15,     # Very slow, maximum compression
        "offline": 3,        # Offline — compress for later sync
    }
    return levels.get(network_type, 3)
