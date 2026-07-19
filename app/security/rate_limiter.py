"""
Rate limiting middleware for FastAPI.

Implements per-endpoint, per-IP, and per-user rate limiting using
a sliding window algorithm with Redis backend (in-memory fallback).

Protects against:
- Brute force attacks on OTP/auth endpoints
- API abuse and scraping
- Denial-of-service via request flooding
- Credential stuffing

Per SECURITY_ARCHITECTURE.md Section 5.1 and OWASP API Security Top 10.
"""

import asyncio
import hashlib
import ipaddress
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """A rate limit rule."""
    max_requests: int
    window_seconds: int
    burst_allowance: int = 0  # Extra requests allowed above max in burst
    block_duration_seconds: int = 0  # How long to block after exceeding (0 = no block)


@dataclass
class SlidingWindowCounter:
    """Sliding window rate limit counter."""
    timestamps: list[float] = field(default_factory=list)
    blocked_until: float = 0.0

    def cleanup(self, window_seconds: int):
        """Remove expired entries."""
        cutoff = time.time() - window_seconds
        self.timestamps = [ts for ts in self.timestamps if ts > cutoff]

    def count(self, window_seconds: int) -> int:
        """Count requests in the current window."""
        self.cleanup(window_seconds)
        return len(self.timestamps)

    def is_blocked(self) -> bool:
        """Check if currently blocked."""
        return self.blocked_until > time.time()

    def record(self):
        """Record a request."""
        self.timestamps.append(time.time())

    def block(self, duration_seconds: int):
        """Block for a duration."""
        self.blocked_until = time.time() + duration_seconds


class RateLimitStore:
    """In-memory rate limit store with automatic cleanup."""

    def __init__(self):
        self._counters: dict[str, SlidingWindowCounter] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = 60  # Cleanup every 60 seconds
        self._last_cleanup = time.time()

    async def check_and_record(
        self,
        key: str,
        rule: RateLimitRule,
    ) -> tuple[bool, int, int]:
        """
        Check rate limit and record the request.

        Returns:
            (allowed, current_count, limit)
        """
        async with self._lock:
            now = time.time()

            # Periodic cleanup
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup()
                self._last_cleanup = now

            counter = self._counters.get(key)
            if counter is None:
                counter = SlidingWindowCounter()
                self._counters[key] = counter

            # Check if blocked
            if counter.is_blocked():
                remaining = int(counter.blocked_until - now)
                return False, rule.max_requests + 1, rule.max_requests

            # Count in window
            counter.cleanup(rule.window_seconds)
            current = counter.count(rule.window_seconds)

            # Check limit
            if current >= rule.max_requests + rule.burst_allowance:
                # Exceeded — apply block if configured
                if rule.block_duration_seconds > 0:
                    counter.block(rule.block_duration_seconds)
                    logger.warning(
                        "Rate limit exceeded for key=%s: %d/%d in %ds — blocked for %ds",
                        key[:50], current, rule.max_requests,
                        rule.window_seconds, rule.block_duration_seconds,
                    )
                return False, current, rule.max_requests

            # Record the request
            counter.record()
            return True, current + 1, rule.max_requests

    def _cleanup(self):
        """Remove expired counters."""
        expired_keys = []
        for key, counter in self._counters.items():
            counter.cleanup(3600)  # Clean entries older than 1 hour
            if not counter.timestamps and not counter.is_blocked():
                expired_keys.append(key)
        for key in expired_keys:
            del self._counters[key]


# ══════════════════════════════════════════════════════════════
# Predefined rate limit rules per endpoint category
# ══════════════════════════════════════════════════════════════

