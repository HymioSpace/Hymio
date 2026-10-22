import tempfile
import unittest
from pathlib import Path

from hymio_backend.event_log import EventLog


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


if __name__ == "__main__":
    unittest.main()
