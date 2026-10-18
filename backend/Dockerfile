FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
COPY hymio_backend ./hymio_backend
RUN uv sync --frozen --no-dev
ENTRYPOINT ["/opt/venv/bin/python", "-m", "hymio_backend"]
CMD ["--config", "/config/hymio.toml"]
