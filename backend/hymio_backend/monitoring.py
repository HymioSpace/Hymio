"""Administrator observability API, client ingestion and Prometheus bridge."""

import asyncio
import time
from typing import Any

from starlette.responses import JSONResponse
from starlette.routing import Route

from . import client_telemetry, compression, tool_monitoring
from .investigation import trace_triggers
from .observability import observe_turn
from .session_store import Unauthorized


def _p95(metric, group=""):
    labels = "le" + (", " + group if group else "")
    return f"histogram_quantile(0.95, sum by ({labels}) (rate({metric}_bucket[5m])))"


SERIES: dict[str, str] = {
    "host_memory_used": "1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes",
    "host_iowait": 'avg(rate(node_cpu_seconds_total{mode="iowait"}[5m]))',
    "process_memory": 'process_resident_memory_bytes{job=~"oath|hymio"}',
    "storage_bytes": "oath_storage_bytes",
    "storage_lock_p95": (
        "histogram_quantile(0.95,sum by (le,mode) "
        "(rate(oath_storage_lock_wait_seconds_bucket[5m])))"
    ),
    "storage_busy": 'sum(rate(oath_storage_transaction_seconds_count{outcome="busy"}[5m]))',
    "rpc_p95": _p95("oath_rpc_duration_seconds", "service"),
    "queue_publish_p95": _p95("oath_queue_publish_delay_seconds"),
    "queue_buffer_p95": _p95("oath_queue_to_buffer_seconds"),
    "wake_wait_p95": _p95("oath_buffer_wake_delay_seconds"),
    "brain_claim_p95": _p95("oath_brain_claim_wait_seconds"),
    "llm_ttft_p95": _p95("oath_llm_ttft_seconds", "model"),
    "llm_duration_p95": _p95("oath_llm_duration_seconds", "model"),
    "tool_duration_p95": _p95("oath_tool_duration_seconds", "tool"),
    "tool_success_rate": (
        'sum by (tool) (rate(oath_tool_terminals_total{outcome="succeeded"}[5m])) '
        "/ clamp_min(sum by (tool) (rate(oath_tool_terminals_total[5m])), 0.000001)"
    ),
    "delivery_p95": _p95("oath_delivery_delay_seconds", "type"),
    "gateway_rate": "sum by (type, channel, status) (rate(oath_gateway_commands_total[5m]))",
    "rpc_rate": "sum(rate(oath_rpc_requests_total[5m]))",
    "rpc_error_rate": (
        'sum(rate(oath_rpc_requests_total{status=~"5..|413"}[5m])) '
        "/ clamp_min(sum(rate(oath_rpc_requests_total[5m])), 0.000001)"
    ),
    "tool_terminal_rate": "sum(rate(oath_tool_terminals_total[10m]))",
    "rabbit_ready": "sum by (queue) (rabbitmq_queue_messages_ready)",
    "services_up": 'sum(up{job="oath"})',
    "http_request_rate": (
        'sum by (method, route) (rate(hymio_http_requests_total{route!="/metrics"}[5m]))'
    ),
    "http_success_rate": (
        "(sum by (method, route) "
        '(rate(hymio_http_requests_total{route!="/metrics",status=~"2.."}[5m])) '
        "/ clamp_min(sum by (method, route) "
        '(rate(hymio_http_requests_total{route!="/metrics"}[5m])), 0.000001)) '
        "or (0 * sum by (method, route) "
        '(rate(hymio_http_requests_total{route!="/metrics"}[5m])))'
    ),
    "http_avg": (
        "sum by (method, route) (rate(hymio_http_request_duration_seconds_sum[5m])) "
        "/ clamp_min(sum by (method, route) "
        "(rate(hymio_http_request_duration_seconds_count[5m])), 0.000001)"
    ),
    "http_p50": (
        "histogram_quantile(0.50, sum by (method, route, le) "
        "(rate(hymio_http_request_duration_seconds_bucket[5m])))"
    ),
    "http_p90": (
        "histogram_quantile(0.90, sum by (method, route, le) "
        "(rate(hymio_http_request_duration_seconds_bucket[5m])))"
    ),
    "http_p95": (
        "histogram_quantile(0.95, sum by (method, route, le) "
        "(rate(hymio_http_request_duration_seconds_bucket[5m])))"
    ),
    "compaction_attempt_rate": (
        "sum by (mode, outcome) (rate(oath_compaction_attempts_total[5m]))"
    ),
    "compaction_duration_p95": (
        "histogram_quantile(0.95, sum by (le, mode, outcome) "
        "(rate(oath_compaction_duration_seconds_bucket[5m])))"
    ),
    "compaction_lease_wait_p95": (
        "histogram_quantile(0.95, sum by (le, mode) "
        "(rate(oath_compaction_lease_wait_seconds_bucket[5m])))"
    ),
    "compaction_blocked_rate": ("sum by (mode) (rate(oath_compaction_blocked_steps_total[5m]))"),
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


async def _targets(settings, upstream):
    result = await _prometheus_get(settings, upstream, "/api/v1/targets", {})
    return result.get("data", {})


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


async def _compaction_events(settings, upstream, hours: int) -> list[dict[str, Any]] | None:
    try:
        token_file = settings.oath_admin_token_file
        if token_file is None:
            return None
        response = await upstream.get(
            settings.oath_biz.rstrip("/") + "/admin/compactions",
            params={"hours": hours},
            headers={"Authorization": "Bearer " + token_file.read_text().strip()},
            timeout=5,
        )
        response.raise_for_status()
        events = response.json().get("events")
        return events if isinstance(events, list) else None
    except Exception:
        return None


def monitoring_routes(settings, sessions, upstream, bearer, body):
    async def endpoint(request):
        try:
            if not _admin(settings, sessions, bearer, request):
                raise Unauthorized()
            path = request.url.path
            if path == "/admin/api/monitoring/prompt":
                channel = request.query_params.get("channel", "web")
                if channel not in {"web", "ios", "desk", "chrome", "unknown"}:
                    raise ValueError("invalid_channel")
                if settings.oath_admin_token_file is None:
                    return JSONResponse({"error": "oath_admin_token_not_configured"}, 503)
                response = await upstream.get(
                    settings.oath_biz.rstrip("/") + "/admin/system-prompt",
                    params={"channel": channel},
                    headers={
                        "Authorization": "Bearer "
                        + settings.oath_admin_token_file.read_text().strip()
                    },
                    timeout=10,
                )
                response.raise_for_status()
                return JSONResponse(response.json())
            if path == "/admin/api/monitoring/tools":
                hours = min(168, max(1, int(request.query_params.get("hours", 24))))
                return JSONResponse(
                    await tool_monitoring.report(settings, upstream, hours, _instant, _targets)
                )
            if path == "/admin/api/monitoring/overview":
                hours = min(168, max(1, int(request.query_params.get("hours", 24))))
                channel = request.query_params.get("channel", "")
                if channel and channel not in client_telemetry.CHANNELS:
                    raise ValueError("invalid_channel")
                client = client_telemetry.summary(
                    sessions, since=time.time() - hours * 3600, channel=channel
                )
                remote_events = await _compaction_events(settings, upstream, hours)
                try:
                    compaction = compression.summary(
                        sessions,
                        since=time.time() - hours * 3600,
                        events=remote_events,
                    )
                except Exception:
                    compaction = compression.empty(window_hours=hours)
                await asyncio.to_thread(sessions.event_log.annotate, client["recent"])
                try:
                    values = await asyncio.gather(
                        *(_instant(settings, upstream, query) for query in SERIES.values()),
                        _alerts(settings, upstream),
                        return_exceptions=True,
                    )
                    alert_state = values.pop()
                    failures = [
                        name
                        for name, value in zip(SERIES, values, strict=True)
                        if isinstance(value, Exception)
                    ]
                    prometheus = {
                        "available": len(failures) < len(SERIES),
                        "errors": failures,
                        **(
                            alert_state
                            if isinstance(alert_state, dict)
                            else {"active": [], "rule_errors": []}
                        ),
                        "metrics": {
                            name: [
                                {
                                    "labels": item.get("metric", {}),
                                    "value": item.get("value", [None, "0"])[1],
                                }
                                for item in (result if isinstance(result, list) else [])
                            ]
                            for name, result in zip(SERIES, values, strict=True)
                        },
                    }
                except Exception:
                    prometheus = {"available": False, "metrics": {}}
                return JSONResponse(
                    {
                        "client": client,
                        "compaction": compaction,
                        "prometheus": prometheus,
                        "grafana_url": settings.grafana_url,
                        "http_collection": await tool_monitoring.collection_health(
                            settings, upstream, "hymio", _targets
                        ),
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
                source = request.query_params.get("source", "application")
                if source not in {"application", "otel", "log", "all"}:
                    raise ValueError("invalid_source")
                hours = min(168, max(1, int(request.query_params.get("hours", 24))))
                channel = request.query_params.get("channel", "")
                if channel and channel not in client_telemetry.CHANNELS:
                    raise ValueError("invalid_channel")
                if source == "log":
                    logs = await asyncio.to_thread(
                        sessions.event_log.search_logs,
                        query,
                        since=time.time() - hours * 3600,
                        channel=channel,
                        level=request.query_params.get("level", ""),
                    )
                    return JSONResponse(
                        {
                            "query": query,
                            "hours": hours,
                            "channel": channel,
                            "source": source,
                            "scanned": len(logs),
                            "failed": 0,
                            "matched": len(logs),
                            "traces": [],
                            "logs": logs,
                        }
                    )
                rows = await asyncio.to_thread(
                    sessions.event_log.search,
                    query,
                    since=time.time() - hours * 3600,
                    channel=channel,
                    source="" if source == "all" else source,
                )
                indexed = await asyncio.to_thread(
                    sessions.event_log.indexed_messages,
                    since=time.time() - hours * 3600,
                    channel=channel,
                    source="" if source == "all" else source,
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
                                "source": row["source"],
                            }
                        )
                await asyncio.to_thread(sessions.event_log.annotate, traces)
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
                        sessions.event_log.detail,
                        user_id,
                        message_id=trace_id[8:],
                        source="application",
                    )
                    return JSONResponse({"trace_id": trace_id, "duration_ms": None, "spans": spans})
                lifecycle = await asyncio.to_thread(
                    sessions.event_log.detail,
                    user_id,
                    trace_id=trace_id,
                    source="application",
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
                    detail["triggers"] = trace_triggers(detail)
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
        Route("/admin/api/monitoring/tools", endpoint),
        Route("/admin/api/monitoring/prompt", endpoint),
        Route("/admin/api/monitoring/series", endpoint),
        Route("/admin/api/monitoring/search", endpoint),
        Route("/admin/api/monitoring/trace", endpoint),
    ]


__all__ = ["SERIES", "monitoring_routes", "record_client_turn"]
