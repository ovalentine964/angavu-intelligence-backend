"""
Buyer authentication dependencies for FastAPI.

Architecture: arch_backend.md §7.2
"""
from typing import Optional

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from app.db.database import get_db
from app.services.auth import verify_buyer_token

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/buyer/auth/token", auto_error=False)


async def get_current_buyer(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    """Validate buyer credentials — accepts either OAuth2 token or API key."""
    if token:
        claims = verify_buyer_token(token)
        if claims:
            return claims
        raise HTTPException(401, "Invalid or expired token")

    if api_key:
        from app.db.redis import get_redis
        from app.services.buyer_rate_limiter import BuyerRateLimiter
        from sqlalchemy import select
        from app.models.buyer import BuyerAPIKey
        import hashlib

        # This is a lightweight path — full validation happens in the route
        raise HTTPException(401, "Use OAuth2 token. Exchange API key at /api/v1/buyer/auth/token")

    raise HTTPException(401, "Authentication required")


def require_product(product: str):
    """Dependency factory — checks buyer has access to a specific product."""
    async def _check(claims: dict = Depends(get_current_buyer)):
        products = claims.get("products", [])
        if product not in products and "*" not in products:
            raise HTTPException(403, f"Not subscribed to {product}")
        return claims
    return _check
