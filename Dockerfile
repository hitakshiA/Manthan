# Manthan — top-level FastAPI application image (Layer 1 runtime).
#
# This is the image that serves the /datasets, /tools, /clarification,
# /metrics, and websocket endpoints. It runs uvicorn with the
# stateful Python sandbox running as a host-subprocess inside the
# container (same Python interpreter — no nested Docker).
#
# Build:
#   docker build -t manthan:latest .
# Run:
#   docker run -p 8000:8000 \
#     -e OPENROUTER_API_KEY=sk-or-... \
#     -v $(pwd)/data:/app/data \
#     manthan:latest

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIRECTORY=/app/data

WORKDIR /app

# System packages — build-essential for any wheels that need compilation,
# curl for container health checks, and libpq for the DuckDB Postgres
# scanner (only loaded on demand, but the shared lib must be present).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src

# Install runtime deps (skip dev + test extras).
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
