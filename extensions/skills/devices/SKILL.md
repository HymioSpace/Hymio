---
name: devices
description: Choose an explicit device for Bash, browser and desktop actions.
---

There is one personal agent and one conversation. Clients are channels, not execution targets.
Call `devices` before executing. Use the exact device_id and required capability from its response.
An iPhone or Web client does not imply control of that phone or browser.
Keep the same target for a task. If it goes offline, report it; do not fall back to another computer.

`bash`, `browser`, `computer` all require device_id. The cloud desktop shares one browser profile,
filesystem and screen across these tools. Prefer browser DOM snapshots for web tasks.
GUI and shell operations on a device are serialized. A busy response means wait, not switch devices.
An outcome_unknown result may have side effects. Do not retry the action under a new invocation.
Use `device_command` with the original device_id and invocation_id to query a lost result.
Paused computers require explicit user resume; listing devices must never resume them.
Browser `tabs` returns stable page_id values. Specify page_id for multi-tab tasks.
Ask the user to recover or revoke the device. Never claim a screenshot was seen if only a media ID
was returned; visual reasoning requires a model/context adapter that supports images.

If no controllable device exists, direct the user to avatar → 我的设备 → 添加云电脑.
Wait for online, then refresh devices. Mac native control is not implemented; binding
a Mac or phone does not create an execution target. Never suggest otherwise.

For screenshots, use computer screenshot and include the returned screenshot.url in a Markdown
image. Do not invent a URL or use a sandbox /tmp path; those files are not public attachments.

Cloud desktops run Linux, not Windows/macOS. Microsoft Excel desktop is not available;
use LibreOffice Calc for .xlsx files, and verify installation with command -v libreoffice.
Do not assume sudo access. On E2B, check sudo -n true; if permitted, sudo may install
system packages inside that sandbox.
User-space packages can be installed in the workspace with a virtual environment.

Device provider is authoritative: e2b is the supported hosted cloud sandbox.
