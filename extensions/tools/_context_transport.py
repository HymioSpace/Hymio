import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.protocol.datatype import ToolResult
from core.protocol.error import ToolExecutionError


def call_context(invocation):
    try:
        config = json.loads(Path(__file__).with_name("_connection.local").read_text())
        timeout = min(20, invocation.deadline - time.monotonic()) if invocation.deadline else 20
        if timeout <= 0:
            raise ToolExecutionError("Context request deadline expired")
        payload = {**invocation.arguments, "user_id": invocation.user.user_id}
        request = Request(
            config["url"].rstrip("/") + "/internal/context/call",
            data=json.dumps(payload, allow_nan=False).encode(),
            headers={
                "Authorization": "Bearer " + config["token"],
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ToolExecutionError("Response too large; query fewer records")
            return ToolResult(json.loads(raw))
    except HTTPError as exc:
        body = exc.read(8192).decode("utf-8", errors="replace")
        raise ToolExecutionError(f"Context API {exc.code}: {body}") from exc
    except (OSError, ValueError, KeyError, URLError, TimeoutError) as exc:
        raise ToolExecutionError(
            "Context connection unavailable. Retry uncertain writes with the same operation_id."
        ) from exc