RATE_LIMITS = {
    # Authentication endpoints — strict limits
    "auth/otp_request": RateLimitRule(
        max_requests=3, window_seconds=600,  # 3 per 10 min per phone
        burst_allowance=0, block_duration_seconds=600,
    ),
    "auth/otp_verify": RateLimitRule(
        max_requests=5, window_seconds=600,  # 5 attempts per 10 min
        burst_allowance=0, block_duration_seconds=900,  # 15 min lockout
    ),
    "auth/register": RateLimitRule(
        max_requests=5, window_seconds=3600,  # 5 registrations per hour per IP
        burst_allowance=0, block_duration_seconds=3600,
    ),
    "auth/refresh": RateLimitRule(
        max_requests=30, window_seconds=3600,  # 30 refreshes per hour
        burst_allowance=5, block_duration_seconds=0,
    ),
    # API key endpoints — moderate limits
    "api/intelligence": RateLimitRule(
        max_requests=100, window_seconds=60,  # 100 per minute per API key
        burst_allowance=20, block_duration_seconds=0,
    ),
    "api/market": RateLimitRule(
        max_requests=60, window_seconds=60,  # 60 per minute
        burst_allowance=10, block_duration_seconds=0,
    ),
    # Transaction endpoints — per-user limits
    "transactions/send": RateLimitRule(
        max_requests=10, window_seconds=300,  # 10 per 5 min
        burst_allowance=0, block_duration_seconds=300,
    ),
    "transactions/history": RateLimitRule(
        max_requests=30, window_seconds=60,  # 30 per minute
        burst_allowance=5, block_duration_seconds=0,
    ),
    # General API — per-IP limits
    "default": RateLimitRule(
        max_requests=200, window_seconds=60,  # 200 per minute per IP
        burst_allowance=50, block_duration_seconds=0,
    ),
    # Federated learning — per-device limits
    "fl/upload": RateLimitRule(
        max_requests=10, window_seconds=3600,  # 10 gradient uploads per hour
        burst_allowance=0, block_duration_seconds=0,
    ),
}


# ══════════════════════════════════════════════════════════════
# Trusted Proxy Configuration
# ══════════════════════════════════════════════════════════════
#
# Only trust X-Forwarded-For headers from these known proxy IPs.
# Configure via ANGAVU_TRUSTED_PROXIES env var (comma-separated CIDRs).
# Default covers common cloud load balancer and Docker network ranges.
#
# SECURITY: If this list is empty or misconfigured, X-Forwarded-For is
# IGNORED and we fall back to the direct connection IP. This prevents
# attackers from spoofing the header to bypass rate limits.

_DEFAULT_TRUSTED_PROXIES = [
    "127.0.0.0/8",       # localhost
    "10.0.0.0/8",        # RFC 1918 private
    "172.16.0.0/12",     # RFC 1918 private (Docker default)
    "192.168.0.0/16",    # RFC 1918 private
    "100.64.0.0/10",     # RFC 6598 CGNAT (cloud LBs)
]


