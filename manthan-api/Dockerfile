# Multi-stage build:
#   1. coral-builder - Rust 1.95, compiles the Coral binary from sibling source
#   2. base          - Python 3.12 + uv + FastAPI app + 3 workers
#
# Build context: the manthanv2/ root (so coral/, agent/, manthan-api/ are
# all siblings). Configured in fly.toml: `build.dockerfile`.
#
# Fly.io: process groups in fly.toml run web / investigate / actor /
# prettifier as separate machines, each launched from this image.

# ──────────────────────────────────────────────────────────────────────
# Stage 1 - compile Coral
# ──────────────────────────────────────────────────────────────────────

FROM rust:1.95-slim AS coral-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        pkg-config libssl-dev ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build/coral
COPY coral /build/coral

# Compile only the coral binary (workspace has multiple crates).
# Release profile; result lands at /build/coral/target/release/coral.
RUN cargo build --release --bin coral

# ──────────────────────────────────────────────────────────────────────
# Stage 2 - Python runtime + workers + Coral binary
# ──────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

# uv + minimal runtime libs that Coral and the Python deps link against
# (libssl for HTTPS, ca-certs for cert chain).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libssl3 \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cp /root/.local/bin/uv /usr/local/bin/uv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the agent sibling first because manthan-api depends on it.
COPY agent /app/agent
COPY manthan-api /app/manthan-api

# Bring the Coral binary from the builder stage. The agent's coral_session
# spawns this as a subprocess on each investigation.
COPY --from=coral-builder /build/coral/target/release/coral /usr/local/bin/coral

WORKDIR /app/manthan-api

# Rewrite the editable path dep so it points to the in-image agent.
RUN sed -i 's|path = "../agent"|path = "/app/agent"|' pyproject.toml

# Sync deps system-wide.
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Point the agent's coral_session at the in-image binary. Can be
# overridden per-deploy via fly secrets.
ENV CORAL_BINARY=/usr/local/bin/coral \
    PORT=8000

EXPOSE 8000

# Default command: the API. fly.toml overrides for investigate / actor /
# prettifier process groups.
CMD ["uv", "run", "uvicorn", "manthan_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
