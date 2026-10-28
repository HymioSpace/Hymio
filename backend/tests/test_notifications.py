import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.notifications import NotificationService, notification_routes
from hymio_backend.session_store import Unauthorized


class Sessions:
    def __init__(self, path):
        self.path = path

    def transaction(self):
        return _Transaction(self.path)


class _Transaction:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row

    def __enter__(self):
        self.db.execute("BEGIN IMMEDIATE")
        return self.db

    def __exit__(self, kind, value, traceback):
        if kind:
            self.db.rollback()
        else:
            self.db.commit()
        self.db.close()


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.sessions = Sessions(Path(self.folder.name) / "notifications.sqlite")
        self.service = NotificationService(
            SimpleNamespace(
                apns_key_file=None,
                apns_key_id="",
                apns_team_id="",
                apns_bundle_id="",
                service_token_file=None,
            ),
            self.sessions,
        )
        with self.sessions.transaction() as db:
            db.executescript(
                """
                CREATE TABLE tasks(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,title TEXT NOT NULL);
                CREATE TABLE task_runs(
                    id TEXT PRIMARY KEY,task_id TEXT NOT NULL,user_id TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT '',next_step TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '');
                INSERT INTO tasks VALUES('task-1','owner','Task');
                INSERT INTO task_runs(id,task_id,user_id) VALUES('run-1','task-1','owner');
                """
            )
        self.service.update(
            "owner",
            {
                "action": "register",
                "installation_id": "installation-1234",
                "token": "a" * 64,
                "environment": "sandbox",
                "app_version": "1.0",
            },
        )

    def tearDown(self):
        self.folder.cleanup()

    def test_preferences_and_registration_are_user_scoped(self):
        self.service.update(
            "owner",
            {
                "action": "preferences",
                "start_enabled": False,
                "show_details": True,
            },
        )
        status = self.service.status("owner")

        self.assertFalse(status["preferences"]["start_enabled"])
        self.assertTrue(status["preferences"]["show_details"])
        self.assertEqual(len(status["devices"]), 1)

    def test_disabled_notification_needs_no_delivery(self):
        self.service.update("owner", {"action": "preferences", "start_enabled": False})

        result = self.service.notify(
            "owner", {"kind": "started", "summary": "Working"}, "invocation-1"
        )

        self.assertEqual(result["status"], "suppressed")
        with self.sessions.transaction() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0], 0
            )

    def test_task_and_model_notification_share_a_stable_dedupe_key(self):
        first = self.service.notify(
            "owner",
            {
                "kind": "completion",
                "summary": "Done",
                "task_id": "task-1",
                "run_id": "run-1",
            },
            "tool-invocation",
        )
        second = self.service.notify(
            "owner",
            {
                "kind": "completion",
                "summary": "Done",
                "task_id": "task-1",
                "run_id": "run-1",
            },
            "rule-invocation",
        )

        self.assertEqual(first["status"], "queued")
        self.assertEqual(second["status"], "queued")
        with self.sessions.transaction() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0], 1
            )

    def test_details_are_hidden_on_lock_screen_until_opted_in(self):
        payload = self.service._payload(
            {
                "kind": "completion",
                "summary": "Private result",
                "task_id": "task",
                "route": "task:task",
                "event_key": "event",
            },
            False,
        )
        self.assertNotIn("Private", payload["aps"]["alert"]["body"])

    def test_notification_routes_require_account_or_internal_credentials(self):
        token_file = Path(self.folder.name) / "token"
        token_file.write_text("s" * 40)
        admin_file = Path(self.folder.name) / "admin-token"
        admin_file.write_text("a" * 40)
        self.service.settings.service_token_file = token_file
        self.service.settings.oath_admin_token_file = admin_file

        def verify(token):
            if token != "account-token":
                raise Unauthorized()
            return {"user_id": "owner"}

        self.sessions.verify = verify

        async def parse_body(request, limit=16384):
            return await request.json()

        def read_bearer(request):
            value = request.headers.get("authorization", "")
            return value[7:] if value.startswith("Bearer ") else ""

        app = Starlette(
            routes=notification_routes(
                self.service.settings, self.sessions, read_bearer, parse_body, self.service
            )
        )
        client = TestClient(app)
        self.addCleanup(client.close)

        self.assertEqual(client.get("/notifications").status_code, 401)
        status = client.get(
            "/notifications", headers={"Authorization": "Bearer account-token"}
        ).json()
        self.assertFalse(status["configured"])
        rejected = client.post(
            "/internal/notifications",
            json={"user_id": "owner", "kind": "started"},
            headers={"Authorization": "Bearer wrong"},
        )
        self.assertEqual(rejected.status_code, 401)
        accepted = client.post(
            "/internal/notifications",
            json={
                "user_id": "owner",
                "kind": "attention",
                "summary": "Approval needed",
                "request_id": "approval:test",
            },
            headers={"Authorization": "Bearer " + "a" * 40},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "queued")
