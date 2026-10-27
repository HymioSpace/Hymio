import assert from "node:assert/strict";
import test from "node:test";
import { sortTools, toolTotals, type ToolRow } from "../src/tool-model.ts";

const rows: ToolRow[] = [
  {
    tool: "search",
    total: 90,
    outcomes: { succeeded: 90 },
    success_rate: 1,
    average: 0.2,
    p95: 0.5,
    samples: 80,
  },
  {
    tool: "browser",
    total: 10,
    outcomes: { succeeded: 5, failed: 5 },
    success_rate: 0.5,
    average: 2,
    p95: 4,
    samples: 10,
  },
];

test("totals weight average execution time by measured samples", () => {
  const totals = toolTotals(rows);
  assert.equal(totals.total, 100);
  assert.equal(totals.unsuccessful, 5);
  assert.equal(totals.successRate, 0.95);
  assert.equal(totals.average, 0.4);
});

test("empty data has no implied success rate or latency", () => {
  const totals = toolTotals([]);
  assert.equal(totals.total, 0);
  assert.equal(totals.successRate, null);
  assert.equal(totals.average, null);
});

test("sorting leaves unavailable rates and latencies at the bottom", () => {
  const unavailable: ToolRow = {
    tool: "idle",
    total: 0,
    outcomes: {},
    success_rate: null,
    p95: null,
  };
  assert.equal(sortTools([...rows, unavailable], "reliability")[0].tool, "browser");
  assert.equal(sortTools([...rows, unavailable], "latency")[0].tool, "browser");
});
