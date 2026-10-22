# =============================================================================
# Intelligence Module Backend - Dockerfile for Data Science Workloads
# =============================================================================
# Multi-stage build optimized for ML/Data Science libraries

# Stage 1: Dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for data science libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Production image
FROM python:3.11-slim

# Link GHCR package to repo (enables GITHUB_TOKEN push in CI)
LABEL org.opencontainers.image.source=https://github.com/nkz-os/nekazari-module-intelligence

WORKDIR /app

# Install runtime dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder to a location accessible by appuser
COPY --from=builder /root/.local /app/.local
ENV PATH=/app/.local/bin:$PATH
ENV PYTHONPATH=/app/.local/lib/python3.11/site-packages

# Copy application code
COPY app/ ./app/

# Create non-root user and fix permissions
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
