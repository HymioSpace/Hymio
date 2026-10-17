# Server-side channels

Adapters for Slack and other external messaging services. Verify source identity and callback signatures, map accounts to Hymio users, and preserve stable input/delivery identities.

Reuse the same agent integration as first-party clients. Group-channel output needs its own authorization; a private user conversation is not automatically safe to mirror into a shared channel. See [feature02](../../spec/feature02-agent-channels.md).
