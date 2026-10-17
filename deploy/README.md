# Deployment

Hymio owns product deployment: configure and compose its backend, Oath and Nostalgia, mount Hymio extensions, and publish client-facing endpoints. Clients connect to the running services; no Oath deployment is created per login or WebSocket.

The target is a single product deployment entry point. Today Oath has its own `oath start`; Hymio has no combined startup command or Compose file yet. Do not run deployments as a side effect of importing backend code or starting a client.

Use versioned runtime images/artifacts by default. Git submodules are optional for coordinated source development, not required for deployment. See [feature05](../spec/feature05-repository-deployment.md).

Configuration holds endpoints, artifact versions and secret references. Private extension paths are explicit and optional; public builds must not require private repository credentials.
