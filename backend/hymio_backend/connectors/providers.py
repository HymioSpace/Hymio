"""Bounded, read-only official HTTP adapters."""

import base64
import re
from datetime import datetime, timedelta, timezone
from html import unescape

import httpx

from .catalog import PROVIDERS, ConnectorError


async def request(client, method, url, **kwargs):
    try:
        async with client.stream(method, url, **kwargs) as response:
            raw = bytearray()
            async for part in response.aiter_bytes():
                raw.extend(part)
                if len(raw) > 2 * 1024 * 1024:
                    raise ConnectorError("upstream_page_too_large", 503)
            import json

            value = json.loads(raw) if raw else {}
            error = value.get("error") if isinstance(value, dict) else None
            reasons = (
                {x.get("reason") for x in error.get("errors", [])}
                if isinstance(error, dict)
                else set()
            )
            if response.status_code == 429 or reasons & {
                "rateLimitExceeded",
                "userRateLimitExceeded",
                "quotaExceeded",
                "dailyLimitExceeded",
            }:
                raise ConnectorError("upstream_rate_limited", 503)
            if response.status_code in {401, 403} or error == "invalid_grant":
                raise ConnectorError("reconnect_required", 409)
            if response.status_code == 404:
                raise ConnectorError("upstream_not_found", 404)
            if response.status_code >= 300:
                raise ConnectorError("upstream_unavailable", 503)
            return value
    except (httpx.HTTPError, ValueError) as exc:
        raise ConnectorError("upstream_unavailable", 503) from exc


def email_item(message):
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    text = []

    def walk(part, depth=0):
        if depth > 8:
            return
        if part.get("mimeType") in {"text/plain", "text/html"}:
            data = part.get("body", {}).get("data", "")
            if isinstance(data, str) and len(data) <= 65536:
                value = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                    "utf-8", errors="replace"
                )
                if part.get("mimeType") == "text/html":
                    value = unescape(re.sub(r"<[^>]*>", " ", value))
                text.append(value[:16000])
        for child in part.get("parts", [])[:20]:
            walk(child, depth + 1)

    walk(message.get("payload", {}))
    return {
        "external_id": str(message["id"]),
        "title": headers.get("subject", "无主题")[:300],
        "text": "\n".join(text)[:16000] or message.get("snippet", "")[:2000],
        "from": headers.get("from", "")[:300],
        "date": headers.get("date", "")[:100],
        "labels": sorted(message.get("labelIds", [])),
        "kind": "email",
    }


async def pull_gmail(client, token, checkpoint):
    api = PROVIDERS["gmail"]["api"]
    headers = {"Authorization": "Bearer " + token}

    async def get(path, **params):
        return await request(client, "GET", api + path, headers=headers, params=params)

    if checkpoint.get("history"):
        try:
            page = await get(
                "/history",
                startHistoryId=checkpoint["history"],
                maxResults=25,
                **({"pageToken": checkpoint["page"]} if checkpoint.get("page") else {}),
            )
        except ConnectorError as exc:
            if exc.code != "upstream_not_found":
                raise
            return await pull_gmail(client, token, {})
        ids = set()
        for item in page.get("history", []):
            for field in (
                "messages",
                "messagesAdded",
                "messagesDeleted",
                "labelsAdded",
                "labelsRemoved",
            ):
                for entry in item.get(field, []):
                    mid = (entry.get("message") or entry).get("id")
                    if mid:
                        ids.add(mid)
        if len(ids) > 200:
            raise ConnectorError("upstream_page_too_large", 503)
        next_state = (
            {"history": checkpoint["history"], "page": page["nextPageToken"]}
            if page.get("nextPageToken")
            else {"history": page["historyId"]}
        )
    else:
        anchor = checkpoint.get("anchor") or (await get("/profile"))["historyId"]
        page = await get(
            "/messages",
            q="in:inbox newer_than:30d",
            maxResults=25,
            **({"pageToken": checkpoint["page"]} if checkpoint.get("page") else {}),
        )
        ids = {x["id"] for x in page.get("messages", [])}
        next_state = (
            {"anchor": anchor, "page": page["nextPageToken"]}
            if page.get("nextPageToken")
            else {"history": anchor}
        )
    items = []
    for mid in sorted(ids):
        try:
            from urllib.parse import quote

            message = await get("/messages/" + quote(mid, safe=""), format="full")
            items.append(
                email_item(message)
                if "INBOX" in message.get("labelIds", [])
                else {"external_id": mid, "deleted": True, "title": "已移出收件箱"}
            )
        except ConnectorError as exc:
            if exc.code != "upstream_not_found":
                raise
            items.append({"external_id": mid, "deleted": True, "title": "邮件已删除"})
    return items, next_state


