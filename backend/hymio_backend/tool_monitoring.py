"""Bounded operator metrics; execution data remains owned by Oath."""

import asyncio
import math


def queries(hours):
    window = f"{hours}h"
    count = f"sum by (tool) (increase(oath_tool_duration_seconds_count[{window}]))"
    buckets = f"sum by (tool,le) (increase(oath_tool_duration_seconds_bucket[{window}]))"
    return {
        "outcomes": f"sum by (tool,outcome) (increase(oath_tool_terminals_total[{window}]))",
        "samples": count,
        "average": (
            f"sum by (tool) (increase(oath_tool_duration_seconds_sum[{window}])) / ({count} > 0)"
        ),
        "p50": f"histogram_quantile(0.5,{buckets})",
        "p95": f"histogram_quantile(0.95,{buckets})",
        "observed": "sum by (tool) (oath_tool_terminals_total)",
    }


def rows_from_metrics(metrics):
    rows = {}
    for name, samples in metrics.items():
        for sample in samples:
            tool = sample.get("metric", {}).get("tool")
            try:
                value = float(sample["value"][1])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            if not tool or not math.isfinite(value) or value < 0:
                continue
            row = rows.setdefault(tool, {"tool": tool, "outcomes": {}})
            if name == "outcomes":
                row["outcomes"][sample["metric"].get("outcome", "unknown")] = value
            else:
                row[name] = value
    for row in rows.values():
        row["total"] = sum(row["outcomes"].values())
        row["success_rate"] = (
            row["outcomes"].get("succeeded", 0) / row["total"] if row["total"] > 0 else None
        )
        if row.get("samples", 0) <= 0:
            for name in ("average", "p50", "p95"):
                row[name] = None
    return sorted(rows.values(), key=lambda r: (-r["total"], r["tool"]))


async def collection_health(settings, upstream, job, targets):
    try:
        data = await targets(settings, upstream)
    except Exception:
        return {"status": "unavailable", "targets": []}
    matches = [
        {
            "instance": item.get("labels", {}).get("instance", ""),
            "scrape_url": item.get("scrapeUrl", ""),
            "last_error": item.get("lastError", ""),
            "up": item.get("health") == "up",
        }
        for item in data.get("activeTargets", [])
        if item.get("labels", {}).get("job") == job
    ]
    return {
        "status": (
            "missing"
            if not matches
            else "ready"
            if all(t["up"] for t in matches)
            else "down"
        ),
        "targets": matches,
    }


async def report(settings, upstream, hours, instant, targets):
    definitions = queries(hours)
    results = await asyncio.gather(
        *(instant(settings, upstream, q) for q in definitions.values()),
        collection_health(settings, upstream, "oath", targets),
        return_exceptions=True,
    )
    health = results.pop()
    # Oath has many services; Tools collection is the relevant target here.
    if isinstance(health, dict):
        health["targets"] = [t for t in health["targets"] if t["instance"].split(":")[0] == "tools"]
        health["status"] = (
            "ready" if health["targets"] and all(t["up"] for t in health["targets"])
            else "unavailable" if health["status"] == "unavailable"
            else "down" if health["targets"] else "missing"
        )
    metrics = {k: v for k, v in zip(definitions, results) if not isinstance(v, Exception)}
    return {
        "hours": hours,
        "estimated": True,
        "collection": health,
        "errors": [k for k, v in zip(definitions, results) if isinstance(v, Exception)],
        "tools": rows_from_metrics(metrics),
    }
