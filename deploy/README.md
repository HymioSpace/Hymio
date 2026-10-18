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

Visit http://localhost:8000, change the initial administrator password and create a Hymio OIDC application. Enable authorization code with PKCE S256 and standard JWT claims (RS256/ES256). Set redirect URI to `http://localhost:8080/auth/callback`; copy its client ID and secret. Enable signup to allow new accounts; for Google sign-in follow the [provider setup](../backend/README.md#registration-and-google-sign-in).

```bash
cd backend
uv sync --frozen
uv run python scripts/setup.py --client-id YOUR_CASDOOR_CLIENT_ID
cd ..
```

Setup prompts for the secret and generates ignored private files. In `backend/hymio.toml`, set `host = "0.0.0.0"` so Docker Oath can reach the host Backend. Keep port 8080 and the default localhost service URLs for this launcher. Bind exposure must be appropriate for your local network.

## Start

From Hymio's root:

```bash
uv run --python 3.12 --no-project python deploy/start.py --client web
# Or:
uv run --python 3.12 --no-project python deploy/start.py --client desk
# Services without a client:
uv run --python 3.12 --no-project python deploy/start.py --client none
```

Default client is `web`. Open http://127.0.0.1:1420 and sign in. The client gets its public Backend address from `apps/client/client.toml`; users do not enter service URLs. Desktop opens its own window. First Desktop compilation can take several minutes.

| Service | Default endpoint |
| --- | --- |
| Web | http://127.0.0.1:1420 |
| Backend | http://localhost:8080 |
| Casdoor | http://localhost:8000 |
| Oath WS | ws://127.0.0.1:8765 |
| Oath Biz | http://127.0.0.1:8766 |

Options: `--backend-config PATH`, `--oath-config PATH`, `--auth-project NAME`. Relative paths are relative to your working directory. Backend credential paths resolve against its config directory. Model settings stay in Oath's config; login settings stay in Backend's config. No `.env` is required.

**Existing local setup:** if Casdoor was initialized under `hymio-auth-dev`, append `--auth-project hymio-auth-dev` on every launch. Using a different project creates a different data volume; it does not migrate accounts or OIDC applications.

## Stop and restart

Keep the launcher terminal open. Ctrl+C stops only the Backend and client it launched. Docker services remain available so accepted Agent work continues. Run the same command to start again; dependency installation uses lockfiles and existing configuration is preserved.

To stop Docker services explicitly:

```bash
oath stop
docker compose -f deploy/auth/compose.yaml down
# Existing dev project: add -p hymio-auth-dev before down
```

Do not add `--volumes` unless you intend to delete login data. The launcher rejects occupied Backend/client ports rather than stopping someone else's processes. Failures show the failing command or service output; Docker resources are left intact for inspection.

Production deployment, Nostalgia and connector services are not included. See [feature09](../spec/feature09-local-start.md) for boundaries and [Backend](../backend/README.md) for the authentication contract.
