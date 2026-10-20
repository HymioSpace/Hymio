"""Desktop providers execute the same controller inside the target environment."""

import json
import shlex
import time
from abc import ABC, abstractmethod
from pathlib import Path

CONTROLLER = Path(__file__).with_name("desktop_controller.py").read_text()


def controller_program(request, expires_at=None):
    return (
        "import json\n"
        + CONTROLLER
        + (
            f"\ntry:\n    request = {request!r}\n"
            + (
                f"    remaining = {expires_at!r} - time.time()\n"
                "    if remaining <= 0: raise OperationRejected('Dispatch deadline expired')\n"
                "    request['timeout'] = min(request['timeout'], remaining)\n"
                if expires_at is not None
                else ""
            )
            + "    print(json.dumps(execute(request)))\n"
            "except OperationRejected as error:\n"
            "    print(json.dumps({'operation_rejected': str(error)}))\n"
        )
    )


class ComputerProvider(ABC):
    @abstractmethod
    def provision(self, device): ...

    @abstractmethod
    def inspect(self, device): ...

    @abstractmethod
    def execute(self, device, request, timeout): ...

    @abstractmethod
    def stop(self, device): ...

    def state(self, device):
        return "online" if self.inspect(device) else "offline"

    @abstractmethod
    def execution_idle(self, device): ...

    @abstractmethod
    def pause(self, device): ...

    @abstractmethod
    def resume(self, device): ...


class E2BComputer(ComputerProvider):
    def __init__(self, key_file, template):
        self.key_file, self.template = key_file, template

    def connect(self, device, *, request_timeout=10):
        from e2b_desktop import Sandbox

        if not device["provider_ref"]:
            raise ValueError("Desktop not provisioned")
        return Sandbox.connect(
            device["provider_ref"],
            timeout=3600,
            api_key=self.key_file.read_text().strip(),
            request_timeout=request_timeout,
        )

    def provision(self, device):
        from e2b_desktop import Sandbox

        if device["provider_ref"]:
            self.connect(device)
            return device["provider_ref"]
        desktop = Sandbox.create(
            template=self.template,
            timeout=3600,
            lifecycle={"on_timeout": "pause", "auto_resume": False},
            resolution=(1280, 800),
            metadata={"hymio_device_id": device["id"]},
            request_timeout=40,
            api_key=self.key_file.read_text().strip(),
        )
        try:
            desktop.commands.run("mkdir -p ~/workspace ~/browser", timeout=10)
            desktop.commands.run(
                "/opt/hymio/bin/python -m http.server 8000 --bind 127.0.0.1 "
                '--directory "$HOME/workspace"',
                background=True,
                timeout=0,
            ).disconnect()
            desktop.commands.run(
                "google-chrome --no-sandbox --no-first-run --remote-debugging-address=127.0.0.1 "
                "--remote-debugging-port=9222 --user-data-dir=$HOME/browser --window-size=1280,800 "
                "about:blank >/tmp/hymio-chrome.log 2>&1",
                envs={"DISPLAY": ":0"},
                background=True,
                timeout=0,
            ).disconnect()
            ready = """import time,urllib.request
for attempt in range(50):
    try:
        urllib.request.urlopen('http://127.0.0.1:9222/json/version',timeout=1).read()
        break
    except OSError:
        time.sleep(.2)
else:
    raise TimeoutError('Browser unavailable')
"""
            desktop.commands.run("/opt/hymio/bin/python -c " + shlex.quote(ready), timeout=20)
        except Exception:
            desktop.kill()
            raise
        return desktop.sandbox_id

    def inspect(self, device):
        return self.state(device) == "online"

    def state(self, device):
        from e2b import Sandbox, SandboxNotFoundException

        try:
            info = Sandbox.get_info(
                device["provider_ref"], api_key=self.key_file.read_text().strip(), request_timeout=5
            )
            return "paused" if info.state.value == "paused" else "online"
        except SandboxNotFoundException:
            return "missing"
        except Exception:
            return "offline"

    def pause(self, device):
        from e2b import Sandbox

        paused = Sandbox.pause(
            device["provider_ref"],
            mode="full",
            api_key=self.key_file.read_text().strip(),
            request_timeout=30,
        )
        if not paused:
            raise RuntimeError("Sandbox could not pause")

    def resume(self, device):
        from e2b import Sandbox

        return Sandbox.connect(
            device["provider_ref"],
            timeout=3600,
            api_key=self.key_file.read_text().strip(),
            request_timeout=30,
        )

    def execution_idle(self, device):
        sandbox = self.connect(device)
        processes = sandbox.commands.list(request_timeout=5)
        return not any("class OperationRejected" in " ".join([p.cmd, *p.args]) for p in processes)

    def execute(self, device, request, timeout):
        deadline = time.monotonic() + timeout
        sandbox = self.connect(device, request_timeout=min(5, timeout))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Execution deadline expired before dispatch")
        request = {**request, "timeout": min(request["timeout"], remaining)}
        program = controller_program(request, expires_at=time.time() + remaining)
        command = f"timeout -k 1s {remaining + 1}s /opt/hymio/bin/python -c " + shlex.quote(program)
        return json.loads(
            sandbox.commands.run(
                command,
                envs={"DISPLAY": ":0"},
                timeout=remaining + 2,
                request_timeout=remaining + 2,
            ).stdout
        )

    def stop(self, device):
        from e2b import Sandbox, SandboxNotFoundException

        try:
            Sandbox.kill(
                device["provider_ref"],
                api_key=self.key_file.read_text().strip(),
                request_timeout=10,
            )
        except SandboxNotFoundException:
            pass
