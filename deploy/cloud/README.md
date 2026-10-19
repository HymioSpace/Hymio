# Single-host cloud deployment

Run Web, HTTPS and Hymio Backend with Compose on a Linux Docker host. Use E2B for cloud
desktops: Backend has no Docker socket and user computers do not share this server.
Oath and your OIDC provider remain independently managed services. This is a single-host
starting point, not a multi-replica deployment or a fully provisioned cloud installer.

## Prepare once

1. Install Docker Engine + Compose and Python 3.11+. Deploy Oath using its installer and
   configure the model, Vault credentials and Hymio remote auth. Deploy/configure Casdoor
   separately with a public HTTPS issuer and minimal signup fields.
2. Point three DNS names at this server: `app.example.com`, `api.example.com`,
   `agent.example.com`. Allow inbound 80/443. Caddy obtains and renews certificates.
3. Create `/opt/hymio/config/hymio.toml` from the Backend example. Store secrets under
   `/opt/hymio/config/private/`, readable by container UID 10001. Do not copy secrets into
   the repository or loosen them to world-readable. Bind mounts preserve host ownership.
4. Set these Backend values (replace example domains):

```toml
database = "/data/hymio.sqlite"
host = "0.0.0.0"
port = 8080
public_url = "https://api.example.com"
callback_url = "https://api.example.com/auth/callback"
origins = ["https://app.example.com", "http://tauri.localhost", "tauri://localhost"]
oath_ws = "wss://agent.example.com"
oath_biz = "http://host.docker.internal:8766"
computer_provider = "e2b"
e2b_key_file = "./private/e2b-api-key"
e2b_template = "hymio-desktop"
```

Keep issuer, client ID, client secret and service token settings from the Backend setup.
Register the HTTPS callback in Casdoor. Build the E2B template once using the
[computer guide](../computer/README.md#e2b-desktop).

5. Copy `cloud.example.toml` to `cloud.local.toml`. Set domains and config directory.
   `backend_internal_bind` must be the host's Docker bridge IPv4 address (usually
   `172.17.0.1`; check `ip addr show docker0`), not its public interface. Oath containers
   reach Hymio via `http://host.docker.internal:8080`. Use that base for remote auth and
   the Hymio extensions' private connection file; mount the Hymio tools/skills through
   Oath's CLI. Disable host Bash. Follow the local launcher's generated configuration
   structure; automated Oath cloud configuration is not included yet.
6. Oath WS/Biz published ports must be reachable from the Docker bridge. A port bound
   only to host `127.0.0.1` cannot be reached through host.docker.internal. Configure Oath
   bindings accordingly, keeping Biz and direct WS inaccessible from the public network
   (including Docker's firewall rules). Only Caddy's WSS entry is public; enable Oath
   remote auth before exposing it. Redis/Vault and other Oath internal ports stay private.

## Operate

From the Hymio repository:

```bash
python3 deploy/cloud/manage.py prepare
# Inspect generated Compose and Caddy configuration, then:
python3 deploy/cloud/manage.py start
python3 deploy/cloud/manage.py status
python3 deploy/cloud/manage.py logs
python3 deploy/cloud/manage.py stop
```

`start` builds locked application dependencies, starts containers and waits for Backend
health. Web's public API address is bundled at build time; change the cloud config and
run start again after changing domains. No .env is used. Stop preserves named volumes
and does not stop Oath, Casdoor or E2B computers. Upgrade Hymio by checking out a reviewed
commit and running start again; manage Oath upgrades separately with a fixed version.

## Persistence and checks

Backend database/screenshots and Caddy certificates use named volumes. Never use
`down --volumes` as a normal stop. Take consistent SQLite backups with SQLite's backup
API, not by copying a live database without its WAL. Back up Oath and Casdoor separately;
E2B pause is not a file backup. Test a restore before depending on the deployment.

Verify login/signup/logout, two-account isolation, WSS reconnect replay, a cloud command,
command lookup and pause/resume after deploying. `/health` is process liveness, not proof
that Oath, OIDC or E2B is healthy. Existing device E2E accepts a deployed Backend URL;
see its `--help`. Public DNS/TLS and actual cloud networking require deployment validation.

SQLite is intentionally single Backend instance. Horizontal scaling requires a shared
database and coordinated provider control; adding replicas now is unsupported. Automatic
backups, sandbox renewal, idle policy and a full Oath/Casdoor provisioning script remain
future work.
