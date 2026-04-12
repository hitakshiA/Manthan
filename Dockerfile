# Manthan — Full stack: FastAPI backend + React frontend
#
# Multi-stage build:
#   Stage 1: Build the frontend (Node)
#   Stage 2: Serve everything from Python (FastAPI + static files)

# ── Stage 1: Build frontend ──────────────────────────────────
FROM node:22-slim AS frontend

WORKDIR /frontend
COPY manthan-ui/package.json manthan-ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY manthan-ui/ ./
RUN npm run build

# ── Stage 2: Python runtime ─────────────────────────────────
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIRECTORY=/app/data

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir -e .

# Copy built frontend from stage 1
COPY --from=frontend /frontend/dist /app/manthan-ui/dist

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
