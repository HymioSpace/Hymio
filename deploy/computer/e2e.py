"""Verify device ownership, execution, DOM/desktop sharing and persistence via HTTP."""

import argparse
import secrets
import shlex
import time
import uuid

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    with httpx.Client(base_url=args.backend, timeout=140, trust_env=False) as client:

        def signup():
            response = client.post(
                "/auth/account",
                json={
                    "action": "signup",
                    "username": "device_" + secrets.token_hex(5),
                    "password": secrets.token_urlsafe(24),
                },
            )
            response.raise_for_status()
            return {"Authorization": "Bearer " + response.json()["access_token"]}

        owner, other = signup(), signup()

        def post(path, data, headers=owner):
            response = client.post(path, json=data, headers=headers)
            response.raise_for_status()
            return response.json()

        device = post("/devices/provision", {})
        device_id = device["device_id"]

        def execute(capability, arguments, invocation=None, headers=owner):
            return post(
                "/devices/execute",
                {
                    "device_id": device_id,
                    "invocation_id": invocation or uuid.uuid4().hex,
                    "capability": capability,
                    "arguments": arguments,
                    "timeout": 25,
                },
                headers,
            )

        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                devices = client.get("/devices", headers=owner).json()["devices"]
                if any(d["device_id"] == device_id and d["online"] for d in devices):
                    break
                time.sleep(0.5)
            # Let Chromium bind CDP before the first action.
            time.sleep(2)
            operation = uuid.uuid4().hex
            html = """<html><body><button id=go onclick="
                localStorage.setItem('saved','persisted');
                document.title=String(Number(document.title||0)+1)
                ">Go</button><input id=note><p id=saved></p><script>
                document.getElementById('saved').textContent=localStorage.getItem('saved')||'';
                </script></body></html>"""
            write = {
                "command": "printf x >> counter; printf %s "
                + shlex.quote(html)
                + " > index.html"
            }
            assert execute("bash", write, operation)["status"] == "succeeded"
            assert execute("bash", write, operation)["status"] == "succeeded"
            assert (
                execute("bash", {"command": "cat counter"})["result"]["stdout"] == "x"
            )
            response = client.post(
                "/devices/execute",
                headers=other,
                json={
                    "device_id": device_id,
                    "invocation_id": uuid.uuid4().hex,
                    "capability": "bash",
                    "arguments": {"command": "pwd"},
                    "timeout": 5,
                },
            )
            assert response.status_code == 404, response.text
            page = execute(
                "browser",
                {"action": "navigate", "url": "http://127.0.0.1:8000/index.html"},
            )
            assert page["status"] == "succeeded", page
            assert "Go" in page["result"]["text"], page
            clicked = execute("browser", {"action": "click", "selector": "#go"})
            assert clicked["result"]["title"] == "1", clicked
            # Keyboard acts on the very same browser focused by Playwright.
            execute("computer", {"action": "key", "key": "Return"})
            after_key = execute("browser", {"action": "snapshot"})
            assert after_key["result"]["title"] == "2", after_key
            execute("computer", {"action": "click", "x": 400, "y": 500})
            pointer = execute("bash", {"command": "xdotool getmouselocation --shell"})
            assert (
                "X=400" in pointer["result"]["stdout"]
                and "Y=500" in pointer["result"]["stdout"]
            )
            execute("browser", {"action": "click", "selector": "#note"})
            execute("computer", {"action": "type", "text": "hello"})
            typed = execute("browser", {"action": "snapshot"})
            assert any(
                element.get("value") == "hello"
                for element in typed["result"]["elements"]
            ), typed
            first_page = typed["result"]["page_id"]
            tab = execute(
                "browser",
                {"action": "new_tab", "url": "http://127.0.0.1:8000/proof-missing"},
            )
            second_page = tab["result"]["page_id"]
            tabs = execute("browser", {"action": "tabs"})
            assert {first_page, second_page} <= {
                item["page_id"] for item in tabs["result"]["tabs"]
            }
            execute("browser", {"action": "switch_tab", "page_id": first_page})
            rejected = execute(
                "browser", {"action": "snapshot", "page_id": "missing-page"}
            )
            assert rejected["status"] == "failed", rejected
            execute("browser", {"action": "close_tab", "page_id": second_page})
            history = client.get(
                f"/devices/{device_id}/commands/{operation}", headers=owner
            )
            assert (
                history.status_code == 200 and history.json()["status"] == "succeeded"
            )
            assert (
                client.get(f"/devices/{device_id}/commands", headers=other).status_code
                == 404
            )
            paused = post(f"/devices/{device_id}/pause", {})
            assert paused["state"] == "paused", paused
            # Listing must not wake a paused E2B sandbox.
            for _ in range(2):
                listed = client.get("/devices", headers=owner).json()["devices"]
                listed_device = next(
                    item for item in listed if item["device_id"] == device_id
                )
                assert (
                    listed_device["state"] == "paused"
                    and listed_device["provider_state"] == "paused"
                ), listed_device
            blocked = client.post(
                "/devices/execute",
                headers=owner,
                json={
                    "device_id": device_id,
                    "invocation_id": uuid.uuid4().hex,
                    "capability": "bash",
                    "arguments": {"command": "pwd"},
                    "timeout": 5,
                },
            )
            assert blocked.status_code == 409, blocked.text
            resumed = post(f"/devices/{device_id}/resume", {})
            assert resumed["state"] == "online", resumed
            assert (
                execute("bash", {"command": "cat counter"})["result"]["stdout"] == "x"
            )
            memory = execute("browser", {"action": "snapshot", "page_id": first_page})
            assert memory["result"]["title"] == "2", memory
            assert any(
                item.get("value") == "hello" for item in memory["result"]["elements"]
            ), memory
            restored_page = execute(
                "browser",
                {"action": "navigate", "url": "http://127.0.0.1:8000/index.html"},
            )
            assert "persisted" in restored_page["result"]["text"]
            screen = execute("computer", {"action": "screenshot"})
            media = screen["result"]["screenshot"]["url"]
            response = client.get(media, headers=owner)
            assert response.status_code == 200 and response.content.startswith(
                b"\x89PNG"
            )
            assert client.get(media, headers=other).status_code == 404
            print(
                "PASS: ownership, idempotency, shared files/browser/desktop, "
                "private screenshot, tabs, command lookup, pause/resume"
                + ", desktop memory restore"
            )
        finally:
            post("/devices/" + device_id + "/revoke", {})


if __name__ == "__main__":
    main()
