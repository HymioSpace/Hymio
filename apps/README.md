# Clients

Clients are entry points to the same Hymio product. Each owns its navigation, platform integration and release artifacts. Product authorization and business rules belong to backend APIs.

- [client](client/README.md): web frontend and Tauri desktop shell.
- [admin](admin/README.md): standalone operator console for cloud resources and future operations.
- [chrome](chrome/README.md): extension UI, background tasks and browser permissions.
- [ios](ios/README.md): iOS UI and native capabilities.

Client identity must be stable per device for Oath replay cursors. Each connection authenticates independently; credentials and connector tokens are never baked into builds.
