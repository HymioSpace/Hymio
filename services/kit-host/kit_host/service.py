import json
import re
import uuid
from pathlib import Path

from .builtin_ledger import LedgerKit
from .generated import GeneratedCollectionKit
from .store import KitStore

KIT_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
OPERATION_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
HANDLERS = {
    "kit_host.builtin_ledger:LedgerKit": LedgerKit,
    "kit_host.generated:GeneratedCollectionKit": GeneratedCollectionKit,
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
    if isinstance(value, list) and "items" in schema:
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
        if app["mode"] == "static" and operations:
            raise ValueError("Static Kit applications cannot expose operations")

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
            if key == "kit_host.generated:GeneratedCollectionKit":
                self.handlers[cache_key] = HANDLERS[key](self.store, manifest)
            else:
                self.handlers[cache_key] = HANDLERS[key](self.store)
        return self.handlers[cache_key]

    @staticmethod
    def _catalog_item(manifest, installed=False):
        return {
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
        if manifest["api"]["handler"] == "kit_host.generated:GeneratedCollectionKit":
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
        result = self._handler(manifest).invoke(
            user_id, operation, arguments, idempotency_key
        )
        return {"kit_id": kit_id, "operation": operation, "result": result}

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
            "operations": [
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
            else [],
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
