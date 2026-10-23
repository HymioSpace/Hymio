# Single-host cloud deployment

One HTTPS entry serves Web, the independent `/admin/` operator console, login, chat, business
APIs and authenticated media. Caddy, Backend and optionally Casdoor run in Compose; Oath remains
independently managed with its CLI. Cloud computers use the configured provider and never run as
containers on this host. This supports one Backend instance, not horizontal scaling or a complete
infrastructure provisioner.

## 1. Prepare the host and private files

Install Docker Engine, Compose, Python 3.11+ and Oath. Check out reviewed versions of
Hymio and Oath. Point `hymio.example.com` at the host and allow inbound TCP 80/443.
Keep direct Oath, identity, queue and Vault ports private.

Keep configuration outside the checkout:

```text
/opt/hymio/config/
  cloud.toml
  hymio.toml
  oath.toml
  private/
    backend/
      casdoor-client-secret
      internal-service-token
      e2b-api-key
      daytona-api-key
      invitation-codes
    oath/
      vault-role-id
      vault-secret-id
```

Use mode 600 for secret/config files. Backend and Oath application containers use UID
10001: bind-mounted inputs must be readable by that UID, and parent directories mounted
into Backend must be traversable. Keep model import credentials and identity administrator
credentials separately readable by the host administrator only. Do not put them in an image,
checkout, client config, `.env` or shell history.

The cloud Oath worker and tools run as UID 10001. Skill directories must be traversable and
`SKILL.md` files readable by that UID. A root-only file makes container health pass while every
Agent step fails during context assembly. Keep private connection files mode 600 and owned by
the runtime UID.

Copy `backend/hymio.example.toml` to `/opt/hymio/config/hymio.toml`, retaining its identity
and secret-file settings. For the shared Docker-network setup, use:

```toml
database = "/data/hymio.sqlite"
host = "0.0.0.0"
port = 8080
issuer = "http://identity:8000"
client_id = "REPLACE_WITH_CASDOOR_CLIENT_ID"
client_secret_file = "./private/backend/casdoor-client-secret"
service_token_file = "./private/backend/internal-service-token"
admin_user_ids = ["PRODUCT_USER_ID"]
oath_admin_token_file = "./private/backend/oath-admin-token"
public_url = "https://hymio.example.com"
callback_url = "https://hymio.example.com/auth/callback"
origins = ["https://hymio.example.com", "http://tauri.localhost", "tauri://localhost"]
oath_ws = "ws://gateway:8765"
oath_biz = "http://biz:8766"
prometheus_url = "http://prometheus:9090"
login_method = "account"
signup_enabled = true
invitation_codes_file = "./private/backend/invitation-codes"
computer_provider = "e2b"
e2b_key_file = "./private/backend/e2b-api-key"
e2b_template = "hymio-desktop"
```

`oath_admin_token_file` must contain exactly Oath's private
`services.internal_token`. It is used only by Backend's administrator trace reader and
background event indexer, never by clients. Keep it mode 600 and owned by the Backend
runtime UID.

