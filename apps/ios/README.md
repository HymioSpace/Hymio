# iOS

The iOS client owns platform UI, voice/photo input, notifications and secure local credential storage. It uses the same Hymio business APIs and Oath event protocol as the other clients.

Shared web components do not automatically become native iOS views. Reuse protocol schemas, design tokens and assets where appropriate; choose the native UI or web-hosting approach when implementing the client.

Status: responsibility scaffold; no Xcode project or signing configuration yet. The separate Hymio-iOS repository is not a build dependency and is not migrated by this initialization.
