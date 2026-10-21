#!/usr/bin/env bash
# Deploy host-side API. Input directory contains code, token, TLS leaf certificate and key.
set -euo pipefail
[[ $EUID == 0 && $# == 1 ]] || { echo 'Usage: sudo install-api.sh PAYLOAD_DIRECTORY' >&2; exit 1; }
base=$(cd -- "$1" && pwd)
/opt/hymio-device/bin/pip install 'starlette>=0.41,<1' 'uvicorn>=0.32,<1'
install -m 0644 "$base/device_api.py" "$base/device_runtime.py" "$base/device_worker.py" \
  "$base/controller.py" "$base/validation.py" /opt/hymio-device/
install -d -m 0750 -o root -g hymio-device /etc/hymio-device
install -m 0640 -o root -g hymio-device "$base/token" /etc/hymio-device/token
install -m 0640 -o root -g hymio-device "$base/server-key.pem" /etc/hymio-device/server-key.pem
install -m 0644 -o root -g root "$base/server.pem" /etc/hymio-device/server.pem
cat > /etc/systemd/system/hymio-device-api.service <<'UNIT'
[Unit]
Description=Hymio device HTTPS API
Requires=hymio-desktop.service
After=hymio-desktop.service network-online.target
[Service]
User=hymio-device
Group=hymio-device
WorkingDirectory=/home/hymio-device/workspace
Environment=HYMIO_DEVICE_TOKEN_FILE=/etc/hymio-device/token
Environment=PYTHONPATH=/opt/hymio-device
Environment=DISPLAY=:99
Environment=TMPDIR=/run/hymio-device-api
RuntimeDirectory=hymio-device-api
RuntimeDirectoryMode=0700
ExecStart=/opt/hymio-device/bin/python -m uvicorn device_api:app --host 0.0.0.0 --port 443 --ssl-keyfile /etc/hymio-device/server-key.pem --ssl-certfile /etc/hymio-device/server.pem --limit-concurrency 16 --timeout-keep-alive 5 --no-access-log
Restart=on-failure
RestartSec=3
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/home/hymio-device /run/hymio-device-api
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now hymio-device-api
systemctl restart hymio-device-api
