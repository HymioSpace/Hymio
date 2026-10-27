import asyncio
import unittest

from hymio_backend.tool_monitoring import collection_health, rows_from_metrics


class ToolMonitoringTests(unittest.TestCase):
    def test_tool_rows_keep_outcomes_separate_from_latency_samples(self):
        rows = rows_from_metrics(
            {
                "outcomes": [
                    {"metric": {"tool": "search", "outcome": "succeeded"}, "value": [0, "9"]},
                    {"metric": {"tool": "search", "outcome": "timeout"}, "value": [0, "1"]},
                ],
                "samples": [{"metric": {"tool": "search"}, "value": [0, "7"]}],
                "average": [{"metric": {"tool": "search"}, "value": [0, "0.25"]}],
                "p50": [{"metric": {"tool": "search"}, "value": [0, "0.2"]}],
                "p95": [{"metric": {"tool": "search"}, "value": [0, "0.8"]}],
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total"], 10)
        self.assertEqual(rows[0]["success_rate"], 0.9)
        self.assertEqual(rows[0]["samples"], 7)

    def test_zero_latency_samples_do_not_claim_zero_duration(self):
        rows = rows_from_metrics(
            {
                "outcomes": [
                    {"metric": {"tool": "approval", "outcome": "cancelled"}, "value": [0, "1"]}
                ],
                "samples": [],
                "average": [{"metric": {"tool": "approval"}, "value": [0, "0"]}],
            }
        )

        self.assertEqual(rows[0]["total"], 1)
        self.assertEqual(rows[0]["success_rate"], 0)
        self.assertIsNone(rows[0]["average"])

    def test_collection_health_uses_current_targets_not_stale_up_series(self):
        async def missing(settings, upstream):
            return {"activeTargets": []}

        async def down(settings, upstream):
            return {
                "activeTargets": [
                    {
                        "labels": {"job": "oath", "instance": "tools:8773"},
                        "health": "down",
                        "lastError": "connection refused",
                    }
                ]
            }

        missing_state = asyncio.run(collection_health(None, None, "oath", missing))
        down_state = asyncio.run(collection_health(None, None, "oath", down))

        self.assertEqual(missing_state["status"], "missing")
        self.assertEqual(down_state["status"], "down")
        self.assertEqual(down_state["targets"][0]["instance"], "tools:8773")
        self.assertEqual(down_state["targets"][0]["last_error"], "connection refused")


if __name__ == "__main__":
    unittest.main()
