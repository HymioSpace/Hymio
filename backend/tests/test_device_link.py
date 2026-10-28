import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.devices.link import DeviceLink, link_routes
from hymio_backend.devices.routes import device_routes
from hymio_backend.devices.store import DeviceStore
from hymio_backend.server import body
from hymio_backend.session_store import SessionStore, Unauthorized


@pytest.fixture
def stack():
    with tempfile.TemporaryDirectory() as temp:
        settings = SimpleNamespace(database=Path(temp) / "db.sqlite", origins=[], e2b_key_file=None)
        sessions = SessionStore(settings)

        def verify(value):
            if value in ("alice-token", "bob-token"):
                return {"user_id": value.split("-")[0]}
            raise Unauthorized()

        sessions.verify = verify
        link = DeviceLink(DeviceStore(sessions))

        def bearer(request):
            return request.headers.get("authorization", "").removeprefix("Bearer ")

        routes = link_routes(settings, sessions, bearer, body, link)
        routes += device_routes(settings, sessions, bearer, body, link=link)
        with TestClient(Starlette(routes=routes)) as client:
            yield client, link


def headers(user="alice"):
    return {"Authorization": "Bearer " + user + "-token"}


def pair(client):
    code = client.post("/devices/link/pairings", headers=headers(), json={}).json()["code"]
    response = client.post("/devices/link/claim", json={"code": code, "name": "Synthetic Mac"})
    assert response.status_code == 200
    return response.json(), code


def connect(ws, pair):
    ws.send_json(
        {
            "v": 1,
            "type": "link.attach",
            "credential": pair["credential"],
            "capabilities": ["bash", "computer"],
        }
    )
    ready = ws.receive_json()
    assert ready["type"] == "link.ready"
    return ready


def request(pair, invocation="example", timeout=2):
    return {
        "device_id": pair["device_id"],
        "invocation_id": invocation,
        "capability": "bash",
        "arguments": {"command": "printf synthetic"},
        "timeout": timeout,
    }


def test_pairing_is_single_use_and_device_token_cannot_be_user_token(stack):
    client, link = stack
    paired, code = pair(client)
    assert client.post("/devices/link/claim", json={"code": code}).status_code == 401
    assert (
        client.get(
            "/devices", headers={"Authorization": "Bearer " + paired["credential"]}
        ).status_code
        == 401
    )
    assert client.get("/devices", headers=headers("bob")).json()["devices"] == []
    assert (
        client.post("/devices/execute", headers=headers("bob"), json=request(paired)).status_code
        == 404
    )
    expired = link.pairing("bob")
    with link.store.transaction() as db:
        db.execute("UPDATE link_pairings SET expires=0")
    assert client.post("/devices/link/claim", json={"code": expired["code"]}).status_code == 401


def test_real_websocket_dispatch_dedup_pause_and_revoke(stack):
    client, link = stack
    paired, _ = pair(client)
    with client.websocket_connect("/devices/link/ws") as ws, ThreadPoolExecutor() as workers:
        ready = connect(ws, paired)
        listed = client.get("/devices", headers=headers()).json()["devices"]
        assert listed[0]["online"] and listed[0]["capabilities"] == ["bash", "computer"]
        future = workers.submit(
            client.post, "/devices/execute", headers=headers(), json=request(paired)
        )
        command = ws.receive_json()
        assert command["type"] == "link.command" and command["device_id"] == paired["device_id"]
        ws.send_json(
            {
                "v": 1,
                "type": "link.result",
                "generation": ready["generation"],
                "invocation_id": command["invocation_id"],
                "payload": {"output": "synthetic"},
            }
        )
        assert ws.receive_json()["type"] == "link.ack"
        result = future.result().json()
        assert result["status"] == "succeeded" and result["result"]["output"] == "synthetic"
        assert (
            client.post("/devices/execute", headers=headers(), json=request(paired)).json()
            == result
        )
        paused = client.post(
            "/devices/" + paired["device_id"] + "/pause", headers=headers(), json={}
        )
        assert paused.json()["state"] == "paused"
        assert (
            client.post(
                "/devices/execute", headers=headers(), json=request(paired, "blocked")
            ).status_code
            == 409
        )
        client.post("/devices/" + paired["device_id"] + "/resume", headers=headers(), json={})
        client.post("/devices/" + paired["device_id"] + "/revoke", headers=headers(), json={})
        with pytest.raises(Unauthorized):
            link.identity(paired["credential"])


