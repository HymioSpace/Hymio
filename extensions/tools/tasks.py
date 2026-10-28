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
            "Track actionable work that has a deliverable, external side effect or "
            "follow-up beyond this reply. Never use for personal facts or preferences, "
            "greetings, casual statements, "
            "immediate answers or tentative ideas. Capture current work early with "
            "capture(title, objective, success_criteria, intent_key): records an already "
            "admitted running task, NEVER dispatches it again. Reuse the intent_key for "
            "the same outcome; use returned run_id for updates. "
            "Use kind=reminder for notifications; use task for work requiring explicit outcome. "
            "Create schedules NEW independent background work; the backend binds its subagent. "
            "Do not create a second run for work already underway. "
            "For app.task.due call action=start with run_id before acting; cancelled runs "
            "must not execute. Record progress, complete/fail/block with content, phase "
            "and next_step. Delegate a started run for independent asynchronous work. "
            "Schedule: mode now/once/daily/weekly, timezone IANA; once at ISO8601 with "
            "offset; daily/weekly time HH:MM, weekday Monday=0. "
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
                            "capture",
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
                            "activity",
                            "wait",
                            "continue",
                            "accept_suggestion",
                            "dismiss_suggestion",
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
                            "intent_key",
                            "phase",
                            "next_step",
                            "suggestion_id",
                        ]
                    },
                    "wait_reason": {
                        "type": "string",
                        "enum": ["user", "time", "external", "device", "retry"],
                    },
                    "resume_at": {
                        "type": "number",
                        "description": "UTC Unix timestamp for a justified follow-up; omit while awaiting a user decision.",
                    },
                    "kind": {"type": "string", "enum": ["task", "reminder"]},
                    "status": {
                        "type": "string",
                        "enum": ["running", "blocked", "succeeded"],
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
                            "grace_seconds": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 86400,
                            },
                            "run_timeout_seconds": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 604800,
                            },
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
                "Task response unavailable; retry with the same task/run identity, "
                "never repeat external effects."
            ) from exc
