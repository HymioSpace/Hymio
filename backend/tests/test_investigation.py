import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.event_log import EventLog
from hymio_backend.investigation import trace_triggers, trigger
from hymio_backend.monitoring import SERIES, monitoring_routes


class InvestigationTests(unittest.TestCase):
    def test_one_failed_metric_does_not_hide_other_metrics(self):
        async def instant(settings, upstream, query):
            if query == SERIES["http_avg"]:
                raise TimeoutError()
            return [{"metric": {}, "value": [0, "1"]}]

        settings = SimpleNamespace(admin_user_ids=("u",), grafana_url="")
        sessions = SimpleNamespace(
            verify=lambda token: {"user_id": "u"},
            event_log=SimpleNamespace(annotate=lambda rows: rows),
        )
        app = Starlette(
            routes=monitoring_routes(settings, sessions, None, lambda request: "test", None)
        )
        with (
            patch("hymio_backend.monitoring.client_telemetry.summary", return_value={"recent": []}),
            patch("hymio_backend.monitoring._instant", side_effect=instant),
            patch(
                "hymio_backend.monitoring._alerts",
                new=AsyncMock(return_value={"active": [], "rule_errors": []}),
            ),
        ):
            data = TestClient(app).get("/admin/api/monitoring/overview").json()
        self.assertTrue(data["prometheus"]["available"])
        self.assertEqual(data["prometheus"]["errors"], ["http_avg"])
        self.assertEqual(data["prometheus"]["metrics"]["services_up"][0]["value"], "1")

    def test_trigger_reads_input_not_model_request(self):
        body = {
            "kind": "system",
            "source": "app.task.due",
            "payload": {"content": "检查今天的安排"},
        }
        item = trigger("oath.input.system", {"body": json.dumps(body)})
        self.assertEqual(item["kind"], "system")
        self.assertEqual(item["source"], "app.task.due")
        self.assertEqual(item["text"], "检查今天的安排")
        self.assertIsNone(trigger("gen_ai.client.inference.operation.details", body))

    def test_summary_and_recent_events_remain_user_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            log = EventLog(Path(folder) / "events.sqlite3")
            log.append(
                "a", "same", "gateway.received", {"content": "请帮我安排旅行"}, trace_id="ta"
            )
            log.append(
                "b", "same", "gateway.received", {"content": "另一位用户的内容"}, trace_id="tb"
            )
            turns = [{"user_id": "a", "message_id": "same", "trace_id": "ta"}]
            log.annotate(turns)
            self.assertEqual(turns[0]["trigger"]["text"], "请帮我安排旅行")
            self.assertEqual(len(log.search("", since=0)), 2)

    def test_trace_input_dedup_does_not_lose_different_wake_events(self):
        event = {
            "name": "oath.input.user",
            "attributes": {"body": json.dumps({"payload": {"content": "你好"}})},
        }
        system = {
            "name": "oath.input.tool",
            "attributes": {"body": {"source": "tool.terminal", "payload": {"content": "已经完成"}}},
        }
        values = trace_triggers({"spans": [{"events": [event]}, {"events": [event, system]}]})
        self.assertEqual([value["kind"] for value in values], ["user", "tool"])
