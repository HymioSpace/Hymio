import logging
import tempfile
import unittest
from pathlib import Path

from hymio_backend.event_log import EventLog
from hymio_backend.system_log import EventLogHandler, LogCapture


class EventLogTests(unittest.TestCase):
    def test_user_message_is_searchable_before_trace_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "observability.sqlite3")
            log.append(
                "user-1",
                "message-1",
                "client.sent",
                {
                    "payload": {
                        "content": "你好呀",
                        "user_context": {"channel": "web"},
                    }
                },
                channel="web",
            )

            rows = log.search("你好呀", since=0, channel="web")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["message_id"], "message-1")
            self.assertIn("你好呀", rows[0]["snippet"])

    def test_duplicate_lifecycle_event_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "observability.sqlite3")
            for _ in range(2):
                log.append(
                    "user-1",
                    "message-1",
                    "client.sent",
                    {"content": "只回复 OK"},
                    channel="web",
                )

            rows = log.search("OK", since=0)

            self.assertEqual(len(rows), 1)
            self.assertEqual(log.indexed_messages(since=0), 1)

    def test_log_search_excludes_otel_span_events(self):
        with tempfile.TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "observability.sqlite3")
            log.append(
                "user-1",
                "message-1",
                "gateway.received",
                {"content": "trace needle"},
                channel="web",
            )
            log.append(
                "user-1",
                "message-1",
                "chat MiniMax",
                {"attributes": {"body": {"content": "trace needle"}}},
                channel="web",
                source="otel",
            )

            logs = log.search("trace needle", since=0, source="application")
            spans = log.search("trace needle", since=0, source="otel")

            self.assertEqual([row["stage"] for row in logs], ["gateway.received"])
            self.assertEqual([row["stage"] for row in spans], ["chat MiniMax"])

    def test_ack_body_repairs_missing_trace_link(self):
        with tempfile.TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "observability.sqlite3")
            trace_id = "a" * 32
            log.append(
                "user-1",
                "message-1",
                "gateway.received",
                {"content": "hello"},
                channel="ios",
            )
            log.append(
                "user-1",
                "",
                "invoke_agent",
                {"name": "invoke_agent"},
                trace_id=trace_id,
                channel="ios",
                source="otel",
            )
            log.append(
                "user-1",
                "message-1",
                "gateway.ack",
                {"type": "ack", "trace_id": trace_id},
                channel="ios",
            )

            log.repair_trace_links()

            link = log.trace_links()[0]
            self.assertEqual(link["user_id"], "user-1")
            self.assertEqual(link["message_id"], "message-1")
            self.assertEqual(link["trace_id"], trace_id)
            self.assertEqual(
                [
                    span["name"]
                    for span in log.detail("user-1", message_id="message-1", source="otel")
                ],
                ["message.lifecycle"],
            )

    def test_real_logger_records_are_separate_from_lifecycle_events(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventLog(Path(directory) / "observability.sqlite3")
            handler = EventLogHandler(store, service="hymio-backend")
            record = logging.LogRecord(
                name="hymio_backend.devices.routes",
                level=logging.ERROR,
                pathname=__file__,
                lineno=12,
                msg="device lookup failed authorization=Bearer synthetic-token",
                args=(),
                exc_info=None,
            )
            record.trace_id = "a" * 32
            record.channel = "ios"

            handler.emit(record)
            logs = store.search_logs("device lookup", since=0, channel="ios")

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["service"], "hymio-backend")
            self.assertEqual(logs[0]["level"], "ERROR")
            self.assertEqual(logs[0]["trace_id"], "a" * 32)
            self.assertNotIn("synthetic-token", logs[0]["message"])
            self.assertEqual(store.search("device lookup", since=0, source="application"), [])
            self.assertEqual(store.search("device lookup", since=0, source="otel"), [])

    def test_log_capture_includes_info_records_from_root_logger(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventLog(Path(directory) / "observability.sqlite3")
            capture = LogCapture(store)
            try:
                logging.getLogger("hymio_backend.test").info("captured info record")
            finally:
                capture.stop()

            logs = store.search_logs("captured info record", since=0)

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["level"], "INFO")


if __name__ == "__main__":
    unittest.main()
