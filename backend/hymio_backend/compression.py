"""Read-only aggregation for durable context-compaction events."""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from datetime import datetime
from typing import Any

from .client_telemetry import percentile

COMPACTION_EVENT = "server.context.compaction"
STEP_STATUS_EVENT = "server.step.status"


def empty(*, window_hours: float = 0) -> dict[str, Any]:
    return {
        "window_hours": window_hours,
        "attempts": 0,
        "started": 0,
        "ready": 0,
        "applied": 0,
        "failed": 0,
        "skipped": 0,
        "blocked_steps": 0,
        "by_mode": {},
        "reasons": [],
        "duration": {"p50": None, "p95": None},
        "recent": [],
        "unavailable": True,
    }


def _body(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return round(value, 3) if math.isfinite(value) and value >= 0 else None


def _timestamp(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def summary(
    sessions,
    *,
    since: float,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return compact, content-free compaction health for the admin console."""
    with sessions.transaction() as db:
        if events is None:
            rows = [
                {
                    **dict(row),
                    "event_type": row["stage"],
                    "payload": row["body"],
                }
                for row in db.execute(
                    "SELECT e.user_id,e.trace_id,e.channel,e.stage,e.occurred_at,e.body,"
                    "u.name AS user_name FROM events e "
                    "LEFT JOIN users u ON u.user_id=e.user_id "
                    "WHERE e.occurred_at>=? AND e.stage IN (?,?) "
                    "ORDER BY e.id DESC LIMIT 5000",
                    (since, COMPACTION_EVENT, STEP_STATUS_EVENT),
                )
            ]
        else:
            user_ids = sorted(
                {event.get("user_id") for event in events if isinstance(event.get("user_id"), str)}
            )
            names = {}
            if user_ids:
                names = {
                    row[0]: row[1] or ""
                    for row in db.execute(
                        f"SELECT user_id,name FROM users WHERE user_id IN "
                        f"({','.join('?' for _ in user_ids)})",
                        user_ids,
                    )
                }
            rows = []
            for event in events:
                occurred_at = _timestamp(event.get("occurred_at"))
                if occurred_at is None or occurred_at < since:
                    continue
                rows.append(
                    {
                        "user_id": str(event.get("user_id") or ""),
                        "user_name": names.get(event.get("user_id"), ""),
                        "channel": str((event.get("payload") or {}).get("channel") or "unknown"),
                        "trace_id": str((event.get("payload") or {}).get("trace_id") or ""),
                        "stage": str(event.get("event_type") or ""),
                        "event_type": str(event.get("event_type") or ""),
                        "occurred_at": occurred_at,
                        "body": event.get("payload") or {},
                    }
                )

    attempts: dict[str, dict[str, Any]] = {}
    blocked_steps = 0
    for row in sorted(rows, key=lambda item: item["occurred_at"]):
        payload = _body(row["body"])
        if row["event_type"] == STEP_STATUS_EVENT:
            if payload.get("status") == "paused" and payload.get("reason") == "context_window":
                blocked_steps += 1
            continue
        identity = str(payload.get("compression_id") or f"event:{row['occurred_at']}")
        attempt = attempts.setdefault(
            identity,
            {
                "compression_id": identity,
                "user_id": row["user_id"],
                "user_name": row["user_name"] or "",
                "channel": row["channel"] or "unknown",
                "trace_id": row["trace_id"] or str(payload.get("trace_id") or ""),
                "step_id": str(payload.get("step_id") or ""),
                "mode": str(payload.get("mode") or "unknown"),
                "status": "started",
                "reason": "",
                "covers": _int(payload.get("covers")),
                "context_window": _int(payload.get("context_window")),
                "input_tokens": _int(payload.get("input_tokens")),
                "output_tokens": _int(payload.get("output_tokens")),
                "duration_ms": _float(payload.get("duration_ms")),
                "started_at": None,
                "finished_at": None,
                "applied": False,
            },
        )
        attempt["trace_id"] = (
            row["trace_id"] or attempt["trace_id"] or str(payload.get("trace_id") or "")
        )
        attempt["step_id"] = str(payload.get("step_id") or attempt["step_id"] or "")
        attempt["mode"] = str(payload.get("mode") or attempt["mode"])
        status = str(payload.get("status") or "")
        if status == "started":
            attempt["started_at"] = row["occurred_at"]
        elif status == "applied":
            attempt["applied"] = True
            attempt["finished_at"] = row["occurred_at"]
        elif status in {"ready", "failed", "skipped"}:
            attempt["status"] = status
            attempt["reason"] = str(payload.get("reason") or "")
            attempt["finished_at"] = row["occurred_at"]
            attempt["duration_ms"] = _float(payload.get("duration_ms"))
        for key in ("covers", "context_window", "input_tokens", "output_tokens"):
            value = _int(payload.get(key))
            if value is not None:
                attempt[key] = value

    values = list(attempts.values())
    status_counts = Counter(item["status"] for item in values)
    modes: dict[str, Counter] = {}
    for item in values:
        modes.setdefault(item["mode"], Counter())[item["status"]] += 1
    durations = [
        float(item["duration_ms"])
        for item in values
        if isinstance(item["duration_ms"], (int, float))
    ]
    reasons = Counter(
        item["reason"]
        for item in values
        if item["status"] in {"failed", "skipped"} and item["reason"]
    )
    return {
        "window_hours": round((time.time() - since) / 3600, 2),
        "attempts": len(values),
        "started": status_counts["started"],
        "ready": status_counts["ready"],
        "applied": sum(bool(item["applied"]) for item in values),
        "failed": status_counts["failed"],
        "skipped": status_counts["skipped"],
        "blocked_steps": blocked_steps,
        "by_mode": {
            mode: {
                "attempts": sum(counts.values()),
                "started": counts["started"],
                "ready": counts["ready"],
                "failed": counts["failed"],
                "skipped": counts["skipped"],
                "applied": sum(1 for item in values if item["mode"] == mode and item["applied"]),
            }
            for mode, counts in sorted(modes.items())
        },
        "reasons": [{"reason": reason, "count": count} for reason, count in reasons.most_common()],
        "duration": {
            "p50": round(percentile(durations, 0.5) or 0, 1) if durations else None,
            "p95": round(percentile(durations, 0.95) or 0, 1) if durations else None,
        },
        "recent": sorted(
            values,
            key=lambda item: item["started_at"] or item["finished_at"] or 0,
            reverse=True,
        )[:80],
    }


__all__ = ["empty", "summary"]
