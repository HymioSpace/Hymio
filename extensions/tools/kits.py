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


class KitBuildTool(Tool):
    allow_subagent = False
    expose_channels = frozenset({"ios"})

    @property
    def definition(self):
        return ToolDefinition(
            "kit_build",
            "Create and install a small self-contained web application from the user's "
            "requirements. Use when the user asks Hymio to make an app, tracker or collection. "
            "Choose a concise name, one sentence purpose, and write a self-contained HTML/CSS/JS "
            "application page. If the page needs to persist entries, provide fields and use "
            "HymioKit.call through the sandbox bridge. A page with no fields can be static and "
            "exposes no Agent operations. The app is installed immediately for this user.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 40},
                    "tagline": {"type": "string", "minLength": 1, "maxLength": 160},
                    "description": {"type": "string", "maxLength": 400},
                    "category": {"type": "string", "minLength": 1, "maxLength": 20},
                    "item_label": {"type": "string", "minLength": 1, "maxLength": 20},
                    "accent": {
                        "type": "string",
                        "enum": ["blue", "amber", "green", "rose", "violet"],
                    },
                    "app_html": {"type": "string", "maxLength": 512000},
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
                "required": ["name", "tagline", "app_html"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        return _request(
            invocation,
            "/internal/kits/generate",
            {"spec": dict(invocation.arguments)},
        )
