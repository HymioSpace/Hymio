import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.protocol.datatype import ToolDefinition, ToolResult
from core.protocol.error import ToolExecutionError
from core.protocol.interface import Tool


class TasksTool(Tool):
    allow_subagent = False

    @property
    def definition(self):
        return ToolDefinition(
            "tasks",
            "Manage durable tasks and scheduled work. Create requires title, objective and success_criteria. "
            "For app.task.due call start(run_id) before acting; cancelled runs must not execute. "
            "Record progress, complete/fail/block with content. Delegate a started run for independent asynchronous work. "
            "Schedule: mode now/once/daily/weekly, timezone IANA; once at ISO8601 with offset; daily/weekly time HH:MM, weekday Monday=0. "
            "Never poll in a loop; delegated completion arrives automatically.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "list",
                            "get",
                            "create",
                            "edit",
                            "delete",
                            "pause",
                            "resume",
                            "cancel",
                            "start",
                            "progress",
                            "complete",
                            "fail",
                            "block",
                            "delegate",
                        ],
                    },
                    **{
                        k: {"type": "string"}
                        for k in [
                            "task_id",
                            "run_id",
                            "title",
                            "objective",
                            "success_criteria",
                            "content",
                        ]
                    },
                    "schedule": {
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["now", "once", "daily", "weekly"],
                            },
                            "timezone": {"type": "string"},
                            "at": {"type": "string"},
                            "time": {"type": "string"},
                            "weekday": {"type": "integer", "minimum": 0, "maximum": 6},
                        },
                        "required": ["mode"],
                        "additionalProperties": False,
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        if invocation.user.agent_id:
            raise ToolExecutionError("Subagents cannot manage tasks")
        config = json.loads(Path(__file__).with_name("_connection.local").read_text())
        data = {
            **invocation.arguments,
            "user_id": invocation.user.user_id,
            "request_id": invocation.invocation_id,
            "note_id": invocation.invocation_id,
        }
        request = Request(
            config["url"] + "/internal/tasks",
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
                return ToolResult(json.loads(response.read(16 * 1024 * 1024)))
        except HTTPError as exc:
            raise ToolExecutionError(
                "Task request rejected: "
                + str(exc.code)
                + " "
                + exc.read(1024).decode(errors="replace")
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise ToolExecutionError(
                "Task response unavailable; retry with the same task/run identity, never repeat external effects."
            ) from exc
