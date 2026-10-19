import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.protocol.datatype import ToolResult
from core.protocol.error import ToolExecutionError


def call(invocation, operation, capability=None):
    config = json.loads(Path(__file__).with_name("_connection.local").read_text())
    budget = 110 if operation == "list" else 25
    timeout = (
        min(budget, invocation.deadline - time.monotonic())
        if invocation.deadline
        else budget
    )
    if timeout <= 0:
        raise ToolExecutionError("Device request deadline expired")
    data = {"user_id": invocation.user.user_id}
    if operation == "command":
        data.update(
            device_id=invocation.arguments["device_id"],
            invocation_id=invocation.arguments["invocation_id"],
        )
    if capability:
        args = dict(invocation.arguments)
        data.update(
            device_id=args.pop("device_id"),
            invocation_id=invocation.invocation_id,
            capability=capability,
            arguments=args,
            timeout=max(0.1, timeout - 5),
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
            return ToolResult(json.loads(response.read(1024 * 1024)))
    except HTTPError as error:
        raise ToolExecutionError(
            "Device service rejected request: " + str(error.code)
        ) from error
    except (URLError, TimeoutError) as error:
        if operation == "list":
            raise ToolExecutionError(
                "Computer preparation may still be running. Call devices again; do not repeat commands."
            ) from error
        raise ToolExecutionError(
            f"Result unavailable for device_id={invocation.arguments.get('device_id')}, "
            f"invocation_id={invocation.invocation_id}. "
            "Query device_command; do not repeat effects."
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