def _load_trusted_proxies() -> set[ipaddress.IPv4Network]:
    """Load trusted proxy CIDRs from environment or use defaults."""
    env_val = os.getenv("ANGAVU_TRUSTED_PROXIES", "")
    if env_val:
        cidrs = [c.strip() for c in env_val.split(",") if c.strip()]
    else:
        cidrs = _DEFAULT_TRUSTED_PROXIES

    networks = set()
    for cidr in cidrs:
        try:
            networks.add(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("Invalid trusted proxy CIDR ignored: %s", cidr)
    return networks


_TRUSTED_PROXY_NETS: set[ipaddress.IPv4Network] = _load_trusted_proxies()


def _is_trusted_proxy(ip_str: str) -> bool:
    """Check if an IP address belongs to a trusted proxy network."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _TRUSTED_PROXY_NETS)
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """
    Extract client IP, respecting X-Forwarded-For ONLY from trusted proxies.

    Security model:
    1. Get the direct connection IP (request.client.host)
    2. If the direct IP is a trusted proxy, parse X-Forwarded-For
    3. Walk the chain right-to-left, stopping at the first non-trusted IP
       (that's the real client)
    4. If direct IP is NOT a trusted proxy, ignore X-Forwarded-For entirely

    This prevents attackers from spoofing X-Forwarded-For to bypass
    rate limits or hide their identity.
    """
    direct_ip = request.client.host if request.client else "unknown"

    # Only trust X-Forwarded-For if the direct connection is from a trusted proxy
    if direct_ip == "unknown" or not _is_trusted_proxy(direct_ip):
        return direct_ip

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return direct_ip

    # Parse the chain: client, proxy1, proxy2, ...
    # Walk right-to-left; each trusted proxy may have appended its entry.
    # The rightmost non-trusted IP is the real client.
    ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]

    # Walk from right (closest to us) to left (original client)
    # Skip trusted proxy IPs, return the first non-trusted one
    for ip in reversed(ips):
        if not _is_trusted_proxy(ip):
            try:
                ipaddress.ip_address(ip)  # Validate it's a real IP
                return ip
            except ValueError:
                continue

    # All IPs in chain were trusted proxies — use direct IP
    return direct_ip


def get_rate_limit_key(request: Request, rule_name: str) -> str:
    """Generate a rate limit key combining IP, user identity, and endpoint."""
    ip = get_client_ip(request)
    # Try to extract user identifier from auth header
    auth = request.headers.get("Authorization", "")
    user_hash = hashlib.sha256(auth.encode()).hexdigest()[:16] if auth else "anon"

    return f"rl:{rule_name}:{ip}:{user_hash}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Applies rate limits based on endpoint pattern matching.
    Returns standard 429 Too Many Requests with Retry-After header.
    """

    def __init__(self, app, store: RateLimitStore | None = None):
        super().__init__(app)
        self.store = store or RateLimitStore()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Determine which rate limit rule applies
        rule_name = self._match_endpoint(request.url.path)
        rule = RATE_LIMITS.get(rule_name, RATE_LIMITS["default"])

        # Generate rate limit key
        key = get_rate_limit_key(request, rule_name)

        # Check rate limit
        allowed, current, limit = await self.store.check_and_record(key, rule)

        if not allowed:
            retry_after = rule.block_duration_seconds if rule.block_duration_seconds > 0 else rule.window_seconds
            logger.warning(
                "Rate limit exceeded: path=%s, key=%s, current=%d, limit=%d",
                request.url.path, key[:50], current, limit,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current))
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + rule.window_seconds)

        return response

    def _match_endpoint(self, path: str) -> str:
        """Match URL path to rate limit rule name."""
        path_lower = path.lower().rstrip("/")

        if "/auth/otp" in path_lower or "/otp" in path_lower:
            if "verify" in path_lower:
                return "auth/otp_verify"
            return "auth/otp_request"
        if "/auth/register" in path_lower:
            return "auth/register"
        if "/auth/refresh" in path_lower:
            return "auth/refresh"
        if "/intelligence" in path_lower:
            return "api/intelligence"
        if "/market" in path_lower:
            return "api/market"
        if "/transactions/send" in path_lower:
            return "transactions/send"
        if "/transactions" in path_lower:
            return "transactions/history"
        if "/fl/upload" in path_lower or "/federated" in path_lower:
            return "fl/upload"

        return "default"


# ══════════════════════════════════════════════════════════════
# Decorator for per-endpoint rate limiting (alternative to middleware)
# ══════════════════════════════════════════════════════════════

_global_store = RateLimitStore()


def rate_limit(
    max_requests: int,
    window_seconds: int,
    burst_allowance: int = 0,
    block_duration_seconds: int = 0,
    key_func: Callable | None = None,
):
    """
    Decorator for per-endpoint rate limiting.

    Usage:
        @router.post("/auth/otp")
        @rate_limit(max_requests=3, window_seconds=600)
        async def request_otp(request: Request, ...):
            ...
    """
    rule = RateLimitRule(
        max_requests=max_requests,
        window_seconds=window_seconds,
        burst_allowance=burst_allowance,
        block_duration_seconds=block_duration_seconds,
    )

    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            if key_func:
                key = key_func(request)
            else:
                key = get_rate_limit_key(request, func.__name__)

            allowed, current, limit = await _global_store.check_and_record(key, rule)

            if not allowed:
                retry_after = block_duration_seconds if block_duration_seconds > 0 else window_seconds
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
