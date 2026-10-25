# Hymio Kit Host

The Kit Host is an independent internal service. It owns application source projects, immutable
published revisions, built Web bundles, installations, coding conversation metadata and business
data. Generated applications use React plus bounded Python handlers; trusted first-party manifests
may still use bundled Python handlers.

The cloud stack publishes no Kit Host port. Backend and Kit Host share a private Docker network;
both use the internal service token. The default persistent database is `/data/kits.sqlite3`.

```sh
KIT_HOST_DATABASE=./data/kits.sqlite3 \
KIT_HOST_TOKEN_FILE=/path/to/internal-service-token \
KIT_HOST_MANIFESTS_DIR=../../kits \
uv run python -m kit_host
```

Published applications use `/v1/catalog`, `/v1/install`, `/v1/uninstall`, `/v1/app`,
`/v1/agent-context` and `/v1/invoke`. Development uses `/v1/project/create`,
`/v1/project/bind-agent`, `/v1/dev`, `/v1/dev/context`, `/v1/editor` and `/v1/editor/message`.

The service compiles React with a pinned local esbuild dependency. Python API handlers run in
short-lived resource-bounded subprocesses and commit validated mutations with an idempotency
receipt. It does not expose a public port or execute application code in the Backend.
