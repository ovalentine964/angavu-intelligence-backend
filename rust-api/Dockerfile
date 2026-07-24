# ═══════════════════════════════════════════════════════════════
# Angavu Intelligence — Rust API Dockerfile
# Multi-stage build for minimal production image (~15MB)
# ═══════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────
FROM rust:1.82-bookworm AS builder

WORKDIR /build

# Create a dummy project to cache dependencies
RUN cargo init --name angavu-api .

COPY Cargo.toml Cargo.lock ./
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/build/target \
    cargo build --release 2>/dev/null || true

# Copy source and build the real binary
COPY src/ src/
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/build/target \
    cargo build --release && \
    cp target/release/angavu-api /angavu-api

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r angavu && useradd -r -g angavu -d /app -s /sbin/nologin angavu

WORKDIR /app

# Copy binary from builder
COPY --from=builder /angavu-api /app/angavu-api

# Create directories
RUN mkdir -p /app/logs && chown -R angavu:angavu /app

USER angavu

# Environment defaults (overridable at runtime)
ENV HOST=0.0.0.0 \
    PORT=8080 \
    RUST_LOG=info \
    ENVIRONMENT=production

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/app/angavu-api", "--health"] 2>/dev/null || \
    curl -sf http://localhost:8080/api/v1/health || exit 1

# Use tini as PID 1 for proper signal handling
ENTRYPOINT ["tini", "--"]
CMD ["/app/angavu-api"]
