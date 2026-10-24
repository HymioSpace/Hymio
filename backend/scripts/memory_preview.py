"""Local simulator fixture: real Hymio proxy + Nostalgia, synthetic data only.

uv run --with-editable ../../Nostalgia --with pytest python scripts/memory_preview.py
Build iOS with HYMIO_BACKEND_URL=http://127.0.0.1:18480; login demo / memory-demo.
This loopback-only fixture does not run Oath or external account services.
"""

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from fastapi.testclient import TestClient
from nostalgia.api import create_app
from nostalgia.bootstrap.config import Settings
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocketDisconnect

from hymio_backend.context.routes import context_routes
from hymio_backend.media.routes import media_routes
from hymio_backend.media.store import MediaStore
from hymio_backend.server import bearer, body
from hymio_backend.session_store import SessionStore

root = Path(tempfile.mkdtemp(prefix="hymio-memory-preview-"))
settings = SimpleNamespace(
    database=Path(os.environ.get("HYMIO_PREVIEW_SESSION_DB", root / "hymio.sqlite")),
    issuer="memory-preview",
    access_seconds=86400,
    refresh_seconds=86400,
    public_url="http://127.0.0.1:18480",
    origins=("http://127.0.0.1:1422",),
    service_token_file=root / "service-token",
    nostalgia_connections_file=root / "connections.json",
    oath_ws="ws://127.0.0.1:18480/agent/ws",
    model_options=("MiniMax-M2.7", "MiniMax-M3", "deepseek-flash", "Qwen/Qwen3.8-27B"),
    model_context_windows={},
)
settings.service_token_file.write_text("synthetic-preview-service-token")
sessions = SessionStore(settings)
claims = {"iss": "memory-preview", "sub": "demo", "name": "演示账号"}
uid = sessions.create_session(claims)["user_id"]
token = "synthetic-nostalgia-preview-token"
(root / "nostalgia-token").write_text(token)
settings.nostalgia_connections_file.write_text(
    json.dumps({"users": {uid: {"url": "http://127.0.0.1:18481", "token_file": "nostalgia-token"}}})
)
nostalgia = create_app(
    Settings(database=root / "nostalgia.sqlite", tokens={token: uid}, preview_max_chars=1000)
)
api = TestClient(nostalgia)
headers = {"Authorization": "Bearer " + token}
step = 0


def call(method, path, data=None, extra=None):
    global step
    step += 1
    res = api.request(
        method, path, json=data, headers={**headers, "Idempotency-Key": str(step), **(extra or {})}
    )
    assert res.status_code < 300, res.text
    return res


records = []
for text, kind, namespace in [
    ("讨论方案时，我希望先看到结论和可操作的版本，再展开依据。", "conversation", "conversation"),
    ("我不太喜欢过于正式的表达，直接一点、自然一点就好。", "conversation", "conversation"),
    ("最近在学西班牙语。想在每天散步的时候听一点简单的日常对话。", "user", "saved"),
    ("下午尽量不喝咖啡，更喜欢清淡的茶。", "conversation", "conversation"),
    ("下周三下午，与设计团队讨论新的首页方案。", "connector", "calendar"),
]:
    records.append(
        call(
            "POST",
            "/v1/records",
            {
                "item_type": "context",
                "context_type": "text",
                "context": {
                    "text": text,
                    "category": ["work", "life", "learning", "life", "work"][len(records)],
                    "title": [
                        "先看结论，再看依据",
                        "自然一点的表达",
                        "散步时学西语",
                        "下午的饮品偏好",
                        "首页方案讨论",
                    ][len(records)],
                },
                "source": {
                    "kind": kind,
                    "namespace": namespace,
                    "external_id": str(len(records) + 1),
                },
            },
        ).json()
    )
dream = call("POST", "/v1/dreams").json()["dream_id"]
for record in records:
    path = f"/v1/records/{record['id']}?dream_id={dream}"
    etag = call("GET", path).headers["etag"]
    call("PATCH", path, {"processing_state": "applied", "status": "active"}, {"If-Match": etag})
