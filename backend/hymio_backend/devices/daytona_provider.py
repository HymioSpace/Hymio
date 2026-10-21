"""Daytona sandbox lifecycle with one persistent desktop/browser per product device."""

import base64
import io
import json
import math
import os
import shlex
import threading
import time

from .providers import (
    ComputerProvider,
    DeviceProfile,
    DispatchRejected,
    ProviderUnavailable,
    ProvisionRejected,
    controller_program,
)


class DaytonaComputer(ComputerProvider):
    profile = DeviceProfile(resolution=(1024, 768))

    def __init__(self, key_file=None, api_url="https://app.daytona.io/api", snapshot=""):
        self.key_file, self.api_url, self.snapshot = key_file, api_url, snapshot
        self._client = None
        self._lock = threading.Lock()

    def client(self):
        with self._lock:
            if self._client is None:
                from daytona import Daytona, DaytonaConfig

                key = (
                    self.key_file.read_text().strip()
                    if self.key_file
                    else os.environ.get("DAYTONA_API_KEY", "")
                )
                if not key:
                    raise ProvisionRejected("provider_not_configured")
                self._client = Daytona(
                    DaytonaConfig(api_key=key, api_url=self.api_url, use_deprecated_polling=True)
                )
            return self._client

    def connect(self, device, timeout=10):
        return self.client().get(device["provider_ref"], request_timeout=timeout)

    def recover(self, device):
        from daytona import DaytonaNotFoundError

        try:
            sandbox = self.client().get("hymio-" + device["id"], request_timeout=10)
        except DaytonaNotFoundError:
            return None
        self.prepare(sandbox)
        return sandbox.id

    def provision(self, device):
        from daytona import CreateSandboxFromSnapshotParams

        # Stable names let an uncertain create be recovered without repeating allocation.
        try:
            sandbox = self.client().create(
                CreateSandboxFromSnapshotParams(
                    name="hymio-" + device["id"],
                    snapshot=self.snapshot or None,
                    labels={"hymio_device_id": device["id"], "managed_by": "hymio"},
                    auto_stop_interval=20,
                    auto_archive_interval=0,
                    auto_delete_interval=-1,
                    public=False,
                ),
                timeout=90,
            )
        except Exception as error:
            from daytona import (
                DaytonaAuthenticationError,
                DaytonaAuthorizationError,
                DaytonaValidationError,
            )

            if isinstance(
                error,
                (DaytonaAuthenticationError, DaytonaValidationError, DaytonaAuthorizationError),
            ):
                raise ProvisionRejected("daytona_request_rejected") from None
            raise
        self.prepare(sandbox)
        return sandbox.id

    def prepare(self, sandbox):
        sandbox.computer_use.start(request_timeout=15)
        deadline = time.monotonic() + 45
        while sandbox.computer_use.get_status(request_timeout=5).status != "active":
            if time.monotonic() > deadline:
                raise ProviderUnavailable("desktop_start_timeout")
            time.sleep(0.5)
        script = """set -e
mkdir -p ~/workspace ~/browser ~/.hymio-runtime
if ! test -x ~/.hymio-runtime/bin/python; then
 python3 -m venv --system-site-packages ~/.hymio-runtime
fi
if ! ~/.hymio-runtime/bin/python -c 'import playwright' 2>/dev/null; then
 ~/.hymio-runtime/bin/pip -q install playwright
fi
if ! curl -fsS --max-time 2 http://127.0.0.1:9222/json/version >/dev/null; then
 BROWSER=$(command -v chromium || command -v chromium-browser || command -v google-chrome)
 DISPLAY=:0 nohup "$BROWSER" --no-sandbox --no-first-run --disable-quic \
 --disable-dev-shm-usage --remote-debugging-address=127.0.0.1 \
 --remote-debugging-port=9222 --user-data-dir="$HOME/browser" \
 --window-size=1024,768 --window-position=0,0 about:blank \
 > /tmp/hymio-browser.log 2>&1 </dev/null &
fi
"""
        result = sandbox.process.exec("bash -lc " + shlex.quote(script), timeout=45)
        if result.exit_code:
            raise ProviderUnavailable("desktop_initialization_failed")
        ready = """import urllib.request,time
for _ in range(40):
 try:
  urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=1).read();break
 except OSError:time.sleep(.25)
else:raise TimeoutError('Browser unavailable')
"""
        result = sandbox.process.exec("python3 -c " + shlex.quote(ready), timeout=15)
        if result.exit_code:
            raise ProviderUnavailable("browser_start_timeout")

    def state(self, device):
        from daytona import DaytonaNotFoundError

        try:
            sandbox = self.connect(device)
        except DaytonaNotFoundError:
            return "missing"
        except Exception:
            raise ProviderUnavailable("daytona_unavailable") from None
        state = str(getattr(sandbox.state, "value", sandbox.state)).lower()
        if state == "started":
            return "online"
        if state in ("stopped", "archived"):
            return "paused"
        return "offline"

    def inspect(self, device):
        return self.state(device) == "online"

    def execute(self, device, request, timeout):
        started = time.monotonic()
        sandbox = self.connect(device, timeout=min(10, timeout))
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise DispatchRejected("device_deadline_expired")
        if request["capability"] == "computer":
            return self.computer(sandbox, request["arguments"], remaining)
        program = controller_program(
            {**request, "timeout": remaining}, expires_at=time.time() + remaining
        )
        command = "DISPLAY=:0 ~/.hymio-runtime/bin/python -c " + shlex.quote(program)
        result = sandbox.process.exec(command, timeout=max(1, math.ceil(remaining)))
        if result.exit_code:
            raise ProviderUnavailable("device_execution_interrupted")
        return json.loads(result.result)

    def computer(self, sandbox, args, timeout):
        cu = sandbox.computer_use
        action = args["action"]
        if action == "screenshot":
            from PIL import Image

            from .desktop_controller import image_result

            raw = base64.b64decode(
                cu.screenshot.take_full_screen(request_timeout=timeout).screenshot
            )
            with Image.open(io.BytesIO(raw)) as image:
                output = io.BytesIO()
                image.save(output, format="PNG")
            return image_result(output.getvalue(), "desktop")
        if action == "click":
            display = cu.display.get_info(request_timeout=min(timeout, 5)).displays[0]
            if not 0 <= args["x"] < display.width or not 0 <= args["y"] < display.height:
                raise DispatchRejected("invalid_coordinate")
            cu.mouse.click(args["x"], args["y"], request_timeout=timeout)
        elif action == "type":
            cu.keyboard.type(args["text"], request_timeout=timeout)
        elif action == "key":
            cu.keyboard.hotkey(args["key"], request_timeout=timeout)
        elif action == "scroll":
            amount = args.get("amount", 3)
            cu.mouse.scroll(
                512, 384, "down" if amount > 0 else "up", abs(amount), request_timeout=timeout
            )
        else:
            raise DispatchRejected("invalid_action")
        return {"performed": action}

    def execution_idle(self, device):
        # The remote controller enforces its own deadline. This is checked only after the
        # local lock has expired with grace, so a responsive sandbox means the bounded command
        # has ended. Probe without repeating the original operation.
        try:
            result = self.connect(device, timeout=5).process.exec("true", timeout=5)
            return result.exit_code == 0 and self.state(device) == "online"
        except Exception:
            return False

    def pause(self, device):
        self.connect(device).stop(timeout=45)

    def resume(self, device):
        sandbox = self.connect(device)
        sandbox.start(timeout=60)
        self.prepare(sandbox)

    def stop(self, device):
        from daytona import DaytonaNotFoundError

        try:
            self.connect(device).delete(timeout=60, wait=True)
        except DaytonaNotFoundError:
            pass
