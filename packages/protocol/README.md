# Protocol

Hymio-owned API schemas, Kit contracts and generated client types belong here. Keep wire contracts usable across web, desktop, Chrome and iOS.

Oath events and Nostalgia Context entities are upstream contracts. Reference or generate from a pinned upstream definition; do not independently redefine their semantics. Hymio business API and Nostalgia examples in `spec/` remain proposals until their integrations are implemented.

`src/index.ts` currently defines the client-consumed subset of Oath WS v2 and Trace responses, with frame validation. Oath remains the source of truth; Hymio business schemas will be added as those services are implemented.
