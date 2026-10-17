# Hymio

**Your personal AI agent, in tune with you.**

Hymio is the application layer of [HymioSpace](https://github.com/HymioSpace). It brings the agent, personal context, connectors and everyday applications into one experience across desktop, web, iOS and Chrome.

[Oath](https://github.com/HymioSpace/Oath) runs the agent. [Nostalgia](https://github.com/HymioSpace/Nostalgia) manages personal context. Hymio owns the product: accounts, authorization, imports and sync, Kits, clients and deployment.

**Status:** repository scaffolding and design. There is no runnable Hymio application or combined deployment yet. Oath can be deployed separately; Nostalgia integration is planned.

## One product, several clients

Web and the Tauri desktop app share one frontend. Chrome can reuse shared web components and protocol packages while keeping its own background tasks and permissions. iOS has a separate platform implementation within the same repository.

A user has one ongoing agent conversation across clients. Closing a client does not end work accepted by Oath; reconnecting clients receive persisted progress. Context and Kit data are shared through their service APIs.

## Repository

| Directory | Responsibility |
| --- | --- |
| [apps/client](apps/client/README.md) | Shared web frontend and Tauri desktop shell |
| [apps/chrome](apps/chrome/README.md) | Browser extension, page capture and background tasks |
| [apps/ios](apps/ios/README.md) | iOS client and native platform capabilities |
| [packages](packages/README.md) | Shared UI, A2UI rendering, protocols and client communication |
| [backend](backend/README.md) | Accounts, authorization, connectors, context ingress and product APIs |
| [extensions](extensions/README.md) | Hymio-specific Oath skills, tools and CLI commands |
| [kits](kits/README.md) | Applications that expose operations to agents and experiences to users |
| [deploy](deploy/README.md) | Product deployment and dependency composition |
| [spec](spec/README.md) | Architecture and feature designs |

Apps and services may build and release independently. Sharing a repository does not require sharing platform-specific UI or deploying every module as a separate service.

## Runtime and context

Oath and Nostalgia remain independent projects. Integrate through their public protocols and versioned artifacts; keep their core implementations out of Hymio. No Git submodules are required by this scaffold.

Hymio's deployment layer will compose the backend, Oath and Nostalgia. Clients connect to the configured services. The current Oath command already accepts external extension directories; Hymio provides the directories in [extensions](extensions/README.md).

## Start here

```bash
git clone https://github.com/HymioSpace/Hymio.git
cd Hymio
```

Read the [overview](spec/overview.md), [repository design](spec/feature06-application-monorepo.md) and the relevant [feature plan](spec/README.md). There is no dependency installation or application start command yet. Frontend build tooling, backend framework and authentication provider will be selected with the first implementations.

Shared development conventions live in `spec/README.md`. Local `AGENTS.md`, credentials, private extensions and runtime data are ignored by Git.
