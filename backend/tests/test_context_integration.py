"""Real HTTP health and context-tool integration without provider credentials.

Run with --with-editable ../../Oath --with-editable ../../Nostalgia from backend.
"""

import asyncio
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
        arguments={
            "summary": "喜欢吃辣。",
            "text": "我喜欢吃辣。",
            "topic": "饮食",
            "title": "喜欢辣味",
            "category": "life",
        },
        deadline=time.monotonic() + 20,
    )
    saved = tools["remember"].execute(invocation)
    assert saved.content["data"]["source"]["kind"] == "conversation"
    assert saved.content["data"]["context"]["text"] == "我喜欢吃辣。"
    assert saved.content["data"]["context"]["memory"] == {
        "summary": "喜欢吃辣。",
        "state": "proposed",
        "title": "喜欢辣味",
        "category": "life",
    }
    assert saved.content["data"]["context"]["provenance"] == {
        "kind": "provided_quote",
        "invocation_id": "remember-spicy-food",
    }
    assert saved.content["data"]["source"]["parser"] == "hymio.remember.v2"
    from core.protocol.error import ToolExecutionError

    with pytest.raises(ToolExecutionError):
        tools["remember"].execute(
            ToolInvocation(
                user=stack.user,
                invocation_id="missing-extraction",
                arguments={"text": "随便聊两句。"},
                deadline=time.monotonic() + 20,
            )
        )
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


def test_recall_reads_full_originals_and_rejects_ambiguous_requests(stack):
    from core.protocol.error import ToolExecutionError

    extensions_path = stack.tmp / "read-tools"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "extensions",
        extensions_path,
        ignore=shutil.ignore_patterns("_connection.local", "__pycache__"),
    )
    (extensions_path / "tools/_connection.local").write_text(
        json.dumps({"url": stack.url, "token": "s" * 40})
    )
    tool = next(
        tool
        for tool in load_extensions((extensions_path,)).tools
        if tool.definition.name == "recall"
    )
    original = "学习西语。" + "原始依据需要完整保留。" * 200
    record = append(stack, original, "long-original")

    def recall(arguments):
        return tool.execute(
            ToolInvocation(
                user=stack.user,
                invocation_id="read-original",
                arguments=arguments,
                deadline=time.monotonic() + 20,
            )
        ).content["data"]

    hit = recall({"query": "西语"})["items"][0]
    assert hit["truncated"] is True
    full = recall({"action": "read", "kind": "record", "id": hit["id"]})
    assert full["id"] == record["id"]
    assert full["context"]["text"] == original
    # Publish an interpretation, then follow its reference through the same Agent tool.
    url, token = stack.context.connection(stack.user.user_id)
    with httpx.Client(
        base_url=url, headers={"Authorization": "Bearer " + token}, trust_env=False
    ) as api:
        started = api.post("/v1/dreams", headers={"Idempotency-Key": "start-read-test"})
        assert started.status_code < 300, started.text
        dream_id = started.json()["dream_id"]
        record_path = f"/v1/records/{record['id']}?dream_id={dream_id}"
        etag = api.get(record_path).headers["etag"]
        marked = api.patch(
            record_path,
            json={"processing_state": "applied", "status": "active"},
            headers={"Idempotency-Key": "mark-read-test", "If-Match": etag},
        )
        assert marked.status_code < 300, marked.text
        for item_id, body in [
            (
                "learning",
                {
                    "content": "学习西语",
                    "fields": {"title": "散步时学西语", "category": "learning"},
                    "references": [{"record_id": record["id"], "root_id": record["root_id"]}],
                },
            ),
            ("_index", {"content": "学习", "links": ["learning"]}),
        ]:
            result = api.put(
                f"/v1/artifacts/{item_id}?dream_id={dream_id}",
                json=body,
                headers={"Idempotency-Key": "put-" + item_id, "If-None-Match": "*"},
            )
            assert result.status_code < 300, result.text
        etag = api.get(f"/v1/dreams/{dream_id}").headers["etag"]
        published = api.post(
            f"/v1/dreams/{dream_id}/commit",
            headers={"Idempotency-Key": "commit-read-test", "If-Match": etag},
        )
        assert published.status_code < 300, published.text
    categorized = stack.public.post(
        "/context/browse", json={"target": "artifacts", "category": "learning"}
    ).json()
    assert [v["id"] for v in categorized["items"]] == ["learning"]
    assert categorized["items"][0]["title"] == "散步时学西语"
    assert (
        stack.public.post(
            "/context/browse", json={"target": "artifacts", "category": "work"}
        ).json()["items"]
        == []
    )
    interpretation = recall({"action": "read", "kind": "artifact", "id": "learning"})
    assert interpretation["content"] == "学习西语"
    assert interpretation["references"][0]["record_id"] == record["id"]
    with pytest.raises(ToolExecutionError):
        recall({"action": "read", "id": record["id"]})
    with pytest.raises(ToolExecutionError):
        recall({"action": "read", "kind": "record", "id": record["id"], "query": "西语"})
    with pytest.raises(ToolExecutionError):
        recall({"action": "delete", "kind": "record", "id": record["id"]})