for id, text, topic, title, category, indices in [
    (
        "communication",
        "你喜欢直接、自然的交流。讨论方案时，先给结论和可操作的版本，再展开依据。",
        "交流方式",
        "先看结论，再看依据",
        "work",
        [0, 1],
    ),
    (
        "learning",
        "我喜欢在散步时听西语日常对话，利用碎片时间学习，希望轻松一点、容易坚持。",
        "语言学习",
        "散步时学西语",
        "learning",
        [2],
    ),
    (
        "daily-drinks",
        "下午尽量不喝咖啡，选择清淡的茶。",
        "日常习惯",
        "下午，喝一点清茶",
        "life",
        [3],
    ),
]:
    call(
        "PUT",
        f"/v1/artifacts/{id}?dream_id={dream}",
        {
            "content": text,
            "topics": [topic],
            "fields": {"title": title, "category": category},
            "references": [
                {"root_id": records[i]["root_id"], "record_id": records[i]["id"]} for i in indices
            ],
        },
        {"If-None-Match": "*"},
    )
call(
    "PUT",
    f"/v1/artifacts/_core?dream_id={dream}",
    {
        "content": "偏好直接、自然且有依据的表达。正在学习西语，喜欢把练习融入日常散步。",
        "fields": {"title": "关于你的概述"},
        "references": [
            {"root_id": records[i]["root_id"], "record_id": records[i]["id"]} for i in [0, 1, 2]
        ],
    },
    {"If-None-Match": "*"},
)
for source, target, kind, reason, evidence in [
    (
        ("record", records[0]["id"]),
        ("record", records[1]["id"]),
        "supplements",
        "两次陈述共同描述交流方式。",
        [0, 1],
    ),
    (
        ("artifact", "communication"),
        ("artifact", "_core"),
        "supports",
        "交流偏好是长期概述的一部分。",
        [0, 1],
    ),
    (("artifact", "learning"), ("artifact", "_core"), "supports", "概述保留了当前学习习惯。", [2]),
    (
        ("record", records[4]["id"]),
        ("artifact", "communication"),
        "related",
        "方案讨论可以参考已明确的表达偏好，不代表这次会议已经发生。",
        [0, 4],
    ),
]:
    etag = call("GET", f"/v1/dreams/{dream}").headers["etag"]
    call(
        "PUT",
        f"/v1/relations?dream_id={dream}",
        {
            "source": {"kind": source[0], "id": source[1]},
            "target": {"kind": target[0], "id": target[1]},
            "type": kind,
            "origin": "model",
            "rationale": reason,
            "evidence_refs": [
                {"root_id": records[i]["root_id"], "record_id": records[i]["id"]} for i in evidence
            ],
        },
        {"If-Match": etag},
    )
call(
    "PUT",
    f"/v1/artifacts/_index?dream_id={dream}",
    {"content": "交流偏好与正在关注的事。", "links": ["communication", "learning"]},
    {"If-None-Match": "*"},
)
etag = call("GET", f"/v1/dreams/{dream}").headers["etag"]
call("POST", f"/v1/dreams/{dream}/commit", extra={"If-Match": etag})
server = uvicorn.Server(
    uvicorn.Config(nostalgia, host="127.0.0.1", port=18481, log_level="warning")
)
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.02)


async def options(request):
    return JSONResponse({"login_method": "account", "signup_enabled": False})


async def login(request):
    data = await request.json()
    if data.get("username") != "demo" or data.get("password") != "memory-demo":
        return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse(sessions.create_session(claims))


async def empty(request):
    if request.url.path == "/tasks":
        tasks = []
        for index, title in enumerate(["整理本周阅读笔记", "准备周末出行清单", "明天的语言练习"]):
            tasks.append(
                {
                    "id": f"preview-plan-{index}",
                    "title": title,
                    "objective": title,
                    "success_criteria": "完成清单",
                    "state": "active",
                    "source": "user",
                    "updated_at": time.time() - index,
                    "schedule": {
                        "mode": "once",
                        "at": f"2026-11-0{index + 1}T09:00:00+08:00",
                        "timezone": "Asia/Shanghai",
                    },
                    "runs": [],
                }
            )
        return JSONResponse({"tasks": tasks})
    return JSONResponse({"tasks": [], "models": []})


