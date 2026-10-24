# Hymio Kit Host

The Kit Host is an independent internal HTTP service. It owns Kit manifests, application HTML,
installations and business data. Applications may be static or call their own business operations
through the iOS host bridge. Hymio Backend only proxies authenticated product requests and exposes
installed operations through the unified `kit_call` tool.

The cloud stack publishes no Kit Host port. Backend and Kit Host share a private Docker network;
both use the internal service token. The default persistent database is `/data/kits.sqlite3`.

```sh
KIT_HOST_DATABASE=./data/kits.sqlite3 \
KIT_HOST_TOKEN_FILE=/path/to/internal-service-token \
KIT_HOST_MANIFESTS_DIR=../../kits \
uv run python -m kit_host
```

Endpoints are `POST /v1/catalog`, `/v1/install`, `/v1/uninstall`, `/v1/app`, `/v1/generate`,
`/v1/agent-context`, and `/v1/invoke`. There is no model-facing list/discovery step: Hymio injects
the current user's installed operation signatures into the context provider on each step.
