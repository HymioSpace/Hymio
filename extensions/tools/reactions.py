"""One-way social reactions from Hymio to a user's message."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.protocol.datatype import ToolDefinition, ToolResult
from core.protocol.error import ToolExecutionError
from core.protocol.interface import Tool


class ReactionsTool(Tool):
    allow_subagent = False

    @property
    def definition(self):
        return ToolDefinition(
            "react",
            "React warmly and sparingly to the user's latest message when one emoji adds social "
            "meaning. Copy target from its user_message id; never guess an ID. emoji=null removes "
            "the reaction. Users cannot react to you. Do not replace a substantive answer or create "
            "a task just to react.",
            {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "emoji": {
                        "type": ["string", "null"],
                        "enum": ["👍", "❤️", "😂", "🎉", "🤔", "👎", None],
                    },
                },
                "required": ["target", "emoji"],
                "additionalProperties": False,
            },
        )

    def execute(self, invocation):
        if invocation.user.agent_id:
            raise ToolExecutionError("Subagents cannot react")
        config = json.loads(Path(__file__).with_name("_connection.local").read_text())
        data = {
            **invocation.arguments,
            "user_id": invocation.user.user_id,
            "operation_id": invocation.invocation_id,
        }
        request = Request(
            config["url"] + "/internal/reactions",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": "Bearer " + config["token"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(
                request,
                timeout=min(15, max(0.1, invocation.deadline - time.monotonic()))
                if invocation.deadline
                else 15,
            ) as response:
                return ToolResult(json.loads(response.read(4096)))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ToolExecutionError(
                "Reaction unavailable; retry the same message reference"
            ) from exc