async def pull_dida(client, token, checkpoint):
    from urllib.parse import quote

    api = PROVIDERS["dida"]["api"]
    headers = {"Authorization": "Bearer " + token}
    projects = await request(client, "GET", api + "/project", headers=headers)
    if not isinstance(projects, list) or len(projects) > 200:
        raise ConnectorError("upstream_page_too_large", 503)
    # Rotate through bounded project windows; never infer deletion from a missing task.
    projects.sort(key=lambda project: str(project["id"]))
    offset = checkpoint.get("project_offset", 0)
    selected = projects[offset : offset + 5]
    items = []
    for project in selected:
        pid = str(project["id"])
        page = await request(
            client, "GET", api + "/project/" + quote(pid, safe="") + "/data", headers=headers
        )
        tasks = page.get("tasks", [])
        if len(tasks) > 500 or len(items) + len(tasks) > 1000:
            raise ConnectorError("upstream_page_too_large", 503)
        for task in tasks:
            items.append(
                {
                    "external_id": pid + ":" + str(task["id"]),
                    "kind": "task",
                    "title": str(task.get("title", ""))[:300],
                    "text": str(task.get("content", ""))[:8000],
                    "project": str(project.get("name", ""))[:200],
                    "due": task.get("dueDate"),
                    "completed": task.get("status") == 2,
                    "priority": task.get("priority", 0),
                }
            )
    if selected:
        now = datetime.now(timezone.utc)
        completed = await request(
            client,
            "POST",
            api + "/task/completed",
            headers=headers,
            json={
                "projectIds": [str(project["id"]) for project in selected],
                "startDate": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S%z"),
                "endDate": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        )
        if not isinstance(completed, list) or len(completed) > 200:
            raise ConnectorError("upstream_page_too_large", 503)
        projects_by_id = {str(project["id"]): project for project in selected}
        for task in completed:
            pid = str(task["projectId"])
            if pid not in projects_by_id:
                continue
            items.append(
                {
                    "external_id": pid + ":" + str(task["id"]),
                    "kind": "task",
                    "title": str(task.get("title", ""))[:300],
                    "text": str(task.get("content", ""))[:8000],
                    "project": str(projects_by_id[pid].get("name", ""))[:200],
                    "due": task.get("dueDate"),
                    "completed": True,
                    "priority": task.get("priority", 0),
                }
            )
    return items, {"project_offset": offset + 5 if offset + 5 < len(projects) else 0}


def normalize_native(provider, data):
    items = data.get("items")
    if not isinstance(items, list) or len(items) > 250:
        raise ConnectorError("invalid_batch")
    result = []
    for value in items:
        if not isinstance(value, dict):
            raise ConnectorError("invalid_item")
        if not isinstance(value.get("title", ""), str):
            raise ConnectorError("invalid_item")
        if provider == "apple_health":
            allowed = {"external_id", "kind", "day", "steps", "active_kcal", "title", "timezone"}
            if set(value) - allowed or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", str(value.get("day", ""))
            ):
                raise ConnectorError("invalid_health_summary")
            try:
                datetime.strptime(value["day"], "%Y-%m-%d")
            except ValueError as exc:
                raise ConnectorError("invalid_health_summary") from exc
            if value.get("external_id") != "daily:" + value["day"]:
                raise ConnectorError("invalid_health_identity")
            for key, maximum in (("steps", 200000), ("active_kcal", 20000)):
                amount = value.get(key)
                if amount is not None and (
                    type(amount) not in (int, float) or not 0 <= amount <= maximum
                ):
                    raise ConnectorError("invalid_health_summary")
        else:
            allowed = {"external_id", "kind", "title", "start", "end", "calendar_id", "all_day"}
            if set(value) - allowed:
                raise ConnectorError("invalid_calendar_event")
            for key in ("start", "end"):
                try:
                    parsed = datetime.fromisoformat(value[key].replace("Z", "+00:00"))
                    if not parsed.tzinfo:
                        raise ValueError()
                    value[key] = (
                        parsed.astimezone(timezone.utc)
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z")
                    )
                except (ValueError, KeyError, TypeError, AttributeError) as exc:
                    raise ConnectorError("invalid_calendar_event") from exc
        value["kind"] = "health_daily" if provider == "apple_health" else "calendar_event"
        if provider == "apple_calendar" and (
            not isinstance(value.get("calendar_id"), str)
            or not 1 <= len(value["calendar_id"]) <= 512
            or value["end"] < value["start"]
        ):
            raise ConnectorError("invalid_calendar_event")
        identity = value.get("external_id")
        if (
            not isinstance(identity, str)
            or not 1 <= len(identity) <= 512
            or len(str(value.get("title", ""))) > 300
        ):
            raise ConnectorError("invalid_item")
        result.append(value)
    reconciliation = None
    if provider == "apple_calendar" and data.get("complete") is True:
        window = data.get("window", {})
        try:
            start, end = (
                datetime.fromisoformat(window[k].replace("Z", "+00:00")) for k in ("start", "end")
            )
            if not start.tzinfo or not end.tzinfo or not 0 < (end - start).days <= 45:
                raise ValueError()
            calendars = window["calendars"]
            if (
                not isinstance(calendars, list)
                or not 1 <= len(calendars) <= 100
                or any(not isinstance(x, str) or len(x) > 512 for x in calendars)
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ConnectorError("invalid_calendar_window") from exc
        reconciliation = {
            "start": start.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
            "end": end.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
            "calendars": calendars,
        }
    return result, reconciliation
