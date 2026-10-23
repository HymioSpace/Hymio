import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.reactions import reaction_routes


def test_only_the_agent_service_can_react(tmp_path):
    private = tmp_path / "service"
    private.write_text("test-service")
    settings = SimpleNamespace(origins=(), service_token_file=private, oath_biz="http://agent")

    async def body(request, **kwargs):
        return json.loads(await request.body())

    app = Starlette(
        routes=reaction_routes(
            settings,
            lambda request: request.headers.get("authorization", "").removeprefix("Bearer "),
            body,
        )
    )
    remote = SimpleNamespace(status_code=200, json=lambda: {"emoji": "🎉"})
    client = SimpleNamespace(post=AsyncMock(return_value=remote))
    transport = AsyncMock()
    transport.__aenter__.return_value = client
    with (
        patch("hymio_backend.reactions.httpx.AsyncClient", return_value=transport),
        patch("hymio_backend.reactions.issue", return_value="test-token") as issue,
    ):
        response = TestClient(app).post(
            "/internal/reactions",
            headers={"Authorization": "Bearer test-service"},
            json={
                "actor": "user",
                "user_id": "bob",
                "target": "user:1",
                "emoji": "🎉",
                "operation_id": "o",
            },
        )
    assert response.status_code == 200
    assert client.post.call_args.kwargs["json"] == {
        "actor": "assistant",
        "target": "user:1",
        "emoji": "🎉",
        "operation_id": "o",
    }
    assert issue.call_args.args[1] == "bob"


def test_public_and_unauthenticated_reaction_paths_are_unavailable(tmp_path):
    private = tmp_path / "service"
    private.write_text("test-service")

    async def body(request, **kwargs):
        return {}

    app = Starlette(
        routes=reaction_routes(
            SimpleNamespace(origins=(), service_token_file=private),
            lambda request: "",
            body,
        )
    )
    assert TestClient(app).post("/internal/reactions", json={}).status_code == 401
    assert TestClient(app).post("/reactions", json={}).status_code == 404
