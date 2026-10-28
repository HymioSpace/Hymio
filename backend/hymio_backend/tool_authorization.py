"""Deterministic product policy for Agent tool actions and user-facing modes."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.routing import Route

from .session_store import Unauthorized

MODE_READ_ONLY = "read_only"
MODE_GUIDED = "guided"
MODE_AUTONOMOUS = "autonomous"
MODES = (MODE_READ_ONLY, MODE_GUIDED, MODE_AUTONOMOUS)
POLICY_VERSION = "hymio-tool-policy-v1"

_DENY_COMMAND = re.compile(
    r"\b(?:sudo|su)\b|"
    r"\bsecurity\s+(?:dump-keychain|find-generic-password|find-internet-password|export)\b|"
    r"\brm\s+-[^\n;&|]*r[^\n;&|]*f[^\n;&|]*(?:/|~|\$HOME)\b|"
    r"\blaunchctl\s+(?:bootstrap|disable)\b|"
    r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash|zsh)\b",
    re.IGNORECASE,
)

_SAFE_INTERNAL_ACTIONS = {
    "tasks": {"list", "get", "capture", "progress", "complete", "fail", "block", "start"},
    "connections": {"list", "read"},
    "recall": {"search", "read", "retrieve", "related"},
    "browser": {"tabs", "snapshot"},
}


def _grant_key(user_id, tool, arguments):
    action = arguments.get("action", "")
    target = (
        arguments.get("url")
        or arguments.get("page_id")
        or arguments.get("device_id")
        or arguments.get("kit_id")
        or ""
    )
    command = arguments.get("command", "")
    if tool == "bash" and isinstance(command, str):
        target = command.strip().splitlines()[0][:160]
    raw = json.dumps(
        [user_id, tool, action, target],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _safe_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname


def _private_host(host):
    if host in {"localhost"} or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


class ToolAuthorizationService:
    def __init__(self, settings, sessions):
        self.settings = settings
        self.sessions = sessions
        with sessions.transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS tool_authorization_preferences ("
                "user_id TEXT PRIMARY KEY, mode TEXT NOT NULL, updated_at REAL NOT NULL)"
            )

    def mode(self, user_id):
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT mode FROM tool_authorization_preferences WHERE user_id=?",
                (user_id,),
            ).fetchone()
        return row["mode"] if row else MODE_GUIDED

    def set_mode(self, user_id, mode):
        if mode not in MODES:
            raise ValueError("invalid_mode")
        with self.sessions.transaction() as db:
            db.execute(
                "INSERT INTO tool_authorization_preferences VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode,"
                "updated_at=excluded.updated_at",
                (user_id, mode, time.time()),
            )

    def settings_view(self, user_id):
        return {"mode": self.mode(user_id), "modes": list(MODES)}

    def check(self, data):
        user_id = data.get("user_id")
        tool = data.get("tool")
        arguments = data.get("arguments")
        if (
            not isinstance(user_id, str)
            or not 1 <= len(user_id) <= 160
            or not isinstance(tool, str)
            or not 1 <= len(tool) <= 64
            or not isinstance(arguments, dict)
        ):
            raise ValueError("invalid_policy_request")
        mode = self.mode(user_id)
        action = arguments.get("action")
        reason = ""

        if tool == "bash":
            command = arguments.get("command")
            if not isinstance(command, str) or not command.strip():
                return self._deny("Invalid shell command")
            if _DENY_COMMAND.search(command):
                return self._deny("This command crosses a protected local security boundary")
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not execute shell commands")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许在所选电脑上运行命令？",
                summary="命令将在选中的设备上执行，并可能读取或修改其文件。",
                risk="high",
                effects=["execute", "local_access"],
                target={
                    "kind": "device",
                    "id": str(arguments.get("device_id", "")),
                    "label": "所选电脑",
                },
                scopes=["once", "run"],
            )

        if tool == "computer":
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not control the desktop")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许操作所选电脑的桌面？",
                summary="Hymio 将发送桌面鼠标、键盘或截图操作。",
                risk="high",
                effects=["desktop_control"],
                target={
                    "kind": "device",
                    "id": str(arguments.get("device_id", "")),
                    "label": "所选电脑",
                },
                scopes=["once", "run"],
            )

        if tool == "browser":
            if action in {"tabs", "snapshot"}:
                return self._allow("Bounded browser read")
            host = _safe_url(arguments.get("url"))
            if action == "navigate" and host is None:
                return self._deny("Navigation requires a public HTTP(S) URL")
            if host and _private_host(host):
                return self._deny("Browser navigation cannot reach a private or loopback host")
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not modify browser state")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许操作浏览器页面？",
                summary="Hymio 将导航、点击、填写、提交或读取页面状态。",
                risk="high",
                effects=["browser_control"],
                target={
                    "kind": "origin" if host else "page",
                    "id": host
                    or str(arguments.get("page_id", ""))
                    or str(arguments.get("device_id", "")),
                    "label": host
                    or str(arguments.get("page_id", ""))
                    or "所选浏览器",
                },
                scopes=["once", "run"],
            )

        if tool == "kit_call":
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not invoke application operations")
            if mode == MODE_AUTONOMOUS:
                return self._allow("Autonomous application operation")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许调用应用操作？",
                summary="该操作可能修改你在应用里的数据。",
                risk="medium",
                effects=["app_write"],
                target={
                    "kind": "app",
                    "id": str(arguments.get("kit_id", "")),
                    "label": str(arguments.get("operation", "应用操作")),
                },
                scopes=["once", "run"],
            )

        if tool == "tasks" and action not in _SAFE_INTERNAL_ACTIONS["tasks"]:
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not change tasks")
            if mode == MODE_AUTONOMOUS and action not in {"delete", "cancel"}:
                return self._allow("Autonomous task operation")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许修改任务安排？",
                summary="该操作可能创建、取消或改变未来执行的工作。",
                risk="medium",
                effects=["scheduled_work"],
                target={"kind": "task", "id": str(arguments.get("task_id", "")), "label": "任务"},
                scopes=["once", "run"],
            )

        if tool in {
            "cli",
            "devices",
            "recall",
            "multimodal_understand",
            "skill",
            "detail_read",
        }:
            return self._allow(reason)
        if tool == "connections":
            return self._allow("Connected-source read")
        if tool == "tasks" and action in {"list", "get"}:
            return self._allow("Bounded task read")
        if tool == "tasks":
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not change task state")
            return self._allow("Bounded task progress")
        if tool in {"remember", "notify_user", "react", "image_generate", "kit_build", "kit_dev"}:
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not perform writes or generation")
            return self._allow("Bounded reversible product action")
        if tool == "browser" and action in _SAFE_INTERNAL_ACTIONS["browser"]:
            return self._allow("Bounded browser read")

        if mode == MODE_READ_ONLY:
            return self._deny("Read-only mode does not run unclassified tools")
        return self._ask(
            user_id,
            tool,
            arguments,
            title=f"允许运行 {tool}？",
            summary="这个操作没有足够的自动分类信息，需要你确认。",
            risk="medium",
            effects=["unknown"],
            target={"kind": "tool", "id": tool, "label": tool},
            scopes=["once"],
        )

    @staticmethod
    def _allow(reason=""):
        return {
            "verdict": "allow",
            "reason": reason,
            "policy_version": POLICY_VERSION,
        }

    @staticmethod
    def _deny(reason):
        return {
            "verdict": "deny",
            "reason": reason,
            "policy_version": POLICY_VERSION,
        }

    @staticmethod
    def _ask(
        user_id,
        tool,
        arguments,
        *,
        title,
        summary,
        risk,
        effects,
        target,
        scopes,
    ):
        key = _grant_key(user_id, tool, arguments)
        return {
            "verdict": "ask",
            "reason": summary,
            "grant_key": key,
            "policy_version": POLICY_VERSION,
            "approval": {
                "title": title,
                "summary": summary,
                "risk": risk,
                "effects": effects,
                "target": target,
                "scope_options": scopes,
                "grant_key": key,
                "policy_version": POLICY_VERSION,
            },
        }


def tool_authorization_routes(settings, sessions, service, bearer, body):
    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            path = request.url.path
            if path == "/internal/tool-authorization/check":
                token_file = settings.oath_admin_token_file
                if token_file is None:
                    return JSONResponse({"error": "policy_unavailable"}, 503)
                expected = token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                return JSONResponse(service.check(await body(request, limit=65536)))
            identity = sessions.verify(bearer(request))
            user_id = identity["user_id"]
            if path == "/settings/tool-authorization":
                if request.method == "POST":
                    service.set_mode(user_id, (await body(request)).get("mode"))
                return JSONResponse(service.settings_view(user_id))
            raise Unauthorized()
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ValueError:
            return JSONResponse({"error": "invalid_tool_authorization"}, 400)

    return [
        Route(
            "/internal/tool-authorization/check",
            endpoint,
            methods=["POST"],
        ),
        Route(
            "/settings/tool-authorization",
            endpoint,
            methods=["GET", "POST"],
        ),
    ]
