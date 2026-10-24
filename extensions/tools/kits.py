import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.protocol.datatype import ToolDefinition, ToolResult
from core.protocol.error import ToolExecutionError
from core.protocol.interface import Tool


def _request(invocation, path, payload):
    configured = os.environ.get("HYMIO_KIT_CONNECTION_FILE")
    config_path = (
        Path(configured) if configured else Path(__file__).with_name("_connection.local")
    )
    try:
        config = json.loads(config_path.read_text())
        request = Request(
            config["url"].rstrip("/") + path,
            data=json.dumps(
                {**payload, "user_id": invocation.user.user_id},
                ensure_ascii=False,
                allow_nan=False,
            ).encode(),
            headers={
                "Authorization": "Bearer " + config["token"],
                "Content-Type": "application/json",
            },
        )
        timeout = (
            min(30, max(0.1, invocation.deadline - time.monotonic()))
            if invocation.deadline
            else 30
        )
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ToolExecutionError("应用返回内容过大")
            return ToolResult(json.loads(raw))
    except HTTPError as exc:
        detail = exc.read(8192).decode("utf-8", errors="replace")
        if exc.code == 409 and "kit_not_installed" in detail:
            raise ToolExecutionError(
                "这个应用尚未加入。请让用户在“应用”中添加后再操作。"
            ) from exc
        raise ToolExecutionError(f"应用操作被拒绝：{exc.code} {detail}") from exc
    except (OSError, ValueError, KeyError, URLError, TimeoutError) as exc:
        raise ToolExecutionError(
            "应用操作暂时无法确认结果。不要用新的调用重复写入。"
        ) from exc


def _dev_request(invocation, action, arguments):
    result = _request(
        invocation,
        "/internal/kits/dev",
        {
            "agent_id": invocation.user.agent_id,
            "dev_action": action,
            "arguments": arguments,
            "invocation_id": invocation.invocation_id,
        },
    ).content
    if not isinstance(result, dict):
        raise ToolExecutionError("应用开发服务返回了无效结果")
    return ToolResult(result)


class KitTool(Tool):
    allow_subagent = False
    expose_channels = frozenset({"ios"})

    @property
    def definition(self):
        return ToolDefinition(
            "kit_call",
            "Call an operation on one of the applications installed for this user. The "
            "runtime injects the current installed application list and exact operation input "
            "schemas into the system prompt. Read that list and call the requested kit_id and "
            "operation directly; never call a generic discovery or list action. Never invent "
            "an operation, and never claim a write succeeded without its result.",
            {
                "type": "object",
                "properties": {
                    "kit_id": {"type": "string", "minLength": 1, "maxLength": 160},
                    "operation": {"type": "string", "minLength": 1, "maxLength": 160},
                    "arguments": {"type": "object"},
                },
                "required": ["kit_id", "operation", "arguments"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        kit_id = invocation.arguments.get("kit_id")
        operation = invocation.arguments.get("operation")
        arguments = invocation.arguments.get("arguments")
        if (
            not isinstance(kit_id, str)
            or not kit_id
            or not isinstance(operation, str)
            or not operation
            or not isinstance(arguments, dict)
        ):
            raise ToolExecutionError("Invalid application operation")
        return _request(
            invocation,
            "/internal/kits",
            {
                "kit_id": kit_id,
                "operation": operation,
                "arguments": arguments,
                "invocation_id": invocation.invocation_id,
            },
        )


class KitDevTool(Tool):
    subagent_only = True
    allow_subagent = True
    expose_channels = frozenset({"ios"})

    @property
    def definition(self):
        return ToolDefinition(
            "kit_dev",
            "Read, patch, check and publish the React/Python application bound to this coding "
            "context. The file tree, API contract and current source_revision are in context. "
            "Read exact file chunks before changing them. Use small exact patches, run check "
            "until it succeeds, then publish with a concise change summary. Do not invent files, "
            "do not expose internal IDs to users, and never claim a change is live before publish.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "patch", "check", "publish"],
                    },
                    "path": {"type": "string", "maxLength": 200},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 3000},
                    "expected_revision": {
                        "type": "string",
                        "pattern": r"^[0-9a-f]{64}$",
                    },
                    "changes": {
                        "type": "array",
                        "maxItems": 24,
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "maxLength": 200},
                                "old": {"type": "string", "maxLength": 12000},
                                "new": {"type": "string", "maxLength": 12000},
                                "content": {"type": "string", "maxLength": 12000},
                            },
                            "required": ["path"],
                            "additionalProperties": False,
                        },
                    },
                    "deletions": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {"type": "string", "maxLength": 200},
                    },
                    "summary": {"type": "string", "maxLength": 2000},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        if not invocation.user.agent_id:
            raise ToolExecutionError("应用开发工具只允许在独立 coding context 中使用")
        action = invocation.arguments.get("action")
        if action not in {"read", "patch", "check", "publish"}:
            raise ToolExecutionError("无效的应用开发操作")
        arguments = {
            key: value
            for key, value in invocation.arguments.items()
            if key != "action"
        }
        return _dev_request(invocation, action, arguments)


class KitBuildTool(Tool):
    allow_subagent = False
    expose_channels = frozenset({"ios"})

    @property
    def definition(self):
        return ToolDefinition(
            "kit_build",
            "Create or update a real application through its dedicated coding agent. Use action "
            "create for a new app, or action edit with an installed generated kit_id. Give a "
            "concrete product brief and acceptance criteria; do not write source code in the main "
            "conversation. The coding agent owns a React frontend, bounded Python API and version "
            "history in the background. Returned status=coding means work was accepted, not that "
            "the app is already published.",
            {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "edit"]},
                    "kit_id": {"type": "string", "maxLength": 160},
                    "name": {"type": "string", "minLength": 1, "maxLength": 40},
                    "tagline": {"type": "string", "minLength": 1, "maxLength": 160},
                    "description": {"type": "string", "maxLength": 400},
                    "category": {"type": "string", "minLength": 1, "maxLength": 20},
                    "item_label": {"type": "string", "minLength": 1, "maxLength": 20},
                    "accent": {
                        "type": "string",
                        "enum": ["blue", "amber", "green", "rose", "violet"],
                    },
                    "requirements": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 20000,
                    },
                    "fields": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {
                                    "type": "string",
                                    "pattern": r"^[a-z][a-z0-9_]{0,40}$",
                                },
                                "label": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 40,
                                },
                                "type": {
                                    "type": "string",
                                    "enum": ["text", "number", "boolean", "date"],
                                },
                                "required": {"type": "boolean"},
                            },
                            "required": ["key", "label", "type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["action", "requirements"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        action = invocation.arguments.get("action")
        if action == "create":
            spec = {
                key: value
                for key, value in invocation.arguments.items()
                if key
                in {
                    "name",
                    "tagline",
                    "description",
                    "category",
                    "item_label",
                    "accent",
                    "fields",
                    "requirements",
                }
            }
            if not spec.get("name") or not spec.get("tagline"):
                raise ToolExecutionError("创建应用需要名称和一句用途")
            payload = {"action": "create", "spec": spec}
        elif action == "edit":
            kit_id = invocation.arguments.get("kit_id")
            if not isinstance(kit_id, str) or not kit_id:
                raise ToolExecutionError("编辑应用需要 kit_id")
            payload = {
                "action": "edit",
                "kit_id": kit_id,
                "requirements": invocation.arguments["requirements"],
            }
        else:
            raise ToolExecutionError("应用构建操作无效")
        return _request(
            invocation,
            "/internal/kits/build",
            {**payload, "invocation_id": invocation.invocation_id},
        )