def test_unknown_outcome_keeps_lock_until_late_durable_result(stack):
    client, link = stack
    paired, _ = pair(client)
    with client.websocket_connect("/devices/link/ws") as ws, ThreadPoolExecutor() as workers:
        ready = connect(ws, paired)
        future = workers.submit(
            client.post, "/devices/execute", headers=headers(), json=request(paired, timeout=0.1)
        )
        command = ws.receive_json()
        assert future.result().json()["status"] == "outcome_unknown"
        assert (
            client.post(
                "/devices/execute", headers=headers(), json=request(paired, "new")
            ).status_code
            == 409
        )
        ws.send_json(
            {
                "v": 1,
                "type": "link.result",
                "generation": ready["generation"],
                "invocation_id": command["invocation_id"],
                "payload": {"output": "saved-result"},
            }
        )
        assert ws.receive_json()["type"] == "link.ack"
        known = client.post("/devices/execute", headers=headers(), json=request(paired)).json()
        assert known["status"] == "succeeded" and known["result"]["output"] == "saved-result"
        with link.store.transaction() as db:
            assert db.execute("SELECT 1 FROM device_locks").fetchone() is None


def test_unrecognized_and_stale_results_are_rejected(stack):
    client, link = stack
    paired, _ = pair(client)
    device = link.identity(paired["credential"])
    with pytest.raises(ValueError):
        link.result(device, {"generation": 1, "invocation_id": "not-dispatched", "payload": {}})
    with pytest.raises(ValueError):
        link.result(device, {"generation": 99, "invocation_id": "example", "payload": {}})
    offline = client.post("/devices/execute", headers=headers(), json=request(paired)).json()
    assert offline["status"] == "failed" and offline["dispatched"] is False


def test_operator_resolution_preserves_unknown_history(stack):
    client, link = stack
    paired, _ = pair(client)
    link.store.claim("alice", paired["device_id"], "interrupted", {"capability": "bash"}, 0.1)
    link.store.finish("alice", "interrupted", {"status": "outcome_unknown"}, release=False)
    path = "/devices/link/" + paired["device_id"] + "/resolve"
    assert (
        client.post(path, headers=headers(), json={"invocation_id": "interrupted"}).status_code
        == 400
    )
    assert (
        client.post(
            path,
            headers=headers("bob"),
            json={"invocation_id": "interrupted", "acknowledge_unknown": True},
        ).status_code
        == 404
    )
    assert client.post(
        path, headers=headers(), json={"invocation_id": "interrupted", "acknowledge_unknown": True}
    ).json()["resolved"]
    with link.store.transaction() as db:
        assert (
            db.execute("SELECT status FROM device_commands").fetchone()["status"]
            == "outcome_unknown"
        )
        assert db.execute("SELECT 1 FROM device_locks").fetchone() is None


def test_permissions_refresh_and_revocation_without_reconnect(stack):
    client, _ = stack
    paired, _ = pair(client)
    with client.websocket_connect("/devices/link/ws") as ws:
        ws.send_json(
            {
                "v": 1,
                "type": "link.attach",
                "credential": paired["credential"],
                "capabilities": [],
                "permissions": {"screen_recording": True, "accessibility": False, "shell": False},
            }
        )
        assert ws.receive_json()["type"] == "link.ready"
        before = client.get("/devices", headers=headers()).json()["devices"][0]
        assert before["capabilities"] == [] and before["permissions"]["accessibility"] is False
        ws.send_json(
            {
                "v": 1,
                "type": "link.ping",
                "capabilities": ["computer"],
                "permissions": {"screen_recording": True, "accessibility": True, "shell": False},
            }
        )
        assert ws.receive_json()["type"] == "link.pong"
        after = client.get("/devices", headers=headers()).json()["devices"][0]
        assert after["capabilities"] == ["computer"] and after["permissions"]["accessibility"]
        ws.send_json(
            {
                "v": 1,
                "type": "link.ping",
                "capabilities": [],
                "permissions": {"screen_recording": True, "accessibility": False, "shell": False},
            }
        )
        assert ws.receive_json()["type"] == "link.pong"
        assert client.get("/devices", headers=headers()).json()["devices"][0]["capabilities"] == []


