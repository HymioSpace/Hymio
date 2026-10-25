import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from hymio_backend.context.routes import context_routes
from hymio_backend.kits.routes import kit_routes
from hymio_backend.kits.service import KitsService
from hymio_backend.session_store import SessionStore

REPO = Path(__file__).resolve().parents[2]
OATH = REPO.parent / "Oath"
pytestmark = pytest.mark.skipif(not OATH.is_dir(), reason="requires sibling Oath checkout")


def serve(app):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", lifespan="off", access_log=False)
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Test service did not start")
        time.sleep(0.01)
    return f"http://127.0.0.1:{listener.getsockname()[1]}", server, thread


def stop(server, thread):
    server.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive()


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_ui_and_unified_kit_tool_reach_separate_kit_host(tmp_path):
    sys.path.insert(0, str(OATH))
    sys.path.insert(0, str(REPO / "services/kit-host"))
    from bootstrap.common.extension_loader import load_extensions
    from core.protocol.datatype import ToolInvocation, User
    token = "kit-service-token-" + "x" * 40
    token_file = tmp_path / "service-token"
    token_file.write_text(token)
    agent_id = "c" * 32
    oath_state = {"status": "succeeded", "result": "第一版应用已完成。"}

    async def oath_endpoint(request):
        data = await request.json()
        action = request.path_params["action"]
        if action == "spawn":
            assert data["defer_start"] is True
            return JSONResponse({"agent_id": agent_id, "status": "waiting"})
        if action == "continue":
            oath_state["status"] = "running"
            return JSONResponse({"agent_id": agent_id, "status": "running"})
        if action == "get":
            return JSONResponse(
                {
                    "agent_id": agent_id,
                    "status": oath_state["status"],
                    "result": oath_state["result"],
                }
            )
        if action == "cancel":
            oath_state["status"] = "cancelled"
            return JSONResponse({"agent_id": agent_id, "status": "cancelled"})
        return JSONResponse({"error": "not_found"}, 404)

    oath_url, oath_server, oath_thread = serve(
        Starlette(routes=[Route("/subagents/{action}", oath_endpoint, methods=["POST"])])
    )

    host_port = free_port()
    host_process = subprocess.Popen(
        [sys.executable, "-m", "kit_host"],
        cwd=REPO / "services/kit-host",
        env={
            **os.environ,
            "PYTHONPATH": str(REPO / "services/kit-host"),
            "KIT_HOST_DATABASE": str(tmp_path / "kit-host.sqlite3"),
            "KIT_HOST_MANIFESTS_DIR": str(REPO / "kits"),
            "KIT_HOST_HOST": "127.0.0.1",
            "KIT_HOST_PORT": str(host_port),
            "KIT_HOST_TOKEN_FILE": str(token_file),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    host_url = f"http://127.0.0.1:{host_port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if host_process.poll() is not None:
            raise RuntimeError(host_process.stdout.read())
        try:
            with httpx.Client(timeout=1, trust_env=False) as probe:
                if probe.get(host_url + "/health").status_code == 200:
                    break
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    else:
        host_process.terminate()
        raise RuntimeError("Kit Host process did not start")
    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        public_url="http://127.0.0.1",
        access_seconds=3600,
        refresh_seconds=3600,
        origins=(),
        service_token_file=token_file,
        kits_url=host_url,
        oath_biz=oath_url,
    )
    sessions = SessionStore(settings)
    alice = sessions.create_session({"iss": "synthetic", "sub": "alice", "name": "Alice"})
    bob = sessions.create_session({"iss": "synthetic", "sub": "bob", "name": "Bob"})
    downstream = httpx.AsyncClient(timeout=10, trust_env=False)
    service = KitsService(settings, downstream)

    async def body(request, *, limit=16384):
        return await request.json()

    def bearer(request):
        return request.headers.get("authorization", "").removeprefix("Bearer ")

    backend_app = Starlette(
        routes=(
            context_routes(settings, sessions, bearer, body, kits=service)
            + kit_routes(settings, sessions, service, bearer, body)
        )
    )
    backend_url, backend_server, backend_thread = serve(backend_app)

    connection = tmp_path / "kit-connection.json"
    connection.write_text(
        __import__("json").dumps({"url": backend_url, "token": token})
    )
    os.environ["HYMIO_KIT_CONNECTION_FILE"] = str(connection)
    module_spec = importlib.util.spec_from_file_location(
        "hymio_kit_tools_e2e", REPO / "extensions/tools/kits.py"
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    discovered = load_extensions(
        [REPO / "extensions"], kinds=frozenset({"tools"})
    ).tools
    tool_names = {tool.definition.name for tool in discovered}
    assert {"kit_call", "kit_build", "kit_dev"} <= tool_names
    assert next(
        tool for tool in discovered if tool.definition.name == "kit_dev"
    ).subagent_only is True
    assert all(
        tool.expose_channels == frozenset({"ios"})
        for tool in discovered
        if tool.definition.name in {"kit_call", "kit_build", "kit_dev"}
    )
    assert "channels: [ios]" in (
        REPO / "extensions/skills/kit-builder/SKILL.md"
    ).read_text()
    assert not {
        "ledger_record_expense",
        "ledger_recent_entries",
        "ledger_month_summary",
    } & tool_names
    headers = {"Authorization": "Bearer " + alice["access_token"]}
    try:
        with httpx.Client(timeout=10, trust_env=False) as http:
            from core.protocol.error import ToolExecutionError

            try:
                module.KitTool().execute(
                    ToolInvocation(
                        user=User(alice["user_id"]),
                        invocation_id="not-installed",
                        arguments={
                            "kit_id": "hymio.ledger",
                            "operation": "summary",
                            "arguments": {},
                        },
                        deadline=None,
                    )
                )
            except ToolExecutionError as exc:
                assert "尚未加入" in str(exc)
            else:
                raise AssertionError("Direct tool must reject an uninstalled application")
            assert (
                http.post(
                    backend_url + "/kits/hymio.ledger/install", headers=headers
                ).status_code
                == 200
            )
            ui_write = http.post(
                backend_url + "/kits/hymio.ledger/actions/entries.create",
                headers={**headers, "Idempotency-Key": "ui-e2e"},
                json={"amount": 35, "category": "food", "note": "界面记录"},
            )
            assert ui_write.status_code == 200

            read = module.KitTool().execute(
                ToolInvocation(
                    user=User(alice["user_id"]),
                    invocation_id="agent-read-1",
                    arguments={
                        "kit_id": "hymio.ledger",
                        "operation": "entries.list",
                        "arguments": {},
                    },
                    deadline=None,
                )
            )
            assert read.content["items"][0]["note"] == "界面记录"
            assert read.content["items"][0]["amount"] == 35

            tool = module.KitTool()
            invocation = ToolInvocation(
                user=User(alice["user_id"]),
                invocation_id="agent-write-1",
                arguments={
                    "kit_id": "hymio.ledger",
                    "operation": "entries.create",
                    "arguments": {
                        "amount": 12.5,
                        "category": "transport",
                        "note": "Agent 记录",
                    },
                },
                deadline=None,
            )
            first = tool.execute(invocation)
            second = tool.execute(invocation)
            assert first.content["entry"]["id"] == second.content["entry"]["id"]

            view = http.post(
                backend_url + "/kits/hymio.ledger/actions/entries.list",
                headers=headers,
                json={},
            )
            assert view.status_code == 200
            entries = view.json()["result"]["items"]
            assert [item["note"] for item in entries].count("Agent 记录") == 1

            bob_headers = {"Authorization": "Bearer " + bob["access_token"]}
            assert (
                http.post(
                    backend_url + "/kits/hymio.ledger/actions/summary",
                    headers=bob_headers,
                    json={},
                ).status_code
                == 409
            )
            bob_catalog = http.get(backend_url + "/kits", headers=bob_headers).json()
            assert bob_catalog["kits"][0]["installed"] is False

            built = module.KitBuildTool().execute(
                ToolInvocation(
                    user=User(alice["user_id"]),
                    invocation_id="build-water-kit",
                    arguments={
                        "action": "create",
                        "name": "饮水记录",
                        "tagline": "记下每天喝了多少水。",
                        "category": "生活",
                        "item_label": "杯水",
                        "accent": "blue",
                        "requirements": (
                            "做一个安静、清晰的饮水首页，显示今天累计杯数、最近记录，"
                            "并在键盘上方提供添加动作。不要编造目标值。"
                        ),
                        "fields": [
                            {
                                "key": "amount",
                                "label": "杯数",
                                "type": "number",
                                "required": True,
                            },
                            {
                                "key": "note",
                                "label": "备注",
                                "type": "text",
                                "required": False,
                            },
                        ],
                    },
                    deadline=None,
                )
            )
            generated_id = built.content["kit_id"]
            assert generated_id.startswith("user.")
            assert built.content["status"] == "coding"

            coding_user = User(alice["user_id"], agent_id)
            coding_context = http.post(
                backend_url + "/internal/agent/context",
                headers={"authorization": "Bearer " + token},
                json={
                    "user_id": alice["user_id"],
                    "agent_id": agent_id,
                    "channel": "ios",
                },
            )
            coding_context.raise_for_status()
            assert "React frontend" in coding_context.json()["content"]
            assert "web/src/App.jsx" in coding_context.json()["content"]
            assert "hymio.ledger" not in coding_context.json()["content"]
            source = module.KitDevTool().execute(
                ToolInvocation(
                    user=coding_user,
                    invocation_id="dev-read-1",
                    arguments={
                        "action": "read",
                        "path": "web/src/App.jsx",
                        "limit": 3000,
                    },
                    deadline=None,
                )
            ).content
            assert source["content"]
            patched = module.KitDevTool().execute(
                ToolInvocation(
                    user=coding_user,
                    invocation_id="dev-patch-1",
                    arguments={
                        "action": "patch",
                        "expected_revision": source["source_revision"],
                        "changes": [
                            {
                                "path": "web/src/App.jsx",
                                "old": "<h1>{DISPLAY.name}</h1>",
                                "new": "<h1>今日饮水</h1>",
                            }
                        ],
                    },
                    deadline=None,
                )
            ).content
            checked = module.KitDevTool().execute(
                ToolInvocation(
                    user=coding_user,
                    invocation_id="dev-check-1",
                    arguments={"action": "check"},
                    deadline=None,
                )
            ).content
            assert checked["ok"] is True, checked
            published = module.KitDevTool().execute(
                ToolInvocation(
                    user=coding_user,
                    invocation_id="dev-publish-1",
                    arguments={
                        "action": "publish",
                        "expected_revision": patched["source_revision"],
                        "summary": "完成饮水首页和 Python 数据结构",
                    },
                    deadline=None,
                )
            ).content
            assert published["installed"] is True
            dynamic = http.post(
                backend_url + "/internal/agent/context",
                headers={"authorization": "Bearer " + token},
                json={"user_id": alice["user_id"], "channel": "ios"},
            )
            dynamic.raise_for_status()
            assert generated_id in dynamic.json()["content"]
            assert "items.create" in dynamic.json()["content"]
            assert len(dynamic.json()["content"]) <= 16000
            web_dynamic = http.post(
                backend_url + "/internal/agent/context",
                headers={"authorization": "Bearer " + token},
                json={"user_id": alice["user_id"], "channel": "web"},
            )
            web_dynamic.raise_for_status()
            assert "## Applications" not in web_dynamic.json()["content"]
            assert generated_id not in web_dynamic.json()["content"]
            assert "kit_call" not in web_dynamic.json()["content"]
            generated_write = module.KitTool().execute(
                ToolInvocation(
                    user=User(alice["user_id"]),
                    invocation_id="generated-write-1",
                    arguments={
                        "kit_id": generated_id,
                        "operation": "items.create",
                        "arguments": {"amount": 5, "note": "下午"},
                    },
                    deadline=None,
                )
            )
            assert generated_write.content["count"] == 1
            generated_view = http.post(
                backend_url + "/kits/" + generated_id + "/actions/items.list",
                headers=headers,
                json={},
            )
            generated_view.raise_for_status()
            assert generated_view.json()["result"]["count"] == 1
            generated_app = http.get(
                backend_url + "/kits/" + generated_id + "/app", headers=headers
            )
            generated_app.raise_for_status()
            assert 'id="root"' in generated_app.json()["html"]

            edited = module.KitBuildTool().execute(
                ToolInvocation(
                    user=User(alice["user_id"]),
                    invocation_id="edit-water-kit",
                    arguments={
                        "action": "edit",
                        "kit_id": generated_id,
                        "requirements": "增加按日期查看最近记录，不改变已有饮水量字段。",
                    },
                    deadline=None,
                )
            ).content
            assert edited["accepted"] is True
            editor = http.get(
                backend_url + "/kits/" + generated_id + "/editor", headers=headers
            )
            editor.raise_for_status()
            assert editor.json()["coding_agent_id"] == agent_id
            assert editor.json()["agent_status"] == "running"
            assert editor.json()["messages"]
            assert [message["author"] for message in editor.json()["messages"]] == [
                "main_agent",
                "main_agent",
            ]
            generated_after_edit = http.post(
                backend_url + "/kits/" + generated_id + "/actions/items.list",
                headers=headers,
                json={},
            )
            generated_after_edit.raise_for_status()
            assert generated_after_edit.json()["result"]["count"] == 1

            deleted = module.KitTool().execute(
                ToolInvocation(
                    user=User(alice["user_id"]),
                    invocation_id="delete-water-kit",
                    arguments={
                        "kit_id": generated_id,
                        "operation": "app.delete",
                        "arguments": {"confirmation": "DELETE"},
                    },
                    deadline=None,
                )
            ).content
            assert deleted == {"deleted": True}
            catalog_after_delete = http.get(
                backend_url + "/kits", headers=headers
            ).json()["kits"]
            assert generated_id not in {item["id"] for item in catalog_after_delete}
            assert (
                http.get(
                    backend_url + "/kits/" + generated_id + "/app", headers=headers
                ).status_code
                == 409
            )
    finally:
        os.environ.pop("HYMIO_KIT_CONNECTION_FILE", None)
        import asyncio

        asyncio.run(downstream.aclose())
        stop(backend_server, backend_thread)
        stop(oath_server, oath_thread)
        host_process.terminate()
        host_process.wait(timeout=5)
