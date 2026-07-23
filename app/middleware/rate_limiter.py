"""
Per-endpoint rate limiting middleware using Redis sliding window.

Architecture: arch_backend.md §7

Wires rate limits to all API endpoints:
- /api/v1/sync/*          → 100/hour per worker
- /api/v1/buyer/report/*  → 200/hour per worker
- /api/v1/intelligence/*  → 50/hour per worker
- /api/v1/buyer/*         → 1000/hour per API key

Adds X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
headers to every response. Returns 429 Too Many Requests when exceeded.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Optional, Tuple

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger(__name__)

# ── Tier definitions ──────────────────────────────────────────────────────────
# (prefix, default_limit, default_window_seconds, identity_header)
# Order matters: more specific prefixes must come first.

TIERS: list[dict] = [
    {
        "name": "buyer_report",
        "prefix": "/api/v1/buyer/report",
        "limit": 200,
        "window": 3600,
        "identity": "api_key",  # per buyer API key
    },
    {
        "name": "buyer",
        "prefix": "/api/v1/buyer",
        "limit": 1000,
        "window": 3600,
        "identity": "api_key",
    },
    {
        "name": "sync",
        "prefix": "/api/v1/sync",
        "limit": 100,
        "window": 3600,
        "identity": "worker",
    },
    {
        "name": "intelligence",
        "prefix": "/api/v1/intelligence",
        "limit": 50,
        "window": 3600,
        "identity": "worker",
    },
]


def _parse_rate(s: str) -> Tuple[int, int]:
    """Parse '100/hour' → (100, 3600)."""
    try:
        count, unit = s.split("/")
        count = int(count.strip())
        unit = unit.strip().lower()
        window = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}.get(unit, 3600)
        return count, window
    except Exception:
        return 100, 3600


def _extract_jwt_sub(authorization: str) -> Optional[str]:
    """Extract 'sub' claim from JWT without verifying (verification happens in route)."""
    try:
        parts = authorization.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1] + "=="  # padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("sub") or payload.get("wid")
    except Exception:
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that enforces per-client rate limits using Redis.

    For each request:
    1. Match path to a tier (sync / intelligence / buyer / buyer_report).
    2. Resolve client identity (worker JWT sub, API key, or fallback to IP).
    3. Increment a Redis key with a sliding-window TTL.
    4. Attach X-RateLimit-* headers to the response.
    5. Return 429 if the limit is exceeded.
    """

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self._redis = redis_client  # injected at startup; lazy-fallback if None

    # ── helpers ───────────────────────────────────────────────────────────

    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        from app.db.redis import get_redis
        self._redis = await get_redis()
        return self._redis

    @staticmethod
    def _match_tier(path: str) -> Optional[dict]:
        """Return the first matching tier dict for *path*, or None."""
        for tier in TIERS:
            if path.startswith(tier["prefix"]):
                return tier
        return None

    @staticmethod
    def _resolve_identity(request: Request, tier: dict) -> str:
        """Determine the rate-limit key for this client."""
        if tier["identity"] == "worker":
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                sub = _extract_jwt_sub(auth)
                if sub:
                    return f"worker:{sub}"
            # fallback to IP for unauthenticated sync/intelligence calls
            return f"ip:{request.client.host if request.client else 'unknown'}"

        if tier["identity"] == "api_key":
            api_key = request.headers.get("x-api-key", "")
            if api_key:
                return f"apikey:{api_key}"
            # Also try to extract from JWT for OAuth2-authenticated buyers
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                sub = _extract_jwt_sub(auth)
                if sub:
                    return f"buyer:{sub}"
            return f"ip:{request.client.host if request.client else 'unknown'}"

        return f"ip:{request.client.host if request.client else 'unknown'}"

    # ── middleware entry point ─────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Only rate-limit API routes; let health/docs/metrics/root through
        if not path.startswith("/api/v1/"):
            return await call_next(request)

        tier = self._match_tier(path)
        if tier is None:
            return await call_next(request)

        # Resolve limits (config overrides defaults)
        limit, window = self._resolve_limits(tier)

        # Build Redis key
        identity = self._resolve_identity(request, tier)
        now = int(time.time())
        window_start = now - (now % window)  # align to window boundary
        key = f"rl:{tier['name']}:{identity}:{window_start}"

        try:
            r = await self._get_redis()
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, window + 1)  # +1 for safety
            results = await pipe.execute()
            current = int(results[0])
        except Exception as exc:
            logger.warning("rate_limit_redis_error", error=str(exc))
            # Fail open — don't block requests if Redis is down
            return await call_next(request)

        remaining = max(0, limit - current)
        reset_ts = window_start + window

        # Set rate-limit headers on every response (even 429)
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_ts),
        }

        if current > limit:
            retry_after = max(1, reset_ts - now)
            headers["Retry-After"] = str(retry_after)
            logger.info(
                "rate_limit_exceeded",
                tier=tier["name"],
                identity=identity,
                current=current,
                limit=limit,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "tier": tier["name"],
                    "limit": limit,
                    "window_seconds": window,
                    "retry_after": retry_after,
                },
                headers=headers,
            )

        response = await call_next(request)

        # Inject rate-limit headers into the upstream response
        for k, v in headers.items():
            response.headers[k] = v

        return response

    # ── config integration ────────────────────────────────────────────────

    @staticmethod
    def _resolve_limits(tier: dict) -> Tuple[int, int]:
        """Read limits from settings if available, else use tier defaults."""
        from app.config import settings

        config_map = {
            "sync": "RATE_LIMIT_SYNC",
            "intelligence": "RATE_LIMIT_INTELLIGENCE",
            "buyer_report": "RATE_LIMIT_REPORTS",
            "buyer": "RATE_LIMIT_BUYER",
        }
        attr = config_map.get(tier["name"])
        if attr and hasattr(settings, attr):
            return _parse_rate(getattr(settings, attr))
        return tier["limit"], tier["window"]


# ── Public helper: per-route dependency (preserved for backward compat) ──────

def create_rate_limiter(requests: int = 100, window: int = 3600):
    """Factory for per-route FastAPI Depends() rate limiters."""
    from fastapi import Request as _Req
    from starlette.exceptions import HTTPException as _HTTPExc

    _limiter = None

    async def _get_limiter():
        nonlocal _limiter
        if _limiter is None:
            from app.db.redis import get_redis
            r = await get_redis()
            _limiter = _RateLimiterDep(r, requests, window)
        return _limiter

    async def rate_limit(request: _Req):
        limiter = await _get_limiter()
        await limiter(request)

    return rate_limit


class _RateLimiterDep:
    """Redis-backed per-route rate limiter (used via Depends)."""

    def __init__(self, redis_client, requests: int = 100, window: int = 3600):
        self.redis = redis_client
        self.requests = requests
        self.window = window

    async def __call__(self, request):
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate:{request.url.path}:{client_ip}"
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, self.window)
        if current > self.requests:
            from fastapi import HTTPException
            raise HTTPException(
                429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(self.window)},
            )