def test_android_binding_is_independent_of_mac_and_unique_per_user(stack):
    client, link = stack
    pair(client)
    code = link.pairing("alice")["code"]
    android = client.post(
        "/devices/link/claim",
        json={"code": code, "name": "Synthetic phone", "kind": "personal_android"},
    )
    assert android.status_code == 200
    devices = client.get("/devices", headers=headers()).json()["devices"]
    assert {device["kind"] for device in devices} == {"personal_mac", "personal_android"}
    code = link.pairing("alice")["code"]
    assert (
        client.post(
            "/devices/link/claim",
            json={"code": code, "name": "Duplicate phone", "kind": "personal_android"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/devices/link/claim", json={"code": code, "name": "Fake platform", "kind": "admin"}
        ).status_code
        == 400
    )
    with pytest.raises(ValueError, match="invalid_android_capability"):
        link.report({"capabilities": ["bash"]}, "personal_android")


def test_android_swipe_delivery_and_canvas_validation(stack):
    from hymio_backend.devices.validation import validate

    client, link = stack
    validate("bash", {"command": "pwd", "description": "Inspect the workspace"})
    with pytest.raises(ValueError, match="description_too_long"):
        validate("bash", {"command": "pwd", "description": "x" * 81})
    paired = link.claim(link.pairing("alice")["code"], "Synthetic phone", "personal_android")
    args = {"action": "swipe", "x": 640, "y": 600, "x2": 640, "y2": 250, "duration_ms": 400}
    validate("computer", args)
    for invalid in (
        {**args, "x2": 1280},
        {**args, "duration_ms": True},
        {**args, "duration_ms": 99},
    ):
        with pytest.raises(ValueError):
            validate("computer", invalid)
    with client.websocket_connect("/devices/link/ws") as ws:
        ws.send_json(
            {
                "v": 1,
                "type": "link.attach",
                "credential": paired["credential"],
                "capabilities": ["computer"],
            }
        )
        ready = ws.receive_json()
        device = client.get("/devices", headers=headers()).json()["devices"][0]
        assert device["kind"] == "personal_android" and "swipe" in device["supported_actions"]
        with ThreadPoolExecutor() as pool:
            pending = pool.submit(
                client.post,
                "/devices/execute",
                headers=headers(),
                json={
                    "device_id": paired["device_id"],
                    "invocation_id": "phone-swipe",
                    "capability": "computer",
                    "arguments": args,
                    "timeout": 2,
                },
            )
            frame = ws.receive_json()
            assert frame["arguments"] == args
            ws.send_json(
                {
                    "v": 1,
                    "type": "link.result",
                    "generation": ready["generation"],
                    "invocation_id": "phone-swipe",
                    "payload": {"applied": True},
                }
            )
            assert ws.receive_json()["type"] == "link.ack"
            assert pending.result().json()["status"] == "succeeded"
        ws.send_json(
            {
                "v": 1,
                "type": "link.ping",
                "capabilities": [],
                "permissions": {
                    "screen_recording": True,
                    "accessibility": True,
                    "unlocked": False,
                    "screen_awake": True,
                    "shell": False,
                },
            }
        )
        assert ws.receive_json()["type"] == "link.pong"
        locked = client.get("/devices", headers=headers()).json()["devices"][0]
        assert "unlock" in locked["guidance"].lower()
