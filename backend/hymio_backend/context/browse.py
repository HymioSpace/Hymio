"""Product cards over the authoritative context store; no parallel memory database."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor

CATEGORIES = {"work": "工作", "learning": "学习", "life": "生活", "uncategorized": "未分类"}
ALIASES = {**{key: key for key in CATEGORIES}, **{v: k for k, v in CATEGORIES.items()}}
PAGE_SIZE = 30


def card(hit, value):
    context = value.get("context") or {}
    metadata = value.get("fields") if hit["kind"] == "artifact" else context.get("memory")
    metadata = metadata if isinstance(metadata, dict) else {}
    raw_category = metadata.get("category") or context.get("category")
    category = ALIASES.get(raw_category) if isinstance(raw_category, str) else None
    if not category:
        category = next(
            (ALIASES[t] for t in hit.get("topics", []) if t in ALIASES), "uncategorized"
        )
    title = metadata.get("title") or context.get("title")
    return {
        **hit,
        "category": category,
        "labels": metadata.get("labels") or [CATEGORIES[category]],
        "domains": metadata.get("domains") or [],
        "title": title if isinstance(title, str) else "",
        "updated_at": value.get("updated_at"),
    }


def browse(client, user_id, data):
    if set(data) - {"target", "query", "category", "source_kind", "cursor", "limit"}:
        raise ValueError("Unknown browse options")
    target = data.get("target", "artifacts")
    query = data.get("query") or ""
    category = data.get("category") or "all"
    source = data.get("source_kind") or "all"
    limit = data.get("limit", 30)
    if (
        not isinstance(target, str)
        or target not in {"artifacts", "records"}
        or not isinstance(query, str)
        or len(query) > 4000
        or not isinstance(category, str)
        or not 1 <= len(category) <= 32
        or source not in {"all", "conversation", "user", "connector", "kit", "legacy"}
        or type(limit) is not int
        or not 1 <= limit <= 30
    ):
        raise ValueError("Invalid browse options")
    signature = [target, query, category, source]
    upstream, offset = None, 0
    if data.get("cursor"):
        try:
            encoded = data["cursor"]
            if not isinstance(encoded, str) or len(encoded) > 8192:
                raise ValueError("Invalid cursor")
            state = json.loads(base64.urlsafe_b64decode(encoded.encode()))
            upstream, offset = state["upstream"], state["offset"]
            if (
                state["scope"] != signature
                or type(offset) is not int
                or not 0 <= offset < PAGE_SIZE
                or (upstream is not None and not isinstance(upstream, str))
            ):
                raise ValueError("Cursor scope changed")
        except Exception as exc:
            raise ValueError("Invalid cursor") from exc
    items, partial = [], False
    exhausted = False
    # Bound one response to four upstream pages. Sparse filters can continue with a cursor.
    for _ in range(4):
        page = client.call(
            user_id,
            "search",
            data={
                "target": target,
                "mode": "text" if query else "filter",
                "query": query or None,
                "filters": {"source_kind": source}
                if target == "records" and source != "all"
                else {},
                "limit": PAGE_SIZE,
                "cursor": upstream,
            },
        )["data"]
        hits = page["items"]
        partial = partial or page.get("partial", False)
        candidates = [h for h in hits[offset:] if not h["id"].startswith("_")]

        def enrich(hit):
            value = client.call(
                user_id,
                "artifacts.read" if hit["kind"] == "artifact" else "records.read",
                item_id=hit["id"],
            )["data"]
            return card(hit, value)

        with ThreadPoolExecutor(max_workers=6) as pool:
            cards = iter(pool.map(enrich, candidates))
            for index in range(offset, len(hits)):
                hit = hits[index]
                offset = index + 1
                if hit["id"].startswith("_"):
                    continue
                item = next(cards)
                if category == "all" or item["category"] == category or category in item["labels"]:
                    items.append(item)
                if len(items) == limit:
                    break
        if offset >= len(hits):
            upstream, offset = page.get("next_cursor"), 0
            if not upstream:
                exhausted = True
        if exhausted or len(items) == limit:
            break
    cursor = (
        None
        if exhausted
        else base64.urlsafe_b64encode(
            json.dumps(
                {
                    "scope": signature,
                    "upstream": upstream,
                    "offset": offset,
                },
                separators=(",", ":"),
            ).encode()
        ).decode()
    )
    return {"items": items, "next_cursor": cursor, "partial": partial}
