# CLI capability handlers

Implement atomic operations as Python handlers using Oath's Tool interface. Discovery requires
zero-argument construction. Their schemas form the oath-cli catalog; no second registry is needed.

Hymio exposes only `bash`, `cli` and `skill` directly to the model. Product handlers remain in
ToolSystem for admission, authorization, durable status and traces. Add workflow guidance under
`extensions/skills`; use `oath-cli status INVOCATION_ID` for execution queries.
