# Local deployment

Hymio owns service composition. `start.py` starts Casdoor, Hymio Backend and Oath, then a Web or Tauri development client. Clients themselves never deploy Oath. This is a macOS/Linux development workflow, not a production installer.

## First run: one private configuration

Requires macOS/Linux, Docker with its daemon running, [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22.12+ and pnpm 11. Desktop also needs Rust and Tauri platform dependencies (Xcode command line tools on macOS).

Clone both repositories beside one another and install their commands:

```bash
git clone https://github.com/HymioSpace/Oath.git
git clone https://github.com/HymioSpace/Hymio.git
(cd Oath && bash scripts/oath-install)
cd Hymio
bash scripts/hymio-install
# If either command is missing: uv tool update-shell, then reopen your terminal.
hymio init
hymio start --client web --timeout 900
```

`hymio init` asks for **the MiniMax key**, with hidden input, and saves them in
**`~/.hymio/config.toml`**, mode 600. This is the only file you edit or copy for a fresh
installation on another computer. Its public template is [config.example.toml](config.example.toml).
Open http://127.0.0.1:1420 and register your Hymio account after startup.

| Input | Where to get it / what it does |
| --- | --- |
| `minimax_api_key` | Create a platform API key at [MiniMax China](https://platform.minimax.cn/login), with access/balance for your selected text and media APIs. A chat-app subscription is not an API credential. |
| `daytona_api_key` (cloud desktop) | Get a key from [Daytona](https://app.daytona.io/api), or supply `DAYTONA_API_KEY`. Optional for chat-only installations. |
| `admin_user_ids` | Private list of Hymio product account IDs allowed to manage resources. Empty by default. See below. |
| `e2b_api_key` (legacy E2B only) | Get a key from the [E2B console](https://console.e2b.dev/). Template builds and computers use this account's quota/billing. |
| `models` (optional) | Settings choices; the first model is the default. Defaults to MiniMax-M2.7 / MiniMax-M3. Only list models your account can call. |
| `vision_model` (optional) | Image/document understanding model; defaults to MiniMax-M3. Verify its API access separately from text generation. |
| `minimax_api_base` (optional) | Defaults to `https://api.minimax.cn/v1`. International accounts need their matching endpoint and key. See [MiniMax API documentation](https://platform.minimax.cn/docs/api-reference/text-openai-api). |
| `casdoor_port` (optional) | Defaults to 8000; set 8001 if another application already uses 8000. Issuer and health checks follow automatically. |
| `lan_host` (optional) | `off` by default. Set `auto` for iPhone/LAN development; no other IP edits needed. |
| `e2b_template` (optional) | Defaults to `hymio-desktop`. Checked on startup and built with Hymio's recipe if absent. Existing aliases are reused, not rebuilt automatically. |
| `invitation_codes` (optional) | List of reusable signup codes. Empty means local signup does not require an invitation. Restart after editing this list. |

No OpenAI, Google, Apple, cloud-host or manually created Casdoor client credentials are needed
for the local Web stack. Google sign-in remains an advanced manual identity-provider setup.

Initialization generates a separate Casdoor administrator password, Hymio organization, minimal
username/password signup application, signing certificate and internal service credentials.
You do **not** need to open Casdoor to create its organization/application. The model key is imported
to Oath Vault. Cloud provider credentials stay in Backend. Generated files live in `~/.hymio/local-<id>/`;
the startup log prints this directory. `identity.json` there contains the initial private Casdoor
administrator password (`built-in` / `admin`); do not share it or use it as a normal Hymio account.
Casdoor is exposed only on loopback. Existing identity records/admin changes are preserved on restart.
Generated runtime directories are private (700). Selected files mounted into non-root Docker
containers are readable inside those containers; their private host ancestors prevent access
by other host users. Do not recursively change generated file permissions.

The first start may take several minutes to build Docker images, install dependencies and optionally build
the legacy E2B desktop template. A CLI timeout leaves startup running; check `hymio logs -f` and
`hymio status` before starting another instance. An E2B authorization/network failure is an error,
not a reason to repeatedly rebuild templates. You can change the keys in the private input
file before retrying; a changed model key gets a new Vault alias automatically on restart. Old aliases remain in
Vault for existing records; revoke obsolete keys at the provider when appropriate.

### Environment variables and custom locations

`MINIMAX_API_KEY`, `DAYTONA_API_KEY` and `E2B_API_KEY` override values in the file. For automation, export them
privately, then run `hymio init --non-interactive`. The init command saves the provided values
in the private file so later restarts do not depend on that terminal's environment. Alternatively
copy the example and leave its key fields empty when you intentionally supply the environment
on **every start/restart**. Do not put literal keys in shell commands or shell history.

```bash
hymio init --config /your/private/hymio.toml
hymio start --config /your/private/hymio.toml --timeout 900
```

The chosen path is remembered by the CLI. A different path gets a separate generated runtime
and Casdoor/Oath Compose project. Default service ports still allow only one local stack at a
time. An occupied port produces an error; Hymio never stops another application's container.

### Another computer

1. Install the prerequisites and clone/install the two repositories using the commands above.
2. Securely copy **only `~/.hymio/config.toml`** to the same location on the new computer; run
   `chmod 600 ~/.hymio/config.toml`. Do not run init again or copy generated AppRole/service files.
3. Run `hymio start --client web --timeout 900`. Casdoor and Vault initialize automatically;
   an existing E2B template is reused with the same key/account.

This creates an **independent, empty installation**. Old accounts, chat, tasks and device bindings
are not in the input file. They need a consistent data backup/restore if you want to migrate them.
Both installations share API billing when you reuse keys. Do not copy the generated runtime to
simulate a database migration. For account access to an existing cloud deployment, just open
its Web URL or configure the iOS client; no local backend installation is needed.

### Existing installations

Without `~/.hymio/config.toml`, existing `backend/hymio.toml`, `~/.oath/oath.toml`, Casdoor volumes
and launcher preferences retain their original behavior. Do not rerun setup for a normal update.
`hymio init` opts into a fresh managed installation; stop the old launcher and Oath first to release
ports, and keep its data. Unified mode uses its own named Oath project, never adopts old Vault data.
Use explicit `--backend-config` / `--oath-config` to stay on the legacy path; do not mix them with
`--config`. Advanced manual initialization is in the [Backend guide](../backend/README.md).

## Install and start

From Hymio's root (after `hymio init`, or with an existing legacy setup):

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
| Kit Host (internal) | http://127.0.0.1:8090 |
| Casdoor | http://localhost:8000 |
| Oath WS | ws://127.0.0.1:8765 |
| Oath Biz | http://127.0.0.1:8766 |

CLI options: `--config PATH` (unified input), `--client web|desk|none`, `--home PATH`, `--timeout SECONDS`, `--backend-config PATH`, `--oath-config PATH`, `--auth-project NAME`. Relative paths are relative to your working directory. Backend credential paths resolve against its config directory. Unified mode derives service settings from `~/.hymio/config.toml`; legacy mode keeps model/login settings in their original TOML files. No `.env` is required.

Kit Host is a separate local process managed with Backend. It owns `kits.sqlite3`, installations
and application HTML; iOS and Agent tools reach it only through Backend's authenticated
routes.

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
`hymio doctor` shows the active configuration mode, the editable inputs, generated files,
private credential location and service health without printing secrets.

To stop **legacy** Docker services explicitly:

```bash
oath stop
docker compose -f deploy/auth/compose.yaml down
# Existing dev project: add -p hymio-auth-dev before down
```

For unified mode, use the generated directory shown in `hymio logs`: `oath stop --name hymio-oath-<id>` and `docker compose -p hymio-local-<id> -f ~/.hymio/local-<id>/casdoor-compose.json down`.

Do not add `--volumes` unless you intend to delete login data. The launcher rejects occupied Backend/client ports rather than stopping someone else's processes. Failures show the failing command or service output; Docker resources are left intact for inspection.

This local launcher does not deploy Nostalgia or connector services. See [feature09](../spec/feature09-local-start.md) for boundaries and [Backend](../backend/README.md) for the authentication contract.

## Device environments

The launcher mounts Hymio device tools/skills; cloud desktops are provisioned only after an administrator grants access.
It writes a private `hymio-runtime.local.toml` beside the Oath config, disabling host Bash;
your source Oath configuration is unchanged. See [computer environments](computer/README.md)
for E2B configuration, device management and the end-to-end check.

## Update an existing local installation

After the changes are merged, update both reviewed checkouts. Keep local changes and private
configuration safe before switching branches; do not reset the checkout to update it.

```bash
# From Hymio's root, with Oath beside it:
git -C ../Oath switch main
git -C ../Oath pull --ff-only
git switch main
git pull --ff-only
# Rerun installers if their CLI code changed:
(cd ../Oath && bash scripts/oath-install)
bash scripts/hymio-install
hymio restart --client web --timeout 240
hymio status
curl --fail http://127.0.0.1:8080/health
```

Do not rerun account setup or overwrite existing TOML files for a routine update. Preserve
Casdoor/Oath volumes, Backend SQLite and private configuration. The launcher's dependency
sync/build steps apply the checked-out code. Existing model credentials remain in Vault.
A newly added provider may require a one-time credential import as described below.

Task capture, schedules and delegated-result reconciliation start with Backend. No extra cron
job, queue service or public port is required. Deploy the matching Oath subagent/application-event
contract first; old runtime binaries cannot execute these features. Sign in, send a concrete
request and open Tasks to verify an outcome; `/health` alone does not verify model execution.
For iOS, rebuild/run the app in Xcode to pick up native UI changes; restarting services cannot
update an already installed app or TestFlight build.

## Cloud deployment

For Linux servers, use the separate [cloud deployment entry](cloud/README.md): containerized
Backend, static Web and Caddy HTTPS, with E2B computers and independently managed Oath/OIDC.
The development launcher above is not the cloud deployment command.

## iPhone and LAN development

With unified configuration, set `lan_host = "auto"` in `~/.hymio/config.toml` and restart.

For legacy configuration, network settings live in `deploy/local.toml` (ignored by Git).

```bash
cp deploy/local.example.toml deploy/local.toml
```

Edit that file:

```toml
lan_host = "auto"
```

Then run:

```bash
hymio restart --client web
hymio status
```

`auto` chooses the default-route private IPv4 address. With multiple network interfaces or a VPN, put the desired local private IPv4 address in `lan_host` instead. Set it to `off` to return to local Mac development. Restart reloads the file; CLI preferences store only the configuration path. `--deploy-config /path/to/local.toml` selects another configuration file without changing the source configuration. A missing local file defaults to `off`.

The launcher derives an ignored Backend runtime overlay, the Web development API URL and iOS `Network.generated.xcconfig`. Do not edit these generated outputs. The source Backend config, client.toml and iOS signing settings stay unchanged. Debug includes the generated network file; Release does not, so a LAN endpoint is never silently baked into a release build. Team selection remains in Xcode, and private signing overrides can stay in Local.xcconfig.

The phone uses the single Backend URL printed by `hymio status`: login, chat at `/agent/ws`, and queries at `/oath-biz`. Oath ports remain loopback-only. Native iOS requires only port 8080; Web development preview uses port 1420. Development still runs Backend/Web on the host for live editing, with Oath/Casdoor managed in Docker; production uses the separate Compose deployment.

LAN auto-configuration supports account login and preserves the registered Casdoor callback for backend-only code exchange. Browser OIDC deployments configure public callbacks separately. Existing sessions refresh advertised endpoints on login/refresh; sign out/in if an older session still points at a loopback WS address.

Use the same trusted Wi-Fi, allow the Mac firewall prompt and permit Local Network access on iPhone. LAN HTTP is for Debug development; use cloud HTTPS for remote access. Open the printed Backend URL with `/health` in iPhone Safari, then [install through Xcode](../apps/ios/README.md#install-directly-on-your-own-iphone).

## Models and attachments

Unified mode uses `models` and `vision_model` in `~/.hymio/config.toml`. In legacy mode, the settings screen uses Backend's `model_options` (first item is the default). Local startup forwards that allowlist to Oath and derives the media provider endpoint, Vault alias and private AppRole paths from `oath.toml`. It does not copy the API key. `vision_model` defaults to MiniMax-M3; image generation uses image-01 and audio transcription uses asr-1.0. The account must have access/balance for each API; a text subscription alone may not include them.

Update both Oath and Hymio before starting. The Oath build must support `agent.selectable_models`. The launcher uses a 150-second tool deadline for media calls and writes an ignored `backend/hymio-media.local.toml` overlay. Normal files and photos upload through the authenticated Backend; they do not require an E2B computer.

Uploads support images, PDF, DOCX, PPTX, XLS/XLSX, text/Markdown/CSV/HTML/JSON/XML/YAML and MP3/WAV/M4A/OGG/FLAC. Individual files are limited to 20 MiB, with eight attachments per message and 256 MiB per user. Video and arbitrary archives are not supported. Scanned PDFs may need OCR; empty extracted text is not a successful visual interpretation.

For a second API provider, configure Oath `agent.model_providers.deepseek-flash` with `model`, `api_base`, `credential`, `import_env` and optional `extra_params`. Add `deepseek-flash` to Backend `model_options`. Export `DEEPSEEK_API_KEY` before the first start so Oath can seed its independent Vault alias; later starts read Vault. Media APIs continue to use the default MiniMax provider.

## Cloud device API instead of E2B

To use an existing VM, select `computer_provider = "device_api"`; an E2B key and template
are not required. Add `device_api_targets` to your one private input file. Installation, restricted
host API setup, account assignment and changing the server IP are documented in
[Linux cloud computer](computer/LINUX.md#private-configuration). The host must already exist;
Hymio does not automatically purchase or delete operator-managed VMs.


## Cloud resources and administration

New accounts receive **no cloud desktop or cloud phone**. Chat and attachments work without one.
Daytona is the default desktop provider; the default API URL is `https://app.daytona.io/api`.
Supply `daytona_api_key` in the private input file or export `DAYTONA_API_KEY` for startup.
`daytona_api_url` and `daytona_snapshot` are optional overrides. Provider keys never enter clients
or agent sandboxes. A default Daytona image is prepared with one shared desktop/browser/workspace.

1. Start Hymio and register your administrator's normal product account.
2. Find its product user ID in the private Backend SQLite database (`users` table), or the
   authenticated `/auth/me` response. This is not a Casdoor administrator name or an API key.
3. Add that ID to `admin_user_ids = ["YOUR_PRODUCT_USER_ID"]` in `~/.hymio/config.toml`, then
   restart Hymio. Legacy deployments set this field in private `backend/hymio.toml` instead.
4. Open the independent operator console at `/admin/` and sign in with that product account.

The local observability stack starts with `hymio start`:

- Prometheus: `http://127.0.0.1:19090`
- Grafana: `http://127.0.0.1:13000`
- Operator view: `/admin/#/monitoring`

Override ports with `OATH_PROMETHEUS_PORT` and `OATH_GRAFANA_PORT`. In cloud deployments,
set Backend `prometheus_url` to the private address reachable from its container. Client
telemetry contains timings and anonymous device IDs only, never prompts or model output.
   It is not linked from the user Web sidebar. Server authorization checks every read and change;
   knowing the URL does not grant access.
5. Search a registered user, choose a provider and click **开通云电脑**. On their next login or
   device request, Hymio allocates or resumes that user's computer. Granting access itself
   does not allocate a sandbox. Close access separately from releasing an existing environment.

Global limits are **Daytona 10, E2B 20, 火山 ECS / device API 1**. These are physical allocation
limits, not a limit on the number of grants. Reserved, stopped and uncertain environments count.
Each user has at most one active cloud-computer grant. Switching providers while an allocation
exists is rejected until that cloud computer is released, preventing accidental double binding.
Removing permission prevents future operations but preserves files and capacity. **释放资源**
requires confirmation and deletes hosted sandboxes; an operator-managed API VM is only detached
and continues to exist and incur its provider's charges. Daytona auto-stops after 20 minutes idle;
stopped sandboxes preserve files and still occupy a slot. No automatic deletion is configured.

Creation timeouts retain their reservation. Use **核对分配** to recover the original stable sandbox
identity; never retry by deleting database rows. In-flight or uncertain executions prevent unsafe
release. If release is uncertain, its slot remains held until confirmed. Historical allocations
are imported without granting access; over-limit legacy resources block new allocations and are
not automatically destroyed. Cloud phones are visible as a reserved, disabled resource kind.

The generated Caddy configuration serves the console at `/admin/` and routes `/admin/api/*`
to Backend. Keep `admin_user_ids`, keys and database backups private.
