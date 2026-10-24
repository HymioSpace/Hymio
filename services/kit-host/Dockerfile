FROM node:24-bookworm-slim AS webdeps
WORKDIR /kit-web
COPY services/kit-host/web/package.json services/kit-host/web/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts

FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=webdeps /kit-web/node_modules /app/web/node_modules
WORKDIR /app
COPY services/kit-host/pyproject.toml services/kit-host/uv.lock ./
COPY services/kit-host/kit_host ./kit_host
COPY services/kit-host/web_build.mjs ./web_build.mjs
RUN chmod -R a+rX kit_host \
    && uv sync --frozen --no-dev \
    && useradd --uid 10001 --create-home kit
COPY kits ./kits
RUN chmod -R a+rX kit_host kits \
    && mkdir /data \
    && chown kit /data
ENV KIT_HOST_NODE=/usr/local/bin/node \
    KIT_HOST_WEB_MODULES=/app/web/node_modules
USER kit
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3)"]
ENTRYPOINT ["/app/.venv/bin/python", "-m", "kit_host"]
