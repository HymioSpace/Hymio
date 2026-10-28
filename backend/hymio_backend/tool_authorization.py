"""Deterministic product policy for Agent tool actions and user-facing modes."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import shlex
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.routing import Route

from .session_store import Unauthorized

MODE_READ_ONLY = "read_only"
MODE_GUIDED = "guided"
MODE_AUTONOMOUS = "autonomous"
MODES = (MODE_READ_ONLY, MODE_GUIDED, MODE_AUTONOMOUS)
POLICY_VERSION = "hymio-tool-policy-v2"
COMMAND_DESCRIPTION_LIMIT = 80
MAX_ALLOW_RULES = 100

_DENY_COMMAND = re.compile(
    r"\b(?:sudo|su)\b|"
    r"\bsecurity\s+(?:dump-keychain|find-generic-password|find-internet-password|export)\b|"
    r"\brm\s+-[^\n;&|]*r[^\n;&|]*f[^\n;&|]*(?:/|~|\$HOME)\b|"
    r"\blaunchctl\s+(?:bootstrap|disable)\b|"
    r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash|zsh)\b",
    re.IGNORECASE,
)

_ALWAYS_CONFIRM_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)"
    r"(?:rm|rmdir|shred|truncate|dd|diskutil|fdisk|parted|mkfs(?:\.\w+)?|"
    r"chmod|chown|chgrp|kill|pkill|killall|launchctl|systemctl)\b|"
    r"\bgit\s+(?:reset\s+--hard|clean\s+-[^\s]*f|push(?:\s|$)|"
    r"branch\s+-D\b|tag\s+(?:-d|--delete)\b|send-email\b)|"
    r"\b(?:npm|pnpm|yarn)\s+publish\b|"
    r"\b(?:docker|podman)\s+push\b|"
    r"\bgh\s+(?:pr\s+merge|release|repo\s+delete)\b|"
    r"\b(?:curl|wget)\b[^\n]*(?:--request\s+(?:POST|PUT|PATCH|DELETE)\b|"
    r"-X\s*(?:POST|PUT|PATCH|DELETE)\b|--data(?:-raw|-binary)?\b|--form\b|"
    r"-(?:F|T)\s|--upload-file\b|--post-data\b|--post-file\b)|"
    r"\bssh\b|"
    r"\b(?:stripe|paypal|alipay|wechatpay|checkout|purchase|refund|"
    r"transfer)\b|"
    r"(?:支付|付款|购买|下单|退款|转账)",
    re.IGNORECASE,
)

_READ_ONLY_COMMANDS = {
    "basename",
    "cat",
    "cd",
    "cut",
    "date",
    "df",
    "dirname",
    "du",
    "echo",
    "file",
    "find",
    "git",
    "grep",
    "head",
    "id",
    "jq",
    "ls",
    "printf",
    "pwd",
    "rg",
    "sort",
    "stat",
    "tail",
    "test",
    "tree",
    "tr",
    "uname",
    "uniq",
    "wc",
    "which",
    "whoami",
}
_READ_ONLY_GIT = {
    "blame",
    "branch",
    "describe",
    "diff",
    "log",
    "ls-files",
    "remote",
    "rev-parse",
    "show",
    "status",
}
_READ_ONLY_PACKAGE_SCRIPTS = {"check", "lint", "test", "typecheck"}
_READ_ONLY_KIT_OPERATIONS = {
    "get",
    "list",
    "read",
    "search",
    "snapshot",
    "status",
}
_CRITICAL_ACTION_WORDS = re.compile(
    r"\b(?:buy|checkout|delete|destroy|invite|pay|payment|publish|purchase|"
    r"refund|remove|send|submit|submit-order|transfer|upload)\b|"
    r"(?:支付|付款|购买|下单|删除|退款|转账|发送|提交|发布|上传)",
    re.IGNORECASE,
)

_SAFE_INTERNAL_ACTIONS = {
    "tasks": {"list", "get", "capture", "progress", "complete", "fail", "block", "start"},
    "connections": {"list", "read"},
    "recall": {"search", "read", "retrieve", "related"},
    "browser": {"tabs", "snapshot"},
}


def _safe_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname


def _private_host(host):
    if host in {"localhost"} or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _grant_key(user_id, tool, arguments):
    action = arguments.get("action", "")
    target = ""
    command = arguments.get("command", "")
    if tool == "bash" and isinstance(command, str):
        target = command.strip()
    elif tool == "browser":
        target = (
            _safe_url(arguments.get("url"))
            or arguments.get("page_id")
            or arguments.get("device_id")
            or ""
        )
    elif tool == "kit_call":
        target = ":".join(
            [
                str(arguments.get("kit_id", "")),
                str(arguments.get("operation", "")),
            ]
        )
    else:
        target = (
            arguments.get("task_id")
            or arguments.get("device_id")
            or arguments.get("page_id")
            or arguments.get("kit_id")
            or ""
        )
    raw = json.dumps(
        [user_id, tool, action, target],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _read_only_command(command):
    if any(token in command for token in (">", "<", "`", "$(")):
        return False
    for command_group in re.split(r"\s*(?:&&|\|\||;|\n)\s*", command):
        for segment in command_group.split("|"):
            try:
                tokens = shlex.split(segment)
            except ValueError:
                return False
            if not tokens:
                return False
            name = tokens[0].rsplit("/", 1)[-1]
            if name not in _READ_ONLY_COMMANDS and name not in {
                "cargo",
                "go",
                "npm",
                "pnpm",
                "pytest",
                "ruff",
                "swift",
                "tsc",
                "yarn",
            }:
                return False
            args = tokens[1:]
            if name == "git":
                if not args or args[0] not in _READ_ONLY_GIT:
                    return False
                if args[0] == "branch" and any(
                    value
                    not in {
                        "-a",
                        "--all",
                        "-l",
                        "--list",
                        "--show-current",
                        "-r",
                        "--remotes",
                        "-v",
                        "-vv",
                        "--verbose",
                    }
                    for value in args[1:]
                ):
                    return False
                if args[0] == "remote" and args[1:] != ["-v"]:
                    return False
            elif name == "find" and any(
                value
                in {
                    "-delete",
                    "-exec",
                    "-execdir",
                    "-ok",
                    "-okdir",
                    "-fls",
                    "-fprint",
                    "-fprint0",
                    "-fprintf",
                }
                or value.startswith("--fprint")
                for value in args
            ):
                return False
            elif name == "uniq" and len([value for value in args if not value.startswith("-")]) > 1:
                return False
            elif name == "sort" and any(
                value == "-o" or value.startswith("--output=") for value in args
            ):
                return False
            elif name == "tree" and any(
                value == "-o" or value.startswith("--output") for value in args
            ):
                return False
            elif name == "date" and any(
                value in {"-s", "--set"} or value.startswith("--set=") for value in args
            ):
                return False
            elif name in {"npm", "pnpm", "yarn"}:
                script = (
                    args[1]
                    if args and args[0] == "run" and len(args) > 1
                    else args[0]
                    if args
                    else ""
                )
                if script not in _READ_ONLY_PACKAGE_SCRIPTS:
                    return False
                if any(
                    value in {"-u", "--fix", "--write", "--updateSnapshot"}
                    or value.startswith("--updateSnapshot=")
                    for value in args
                ):
                    return False
            elif name == "cargo" and (not args or args[0] not in {"test", "check"}):
                return False
            elif name == "go" and (not args or args[0] not in {"test", "vet"}):
                return False
            elif name == "swift" and (not args or args[0] != "test"):
                return False
            elif name == "ruff" and (not args or args[0] not in {"check"}):
                return False
            elif name == "tsc" and "--noEmit" not in args:
                return False
    return True


def _requires_explicit_confirmation(tool, arguments):
    if tool == "bash":
        command = arguments.get("command")
        return isinstance(command, str) and bool(
            _ALWAYS_CONFIRM_COMMAND.search(command) or _CRITICAL_ACTION_WORDS.search(command)
        )
    if tool in {"browser", "computer", "kit_call"}:
        values = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        return bool(_CRITICAL_ACTION_WORDS.search(values))
    return False


def _display_target(tool, arguments):
    if tool == "bash":
        return {
            "kind": "device",
            "id": str(arguments.get("device_id", "")),
            "label": "所选电脑",
        }
    if tool == "browser":
        host = _safe_url(arguments.get("url"))
        return {
            "kind": "origin" if host else "page",
            "id": host or str(arguments.get("page_id", "")) or str(arguments.get("device_id", "")),
            "label": host or str(arguments.get("page_id", "")) or "所选浏览器",
        }
    if tool == "computer":
        return {
            "kind": "device",
            "id": str(arguments.get("device_id", "")),
            "label": "所选电脑",
        }
    if tool == "kit_call":
        return {
            "kind": "app",
            "id": str(arguments.get("kit_id", "")),
            "label": str(arguments.get("operation", "应用操作")),
        }
    return {"kind": "tool", "id": tool, "label": tool}


def _read_only_action(tool, arguments):
    if tool == "bash":
        command = arguments.get("command")
        return isinstance(command, str) and _read_only_command(command)
    if tool == "computer":
        return arguments.get("action") == "screenshot"
    if tool == "browser":
        return arguments.get("action") in {
            "back",
            "forward",
            "new_tab",
            "navigate",
            "reload",
            "snapshot",
            "switch_tab",
            "tabs",
        }
    if tool == "kit_call":
        return str(arguments.get("operation", "")) in _READ_ONLY_KIT_OPERATIONS
    return False


def _rule_id(user_id, grant_key):
    return hashlib.sha256(f"{user_id}:{grant_key}".encode()).hexdigest()[:24]


class ToolAuthorizationService:
    def __init__(self, settings, sessions):
        self.settings = settings
        self.sessions = sessions
        with sessions.transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS tool_authorization_preferences ("
                "user_id TEXT PRIMARY KEY, mode TEXT NOT NULL, updated_at REAL NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS tool_authorization_rules ("
                "user_id TEXT NOT NULL, grant_key TEXT NOT NULL, tool TEXT NOT NULL, "
                "title TEXT NOT NULL, summary TEXT NOT NULL, target_label TEXT NOT NULL, "
                "created_at REAL NOT NULL, last_used_at REAL, "
                "PRIMARY KEY(user_id, grant_key))"
            )

    def mode(self, user_id):
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT mode FROM tool_authorization_preferences WHERE user_id=?",
                (user_id,),
            ).fetchone()
        return row["mode"] if row else MODE_GUIDED

    def set_mode(self, user_id, mode):
        if mode not in MODES:
            raise ValueError("invalid_mode")
        with self.sessions.transaction() as db:
            db.execute(
                "INSERT INTO tool_authorization_preferences VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode,"
                "updated_at=excluded.updated_at",
                (user_id, mode, time.time()),
            )

    def settings_view(self, user_id):
        with self.sessions.transaction() as db:
            rules = [
                {
                    "id": _rule_id(user_id, row["grant_key"]),
                    "grant_key": row["grant_key"],
                    "tool": row["tool"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "target": row["target_label"],
                    "created_at": row["created_at"],
                    "last_used_at": row["last_used_at"],
                }
                for row in db.execute(
                    "SELECT grant_key,tool,title,summary,target_label,created_at,last_used_at "
                    "FROM tool_authorization_rules WHERE user_id=? "
                    "ORDER BY created_at DESC",
                    (user_id,),
                )
            ]
        return {"mode": self.mode(user_id), "modes": list(MODES), "rules": rules}

    def add_rule(self, user_id, data):
        tool = data.get("tool")
        arguments = data.get("arguments")
        if not isinstance(tool, str) or not 1 <= len(tool) <= 64 or not isinstance(arguments, dict):
            raise ValueError("invalid_authorization_rule")
        if _requires_explicit_confirmation(tool, arguments):
            raise ValueError("action_requires_confirmation_every_time")
        target = _display_target(tool, arguments)
        target_label = str(target["label"])[:160]
        if tool == "bash":
            title = _command_title(arguments.get("description"))
            summary = "相同的 Bash 命令会自动执行。"
        elif tool == "browser":
            title = f"允许操作 {target_label}"
            summary = "相同站点和操作会自动执行。"
        elif tool == "kit_call":
            title = f"允许 {target_label}"
            summary = "相同应用操作会自动执行。"
        else:
            title = f"允许使用 {tool}"
            summary = "相同工具操作会自动执行。"
        grant_key = _grant_key(user_id, tool, arguments)
        now = time.time()
        with self.sessions.transaction() as db:
            existing = db.execute(
                "SELECT 1 FROM tool_authorization_rules WHERE user_id=? AND grant_key=?",
                (user_id, grant_key),
            ).fetchone()
            if existing is None:
                count = db.execute(
                    "SELECT COUNT(*) AS count FROM tool_authorization_rules WHERE user_id=?",
                    (user_id,),
                ).fetchone()["count"]
                if count >= MAX_ALLOW_RULES:
                    raise ValueError("authorization_rule_limit")
            db.execute(
                "INSERT INTO tool_authorization_rules "
                "(user_id,grant_key,tool,title,summary,target_label,created_at,last_used_at) "
                "VALUES(?,?,?,?,?,?,?,NULL) "
                "ON CONFLICT(user_id,grant_key) DO UPDATE SET "
                "tool=excluded.tool,title=excluded.title,summary=excluded.summary,"
                "target_label=excluded.target_label",
                (user_id, grant_key, tool, title, summary, target_label, now),
            )
        return self.settings_view(user_id)

    def remove_rule(self, user_id, rule_id):
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("invalid_authorization_rule")
        with self.sessions.transaction() as db:
            matches = [
                row["grant_key"]
                for row in db.execute(
                    "SELECT grant_key FROM tool_authorization_rules WHERE user_id=?",
                    (user_id,),
                )
                if _rule_id(user_id, row["grant_key"]) == rule_id
            ]
            if matches:
                db.execute(
                    "DELETE FROM tool_authorization_rules WHERE user_id=? AND grant_key=?",
                    (user_id, matches[0]),
                )
        return self.settings_view(user_id)

    def _matching_rule(self, user_id, tool, arguments):
        grant_key = _grant_key(user_id, tool, arguments)
        now = time.time()
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT title FROM tool_authorization_rules "
                "WHERE user_id=? AND grant_key=? AND tool=?",
                (user_id, grant_key, tool),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE tool_authorization_rules SET last_used_at=? "
                    "WHERE user_id=? AND grant_key=?",
                    (now, user_id, grant_key),
                )
        return row

    def check(self, data):
        user_id = data.get("user_id")
        tool = data.get("tool")
        arguments = data.get("arguments")
        if (
            not isinstance(user_id, str)
            or not 1 <= len(user_id) <= 160
            or not isinstance(tool, str)
            or not 1 <= len(tool) <= 64
            or not isinstance(arguments, dict)
        ):
            raise ValueError("invalid_policy_request")
        mode = self.mode(user_id)
        action = arguments.get("action")
        reason = ""

        if tool == "bash":
            command = arguments.get("command")
            if not isinstance(command, str) or not command.strip():
                return self._deny("Invalid shell command")
            description = arguments.get("description")
            if description is not None and (
                not isinstance(description, str) or len(description) > COMMAND_DESCRIPTION_LIMIT
            ):
                raise ValueError("invalid_command_description")
            if _DENY_COMMAND.search(command):
                return self._deny("This command crosses a protected local security boundary")
            if _read_only_command(command):
                return self._allow("Read-only shell command")
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not execute shell commands")
            critical = _requires_explicit_confirmation("bash", arguments)
            if critical:
                return self._ask(
                    user_id,
                    tool,
                    arguments,
                    title=_command_title(description),
                    summary="这个操作会删除、改写或提交外部状态，每次都需要你确认。",
                    risk="critical",
                    tier="critical",
                    effects=["execute", "local_access"],
                    target=_display_target(tool, arguments),
                    scopes=["once"],
                )
            if mode == MODE_AUTONOMOUS:
                return self._allow("Full-access shell command")
            if self._matching_rule(user_id, tool, arguments):
                return self._allow("Existing always-allow rule")
            return self._ask(
                user_id,
                tool,
                arguments,
                title=_command_title(description),
                summary="命令将修改文件或运行一次有副作用的操作。",
                risk="high",
                tier="write",
                effects=["execute", "local_access"],
                target=_display_target(tool, arguments),
                scopes=["once", "run", "exact_rule"],
            )

        if tool == "computer":
            action = arguments.get("action")
            if action == "screenshot":
                return self._allow("Read-only desktop screenshot")
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not control the desktop")
            critical = _requires_explicit_confirmation(tool, arguments)
            if critical:
                return self._ask(
                    user_id,
                    tool,
                    arguments,
                    title="允许完成支付或不可逆操作？",
                    summary="该操作可能提交订单、转账或改变不可恢复的状态。",
                    risk="critical",
                    tier="critical",
                    effects=["desktop_control"],
                    target=_display_target(tool, arguments),
                    scopes=["once"],
                )
            if mode == MODE_AUTONOMOUS:
                return self._allow("Full-access desktop control")
            if self._matching_rule(user_id, tool, arguments):
                return self._allow("Existing always-allow rule")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许操作所选电脑的桌面？",
                summary="Hymio 将发送桌面鼠标、键盘或截图操作。",
                risk="high",
                tier="write",
                effects=["desktop_control"],
                target=_display_target(tool, arguments),
                scopes=["once", "run", "exact_rule"],
            )

        if tool == "browser":
            host = _safe_url(arguments.get("url"))
            if action == "navigate" and host is None:
                return self._deny("Navigation requires a public HTTP(S) URL")
            if host and _private_host(host):
                return self._deny("Browser navigation cannot reach a private or loopback host")
            if _read_only_action(tool, arguments):
                return self._allow("Bounded browser read or navigation")
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not modify browser state")
            critical = _requires_explicit_confirmation(tool, arguments)
            if critical:
                return self._ask(
                    user_id,
                    tool,
                    arguments,
                    title="允许完成支付或提交操作？",
                    summary="页面操作可能提交表单、确认订单或触发不可逆的外部变化。",
                    risk="critical",
                    tier="critical",
                    effects=["browser_control"],
                    target=_display_target(tool, arguments),
                    scopes=["once"],
                )
            if mode == MODE_AUTONOMOUS:
                return self._allow("Full-access browser interaction")
            if self._matching_rule(user_id, tool, arguments):
                return self._allow("Existing always-allow rule")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许操作浏览器页面？",
                summary="Hymio 将点击、填写或改变页面状态。",
                risk="high",
                tier="write",
                effects=["browser_control"],
                target=_display_target(tool, arguments),
                scopes=["once", "run", "exact_rule"],
            )

        if tool == "kit_call":
            operation = str(arguments.get("operation", ""))
            if operation in _READ_ONLY_KIT_OPERATIONS:
                return self._allow("Bounded application read")
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not invoke application operations")
            critical = _requires_explicit_confirmation(tool, arguments)
            if critical:
                return self._ask(
                    user_id,
                    tool,
                    arguments,
                    title="允许执行不可逆的应用操作？",
                    summary="该操作可能删除、提交或对外发布数据。",
                    risk="critical",
                    tier="critical",
                    effects=["app_write"],
                    target=_display_target(tool, arguments),
                    scopes=["once"],
                )
            if mode == MODE_AUTONOMOUS:
                return self._allow("Autonomous application operation")
            if self._matching_rule(user_id, tool, arguments):
                return self._allow("Existing always-allow rule")
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许调用应用操作？",
                summary="该操作可能修改你在应用里的数据。",
                risk="medium",
                tier="write",
                effects=["app_write"],
                target=_display_target(tool, arguments),
                scopes=["once", "run", "exact_rule"],
            )

        if tool == "tasks" and action not in _SAFE_INTERNAL_ACTIONS["tasks"]:
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not change tasks")
            if mode == MODE_AUTONOMOUS and action not in {"delete", "cancel"}:
                return self._allow("Autonomous task operation")
            critical = action in {"delete", "cancel"}
            return self._ask(
                user_id,
                tool,
                arguments,
                title="允许修改任务安排？",
                summary="该操作可能创建、取消或改变未来执行的工作。",
                risk="critical" if critical else "medium",
                tier="critical" if critical else "write",
                effects=["scheduled_work"],
                target={"kind": "task", "id": str(arguments.get("task_id", "")), "label": "任务"},
                scopes=["once"] if critical else ["once", "run", "exact_rule"],
            )

        if tool in {
            "cli",
            "devices",
            "recall",
            "multimodal_understand",
            "skill",
            "detail_read",
        }:
            return self._allow(reason)
        if tool == "connections":
            return self._allow("Connected-source read")
        if tool == "tasks" and action in {"list", "get"}:
            return self._allow("Bounded task read")
        if tool == "tasks":
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not change task state")
            return self._allow("Bounded task progress")
        if tool in {"remember", "notify_user", "react", "image_generate", "kit_build", "kit_dev"}:
            if mode == MODE_READ_ONLY:
                return self._deny("Read-only mode does not perform writes or generation")
            return self._allow("Bounded reversible product action")
        if tool == "browser" and action in _SAFE_INTERNAL_ACTIONS["browser"]:
            return self._allow("Bounded browser read")

        if mode == MODE_READ_ONLY:
            return self._deny("Read-only mode does not run unclassified tools")
        critical = _requires_explicit_confirmation(tool, arguments)
        if critical:
            return self._ask(
                user_id,
                tool,
                arguments,
                title=f"允许执行 {tool}？",
                summary="这个操作可能产生不可逆的外部影响。",
                risk="critical",
                tier="critical",
                effects=["unknown"],
                target=_display_target(tool, arguments),
                scopes=["once"],
            )
        if mode == MODE_AUTONOMOUS:
            return self._allow("Full-access tool operation")
        if self._matching_rule(user_id, tool, arguments):
            return self._allow("Existing always-allow rule")
        return self._ask(
            user_id,
            tool,
            arguments,
            title=f"允许运行 {tool}？",
            summary="这个操作没有足够的自动分类信息，需要你确认。",
            risk="medium",
            tier="write",
            effects=["unknown"],
            target={"kind": "tool", "id": tool, "label": tool},
            scopes=["once", "run", "exact_rule"],
        )

    @staticmethod
    def _allow(reason=""):
        return {
            "verdict": "allow",
            "reason": reason,
            "policy_version": POLICY_VERSION,
        }

    @staticmethod
    def _deny(reason):
        return {
            "verdict": "deny",
            "reason": reason,
            "policy_version": POLICY_VERSION,
        }

    @staticmethod
    def _ask(
        user_id,
        tool,
        arguments,
        *,
        title,
        summary,
        risk,
        tier,
        effects,
        target,
        scopes,
    ):
        key = _grant_key(user_id, tool, arguments)
        return {
            "verdict": "ask",
            "reason": summary,
            "grant_key": key,
            "policy_version": POLICY_VERSION,
            "approval": {
                "title": title,
                "summary": summary,
                "risk": risk,
                "tier": tier,
                "effects": effects,
                "target": target,
                "scope_options": scopes,
                "scope_descriptions": {
                    "once": "只执行这一次",
                    "run": "直到当前这次任务结束",
                    "exact_rule": "以后相同操作自动允许，可在设置中撤销",
                },
                "policy_managed_grant": True,
                "grant_key": key,
                "policy_version": POLICY_VERSION,
            },
        }


def _command_title(value):
    if not isinstance(value, str):
        return "允许运行命令？"
    title = " ".join(value.split())
    return title[:COMMAND_DESCRIPTION_LIMIT] or "允许运行命令？"


def tool_authorization_routes(settings, sessions, service, bearer, body):
    async def endpoint(request):
        try:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            path = request.url.path
            if path == "/internal/tool-authorization/check":
                token_file = settings.oath_admin_token_file
                if token_file is None:
                    return JSONResponse({"error": "policy_unavailable"}, 503)
                expected = token_file.read_text().strip()
                if not hmac.compare_digest(bearer(request).encode(), expected.encode()):
                    raise Unauthorized()
                return JSONResponse(service.check(await body(request, limit=65536)))
            identity = sessions.verify(bearer(request))
            user_id = identity["user_id"]
            if path == "/settings/tool-authorization":
                if request.method == "POST":
                    service.set_mode(user_id, (await body(request)).get("mode"))
                return JSONResponse(service.settings_view(user_id))
            if path == "/settings/tool-authorization/rules":
                payload = await body(request)
                if payload.get("operation") == "delete":
                    return JSONResponse(service.remove_rule(user_id, payload.get("id")))
                return JSONResponse(service.add_rule(user_id, payload))
            raise Unauthorized()
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except ValueError:
            return JSONResponse({"error": "invalid_tool_authorization"}, 400)

    return [
        Route(
            "/internal/tool-authorization/check",
            endpoint,
            methods=["POST"],
        ),
        Route(
            "/settings/tool-authorization",
            endpoint,
            methods=["GET", "POST"],
        ),
        Route(
            "/settings/tool-authorization/rules",
            endpoint,
            methods=["POST"],
        ),
    ]
