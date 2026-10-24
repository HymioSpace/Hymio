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
            return httpx.Response(
                200,
                json={
                    "kit_id": "hymio.ledger",
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
        assert all(item[2] == "Bearer " + token_file.read_text() for item in requests)

        assert (
            web.post(
                "/internal/kits",
                headers={"authorization": "Bearer " + token_file.read_text()},
                json={"user_id": alice["user_id"], "action": "list"},
            ).status_code
            == 400
        )