def test_ui_save_search_and_pending_understanding(stack):
    saved = stack.public.post(
        "/context/saves",
        json={"text": "每天散步时听西语。"},
        headers={"Idempotency-Key": "ui-save-spanish"},
    )
    assert saved.status_code == 201
    record = saved.json()
    found = stack.public.post(
        "/context/search",
        json={
            "target": "records",
            "mode": "text",
            "query": "西语",
            "filters": {},
            "limit": 30,
        },
    ).json()
    assert found["items"][0]["source"]["kind"] == "user"
    injection = stack.context.call(stack.user.user_id, "injection")["data"]
    assert injection["buffer"][0]["id"] == record["id"]
    # A confirmed save is an original, not fabricated synthesized understanding.
    artifacts = stack.public.post(
        "/context/search",
        json={
            "target": "artifacts",
            "mode": "filter",
            "query": None,
            "filters": {},
            "limit": 30,
        },
    ).json()
    assert not [item for item in artifacts["items"] if not item["id"].startswith("_")]
    conflict = stack.public.post(
        "/context/saves",
        json={"text": "不同的正文"},
        headers={"Idempotency-Key": "ui-save-spanish"},
    )
    assert conflict.status_code == 409


def test_browse_classification_and_cursor(stack):
    # Classification must search beyond the first upstream page, with no loss or repeats.
    expected = []
    for index in range(35):
        category = "learning" if index in {3, 31, 34} else "work"
        res = stack.public.post(
            "/context/saves",
            json={"text": f"browse fixture {index}", "category": category},
            headers={"Idempotency-Key": f"category-{index}"},
        )
        assert res.status_code == 201, res.text
        if category == "learning":
            expected.append(res.json()["id"])
    expected.reverse()  # Browsing is newest first across page boundaries.
    params = {"target": "records", "category": "learning", "limit": 2}
    first = stack.public.post("/context/browse", json=params)
    assert first.status_code == 200, first.text
    page = first.json()
    assert [v["id"] for v in page["items"]] == expected[:2]
    assert all(v["category"] == "learning" for v in page["items"])
    assert page["next_cursor"]
    second = stack.public.post(
        "/context/browse", json={**params, "cursor": page["next_cursor"]}
    ).json()
    assert [v["id"] for v in second["items"]] == expected[2:]
    assert not second["next_cursor"]
    assert (
        stack.public.post(
            "/context/browse", json={**params, "category": "life", "cursor": page["next_cursor"]}
        ).status_code
        == 400
    )
    assert (
        stack.public.post("/context/browse", json={**params, "cursor": "invalid"}).status_code
        == 400
    )
    assert (
        stack.public.post(
            "/context/saves",
            json={"text": "invalid", "category": "guess"},
            headers={"Idempotency-Key": "invalid-category"},
        ).status_code
        == 400
    )
    legacy = stack.public.post(
        "/context/saves",
        json={"text": "legacy without category"},
        headers={"Idempotency-Key": "legacy-category"},
    ).json()
    unclassified = stack.public.post(
        "/context/browse", json={"target": "records", "category": "uncategorized"}
    ).json()
    assert [v["id"] for v in unclassified["items"]] == [legacy["id"]]


def test_connector_versions_reach_real_nostalgia(stack):
    from hymio_backend.connectors.service import ConnectorService

    stack.settings.connectors_config_file = None
    service = ConnectorService(stack.settings, stack.sessions)
    uid = stack.user.user_id
    connection = service.store.create(uid, "apple_health", "synthetic-phone")
    for steps in (1, 2, 1):
        service.ingest(
            uid,
            connection["id"],
            {
                "device_id": "synthetic-phone",
                "consent": True,
                "captured_at": time.time(),
                "items": [
                    {
                        "external_id": "daily:2026-01-01",
                        "day": "2026-01-01",
                        "kind": "health_daily",
                        "steps": steps,
                        "title": "Synthetic steps",
                    }
                ],
            },
        )
        assert service.project()
    with service.store.transaction() as db:
        rows = db.execute("SELECT delivered,record_id FROM connector_changes").fetchall()
    assert len(rows) == 3
    assert all(row["delivered"] and row["record_id"] for row in rows)
    assert len({row["record_id"] for row in rows}) == 3
    asyncio.run(service.http.aclose())