Build the E2B template using the [computer guide](../computer/README.md#e2b-desktop).
The launcher supplies the private Prometheus URL when Backend config omits `prometheus_url`.
An explicit Backend value takes precedence. On the shared Docker network, use the service name;
`127.0.0.1` inside Backend refers to Backend itself. `/telemetry/*` routes to Backend.
An unauthenticated telemetry POST must return JSON 401, never the static Web app's HTML.
`prepare` also generates `hymio-metrics-targets.json`. Set Oath Compose's
`OATH_HYMIO_METRICS_TARGETS` to that file's absolute path before recreating Prometheus.
This makes Prometheus scrape `backend:8080` on the private shared network. Keep that environment
setting in the host's private Oath Compose environment for subsequent deployments.
The default Oath target is the host's port 8080, appropriate for a locally running Backend.
Set `signup_enabled = false` to close registration entirely. If registration is enabled
without `invitation_codes_file`, registration remains open for backward compatibility.

### File-cache read thrashing on Alibaba Cloud Linux

Some hosts expose file-backed transparent huge page controls at
`/sys/kernel/mm/transparent_hugepage/hugepages-*/file_enabled`. If disk reads stay high,
processes block on file faults, and file cache repeatedly disappears despite available
memory, see [host I/O diagnostics](../TROUBLESHOOTING.md#host-io-and-file-cache-thrashing).
The opt-in workaround below disables file-backed THP, sets anonymous THP to `madvise`, and
disables THP defragmentation. It does not change MGLRU, swap, container limits or stored data.
It is not a default for every Linux host. Anonymous THP is restricted because its background
compaction can also sustain cache reclaim on a fragmented small host.

```sh
sudo install -d /usr/local/lib/hymio
sudo install -m 644 deploy/cloud/file_cache.py /usr/local/lib/hymio/file_cache.py
sudo install -m 644 deploy/cloud/hymio-file-cache.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hymio-file-cache.service
python3 /usr/local/lib/hymio/file_cache.py status
```

The first application saves original policies in `/var/lib/hymio/file-cache-original.json`.
Repeated starts preserve that backup. To roll back, first disable the boot service:

```sh
sudo systemctl disable --now hymio-file-cache.service
sudo python3 /usr/local/lib/hymio/file_cache.py restore
```

No reboot or container restart is required. Compare disk read rate, `vmstat` I/O wait and
authenticated application requests before deciding whether to retain the workaround.

## 2. Start Oath and generate the cloud stack

Configure Oath's model provider and Vault using its installer/docs. Import the model key
through the host bootstrap; do not propagate it into Agent/Bash environments. Disable
host Bash for cloud users. The Backend internal service token must match the token Oath
uses for remote authentication and Hymio's device extensions.

From the Hymio checkout, start Oath first to create its Docker network:

```sh
oath start --config /opt/hymio/config/oath.toml \
  --system-prompt "$PWD/extensions/prompts/hymio.md" \
  --skill "$PWD/extensions/skills" --tool "$PWD/extensions/tools" \
  --auth-mode remote --auth-url http://backend:8080/internal/auth/verify \
  --auth-token-file /opt/hymio/config/private/backend/internal-service-token
```

Configure the extensions' ignored `_connection.local` to use `http://backend:8080`
and the same service token, following the [deployment guide](../README.md).
Use a matching Oath release with `--system-prompt`, `max_tool_only_steps`, subagent APIs and
application-event admission support. Tasks and delegated-result reconciliation start with
Backend; they need no additional cron container or public port. Keep the
role, style and skill guidance in the versioned Markdown file; do not put changing device
state or user data in it. Restart after updating instructions. The runtime's tool-only limit
defaults to 100; its independent run step/time limits may stop work sooner.
If bootstrapping as root, ensure generated Vault role/secret files are readable by
UID 10001 after Oath initializes them, before accepting chat requests. A root-only
bind-mounted credential causes model calls to fail even when container health passes.

Copy `deploy/cloud/cloud.example.toml` to `/opt/hymio/config/cloud.toml` and set:

```toml
web_domain = "hymio.example.com"
api_domain = "hymio.example.com"
backend_config_dir = "/opt/hymio/config"
runtime_network = "oath_oath"
managed_identity = true
```

Replace the network name if Oath uses another Compose project/network. Backend joins
this existing network without publishing its own port. Oath WS/Biz and Vault can stay
bound to host localhost. Only Caddy publishes public ports. `/internal/*` returns 404
at the public entry; private containers can still reach Backend's internal endpoints.

```sh
python3 deploy/cloud/manage.py prepare --config /opt/hymio/config/cloud.toml
python3 deploy/cloud/manage.py start --config /opt/hymio/config/cloud.toml
```

`start` builds the images and waits for container health. Managed identity provisions
only a Casdoor container and persistent volume, not its application or owner account.

## 3. Configure identity and invitation registration

Managed Casdoor is published only on host `127.0.0.1:8000`. Access its administration
interface through SSH forwarding, for example:

```sh
ssh -L 8000:127.0.0.1:8000 your-admin@your-server
```

Open `http://localhost:8000` locally. Initialize/rotate administrator credentials according
to the pinned Casdoor image's setup instructions. Create a **separate organization** for
normal users; `built-in` is reserved for Casdoor administrators. Create a password-login
application with authorization-code support and the exact HTTPS callback above. Copy its
client ID into `hymio.toml` and its secret into the private secret file. Create the initial
owner account in that organization. Restart Backend after changing its TOML or client secret.

Enable signup on this private Casdoor application for invitation registration. Keep signup
fields limited to username/password/confirmation; disable extra required profile fields.
The Hymio forms handle the invitation separately. This setup supports account-form login;
Google/browser OIDC requires a separately configured public issuer.

Put one **reusable invitation code per line** in `private/backend/invitation-codes`.
No code is built into the public source. Edit the file to replace or add codes; Backend
reloads it on each signup without restart. Empty/unreadable files never allow registration.
Web and iOS show “邀请码请联系作者获取。”; codes never enter Casdoor, Oath or model context.
Keep Casdoor private: its own public signup route would bypass Hymio's invitation check.

## 4. Verify and operate

```sh
curl --fail https://hymio.example.com/health
curl --fail https://hymio.example.com/auth/options
# Expect 404; no internal endpoint should be accessible here.
curl -o /dev/null -w '%{http_code}\n' https://hymio.example.com/internal/auth/verify

python3 deploy/cloud/manage.py status
python3 deploy/cloud/manage.py logs
python3 deploy/cloud/manage.py stop
```

`status`, `logs` and `stop` use the last generated stack. Start again with the explicit
config path when changing configuration. Changing the Web public address requires a rebuild
(`start`); editing invitation codes does not. Stop preserves volumes, stops managed Casdoor
if enabled, and leaves Oath, externally managed identity and E2B computers running.

The operator console is available at `https://WEB_DOMAIN/admin/` and is never shown in the user
Web navigation. `/admin/api/*` is server-authorized; knowing the route does not grant access.

Verify wrong-code rejection, signup/login/logout, two-account isolation, two chat turns,
WSS reconnect/history, and a cloud-computer command. `/health` proves process liveness,
not that the model, identity or E2B works. Do not use a production account in automated tests.

Container restart policies alone are insufficient for a sealed Vault after host reboot.
Use your host service manager to start Docker, run Oath's bootstrap/unseal flow, restore
credential ownership, and bring up the generated Hymio Compose stack in that order.
Keep the host bootstrap's private inputs outside the repository. This repository does not
yet install a host boot service automatically. Test this recovery path on your deployment.
See the [configuration map](../CONFIGURATION.md) and
[Agent diagnostics guide](../TROUBLESHOOTING.md) for source ownership and log commands.

Back up Backend, Oath, Casdoor and Caddy volumes and private configuration separately.
Use SQLite's backup API for live databases; copying the database without its WAL can lose
data. Never use `down --volumes` for routine stops. E2B pause is not a file backup. Test
restoration before relying on backups. Upgrade reviewed versions and restart the stacks;
automated backups and a full identity/host provisioner remain future work.

## Other networking layouts

Distinct Web/API domains remain supported. Without `runtime_network`, Backend publishes
on `backend_internal_bind` (default Docker bridge `172.17.0.1`) and Oath reaches it through
`host.docker.internal`. Verify the actual bridge address and firewall Docker-published ports;
localhost host bindings cannot be reached through that bridge. Configure Oath upstream ports
accordingly. Optional legacy `agent_domain` exposes a separate Oath entry and must differ
from Web/API names. The recommended shared-network layout needs no direct public Oath entry.

For iPhone distribution, follow the [iOS/TestFlight guide](../../apps/ios/README.md#testflight-distribution).

### Media model access

Deploy the model-selection Oath release before enabling model settings. Set the same IDs in Backend `model_options` and Oath `agent.selectable_models`; choices without an override use the default provider. For another provider, configure the
corresponding `agent.model_providers.<choice>` entry with its model, API base, Vault credential
alias and one-time import environment name. Do not send text requests to a different provider
using the default provider's credential. Set Oath `tool_timeout_seconds = 150` for media operations.

Backend media calls reuse the main provider's Vault alias. Set `media_api_base`, `media_credential`, `vision_model`, `vault_url`, `vault_role_id_file` and `vault_secret_id_file` in the private Backend configuration. Place AppRole identity files under the private configuration directory already mounted at `/config`; use container paths in TOML. Do not publish them in the image or repository, and do not put the model key in an environment variable.

Use `runtime_network` to join Oath's existing private Docker network and reach Vault by its internal service name. Never publish Vault publicly. Preserve the installed dependency license notices when distributing the image. Attachments and generated images use the persistent Backend SQLite volume and require its normal backup policy.
