"""Run as hymio-device with DISPLAY=:99 after copying controller.py beside this script."""

import base64
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "controller", Path(__file__).with_name("controller.py")
)
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def run(capability, **arguments):
    result = controller.execute(
        {"capability": capability, "arguments": arguments, "timeout": 20}
    )
    print(json.dumps({"capability": capability, "result": result}), flush=True)
    return result


with tempfile.TemporaryDirectory() as directory:
    Path(
        directory, "index.html"
    ).write_text("""<html><head><title>Hymio Cloud Desktop</title></head>
<body style="background:#f3f6fc;color:#172643;font-family:sans-serif;padding:72px">
<h1>Hymio cloud computer is ready.</h1><p>Bash / Browser / Computer Use</p>
<button onclick="this.textContent='Browser click verified'">Verify browser</button></body></html>""")
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8765", "--bind", "127.0.0.1"],
        cwd=directory,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1)
        assert server.poll() is None, "Test server failed to start"
        result = run("bash", command="id -un; pwd")
        assert result["exit_code"] == 0 and "hymio-device" in result["stdout"]
        result = run("browser", action="navigate", url="http://127.0.0.1:8765")
        assert result["title"] == "Hymio Cloud Desktop"
        result = run("browser", action="click", selector="button")
        assert "Browser click verified" in result["text"]
        run("computer", action="key", key="ctrl+l")
        run("computer", action="type", text="http://127.0.0.1:8765/?cua=verified")
        run("computer", action="key", key="Return")
        time.sleep(2)
        result = run("browser", action="snapshot")
        assert "cua=verified" in result["url"], (
            "GUI and browser did not share the active tab"
        )
        result = controller.execute(
            {
                "capability": "computer",
                "arguments": {"action": "screenshot"},
                "timeout": 10,
            }
        )
        capture = result["capture"]
        assert (capture["width"], capture["height"]) == (1280, 800)
        Path("/home/hymio-device/workspace/desktop-smoke.png").write_bytes(
            base64.b64decode(result["screenshot_base64"])
        )
        print(json.dumps({"verified": True, "capture": capture}), flush=True)
    finally:
        server.terminate()
        server.wait(timeout=5)
