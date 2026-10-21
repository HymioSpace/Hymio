# Resource access and administration

Status: Implemented.

New accounts have no cloud desktop or cloud phone entitlement. A configured administrator
allows a product user to use one provider for a resource kind. Usernames and client-supplied
role flags never grant administrator status. Bootstrap administrator product IDs are private
operator configuration; administration requires a normal authenticated account session.

Hymio owns per-user grants, device identity, allocations, leases and audit records. Providers
own physical lifecycle. Desktop providers are Daytona, legacy E2B, and the operator's existing
cloud API (currently Volcengine ECS). Phone resource kind is reserved but not implemented.

Limits are enforced transactionally before provisioning: Daytona 10, E2B 20, cloud API 1.
Reservations, stopped sandboxes, in-progress deletion and uncertain creates all consume slots.
Only confirmed deletion or a definitive pre-allocation rejection releases capacity. Timeout
never proves that an environment was not created. Recovery queries a stable provider name or
label, without issuing another create. Unused grants do not consume slots.

Removing access prevents future calls without deleting files or freeing an allocation. Physical
release is a separate explicit administrator action with a data-loss confirmation. Unknown
executions block unsafe release. The cloud API preserves its external VM on detach; it is
not deleted by Hymio. Audit records contain actor, target, change and timestamp, never secrets.

The administration screen is an independent operator application at `/admin/`. It does not
appear in product Web navigation and has its own sign-in, visual language and future navigation
space. Only configured administrators can enter; the server checks every operation. It shows
provider capacities, searchable registered users, grants, allocated desktops and a small audit
trail. Phone access remains disabled in this phase rather than implying a working implementation.

Daytona uses its official Python SDK and API endpoint from private configuration. The API key
is loaded from DAYTONA_API_KEY or a private key file, never injected into a sandbox. One
sandbox per assigned user keeps workspace and browser profile isolated. Auto-stop preserves
data; no automatic deletion is configured. Bash, browser and desktop actions target one desktop.

Existing allocations are imported without granting access. Historical allocations above a limit
remain counted and block new creation until confirmed release; migration never destroys them.

A user has one active cloud-computer grant at a time. Changing the grant to another provider is
rejected while any allocation remains active; the operator must release the current computer
first. Historical and revoked provider records remain for audit, while the user-facing device
list exposes only the currently granted provider.