# Loopback-only synthetic event stream for visual inspection of the real chat UI.
preview_sockets = set()
preview_events = []
for kind, payload in [
    (
        "user.message",
        {
            "content": "帮我整理一下杭州出行的安排。",
            "message_id": "preview-message",
            "user_context": {"hymio_message_id": "preview-message"},
        },
    ),
    (
        "assistant.message",
        {
            "content": "好，我会把预算、行程和待确认的事项理清楚。",
            "step_id": "preview-step",
            "tool_calls": [],
        },
    ),
    ("step.status", {"step_id": "preview-step", "status": "completed"}),
]:
    preview_events.append(
        {
            "v": 2,
            "type": "event",
            "user_id": uid,
            "event_seq": len(preview_events) + 1,
            "event_type": kind,
            "payload": payload,
            "occur_dt": datetime.now(timezone.utc).isoformat(),
        }
    )


async def preview_socket(ws):
    await ws.accept()
    try:
        attach = await ws.receive_json()
        sessions.verify(attach.get("payload", {}).get("credential", ""))
        checkpoint = len(preview_events)
        await ws.send_json({"v": 2, "type": "ack", "id": attach.get("id"), "user_id": uid})
        await ws.send_json(
            {
                "v": 2,
                "type": "conversation.snapshot",
                "events": preview_events,
                "checkpoint": checkpoint,
                "before_cursor": None,
                "has_more": False,
            }
        )
        await ws.send_json(
            {
                "v": 2,
                "type": "offline.start",
                "after_cursor": checkpoint,
                "through_cursor": checkpoint,
            }
        )
        await ws.send_json({"v": 2, "type": "offline.end", "through_cursor": checkpoint})
        preview_sockets.add(ws)
        while True:
            command = await ws.receive_json()
            if command.get("type") == "ping":
                await ws.send_json({"v": 2, "type": "pong", "id": command.get("id")})
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        preview_sockets.discard(ws)


async def preview_compaction(request):
    data = await request.json()
    if data.get("status") not in {"started", "ready", "applied", "failed"}:
        return JSONResponse({"error": "invalid_status"}, 400)
    payload = {"compression_id": "synthetic-compression", "covers": 116, "mode": "sync", **data}
    if payload["status"] in {"ready", "applied"}:
        payload.update(input_tokens=147495, output_tokens=270, context_window=128000)
    event = {
        "v": 2,
        "type": "event",
        "user_id": uid,
        "event_seq": len(preview_events) + 1,
        "event_type": "context.compaction",
        "payload": payload,
        "occur_dt": datetime.now(timezone.utc).isoformat(),
    }
    preview_events.append(event)
    for ws in tuple(preview_sockets):
        try:
            await ws.send_json(event)
        except (RuntimeError, WebSocketDisconnect):
            preview_sockets.discard(ws)
    return JSONResponse({"status": "sent", "clients": len(preview_sockets)})


app = Starlette(
    routes=[
        WebSocketRoute("/agent/ws", preview_socket),
        Route("/preview/compaction", preview_compaction, methods=["POST"]),
        Route("/auth/options", options),
        Route("/auth/account", login, methods=["POST"]),
        Route("/auth/logout", empty, methods=["POST"]),
        Route("/tasks", empty),
        Route("/models", empty),
    ]
    + context_routes(settings, sessions, bearer, body)
    + media_routes(settings, sessions, bearer, body, MediaStore(sessions))
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

print(
    "Synthetic memory fixture ready at http://127.0.0.1:18480; login demo / memory-demo", flush=True
)
uvicorn.run(app, host="127.0.0.1", port=18480, log_level="warning")
