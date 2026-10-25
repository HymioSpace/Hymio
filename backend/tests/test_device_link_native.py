"""Opt-in native smoke: HYMIO_DEVICE_BINARY=/absolute/path/hymio-device pytest ..."""

import os
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
import uvicorn
from test_device_link import headers, stack  # noqa: F401


@pytest.mark.skipif(not os.environ.get("HYMIO_DEVICE_BINARY"), reason="native binary not selected")
def test_native_swift_proxy_executes_once(request, tmp_path):
    client, _ = request.getfixturevalue("stack")
    binary = str(Path(os.environ["HYMIO_DEVICE_BINARY"]).resolve())
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(client.app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    env = {**os.environ, "HYMIO_DEVICE_STATE_DIR": str(tmp_path / "link")}
    process = None
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        with httpx.Client(base_url=origin, timeout=10) as api:
            code = api.post("/devices/link/pairings", headers=headers(), json={}).json()["code"]
            paired = subprocess.run(
                [binary, "pair", "--server", origin],
                input=code + "\n",
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert paired.returncode == 0, paired.stderr
            process = subprocess.Popen(
                [binary, "run", "--headless", "--allow-shell"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            device = None
            for _ in range(100):
                devices = api.get("/devices", headers=headers()).json()["devices"]
                if devices and devices[0]["online"]:
                    device = devices[0]
                    break
                assert process.poll() is None, "Native Link exited early"
                time.sleep(0.1)
            assert device and "bash" in device["capabilities"]
            marker = tmp_path / "effect.txt"
            request = {
                "device_id": device["device_id"],
                "invocation_id": "native-smoke",
                "capability": "bash",
                "arguments": {"command": f"printf x >> '{marker}'; cat '{marker}'"},
                "timeout": 5,
            }
            first = api.post("/devices/execute", headers=headers(), json=request).json()
            assert first["status"] == "succeeded", first
            assert first["result"]["output"] == "x"
            second = api.post("/devices/execute", headers=headers(), json=request).json()
            assert second == first and marker.read_text() == "x"
            assert (
                api.get(
                    "/devices/" + device["device_id"] + "/commands/native-smoke", headers=headers()
                ).json()["status"]
                == "succeeded"
            )
            # Crash after a visible effect, then reconnect the real native proxy.
            interrupted = {
                **request,
                "invocation_id": "native-interrupted",
                "arguments": {"command": f"printf y >> '{marker}'; sleep 1"},
            }
            with ThreadPoolExecutor() as workers:
                pending = workers.submit(
                    api.post, "/devices/execute", headers=headers(), json=interrupted
                )
                for _ in range(100):
                    if marker.read_text() == "xy":
                        break
                    time.sleep(0.02)
                assert marker.read_text() == "xy"
                process.terminate()
                process.wait(timeout=5)
                process = subprocess.Popen(
                    [binary, "run", "--headless", "--allow-shell"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                assert pending.result().json()["status"] == "outcome_unknown"
                duplicate = api.post("/devices/execute", headers=headers(), json=interrupted).json()
                assert duplicate["status"] == "outcome_unknown"
                assert marker.read_text() == "xy"
    finally:
        if process:
            process.terminate()
            process.wait(timeout=5)
        # Remove this synthetic device's Keychain item; never touch normal Link state.
        subprocess.run([binary, "forget"], env=env, capture_output=True, timeout=10)
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
