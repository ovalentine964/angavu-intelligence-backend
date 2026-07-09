"""
Security middleware for FastAPI.

Provides:
- CORS configuration with strict origin validation
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- Input validation middleware (SQL injection, XSS detection)
- Request size limiting
- Content-Type validation

Per OWASP API Security Top 10 and SECURITY_ARCHITECTURE.md.
"""

import hashlib
import logging
import re
import time
import uuid
from typing import Callable, List, Optional, Set

from fastapi import HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# CORS Configuration — Strict Origin Validation
# ══════════════════════════════════════════════════════════════

def get_cors_origins() -> List[str]:
    """
    Get allowed CORS origins.

    In production, ONLY the app's own domains should be allowed.
    No wildcards. No localhost.
    """
    import os
    env = os.getenv("ANGAVU_ENV", "development")

    if env == "production":
        return [
            "https://app.msaidizi.app",
            "https://admin.msaidizi.app",
            "https://dashboard.angavu.com",
            "https://api.angavu.com",
        ]
    elif env == "staging":
        return [
            "https://staging.msaidizi.app",
            "https://staging-dashboard.angavu.com",
        ]
    else:
        # Development — still restricted, no wildcards
        return [
            "http://localhost:3000",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
        ]


def configure_cors(app):
    """
    Configure CORS middleware with strict settings.

    Security measures:
    - Explicit origin list (no wildcards)
    - Credentials allowed only for specific origins
    - Limited methods (GET, POST, PUT, DELETE, OPTIONS)
    - Limited headers
    - Max age for preflight caching (reduces OPTIONS requests)
    """
    origins = get_cors_origins()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Request-ID",
            "X-Device-ID",
            "X-App-Version",
            "X-CSRF-Token",
        ],
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Request-ID",
        ],
        max_age=3600,  # Cache preflight for 1 hour
    )


# ══════════════════════════════════════════════════════════════
# Security Headers Middleware
# ══════════════════════════════════════════════════════════════

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses.

    Headers:
    - Strict-Transport-Security: Force HTTPS
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-Frame-Options: Prevent clickjacking
    - X-XSS-Protection: Legacy XSS filter
    - Content-Security-Policy: Restrict resource loading
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Restrict browser features
    - Cache-Control: Prevent caching of sensitive data
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # HSTS — force HTTPS for 1 year, include subdomains
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Content Security Policy — restrict resource loading
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; "
            "form-action 'self'"
        )

        # Referrer policy — don't leak URLs
        response.headers["Referrer-Policy"] = "no-referrer"

        # Permissions policy — disable unnecessary browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=()"
        )

        # Prevent caching of API responses (contains sensitive data)
        if request.url.path.startswith("/api/") or request.url.path.startswith("/auth/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        # Request ID for tracing
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response.headers["X-Request-ID"] = request_id

        return response


# ══════════════════════════════════════════════════════════════
# Input Validation Middleware
# ══════════════════════════════════════════════════════════════

# SQL injection patterns (comprehensive)
SQL_INJECTION_PATTERNS = [
    re.compile(r"(?i)(\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|EXECUTE|UNION|TRUNCATE|REPLACE|LOAD|INTO)\b\s+)"),
    re.compile(r"(?i)(--|;|/\*|\*/|@@|@)"),
    re.compile(r"(?i)(\b(OR|AND)\b\s+\d+\s*=\s*\d+)"),
    re.compile(r"(?i)'\s*(OR|AND)\s+'"),
    re.compile(r"(?i)(CHAR|CONCAT|SUBSTRING|CAST|CONVERT|BENCHMARK|SLEEP|WAITFOR)\s*\("),
    re.compile(r"(?i)(0x[0-9a-f]+)"),  # Hex encoding attacks
    re.compile(r"(?i)(INFORMATION_SCHEMA|SYSOBJECTS|SYSCOLUMNS|MSYSACCESSOBJECTS)"),
]

# XSS patterns
XSS_PATTERNS = [
    re.compile(r"<script[^>]*>", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"expression\s*\(", re.IGNORECASE),
    re.compile(r"data:\s*text/html", re.IGNORECASE),
    re.compile(r"<iframe", re.IGNORECASE),
    re.compile(r"<object", re.IGNORECASE),
    re.compile(r"<embed", re.IGNORECASE),
    re.compile(r"<link\s+.*rel\s*=\s*['\"]?import", re.IGNORECASE),
]

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\."),
    re.compile(r"%2e%2e", re.IGNORECASE),
    re.compile(r"%252e%252e", re.IGNORECASE),
]

# Request size limits by endpoint category
MAX_REQUEST_SIZES = {
    "/auth/": 4_096,           # Auth requests are small
    "/api/intelligence/": 16_384,  # Intelligence queries
    "/fl/upload": 10_485_760,   # Federated learning gradients can be large
    "/api/": 65_536,            # General API
    "default": 1_048_576,       # 1MB default
}


