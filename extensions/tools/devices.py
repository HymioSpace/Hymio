from core.protocol.datatype import ToolDefinition
from core.protocol.interface import Tool

from ._device_transport import DEVICE, TEXT, call, schema


class DevicesTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "devices",
            "Ensure this user's cloud computer is available, then list bound devices and capabilities. "
            "Automatically creates a missing computer and resumes a paused one. "
            "Read binding notices: a replaced computer is empty; do not assume old files exist. "
            "Call before choosing an explicit execution device.",
            schema({}, []),
        )

    def execute(self, invocation):
        return call(invocation, "list")


class DeviceBashTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "bash",
            "Run Bash on an explicit owned device. Never run on the Oath host "
            "or silently switch devices. Returns device_id, stdout, stderr and duration.",
            schema(
                {
                    "device_id": DEVICE,
                    "command": TEXT,
                    "cwd": TEXT,
                },
                ["device_id", "command"],
            ),
        )

    def execute(self, invocation):
        return call(invocation, "execute", "bash")


class DeviceCommandTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "device_command",
            "Query an existing bash, browser or computer invocation on the same device without "
            "repeating it. Requires the original device_id and invocation_id. Never use this for "
            "multimodal_understand, image_generate, tasks, skills, subagents or other tool calls: "
            "those are not device invocations; their results arrive as tool events automatically.",
            schema(
                {"device_id": DEVICE, "invocation_id": TEXT},
                ["device_id", "invocation_id"],
            ),
        )

    def execute(self, invocation):
        return call(invocation, "command")


class BrowserTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "browser",
            "Control Chromium on the target desktop via DOM. snapshot/navigate "
            "return text and selectors; click/fill use those selectors. "
            "Use tabs to get page_id; specify it when working across tabs. "
            "screenshot requires page_id and captures that page's viewport as authenticated media. "
            "Browser and computer share the same desktop and profile.",
            schema(
                {
                    "device_id": DEVICE,
                    "action": {
                        "type": "string",
                        "enum": [
                            "snapshot",
                            "screenshot",
                            "navigate",
                            "click",
                            "fill",
                            "key",
                            "tabs",
                            "new_tab",
                            "switch_tab",
                            "close_tab",
                            "back",
                            "forward",
                            "reload",
                        ],
                    },
                    "url": TEXT,
                    "page_id": TEXT,
                    "selector": TEXT,
                    "text": TEXT,
                    "key": TEXT,
                },
                ["device_id", "action"],
            ),
        )

    def execute(self, invocation):
        return call(invocation, "execute", "browser")


class ComputerTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "computer",
            "Control the target desktop: screenshot, click(x,y), type(text), key(X11 key), "
            "scroll(amount positive down). "
            "Screenshots return authenticated media references. "
            "Never guess screen coordinates without seeing a screenshot.",
            schema(
                {
                    "device_id": DEVICE,
                    "action": {
                        "type": "string",
                        "enum": ["screenshot", "click", "type", "key", "scroll"],
                    },
                    "x": {"type": "integer", "minimum": 0, "maximum": 1279},
                    "y": {"type": "integer", "minimum": 0, "maximum": 799},
                    "amount": {"type": "integer", "minimum": -20, "maximum": 20},
                    "text": TEXT,
                    "key": TEXT,
                },
                ["device_id", "action"],
            ),
        )

    def execute(self, invocation):
        return call(invocation, "execute", "computer")
