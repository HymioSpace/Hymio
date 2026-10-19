FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/hymio_backend ./hymio_backend
RUN uv sync --frozen --extra e2b --no-dev && useradd --uid 10001 --create-home hymio && mkdir /data && chown hymio /data
USER hymio
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]
ENTRYPOINT ["/app/.venv/bin/python", "-m", "hymio_backend", "--config", "/config/hymio.toml"]
