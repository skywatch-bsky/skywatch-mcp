FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENV SKYWATCH_TRANSPORT=http \
    SKYWATCH_HOST=0.0.0.0 \
    SKYWATCH_PORT=8000
CMD ["/app/.venv/bin/skywatch-mcp"]
