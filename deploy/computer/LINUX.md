# Dedicated Linux cloud computer

This installer prepares a dedicated Ubuntu x86-64 host with an unprivileged execution user,
Bash, an XFCE desktop, a persistent Chromium profile, Playwright and screenshot/input utilities.
It does not purchase resources, bind a device into Hymio, install a second reasoning agent,
or expose a public desktop. The provider connection/enrollment remains separate work.

Ubuntu 26.04 was used for installation verification. Reserve at least 4 vCPU / 8 GB memory;
60 GB disk is recommended for application installation and browser data.

```sh
scp install-linux.sh root@YOUR_HOST:/tmp/
ssh root@YOUR_HOST 'bash /tmp/install-linux.sh'
```

Run only on a host dedicated to agent execution. Commands and browser content can access
this execution user's files; do not place backend credentials or unrelated personal data there.
The `hymio-device` user has no sudo grant. Administrative package installs require the operator.

The browser control port is bound to 127.0.0.1:9222. X11 TCP listening is disabled. Do not expose
CDP or an unauthenticated VNC server through a security group. Runtime control uses the authenticated HTTPS device API below. SSH is only an operator installation and maintenance channel.

## Browser download fallback

When the official browser CDN cannot be reached from the instance, download the Chromium
archive matching the pinned Playwright release from its official download location on another
machine, transfer it privately, and provide its path:

```sh
CHROMIUM_ARCHIVE=/tmp/chromium-linux.zip bash /tmp/install-linux.sh
```

Do not substitute an untrusted download mirror. This installs the archive under
`/opt/hymio-device/chromium`, without changing the device user's profile.

## Service management

```sh
systemctl status hymio-display hymio-desktop hymio-browser
journalctl -u hymio-browser -n 50
systemctl restart hymio-browser
```

Display: `:99`, 1280×800. Workspace: `/home/hymio-device/workspace`.
Persistent browser profile: `/home/hymio-device/browser`.
Python: `/opt/hymio-device/bin/python`.
Services start on boot; stopping them does not release an ECS instance or stop its cloud bill.
Backing up these directories requires protecting browser cookies as credentials.

## Host API and Hymio connection

Hymio uses HTTPS only; it does not load an SSH key or run SSH commands. The host agent
provides POST `/v1/status`, `/v1/execute`, `/v1/pause` and `/v1/resume`, authenticated by a
separate Bearer device token. Bash, browser and desktop actions use the same execution
contract as the backend provider, with a deadline. Responses contain execution results or
screenshots; the backend archives screenshots as private user media.

### Install the API on the prepared host

1. Create a random device token of at least 32 characters. Keep it private on both Backend
   and the execution host. Do not use a Hymio login token, service token or provider AK/SK.
2. Prepare a TLS server certificate and key. Prefer a stable DNS name with an automatically
   renewed public certificate. For an IP-only test, run `issue-certificate.py --host HOST
   --output PRIVATE_DIRECTORY` on the operator machine (requires Python cryptography).
   It creates a private CA and a 90-day server certificate. Keep `ca-key.pem` offline; copy
   only `ca.pem` to Backend and the server certificate/key to the execution host. Renew the
   server certificate before expiry and restart the host API service.
3. Place `device_api.py`, `device_runtime.py`, `device_worker.py`, `install-api.sh`,
   `backend/hymio_backend/devices/desktop_controller.py` (renamed `controller.py`),
   `backend/hymio_backend/devices/validation.py`, `token`, `server.pem`, `server-key.pem`
   into a private temporary directory on the host. Use your administrative connection.
4. Run `sudo bash install-api.sh PAYLOAD_DIRECTORY`. The API runs as `hymio-device`, with
   only the capability required to bind HTTPS port 443. Remove the temporary payload after
   installation. Browser CDP remains on localhost and X11 TCP is disabled.
5. Allow TCP 443 in the security group, preferably restricted to the Backend's source IP.
   An unauthorized request to `/v1/status` must return 401.

### Private configuration

Set this in the existing Backend `hymio.toml`, or unified `~/.hymio/config.toml`:

```toml
computer_provider = "device_api"
device_api_targets = [
  { id = "cloud-primary", user_id = "PRODUCT_USER_ID", base_url = "https://computer.example.com", token_file = "/PRIVATE/DIRECTORY/token", ca_file = "/PRIVATE/DIRECTORY/ca.pem" }
]
```

Omit `ca_file` for a certificate trusted by the system CA store. HTTPS certificate checking
cannot be disabled. Tokens are sent only to the configured endpoint; redirects and environment
proxies are disabled. Only Backend needs this credential. Filled-in configuration and account
IDs must stay outside Git.

`user_id` is the authenticated Hymio product ID, not a display name, provider login or model
parameter. Assign one target per account through trusted operator configuration. Unassigned
accounts can chat but cannot use this computer. Different users must not share a Unix account
and browser profile. This is a dedicated execution machine, not isolation for untrusted tenants.

**Changing IP:** change only `base_url` and restart Backend (`hymio restart` locally). Keep `id`
and `user_id` unchanged to retain the product binding. For an IP certificate, also reissue its
server certificate for the new IP using the same private CA and restart the host API. A stable
DNS name avoids this certificate change. A genuinely new machine requires deliberate rebinding;
do not present an empty machine as restored data.

Containerized Backend needs read-only access to its token/CA files at container-visible paths,
for example `/config/private/`. It does not need OpenSSH, root keys or a Docker socket.

### Lifecycle

The first device query binds the assigned target. No VM is purchased, replaced or deleted.
Pause prevents new agent commands; it does not shut down the ECS or stop its bill. Revoke
removes the product binding and preserves the server and files. If its operator assignment
remains, a later ensure can bind it again. Remove the assignment and rotate the device token
to withdraw access permanently. Already accepted commands may finish after revocation.

A host-side process lease serializes operations in addition to Backend's durable records.
An interrupted request after dispatch is outcome_unknown, never automatically replayed.
Automatic reconciliation of unknown results and real-time manual takeover are future work.
The API exposes the dedicated user's execution environment; never place Backend credentials
or unrelated personal data on that machine.

```sh
systemctl status hymio-device-api
journalctl -u hymio-device-api -n 50
```
