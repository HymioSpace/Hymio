from types import SimpleNamespace

import httpx
from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.kits.routes import kit_routes
from hymio_backend.kits.service import KitsService
from hymio_backend.session_store import SessionStore


def test_backend_proxies_ui_and_direct_agent_operations(tmp_path):
    token_file = tmp_path / "service-token"
    token_file.write_text("service-token-" + "x" * 40)
    requests = []

    async def kit_host(request):
        payload = __import__("json").loads(request.content)
        requests.append((request.url.path, payload, request.headers["authorization"]))
        if request.url.path == "/events":
            return httpx.Response(200, json={"accepted": True})
        if request.url.path == "/v1/catalog":
            return httpx.Response(200, json={"kits": [{"id": "hymio.ledger", "installed": False}]})
        if request.url.path == "/v1/install":
            return httpx.Response(
                200,
                json={"id": "hymio.ledger", "installed": True, "preview": {"value": "¥35.00"}},
            )
        if request.url.path == "/v1/app":
            return httpx.Response(
                200,
                json={
                    "kit_id": "hymio.ledger",
                    "html": "<h1>生活账本</h1>",
                    "bridge": "hymio.kit.bridge/v1",
                },
            )
        if request.url.path == "/v1/invoke":
            effect = "read" if payload["operation"].endswith(".list") else "write"
            return httpx.Response(
                200,
                json={
                    "kit_id": "hymio.ledger",
                    "effect": effect,
                    "operation": payload["operation"],
                    "result": {"message": "这笔记下了。"},
                    "view": {"title": "生活账本"},
                },
            )
        return httpx.Response(404, json={"error": "not_found"})

    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        public_url="http://127.0.0.1",
        access_seconds=3600,
        refresh_seconds=3600,
        origins=(),
        service_token_file=token_file,
        kits_url="http://kit-host:8090",
        oath_biz="http://oath-biz:8766",
    )
    sessions = SessionStore(settings)
    alice = sessions.create_session({"iss": "synthetic", "sub": "alice", "name": "Alice"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(kit_host))
    service = KitsService(settings, client)

    async def body(request, *, limit=16384):
        return await request.json()

    def bearer(request):
        return request.headers.get("authorization", "").removeprefix("Bearer ")

    app = Starlette(routes=kit_routes(settings, sessions, service, bearer, body))
    with TestClient(app) as web:
        web.headers["authorization"] = "Bearer " + alice["access_token"]
        assert web.get("/kits").status_code == 200
        assert web.post("/kits/hymio.ledger/install").status_code == 200
        assert "生活账本" in web.get("/kits/hymio.ledger/app").json()["html"]
        ui_write = web.post(
            "/kits/hymio.ledger/actions/entries.create",
            json={"amount": 35},
            headers={"Idempotency-Key": "ui-entry"},
        )
        assert ui_write.status_code == 200
        event = next(item for item in requests if item[0] == "/events")[1]
        assert event["type"] == "app.kit.interaction"
        assert event["queue"] == "user"
        assert event["defer_wake"] is True
        assert event["payload"]["kit_id"] == "hymio.ledger"
        assert event["payload"]["operation"] == "entries.create"
        assert event["payload"]["result"] == {"message": "这笔记下了。"}

        ui_read = web.post(
            "/kits/hymio.ledger/actions/entries.list",
            json={},
            headers={"Idempotency-Key": "ui-read"},
        )
        assert ui_read.status_code == 200
        assert len([item for item in requests if item[0] == "/events"]) == 1

        agent_write = web.post(
            "/internal/kits",
            headers={"authorization": "Bearer " + token_file.read_text()},
            json={
                "user_id": alice["user_id"],
                "kit_id": "hymio.ledger",
                "operation": "entries.create",
                "arguments": {"amount": 12},
                "invocation_id": "agent-entry",
            },
        )
        assert agent_write.status_code == 200
        assert requests[-1][1]["idempotency_key"] == "agent-entry"
        assert all(
            item[2] == "Bearer " + token_file.read_text()
            for item in requests
            if item[0].startswith("/v1/")
        )

        assert (
            web.post(
                "/internal/kits",
                headers={"authorization": "Bearer " + token_file.read_text()},
                json={"user_id": alice["user_id"], "action": "list"},
            ).status_code
            == 400
        )


def test_backend_delegates_create_and_editor_edits_to_oath_context(tmp_path):
    token_file = tmp_path / "service-token"
    token_file.write_text("service-token-" + "x" * 40)
    requests = []
    agent_id = "b" * 32
    kit_id = "user.123456789abc"

    async def downstream(request):
        payload = __import__("json").loads(request.content)
        requests.append((request.url.path, payload))
        if request.url.path == "/v1/project/create":
            return httpx.Response(
                200,
                json={
                    "kit_id": kit_id,
                    "status": "draft",
                    "display": {
                        "name": "饮水记录",
                        "tagline": "每天喝了多少，一眼就知道。",
                    },
                    "source_revision": "a" * 64,
                },
            )
        if request.url.path == "/v1/project/bind-agent":
            return httpx.Response(200, json=payload)
        if request.url.path == "/v1/editor/message":
            return httpx.Response(200, json={"accepted": True})
        if request.url.path == "/v1/editor":
            return httpx.Response(
                200,
                json={
                    "kit_id": kit_id,
                    "status": "published",
                    "coding_agent_id": agent_id,
                    "source_revision": "a" * 64,
                    "messages": [],
                    "changes": [],
                },
            )
        if request.url.path == "/subagents/spawn":
            return httpx.Response(200, json={"agent_id": agent_id, "status": "waiting"})
        if request.url.path == "/subagents/continue":
            return httpx.Response(200, json={"agent_id": agent_id, "status": "running"})
        if request.url.path == "/subagents/get":
            return httpx.Response(
                200,
                json={
                    "agent_id": agent_id,
                    "status": "succeeded",
                    "result": "第一版已完成。",
                },
            )
        return httpx.Response(404, json={"error": "not_found"})

    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        public_url="http://127.0.0.1",
        access_seconds=3600,
        refresh_seconds=3600,
        origins=(),
        service_token_file=token_file,
        kits_url="http://kit-host:8090",
        oath_biz="http://oath-biz:8766",
    )
    sessions = SessionStore(settings)
    alice = sessions.create_session({"iss": "synthetic", "sub": "alice", "name": "Alice"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(downstream))
    service = KitsService(settings, client)

    async def body(request, *, limit=16384):
        return await request.json()

    def bearer(request):
        return request.headers.get("authorization", "").removeprefix("Bearer ")

    app = Starlette(routes=kit_routes(settings, sessions, service, bearer, body))
    with TestClient(app) as web:
        created = web.post(
            "/internal/kits/build",
            headers={"authorization": "Bearer " + token_file.read_text()},
            json={
                "user_id": alice["user_id"],
                "action": "create",
                "invocation_id": "build-water",
                "spec": {
                    "name": "饮水记录",
                    "tagline": "每天喝了多少，一眼就知道。",
                    "category": "生活",
                    "item_label": "杯水",
                    "fields": [
                        {"key": "amount", "label": "杯数", "type": "number"}
                    ],
                    "requirements": "做成安静、清晰的饮水记录页",
                },
            },
        )
        created.raise_for_status()
        assert created.json()["status"] == "coding"
        spawn = next(item for item in requests if item[0] == "/subagents/spawn")[1]
        assert spawn["defer_start"] is True
        assert spawn["notify_parent"] is True
        assert "饮水记录" in spawn["objective"]
        continued = next(
            item for item in requests if item[0] == "/subagents/continue"
        )[1]
        assert continued["agent_id"] == agent_id
        assert continued["notify_parent"] is True
        bound = next(
            item for item in requests if item[0] == "/v1/project/bind-agent"
        )[1]
        assert bound["agent_id"] == agent_id

        web.headers["authorization"] = "Bearer " + alice["access_token"]
        editor = web.get("/kits/" + kit_id + "/editor")
        editor.raise_for_status()
        assert editor.json()["agent_status"] == "succeeded"
        assert editor.json()["agent_result"] == "第一版已完成。"
        edited = web.post(
            "/kits/" + kit_id + "/editor/messages",
            headers={"Idempotency-Key": "editor-change-1"},
            json={"content": "增加本周趋势，保留已有记录"},
        )
        edited.raise_for_status()
        editor_continue = [
            item[1]
            for item in requests
            if item[0] == "/subagents/continue"
        ][-1]
        assert editor_continue["notify_parent"] is False
        assert "本周趋势" in editor_continue["content"]
