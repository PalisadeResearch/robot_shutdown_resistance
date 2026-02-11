# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY log_viewer.py s3_storage.py index.html ./

EXPOSE 8080
CMD ["uv", "run", "robot-shutdown-avoidance-log-viewer", "--host", "0.0.0.0", "--port", "8080"]
