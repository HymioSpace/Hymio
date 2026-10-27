# Hymio for iOS

A native SwiftUI channel for your one continuous Hymio conversation. iOS 18+, built with Xcode 26.2.

- Account login and registration using the same Hymio backend as Web/Desktop.
- Native interaction cards from the shared Hymio UI catalog, with explicit chat actions and presentation-only streaming buffers.
- Standalone Trace navigation with expandable JSON and continuously loaded records.
- Streaming Markdown replies (headings, emphasis, lists, task lists, quotes, tables, links and fenced code with copy), compact tool details and independent approval cards.
- Authenticated screenshots, image expansion, older-history pagination.
- Per-account durable event cache, secure credentials in Keychain and command replay with stable IDs.
- Foreground reconnect, offline progress, account/device management and connection diagnostics.
- Pair personal Mac/Android devices from Account, then pause, resume or revoke them there.
- A five-tab product shell with account settings behind a leading Companion avatar.
- Installed or generated React applications with bounded Python operations and an
  account-scoped `HymioKit.call` bridge.
- Per-application coding conversations with published version summaries.

The Memory tab (记忆) has understanding and original footprints, text search, direct text saving and an on-demand reference graph. See [memory space](../../spec/feature31-memory-space.md). Automated context collectors and health connectors are not included.

## Run locally

Start the local stack from the repository root:

```sh
hymio start --client web
```

Then:

```sh
bash apps/ios/scripts/run-simulator.sh
```

