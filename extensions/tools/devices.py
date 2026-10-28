from dataclasses import replace

from core.protocol.datatype import ToolDefinition, ToolResult
from core.protocol.interface import Tool

from ._device_transport import DEVICE, TEXT, call, schema


class DevicesTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            "devices",
            "List owned devices and their current capabilities. "
            "Does not provision cloud resources.",
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
            "or silently switch devices. Always provide a concise description (at most "
            "80 characters) of what this command is trying to accomplish. Returns device_id "
            "and bounded command output.",
            schema(
                {
                    "device_id": DEVICE,
                    "command": TEXT,
                    "cwd": TEXT,
                    "description": {
                        "type": "string",
                        "maxLength": 80,
                        "description": "Short user-facing title for this command's purpose",
                    },
                },
                ["command"],
            ),
        )

    def execute(self, invocation):
        args = dict(invocation.arguments)
        selected = None
        if not args.get("device_id"):
            selected = call(invocation, "select", "bash").content
            args["device_id"] = selected["device"]["device_id"]
        if invocation.cli_environment:
            args["command"] = _bootstrap() + "\n" + args["command"]
        result = call(replace(invocation, arguments=args), "execute", "bash")
        if selected and isinstance(result.content, dict):
            result = ToolResult(
                {
                    **result.content,
                    "device_kind": selected["device"]["kind"],
                    "selection": selected["selection"],
                }
            )
        return result


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
            "Control the target desktop: screenshot, click(x,y), type(text), key(shortcut), "
            "Use cmd+l/cmd+c on macOS, Ctrl+l/Ctrl+c on Linux. "
            "scroll(amount positive down). "
            "Screenshots return authenticated media references. "
            "Never guess screen coordinates without seeing a screenshot.",
            schema(
                {
                    "device_id": DEVICE,
                    "action": {
                        "type": "string",
                        "enum": ["screenshot", "click", "type", "key", "scroll", "swipe"],
                    },
                    "x": {"type": "integer", "minimum": 0, "maximum": 1279},
                    "y": {"type": "integer", "minimum": 0, "maximum": 799},
                    "x2": {"type": "integer", "minimum": 0, "maximum": 1279},
                    "y2": {"type": "integer", "minimum": 0, "maximum": 799},
                    "duration_ms": {"type": "integer", "minimum": 100, "maximum": 2000},
                    "amount": {"type": "integer", "minimum": -20, "maximum": 20},
                    "text": TEXT,
                    "key": TEXT,
                },
                ["device_id", "action"],
            ),
        )

    def execute(self, invocation):
        return call(invocation, "execute", "computer")


def _bootstrap():
    return """export PATH="$HOME/.local/bin:$PATH"
python3 - <<'OATH_BOOTSTRAP'
import hashlib, os, pathlib, urllib.request, urllib.parse
base=os.environ['OATH_CLI_SERVER'].rstrip('/')
target=pathlib.Path.home()/'.local/bin/oath-cli'
expected=os.environ['OATH_CLI_SHA256']
if (
    not target.is_file()
    or target.is_symlink()
    or hashlib.sha256(target.read_bytes()).hexdigest()!=expected
):
    parts=urllib.parse.urlsplit(base)
    if (
        parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or (
            parts.scheme!='https'
            and not(
                parts.scheme=='http'
                and parts.hostname in ('localhost','127.0.0.1','::1')
            )
        )
    ):
        raise ValueError('CLI requires HTTPS or loopback HTTP')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**k): raise ValueError('Redirect refused')
    with urllib.request.build_opener(NoRedirect()).open(base+'/cli/install',timeout=10) as response:
        installer=response.read(262145)
    installer_hash=hashlib.sha256(installer).hexdigest()
    if len(installer)>262144 or installer_hash!=os.environ['OATH_CLI_INSTALLER_SHA256']:
        raise ValueError('Installer integrity failed')
    namespace={'__name__':'oath_installer'}
    exec(compile(installer,'oath-installer','exec'),namespace)
    namespace['install'](base+'/cli/client',expected,target.parent)
OATH_BOOTSTRAP
if [ $? -ne 0 ]; then exit 2; fi"""
