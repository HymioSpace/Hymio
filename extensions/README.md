# Oath extensions

Hymio-specific Agent capabilities live here; Oath's core remains in its own repository.

- `skills/`: directories containing `SKILL.md` instructions.
- `tools/`: Python modules implementing Oath's tool interface.
- `cli/`: documentation for product commands exposed through `oath-cli`.

From this repository, with Oath installed:

```bash
oath start \
  --skill ./extensions/skills \
  --tool ./extensions/tools
```

This mounts extension directories. Use the unified Hymio launcher for the full product: it prepares
the private Backend connection, disables host Bash and exposes `bash`, `cli` and `skill` as native
tools. Product capabilities are registered in the same ToolSystem and discovered through
`oath-cli`; device-aware Bash prefers an online personal Mac and reports any cloud fallback.
Running the command above against default Oath config would conflict with the built-in Bash; set
`agent.builtin_bash = false`. See the
[device guide](../deploy/computer/README.md).

Extension code is a deployment dependency. CLI handlers can call Hymio business APIs; keep authorization and business invariants in those APIs, and avoid copying backend implementations into tools. Private capabilities use ignored `extensions-local/` directories or external repositories and must be passed explicitly; they are not auto-discovered.

The `context` skill covers personal-context recall and explicit remember requests. The tools use
the same private `_connection.local` prepared by the launcher. Nostalgia credentials stay in
Backend; tools derive user identity from Oath's verified invocation.

Oath is a generic runtime and must not contain Hymio business tools or personal-context semantics.
Hymio business capabilities are declared here and mounted into the generic Oath runtime.
`remember` and `recall` are context commands exposed to the normal Agent; context injection and
Nostalgia's scheduled dreaming lifecycle remain runtime mechanisms, not Agent commands.

`recall` keeps query-only search compatibility and also accepts `action="read"`, `kind` and `id`
to open a full original or interpretation. The Memory UI and Agent follow the same published
references; saving an original does not promise immediate synthesis.

`remember` now requires `summary` (grounded extraction) and `text` (exact supporting quote).
It selectively retains useful context, not whole conversation streams. Both are stored atomically
in one record with `hymio.remember.v2` provenance; published understanding is still a later step.
The runtime does not provide a verified message index to this tool, so no model-supplied index
is accepted. Legacy records remain readable; new text-only tool calls must supply the summary.

The Agent invokes Kit operations through `oath-cli help`, which reads their current schemas from
the ToolSystem catalog. Execution still checks whether the current user installed the requested application. The
same Kit operation API serves iOS and Agent calls. Web does not expose Kits or request their data.

`kit_call`, `kit_build` and the `kit-builder` skill are scoped to the `ios` channel through Oath's
generic channel-exposure mechanism. `kit_build` delegates source work to one long-lived coding
context per application; the main Agent supplies product requirements rather than code.

The subagent-only `kit_dev` tool reads, patches, checks and publishes the bound React/Python
project. `kit-coding` explains that workflow inside the delegated context. Oath filters
`kit_dev` from main-Agent definitions and server-side admission, not only from prompt text.
Web and Mac receive no application tools, skill entries, instructions or context.
