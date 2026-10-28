---
name: devices
description: Choose a device and use its Bash, browser or desktop capabilities.
---

# Devices

Run `oath-cli devices` to inspect owned devices and current capabilities. Bash defaults to an
online personal Mac; supply device_id when choosing another target. Related operations should
stay on that device because its files, browser profile and desktop belong to it.

Read `oath-cli help browser` or `oath-cli help computer` for the current action schema.

```sh
oath-cli browser --device-id DEVICE_ID --action tabs
oath-cli browser --device-id DEVICE_ID --action snapshot --page-id PAGE_ID
oath-cli computer --device-id DEVICE_ID --action screenshot
```

The Mac browser uses a separate Chromium profile. Pick a returned page_id for multi-tab work.
DOM snapshots provide selectors for click/fill; desktop actions use coordinates from a current
screenshot. A browser screenshot captures its page; a desktop screenshot captures the visible
screen. Use returned media references rather than inventing URLs.

Only call advertised capabilities. Android personal devices expose computer actions including
swipe; conversation-only phones are not controllable devices. Read android-phone or macos-apps
for platform workflows. Status for every invocation is `oath-cli status INVOCATION_ID`, from
Oath ToolSystem, regardless of the target device.
