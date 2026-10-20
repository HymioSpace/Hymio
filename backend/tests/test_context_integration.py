"""Real HTTP services and Oath runtime; deterministic model, no external credentials.

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
pytest.importorskip("core.agent")

from bootstrap.common.assembly import build_context
from bootstrap.common.extension_loader import load_extensions
from bootstrap.gateway import process as gateway
from bootstrap.tools.process import AllowAllPolicy, ToolService
from core.agent import AgentBrain
from core.compaction.coordinator import CompactionCoordinator
from core.compaction.llm import LlmCompactor
from core.consumer import ToolConsumer, UserConsumer
from core.detail import DETAIL_READ, DetailReadTool, ResultShrinker
from core.journal.runtime_store import RuntimeStore
from core.protocol.datatype import User
from core.protocol.datatype.config import AgentConfig, ServicesConfig
from core.protocol.datatype.inbound import Inbound
from core.protocol.datatype.llm import LlmResponse, LlmToolCall
from core.skill import SkillSystem, SkillTool
from core.storage.adapters import DurableEventSink, StoredDetails, StoredQueue
from core.storage.database import Database
from core.storage.service import StorageService
from core.tool.impl import ThreadedToolSystem
from core.tool.registry import ToolRegistry
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
    with pytest.raises(ContextError) as error:
        stack.context.call("other-user", "injection")
    assert error.value.status == 403
    with pytest.raises(ValueError):
        stack.context.call(stack.user.user_id, "http://evil.example")
    with pytest.raises(ValueError):
        stack.context.call(stack.user.user_id, "records.append", data={})


def test_failed_dispatch_retains_draft_for_abort(stack):
    append(stack, "unfinished", "one")
    headers = {"Idempotency-Key": "start"}
    first = stack.public.post("/context/dreams", headers=headers, json={})
    assert first.status_code == 503, first.text
    dream_id = first.json()["dream_id"]
    again = stack.public.post("/context/dreams", headers=headers, json={})
    assert again.json()["dream_id"] == dream_id
    assert stack.public.get(f"/context/dreams/{dream_id}").json()["state"] == "draft"
    response = stack.public.post(
        f"/context/dreams/{dream_id}/abort",
        json={},
        headers={
            "Idempotency-Key": "abort",
        },
    )
    assert response.json()["state"] == "aborted"
    assert stack.public.get("/context/injection").json()["buffer"]


@contextmanager
def oath_gateway(stack, storage, monkeypatch):
    # Production Gateway + authentication + delivery + durable queue. Only RPC transport
    # is replaced by the same StorageService in-process; RabbitMQ isn't needed here.
    class Port:
        def call(self, operation, **params):
            return storage.call(operation, **params)

        def close(self):
            pass

    monkeypatch.setattr(gateway, "ServiceClient", lambda *args: Port())
    monkeypatch.setenv("OATH_AUTH_MODE", "static")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    access = stack.public.headers["Authorization"][7:]
    config = SimpleNamespace(
        services=ServicesConfig(
            gateway_port=port,
            internal_token="i" * 40,
            users={access: stack.user.user_id},
            poll_seconds=0.01,
        )
    )
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    holder = {}

    def run():
        asyncio.set_event_loop(loop)
        task = loop.create_task(gateway.run_async(config))
        holder["task"] = task
        ready.set()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    ready.wait(5)
    stack.settings.oath_ws = f"ws://127.0.0.1:{port}"
    deadline = time.monotonic() + 5
    while True:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/heartbeat", trust_env=False).status_code == 200:
                break
        except httpx.TransportError:
            pass
        assert time.monotonic() < deadline
        time.sleep(0.01)
    try:
        yield
    finally:
        loop.call_soon_threadsafe(holder["task"].cancel)
        thread.join(10)
        assert not thread.is_alive()


class ScriptedModel:
    """Controlled tool decisions; checks results really returned through AgentBrain."""

    def __init__(self, program):
        self.program = program
        self.last = None
        self.requests = []

    def complete(self, request, *, on_delta=None):
        self.requests.append(request)
        results = [message for message in request.messages if message.role == "tool"]
        result = None
        if self.last is not None:
            assert results, "Actual tool result missing from model context"
            result = results[-1].content
            if result.startswith('{"batch_id"'):
                result = json.dumps(json.loads(result)["content"])
        try:
            tool, arguments = self.program.send(result)
        except StopIteration:
            return LlmResponse(content="Dream committed.")
        self.last = str(len(self.requests))
        return LlmResponse(
            tool_calls=(LlmToolCall(tool, arguments, self.last),), finish_reason="tool_calls"
        )


def pump(storage, config, tools, model, compaction):
    def wake(user):
        storage.call("wake", user_id=user.user_id)

    while True:
        delivery = storage.call("relay.claim", owner="test", ttl=60)
        message = delivery["message"]
        if not message:
            break
        item = Inbound.from_dict(json.loads(message["item_json"]))
        user = User(message["user_id"])
        fence = storage.call(
            "lease.acquire",
            user_id=user.user_id,
            lane="consumer:" + item.kind,
            owner="test",
            ttl=60,
        )
        ctx = build_context(config, storage, storage, tools, fence)
        consumer = (UserConsumer if item.kind == "user" else ToolConsumer)(
            ctx, SimpleNamespace(wake=wake)
        )
        consumer.receive(user, item)
        consumer.evaluate(user, True)
        storage.call("relay.confirm", owner="test", token=delivery["token"], id=message["id"])
        storage.call("lease.release", user_id=user.user_id, fence=fence)
    fence = storage.call("brain.claim", owner="test-brain", ttl=60)
    if fence:
        user = User(fence["user_id"])
        ctx = build_context(config, storage, storage, tools, fence)
        brain = AgentBrain(ctx, model, compaction)
        try:
            step = brain.intake.claim(user)
            if step:
                brain.execute(user, step)
        finally:
            brain.close()
            storage.call("brain.finish", user_id=user.user_id, fence=fence, retry=False)


def test_dreaming_through_real_oath_brain_and_tool_system(stack, monkeypatch):
    record = append(stack, "I use Vim", "vim")
    database = Database(stack.tmp / "oath.sqlite")
    storage = StorageService(database)
    extensions_path = stack.tmp / "extensions"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "extensions",
        extensions_path,
        ignore=shutil.ignore_patterns("_connection.local", "__pycache__"),
    )
    (extensions_path / "tools/_connection.local").write_text(
        json.dumps(
            {
                "url": stack.url,
                "token": "s" * 40,
            }
        )
    )
    extensions = load_extensions((extensions_path,))
    registry = ToolRegistry()
    for tool in extensions.tools:
        registry.register(tool)
    skills = SkillSystem(extensions.skill_dirs)
    registry.register(SkillTool(skills))
    details = StoredDetails(storage)
    registry.register(DetailReadTool(details))
    config = SimpleNamespace(
        agent=AgentConfig(
            extension_dirs=(extensions_path,),
            skill_dir=extensions_path / "skills",
            builtin_bash=False,
            max_run_steps=40,
        )
    )
    system = ThreadedToolSystem(
        registry,
        DurableEventSink(storage),
        AllowAllPolicy(),
        store=RuntimeStore(storage),
        queue=StoredQueue(storage),
        shrinker=ResultShrinker(details, 4000, whole=frozenset({DETAIL_READ, "skill"})),
    )
    service = ToolService(system)
    with oath_gateway(stack, storage, monkeypatch):
        response = stack.public.post(
            "/context/dreams",
            json={},
            headers={
                "Idempotency-Key": "start",
            },
        )
        assert response.status_code == 202, response.text
        dream_id = response.json()["dream_id"]
        assert (
            stack.public.post(
                "/context/dreams",
                json={},
                headers={
                    "Idempotency-Key": "start",
                },
            ).json()["command_id"]
            == response.json()["command_id"]
        )
        late = append(stack, "I also use Emacs", "late")
        # The same dispatch stays byte-identical even after its injection changes.
        retried = stack.public.post(
            "/context/dreams",
            json={},
            headers={
                "Idempotency-Key": "start",
            },
        )
        assert retried.status_code == 202, retried.text
        assert retried.json()["command_id"] == response.json()["command_id"]

        def program():
            skill = yield "skill", {"action": "read", "name": "dreaming"}
            assert "Publish last" in skill

            def call(action, **kw):
                return "nostalgia", {"action": action, "dream_id": dream_id, **kw}

            page = json.loads(
                (
                    yield call(
                        "records.list",
                        query={
                            "after_id": "0",
                            "through_id": record["id"],
                            "limit": 1,
                        },
                    )
                )
            )
            assert [row["id"] for row in page["data"]["items"]] == [record["id"]]
            raw = json.loads((yield call("records.read", item_id=record["id"])))
            yield call(
                "records.mark",
                item_id=record["id"],
                etag=raw["etag"],
                operation_id="mark",
                data={"processing_state": "applied", "status": "active"},
            )
            yield call(
                "artifacts.put",
                item_id="editor",
                create=True,
                operation_id="card",
                data={
                    "content": "Uses Vim",
                    "references": [{"root_id": record["root_id"], "record_id": record["id"]}],
                },
            )
            # Published reads remain old until commit.
            assert stack.public.get("/context/injection").json()["summary"]["content"] == ""
            yield call(
                "artifacts.put",
                item_id="_index",
                create=True,
                operation_id="index",
                data={
                    "content": "Editor preference: Vim",
                    "links": ["editor"],
                },
            )
            draft = json.loads((yield call("dreams.read")))
            committed = json.loads(
                (yield call("dreams.commit", etag=draft["etag"], operation_id="commit"))
            )
            assert committed["data"]["state"] == "committed"
            injection = json.loads((yield "nostalgia", {"action": "injection"}))
            assert injection["data"]["summary"]["content"] == "Editor preference: Vim"
            matches = json.loads(
                (
                    yield (
                        "nostalgia",
                        {
                            "action": "search",
                            "data": {
                                "target": "artifacts",
                                "mode": "filter",
                                "filters": {
                                    "root_id": record["root_id"],
                                },
                            },
                        },
                    )
                )
            )
            assert [item["id"] for item in matches["data"]["items"]] == ["editor"]

        model = ScriptedModel(program())
        compaction = CompactionCoordinator(
            RuntimeStore(storage),
            LlmCompactor(model, model="test", max_output_tokens=1000),
            config.agent,
        )
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                pump(storage, config, service, model, compaction)
                state = RuntimeStore(storage).read(stack.user)
                assert not [
                    step.get("error") for step in state["steps"].values() if step.get("error")
                ], state["steps"]
                assert not [
                    call for call in state["calls"].values() if call["status"] == "failed"
                ], state["calls"]
                if (
                    any(
                        step["status"] == "completed" and not step.get("tool_calls")
                        for step in state["steps"].values()
                    )
                    and len(model.requests) >= 11
                ):
                    break
                time.sleep(0.01)
            assert stack.public.get(f"/context/dreams/{dream_id}").json()["state"] == "committed"
            injection = stack.public.get("/context/injection").json()
            assert injection["summary"]["content"] == "Editor preference: Vim"
            assert [item["id"] for item in injection["buffer"]] == [late["id"]]
            assert len(model.requests) == 11
            assert any(
                "Hymio background task" in message.content for message in model.requests[0].messages
            )
            assert all(call["status"] == "succeeded" for call in state["calls"].values())
        finally:
            compaction.shutdown()
            system.shutdown()
            database._owner.close()
