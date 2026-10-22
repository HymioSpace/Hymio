import unittest
from contextlib import contextmanager

from hymio_backend import client_telemetry


class _Database:
    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))


class _Sessions:
    def __init__(self):
        self.db = _Database()

    @contextmanager
    def transaction(self):
        yield self.db


class ClientTelemetryTests(unittest.TestCase):
    def test_stalled_turn_is_valid_without_completion_timestamp(self):
        sessions = _Sessions()
        sample = client_telemetry.record(
            sessions,
            "user-1",
            {
                "message_id": "message-1",
                "channel": "web",
                "outcome": "stalled",
                "sent_at": 1_700_000_000_000,
                "accepted_ms": 420,
                "first_response_ms": None,
                "completed_ms": None,
            },
            None,
        )

        self.assertEqual(sample["outcome"], "stalled")
        self.assertEqual(sample["accepted_ms"], 420)
        self.assertIsNone(sample["completed_ms"])
        self.assertEqual(len(sessions.db.calls), 1)

    def test_unknown_outcome_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_outcome"):
            client_telemetry.record(
                _Sessions(),
                "user-1",
                {
                    "message_id": "message-1",
                    "channel": "web",
                    "outcome": "mystery",
                    "sent_at": 1_700_000_000_000,
                },
                None,
            )


if __name__ == "__main__":
    unittest.main()
