# Configuration map

Hymio separates operator input from generated runtime files and from Oath's independent
configuration. Use `hymio doctor` to see which mode is active.

## Local unified installation

```text
~/.hymio/config.toml                      operator input; the only file to copy for a new install
~/.hymio/preferences.json                 CLI selection; generated
~/.hymio/local-<id>/backend/hymio.toml    generated Backend config
~/.hymio/local-<id>/oath/oath.toml        generated Oath config
~/.hymio/local-<id>/backend/private/      generated credentials
```

Edit only `~/.hymio/config.toml`. Do not edit generated service files: `hymio start` rewrites
them from the operator input. Do not copy generated credentials as a data migration.

## Existing legacy local installation

```text
backend/hymio.toml                   Backend input
~/.oath/oath.toml                    Oath input
deploy/local.toml                    LAN/network input
backend/hymio-media.local.toml       generated Backend overlay; do not edit
```

Legacy mode has independent inputs because it predates the portable launcher. Moving an existing
installation with accounts, history and identity data to unified mode requires a planned data
backup and restore. Creating a new `~/.hymio/config.toml` alone produces a fresh installation.

## Cloud installation

```text
/opt/hymio/config/hymio.toml         Hymio product/service input
/opt/hymio/config/oath.toml          Oath runtime input, owned by the Oath process
/opt/hymio/config/cloud.toml         Hymio/Caddy deployment input
/opt/hymio/config/private/           host-only credentials
```

Oath is separately deployed and keeps its own configuration contract. It cannot be replaced by
Hymio's product TOML without coupling the two projects. Treat it as the single external-runtime
configuration, not a second copy of Hymio settings.

The useful rule is: one editable Hymio input, one editable Oath input for the independent agent
runtime, one deployment input, and generated files are never hand-edited. Keys remain in private
files so they do not appear in launch logs or shell history.
