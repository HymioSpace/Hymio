import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from hymio_backend.session_store import SessionStore
from hymio_backend.tasks.service import TaskService
from hymio_backend.tasks.store import TaskStore


class TaskReconciliationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = SimpleNamespace(database=Path(self.folder.name) / "tasks.sqlite")
        self.store = TaskStore(SessionStore(self.settings))

    def create(self, **patches):
        return self.store.create(
            "owner",
            dict(
                title="Reminder",
                objective="Notify me",
                success_criteria="Notification persisted",
                **patches,
            ),
        )

    def test_expired_once_is_not_claimed_and_cannot_start(self):
        at = datetime.fromtimestamp(time.time() - 100, timezone.utc).isoformat()
        task = self.create(schedule=dict(mode="once", timezone="UTC", at=at, grace_seconds=10))
        rid = task["runs"][0]["id"]
        self.assertEqual(self.store.claim_due(), [])
        with self.assertRaisesRegex(ValueError, "expired"):
            self.store.start("owner", rid)
        self.store.reconcile_time()
        self.store.reconcile_time()
        task = self.store.get("owner", task["id"])
        self.assertEqual(task["runs"][0]["status"], "expired")
        self.assertEqual(len(task["runs"][0]["updates"]), 1)
        self.assertEqual(len(self.store.notices()), 1)
        self.assertEqual(TaskStore(SessionStore(self.settings)).notices()[0]["id"], rid)
        self.assertEqual(self.store.list("other"), [])

    def test_late_within_window_can_start_but_ready_outside_cannot(self):
        at = datetime.fromtimestamp(time.time() - 20, timezone.utc).isoformat()
        task = self.create(schedule=dict(mode="once", timezone="UTC", at=at, grace_seconds=60))
        rid = task["runs"][0]["id"]
        self.assertEqual(len(self.store.claim_due()), 1)
        self.store.delivered("owner", rid)
        with patch("hymio_backend.tasks.store.time.time", return_value=time.time() + 100):
            with self.assertRaises(ValueError):
                self.store.start("owner", rid)
            self.store.reconcile_time()
        self.assertEqual(self.store.get("owner", task["id"])["runs"][0]["status"], "expired")

    def test_active_timeout_blocks_without_fabricating_completion(self):
        task = self.create(schedule=dict(mode="now", run_timeout_seconds=10))
        rid = task["runs"][0]["id"]
        self.store.claim_due()
        self.store.start("owner", rid, "step-0")
        with patch("hymio_backend.tasks.store.time.time", return_value=time.time() + 11):
            self.store.reconcile_time()
        run = self.store.get("owner", task["id"])["runs"][0]
        self.assertEqual(run["status"], "blocked")
        self.assertEqual(run["result"], "")
        self.assertEqual(len(self.store.notices()), 1)

    def test_expired_recurrence_plans_only_next_future_occurrence(self):
        task = self.create(schedule=dict(mode="daily", timezone="UTC", time="09:00"))
        rid = task["runs"][0]["id"]
        with self.store.transaction() as db:
            db.execute(
                "UPDATE task_runs SET due_at=?,expires_at=? WHERE id=?",
                (time.time() - 90000, time.time() - 89900, rid),
            )
        self.store.reconcile_time()
        runs = self.store.get("owner", task["id"])["runs"]
        self.assertEqual(len(runs), 2)
        self.assertEqual({r["status"] for r in runs}, {"scheduled", "expired"})
        self.assertGreater(
            next(r["due_at"] for r in runs if r["status"] == "scheduled"), time.time()
        )

    async def test_main_closure_is_durable_and_general_work_requires_outcome(self):
        for kind in ["reminder", "task"]:
            task = self.create(kind=kind)
            rid = task["runs"][0]["id"]
            self.store.claim_due()
            self.store.start("owner", rid, "step-0")
            service = TaskService(self.settings, self.store)
            service.oath = AsyncMock(return_value=dict(status="completed", content="Reminder text"))
            run = next(r for r in self.store.main_runs() if r["id"] == rid)
            await service.reconcile_main(run)
            result = self.store.get("owner", task["id"])["runs"][0]
            self.assertEqual(result["status"], "succeeded" if kind == "reminder" else "blocked")
            if kind == "task":
                self.assertTrue(self.store.notices())
            else:
                self.assertEqual(result["result"], "Reminder text")
            await service.reconcile_main(run)
            self.assertEqual(
                self.store.get("owner", task["id"])["runs"][0]["status"], result["status"]
            )

    def test_progress_renews_inactivity_and_cancellation_does_not_expire(self):
        task = self.create(schedule=dict(mode="now", run_timeout_seconds=10))
        rid = task["runs"][0]["id"]
        self.store.claim_due()
        self.store.start("owner", rid, "step-0")
        now = time.time()
        with patch("hymio_backend.tasks.store.time.time", return_value=now + 8):
            self.store.update_run("owner", rid, "running", "Made progress", "progress-1")
        with patch("hymio_backend.tasks.store.time.time", return_value=now + 12):
            self.store.reconcile_time()
        self.assertEqual(self.store.get("owner", task["id"])["runs"][0]["status"], "running")
        self.store.control("owner", task["id"], "cancel")
        with patch("hymio_backend.tasks.store.time.time", return_value=now + 100000):
            self.store.reconcile_time()
        self.assertEqual(self.store.get("owner", task["id"])["runs"][0]["status"], "cancelled")
        self.assertEqual(self.store.notices(), [])

    def test_intervention_is_bounded_and_old_ack_cannot_consume_new_notice(self):
        task = self.create(schedule=dict(mode="now", run_timeout_seconds=1))
        rid = task["runs"][0]["id"]
        self.store.claim_due()
        self.store.start("owner", rid, "first-0")
        now = time.time()
        with patch("hymio_backend.tasks.store.time.time", return_value=now + 2):
            self.store.reconcile_time()
        first = self.store.notices()[0]
        self.store.update_run(
            "owner", rid, "running", "User resumed", "resume", invocation_id="second-0"
        )
        with patch("hymio_backend.tasks.store.time.time", return_value=now + 10):
            self.store.reconcile_time()
        second = self.store.notices()[0]
        self.assertGreater(second["notice_version"], first["notice_version"])
        self.store.notice_sent("owner", rid, first["notice_version"])
        self.assertTrue(self.store.notices())
        self.store.notice_sent("owner", rid, second["notice_version"])
        self.store.update_run(
            "owner", rid, "running", "User resumed again", "resume2", invocation_id="third-0"
        )
        with patch("hymio_backend.tasks.store.time.time", return_value=now + 20):
            self.store.reconcile_time()
        self.assertEqual(self.store.notices(), [])
        self.assertEqual(self.store.get("owner", task["id"])["runs"][0]["status"], "blocked")
