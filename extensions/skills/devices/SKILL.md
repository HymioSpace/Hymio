---
name: devices
description: Choose an explicit device for Bash, browser and desktop actions.
---

There is one personal agent and one conversation. Clients are channels, not execution targets.
Call `devices` before executing. Use the exact device_id and required capability from its response.
An iPhone or Web client does not imply control of that phone or browser.
Keep the same target for a task. Refresh devices if unavailable; inspect binding notices before using a new target.
A replacement is empty, so do not assume files or applications from the deleted computer survived.

`bash`, `browser`, `computer` all require device_id. The cloud desktop shares one browser profile,
filesystem and screen across these tools. Prefer browser DOM snapshots for web tasks.
GUI and shell operations on a device are serialized. A busy response means wait, not switch devices.
An outcome_unknown result may have side effects. Do not retry the action under a new invocation.
Use `device_command` with the original device_id and invocation_id to query a lost result.
The devices tool ensures a usable cloud computer and may resume or provision one.
Passive UI list polling is read-only. Device preparation never replays a previous command.
Browser `tabs` returns stable page_id values. Specify page_id for multi-tab tasks.
For blocked/unknown executions, report the condition rather than repeat effects. A browser or
computer screenshot result contains `screenshot.media_id` (also exposed as
`screenshot.attachment_id`). Pass that ID directly to `multimodal_understand`; it can resolve
device screenshots and user attachments. Do not pass `/devices/media/...`, `page_id` or
`device_id` as the media ID, and do not download and re-upload the screenshot just to inspect it.
Never claim a screenshot was seen until multimodal analysis or an image-capable context confirms it.

Cloud computers are bound automatically only for users granted access by an administrator.
If resource_access_denied or capacity exhaustion is returned, explain it and stop; do not retry
creation or repair account permissions. Do not ask authorized users to manually create a computer. If binding says preparing, wait then call devices again. Provider
outages are not grounds to destroy an existing environment. Mac native control is not implemented.

For a web-page screenshot, use browser(action="screenshot", page_id="...") with the selected
page_id from tabs or navigation. It captures that page even if another desktop window is in front.
Use computer screenshot only for the entire visible desktop. Check capture.kind, page_id and URL
before describing what was captured. Do not switch windows by activating every Chrome match.
Include the returned screenshot.url in a Markdown
image. Do not invent a URL or use a sandbox /tmp path; those files are not public attachments.

Cloud desktops run Linux, not Windows/macOS. Microsoft Excel desktop is not available;
use LibreOffice Calc for .xlsx files, and verify installation with command -v libreoffice.
Do not assume sudo access. On E2B, check sudo -n true; if permitted, sudo may install
system packages inside that sandbox.
User-space packages can be installed in the workspace with a virtual environment.

Device provider is authoritative: Daytona, legacy E2B, or an operator-managed HTTPS device API.
Do not assume SSH, sudo, a particular image or applications are available.
If binding reports retry_after_seconds or a provider error, stop and explain it. Backend owns
recovery and backoff; do not poll repeatedly or attempt to repair credentials, quota or networking.
