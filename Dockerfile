# Angavu Intelligence Backend — Docker Build
# Architecture: arch_backend.md
# Target: Oracle Cloud Free Tier (ARM64)
FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2, cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY database/ ./database/

# Create keys directory
RUN mkdir -p keys

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with gunicorn (4 workers for 2 OCPUs)
CMD ["gunicorn", "app.main:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--timeout", "120", "--keep-alive", "5"]
