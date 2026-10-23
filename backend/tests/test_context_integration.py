"""Real HTTP health and context-tool integration without provider credentials.

Run with --with-editable ../../Oath --with-editable ../../Nostalgia from backend.
"""

import json
import shutil
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette

pytest.importorskip("nostalgia")
from bootstrap.common.extension_loader import load_extensions
from core.protocol.datatype import ToolInvocation, User
from nostalgia.api import create_app
from nostalgia.bootstrap.config import Settings as NostalgiaSettings

from hymio_backend.context.client import ContextError, NostalgiaClient
from hymio_backend.context.routes import context_routes
from hymio_backend.server import bearer, body
from hymio_backend.session_store import SessionStore


@contextmanager
def http_service(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    address = "http://127.0.0.1:" + str(sock.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert thread.is_alive() and time.monotonic() < deadline
        time.sleep(0.01)
    try:
        yield address
    finally:
        server.should_exit = True
        thread.join(10)
        assert not thread.is_alive()
        sock.close()


@pytest.fixture
def stack(tmp_path):
    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        issuer="test",
        access_seconds=900,
        refresh_seconds=3600,
        public_url="http://test",
        origins=(),
        service_token_file=tmp_path / "service-token",
        nostalgia_connections_file=tmp_path / "connections.json",
        oath_ws="ws://127.0.0.1:1",
    )
    settings.service_token_file.write_text("s" * 40)
    sessions = SessionStore(settings)
    session = sessions.create_session({"iss": "test", "sub": "alice", "name": "Alice"})
    uid = session["user_id"]
    token = "nostalgia-private-alice-token"
    (tmp_path / "nostalgia-token").write_text(token)
    app = create_app(NostalgiaSettings(database=tmp_path / "context.sqlite", tokens={token: uid}))
    with http_service(app) as nostalgia_url:
        settings.nostalgia_connections_file.write_text(
            json.dumps(
                {
                    "users": {
                        uid: {"url": nostalgia_url, "token_file": "nostalgia-token"},
                    }
                }
            )
        )
        backend = Starlette(routes=context_routes(settings, sessions, bearer, body))
        with http_service(backend) as backend_url:
            with httpx.Client(
                base_url=backend_url,
                headers={
                    "Authorization": "Bearer " + session["access_token"],
                },
                trust_env=False,
                timeout=30,
            ) as public:
                yield SimpleNamespace(
                    settings=settings,
                    user=User(uid),
                    sessions=sessions,
                    public=public,
                    url=backend_url,
                    tmp=tmp_path,
                    context=NostalgiaClient(settings),
                )


def append(stack, text, key):
    response = stack.public.post(
        "/context/records",
        headers={"Idempotency-Key": key},
        json={
            "item_type": "context",
            "context_type": "text",
            "context": {"text": text},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_identity_idempotence_and_closed_mapping(stack):
    first = append(stack, "original", "same")
    assert append(stack, "original", "same") == first
    response = stack.public.post(
        "/context/records",
        headers={"Idempotency-Key": "same"},
        json={"item_type": "context", "context_type": "text", "context": {"text": "changed"}},
    )
    assert response.status_code == 409
    assert (
        stack.public.get(
            "/context/injection", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        stack.public.post(
            "/internal/context/call", json={"user_id": stack.user.user_id, "action": "injection"}
        ).status_code
        == 401
    )
    assert stack.public.post("/internal/dreaming/propose", json={}).status_code == 401
    with pytest.raises(ContextError) as error:
        stack.context.call("other-user", "injection")
    assert error.value.status == 403
    with pytest.raises(ValueError):
        stack.context.call(stack.user.user_id, "http://evil.example")
    with pytest.raises(ValueError):
        stack.context.call(stack.user.user_id, "records.append", data={})


def test_semantic_context_tools_remember_and_recall(stack):
    extensions_path = stack.tmp / "semantic-tools"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "extensions",
        extensions_path,
        ignore=shutil.ignore_patterns("_connection.local", "__pycache__"),
    )
    (extensions_path / "tools/_connection.local").write_text(
        json.dumps({"url": stack.url, "token": "s" * 40})
    )
    extensions = load_extensions((extensions_path,))
    tools = {tool.definition.name: tool for tool in extensions.tools}
    assert {"remember", "recall"} <= set(tools)
    assert "nostalgia" not in tools
    invocation = ToolInvocation(
        user=stack.user,
        invocation_id="remember-spicy-food",
        arguments={"text": "我喜欢吃辣。", "topic": "饮食"},
        deadline=time.monotonic() + 20,
    )
    saved = tools["remember"].execute(invocation)
    assert saved.content["data"]["source"]["kind"] == "conversation"
    assert saved.content["data"]["context"]["text"] == "我喜欢吃辣。"
    repeated = tools["remember"].execute(invocation)
    assert repeated.content["data"]["id"] == saved.content["data"]["id"]
    recalled = tools["recall"].execute(
        ToolInvocation(
            user=stack.user,
            invocation_id="recall-spicy-food",
            arguments={"query": "辣"},
            deadline=time.monotonic() + 20,
        )
    )
    assert [item["id"] for item in recalled.content["data"]["items"]] == [
        saved.content["data"]["id"]
    ]


def test_moments_proxy_and_event_callback_recovery(stack):
    from hymio_backend.context.events import deliver

    response = stack.public.post(
        "/context/saves", json={"text": "喜欢茶"}, headers={"Idempotency-Key": "save-tea"}
    )
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["source"]["kind"] == "user"
    assert (
        stack.public.post(
            "/context/saves", json={"text": "喜欢茶"}, headers={"Idempotency-Key": "save-tea"}
        ).json()
        == record
    )
    assert (
        stack.public.get("/context/records/" + record["id"]).json()["context"]["text"] == "喜欢茶"
    )
    assert stack.public.get("/context/assembly").json()["stable"]["content"] == ""
    assert (
        stack.public.get("/context/records", params={"source_kind": "user"}).json()["items"][0][
            "id"
        ]
        == record["id"]
    )
    uid = stack.sessions.verify(stack.public.headers["Authorization"][7:])["user_id"]
    accepted = []

    def fail(event):
        accepted.append(event["id"])
        raise RuntimeError("queue not durable")

    with pytest.raises(RuntimeError):
        deliver(stack.context, uid, "queue-test", stack.settings.database, fail)
    deliver(
        stack.context,
        uid,
        "queue-test",
        stack.settings.database,
        lambda event: accepted.append(event["id"]),
    )
    assert accepted[0] == accepted[1]
    assert (
        deliver(
            stack.context,
            uid,
            "queue-test",
            stack.settings.database,
            lambda event: pytest.fail("already checkpointed"),
        )["has_more"]
        is False
    )
