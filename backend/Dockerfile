# ──────────────────────────────────────────────────────────────────
#  Backend — Python 3.12 + FastAPI + uv
# ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv (fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install system deps needed by some wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file first for layer caching
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

# ── Runtime stage ─────────────────────────────────────────────────
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv ./.venv

# Copy application code
COPY backend/ ./backend/
COPY pyproject.toml .
COPY skills/ ./skills/

# Ensure the .venv/bin is in PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
