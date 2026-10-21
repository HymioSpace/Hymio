"""Host-side execution and leases, independent of Hymio and HTTP transport."""

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

signal.signal(signal.SIGHUP, signal.SIG_IGN)

ROOT = Path.home() / ".local/state/hymio-device"
ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
PAUSED = ROOT / "paused"


def handle(data):
    with (ROOT / "execution.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            idle = True
        except BlockingIOError:
            idle = False
        action = data.get("action")
        if action == "status":
            ready = all(
                subprocess.run(
                    ["systemctl", "is-active", "--quiet", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                == 0
                for name in ("hymio-display", "hymio-desktop", "hymio-browser")
            )
            return {
                "state": "paused"
                if PAUSED.exists()
                else "online"
                if ready
                else "offline",
                "idle": idle,
            }
        if not idle:
            return {"rejected": "device_busy"}
        if action == "pause":
            PAUSED.touch(mode=0o600)
            return {"state": "paused"}
        if action == "resume":
            PAUSED.unlink(missing_ok=True)
            return {"state": "online"}
        if action != "execute":
            return {"error": "invalid_device_action"}
        if PAUSED.exists():
            return {"rejected": "device_paused"}
        request = data["request"]
        sys.path.insert(0, "/opt/hymio-device")
        from validation import validate

        validate(request["capability"], request["arguments"])
        timeout = request["timeout"]
        if type(timeout) not in (int, float) or not 0 < timeout <= 120:
            return {"rejected": "invalid_timeout"}
        remaining = data["deadline"] - time.time()
        if remaining <= 0:
            return {"rejected": "device_deadline_expired"}
        request["timeout"] = min(timeout, remaining)
        # A separate worker keeps the device lease even if the API connection is lost.
        worker = subprocess.run(
            [sys.executable, "/opt/hymio-device/device_worker.py"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
            pass_fds=(lock.fileno(),),
            env={**os.environ, "DISPLAY": ":99"},
        )
        if worker.returncode:
            return {"error": "device_execution_interrupted"}
        return {"result": json.loads(worker.stdout)}
