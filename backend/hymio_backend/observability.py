"""Product telemetry metrics and bounded Prometheus queries."""

import math
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


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


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
