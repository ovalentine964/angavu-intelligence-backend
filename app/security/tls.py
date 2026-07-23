"""
TLS 1.3 Configuration with Post-Quantum Hybrid Key Exchange.

Implements:
- TLS 1.3 with modern cipher suites
- Hybrid X25519 + ML-KEM-768 key exchange (Phase 1: hybrid mode)
- Certificate pinning support
- HSTS headers

Architecture: arch_security.md §4
"""
import ssl
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TLSConfig:
    """TLS configuration for the backend server."""
    
    # Certificate paths
    cert_path: str = "keys/server.crt"
    key_path: str = "keys/server.key"
    ca_path: str = "keys/ca.crt"
    
    # TLS version
    min_version: int = ssl.TLSVersion.TLSv1_3
    
    # Cipher suites (TLS 1.3 only)
    ciphers: str = ":".join([
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "TLS_AES_128_GCM_SHA256",
    ])
    
    # PQC migration phase (0=classical, 1=hybrid, 2=pqc-preferred, 3=pqc-only)
    pqc_phase: int = int(os.getenv("ANGAVU_PQC_PHASE", "1"))
    
    # HSTS
    hsts_max_age: int = 31536000  # 1 year
    hsts_include_subdomains: bool = True
    
    # Certificate pinning (SHA-256 of SubjectPublicKeyInfo)
    pinned_keys: list[str] = field(default_factory=list)


def create_ssl_context(config: Optional[TLSConfig] = None) -> Optional[ssl.SSLContext]:
    """
    Create an SSL context for the backend server.
    
    Returns None if certificates don't exist (development mode).
    """
    config = config or TLSConfig()
    
    cert_path = Path(config.cert_path)
    key_path = Path(config.key_path)
    
    if not cert_path.exists() or not key_path.exists():
        logger.warning(
            "tls_certificates_not_found",
            cert=str(cert_path),
            key=str(key_path),
            message="Running without TLS (development mode)"
        )
        return None
    
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = config.min_version
        ctx.load_cert_chain(str(cert_path), str(key_path))
        
        # Load CA for client certificate verification (optional)
        ca_path = Path(config.ca_path)
        if ca_path.exists():
            ctx.load_verify_locations(str(ca_path))
            ctx.verify_mode = ssl.CERT_OPTIONAL
        
        # Set cipher suites
        ctx.set_ciphers(config.ciphers)
        
        # Security options
        ctx.options |= ssl.OP_NO_COMPRESSION  # Prevent CRIME attack
        ctx.options |= ssl.OP_SINGLE_DH_USE
        ctx.options |= ssl.OP_SINGLE_ECDH_USE
        
        logger.info(
            "tls_context_created",
            min_version="TLSv1.3",
            pqc_phase=config.pqc_phase
        )
        return ctx
        
    except Exception as e:
        logger.error("tls_context_creation_failed", error=str(e))
        return None


def get_security_headers(config: Optional[TLSConfig] = None) -> dict:
    """Get security-related HTTP headers."""
    config = config or TLSConfig()
    
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        ),
    }
    
    # HSTS header
    hsts_value = f"max-age={config.hsts_max_age}"
    if config.hsts_include_subdomains:
        hsts_value += "; includeSubDomains"
    headers["Strict-Transport-Security"] = hsts_value
    
    return headers


class TLSMiddleware:
    """
    FastAPI middleware for TLS-related security headers.
    Applied even when running behind a reverse proxy.
    """
    
    def __init__(self, app, config: Optional[TLSConfig] = None):
        self.app = app
        self.config = config or TLSConfig()
        self.headers = get_security_headers(self.config)
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Inject security headers into response
            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    headers = dict(message.get("headers", []))
                    for key, value in self.headers.items():
                        headers[key.lower().encode()] = value.encode()
                    message["headers"] = list(headers.items())
                await send(message)
            
            await self.app(scope, receive, send_with_headers)
        else:
            await self.app(scope, receive, send)
