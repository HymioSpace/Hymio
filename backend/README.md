# Hymio Backend

Product identity and application sessions, with standard OIDC login through Casdoor. The backend issues short-lived access tokens accepted by both Hymio and Oath, rotates refresh tokens, revokes logins and proxies authenticated Trace queries. SQLite stores stable user mappings and hashed application credentials.

## Run locally

Requires Python 3.11+ and uv. Start Casdoor using the pinned deployment:

```bash
docker compose -f deploy/auth/compose.yaml up -d
```

Open `http://localhost:8000`, finish Casdoor administration, create a dedicated `hymio` organization, then create an OIDC application bound to that organization. The reserved `built-in` organization cannot self-register. Configure authorization code flow, PKCE S256, standard JWT claims with RS256 or ES256, and redirect URI `http://localhost:8080/auth/callback`. Obtain its client ID and client secret. Change the initial Casdoor administrator password before exposing the service.

```bash
cd backend
uv sync --frozen
python scripts/setup.py --client-id YOUR_CASDOOR_CLIENT_ID
uv run python -m hymio_backend --config hymio.toml
```

Setup prompts for the Casdoor secret and generates a separate Oath verifier service credential. All private files are ignored. Configuration lives in `hymio.toml`; secrets are file references. `access_seconds` and `refresh_seconds` are configurable. For a production domain, change `issuer`, `public_url`, `callback_url`, `origins`, together. `oath_ws` and `oath_biz` are private upstream addresses; login responses advertise `public_url` with `/agent/ws` and `/oath-biz`.

## Connect Oath

Use the Oath authentication feature and start it with:

```bash
oath start --auth-mode remote \
  --auth-url http://host.docker.internal:8080/internal/auth/verify \
  --auth-token-file /absolute/path/to/Hymio/backend/private/oath-auth-token
```

The Backend must be reachable from Oath containers. On Linux, set Backend `host = "0.0.0.0"` and restrict ingress to intended clients/services; Oath adds the Docker host-gateway mapping. In a shared Docker network use Backend's service DNS instead. The credential file is mounted only into Oath Gateway and Biz. Restart retains the auth arguments.

Set the public Backend URL in `apps/client/client.toml` before building or running the client. Users sign in or create an account on Hymio's own initial screen; they never enter service endpoints or tokens. Web returns through its original popup; Desktop returns through a temporary loopback listener. Only the initiating client can exchange the callback confirmation code. Refresh reconnects WS; logout clears the local view and revokes server credentials. Credentials stay in the window session; persistent desktop login is not implemented.

## APIs

| Endpoint | Purpose |
| --- | --- |
| `GET /auth/options` | Public login presentation (`account` or configured `google`) |
| `POST /auth/account` | `{action: "login" or "signup", username, password}` → application session |
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

## Registration and Google sign-in

Use a dedicated Hymio organization, not `built-in`. Enable **Enable signup** on the Hymio application and leave **Disable self signup** off. Keep password sign-in enabled in account mode.

The Hymio form collects only username and password; Backend supplies the display name and password confirmation. In Casdoor's Signup items, keep Username, Display name, Password and Confirm password visible. For local development, hide Email and Phone, make both optional, and set their rule to **No verification**. Otherwise the default email verification blocks registration without a configured mail provider. For this local setup, hide the Agreement item and make it optional too. The form does not fabricate acceptance of terms. Enable only signup policies this two-field form can fulfill; add an explicit consent UI before requiring terms.

Passwords pass transiently through Backend to Casdoor and are never saved or logged by Hymio. Casdoor owns password storage and validation; Backend exchanges its authorization code through the same PKCE/OIDC verification as browser login. Use HTTPS on both links in production. Additional CAPTCHA/MFA/consent policies are not bypassed; this minimal account form does not yet render those challenges. Google uses the existing browser authorization flow.

For Google:

1. In [Google Cloud](https://console.cloud.google.com/), create an OAuth client of type **Web application**. Configure its consent screen and test users as required by your testing setup.
2. Set its authorized redirect URI to `http://localhost:8000/callback` for this local deployment. This is Casdoor's callback, **not** Backend's `/auth/callback`.
3. In Casdoor, add an OAuth provider of type **Google**, enter the Google client ID and secret, and attach it to the Hymio application. Allow this provider to sign up users as well as sign in. Request only identity/profile/email, not Gmail API scopes.
4. For a direct Google experience, make Google the only visible sign-in provider and disable password, code, passkey, LDAP and magic-link sign-in on this application. Keep signup enabled. Casdoor then redirects to the single provider.
5. Set `login_method = "google"` in private `backend/hymio.toml` and restart Backend. The client shows **使用 Google 继续**. This setting changes presentation; it does not create the Google provider. Leave it as `account` until provider setup is complete.

Google credentials belong only in Casdoor's private database. Backend retains its Casdoor client credentials; these are different OAuth clients. Gmail mailbox authorization is separate from account login.

References: [Casdoor Google setup](https://casdoor.ai/docs/provider/oauth/google/), [Google Web OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).
