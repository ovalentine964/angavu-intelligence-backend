"""
Angavu Intelligence Backend — Main Application

FastAPI application serving as the collective intelligence platform
for Msaidizi super agents.

Architecture: arch_backend.md
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.v1 import sync, intelligence, buyer, auth, health
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Startup
    print("🚀 Angavu Intelligence Backend starting...")
    print(f"   Version: {settings.APP_VERSION}")
    print(f"   Environment: {settings.ENVIRONMENT}")
    yield
    # Shutdown
    print("🛑 Angavu Intelligence Backend shutting down...")


app = FastAPI(
    title="Angavu Intelligence API",
    description="Africa's operating system for the informal economy",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(sync.router, prefix="/api/v1/sync", tags=["Sync"])
app.include_router(intelligence.router, prefix="/api/v1/intelligence", tags=["Intelligence"])
app.include_router(buyer.router, prefix="/api/v1/buyer", tags=["Buyer Dashboard"])


@app.get("/")
async def root():
    return {
        "name": "Angavu Intelligence",
        "version": settings.APP_VERSION,
        "description": "Africa's operating system for the informal economy",
        "status": "running"
    }
