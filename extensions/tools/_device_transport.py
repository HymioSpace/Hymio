import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.protocol.datatype import ToolResult
from core.protocol.error import ToolExecutionError


def call(invocation, operation, capability=None):
    config = json.loads(Path(__file__).with_name("_connection.local").read_text())
    budget = 110 if operation in {"list", "select"} else 25
    timeout = min(budget, invocation.deadline - time.monotonic()) if invocation.deadline else budget
    if timeout <= 0:
        raise ToolExecutionError("Device request deadline expired")
    data = {"user_id": invocation.user.user_id}
    if operation == "select":
        data["capability"] = capability or "bash"
    if operation == "command":
        data.update(
            device_id=invocation.arguments["device_id"],
            invocation_id=invocation.arguments["invocation_id"],
        )
    if capability and operation == "execute":
        args = dict(invocation.arguments)
        data.update(
            device_id=args.pop("device_id"),
            invocation_id=invocation.invocation_id,
            capability=capability,
            arguments=args,
            timeout=max(0.1, timeout - 5),
            execution_environment=invocation.cli_environment if capability == "bash" else {},
            parent_invocation_id=invocation.parent_invocation_id,
        )
    request = Request(
        config["url"] + "/internal/devices/" + operation,
        data=json.dumps(data).encode(),
        headers={
            "Authorization": "Bearer " + config["token"],
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read(1024 * 1024))
            result = value.get("result") if isinstance(value, dict) else None
            screenshot = result.get("screenshot") if isinstance(result, dict) else None
            media_id = screenshot.get("media_id") if isinstance(screenshot, dict) else None
            if isinstance(media_id, str) and media_id:
                value["image_refs"] = [media_id]
            return ToolResult(value)
    except HTTPError as error:
        try:
            failure = json.loads(error.read(65536))
        except (ValueError, OSError):
            failure = {}
        if failure.get("error") == "not_a_device_invocation":
            raise ToolExecutionError(
                "This call is not a device operation. Inspect its ToolSystem state with "
                "oath-cli status."
            ) from error
        raise ToolExecutionError("Device service rejected request: " + str(error.code)) from error
    except (URLError, TimeoutError) as error:
        if operation == "list":
            raise ToolExecutionError(
                "Device discovery is unavailable. Report the condition and wait for new input; "
                "do not poll or repeat commands."
            ) from error
        raise ToolExecutionError(
            f"Result unavailable for device_id={invocation.arguments.get('device_id')}, "
            f"invocation_id={invocation.invocation_id}. "
            "Inspect this invocation with oath-cli status; do not repeat effects."
        ) from error


def schema(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


DEVICE = {
    "type": "string",
    "description": "Exact device_id returned by devices; never infer a target",
}
TEXT = {"type": "string"}
