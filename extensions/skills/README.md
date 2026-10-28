# Skills

Add one directory per skill with a `SKILL.md` following Oath's skill contract.

- CLI handlers provide stable atomic operations and structured results through ToolSystem.
- Skills explain intent, when a capability is useful, and how to compose operations.
- Discover parameters with `oath-cli help NAME`; use `--json` for structured input.
- Query execution state with `oath-cli status INVOCATION_ID`, including Bash and device calls.
- Keep credentials and deployment addresses out of skills. Authorization belongs to the runtime
  and business APIs. Preserve channel and delegated-agent restrictions.

Product extensions use CLI + Skill. The native surface remains `bash`, `cli` and `skill`; adding
an application capability does not require another model-facing tool.
