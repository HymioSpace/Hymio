"""Privacy-bounded end-to-end samples reported by product clients."""

import math
import time
from collections import defaultdict
from typing import Any

CHANNELS = frozenset({"web", "ios", "desk", "chrome", "unknown"})
OUTCOMES = frozenset(
    {"sent", "accepted", "in_progress", "completed", "failed", "cancelled", "partial", "stalled"}
)
TIMINGS = {
    "accepted_ms": float,
    "first_response_ms": float,
    "first_renderable_ms": float,
    "first_paint_ms": float,
    "completed_ms": float,
}


def _bounded_text(value: object, limit: int = 128) -> str:
    return value[:limit] if isinstance(value, str) and value else ""


def _timing(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_timing")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 86_400_000:
        raise ValueError("invalid_timing")
    return round(value, 3)


def trace_stats(trace: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(trace, dict) or not isinstance(trace.get("spans"), list):
        return {}
    spans = trace["spans"]
    steps = [
        span
        for span in spans
        if isinstance(span, dict)
        and span.get("name") == "invoke_agent"
        and span.get("parent_span_id") is None
    ]
    models = [
        span
        for span in spans
        if isinstance(span, dict)
        and isinstance(span.get("attributes"), dict)
        and span["attributes"].get("gen_ai.operation.name") == "chat"
    ]
    tools = [
        span
        for span in spans
        if isinstance(span, dict) and str(span.get("name", "")).startswith("execute_tool ")
    ]
    successes = [
        span for span in tools if span.get("attributes", {}).get("oath.tool.outcome") == "succeeded"
    ]
    return {
        "step_count": len(steps),
        "model_calls": len(models),
        "tool_calls": len(tools),
        "tool_successes": len(successes),
        "tool_ms": round(
            sum(
                float(span["duration_ms"])
                for span in tools
                if isinstance(span.get("duration_ms"), (int, float))
            ),
            3,
        ),
    }


def record(sessions, user_id: str, data: dict[str, Any], trace: dict[str, Any] | None) -> dict:
    message_id = _bounded_text(data.get("message_id"))
    if not message_id:
        raise ValueError("message_id_required")
    channel = _bounded_text(data.get("channel"), 32) or "unknown"
    if channel not in CHANNELS:
        raise ValueError("invalid_channel")
    outcome = _bounded_text(data.get("outcome"), 32)
    if outcome not in OUTCOMES:
        raise ValueError("invalid_outcome")
    sent_at = data.get("sent_at")
    if isinstance(sent_at, bool) or not isinstance(sent_at, (int, float)):
        raise ValueError("invalid_sent_at")
    if not math.isfinite(float(sent_at)) or sent_at <= 0:
        raise ValueError("invalid_sent_at")
    sample = {
        "message_id": message_id,
        "channel": channel,
        "client_id": _bounded_text(data.get("client_id")),
        "device_id": _bounded_text(data.get("device_id")),
        "trace_id": _bounded_text(data.get("trace_id"), 64),
        "sent_at": float(sent_at),
        "outcome": outcome,
        "received_at": time.time(),
        **{key: _timing(data.get(key)) for key in TIMINGS},
        **trace_stats(trace),
    }
    with sessions.transaction() as db:
        db.execute(
            """
            INSERT INTO client_turns(
                user_id,message_id,channel,client_id,device_id,trace_id,sent_at,
                accepted_ms,first_response_ms,first_renderable_ms,first_paint_ms,completed_ms,
                outcome,step_count,model_calls,tool_calls,tool_successes,tool_ms,received_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id,message_id) DO UPDATE SET
                channel=excluded.channel,client_id=excluded.client_id,device_id=excluded.device_id,
                trace_id=CASE WHEN excluded.trace_id<>'' THEN excluded.trace_id
                    ELSE client_turns.trace_id END,
                accepted_ms=COALESCE(client_turns.accepted_ms,excluded.accepted_ms),
                first_response_ms=COALESCE(client_turns.first_response_ms,excluded.first_response_ms),
                first_renderable_ms=COALESCE(client_turns.first_renderable_ms,excluded.first_renderable_ms),
                first_paint_ms=COALESCE(client_turns.first_paint_ms,excluded.first_paint_ms),
                completed_ms=COALESCE(client_turns.completed_ms,excluded.completed_ms),
                outcome=CASE WHEN client_turns.outcome='completed' THEN client_turns.outcome
                    WHEN excluded.outcome IN ('completed','failed','cancelled','partial')
                        THEN excluded.outcome
                    WHEN client_turns.outcome IN ('failed','cancelled','partial')
                        THEN client_turns.outcome
                    WHEN excluded.outcome='sent' THEN client_turns.outcome
                    ELSE excluded.outcome END,
                step_count=COALESCE(excluded.step_count,client_turns.step_count),
                model_calls=COALESCE(excluded.model_calls,client_turns.model_calls),
                tool_calls=COALESCE(excluded.tool_calls,client_turns.tool_calls),
                tool_successes=COALESCE(excluded.tool_successes,client_turns.tool_successes),
                tool_ms=COALESCE(excluded.tool_ms,client_turns.tool_ms),
                received_at=excluded.received_at
            """,
            (
                user_id,
                sample["message_id"],
                sample["channel"],
                sample["client_id"],
                sample["device_id"],
                sample["trace_id"],
                sample["sent_at"],
                sample["accepted_ms"],
                sample["first_response_ms"],
                sample["first_renderable_ms"],
                sample["first_paint_ms"],
                sample["completed_ms"],
                sample["outcome"],
                sample.get("step_count"),
                sample.get("model_calls"),
                sample.get("tool_calls"),
                sample.get("tool_successes"),
                sample.get("tool_ms"),
                sample["received_at"],
            ),
        )
    return sample


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summary(sessions, *, since: float, channel: str = "") -> dict[str, Any]:
    with sessions.transaction() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT ct.*, u.name AS user_name FROM client_turns ct "
                "LEFT JOIN users u ON u.user_id=ct.user_id WHERE ct.received_at>=? "
                + ("AND ct.channel=? " if channel else "")
                + "ORDER BY ct.received_at DESC LIMIT 5000",
                (since, channel) if channel else (since,),
            )
        ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["channel"]].append(row)
    stages = (
        "accepted_ms",
        "first_response_ms",
        "first_renderable_ms",
        "first_paint_ms",
        "completed_ms",
    )
    channels = []
    for name, samples in sorted(grouped.items()):
        outcomes = {
            outcome: sum(row["outcome"] == outcome for row in samples)
            for outcome in sorted(OUTCOMES)
        }
        channels.append(
            {
                "channel": name,
                "turns": len(samples),
                "completed": outcomes["completed"],
                "failed": outcomes["failed"],
                "cancelled": outcomes["cancelled"],
                "partial": outcomes["partial"],
                "stalled": outcomes["stalled"],
                "outcomes": outcomes,
                "no_ack": sum(
                    row["outcome"] == "stalled" and row["accepted_ms"] is None for row in samples
                ),
                "no_delta": sum(
                    row["outcome"] == "stalled"
                    and row["accepted_ms"] is not None
                    and row["first_response_ms"] is None
                    for row in samples
                ),
                "latency": {
                    stage: {
                        str(int(q * 100)): round(percentile(values, q) or 0, 1)
                        for q in (0.5, 0.95, 0.99)
                    }
                    for stage in stages
                    if (values := [row[stage] for row in samples if row[stage] is not None])
                },
                "steps_avg": _average(samples, "step_count"),
                "tools_avg": _average(samples, "tool_calls"),
                "tool_success_rate": _ratio(
                    sum(row["tool_successes"] or 0 for row in samples),
                    sum(row["tool_calls"] or 0 for row in samples),
                ),
                "tool_ms_avg": _average(samples, "tool_ms"),
            }
        )
    return {
        "window_hours": round((time.time() - since) / 3600, 2),
        "channels": channels,
        "recent": [
            {
                key: row[key]
                for key in (
                    "user_id",
                    "user_name",
                    "message_id",
                    "channel",
                    "client_id",
                    "device_id",
                    "trace_id",
                    "sent_at",
                    "accepted_ms",
                    "first_response_ms",
                    "first_renderable_ms",
                    "first_paint_ms",
                    "completed_ms",
                    "outcome",
                    "step_count",
                    "model_calls",
                    "tool_calls",
                    "tool_successes",
                    "tool_ms",
                    "received_at",
                )
            }
            for row in rows[:80]
        ],
    }


def _average(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row[key] is not None]
    return round(sum(values) / len(values), 2) if values else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


__all__ = [
    "CHANNELS",
    "OUTCOMES",
    "percentile",
    "record",
    "summary",
    "trace_stats",
]
