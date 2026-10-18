# Hymio Client

One ongoing conversation, shared by Web and the Tauri macOS app. The client supports Hymio account login, including streamed replies, tool summaries, real approval cards, offline replay and an optional event/Trace inspector.

## Run

Requires Node.js 22.12+, pnpm 11 and a running Oath deployment. Desktop development also needs Rust and the platform dependencies listed in [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/).

Run from `apps/client` (pnpm discovers the workspace automatically):

```bash
cd apps/client
pnpm install
pnpm dev              # Web: http://127.0.0.1:1420
pnpm desktop          # Tauri; reuses a running Hymio dev server
```

Use the [stack launcher](../../deploy/README.md) to start Backend, Casdoor and Oath together. The client requires Hymio login; it has no direct Oath connection form or local credential reader.

Set the public Backend URL in `client.toml` before starting or building. It defaults to `http://localhost:8080` for local development; end users do not configure addresses. Credentials never belong in this file. Closing the client window clears its application session; events remain isolated by endpoint and authenticated user.

The initial screen offers account login/registration. A configured Google-only Casdoor application can enable **使用 Google 继续**, with first sign-in creating an account. See the [backend guide](../../backend/README.md). The frontend does not implement Google OAuth itself.

## Use

- Enter sends; Shift+Enter inserts a newline. Chinese IME composition does not send prematurely.
- Additional messages can be sent while the agent is working.
- The character breathes, blinks, waves on click and changes with actual working/replying/approval/connection states. Reduced-motion preferences are respected.
- Closing or disconnecting the client does not cancel accepted Oath work. Reconnect to receive saved events; drafts survive a page refresh.
- **工作观察** opens actual events, Trace spans/raw data, WS/Biz status, explicit retry and cancellation controls. Event export includes conversation content, but excludes connection credentials.
- Approval cards appear only when Oath emits real permission requests. Its current default allow-all policy does not produce them.

## Build

```bash
pnpm build            # dist/
pnpm desktop:build    # macOS .app under src-tauri/target/release/bundle/macos
pnpm check

# Shared checks, from the repository root:
cd ../..
pnpm format:check
pnpm test             # stream/approval projection regressions
```

The macOS `.app` is a local development build, not signed/notarized distribution. The desktop shell uses the same frontend, a restricted GET-only HTTP command for Biz health/trace paths. The shell does not start or stop Oath.

## HTTP routing

Logged-in clients connect to the WS endpoint supplied by Backend and use its authenticated `/oath-biz` proxy for HTTP queries. Web requires Backend's CORS allowlist to include the client origin. HTTPS deployments must provide WSS/HTTPS endpoints. `pnpm preview` serves static assets only; it does not start services.

## Boundaries

Received events are committed to IndexedDB before ACK. Commands are persisted with stable IDs and retried with the same payload after reconnect. Storage failure stops confirmation and shows an error; it is not treated as successful delivery.

History rendering is not virtualized or archived yet. Product sessions come only from Hymio Backend. Account credentials are retained only for the current window session. Nostalgia, connectors, attachments, voice, Kits and A2UI business rendering remain future work. The message component and shared package boundaries provide their integration points without exposing placeholder actions.
