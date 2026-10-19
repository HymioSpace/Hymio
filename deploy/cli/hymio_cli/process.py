"""Identify only our launcher, never a process based on an occupied port."""

import json
import os
import re
import signal
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen


def alive(state):
    if not state:
        return False
    try:
        pid = int(state["pid"])
        if pid < 2 or not re.fullmatch(r"[a-f0-9]{32}", state.get("instance", "")):
            return False
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            text=True,
            check=False,
        )
        return (
            result.returncode == 0
            and state["instance"] in result.stdout
            and "deploy/start.py" in result.stdout
        )
    except (KeyError, ValueError, OSError):
        return False


def endpoint(url, marker=None):
    try:
        with urlopen(url, timeout=2) as response:
            content = response.read(65536).decode(errors="replace")
            return response.status == 200 and (marker is None or marker in content)
    except (OSError, URLError):
        return False


def health(client):
    backend = endpoint("http://127.0.0.1:8080/health", '"alive":true')
    web = client == "none" or endpoint("http://127.0.0.1:1420", "<title>Hymio")
    return backend, web


def save(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def stop(state):
    if not alive(state):
        return
    os.killpg(state["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 20
    while alive(state) and time.monotonic() < deadline:
        time.sleep(0.2)
    if alive(state):
        raise RuntimeError(
            "Launcher has not stopped; inspect logs before retrying. No unrelated process was killed."
        )