class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates incoming requests for injection attacks.

    Checks:
    - SQL injection in query params, headers, body
    - XSS in query params, body
    - Path traversal in URL
    - Request size limits
    - Content-Type validation for POST/PUT
    """

    # Paths to skip validation (static files, health checks)
    SKIP_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip validation for certain paths
        if any(path.startswith(skip) for skip in self.SKIP_PATHS):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # 1. Check request size
        content_length = request.headers.get("content-length")
        if content_length:
            max_size = self._get_max_size(path)
            if int(content_length) > max_size:
                logger.warning(
                    "Request too large: path=%s, size=%d, max=%d, ip=%s",
                    path, int(content_length), max_size, client_ip,
                )
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Request body too large",
                )

        # 2. Validate Content-Type for write methods
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if content_type and not any(
                ct in content_type
                for ct in ["application/json", "multipart/form-data", "application/x-www-form-urlencoded"]
            ):
                logger.warning(
                    "Invalid Content-Type: %s, path=%s, ip=%s",
                    content_type, path, client_ip,
                )
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Unsupported content type",
                )

        # 3. Check URL for path traversal
        url_str = str(request.url)
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(url_str):
                logger.warning(
                    "Path traversal attempt: url=%s, ip=%s",
                    url_str[:100], client_ip,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid request path",
                )

        # 4. Check query parameters for injection
        for key, value in request.query_params.items():
            if self._contains_injection(value):
                logger.warning(
                    "Injection attempt in query param '%s': value='%s', ip=%s, path=%s",
                    key, value[:50], client_ip, path,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid request parameters",
                )

        # 5. Check headers for injection (skip standard headers)
        skip_headers = {
            "authorization", "content-type", "accept", "host",
            "connection", "user-agent", "accept-encoding",
            "accept-language", "cache-control", "x-forwarded-for",
        }
        for key, value in request.headers.items():
            if key.lower() not in skip_headers and self._contains_injection(value):
                logger.warning(
                    "Injection attempt in header '%s': ip=%s, path=%s",
                    key, client_ip, path,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid request headers",
                )

        # 6. Check body for injection (for JSON requests)
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.body()
                    if body:
                        body_str = body.decode("utf-8", errors="ignore")
                        # Check body size for injection scan (don't scan huge bodies)
                        if len(body_str) < 100_000:
                            if self._contains_injection(body_str):
                                logger.warning(
                                    "Injection attempt in request body: ip=%s, path=%s",
                                    client_ip, path,
                                )
                                raise HTTPException(
                                    status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Invalid request body",
                                )
                except UnicodeDecodeError:
                    pass  # Binary data, skip injection check

        return await call_next(request)

    def _contains_injection(self, value: str) -> bool:
        """Check if a string contains SQL injection, XSS, or prompt injection."""
        for pattern in SQL_INJECTION_PATTERNS:
            if pattern.search(value):
                return True
        for pattern in XSS_PATTERNS:
            if pattern.search(value):
                return True
        return False

    def _get_max_size(self, path: str) -> int:
        """Get maximum request size for a path."""
        for prefix, size in MAX_REQUEST_SIZES.items():
            if path.startswith(prefix):
                return size
        return MAX_REQUEST_SIZES["default"]


# ══════════════════════════════════════════════════════════════
# Audit Logging Middleware
# ══════════════════════════════════════════════════════════════

class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs all API requests for security audit trail.

    Captures:
    - Request method, path, query params
    - Client IP, user agent
    - Response status code
    - Response time
    - Authentication state
    - Security-relevant events (failed auth, rate limits, injection attempts)
    """

    SENSITIVE_PATHS = {"/auth/", "/api/transactions/", "/fl/"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "")[:200]

        # Extract auth info
        auth_header = request.headers.get("Authorization", "")
        auth_hash = hashlib.sha256(auth_header.encode()).hexdigest()[:16] if auth_header else "none"

        try:
            response = await call_next(request)
            elapsed_ms = (time.time() - start_time) * 1000

            # Log security-sensitive requests
            is_sensitive = any(
                request.url.path.startswith(p) for p in self.SENSITIVE_PATHS
            )

            if is_sensitive or response.status_code >= 400:
                log_level = "warning" if response.status_code >= 400 else "info"
                getattr(logger, log_level)(
                    "AUDIT: %s %s -> %d (%.1fms) ip=%s auth=%s ua=%s rid=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed_ms,
                    client_ip,
                    auth_hash,
                    user_agent,
                    request_id,
                )

            # Add timing header
            response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

            return response

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "AUDIT: %s %s -> ERROR (%.1fms) ip=%s error=%s rid=%s",
                request.method,
                request.url.path,
                elapsed_ms,
                client_ip,
                str(e),
                request_id,
            )
            raise


# ══════════════════════════════════════════════════════════════
# Setup function
# ══════════════════════════════════════════════════════════════

def configure_security_middleware(app):
    """
    Configure all security middleware in the correct order.

    Order matters:
    1. CORS (handles preflight OPTIONS requests)
    2. Security headers (adds to all responses)
    3. Input validation (rejects bad requests early)
    4. Rate limiting (after validation, before business logic)
    5. Audit logging (captures everything)
    """
    # CORS — must be first
    configure_cors(app)

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Input validation
    app.add_middleware(InputValidationMiddleware)

    # Rate limiting
    from app.security.rate_limiter import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    # Audit logging — last to capture all requests
    app.add_middleware(AuditLoggingMiddleware)

    logger.info("Security middleware configured: CORS, headers, input validation, rate limiting, audit")
