# Hymio Backend

Product identity and application sessions, with standard OIDC login through Casdoor. The backend issues short-lived access tokens accepted by both Hymio and Oath, rotates refresh tokens, revokes logins and proxies authenticated Trace queries. SQLite stores stable user mappings and hashed application credentials.

## Run locally

Requires Python 3.11+ and uv. Start Casdoor using the pinned deployment:

```bash
docker compose -f deploy/auth/compose.yaml up -d
```

Open `http://localhost:8000`, finish Casdoor administration and create an OIDC application for Hymio. Configure authorization code flow, PKCE S256, standard JWT claims with RS256 or ES256, and redirect URI `http://localhost:8080/auth/callback`. Obtain its client ID and client secret. Change the initial Casdoor administrator password before exposing the service.

```bash
cd backend
uv sync --frozen
python scripts/setup.py --client-id YOUR_CASDOOR_CLIENT_ID
uv run python -m hymio_backend --config hymio.toml
```

Setup prompts for the Casdoor secret and generates a separate Oath verifier service credential. All private files are ignored. Configuration lives in `hymio.toml`; secrets are file references. `access_seconds` and `refresh_seconds` are configurable. For a production domain, change `issuer`, `public_url`, `callback_url`, `origins`, and public `oath_ws` together. `oath_biz` is the backend's private upstream address.

## Connect Oath

Use the Oath authentication feature and start it with:

```bash
oath start --auth-mode remote \
  --auth-url http://host.docker.internal:8080/internal/auth/verify \
  --auth-token-file /absolute/path/to/Hymio/backend/private/oath-auth-token
```

The Backend must be reachable from Oath containers. On Linux, set Backend `host = "0.0.0.0"` and restrict ingress to intended clients/services; Oath adds the Docker host-gateway mapping. In a shared Docker network use Backend's service DNS instead. The credential file is mounted only into Oath Gateway and Biz. Restart retains the auth arguments.

In the Hymio client's connection settings, enter `http://localhost:8080` as the Hymio service and choose **在浏览器中登录**. Web returns through its original popup; Desktop returns through a temporary loopback listener. Only the initiating client can exchange the callback confirmation code. Refresh reconnects WS; logout clears the local view and revokes server credentials. Credentials stay in the window session; persistent desktop login is not implemented.

## APIs

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/start` | `{return_uri}` → provider authorization URL + private exchange handle |
| `GET /auth/callback` | Provider redirect; delivers a one-time confirmation code |
| `POST /auth/exchange` | `{flow_id, login_code}` → application tokens, user ID and endpoints |
| `POST /auth/refresh` | `{refresh_token}` → rotated application credentials |
| `POST /auth/logout` | Bearer access token → revoke this login |
| `GET /auth/me` | Bearer access token → verified identity |
| `POST /internal/auth/verify` | Service Bearer credential + `{credential}` → user ID and expiry |
| `GET /agent/traces`, `/agent/traces/{id}` | Query Oath on behalf of authenticated user |
| `GET /oath-biz/heartbeat`, `/list_traces`, `/query_trace` | Same-origin client Biz proxy under `/oath-biz` |

Revocation is visible to Oath on the next verification (within 30 seconds for idle WS). Revoking access does not cancel accepted Agent work. Logout ends the Hymio login; Casdoor's broader SSO session is independent. No connector authorization, account administration or multi-instance database support is included.

The Dockerfile builds the same backend. Mount private configuration and credential files read-only, mount a writable database directory, and set `host = "0.0.0.0"` in container configuration. Use HTTPS/WSS for deployed clients.
