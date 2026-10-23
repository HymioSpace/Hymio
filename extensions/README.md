# Oath extensions

Hymio-specific Agent capabilities live here; Oath's core remains in its own repository.

- `skills/`: directories containing `SKILL.md` instructions.
- `tools/`: Python modules implementing Oath's tool interface.
- `cli/`: Python modules declaring Oath CLI commands.

From this repository, with Oath installed:

```bash
oath start \
  --skill ./extensions/skills \
  --tool ./extensions/tools \
  --cli ./extensions/cli
```

This mounts extension directories. Use the unified Hymio launcher for the full product: it prepares
the private Backend connection, disables host Bash and registers `nostalgia`, `devices`, device-aware `bash`,
`browser`, `computer` and the read-only `device_command`. Running the command above against default Oath config would conflict with
the built-in Bash; set `agent.builtin_bash = false`. See the [device guide](../deploy/computer/README.md).

Extension code is a deployment dependency. CLI handlers can call Hymio business APIs; keep authorization and business invariants in those APIs, and avoid copying backend implementations into tools. Private capabilities use ignored `extensions-local/` directories or external repositories and must be passed explicitly; they are not auto-discovered.

The `context` skill covers personal context queries; `dreaming` covers draft maintenance and
publication. Both use the `nostalgia` tool and the same private `_connection.local` prepared by
the launcher. Nostalgia credentials stay in Backend; the tool derives user identity from Oath's
verified invocation. See [Context and dreaming](../spec/feature17-context-dreaming.md).
