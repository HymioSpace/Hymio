"""Administrator observability API, client ingestion and Prometheus bridge."""

import asyncio
import time
from typing import Any

from starlette.responses import JSONResponse
from starlette.routing import Route

from . import client_telemetry
from .observability import observe_turn
from .session_store import Unauthorized

SERIES: dict[str, str] = {
    "host_memory_used": "1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes",
    "host_iowait": 'avg(rate(node_cpu_seconds_total{mode="iowait"}[5m]))',
    "process_memory": 'process_resident_memory_bytes{job=~"oath|hymio"}',
    "storage_bytes": "oath_storage_bytes",
    "storage_lock_p95": ("histogram_quantile(0.95,sum by (le,mode) "
                         "(rate(oath_storage_lock_wait_seconds_bucket[5m])))"),
    "storage_busy": 'sum(rate(oath_storage_transaction_seconds_count{outcome="busy"}[5m]))',
    "rpc_p95": (
        "histogram_quantile(0.95, sum by (service, le) (oath_rpc_duration_seconds_bucket))"
    ),
    "queue_publish_p95": (
        "histogram_quantile(0.95, sum by (le) (oath_queue_publish_delay_seconds_bucket))"
    ),
    "queue_buffer_p95": (
        "histogram_quantile(0.95, sum by (le) (oath_queue_to_buffer_seconds_bucket))"
    ),
    "wake_wait_p95": (
        "histogram_quantile(0.95, sum by (le) (oath_buffer_wake_delay_seconds_bucket))"
    ),
    "brain_claim_p95": (
        "histogram_quantile(0.95, sum by (le) (oath_brain_claim_wait_seconds_bucket))"
    ),
    "llm_ttft_p95": ("histogram_quantile(0.95, sum by (model, le) (oath_llm_ttft_seconds_bucket))"),
    "llm_duration_p95": (
        "histogram_quantile(0.95, sum by (model, le) (oath_llm_duration_seconds_bucket))"
    ),
    "tool_duration_p95": (
        "histogram_quantile(0.95, sum by (tool, le) (oath_tool_duration_seconds_bucket))"
    ),
    "tool_success_rate": (
        'sum by (tool) (rate(oath_tool_terminals_total{outcome="succeeded"}[5m])) '
        "/ clamp_min(sum by (tool) (rate(oath_tool_terminals_total[5m])), 0.000001)"
    ),
    "delivery_p95": (
        "histogram_quantile(0.95, sum by (type, le) (oath_delivery_delay_seconds_bucket))"
    ),
    "gateway_rate": "sum by (type, channel, status) (rate(oath_gateway_commands_total[5m]))",
    "rpc_rate": "sum(rate(oath_rpc_requests_total[5m]))",
    "rpc_error_rate": (
        'sum(rate(oath_rpc_requests_total{status=~"5..|413"}[5m])) '
        "/ clamp_min(sum(rate(oath_rpc_requests_total[5m])), 0.000001)"
    ),
    "tool_terminal_rate": "sum(rate(oath_tool_terminals_total[10m]))",
    "rabbit_ready": "sum by (queue) (rabbitmq_queue_messages_ready)",
    "services_up": 'sum(up{job="oath"})',
}


def _admin(settings, sessions, bearer, request):
    identity = sessions.verify(bearer(request))
    return identity["user_id"] in settings.admin_user_ids


async def record_client_turn(settings, sessions, upstream, request, bearer, body):
    identity = sessions.verify(bearer(request))
    data = await body(request)
    sample = await asyncio.to_thread(
        client_telemetry.record, sessions, identity["user_id"], data, None
    )
    inserted = await asyncio.to_thread(
        sessions.event_log.append,
        identity["user_id"],
        sample["message_id"],
        (
            data["stage"][:64]
            if isinstance(data.get("stage"), str) and data["stage"]
            else "client." + data["outcome"]
        ),
        data,
        trace_id=sample["trace_id"],
        channel=sample["channel"],
    )
    if inserted and data["outcome"] in {"completed", "failed", "cancelled", "partial", "stalled"}:
        observe_turn(sample)
    return JSONResponse({"recorded": True})


