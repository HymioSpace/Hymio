# Web and Desktop

One frontend for the browser and the Tauri desktop app. Conversation, Kits, Context, connector settings and Trace views share UI and interaction logic.

The Tauri shell and native commands will live in `src-tauri/`. Frontend features call platform adapters for file picking, notifications, credential storage and desktop-only actions. Browser builds must not depend on a running Tauri host.

Use shared modules from `packages/`. Oath execution remains server-side; closing the desktop window does not own the lifecycle of the agent. Starting a local Hymio deployment can be a later, explicit desktop capability.

Status: responsibility scaffold. Frontend framework and build configuration are not initialized yet.
