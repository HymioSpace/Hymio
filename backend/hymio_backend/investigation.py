"""Small trigger summaries for the admin request list and Trace inspector."""

import json


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def trigger(stage, body):
    if stage not in {"gateway.received", "oath.input.user", "oath.input.system", "oath.input.tool"}:
        return None
    body = decode(body)
    for _ in range(5):
        if not isinstance(body, dict):
            break
        if "attributes" in body:
            body = decode(body["attributes"].get("body", body["attributes"]))
        elif "body" in body:
            body = decode(body["body"])
        else:
            break
    kind = "user" if stage in {"gateway.received", "oath.input.user"} else stage.rsplit(".", 1)[-1]
    source = body.get("source", "") if isinstance(body, dict) else ""
    payload = body.get("payload", body) if isinstance(body, dict) else body
    if isinstance(payload, dict):
        text = (
            payload.get("content")
            or payload.get("message")
            or payload.get("objective")
            or payload.get("title")
        )
        if not isinstance(text, str):
            text = source or ("工具执行结果" if kind == "tool" else "系统事件")
    else:
        text = payload if isinstance(payload, str) else ""
    return {
        "kind": kind,
        "label": {"user": "用户消息", "system": "系统唤醒", "tool": "工具结果"}[kind],
        "text": text.strip()[:500],
        "source": source,
    }


def trace_triggers(trace):
    result = []
    seen = set()
    for span in trace.get("spans", []):
        for event in span.get("events", []):
            item = trigger(event.get("name", ""), event.get("attributes", {}))
            if item:
                # Gateway and Oath record the same user input with different sources.
                key = (item["kind"], item["text"], "" if item["kind"] == "user" else item["source"])
                if key not in seen:
                    seen.add(key)
                    result.append(item)
    return result[:12]
