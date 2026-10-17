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

This starts Oath with these directories mounted, not the complete Hymio product. The directories currently contain documentation only and register no capabilities. Current contracts live in [Oath](https://github.com/HymioSpace/Oath/blob/main/spec/feature-oath-command.md).

Extension code is a deployment dependency. CLI handlers can call Hymio business APIs; keep authorization and business invariants in those APIs, and avoid copying backend implementations into tools. Private capabilities use ignored `extensions-local/` directories or external repositories and must be passed explicitly; they are not auto-discovered.
