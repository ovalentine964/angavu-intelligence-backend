# ── Build stage ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl build-essential pkg-config && \
    rm -rf /var/lib/apt/lists/*

# Install Rust for PyO3 extension
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Build Rust extension
COPY rust/ /build/rust/
COPY pyproject.toml /build/
COPY app/ /build/app/
RUN cd /build && pip install --no-cache-dir --prefix=/install maturin && \
    maturin build --release --out /build/wheels 2>/dev/null || true

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r angavu && useradd -r -g angavu -d /app -s /sbin/nologin angavu

COPY --from=builder /install /usr/local
WORKDIR /app
COPY app/ /app/app/
COPY config/ /app/config/
COPY alembic.ini /app/
COPY database/ /app/database/
COPY scripts/ /app/scripts/

RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

USER angavu
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
