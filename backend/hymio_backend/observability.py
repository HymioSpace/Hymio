"""Product telemetry metrics and bounded Prometheus queries."""

import math
import re
import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    ProcessCollector,
    generate_latest,
)

REGISTRY = CollectorRegistry()
ProcessCollector(registry=REGISTRY)
CLIENT_STAGE = Histogram(
    "hymio_client_turn_seconds",
    "Client-observed turn latency by channel and stage.",
    ("channel", "stage"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60, 120, 300),
    registry=REGISTRY,
)
CLIENT_OUTCOMES = Counter(
    "hymio_client_turns_total",
    "Client turns by channel and outcome.",
    ("channel", "outcome"),
    registry=REGISTRY,
)
CLIENT_STEPS = Histogram(
    "hymio_trace_steps",
    "Steps in a completed client turn trace.",
    ("channel",),
    buckets=(1, 2, 3, 5, 8, 13, 21, 34),
    registry=REGISTRY,
)
CLIENT_TOOLS = Histogram(
    "hymio_trace_tools",
    "Tool calls in a completed client turn trace.",
    ("channel",),
    buckets=(0, 1, 2, 3, 5, 8, 13, 21, 34),
    registry=REGISTRY,
)
HTTP_REQUESTS = Counter(
    "hymio_http_requests_total",
    "Completed HTTP requests by method, route and exact status.",
    ("method", "route", "status"),
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "hymio_http_request_duration_seconds",
    "HTTP request latency from ASGI receive to final response body chunk.",
    ("method", "route"),
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2,
        3,
        5,
        8,
        13,
        21,
        34,
        60,
    ),
    registry=REGISTRY,
)

_ID_SEGMENTS = (
    (re.compile(r"^/attachments/[^/]+$"), "/attachments/{attachment_id}"),
    (re.compile(r"^/devices/media/[^/]+$"), "/devices/media/{media_id}"),
    (re.compile(r"^/agent/traces/[^/]+$"), "/agent/traces/{trace_id}"),
    (
        re.compile(r"^/admin/api/resources/devices/[^/]+$"),
        "/admin/api/resources/devices/{device_id}",
    ),
)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def http_route(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    fallback = str(scope.get("path", "unmatched"))
    for name, value in (scope.get("path_params") or {}).items():
        if value:
            fallback = fallback.replace(f"/{value}", f"/{{{name}}}", 1)
    for pattern, label in _ID_SEGMENTS:
        if pattern.match(fallback):
            return label
    return fallback[:160]


class HTTPMetricsMiddleware:
    """Measure every completed HTTP response, including streamed bodies.

    ``BaseHTTPMiddleware`` returns before a streaming response body is fully sent.
    Wrapping ASGI ``send`` keeps download and export latency in the same metric.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        status = 500

        async def measured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, measured_send)
        except Exception:
            status = 500
            raise
        finally:
            method = str(scope.get("method", "GET"))
            route = http_route(scope)
            HTTP_REQUESTS.labels(method, route, str(status)).inc()
            HTTP_DURATION.labels(method, route).observe(time.monotonic() - started)


def observe_turn(sample: dict[str, Any]) -> None:
    channel = str(sample.get("channel", "unknown"))
    outcome = str(sample.get("outcome", "unknown"))
    CLIENT_OUTCOMES.labels(channel, outcome).inc()
    for key, stage in (
        ("accepted_ms", "accepted"),
        ("first_response_ms", "first_response"),
        ("first_renderable_ms", "first_renderable"),
        ("first_paint_ms", "first_paint"),
        ("completed_ms", "completed"),
    ):
        value = sample.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            CLIENT_STAGE.labels(channel, stage).observe(value / 1000)
    steps = sample.get("step_count")
    if isinstance(steps, int) and steps >= 0:
        CLIENT_STEPS.labels(channel).observe(steps)
    tools = sample.get("tool_calls")
    if isinstance(tools, int) and tools >= 0:
        CLIENT_TOOLS.labels(channel).observe(tools)