async def _prometheus_get(settings, upstream, path: str, params: dict[str, Any]):
    response = await upstream.get(
        settings.prometheus_url.rstrip("/") + path,
        params=params,
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


async def _range(settings, upstream, query: str, *, hours: int):
    end = time.time()
    step = max(15, int(hours * 3600 / 180))
    result = await _prometheus_get(
        settings,
        upstream,
        "/api/v1/query_range",
        {"query": query, "start": end - hours * 3600, "end": end, "step": step},
    )
    return result.get("data", {}).get("result", [])


async def _instant(settings, upstream, query: str):
    result = await _prometheus_get(settings, upstream, "/api/v1/query", {"query": query})
    return result.get("data", {}).get("result", [])


async def _alerts(settings, upstream) -> dict[str, Any]:
    result = await _prometheus_get(settings, upstream, "/api/v1/rules", {"type": "alert"})
    alerts = []
    unhealthy = []
    for group in result.get("data", {}).get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("health") not in (None, "ok"):
                unhealthy.append(
                    {
                        "name": rule.get("name", ""),
                        "health": rule.get("health"),
                        "group": group.get("name", ""),
                    }
                )
            if rule.get("state") not in ("firing", "pending"):
                continue
            first_alert = (rule.get("alerts") or [{}])[0]
            labels = first_alert.get("labels") or {}
            summary = (rule.get("annotations") or {}).get("summary", "")
            for key, value in labels.items():
                summary = summary.replace("{{ $labels." + key + " }}", str(value))
                summary = summary.replace("{{$labels." + key + "}}", str(value))
            alerts.append(
                {
                    "name": rule.get("name", ""),
                    "state": rule.get("state"),
                    "severity": (rule.get("labels") or {}).get("severity", "warning"),
                    "summary": summary,
                    "active_at": (rule.get("activeAt") or ""),
                    "value": str(first_alert.get("value", "")),
                }
            )
    return {"active": alerts, "rule_errors": unhealthy}


def monitoring_routes(settings, sessions, upstream, bearer, body):
    async def endpoint(request):
        try:
            if not _admin(settings, sessions, bearer, request):
                raise Unauthorized()
            path = request.url.path
            if path == "/admin/api/monitoring/overview":
                hours = min(168, max(1, int(request.query_params.get("hours", 24))))
                channel = request.query_params.get("channel", "")
                if channel and channel not in client_telemetry.CHANNELS:
                    raise ValueError("invalid_channel")
                client = client_telemetry.summary(
                    sessions, since=time.time() - hours * 3600, channel=channel
                )
                try:
                    values = await asyncio.gather(
                        *(_instant(settings, upstream, query) for query in SERIES.values()),
                        _alerts(settings, upstream),
                    )
                    alert_state = values.pop()
                    prometheus = {
                        "available": True,
                        **alert_state,
                        "metrics": {
                            name: [
                                {
                                    "labels": item.get("metric", {}),
                                    "value": item.get("value", [None, "0"])[1],
                                }
                                for item in result
                            ]
                            for name, result in zip(SERIES, values, strict=True)
                        },
                    }
                except Exception:
                    prometheus = {"available": False, "metrics": {}}
                return JSONResponse(
                    {
                        "client": client,
                        "prometheus": prometheus,
                        "grafana_url": settings.grafana_url,
                    }
                )
            if path == "/admin/api/monitoring/series":
                name = request.query_params.get("name", "")
                if name not in SERIES:
                    raise ValueError("invalid_metric")
                hours = min(168, max(1, int(request.query_params.get("hours", 6))))
                try:
                    series = await _range(settings, upstream, SERIES[name], hours=hours)
                    available = True
                except Exception:
                    series = []
                    available = False
                return JSONResponse(
                    {"name": name, "available": available, "hours": hours, "series": series}
                )
            if path == "/admin/api/monitoring/search":
                query = request.query_params.get("q", "").strip()[:128]
                if not query:
                    raise ValueError("query_required")
                hours = min(168, max(1, int(request.query_params.get("hours", 24))))
                channel = request.query_params.get("channel", "")
                if channel and channel not in client_telemetry.CHANNELS:
                    raise ValueError("invalid_channel")
                rows = await asyncio.to_thread(
                    sessions.event_log.search,
                    query,
                    since=time.time() - hours * 3600,
                    channel=channel,
                )
                indexed = await asyncio.to_thread(
                    sessions.event_log.indexed_messages,
                    since=time.time() - hours * 3600,
                    channel=channel,
                )
                traces = []
                grouped = {}
                with sessions.transaction() as db:
                    for row in rows:
                        key = (row["user_id"], row["trace_id"] or "message:" + row["message_id"])
                        if key not in grouped:
                            stored = db.execute(
                                "SELECT ct.*,u.name AS user_name FROM client_turns ct "
                                "LEFT JOIN users u ON u.user_id=ct.user_id "
                                "WHERE ct.user_id=? AND ct.message_id=?",
                                (row["user_id"], row["message_id"]),
                            ).fetchone()
                            turn = (
                                dict(stored)
                                if stored
                                else {
                                    "user_id": row["user_id"],
                                    "user_name": "",
                                    "message_id": row["message_id"],
                                    "channel": row["channel"],
                                    "sent_at": row["occurred_at"] * 1000,
                                    "received_at": row["occurred_at"],
                                    "outcome": "in_progress",
                                }
                            )
                            turn.update(trace_id=key[1], matches=[], match_count=0, matched_spans=1)
                            grouped[key] = turn
                            traces.append(turn)
                        turn = grouped[key]
                        turn["match_count"] += 1
                        turn["matches"].append(
                            {
                                "span_id": "message",
                                "span_name": "message.lifecycle",
                                "event_name": row["stage"],
                                "unix_nano": int(row["occurred_at"] * 1e9),
                                "snippet": row["snippet"] or row["body"][:180],
                            }
                        )
                return JSONResponse(
                    {
                        "query": query,
                        "hours": hours,
                        "channel": channel,
                        "scanned": indexed,
                        "failed": 0,
                        "matched": len(traces),
                        "traces": traces,
                    }
                )
            if path == "/admin/api/monitoring/trace":
                user_id = request.query_params.get("user_id", "")
                trace_id = request.query_params.get("trace_id", "")
                if not user_id or not trace_id:
                    raise ValueError("trace_required")
                if trace_id.startswith("message:"):
                    spans = await asyncio.to_thread(
                        sessions.event_log.detail, user_id, message_id=trace_id[8:]
                    )
                    return JSONResponse({"trace_id": trace_id, "duration_ms": None, "spans": spans})
                lifecycle = await asyncio.to_thread(
                    sessions.event_log.detail, user_id, trace_id=trace_id
                )
                try:
                    token_file = settings.oath_admin_token_file
                    if token_file is None:
                        raise ValueError("oath_admin_token_not_configured")
                    response = await upstream.get(
                        settings.oath_biz.rstrip("/") + "/admin/trace",
                        params={"user_id": user_id, "trace_id": trace_id},
                        headers={"Authorization": "Bearer " + token_file.read_text().strip()},
                        timeout=5,
                    )
                    response.raise_for_status()
                    detail = response.json()
                    detail["spans"] = lifecycle + detail.get("spans", [])
                    return JSONResponse(detail)
                except Exception:
                    return JSONResponse(
                        {
                            "trace_id": trace_id,
                            "duration_ms": None,
                            "spans": lifecycle,
                            "upstream_available": False,
                        }
                    )
            return JSONResponse({"error": "not_found"}, 404)
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "invalid_monitoring_request"}, 400)
        except Exception:
            return JSONResponse({"error": "monitoring_unavailable"}, 503)

    return [
        Route("/admin/api/monitoring/overview", endpoint),
        Route("/admin/api/monitoring/series", endpoint),
        Route("/admin/api/monitoring/search", endpoint),
        Route("/admin/api/monitoring/trace", endpoint),
    ]


__all__ = ["SERIES", "monitoring_routes", "record_client_turn"]