Or open `apps/ios/Hymio.xcodeproj`, select **Hymio** and an iPhone Simulator, and run.
Debug uses `http://127.0.0.1:8080` (the Mac's backend from Simulator). Sign up in the app or use your existing Hymio account. This client currently supports deployments with `login_method = "account"`; browser OIDC login is not yet implemented on iOS.

Each installation has its own delivery cursor. Backgrounding the app disconnects the socket without cancelling cloud work. Returning to the foreground refreshes credentials, restores the cache and synchronizes progress. This does not provide background execution or push delivery.

## Real iPhone / TestFlight

For a LAN Debug build, set `lan_host = "auto"` in the ignored repository file `deploy/local.toml`, then run `hymio restart --client web`. The launcher derives ignored `Config/Network.generated.xcconfig` from that single network configuration; do not edit the generated file. Debug uses it; Release does not. Signing settings stay unchanged. Select your Team in Xcode → Signing & Capabilities; there is no need to enter the same Team ID twice.

For a remote deployment, copy `Config/Local.example.xcconfig` to ignored
`Config/Local.xcconfig` and set the backend URL. Copy
`Config/LocalSigning.example.xcconfig` to ignored `Config/LocalSigning.xcconfig` and
set the bundle identifier and development team. Keeping signing overrides in this
separate file prevents Xcode from writing personal values into the committed project.
Remove the backend override to return to automatic LAN configuration. Do not enter
keys or credentials in either file.

```xcconfig
HYMIO_BACKEND_URL = https:/$()/your-domain.example
```

```xcconfig
HYMIO_APP_BUNDLE_IDENTIFIER = your.unique.hymio
HYMIO_DEVELOPMENT_TEAM = YOUR_TEAM_ID
```

For a local phone test you can use a LAN HTTP address in a **Debug** build; the server must be reachable from the phone. Release accepts HTTPS/WSS only. The backend public URL must be reachable. Login advertises chat at that same host’s `/agent/ws` and business APIs at `/oath-biz`; Oath upstream addresses stay internal.

Before TestFlight, deploy Hymio/Oath, configure HTTPS/WSS and account login, select your Apple team in Xcode, archive **Release** for a generic iOS device, and upload through Organizer. Never ship the default `invalid.example` endpoint. Signing and App Store Connect access are required; no certificates, provisioning profiles or account secrets are stored in this project.

The app uses only system encryption (TLS, Keychain and file protection). Verify App Store Connect's export compliance questions against the final build and distribution requirements.

### Install directly on your own iPhone

1. Connect the iPhone to the Mac by USB, unlock it and trust the Mac.
2. In Xcode Settings → Apple Accounts, sign in with your developer account.
3. Copy `Config/LocalSigning.example.xcconfig` to ignored
   `Config/LocalSigning.xcconfig`, then set your Team ID and unique bundle identifier there.
   Open `Hymio.xcodeproj` and keep automatic signing enabled.
4. Enable Developer Mode on the phone under Settings → Privacy & Security, following the restart prompt.
5. Select the iPhone as the run destination and press Run (⌘R). This installs a development build without TestFlight or App Store publication.

Installation does not make the backend reachable. If your phone is on another network, it needs a deployed server, a private VPN route or a properly secured HTTPS/WSS tunnel. Configure the backend public URL; its WebSocket proxy and business proxy share that public entry. Never expose internal queues, databases or service credentials through a tunnel.

See Apple's [physical-device run guide](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices) and [Developer Mode guide](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device).

## Verify

```sh
swift test --package-path apps/ios
xcodebuild -project apps/ios/Hymio.xcodeproj -scheme Hymio \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- test
```

The UI test registers a synthetic account against the configured local backend, chats twice across app termination/relaunch, and signs out. It requires the running stack and a working model configuration. The test revokes its own devices after running; generated accounts remain in the development identity provider. Automatically provisioned cloud computers use real deployment resources, so run against a development deployment.

The focused Kit bridge test installs the first-party ledger, writes from its Web page through WKWebView,
checks the same record through the authenticated business API, writes from the business API, and
reopens the page to verify the same data appears. It needs the local Backend and Kit Host but no
model call:

The Kit Host React build uses pinned local Node dependencies. Install them once:

```sh
npm ci --prefix services/kit-host/web
```

```sh
xcodebuild -project apps/ios/Hymio.xcodeproj -scheme Hymio \
  -destination 'platform=iOS Simulator,name=iPhone 16e' \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- \
  -only-testing:HymioUITests/HymioUITests/testKitWebBridgeAndBusinessDataSync test
```

Core models and projection are independently testable through Swift Package Manager. The Xcode project is checked in; no project generator is needed. Xcode resolves the pinned [MarkdownUI 2.4.1](https://github.com/gonzalezreal/swift-markdown-ui/releases/tag/2.4.1) package on the first build. Images use app-owned providers, with no credentials sent to external image hosts.

The privacy manifest declares app-scoped UserDefaults use for the installation ID ([Apple's required-reason API guidance](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype)). Complete the distribution privacy labels and privacy-policy URL for your actual backend: accounts and conversation content are sent to your deployment and model provider.

Archive checks the configured HTTPS backend before building. After changing an endpoint, create a new archive and upload a higher build number; an existing archive retains its original endpoint.

## TestFlight distribution

1. Deploy and verify the [HTTPS Backend](../../deploy/cloud/README.md). In ignored
   `Config/Local.xcconfig`, configure its HTTPS origin. Put your bundle identifier and
   Team ID in ignored `Config/LocalSigning.xcconfig`; never commit personal signing values.
2. Create the matching App in App Store Connect. Sign into Xcode's Apple Accounts and
   select your Team with automatic signing. Choose **Any iOS Device (arm64)**.
3. Set Version and a new Build number in Xcode. Info.plist derives these from
   `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION`; increment Build for every upload.
4. **Product → Archive** uses Release. Inspect the resulting archive's app Info.plist:
   `HymioBackendURL` must be the real HTTPS origin, not a placeholder or LAN address.
   `CFBundleVersion` must be the new build number. Old archives retain their original values.
5. In Organizer choose **Distribute App → App Store Connect → Upload**. A successful local
   archive is not an upload. Wait until Apple's processing completes in App Store Connect.
6. Under TestFlight, complete any requested compliance information, add this build to an
   internal testing group, and add your App Store Connect user as an internal tester.
7. On iPhone install TestFlight, accept the invitation, then install/update the correct
   build. Neither USB nor a shared LAN is required when the Backend is reachable remotely.

If a build is missing, first check upload success, Apple processing, compliance and group
assignment. Rebuilding locally never updates an already installed TestFlight binary.
If the app says the service is unconfigured, inspect the installed build's archive endpoint
and upload a corrected, higher build number. If signup settings cannot load, the login page
shows retry; invitation registration appears when Backend advertises it.

See [Apple's upload guide](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
and [internal tester guide](https://developer.apple.com/help/app-store-connect/test-a-beta-version/add-internal-testers/).

UI catalog, progressive rendering and model skill integration: [feature20](../../spec/feature20-progressive-ui.md). Run `testNativeSurfaceInteraction` only against a development Backend with open registration; it uses real model calls and may provision an E2B computer before cleanup.

## Memory UI previews

Debug includes synthetic, account-independent memory previews. Launch the built Simulator app
with `-HymioContextPreview`; add `-HymioContextEmptyPreview` for first use,
`-HymioContextDarkPreview` for dark appearance, or `-HymioContextLargeTextPreview` for
accessibility text size. These flags do not alter the real account or system appearance.
For actual persistence across clients, `backend/scripts/memory_preview.py` serves a loopback-only
synthetic Hymio/Nostalgia stack; the Web preview origin is restricted to `http://127.0.0.1:1422`.

Application previews use `-HymioKitAppPreview` for the WebView shell and
`-HymioKitEditorPreview` for the coding conversation and published version history.

## Connections

Calendar and HealthKit consent, signing and provider setup: [Connections](../../docs/connectors.md). Debug preview: `-HymioConnectorsPreview`. Native sync is manual/foreground in this release.
