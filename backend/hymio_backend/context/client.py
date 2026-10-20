import json
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx


class ContextError(Exception):
    def __init__(self, status, code, message, *, data=None):
        self.status = status
        self.data = data or {"error": {"code": code, "message": message}}


class NostalgiaClient:
    """Closed operation mapping; model input never selects a host or credential."""

    READS = {"injection", "records.list", "records.read", "artifacts.read", "dreams.read"}
    WRITES = {
        "records.append",
        "records.mark",
        "artifacts.put",
        "artifacts.delete",
        "dreams.begin",
        "dreams.commit",
        "dreams.abort",
    }

    def __init__(self, settings):
        self.settings = settings

    def connection(self, user_id):
        path = getattr(self.settings, "nostalgia_connections_file", None)
        if not path:
            raise ContextError(503, "context_disabled", "Nostalgia is not configured")
        path = Path(path)
        try:
            bindings = json.loads(path.read_text())["users"]
            entry = bindings.get(user_id)
            if entry is None:
                raise ContextError(403, "context_unbound", "No context endpoint for this user")
            url = entry["url"].rstrip("/")
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Invalid endpoint")
            token_file = Path(entry["token_file"]).expanduser()
            if not token_file.is_absolute():
                token_file = path.parent / token_file
            token = token_file.read_text().strip()
            if len(token) < 16:
                raise ValueError("Missing credential")
            return url, token
        except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ContextError(
                503, "context_configuration", "Invalid context configuration"
            ) from exc

    def call(
        self,
        user_id,
        action,
        *,
        item_id=None,
        dream_id=None,
        data=None,
        query=None,
        etag=None,
        create=False,
        operation_id=None,
    ):
        if action not in self.READS | self.WRITES | {"search"}:
            raise ValueError("Unsupported context action")
        if action in self.WRITES and (
            not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 160
        ):
            raise ValueError("Writes require a stable operation_id of 1..160 characters")
        if (
            action
            in {
                "records.mark",
                "artifacts.put",
                "artifacts.delete",
                "dreams.commit",
                "dreams.abort",
            }
            and not dream_id
        ):
            raise ValueError("This operation requires dream_id")
        if action in {
            "records.read",
            "records.mark",
            "artifacts.read",
            "artifacts.put",
            "artifacts.delete",
        } and not isinstance(item_id, str):
            raise ValueError("This operation requires item_id")
        if action == "dreams.read" and not dream_id:
            raise ValueError("This operation requires dream_id")
        component = quote(str(item_id), safe="")
        dream = quote(str(dream_id), safe="")
        routes = {
            "injection": ("GET", "/v1/injection"),
            "records.list": ("GET", "/v1/records"),
            "records.read": ("GET", f"/v1/records/{component}"),
            "records.append": ("POST", "/v1/records"),
            "records.mark": ("PATCH", f"/v1/records/{component}"),
            "artifacts.read": ("GET", f"/v1/artifacts/{component}"),
            "artifacts.put": ("PUT", f"/v1/artifacts/{component}"),
            "artifacts.delete": ("DELETE", f"/v1/artifacts/{component}"),
            "search": ("POST", "/v1/search"),
            "dreams.begin": ("POST", "/v1/dreams"),
            "dreams.read": ("GET", f"/v1/dreams/{dream}"),
            "dreams.commit": ("POST", f"/v1/dreams/{dream}/commit"),
            "dreams.abort": ("POST", f"/v1/dreams/{dream}/abort"),
        }
        method, path = routes[action]
        params = dict(query or {})
        payload = dict(data or {})
        if dream_id and action in {
            "records.list",
            "records.read",
            "records.mark",
            "artifacts.read",
            "artifacts.put",
            "artifacts.delete",
        }:
            if params.get("dream_id", dream_id) != dream_id:
                raise ValueError("Conflicting dream scopes")
            params["dream_id"] = dream_id
        if action == "search" and dream_id:
            if payload.get("dream_id", dream_id) != dream_id:
                raise ValueError("Conflicting dream scopes")
            payload["dream_id"] = dream_id
        if action == "records.list":
            params.setdefault("limit", 10)
        if action == "search":
            payload.setdefault("limit", 10)
        headers = {"Content-Type": "application/json"}
        if action in self.WRITES:
            headers["Idempotency-Key"] = operation_id
        if etag:
            headers["If-Match"] = etag
        if create:
            headers["If-None-Match"] = "*"
        url, token = self.connection(user_id)
        headers["Authorization"] = "Bearer " + token
        try:
            with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    method,
                    url + path,
                    params=params,
                    headers=headers,
                    json=payload if method in {"POST", "PUT", "PATCH"} else None,
                ) as res:
                    raw = bytearray()
                    for chunk in res.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise ContextError(
                                503,
                                "context_response_limit",
                                "Read fewer records; retry writes with the same operation_id",
                            )
                    value = json.loads(raw) if raw else None
                    if res.status_code >= 300:
                        raise ContextError(
                            res.status_code, "context_rejected", "Request rejected", data=value
                        )
                    return {
                        "status_code": res.status_code,
                        "data": value,
                        "etag": res.headers.get("etag"),
                    }
        except (httpx.HTTPError, ValueError) as exc:
            raise ContextError(
                503,
                "context_unavailable",
                "Result unavailable; retry writes with the same operation_id",
            ) from exc
