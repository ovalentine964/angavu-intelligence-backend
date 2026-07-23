"""
Health check + Prometheus metrics endpoint.

Architecture: arch_backend.md §3.7
"""
from fastapi import APIRouter
from app.infrastructure.metrics import get_metrics_response

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {
        "status": "healthy",
        "service": "angavu-intelligence-backend",
        "version": "2.0.0",
    }


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_response()
