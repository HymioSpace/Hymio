"""Source, build and bounded execution for generated React/Python applications."""

import ast
import hashlib
import json
import os
import re
import resource
import subprocess
import sys
from pathlib import Path

OPERATION_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
HANDLER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SAFE_PATHS = ("app.json", "README.md", "server/", "web/")
ALLOWED_IMPORTS = {"collections", "datetime", "json", "math", "re", "statistics"}
DENIED_NAMES = {
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}


def revision(files):
    return hashlib.sha256(
        json.dumps(
            files, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def validate_files(files):
    if not isinstance(files, dict) or not 5 <= len(files) <= 64:
        raise ValueError("Application source must contain 5 to 64 files")
    total = 0
    for path, content in files.items():
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or ".." in Path(path).parts
            or not path.startswith(SAFE_PATHS)
            or not isinstance(content, str)
            or len(content) > 512 * 1024
        ):
            raise ValueError("Invalid application source file")
        total += len(content)
    if total > 900 * 1024:
        raise ValueError("Application source is too large")


def validate_application(files):
    validate_files(files)
    try:
        app = json.loads(files["app.json"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("app.json must contain valid JSON") from exc
    if not isinstance(app, dict) or app.get("schema") != "hymio.app/v1":
        raise ValueError("Unsupported application source schema")
    display = app.get("display")
    if (
        not isinstance(display, dict)
        or any(
            not isinstance(display.get(key), str) or not display[key].strip()
            for key in ("name", "tagline", "description", "category", "icon")
        )
        or display.get("accent") not in {"blue", "amber", "green", "rose", "violet"}
        or len(display["name"].strip()) > 40
        or len(display["tagline"].strip()) > 160
        or len(display["description"].strip()) > 400
        or len(display["category"].strip()) > 20
        or (
            "item_label" in display
            and (
                not isinstance(display["item_label"], str)
                or not 1 <= len(display["item_label"].strip()) <= 20
            )
        )
    ):
        raise ValueError("Application display metadata is invalid")
    operations = app.get("operations")
    if not isinstance(operations, list):
        raise ValueError("Application operations must be an array")
    seen = set()
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("Invalid application operation")
        operation_id = operation.get("id")
        handler = operation.get("handler")
        if (
            not isinstance(operation_id, str)
            or not OPERATION_ID.fullmatch(operation_id)
            or operation_id in seen
            or not isinstance(handler, str)
            or not HANDLER_NAME.fullmatch(handler)
            or operation.get("effect") not in {"read", "write"}
            or not isinstance(operation.get("agent_visible", True), bool)
            or not isinstance(operation.get("input_schema"), dict)
        ):
            raise ValueError("Invalid application operation")
        seen.add(operation_id)
    source = files.get("server/main.py")
    if not isinstance(source, str):
        raise ValueError("server/main.py is required")
    _validate_python(source, {operation["handler"] for operation in operations})
    entry = files.get("web/src/main.jsx")
    if not isinstance(entry, str) or not entry.strip():
        raise ValueError("web/src/main.jsx is required")
    return app


def _validate_python(source, handlers):
    try:
        tree = ast.parse(source, filename="server/main.py")
    except SyntaxError as exc:
        raise ValueError(
            f"server/main.py:{exc.lineno or 0}:{exc.offset or 0} {exc.msg}"
        ) from exc
    functions = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] not in ALLOWED_IMPORTS:
                    raise ValueError(f"Import is unavailable: {alias.name}")
        if isinstance(node, ast.ImportFrom):
            if not node.module or node.module.split(".", 1)[0] not in ALLOWED_IMPORTS:
                raise ValueError("Import is unavailable")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("Private Python attributes are unavailable")
        if isinstance(node, ast.Name) and node.id in DENIED_NAMES:
            raise ValueError(f"Python name is unavailable: {node.id}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
    missing = sorted(handlers - functions)
    if missing:
        raise ValueError("Missing Python handlers: " + ", ".join(missing))


def apply_changes(files, changes, deletions=None):
    updated = dict(files)
    deletions = deletions or []
    if not isinstance(changes, list) or not isinstance(deletions, list):
        raise ValueError("Application changes must be arrays")
    if len(changes) > 24 or len(deletions) > 8:
        raise ValueError("Too many application changes")
    for path in deletions:
        if not isinstance(path, str) or path == "app.json" or path not in updated:
            raise ValueError("Invalid application file deletion")
        del updated[path]
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("Invalid application file change")
        path = change.get("path")
        if (
            not isinstance(path, str)
            or path.startswith("/")
            or ".." in Path(path).parts
            or not path.startswith(SAFE_PATHS)
        ):
            raise ValueError("Application change targets an unknown file")
        source = updated.get(path)
        if "content" in change:
            content = change["content"]
            if not isinstance(content, str):
                raise ValueError("Application file content must be text")
            updated[path] = content
            continue
        if source is None:
            raise ValueError("A new application file requires full content")
        old, new = change.get("old"), change.get("new")
        if (
            not isinstance(old, str)
            or not old
            or not isinstance(new, str)
            or len(old) > 12000
            or len(new) > 12000
            or source.count(old) != 1
        ):
            raise ValueError("Each patch old value must occur exactly once")
        updated[path] = source.replace(old, new, 1)
    validate_application(updated)
    return updated


def build_web(files):
    node = os.environ.get("KIT_HOST_NODE", "node")
    modules = os.environ.get(
        "KIT_HOST_WEB_MODULES",
        str(Path(__file__).resolve().parent.parent / "web/node_modules"),
    )
    script = Path(__file__).resolve().parent.parent / "web_build.mjs"
    try:
        completed = subprocess.run(
            [node, str(script)],
            input=json.dumps(
                {
                    "files": {
                        path: content
                        for path, content in files.items()
                        if path.startswith("web/")
                    },
                    "entry": "web/src/main.jsx",
                    "modules": modules,
                },
                ensure_ascii=False,
            ),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
            env={
                "PATH": os.environ.get("PATH", ""),
                "NODE_ENV": "production",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Web build process is unavailable") from exc
    try:
        result = json.loads(completed.stdout)
    except ValueError as exc:
        raise ValueError((completed.stderr or "Web build failed")[:4000]) from exc
    if not result.get("ok"):
        errors = result.get("errors") or ["Web build failed"]
        raise ValueError("\n".join(str(error) for error in errors)[:4000])
    html = result.get("html")
    if not isinstance(html, str) or not html or len(html) > 512 * 1024:
        raise ValueError("Web build output is invalid")
    return html


def invoke_python(files, handler, arguments, records, timeout=3):
    source = files.get("server/main.py")
    if not isinstance(source, str):
        raise ValueError("Application backend is unavailable")
    request = json.dumps(
        {
            "source": source,
            "handler": handler,
            "arguments": arguments,
            "records": records,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(request) > 2 * 1024 * 1024:
        raise ValueError("Application state is too large")

    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (1, 2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (24, 24))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024,) * 2)

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                str(Path(__file__).with_name("python_runner.py")),
            ],
            input=request,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
            preexec_fn=limits,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Application backend timed out") from exc
    try:
        output = json.loads(completed.stdout)
    except ValueError as exc:
        raise ValueError("Application backend returned invalid output") from exc
    if completed.returncode != 0 or "error" in output:
        raise ValueError(str(output.get("error") or "Application backend failed")[:4000])
    result = output.get("result")
    mutations = output.get("mutations")
    if not isinstance(mutations, list):
        raise ValueError("Application backend returned invalid mutations")
    return result, mutations


def manifest(kit_id, version, display, operations):
    public_operations = [
        {
            "id": operation["id"],
            "agent_visible": operation.get("agent_visible", True),
            "name": operation.get("name", operation["id"]),
            "description": operation.get("description", ""),
            "effect": operation["effect"],
            "timeout_ms": min(int(operation.get("timeout_ms", 5000)), 10000),
            "input_schema": operation["input_schema"],
            "output_schema": operation.get("output_schema", {"type": "object"}),
        }
        for operation in operations
    ]
    public_operations.append(
        {
            "id": "app.delete",
            "agent_visible": True,
            "name": "删除应用",
            "description": "永久删除应用、源码版本和业务数据，必须得到用户明确确认。",
            "effect": "write",
            "timeout_ms": 10000,
            "input_schema": {
                "type": "object",
                "properties": {
                    "confirmation": {"type": "string", "enum": ["DELETE"]}
                },
                "required": ["confirmation"],
                "additionalProperties": False,
            },
            "output_schema": {"type": "object"},
        }
    )
    return {
        "schema": "hymio.kit/v1",
        "id": kit_id,
        "version": version,
        "display": display,
        "api": {
            "transport": "bundled",
            "handler": "kit_host.generated_source:GeneratedSourceKit",
        },
        "operations": public_operations,
        "preview": False,
        "app": {
            "mode": "interactive" if operations else "static",
            "bridge": "hymio.kit.bridge/v1",
        },
    }


def default_files(display, fields):
    fields = fields or []
    properties = {}
    for field in fields:
        kind = field["type"]
        schema = {
            "text": {"type": "string", "maxLength": 2000},
            "number": {"type": "number"},
            "boolean": {"type": "boolean"},
            "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        }[kind]
        schema["description"] = field["label"]
        properties[field["key"]] = schema
    operations = (
        [
            {
                "id": "items.create",
                "handler": "create_item",
                "name": "添加记录",
                "description": f"新增一条{display['item_label']}。",
                "effect": "write",
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": [
                        field["key"] for field in fields if field.get("required")
                    ],
                    "additionalProperties": False,
                },
            },
            {
                "id": "items.list",
                "handler": "list_items",
                "name": "查看记录",
                "description": f"列出最近的{display['item_label']}。",
                "effect": "read",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100}
                    },
                    "additionalProperties": False,
                },
            },
            {
                "id": "summary",
                "handler": "summary",
                "name": "查看数量",
                "description": f"返回{display['item_label']}总数。",
                "effect": "read",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        ]
        if fields
        else []
    )
    files = {
        "app.json": json.dumps(
            {
                "schema": "hymio.app/v1",
                "display": display,
                "operations": operations,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "README.md": (
            "# "
            + display["name"]
            + "\n\nReact frontend in `web/`; bounded Python API in `server/main.py`.\n"
        ),
        "server/main.py": _PYTHON_TEMPLATE,
        "web/src/main.jsx": (
            'import React from "react";\n'
            'import { createRoot } from "react-dom/client";\n'
            'import App from "./App.jsx";\n'
            'import "./styles.css";\n\n'
            'createRoot(document.getElementById("root")).render(<App />);\n'
        ),
        "web/src/App.jsx": _react_template(display, fields),
        "web/src/styles.css": _CSS_TEMPLATE,
    }
    validate_application(files)
    return files


def _react_template(display, fields):
    field_json = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
    display_json = json.dumps(display, ensure_ascii=False, separators=(",", ":"))
    interactive = bool(fields)
    create_js = (
        'const values = Object.fromEntries(new FormData(event.currentTarget));\n'
        "      for (const field of FIELDS) {\n"
        "        if (field.type === \"number\") values[field.key] = Number(values[field.key]);\n"
        "        if (field.type === \"boolean\") {\n"
        "          values[field.key] = values[field.key] === \"true\";\n"
        "        }\n"
        "      }\n"
        "      await submit(\"items.create\", values);"
        if interactive
        else ""
    )
    load_js = (
        'const result = await HymioKit.call("items.list", { limit: 20 });\n'
        "      setItems(result.items || []);"
        if interactive
        else ""
    )
    form = (
        """
      <form className="entry-form" onSubmit={create}>
        <div className="section-title"><h2>新增</h2><span>一次只记一件事</span></div>
        <div className="fields">
          {FIELDS.map((field) => (
            <label key={field.key}>
              <span>{field.label}</span>
              {field.type === "boolean" ? (
                <select name={field.key} defaultValue="true">
                  <option value="true">是</option>
                  <option value="false">否</option>
                </select>
              ) : (
                <input
                  name={field.key}
                  type={
                    field.type === "number" ? "number" :
                    field.type === "date" ? "date" : "text"
                  }
                  step={field.type === "number" ? "any" : undefined}
                  required={field.required}
                />
              )}
            </label>
          ))}
        </div>
        <button className="primary" disabled={busy}>{busy ? "正在保存…" : "记一条"}</button>
      </form>"""
        if interactive
        else """
      <section className="empty">
        <h2>静下来，看一眼</h2>
        <p>这是一个只为你准备的页面。需要数据时，也可以让 Hymio 继续扩展。</p>
      </section>"""
    )
    list_view = (
        """
      <section className="entries">
        <div className="section-title"><h2>最近</h2><span>{items.length} 条</span></div>
        {items.length === 0 ? <p className="muted">还没有记录。</p> : items.map((item) => (
          <article key={item.id}>
            <strong>{Object.values(item.data || {})[0] ?? "一条记录"}</strong>
            <span>{new Date(item.created_at * 1000).toLocaleDateString("zh-CN")}</span>
          </article>
        ))}
      </section>"""
        if interactive
        else ""
    )
    return f"""import React, {{ useEffect, useState }} from "react";

const DISPLAY = {display_json};
const FIELDS = {field_json};

export default function App() {{
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {{
    if (!{str(interactive).lower()}) return;
    try {{
      {load_js}
    }} catch {{
      setError("暂时无法读取记录。");
    }}
  }}

  useEffect(() => {{ load(); }}, []);

  async function create(event) {{
    event.preventDefault();
    if (!{str(interactive).lower()} || busy) return;
    setBusy(true);
    setError("");
    try {{
      {create_js}
      event.currentTarget.reset();
      await load();
    }} catch {{
      setError("没有保存成功，请再试一次。");
    }} finally {{
      setBusy(false);
    }}
  }}

  return (
    <main>
      <header className="hero">
        <span className="eyebrow">{{DISPLAY.tagline}}</span>
        <h1>{{DISPLAY.name}}</h1>
        <p>{{items.length ? `已经留下 ${{items.length}} 条记录` : "从第一条开始，慢慢积累。"}}</p>
      </header>
      {{error && <p className="error">{{error}}</p>}}
      {form}
      {list_view}
    </main>
  );
}}
"""


_PYTHON_TEMPLATE = '''"""Bounded application API.

Only ctx and JSON-compatible arguments are provided.
"""

from datetime import UTC, datetime


def _clean(item):
    return {
        "id": item["id"],
        "data": item.get("data", {}),
        "revision": item.get("revision", 1),
        "created_at": item.get("created_at", 0),
    }


def create_item(ctx, arguments):
    item = ctx.insert(arguments)
    return {
        "entry": _clean(item),
        "count": ctx.count(),
        "message": "已经记下了。",
    }


def list_items(ctx, arguments):
    items = ctx.list(arguments.get("limit", 20))
    return {"items": [_clean(item) for item in items], "count": ctx.count()}


def summary(ctx, arguments):
    return {"count": ctx.count(), "at": datetime.now(UTC).isoformat()}
'''


_CSS_TEMPLATE = """
:root {
  color-scheme: light dark;
  --canvas: light-dark(#f3f4f1, #0b1018);
  --surface: light-dark(#ffffff, #151b26);
  --ink: light-dark(#18202c, #f3f6fb);
  --muted: light-dark(#5c6675, #9daabc);
  --line: light-dark(#e7e9e5, #293344);
  --accent: light-dark(#3f5cff, #aab8ff);
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
}
* { box-sizing: border-box; }
html, body, #root { min-width: 0; overflow-x: hidden; }
body { margin: 0; color: var(--ink); background: var(--canvas); }
main { width: min(100%, 680px); margin: auto; padding: 20px 18px 96px; }
.hero { padding: 26px 22px; border-radius: 28px; background:
  radial-gradient(
    circle at 90% 10%,
    color-mix(in srgb, var(--accent) 20%, transparent),
    transparent 45%
  ),
  var(--surface); border: 1px solid var(--line); }
.eyebrow { color: var(--muted); font-size: 13px; font-weight: 600; }
h1 { margin: 8px 0 5px; font-size: clamp(34px, 10vw, 48px); letter-spacing: -.045em; }
.hero p, .muted, .section-title span { color: var(--muted); }
.entry-form, .entries, .empty { margin-top: 14px; padding: 18px; border-radius: 20px;
  border: 1px solid var(--line); background: var(--surface); }
.section-title { display: flex; justify-content: space-between; align-items: baseline; }
h2 { margin: 0; font-size: 17px; }
.fields { display: grid; gap: 12px; margin: 16px 0; }
label span { display: block; margin-bottom: 6px; color: var(--muted); font-size: 13px; }
input, select { width: 100%; min-height: 46px; padding: 11px 13px; border-radius: 13px;
  border: 1px solid var(--line); background: var(--canvas); color: var(--ink); font: inherit; }
button { min-height: 46px; border: 0; border-radius: 13px; font: 600 16px inherit; }
.actions { display: flex; min-width: 0; gap: 10px; }
.actions > button, .fields > * { min-width: 0; }
.primary { width: 100%; color: white; background: var(--accent); }
article { display: flex; justify-content: space-between; gap: 16px; padding: 14px 0;
  border-bottom: 1px solid var(--line); }
article:last-child { border-bottom: 0; }
article span { color: var(--muted); font-size: 12px; }
.error { padding: 12px 15px; border-radius: 14px; color: #a33a2d; background: #fff0ed; }
@media (prefers-color-scheme: dark) { .error { color: #ffb4aa; background: #3c2020; } }
"""
