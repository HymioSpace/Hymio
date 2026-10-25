import hashlib
import json
import re
import uuid
from pathlib import Path

from . import devsource
from .builtin_ledger import LedgerKit
from .generated import GeneratedCollectionKit
from .generated_source import GeneratedSourceKit
from .store import KitStore

KIT_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
OPERATION_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
HANDLERS = {
    "kit_host.builtin_ledger:LedgerKit": LedgerKit,
    "kit_host.generated:GeneratedCollectionKit": GeneratedCollectionKit,
    "kit_host.generated_source:GeneratedSourceKit": GeneratedSourceKit,
}


class KitNotFound(Exception):
    pass


class KitNotInstalled(Exception):
    pass


def _validate_value(schema, value, path="arguments"):
    expected = schema.get("type")
    valid_type = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": type(value) is int,
        "boolean": isinstance(value, bool),
    }
    if expected in valid_type and not valid_type[expected]:
        raise ValueError(f"{path} must be {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} has an unsupported value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is too small")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(f"{path} is too small")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} is too large")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"{path} is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path} is too long")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ValueError(f"{path} has an invalid format")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise ValueError(f"Missing required arguments: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ValueError(f"Unknown arguments: {', '.join(unknown)}")
        for key, item in value.items():
            if key in properties:
                _validate_value(properties[key], item, f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValueError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path} has too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_value(schema["items"], item, f"{path}[{index}]")


class KitRegistry:
    def __init__(self, directory):
        self.kits = {}
        directory = Path(directory)
        if not directory.is_dir():
            raise ValueError(f"Kit manifest directory does not exist: {directory}")
        for path in sorted(directory.glob("*/manifest.json")):
            manifest = json.loads(path.read_text())
            self._validate(manifest)
            if manifest["id"] in self.kits:
                raise ValueError(f"Duplicate Kit id: {manifest['id']}")
            self.kits[manifest["id"]] = manifest

    @staticmethod
    def _validate(manifest):
        if not isinstance(manifest, dict) or manifest.get("schema") != "hymio.kit/v1":
            raise ValueError("Unsupported Kit manifest")
        kit_id = manifest.get("id")
        if not isinstance(kit_id, str) or not KIT_ID.fullmatch(kit_id):
            raise ValueError("Invalid Kit id")
        version = manifest.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError("Invalid Kit version")
        display = manifest.get("display")
        if not isinstance(display, dict) or any(
            not isinstance(display.get(key), str) or not display[key].strip()
            for key in ("name", "tagline", "description", "category", "icon", "accent")
        ):
            raise ValueError("Kit display metadata is required")
        if display["accent"] not in {"blue", "amber", "green", "rose", "violet"}:
            raise ValueError("Unknown Kit accent")
        api = manifest.get("api")
        if (
            not isinstance(api, dict)
            or api.get("transport") != "bundled"
            or api.get("handler") not in HANDLERS
        ):
            raise ValueError("Unsupported Kit runtime")
        app = manifest.get("app")
        if (
            not isinstance(app, dict)
            or app.get("bridge") != "hymio.kit.bridge/v1"
            or app.get("mode") not in {"static", "interactive"}
        ):
            raise ValueError("Invalid Kit application")
        if not isinstance(manifest.get("preview", False), bool):
            raise ValueError("Invalid Kit preview flag")
        operations = manifest.get("operations")
        if not isinstance(operations, list):
            raise ValueError("Kit operations must be an array")
        seen = set()
        for operation in operations:
            if not isinstance(operation, dict):
                raise ValueError("Invalid operation")
            operation_id = operation.get("id")
            if (
                not isinstance(operation_id, str)
                or not OPERATION_ID.fullmatch(operation_id)
                or operation_id in seen
                or operation.get("effect") not in {"read", "write"}
                or not isinstance(operation.get("input_schema"), dict)
                or not isinstance(operation.get("agent_visible", False), bool)
            ):
                raise ValueError("Invalid operation descriptor")
            seen.add(operation_id)
        if app["mode"] == "static" and any(
            not operation["id"].startswith("app.") for operation in operations
        ):
            raise ValueError("Static Kit applications cannot expose business operations")

    def get(self, kit_id):
        try:
            return self.kits[kit_id]
        except KeyError as exc:
            raise KitNotFound() from exc

    def all(self):
        return list(self.kits.values())


