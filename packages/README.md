# Shared packages

| Package | Owns |
| --- | --- |
| [ui](ui/README.md) | Web design tokens and reusable presentation components |
| [a2ui](a2ui/README.md) | Rendering supported declarative UI descriptions and emitting user actions |
| [protocol](protocol/README.md) | Hymio schemas, API contracts and generated client types |
| [client](client/README.md) | HTTP/WS communication, authentication integration and event synchronization |

Dependencies flow from apps into these packages. `ui` must not import an app or product service; `a2ui` may depend on `ui` and `protocol`; `client` may depend on `protocol`. Platform APIs are supplied through adapters. Backend contracts define business behavior.

`ui`, `protocol` and `client` are private pnpm workspace packages consumed by `apps/client`. They are not published. `a2ui` remains a design boundary until a real renderer is implemented.
