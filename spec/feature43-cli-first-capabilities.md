# CLI-first capabilities

Status: Implemented

## Overview

Hymio exposes Bash and Skill as native tools. Devices, browsing, desktop control, tasks, media,
notifications, context, applications and delegation are discovered and invoked through oath-cli.
Oath ToolSystem owns every execution and its status; device command recovery remains internal.

Personal Macs with an online Bash capability are preferred over cloud desktops. Device discovery
is read-only. Selecting a fallback is explicit in the returned execution target; a running task
keeps its device. Cloud preparation is only needed when the chosen target requires it.

Hymio proxies the cloud CLI transport under the configured public origin. The device receives
short-lived execution credentials outside persisted arguments, installs a hash-verified client
in its own user directory and reuses it until the expected version changes. Service credentials
never enter the device. Parent-bound child device actions can share a Bash orchestration lease;
unrelated actions remain serialized.

Prompts contain role, capabilities and concise shell-composition guidance. Skills document CLI
usage progressively. The operator prompt page renders the same configured Markdown assembled by
Oath, identifies its fingerprint and channel, and distinguishes it from per-user context data.
