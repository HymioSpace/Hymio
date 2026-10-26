import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from hymio_backend.compression import summary
from hymio_backend.event_log import EventLog


class Sessions:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


class CompressionTests(unittest.TestCase):
    def test_summary_groups_attempts_and_preserves_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observability.sqlite3"
            sessions = Sessions(path)
            log = EventLog(path)
            with sessions.transaction() as db:
                db.execute("CREATE TABLE users(user_id TEXT PRIMARY KEY,name TEXT)")
                db.execute("INSERT INTO users VALUES('u1','Synthetic User')")

            trace = "a" * 32
            now = time.time()
            async_id = "b" * 32
            for status, duration, at in (
                ("started", None, now - 4),
                ("ready", 1200, now - 3),
                ("applied", None, now - 2),
            ):
                payload = {
                    "compression_id": async_id,
                    "status": status,
                    "mode": "async",
                    "covers": 24,
                    "context_window": 128000,
                    "trace_id": trace,
                    "step_id": "c" * 16,
                }
                if duration is not None:
                    payload.update(
                        duration_ms=duration,
                        input_tokens=50000,
                        output_tokens=400,
                    )
                log.append(
                    "u1",
                    "",
                    "server.context.compaction",
                    payload,
                    trace_id=trace,
                    channel="ios",
                    source="otel",
                    occurred_at=at,
                )

            sync_id = "d" * 32
            log.append(
                "u1",
                "",
                "server.context.compaction",
                {
                    "compression_id": sync_id,
                    "status": "started",
                    "mode": "sync",
                    "covers": 28,
                    "trace_id": trace,
                },
                trace_id=trace,
                channel="ios",
                source="otel",
                occurred_at=now - 1,
            )
            log.append(
                "u1",
                "",
                "server.context.compaction",
                {
                    "compression_id": sync_id,
                    "status": "skipped",
                    "mode": "sync",
                    "reason": "over_budget",
                    "duration_ms": 2400,
                    "trace_id": trace,
                },
                trace_id=trace,
                channel="ios",
                source="otel",
                occurred_at=now,
            )
            log.append(
                "u1",
                "",
                "server.step.status",
                {
                    "status": "paused",
                    "reason": "context_window",
                    "trace_id": trace,
                },
                trace_id=trace,
                channel="ios",
                source="otel",
                occurred_at=now,
            )

            result = summary(sessions, since=now - 60)

            self.assertEqual(result["attempts"], 2)
            self.assertEqual(result["ready"], 1)
            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["applied"], 1)
            self.assertEqual(result["blocked_steps"], 1)
            self.assertEqual(result["by_mode"]["async"]["attempts"], 1)
            self.assertEqual(result["by_mode"]["sync"]["skipped"], 1)
            self.assertEqual(result["reasons"], [{"reason": "over_budget", "count": 1}])
            latest = result["recent"][0]
            self.assertEqual(latest["user_name"], "Synthetic User")
            self.assertEqual(latest["trace_id"], trace)
            self.assertEqual(latest["duration_ms"], 2400)

    def test_summary_accepts_durable_events_from_oath_admin_api(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observability.sqlite3"
            sessions = Sessions(path)
            EventLog(path)
            with sessions.transaction() as db:
                db.execute("CREATE TABLE users(user_id TEXT PRIMARY KEY,name TEXT)")
                db.execute("INSERT INTO users VALUES('u2','Remote User')")
            now = time.time()
            events = [
                {
                    "user_id": "u2",
                    "event_type": "context.compaction",
                    "occurred_at": datetime.fromtimestamp(now - 2, timezone.utc).isoformat(),
                    "payload": {
                        "compression_id": "remote",
                        "status": "started",
                        "mode": "sync",
                        "trace_id": "e" * 32,
                        "channel": "web",
                    },
                },
                {
                    "user_id": "u2",
                    "event_type": "context.compaction",
                    "occurred_at": datetime.fromtimestamp(now - 1, timezone.utc).isoformat(),
                    "payload": {
                        "compression_id": "remote",
                        "status": "ready",
                        "mode": "sync",
                        "reason": None,
                        "duration_ms": 1000,
                    },
                },
            ]

            result = summary(sessions, since=now - 86400, events=events)

            self.assertEqual(result["attempts"], 1)
            self.assertEqual(result["ready"], 1)
            self.assertEqual(result["recent"][0]["user_name"], "Remote User")
            self.assertEqual(result["recent"][0]["channel"], "web")


if __name__ == "__main__":
    unittest.main()