class KitsService:
    def __init__(self, database, manifests):
        self.store = KitStore(Path(database))
        self.root = Path(manifests)
        self.registry = KitRegistry(manifests)
        self.handlers = {}

    def _handler(self, manifest):
        key = manifest["api"]["handler"]
        cache_key = (key, manifest["id"])
        if cache_key not in self.handlers:
            if key in {
                "kit_host.generated:GeneratedCollectionKit",
                "kit_host.generated_source:GeneratedSourceKit",
            }:
                self.handlers[cache_key] = HANDLERS[key](self.store, manifest)
            else:
                self.handlers[cache_key] = HANDLERS[key](self.store)
        return self.handlers[cache_key]

    @staticmethod
    def _catalog_item(manifest, installed=False):
        item = {
            "id": manifest["id"],
            "version": manifest["version"],
            "name": manifest["display"]["name"],
            "tagline": manifest["display"]["tagline"],
            "description": manifest["display"]["description"],
            "category": manifest["display"]["category"],
            "icon": manifest["display"]["icon"],
            "accent": manifest["display"]["accent"],
            "installed": installed,
        }
        item["managed"] = (
            manifest["api"]["handler"]
            in {
                "kit_host.generated:GeneratedCollectionKit",
                "kit_host.generated_source:GeneratedSourceKit",
            }
        )
        return item

    def _all_manifests(self, user_id):
        return [*self.registry.all(), *self.store.generated(user_id)]

    def _manifest(self, user_id, kit_id):
        for manifest in self._all_manifests(user_id):
            if manifest["id"] == kit_id:
                return manifest
        raise KitNotFound()

    def catalog(self, user_id):
        installed = self.store.installed(user_id)
        items = []
        for manifest in self._all_manifests(user_id):
            item = self._catalog_item(manifest, manifest["id"] in installed)
            if item["installed"] and manifest.get("preview", False):
                try:
                    preview = getattr(self._handler(manifest), "preview", None)
                    if preview:
                        item["preview"] = preview(user_id)
                except (AttributeError, KeyError, TypeError, ValueError):
                    pass
            items.append(item)
        return items

    def install(self, user_id, kit_id):
        manifest = self._manifest(user_id, kit_id)
        self.store.install(user_id, kit_id, manifest["version"])
        return self._catalog_item(manifest, True)

    def uninstall(self, user_id, kit_id):
        self._manifest(user_id, kit_id)
        self.store.uninstall(user_id, kit_id)
        return {"installed": False}

    def _installed_manifest(self, user_id, kit_id):
        if kit_id not in self.store.installed(user_id):
            raise KitNotInstalled()
        return self._manifest(user_id, kit_id)

    def app(self, user_id, kit_id):
        manifest = self._installed_manifest(user_id, kit_id)
        if manifest["api"]["handler"] in {
            "kit_host.generated:GeneratedCollectionKit",
            "kit_host.generated_source:GeneratedSourceKit",
        }:
            html = self.store.generated_app(user_id, kit_id)
        else:
            relative = Path(manifest["app"]["entry"])
            if relative.is_absolute():
                raise ValueError("Kit application entry must be relative")
            path = (self.root / kit_id / relative).resolve()
            if self.root.resolve() not in path.parents:
                raise ValueError("Kit application entry escapes manifest directory")
            html = path.read_text(encoding="utf-8")
        if not html.strip() or len(html) > 512 * 1024:
            raise ValueError("Kit application UI is invalid")
        return {
            "kit_id": kit_id,
            "html": html,
            "bridge": "hymio.kit.bridge/v1",
        }

    def invoke(self, user_id, kit_id, operation, arguments, idempotency_key):
        if operation in {"app.update", "app.delete"} and idempotency_key:
            existing = self.store.generated_management_receipt(
                user_id, kit_id, operation, idempotency_key
            )
            if existing is not None:
                return existing
        manifest = self._installed_manifest(user_id, kit_id)
        descriptor = next(
            (value for value in manifest["operations"] if value["id"] == operation),
            None,
        )
        if descriptor is None:
            raise KitNotFound()
        if not isinstance(arguments, dict):
            raise ValueError("Operation arguments must be an object")
        _validate_value(descriptor["input_schema"], arguments)
        if descriptor["effect"] == "write" and not idempotency_key:
            raise ValueError("Write operation requires an idempotency key")
        if operation == "app.get_source":
            source = self.store.generated_app(user_id, kit_id)
            offset = arguments.get("offset", 0)
            limit = arguments.get("limit", 2500)
            end = min(len(source), offset + limit)
            while True:
                complete = end >= len(source)
                result = {
                    "name": manifest["display"]["name"],
                    "tagline": manifest["display"]["tagline"],
                    "description": manifest["display"]["description"],
                    "category": manifest["display"]["category"],
                    "accent": manifest["display"]["accent"],
                    "source_revision": self._source_revision(source),
                    "total_chars": len(source),
                    "offset": offset,
                    "next_offset": None if complete else end,
                    "complete": complete,
                    "app_html": source[offset:end],
                }
                encoded = json.dumps(
                    result, ensure_ascii=False, separators=(",", ":")
                )
                if len(encoded) <= 3600 or end - offset <= 256:
                    break
                end = offset + max(256, (end - offset) * 4 // 5)
            return {
                "kit_id": kit_id,
                "application": {
                    "id": kit_id,
                    "name": manifest["display"]["name"],
                },
                "operation": operation,
                "effect": descriptor["effect"],
                "result": result,
            }
        if operation == "app.update":
            source = self.store.generated_app(user_id, kit_id)
            if arguments["expected_revision"] != self._source_revision(source):
                raise ValueError(
                    "Application source changed; call app.get_source again before editing"
                )
            app_html = arguments.get("app_html")
            replacements = arguments.get("replacements")
            if (app_html is None) == (replacements is None):
                raise ValueError("Provide exactly one of app_html or replacements")
            updated_html = (
                app_html
                if app_html is not None
                else self._apply_replacements(source, replacements)
            )
            if not updated_html.strip():
                raise ValueError("Application HTML is required")
            if len(updated_html) > 512 * 1024:
                raise ValueError("Application HTML is too large")
            updated = self._updated_manifest(manifest, arguments)
            response = {
                "kit_id": kit_id,
                "application": {
                    "id": kit_id,
                    "name": updated["display"]["name"],
                },
                "operation": operation,
                "effect": descriptor["effect"],
                "result": {
                    "name": updated["display"]["name"],
                    "tagline": updated["display"]["tagline"],
                    "description": updated["display"]["description"],
                    "category": updated["display"]["category"],
                    "accent": updated["display"]["accent"],
                    "source_revision": self._source_revision(updated_html),
                    "total_chars": len(updated_html),
                },
            }
            response = self.store.update_generated(
                user_id,
                kit_id,
                updated,
                updated_html,
                idempotency_key,
                response,
                arguments["expected_revision"],
            )
            self.handlers.pop(
                ("kit_host.generated:GeneratedCollectionKit", kit_id), None
            )
            return response
        if operation == "app.delete":
            if arguments != {"confirmation": "DELETE"}:
                raise ValueError("Application deletion requires explicit confirmation")
            response = {
                "kit_id": kit_id,
                "application": {
                    "id": kit_id,
                    "name": manifest["display"]["name"],
                },
                "operation": operation,
                "effect": descriptor["effect"],
                "result": {"deleted": True},
            }
            response = self.store.delete_generated(
                user_id,
                kit_id,
                idempotency_key,
                response,
            )
            self.handlers.pop(
                ("kit_host.generated:GeneratedCollectionKit", kit_id), None
            )
            return response
        result = self._handler(manifest).invoke(
            user_id, operation, arguments, idempotency_key
        )
        return {
            "kit_id": kit_id,
            "application": {
                "id": kit_id,
                "name": manifest["display"]["name"],
            },
            "operation": operation,
            "effect": descriptor["effect"],
            "result": result,
        }

    @staticmethod
    def _updated_manifest(manifest, arguments):
        updated = json.loads(json.dumps(manifest))
        for key, limit in (
            ("name", 40),
            ("tagline", 160),
            ("description", 400),
            ("category", 20),
        ):
            if key not in arguments:
                continue
            value = arguments[key]
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
                raise ValueError(f"Invalid application {key}")
            updated["display"][key] = value.strip()
        if "accent" in arguments:
            accent = arguments["accent"]
            if accent not in {"blue", "amber", "green", "rose", "violet"}:
                raise ValueError("Invalid application accent")
            updated["display"]["accent"] = accent
        return updated

    @staticmethod
    def _source_revision(source):
        return hashlib.sha256(source.encode()).hexdigest()

    @staticmethod
    def _apply_replacements(source, replacements):
        if not isinstance(replacements, list) or not 1 <= len(replacements) <= 16:
            raise ValueError("Application edits require 1 to 16 replacements")
        spans = []
        for replacement in replacements:
            if not isinstance(replacement, dict):
                raise ValueError("Invalid application replacement")
            old = replacement.get("old")
            new = replacement.get("new")
            if (
                not isinstance(old, str)
                or not old
                or not isinstance(new, str)
                or len(old) > 12000
                or len(new) > 12000
            ):
                raise ValueError("Invalid application replacement")
            start = source.find(old)
            if start < 0 or source.find(old, start + 1) >= 0:
                raise ValueError(
                    "Each replacement old value must occur exactly once in the source"
                )
            spans.append((start, start + len(old), new))
        spans.sort()
        if any(
            earlier[1] > later[0] for earlier, later in zip(spans, spans[1:])
        ):
            raise ValueError("Application replacements overlap")
        updated = source
        for start, end, new in reversed(spans):
            updated = updated[:start] + new + updated[end:]
        return updated

    def generate(self, user_id, spec):
        name = spec.get("name")
        tagline = spec.get("tagline")
        description = spec.get("description", tagline)
        category = spec.get("category", "个人")
        accent = spec.get("accent", "blue")
        item_label = spec.get("item_label", "记录")
        fields = spec.get("fields", [])
        app_html = spec.get("app_html")
        if (
            not isinstance(name, str)
            or not 1 <= len(name.strip()) <= 40
            or not isinstance(tagline, str)
            or not 1 <= len(tagline.strip()) <= 160
            or not isinstance(description, str)
            or len(description.strip()) > 400
            or not isinstance(category, str)
            or not 1 <= len(category.strip()) <= 20
            or accent not in {"blue", "amber", "green", "rose", "violet"}
            or not isinstance(item_label, str)
            or not 1 <= len(item_label.strip()) <= 20
            or not isinstance(fields, list)
            or len(fields) > 12
            or not isinstance(app_html, str)
            or not app_html.strip()
            or len(app_html) > 512 * 1024
        ):
            raise ValueError("Invalid generated Kit description")
        normalized = []
        keys = set()
        for field in fields:
            if not isinstance(field, dict):
                raise ValueError("Invalid generated Kit field")
            key = field.get("key")
            label = field.get("label")
            kind = field.get("type")
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", key)
                or key in keys
                or not isinstance(label, str)
                or not 1 <= len(label.strip()) <= 40
                or kind not in {"text", "number", "boolean", "date"}
            ):
                raise ValueError("Invalid generated Kit field")
            keys.add(key)
            normalized.append(
                {
                    "key": key,
                    "label": label.strip(),
                    "type": kind,
                    "required": bool(field.get("required", False)),
                }
            )
        title_field = next(
            (field["key"] for field in normalized if field["type"] == "text"),
            normalized[0]["key"] if normalized else None,
        )
        kit_id = "user." + uuid.uuid4().hex[:12]
        properties = {}
        for field in normalized:
            if field["type"] == "text":
                schema = {"type": "string", "maxLength": 2000}
            elif field["type"] == "number":
                schema = {"type": "number"}
            elif field["type"] == "boolean":
                schema = {"type": "boolean"}
            else:
                schema = {
                    "type": "string",
                    "pattern": r"^\d{4}-\d{2}-\d{2}$",
                }
            schema["description"] = field["label"]
            properties[field["key"]] = schema
        empty_schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        list_schema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 30}
            },
            "additionalProperties": False,
        }
        update_app_schema = {
            "type": "object",
            "properties": {
                "app_html": {"type": "string", "maxLength": 512000},
                "replacements": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 16,
                    "items": {
                        "type": "object",
                        "properties": {
                            "old": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 12000,
                            },
                            "new": {"type": "string", "maxLength": 12000},
                        },
                        "required": ["old", "new"],
                        "additionalProperties": False,
                    },
                },
                "expected_revision": {
                    "type": "string",
                    "pattern": r"^[0-9a-f]{64}$",
                },
                "name": {"type": "string", "minLength": 1, "maxLength": 40},
                "tagline": {"type": "string", "minLength": 1, "maxLength": 160},
                "description": {"type": "string", "maxLength": 400},
                "category": {"type": "string", "minLength": 1, "maxLength": 20},
                "accent": {
                    "type": "string",
                    "enum": ["blue", "amber", "green", "rose", "violet"],
                },
            },
            "required": ["expected_revision"],
            "additionalProperties": False,
        }
        source_read_schema = {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 3000},
            },
            "additionalProperties": False,
        }
        management_operations = [
            {
                "id": "app.get_source",
                "agent_visible": True,
                "name": "查看应用代码",
                "description": (
                    "按字符区间读取生成应用的 HTML 和显示信息。默认返回前 2500 字；"
                    "继续读取时使用 next_offset。"
                ),
                "effect": "read",
                "timeout_ms": 5000,
                "input_schema": source_read_schema,
                "output_schema": {"type": "object"},
            },
            {
                "id": "app.update",
                "agent_visible": True,
                "name": "修改应用",
                "description": (
                    "用完整 HTML 或精确 replacements 修改生成应用，可同时修改名称和显示信息。"
                    "expected_revision 必须来自最近一次 app.get_source 或 app.update。"
                ),
                "effect": "write",
                "timeout_ms": 10000,
                "input_schema": update_app_schema,
                "output_schema": {"type": "object"},
            },
            {
                "id": "app.delete",
                "agent_visible": True,
                "name": "删除应用",
                "description": "永久删除当前生成应用及其业务数据，必须得到用户明确确认。",
                "effect": "write",
                "timeout_ms": 10000,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "confirmation": {
                            "type": "string",
                            "enum": ["DELETE"],
                        }
                    },
                    "required": ["confirmation"],
                    "additionalProperties": False,
                },
                "output_schema": {"type": "object"},
            },
        ]
        manifest = {
            "schema": "hymio.kit/v1",
            "id": kit_id,
            "version": "0.1.0",
            "display": {
                "name": name.strip(),
                "tagline": tagline.strip(),
                "description": description.strip() or tagline.strip(),
                "category": category.strip(),
                "icon": "collection",
                "accent": accent,
            },
            "api": {
                "transport": "bundled",
                "handler": "kit_host.generated:GeneratedCollectionKit",
            },
            "operations": (
                [
                {
                    "id": "items.create",
                    "agent_visible": True,
                    "name": "添加记录",
                    "description": f"新增一条{item_label.strip()}。",
                    "effect": "write",
                    "timeout_ms": 10000,
                    "input_schema": {
                        "type": "object",
                        "properties": properties,
                        "required": [
                            field["key"] for field in normalized if field["required"]
                        ],
                        "additionalProperties": False,
                    },
                    "output_schema": {"type": "object"},
                },
                {
                    "id": "items.list",
                    "agent_visible": True,
                    "name": "查看记录",
                    "description": f"列出最近的{item_label.strip()}。",
                    "effect": "read",
                    "timeout_ms": 5000,
                    "input_schema": list_schema,
                    "output_schema": {"type": "object"},
                },
                {
                    "id": "summary",
                    "agent_visible": True,
                    "name": "查看数量",
                    "description": f"返回{item_label.strip()}的总数。",
                    "effect": "read",
                    "timeout_ms": 5000,
                    "input_schema": empty_schema,
                    "output_schema": {"type": "object"},
                },
                ]
                if normalized
                else []
            )
            + management_operations,
            "preview": bool(normalized),
            "app": {
                "mode": "interactive" if normalized else "static",
                "bridge": "hymio.kit.bridge/v1",
            },
            "collection": {
                "item_label": item_label.strip(),
                "create_label": "记一条",
                "title_field": title_field,
                "fields": normalized,
                "ui_fields": [
                    {
                        "name": field["key"],
                        "label": field["label"],
                        "type": (
                            "number"
                            if field["type"] == "number"
                            else "date"
                            if field["type"] == "date"
                            else "boolean"
                            if field["type"] == "boolean"
                            else "text"
                        ),
                        "required": field["required"],
                        **(
                            {
                                "default": "false",
                                "options": [
                                    {"value": "true", "label": "是"},
                                    {"value": "false", "label": "否"},
                                ],
                            }
                            if field["type"] == "boolean"
                            else {}
                        ),
                    }
                    for field in normalized
                ],
            },
        }
        KitRegistry._validate(manifest)
        self.store.save_generated(kit_id, user_id, manifest, app_html)
        self.store.install(user_id, kit_id, manifest["version"])
        return self._catalog_item(manifest, True) | {
            "operations": [
                {
                    "id": operation["id"],
                    "description": operation["description"],
                    "input_schema": operation["input_schema"],
                }
                for operation in manifest["operations"]
                if operation["agent_visible"]
            ]
        }

    def create_project(self, user_id, spec, request_id=None):
        display, fields = self._project_spec(spec)
        suffix = (
            hashlib.sha256((user_id + "\0" + request_id).encode()).hexdigest()[:12]
            if isinstance(request_id, str) and request_id
            else uuid.uuid4().hex[:12]
        )
        kit_id = "user." + suffix
        files = devsource.default_files(display, fields)
        source_revision = devsource.revision(files)
        self.store.create_project(user_id, kit_id, display, files, source_revision)
        project = self.store.project(user_id, kit_id)
        return {
            "kit_id": kit_id,
            "status": project["status"],
            "display": display,
            "source_revision": source_revision,
        }

    @staticmethod
    def _project_spec(spec):
        name = spec.get("name")
        tagline = spec.get("tagline")
        description = spec.get("description", tagline)
        category = spec.get("category", "个人")
        accent = spec.get("accent", "blue")
        item_label = spec.get("item_label", "记录")
        fields = spec.get("fields", [])
        if (
            not isinstance(name, str)
            or not 1 <= len(name.strip()) <= 40
            or not isinstance(tagline, str)
            or not 1 <= len(tagline.strip()) <= 160
            or not isinstance(description, str)
            or len(description.strip()) > 400
            or not isinstance(category, str)
            or not 1 <= len(category.strip()) <= 20
            or accent not in {"blue", "amber", "green", "rose", "violet"}
            or not isinstance(item_label, str)
            or not 1 <= len(item_label.strip()) <= 20
            or not isinstance(fields, list)
            or len(fields) > 12
        ):
            raise ValueError("Invalid application project description")
        normalized = []
        keys = set()
        for field in fields:
            if not isinstance(field, dict):
                raise ValueError("Invalid application field")
            key = field.get("key")
            label = field.get("label")
            kind = field.get("type")
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", key)
                or key in keys
                or not isinstance(label, str)
                or not 1 <= len(label.strip()) <= 40
                or kind not in {"text", "number", "boolean", "date"}
            ):
                raise ValueError("Invalid application field")
            keys.add(key)
            normalized.append(
                {
                    "key": key,
                    "label": label.strip(),
                    "type": kind,
                    "required": bool(field.get("required", False)),
                }
            )
        display = {
            "name": name.strip(),
            "tagline": tagline.strip(),
            "description": description.strip() or tagline.strip(),
            "category": category.strip(),
            "icon": "collection",
            "accent": accent,
            "item_label": item_label.strip(),
        }
        return display, normalized

    def bind_project_agent(self, user_id, kit_id, agent_id):
        if not isinstance(agent_id, str) or not re.fullmatch(r"[a-f0-9]{32}", agent_id):
            raise ValueError("Invalid coding agent")
        self.store.bind_project_agent(user_id, kit_id, agent_id)
        return {"kit_id": kit_id, "agent_id": agent_id}

    def dev_context(self, user_id, agent_id):
        kit_id = self.store.project_by_agent(user_id, agent_id)
        project = self.store.project(user_id, kit_id)
        app = json.loads(project["files"]["app.json"])
        display = app.get("display", project["display"])
        tree = "\n".join(sorted(project["files"]))
        return {
            "kit_id": kit_id,
            "source_revision": project["source_revision"],
            "display": display,
            "tree": tree,
            "operations": app["operations"],
            "instructions": (
                "You are the application coding context. Work only on this application. "
                "Read the kit-coding skill before making changes. "
                "Use kit_dev to read exact source chunks and apply small patches. The project "
                "contains a React frontend in web/ and a bounded Python API in server/main.py. "
                "Treat app.json operations as the shared API contract. Keep existing data keys "
                "unless the user accepts a new application. Use textContent or JSX escaping for "
                "user data. Run check, fix all errors, then publish with a concise change summary. "
                "Never claim a change is live before publish succeeds."
            ),
        }

    def dev_invoke(
        self,
        user_id,
        agent_id,
        action,
        arguments,
        idempotency_key,
    ):
        if not isinstance(arguments, dict):
            raise ValueError("Development arguments must be an object")
        kit_id = self.store.project_by_agent(user_id, agent_id)
        project = self.store.project(user_id, kit_id)
        if action == "read":
            path = arguments.get("path")
            offset = arguments.get("offset", 0)
            limit = arguments.get("limit", 2500)
            if (
                not isinstance(path, str)
                or path not in project["files"]
                or type(offset) is not int
                or offset < 0
                or type(limit) is not int
                or not 1 <= limit <= 3000
            ):
                raise ValueError("Invalid source read")
            source = project["files"][path]
            end = min(len(source), offset + limit)
            while True:
                complete = end >= len(source)
                result = {
                    "path": path,
                    "source_revision": project["source_revision"],
                    "total_chars": len(source),
                    "offset": offset,
                    "next_offset": None if complete else end,
                    "complete": complete,
                    "content": source[offset:end],
                }
                encoded = json.dumps(
                    result, ensure_ascii=False, separators=(",", ":")
                )
                if len(encoded) <= 3600 or end - offset <= 256:
                    return result
                end = offset + max(256, (end - offset) * 4 // 5)
        if action == "patch":
            if not idempotency_key:
                raise ValueError("A stable idempotency key is required")
            changes = arguments.get("changes")
            deletions = arguments.get("deletions", [])
            expected = arguments.get("expected_revision")
            if not isinstance(expected, str):
                raise ValueError("expected_revision is required")
            files = devsource.apply_changes(
                project["files"], changes, deletions
            )
            source_revision = devsource.revision(files)
            result = {
                "source_revision": source_revision,
                "files": sorted(files),
                "message": "源码已更新，尚未发布。",
            }
            return self.store.update_project(
                user_id,
                kit_id,
                files,
                source_revision,
                expected,
                idempotency_key,
                result,
            )
        if action == "check":
            try:
                devsource.validate_application(project["files"])
                html = devsource.build_web(project["files"])
                return {
                    "ok": True,
                    "source_revision": project["source_revision"],
                    "bytes": len(html),
                    "errors": [],
                }
            except ValueError as exc:
                return {
                    "ok": False,
                    "source_revision": project["source_revision"],
                    "bytes": 0,
                    "errors": str(exc).splitlines()[:20],
                }
        if action == "publish":
            if not idempotency_key:
                raise ValueError("A stable idempotency key is required")
            expected = arguments.get("expected_revision")
            summary = arguments.get("summary")
            if (
                not isinstance(expected, str)
                or expected != project["source_revision"]
                or not isinstance(summary, str)
                or not 1 <= len(summary.strip()) <= 2000
            ):
                raise ValueError("Publish requires the current revision and a summary")
            devsource.validate_application(project["files"])
            html = devsource.build_web(project["files"])
            app = json.loads(project["files"]["app.json"])
            display = app.get("display", project["display"])
            manifest = devsource.manifest(
                kit_id, "1.0.0", display, app["operations"]
            )
            KitRegistry._validate(manifest)
            version = int(project["published_revision"]) + 1
            result = self._catalog_item(manifest, True) | {
                "revision": version,
                "source_revision": project["source_revision"],
                "status": "published",
            }
            published = self.store.publish_project(
                user_id,
                kit_id,
                expected,
                manifest,
                html,
                project["source_revision"],
                summary.strip(),
                agent_id,
                idempotency_key,
                result,
                display,
            )
            self.handlers.pop(
                ("kit_host.generated_source:GeneratedSourceKit", kit_id), None
            )
            return published
        raise ValueError("Unknown application development action")

    def editor(self, user_id, kit_id):
        project = self.store.project(user_id, kit_id)
        return {
            "kit_id": kit_id,
            "display": project["display"],
            "status": project["status"],
            "coding_agent_id": project["coding_agent_id"],
            "source_revision": project["source_revision"],
            "messages": self.store.coding_messages(user_id, kit_id),
            "changes": self.store.app_revisions(user_id, kit_id),
        }

    def agent_context(self, user_id):
        installed = self.store.installed(user_id)
        sections = []
        for manifest in self._all_manifests(user_id):
            if manifest["id"] not in installed:
                continue
            operations = [
                {
                    "operation": operation["id"],
                    "description": operation["description"],
                    "input_schema": operation["input_schema"],
                }
                for operation in manifest["operations"]
                if operation["agent_visible"]
            ]
            sections.append(
                {
                    "kit_id": manifest["id"],
                    "name": manifest["display"]["name"],
                    "description": manifest["display"]["description"],
                    "operations": operations,
                }
            )
        selected = []
        truncated = False
        header = (
            "## Installed applications\n"
            "These applications are installed for this user. Call them directly with "
            "`kit_call`; do not request a catalog or operation list.\n\n"
        )

        def rendered(items, truncated=False):
            return header + json.dumps(
                {"applications": items, "truncated": truncated},
                ensure_ascii=False,
                separators=(",", ":"),
            )

        for section in sections:
            if len(rendered([*selected, section])) <= 7000:
                selected.append(section)
                continue
            truncated = True
            partial = {**section, "operations": []}
            if len(rendered([*selected, partial], True)) > 7000:
                break
            for operation in section["operations"]:
                candidate = {**partial, "operations": [*partial["operations"], operation]}
                if len(rendered([*selected, candidate], True)) > 7000:
                    break
                partial = candidate
            selected.append(partial)
            break
        return {
            "content": rendered(selected, truncated),
            "kits": sections,
        }
