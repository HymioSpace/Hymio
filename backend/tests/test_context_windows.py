from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.media.model_policy import CONTEXT_WINDOWS, MODEL_CONTEXT_WINDOWS
from hymio_backend.media.routes import media_routes
from hymio_backend.media.store import MediaStore
from hymio_backend.session_store import SessionStore


@pytest.fixture
def settings_client(tmp_path):
    settings = SimpleNamespace(
        database=tmp_path / "settings.sqlite",
        issuer="synthetic",
        public_url="http://127.0.0.1",
        access_seconds=3600,
        refresh_seconds=3600,
        origins=(),
        media_credential="",
        model_options=("MiniMax-M2.7", "MiniMax-M3", "Qwen/Qwen3.8-27B"),
        model_context_windows={},
    )
    sessions = SessionStore(settings)
    token = sessions.create_session({"iss": "synthetic", "sub": "alice", "name": "Alice"})
    media = MediaStore(sessions)

    async def body(request):
        return await request.json()

    def bearer(request):
        return request.headers.get("authorization", "").removeprefix("Bearer ")

    client = TestClient(Starlette(routes=media_routes(settings, sessions, bearer, body, media)))
    client.headers["authorization"] = "Bearer " + token["access_token"]
    with client:
        yield client, media, token["user_id"]


def test_default_and_model_capacity_are_explicit(settings_client):
    client, _, _ = settings_client
    value = client.get("/settings/models").json()
    assert value["context_window"] == 256000
    assert value["effective_context_window"] == 204800
    assert value["context_windows"] == list(CONTEXT_WINDOWS)
    assert value["model_context_windows"] == {k: MODEL_CONTEXT_WINDOWS[k] for k in value["models"]}


def test_four_tiers_persist_and_switch_model_without_losing_preference(settings_client):
    client, media, user = settings_client
    for size in CONTEXT_WINDOWS:
        response = client.post("/settings/models", json={"context_window": size})
        assert response.status_code == 200
        assert MediaStore(media.sessions).context_window(user) == size
    value = client.post("/settings/models", json={"model": "Qwen/Qwen3.8-27B"}).json()
    assert value["context_window"] == 1000000 and value["effective_context_window"] == 262144
    value = client.post("/settings/models", json={"model": "MiniMax-M3"}).json()
    assert value["effective_context_window"] == 1000000
    assert media.context_window("another-user") == 256000


def test_invalid_setting_is_atomic_and_authentication_is_required(settings_client):
    client, _, _ = settings_client
    for invalid in (True, "128000", 129000, None):
        response = client.post(
            "/settings/models", json={"model": "MiniMax-M3", "context_window": invalid}
        )
        assert response.status_code == 400
        value = client.get("/settings/models").json()
        assert value["selected"] == "MiniMax-M2.7" and value["context_window"] == 256000
    client.headers.pop("authorization")
    assert client.get("/settings/models").status_code == 401


def test_qwen_uses_native_capacity(settings_client):
    client, _, _ = settings_client
    # Catalog defaults are intentionally native capacities, never assumed YaRN support.
    assert (
        client.post(
            "/settings/models", json={"model": "Qwen/Qwen3.8-27B", "context_window": 512000}
        ).json()["effective_context_window"]
        == 262144
    )


def test_confirmed_deployment_override_is_respected(settings_client):
    client, media, _ = settings_client
    media.sessions.settings.model_context_windows["Qwen/Qwen3.8-27B"] = 512000
    value = client.post(
        "/settings/models", json={"model": "Qwen/Qwen3.8-27B", "context_window": 1000000}
    ).json()
    assert value["context_window"] == 1000000
    assert value["effective_context_window"] == 512000


def test_gateway_forwards_saved_window_instead_of_client_override(tmp_path):
    import asyncio
    import json
    import socket

    import uvicorn
    from starlette.routing import WebSocketRoute
    from websockets.asyncio.client import connect
    from websockets.asyncio.server import serve

    from hymio_backend.agent_gateway import relay_agent
    from hymio_backend.devices.store import DeviceStore

    async def run():
        async def upstream(ws):
            await ws.recv()
            await ws.send(json.dumps({"type": "ack", "id": "attach"}))
            await ws.send(await ws.recv())
            await ws.wait_closed()

        async with serve(upstream, "127.0.0.1", 0) as remote:
            port = remote.sockets[0].getsockname()[1]
            settings = SimpleNamespace(
                database=tmp_path / "relay.sqlite",
                origins=(),
                oath_ws=f"ws://127.0.0.1:{port}",
                model_options=("MiniMax-M3",),
            )
            storage = SessionStore(settings)
            media = MediaStore(storage)
            media.select_preferences("alice", "MiniMax-M3", 128000)
            sessions = SimpleNamespace(verify=lambda token: {"user_id": "alice"})
            devices = SimpleNamespace(
                store=DeviceStore(storage), ensure_available=lambda user: None
            )

            async def endpoint(ws):
                await relay_agent(ws, settings, sessions, devices, media)

            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            server = uvicorn.Server(
                uvicorn.Config(
                    Starlette(routes=[WebSocketRoute("/ws", endpoint)]),
                    log_level="error",
                    lifespan="off",
                )
            )
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(10):
                    while not server.started:
                        await asyncio.sleep(0.01)
                    async with connect(f"ws://127.0.0.1:{listener.getsockname()[1]}/ws") as client:
                        await client.send(
                            json.dumps(
                                {
                                    "v": 2,
                                    "id": "attach",
                                    "type": "agent.attach",
                                    "payload": {
                                        "credential": "synthetic",
                                        "user_id": "alice",
                                        "client_id": "synthetic-window",
                                    },
                                }
                            )
                        )
                        await client.recv()
                        await client.send(
                            json.dumps(
                                {
                                    "v": 2,
                                    "id": "message",
                                    "type": "user.message",
                                    "payload": {
                                        "content": "hello",
                                        "user_context": {},
                                        "context_window": 1000000,
                                    },
                                }
                            )
                        )
                        forwarded = json.loads(await client.recv())
                        assert forwarded["payload"]["context_window"] == 128000
                        assert forwarded["payload"]["model"] == "MiniMax-M3"
            finally:
                server.should_exit = True
                await task

    asyncio.run(run())
