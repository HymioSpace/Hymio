# Hymio Client

One ongoing conversation, shared by Web and the Tauri macOS app. The client supports Hymio account login and direct Oath connections, including streamed replies, tool summaries, real approval cards, offline replay and an optional event/Trace inspector.

## Run

Requires Node.js 22.12+, pnpm 11 and a running Oath deployment. Desktop development also needs Rust and the platform dependencies listed in [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/).

Run from `apps/client` (pnpm discovers the workspace automatically):

```bash
cd apps/client
pnpm install
pnpm dev              # Web: http://127.0.0.1:1420
pnpm desktop          # Tauri; reuses a running Hymio dev server
```

Start Oath separately with `oath start`. Its installation, model setup and lifecycle are documented in [Oath](https://github.com/HymioSpace/Oath).

For account login, configure the [Hymio Backend](../../backend/README.md) and start Oath with remote authentication. Open **连接设置**, enter the Hymio Backend URL and choose **在浏览器中登录**. Web returns through its login popup; Desktop opens the system browser and receives the result through a temporary local callback. Access tokens refresh automatically; logout revokes the current login and clears the account view.

For direct local Oath, open **连接设置 → 直接连接 Oath**, choose **使用本机 Oath 配置**, then **连接 Hymio**. This reads only the user-facing WS/Biz addresses and one user credential from `~/.oath/oath.toml`. It does not expose model keys or internal service credentials. Local config loading is explicit, available in the desktop app and the loopback-only Web development server.

For another deployment, enter its WS URL, Biz HTTP URL and Oath user credential manually. Credentials stay in the current window's session; re-enter them after closing it. Endpoint preferences and received events persist locally, with events isolated by endpoint and authenticated user. In trusted Oath mode, provide a user ID and leave the credential empty. Connector credentials remain separate from product login.

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

The macOS `.app` is a local development build, not signed/notarized distribution. The desktop shell uses the same frontend, native local-profile loading and a restricted GET-only HTTP command for Biz health/trace paths. The shell does not start or stop Oath.

## HTTP routing

Logged-in clients connect directly to Oath WS and use the Backend Biz proxy for HTTP queries. Direct local Oath connections remain available. Its current Biz server has no browser CORS policy. Development Web proxies `/oath-biz` to the default local `127.0.0.1:8766`; desktop uses native HTTP.

A deployed Web build needs an application-origin reverse proxy or an explicit CORS policy on Biz. With a reverse proxy, enter `/oath-biz` as the Biz URL. If using HTTPS, expose Oath through WSS/HTTPS as well. `pnpm preview` serves static assets; it does not provide the development config reader or create a production backend.

## Boundaries

Received events are committed to IndexedDB before ACK. Commands are persisted with stable IDs and retried with the same payload after reconnect. Storage failure stops confirmation and shows an error; it is not treated as successful delivery.

History rendering is not virtualized or archived yet. Product sessions come from Hymio Backend; direct local connections use Oath configuration. Account credentials are retained only for the current window session. Nostalgia, connectors, attachments, voice, Kits and A2UI business rendering remain future work. The message component and shared package boundaries provide their integration points without exposing placeholder actions.
