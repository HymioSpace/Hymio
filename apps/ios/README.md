# Hymio for iOS

A native SwiftUI channel for your one continuous Hymio conversation. iOS 18+, built with Xcode 26.2.

- Account login and registration using the same Hymio backend as Web/Desktop.
- Streaming Markdown replies (headings, emphasis, lists, task lists, quotes, tables, links and fenced code with copy), compact tool details and independent approval cards.
- Authenticated screenshots, image expansion, older-history pagination.
- Per-account durable event cache, secure credentials in Keychain and command replay with stable IDs.
- Foreground reconnect, offline progress, account/device view and connection diagnostics.

Kits, personal context, uploads, voice input, push notifications and native phone control are not included.

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

For a remote deployment, copy `Config/Local.example.xcconfig` to ignored `Config/Local.xcconfig` and set your backend URL and bundle identifier. Do not enter keys or credentials there.

```xcconfig
HYMIO_BACKEND_URL = https:/$()/your-domain.example
PRODUCT_BUNDLE_IDENTIFIER = your.unique.hymio
```

For a local phone test you can use a LAN HTTP address in a **Debug** build; the server must be reachable from the phone. Release accepts HTTPS/WSS only. The backend public URL must be reachable. Login advertises chat at that same host’s `/agent/ws` and business APIs at `/oath-biz`; Oath upstream addresses stay internal.

Before TestFlight, deploy Hymio/Oath, configure HTTPS/WSS and account login, select your Apple team in Xcode, archive **Release** for a generic iOS device, and upload through Organizer. Never ship the default `invalid.example` endpoint. Signing and App Store Connect access are required; no certificates, provisioning profiles or account secrets are stored in this project.

The app uses only system encryption (TLS, Keychain and file protection). Verify App Store Connect's export compliance questions against the final build and distribution requirements.

### Install directly on your own iPhone

1. Connect the iPhone to the Mac by USB, unlock it and trust the Mac.
2. In Xcode Settings → Apple Accounts, sign in with your developer account.
3. Open `Hymio.xcodeproj`; in Hymio → Signing & Capabilities, enable automatic signing, choose your team and a unique bundle identifier.
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

Core models and projection are independently testable through Swift Package Manager. The Xcode project is checked in; no project generator is needed. Xcode resolves the pinned [MarkdownUI 2.4.1](https://github.com/gonzalezreal/swift-markdown-ui/releases/tag/2.4.1) package on the first build. Images use app-owned providers, with no credentials sent to external image hosts.

The privacy manifest declares app-scoped UserDefaults use for the installation ID ([Apple's required-reason API guidance](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype)). Complete the distribution privacy labels and privacy-policy URL for your actual backend: accounts and conversation content are sent to your deployment and model provider.
