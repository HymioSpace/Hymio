# Feature 26 — Cloud and custom device providers

Status: Implementing. Provider metadata, replacement isolation and operator-assigned Linux HTTPS API execution are implemented.
Volcengine lifecycle APIs, Android execution and self-service custom host enrollment are not yet implemented.

## Product model

One personal agent can use several explicitly identified devices. Hymio owns user binding,
authorization, operation records, deadlines and recovery. Oath owns reasoning and tool execution.
Public cloud is the intended default; a user may opt into a personally owned Mac or other host.
A device's provider is infrastructure, not its user identity or its input channel.

Daytona is the default hosted desktop; an operator-managed VM (including ECS) can instead run
the host-side HTTPS API. Access and quotas follow
[feature 27](feature27-resource-access-administration.md).
Android provider integration and self-service custom host enrollment follow separately.
E2B remains a compatibility implementation during migration, not the target default. Operator-managed ECS access is verified; automatic Volcengine provisioning is not implemented. No automatic provider migration, resource purchase or deletion occurs.

## Device capabilities

Providers declare capabilities, workspace, display dimensions, revoke retention semantics and
whether a missing resource can be automatically replaced. Execution checks capabilities before
claiming a command. Unconfigured providers advertise no executable capabilities.

Cloud Android must not advertise Linux Bash or desktop browser automation without an actual
implementation. Its Android shell, app lifecycle, touch and screenshot operations will require a
versioned tool extension. Existing bash/browser/computer calls remain compatible.

## Lifecycle and identity

A replacement keeps the original provider and kind; it cannot silently become an E2B desktop.
For persistent phones and personally owned computers, automatic replacement is disabled. A
network error is never proof of resource deletion. Reconnection preserves identity; intentional
replacement creates an explicit new environment and records its predecessor.

Enrollment of a custom host must use an expiring single-use authorization tied to a user,
followed by a revocable device credential. It must not accept an arbitrary user_id or remote
execution URL supplied by a model. Prefer an outbound authenticated connection, with no
public unauthenticated shell/CDP port. Mac requires explicit Screen Recording and Accessibility
permissions; enrollment must show what the agent may access. This enrollment is future work.

Manual control and agent execution must share an exclusive lease. Vendor control-plane access,
controller readiness, application readiness and live viewing are separate health checks.
A screenshot carries capture time, actual dimensions and execution generation. Side-effecting
commands with uncertain outcomes are queried, never blindly replayed.

## Volcengine integration gate

Use official cloudphone APIs for device lifecycle, APK installation, command execution and
screenshots. Keep AK/SK exclusively on the backend. Official CUA/MUA task APIs run a vendor
agent; if used, expose them as bounded asynchronous executors with cancellation, callbacks and
budgets, rather than presenting them as low-level mouse/browser APIs.

Before choosing the computer transport, verify account eligibility, exact cost, public endpoint
access, authenticated operations, persisted data, Linux shell, browser/desktop consistency and
manual takeover. HTTP API reachability does not verify ADB, streaming or app compatibility.
No device can be marked supported on documentation alone.

References:
- https://docs.volcengine.com/docs/Cloudphone/what-is-computer-use-agent?lang=zh
- https://docs.volcengine.com/docs/Cloudphone/75748
- https://docs.volcengine.com/docs/Cloudphone/BillingOverview-3?lang=zh

## Operator-assigned Linux device APIs

The host owns installation, execution and process leases. Hymio's APIComputer connects through
HTTPS with a device token and verified TLS certificate. No SSH client, SSH key or operating
system setup command is part of Backend runtime. The Linux installer is a separate operator tool.
Stable target IDs map to per-user endpoint configuration. Changing base_url preserves the binding.
No target is assigned to arbitrary signup users. Explicit E2B configuration is legacy-compatible;
new unified installations default to device_api without requiring an E2B subscription.

The schema permits one active cloud desktop per provider, keeping previous bindings and records.
The migration replaces the old one-desktop index with a per-provider index. Do not run an older
Backend against a migrated database with multiple active provider bindings.

Pause gates agent commands; it does not suspend or delete a VM. Revoke detaches and preserves
the host. Remaining operator assignment permits later rebind. Accepted commands are not rolled
back. Endpoint tokens, TLS, bounded bodies and no redirects protect the device control interface;
SSH is used only by an operator for initial setup and maintenance, outside Hymio runtime.
See [host API deployment](../deploy/computer/LINUX.md).
