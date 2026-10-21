#!/usr/bin/env bash
# Dedicated Ubuntu cloud desktop. Run as root; execution runs as an unprivileged user.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends xfce4-session xfwm4 xfce4-panel xfdesktop4 \
  xfce4-terminal dbus-x11 xvfb xdotool scrot python3-venv curl ca-certificates \
  fonts-noto-cjk fonts-noto-color-emoji
id hymio-device &>/dev/null || useradd --create-home --shell /bin/bash hymio-device
install -d -o hymio-device -g hymio-device /home/hymio-device/workspace /home/hymio-device/browser
python3 -m venv /opt/hymio-device
/opt/hymio-device/bin/pip install 'playwright==1.61.0'
/opt/hymio-device/bin/playwright install-deps chromium
if [[ -n ${CHROMIUM_ARCHIVE:-} ]]; then
  /opt/hymio-device/bin/python - "$CHROMIUM_ARCHIVE" <<'PYZIP'
import sys, zipfile
from pathlib import Path
root = Path('/opt/hymio-device/chromium')
with zipfile.ZipFile(sys.argv[1]) as archive:
    for item in archive.infolist():
        target = (root / item.filename).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Invalid archive path')
    archive.extractall(root)
    for item in archive.infolist():
        mode = item.external_attr >> 16
        if mode:
            (root / item.filename).chmod(mode & 0o777)
PYZIP
else
  runuser -u hymio-device -- /opt/hymio-device/bin/playwright install chromium
fi
cat > /etc/systemd/system/hymio-display.service <<'UNIT'
[Unit]
Description=Hymio virtual display
After=network.target
[Service]
User=hymio-device
ExecStart=/usr/bin/Xvfb :99 -screen 0 1280x800x24 -nolisten tcp -noreset
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/hymio-desktop.service <<'UNIT'
[Unit]
Description=Hymio desktop session
Requires=hymio-display.service
After=hymio-display.service
[Service]
User=hymio-device
Environment=DISPLAY=:99
Environment=HOME=/home/hymio-device
WorkingDirectory=/home/hymio-device
ExecStartPre=/bin/sh -c 'until /usr/bin/xdotool getdisplaygeometry >/dev/null 2>&1; do sleep 0.2; done'
ExecStart=/usr/bin/dbus-run-session -- /usr/bin/xfce4-session
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
cat > /opt/hymio-device/browser.py <<'PY'
import signal
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        '/home/hymio-device/browser', headless=False,
        executable_path='/opt/hymio-device/chromium/chrome-linux64/chrome'
        if Path('/opt/hymio-device/chromium/chrome-linux64/chrome').exists() else None,
        no_viewport=True, args=['--remote-debugging-address=127.0.0.1',
        '--remote-debugging-port=9222', '--window-size=1280,800', '--window-position=0,0'])
    if not context.pages:
        context.new_page()
    while not stop.is_set():
        context.pages[0].wait_for_timeout(500) if context.pages else context.new_page()
    context.close()
PY
cat > /etc/systemd/system/hymio-browser.service <<'UNIT'
[Unit]
Description=Hymio persistent desktop browser
Requires=hymio-desktop.service
After=hymio-desktop.service network-online.target
[Service]
User=hymio-device
Environment=DISPLAY=:99
Environment=HOME=/home/hymio-device
WorkingDirectory=/home/hymio-device/workspace
ExecStart=/opt/hymio-device/bin/python /opt/hymio-device/browser.py
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now hymio-display hymio-desktop hymio-browser
