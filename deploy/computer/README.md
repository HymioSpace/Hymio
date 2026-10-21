# E2B personal computers

One personal agent can use several devices. Web/iPhone/Mac are conversation channels;
the E2B cloud desktop runs Bash, Chromium and desktop automation in one hosted sandbox.
There is no local Docker computer provider. Docker still deploys Oath/login/application services.

## Configure

Unified local deployment reads `e2b_api_key` and optional `e2b_template` from
`~/.hymio/config.toml`. `hymio start` checks the template alias and builds it only if absent.
No separate key file or build command is needed. The manual steps below apply to legacy/cloud
configuration or an intentional template rebuild.

Store your E2B API key in `backend/private/e2b-api-key` (mode 600). Build a template:

```bash
cd backend
uv sync --extra e2b
uv run --extra e2b python ../deploy/computer/build_e2b.py --key-file ./private/e2b-api-key
```

Private `backend/hymio.toml`:

```toml
computer_provider = "e2b"
e2b_key_file = "./private/e2b-api-key"
e2b_template = "hymio-desktop"
```

Start with the [launcher](../README.md) and sign in. Hymio automatically prepares and binds
your cloud computer; the Agent also ensures availability before listing execution devices.
Provisioning uses your own E2B account. The API key stays in Backend, never in tool arguments,
model context or sandbox environment. Backend does not need a Docker socket.

## Lifecycle

One active cloud desktop per user. Every tool requires its exact device_id.
Pause/resume restores the original sandbox, including tabs and form input. Passive GET listing
never wakes them; login and the Agent devices tool explicitly ensure availability. A confirmed
missing sandbox is replaced automatically and reported as a new empty environment.
Transient network/authentication failures do not trigger replacement.
Sandboxes start with a one-hour timeout and automatically pause rather than being destroyed.
Automatic resume is disabled; resume explicitly in device settings. Activity-based idle policy,
automatic renewal and backups are not implemented.
Revoking a sandbox destroys it and can delete files: export data first.
A missing sandbox is shown as expired, separately from transient connectivity failures.
An ensure request replaces a confirmed missing sandbox and records the replaced device ID.
Unknown command outcomes block further commands; do not blindly repeat side effects.
There is no destructive restart endpoint disguised as recovery. A blocked device currently
requires operator investigation or explicit revoke/reprovision with data-loss confirmation.

## Tools and API

- devices: list owned devices and capabilities.
- bash: command/cwd on an explicit device; background descendants end with the invocation.
- browser: DOM snapshot/navigate/click/fill/key, tabs/new_tab/switch_tab/close_tab, back/forward/reload.
- browser screenshot: requires `page_id`, captures that page's viewport regardless of other windows.
- computer: screenshot/click/type/key/scroll, sharing the browser's desktop.
- device_command: query a prior invocation without repeating it.

Public routes use the Hymio bearer token:
GET /devices; POST /devices/register; POST /devices/{id}/heartbeat;
POST /devices/ensure; POST /devices/provision; POST /devices/execute; POST /devices/{id}/pause;
POST /devices/{id}/resume; POST /devices/{id}/revoke;
GET /devices/{id}/commands; GET /devices/{id}/commands/{invocation_id}; GET /devices/media/{id}.
Internal list/execute/command routes require a service credential and authoritative user_id.

Screenshots are owner-only authenticated media references. Client supports enlarged snapshots,
not live remote desktop. Oath's current text context does not visually inspect screenshot references;
autonomous visual reasoning requires a multimodal adapter. DOM-based browsing works today.
Capture metadata identifies browser viewport versus desktop, dimensions, timestamp, and page URL/ID
where applicable. Use the returned screenshot URL rather than inventing a sandbox file link.

Provider errors include safe diagnostic codes (authentication, rate limit, timeout, configuration).
Automatic ensure uses a persistent 5–300 second backoff and retains the existing binding.
A command rejected before dispatch releases its lock; uncertain dispatched effects are never replayed.
Confirmed creation rejection can retry after backoff. If creation was uncertain, recovery may adopt a
single sandbox with the binding's metadata after the old deadline; absence or ambiguity never creates
another sandbox. Expired lifecycle locks resolve only when the provider confirms the intended state.

## Software

The template installs LibreOffice Calc and CJK fonts. This Linux environment cannot run native
Microsoft Excel; Calc handles .xlsx. Rebuild the template for future computers to receive changes.
Check `sudo -n true` before installing sandbox packages; E2B Desktop's normal user supports it.
SDK root maintenance is available to the operator; tools do not expose provider credentials.
GUI apps started through Bash end with that invocation; use the desktop environment for persistent windows.

## Verification

```bash
cd backend
uv run --extra e2b python ../deploy/computer/e2e.py
```

Creates synthetic accounts, verifies ownership/idempotency, shared filesystem/browser/desktop,
tabs, command lookup, authenticated screenshots and full pause/resume memory retention.
Finally destroys the test sandbox. Synthetic account records remain; test credentials are not committed.

Self-hosted E2B or other hosted providers may be added behind ComputerProvider later;
no self-hosted E2B deployment is implemented here.
