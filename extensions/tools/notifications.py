import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.protocol.datatype import ToolDefinition, ToolResult
from core.protocol.error import ToolExecutionError
from core.protocol.interface import Tool


class NotifyUserTool(Tool):
    allow_subagent = False

    @property
    def definition(self):
        return ToolDefinition(
            "notify_user",
            "Send a short product notification when meaningful work starts or reaches a result "
            "the user should see outside the app. Use after tasks.start succeeds for scheduled "
            "work, before the final reply for a long-running request, and when a run is blocked "
            "and needs the user. Do not notify immediate answers, intermediate tool steps, retries "
            "or routine progress. Supply a neutral summary without secrets, tool arguments or "
            "private conversation content. The server applies preferences and foreground "
            "suppression; report delivery only when the result says status=sent.",
            {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["started", "completion", "attention", "chat_reply"],
                    },
                    "summary": {"type": "string", "maxLength": 180},
                    "task_id": {"type": "string", "maxLength": 160},
                    "run_id": {"type": "string", "maxLength": 160},
                },
                "required": ["kind"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        config = json.loads(Path(__file__).with_name("_connection.local").read_text())
        data = {
            **invocation.arguments,
            "user_id": invocation.user.user_id,
            "request_id": invocation.invocation_id,
        }
        request = Request(
            config["url"] + "/internal/notifications",
            data=json.dumps(data, ensure_ascii=False).encode(),
            headers={
                "Authorization": "Bearer " + config["token"],
                "Content-Type": "application/json",
            },
        )
        timeout = (
            min(20, max(0.1, invocation.deadline - time.monotonic()))
            if invocation.deadline
            else 20
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return ToolResult(json.loads(response.read(16384)))
        except HTTPError as exc:
            raise ToolExecutionError(
                "Notification request rejected: " + str(exc.code)
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise ToolExecutionError(
                "Notification status is uncertain; do not claim it was delivered."
            ) from exc
