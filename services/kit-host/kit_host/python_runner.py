"""Trusted runner for bounded generated Python API handlers."""

import json
import math
import re
import statistics
import sys
import uuid
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    allowed = {
        "collections": __import__("collections"),
        "datetime": __import__("datetime"),
        "json": json,
        "math": math,
        "re": re,
        "statistics": statistics,
    }
    if level != 0 or name not in allowed:
        raise ImportError("This module is unavailable in an application backend")
    return allowed[name]


SAFE_BUILTINS = {
    "Exception": Exception,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "date": date,
    "datetime": datetime,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "object": object,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "timedelta": timedelta,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "__import__": safe_import,
}


class Context:
    def __init__(self, records):
        self._records = {
            row["id"]: deepcopy(row)
            for row in records
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        self._mutations = {}

    def list(self, limit=20):
        limit = max(1, min(int(limit), 100))
        rows = sorted(
            self._records.values(),
            key=lambda row: (row.get("created_at", 0), row["id"]),
            reverse=True,
        )
        return deepcopy(rows[:limit])

    def get(self, record_id):
        row = self._records.get(str(record_id))
        return deepcopy(row) if row else None

    def insert(self, data):
        if not isinstance(data, dict):
            raise ValueError("Record data must be an object")
        record_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        row = {
            "id": record_id,
            "data": deepcopy(data),
            "revision": 1,
            "created_at": now.timestamp(),
        }
        self._records[record_id] = row
        self._mutations[record_id] = ("insert", deepcopy(row))
        return deepcopy(row)

    def update(self, record_id, changes):
        row = self._records.get(str(record_id))
        if not row or not isinstance(changes, dict):
            raise ValueError("Record not found or changes are invalid")
        data = deepcopy(row["data"])
        data.update(deepcopy(changes))
        row = {**row, "data": data, "revision": int(row["revision"]) + 1}
        self._records[row["id"]] = row
        self._mutations[row["id"]] = ("update", deepcopy(row))
        return deepcopy(row)

    def delete(self, record_id):
        record_id = str(record_id)
        if record_id not in self._records:
            raise ValueError("Record not found")
        del self._records[record_id]
        self._mutations[record_id] = ("delete", {"id": record_id})

    def count(self):
        return len(self._records)

    def mutations(self):
        return [
            (
                {"kind": kind, "id": value["id"]}
                if kind == "delete"
                else {"kind": kind, "record": value}
            )
            for kind, value in self._mutations.values()
        ]


def main():
    request = json.load(sys.stdin)
    source = request["source"]
    handler_name = request["handler"]
    arguments = request["arguments"]
    context = Context(request.get("records", []))
    namespace = {"__builtins__": SAFE_BUILTINS, "__name__": "hymio_application"}
    exec(compile(source, "<application>", "exec"), namespace, namespace)
    handler = namespace.get(handler_name)
    if not callable(handler):
        raise ValueError("Application API handler is unavailable")
    result = handler(context, arguments)
    json.dump(
        {"result": result, "mutations": context.mutations()},
        sys.stdout,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        json.dump(
            {"error": f"{type(exc).__name__}: {exc}"[:2000]},
            sys.stdout,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        raise SystemExit(1)
