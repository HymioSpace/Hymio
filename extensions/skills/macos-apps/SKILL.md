---
name: macos-apps
description: Use applications on a personal Mac, including Codex.
---

# Mac applications

Use `oath-cli devices` to find the personal Mac. Inspect the current screen with
`oath-cli computer --device-id ID --action screenshot`, then use the computer CLI for click,
type, key and scroll. macOS shortcuts use cmd. Browser web work can use the browser CLI with
its own Chromium profile and DOM selectors; it does not require AppleScript permissions.

With Bash enabled, `open -a 'Codex'` opens the application. Observe before entering text and
verify the result afterward. The Codex application workflow is in references/codex.md; its
computer actions are invoked with oath-cli, and statuses come from `oath-cli status ID`.
