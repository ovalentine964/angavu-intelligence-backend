# =============================================================================
# Angavu Intelligence Backend — Multi-stage Dockerfile
# Rust primary server + Python LLM inference sidecar
# =============================================================================

# ── Stage 1: Build Rust binary ────────────────────────────────────────────────
FROM rust:1.82-bookworm AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config libssl-dev libpq-dev protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY Cargo.toml Cargo.lock* ./
# Cache dependency builds
RUN mkdir src && echo 'fn main(){}' > src/main.rs && \
    echo 'fn main(){}' > src/migrate.rs && \
    cargo build --release 2>/dev/null || true && \
    rm -rf src

COPY src/ ./src/
# Touch source files so cargo detects changes and rebuilds
RUN touch src/main.rs src/migrate.rs && \
    cargo build --release && \
    strip target/release/angavu-server && \
    strip target/release/angavu-migrate

# ── Stage 2: Python LLM inference environment ─────────────────────────────────
FROM python:3.12-slim AS python-llm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app/python
COPY python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY python/ ./


# ── Stage 3: Minimal runtime image ────────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libssl3 ca-certificates curl python3 python3-pip dumb-init && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r angavu && useradd -r -g angavu -d /app -s /sbin/nologin angavu

# Install Python LLM dependencies in runtime
COPY python/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

WORKDIR /app

# Copy Rust binaries
COPY --from=rust-builder /build/target/release/angavu-server /app/angavu-server
COPY --from=rust-builder /build/target/release/angavu-migrate /app/angavu-migrate

# Copy Python LLM inference code
COPY python/ /app/python/

# Copy configuration and scripts
COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

# Create directories for runtime data
RUN mkdir -p /app/config /app/data /app/logs && \
    chown -R angavu:angavu /app

USER angavu

# Environment defaults (overridable at runtime)
ENV RUST_LOG=info \
    RUST_BACKTRACE=1 \
    ANGAVU_HOST=0.0.0.0 \
    ANGAVU_PORT=8000 \
    PYTHONPATH=/app/python \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Use dumb-init for proper signal handling
ENTRYPOINT ["dumb-init", "--"]
CMD ["/app/angavu-server", "--host", "0.0.0.0", "--port", "8000"]
