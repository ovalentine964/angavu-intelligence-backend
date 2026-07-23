"""
Input validation middleware — SQL injection, XSS, path traversal.

Architecture: arch_backend.md §1.2
"""
import re
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger(__name__)

# Patterns for malicious input
SQL_INJECTION = re.compile(
    r"(\b(union|select|insert|update|delete|drop|alter|exec|execute)\b\s)",
    re.IGNORECASE,
)
XSS_PATTERN = re.compile(r"(<script|javascript:|on\w+\s*=)", re.IGNORECASE)
PATH_TRAVERSAL = re.compile(r"(\.\./|\.\.\\)")


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Validate request inputs for common attack patterns."""

    async def dispatch(self, request: Request, call_next):
        # Check query params
        for key, value in request.query_params.items():
            if self._is_malicious(value):
                logger.warning("malicious_input_blocked", param=key, ip=request.client.host if request.client else "unknown")
                raise HTTPException(400, "Invalid input detected")

        # Check URL path
        if PATH_TRAVERSAL.search(str(request.url.path)):
            logger.warning("path_traversal_blocked", path=str(request.url.path))
            raise HTTPException(400, "Invalid path")

        response = await call_next(request)
        return response

    def _is_malicious(self, value: str) -> bool:
        if len(value) > 10000:
            return True
        if SQL_INJECTION.search(value):
            return True
        if XSS_PATTERN.search(value):
            return True
        return False
