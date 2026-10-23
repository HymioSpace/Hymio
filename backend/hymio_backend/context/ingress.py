"""Read authentic Oath events through its authenticated public history API."""

import asyncio

import httpx

from .client import ContextError


async def import_conversation(settings, client, user_id, credential, data):
    if set(data) - {"before", "limit"}:
        raise ValueError("Unknown import fields")
    limit = data.get("limit", 10)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Invalid page limit")
    params = {"limit": limit}
    if data.get("before") is not None:
        before = data["before"]
        if type(before) is not int or before < 1:
            raise ValueError("Invalid history cursor")
        params["before"] = before
    async with httpx.AsyncClient(timeout=30, trust_env=False) as upstream:
        response = await upstream.get(
            settings.oath_biz.rstrip("/") + "/conversation_history",
            params=params,
            headers={"Authorization": "Bearer " + credential},
        )
    if response.status_code != 200:
        raise ContextError(503, "conversation_unavailable", "Conversation history unavailable")
    page = response.json()
    imported = []
    for event in page["events"]:
        kind = event.get("event_type")
        if kind not in {"user.message", "assistant.message"}:
            continue
        payload = event.get("payload") or {}
        text = payload.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        seq = str(event["event_seq"])
        record = await asyncio.to_thread(
            client.call,
            user_id,
            "records.append",
            operation_id="oath-history:" + seq,
            data={
                "item_type": "context",
                "context_type": "conversation",
                "context": {
                    "text": text,
                    "role": "user" if kind == "user.message" else "assistant",
                    "event_seq": seq,
                    "message_id": payload.get("message_id"),
                },
                "produced_at": event.get("occur_dt"),
                "source": {
                    "kind": "conversation",
                    "namespace": "oath.conversation",
                    "external_id": seq,
                    "version": "1",
                    "parser": "oath-history.v1",
                },
            },
        )
        imported.append(record["data"]["id"])
    return {
        "record_ids": imported,
        "before_cursor": page.get("before_cursor"),
        "has_more": bool(page.get("has_more")),
        "checkpoint": page.get("checkpoint"),
    }
