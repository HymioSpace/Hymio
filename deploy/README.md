# Local deployment

Hymio owns service composition. `start.py` starts Casdoor, Hymio Backend and Oath, then a Web or Tauri development client. Clients themselves never deploy Oath. This is a macOS/Linux development workflow, not a production installer.

## First run

Install Docker (start its daemon), uv, Node.js 22.12+ and pnpm 11. Desktop also needs Rust and the Tauri platform dependencies (Xcode command line tools on macOS).

Clone Hymio and Oath beside one another:

```bash
git clone https://github.com/HymioSpace/Hymio.git
git clone https://github.com/HymioSpace/Oath.git
cd Oath
bash scripts/oath-install
```

Configure the model and its credential in `~/.oath/oath.toml`, following Oath's README. The installer must include the remote authentication feature. If `oath` is not on PATH, run `uv tool update-shell` and reopen the terminal.

Set up the login provider once, from Hymio:

```bash
cd ../Hymio
docker compose -f deploy/auth/compose.yaml up -d
```

Visit http://localhost:8000, change the initial administrator password, create a dedicated `hymio` organization (not `built-in`), and create a Hymio OIDC application bound to it. Enable authorization code with PKCE S256 and standard JWT claims (RS256/ES256). Set redirect URI to `http://localhost:8080/auth/callback`; copy its client ID and secret. Enable signup and configure the minimal local signup fields described in the [Backend guide](../backend/README.md#registration-and-google-sign-in); for Google sign-in follow the [provider setup](../backend/README.md#registration-and-google-sign-in).

```bash
cd backend
uv sync --frozen
uv run python scripts/setup.py --client-id YOUR_CASDOOR_CLIENT_ID
cd ..
```

Setup prompts for the secret and generates ignored private files. In `backend/hymio.toml`, set `host = "0.0.0.0"` so Docker Oath can reach the host Backend. Keep port 8080 and the default localhost service URLs for this launcher. Bind exposure must be appropriate for your local network.

## Install and start

From Hymio's root (after the first-run login/model/E2B configuration above):

```bash
bash scripts/hymio-install
hymio start                      # Web, background
hymio status
hymio logs -f
# Other clients:
hymio restart --client desk
hymio restart --client none
```

The installer uses uv to expose the command and records the source location in
`~/.hymio/installation.json`. Keep the checkout in place; this is a source-based local
launcher, not a standalone binary. No Node/TypeScript installation is added at the repo root.
Logs, lifecycle lock and state live under `~/.hymio/`, never in the repository.
To move the checkout, stop Hymio and rerun the installer from its new location.
If `hymio` is not on PATH, run `uv tool update-shell` and reopen the terminal.

Repeated start returns the existing managed instance; changed client/config options require
restart. An already-running unmanaged Hymio is reported with its URL, without taking ownership
or killing processes. Other occupied ports remain errors. `status` reports Backend/client
health separately from whether CLI owns their launcher; it does not verify every Oath service.

For foreground development, the original entry remains available:

```bash
uv run --python 3.12 --no-project python deploy/start.py --client web
```

Default client is `web`. Open http://127.0.0.1:1420 and sign in. The client gets its public Backend address from `apps/client/client.toml`; users do not enter service URLs. Desktop opens its own window. First Desktop compilation can take several minutes.

| Service | Default endpoint |
| --- | --- |
| Web | http://127.0.0.1:1420 |
| Backend | http://localhost:8080 |
| Casdoor | http://localhost:8000 |
| Oath WS | ws://127.0.0.1:8765 |
| Oath Biz | http://127.0.0.1:8766 |

CLI options: `--client web|desk|none`, `--home PATH`, `--timeout SECONDS`, `--backend-config PATH`, `--oath-config PATH`, `--auth-project NAME`. Relative paths are relative to your working directory. Backend credential paths resolve against its config directory. Model settings stay in Oath's config; login settings stay in Backend's config. No `.env` is required.

**Existing local setup:** the installer detects a single existing Casdoor Compose project on port 8000. You can also select `hymio start --auth-project hymio-auth-dev` once; subsequent CLI starts preserve the selection. Using a different project creates a different data volume; it does not migrate accounts or OIDC applications.

## Stop and restart

```bash
hymio stop
hymio restart
```

Stop/restart only manages the launcher and Backend/client processes it owns. Oath, Casdoor
and E2B environments remain running so accepted Agent work can continue. Closing the terminal
does not stop a CLI-managed stack. Foreground `deploy/start.py` still uses Ctrl+C.
A stale PID or unrelated process is never stopped; failed startup details are in `hymio logs`.
The CLI preserves settings across restarts; it does not replace model/login/E2B credentials.

To stop Docker services explicitly:

```bash
oath stop
docker compose -f deploy/auth/compose.yaml down
# Existing dev project: add -p hymio-auth-dev before down
```

Do not add `--volumes` unless you intend to delete login data. The launcher rejects occupied Backend/client ports rather than stopping someone else's processes. Failures show the failing command or service output; Docker resources are left intact for inspection.

Production deployment, Nostalgia and connector services are not included. See [feature09](../spec/feature09-local-start.md) for boundaries and [Backend](../backend/README.md) for the authentication contract.

## Device environments

The launcher mounts Hymio device tools/skills; cloud desktops are provisioned through E2B.
It writes a private `hymio-runtime.local.toml` beside the Oath config, disabling host Bash;
your source Oath configuration is unchanged. See [computer environments](computer/README.md)
for E2B configuration, device management and the end-to-end check.

## Cloud deployment

For Linux servers, use the separate [cloud deployment entry](cloud/README.md): containerized
Backend, static Web and Caddy HTTPS, with E2B computers and independently managed Oath/OIDC.
The development launcher above is not the cloud deployment command.
