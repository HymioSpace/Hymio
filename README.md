# Hymio

**Your personal AI agent, in tune with you.**

Hymio is the application layer of [HymioSpace](https://github.com/HymioSpace). It brings the agent, personal context, connectors and everyday applications into one experience across desktop, web, iOS and Chrome.

[Oath](https://github.com/HymioSpace/Oath) runs the agent. [Nostalgia](https://github.com/HymioSpace/Nostalgia) manages personal context. Hymio owns the product: accounts, authorization, imports and sync, Kits, clients and deployment.

**Status:** Web/Tauri client MVP. Connect to a running Oath deployment for one persistent conversation, streamed replies, offline replay and event/Trace inspection. The OIDC login backend is available; A local stack launcher is available; Nostalgia integration remains future work. A single-host cloud deployment entry is available; production rollout still requires domain, identity and network setup.

<p align="center"><img src="apps/client/assets/welcome.png" alt="Hymio client: a single conversation, an animated line companion and a focused message composer." width="960" /></p>

## iOS preview

Start with Now for task progress, continue the shared conversation, or open Tasks and Account. iOS uses four native tabs; Web uses a labelled sidebar and a wider task inspector.

The native SwiftUI client lives in [apps/ios](apps/ios/README.md). It supports the same account and continuous conversation as Web/Desktop, streaming replies, tool approvals, screenshots and foreground reconnection.

```sh
hymio start --client web
bash apps/ios/scripts/run-simulator.sh
```

Use Xcode 26.2 and an iPhone Simulator. Configure your deployed HTTPS backend and signing team before device/TestFlight distribution; see the [iOS guide](apps/ios/README.md).

## One product, several clients

Web and the Tauri desktop app share one frontend. Chrome can reuse shared web components and protocol packages while keeping its own background tasks and permissions. iOS has a separate platform implementation within the same repository.

A user has one ongoing agent conversation across clients. Closing a client does not end work accepted by Oath; reconnecting clients receive persisted progress. Context and Kit data are shared through their service APIs.

Account settings now manage devices and a cloud desktop. Bash, browser DOM automation and desktop
controls share one configured cloud environment, with an explicit execution device and independent message
delivery cursors per client window. Cloud desktops support Daytona, legacy E2B and operator-managed Linux ECS over HTTPS API. New users have no cloud resources until an administrator grants access; see [resource administration](deploy/README.md#cloud-resources-and-administration).
See the [computer environment guide](deploy/computer/README.md) for setup and current limits.
Conversations open from a recent snapshot, with earlier messages loaded on demand and live events delivered from the snapshot checkpoint.
Cloud desktops can be paused and resumed from device settings. Recent operations are queryable
without replaying commands, and browser tools support explicit tabs and navigation history.

## Repository

| Directory | Responsibility |
| --- | --- |
| [apps/client](apps/client/README.md) | Shared web frontend and Tauri desktop shell |
| [apps/admin](apps/admin) | Standalone operator console for cloud resources and future operations |
| [apps/chrome](apps/chrome/README.md) | Browser extension, page capture and background tasks |
| [apps/ios](apps/ios/README.md) | iOS client and native platform capabilities |
| [packages](packages/README.md) | Shared UI, A2UI rendering, protocols and client communication |
| [backend](backend/README.md) | Accounts, authorization, connectors, context ingress and product APIs |
| [extensions](extensions/README.md) | Hymio-specific Oath skills, tools and CLI commands |
| [kits](kits/README.md) | Applications that expose operations to agents and experiences to users |
| [deploy](deploy/README.md) | Product deployment and dependency composition |
| [spec](spec/README.md) | Architecture and feature designs |

Apps and services may build and release independently. Sharing a repository does not require sharing platform-specific UI or deploying every module as a separate service.
The operator console is a separate application at `/admin/`; it is not part of the user Web
navigation and can evolve independently from the product clients.

## Runtime and context

Oath and Nostalgia remain independent projects. Integrate through their public protocols and versioned artifacts; keep their core implementations out of Hymio. No Git submodules are required by this scaffold.

Hymio's deployment layer starts the local backend, Casdoor and Oath; Nostalgia remains future work. Clients connect to the configured services. The current Oath command already accepts external extension directories; Hymio provides the directories in [extensions](extensions/README.md).

## Start here

For a local stack, install Docker, uv, Node.js and pnpm, and install Oath from the adjacent
[Oath checkout](https://github.com/HymioSpace/Oath). Then run from this repository:

```bash
bash scripts/hymio-install
hymio init                         # Hidden prompt: MiniMax API key; configure your cloud host separately
hymio start --timeout 900
# Desktop instead: --client desk; services only: --client none
```

**One private file: `~/.hymio/config.toml`.** Edit it for model choices, optional invitation codes,
Casdoor port or LAN access. Copy it to another computer for a fresh installation; internal
credentials and Casdoor configuration initialize automatically. Existing accounts/history require
a separate data migration. See the [setup and migration guide](deploy/README.md#first-run-one-private-configuration)
for key links, required fields and compatibility with existing configurations.

The launcher starts Casdoor, Backend and Oath before the chosen development client.
`hymio status`, `hymio logs -f`, `hymio stop` and `hymio restart` manage the local stack. Stop leaves Oath/Casdoor and accepted Agent work running.
`hymio doctor` prints which configuration files are editable inputs and which are generated.

### Client only

Requires Node.js 22.12+, pnpm 11 and a configured Hymio Backend with its Oath services running, then:

```bash
git clone https://github.com/HymioSpace/Hymio.git
cd Hymio/apps/client
pnpm install
pnpm dev       # Web: http://127.0.0.1:1420
# Or, with Rust and Tauri platform prerequisites:
pnpm desktop
```

Follow the [backend guide](backend/README.md) to configure account registration or Google login. The client opens a dedicated sign-in screen; deployment addresses are configured by the operator in `apps/client/client.toml`, never entered by end users. Oath keeps executing accepted work when the client leaves.

Read the [client guide](apps/client/README.md) for builds, debug controls and production Web routing. React/TypeScript/Vite and Tauri 2 share the frontend. The Python backend integrates Casdoor through standard OIDC.

See the [overview](spec/overview.md), [client design](spec/feature07-client-mvp.md) and the [feature plans](spec/README.md) for module boundaries.

Shared development conventions live in `spec/README.md`. Local `AGENTS.md`, credentials, private extensions and runtime data are ignored by Git.

## Cloud hosting

Use the [cloud deployment guide](deploy/cloud/README.md) for static Web, containerized Backend and automatic HTTPS. Cloud computers use the configured provider; Oath and OIDC remain independent services. The first deployment uses one Backend instance with persistent SQLite storage.

### Progressive interaction surfaces

Web/Desk and native iOS render the same limited Hymio UI catalog: cards, metrics, text, choices, inputs and explicit message buttons. Streamed prose is buffered independently of durable events; UI records reveal as valid nodes arrive. See [the contract](spec/feature20-progressive-ui.md) and [model skill](extensions/skills/hymio-ui/SKILL.md). This is a focused native subset inspired by json-render, not arbitrary generated React execution or full Google A2UI compatibility.

Hymio's [application instructions](extensions/prompts/hymio.md) load through Oath's
`--system-prompt` option. The local launcher passes this file automatically; update Oath before
using the launcher. Role and style stay in a fixed prefix, while device state comes from tools.
See [prompt and computer recovery](spec/feature21-prompt-computer-recovery.md).

### Models and media

Choose the conversation model in Settings without creating another conversation. Attach photos, documents or audio; Hymio uses its media tools to understand them on demand. iOS supports Photos, Camera and Files. Image creation supports text prompts and MiniMax character references, with generated images kept as private attachments. See [setup](deploy/README.md#models-and-attachments), [design](spec/feature22-models-and-media.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

### Work that carries on

Ask naturally: compare two offers, investigate a problem, or prepare a document. Hymio is prompted
to keep accepted work in a shared task list, with intermediate findings, blockers, next steps and final
results. Recording current work does not schedule it a second time. You can also arrange future work
or a daily/weekly routine. The agent can work directly or delegate a bounded independent expert;
Web/Desktop and iOS show the same records, within one continuing conversation.
[Tasks and delegation](spec/feature23-tasks-and-delegation.md) describes the execution boundaries.
