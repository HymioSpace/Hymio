import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from hymio_backend.devices.service import DeviceService
from hymio_backend.session_store import SessionStore


class Cloud:
    def __init__(self):
        self.created = 0
        self.states = {}
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.fail = False

    def provision(self, device):
        self.created += 1
        self.started.set()
        self.release.wait(5)
        if self.fail:
            raise TimeoutError("uncertain create")
        ref = "sandbox-" + device["id"]
        self.states[ref] = "online"
        return ref

    def state(self, device):
        return self.states[device["provider_ref"]]

    def execution_idle(self, device):
        return True

    def pause(self, device):
        self.states[device["provider_ref"]] = "paused"

    def resume(self, device):
        self.states[device["provider_ref"]] = "online"


class EnsureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(
            database=Path(self.temp.name) / "db.sqlite", computer_provider="e2b", e2b_key_file=None
        )
        self.sessions = SessionStore(self.settings)
        self.service = DeviceService(self.settings, self.sessions)
        self.cloud = Cloud()
        self.service.providers["e2b"] = self.cloud

    def tearDown(self):
        self.temp.cleanup()

    def test_creates_once_then_reuses_same_binding(self):
        first = self.service.ensure_available("alice")["device"]
        again = self.service.ensure_available("alice")["device"]
        self.assertEqual(first["device_id"], again["device_id"])
        self.assertEqual(self.cloud.created, 1)

    def test_missing_is_replaced_but_transient_failure_is_not(self):
        old = self.service.ensure_available("alice")["device"]
        device = self.service.store.get("alice", old["device_id"])
        self.cloud.states[device["provider_ref"]] = "offline"
        self.assertEqual(self.service.ensure_available("alice")["action"], "unavailable")
        self.assertEqual(self.cloud.created, 1)
        self.cloud.states[device["provider_ref"]] = "missing"
        replacement = self.service.ensure_available("alice")
        self.assertEqual(replacement["action"], "replaced")
        self.assertEqual(replacement["device"]["replaces_device_id"], old["device_id"])
        self.assertNotEqual(replacement["device"]["device_id"], old["device_id"])
        self.assertEqual(len(self.service.store.list("alice")), 1)

    def test_manual_pause_is_respected_until_agent_requests_computer(self):
        device = self.service.ensure_available("alice")["device"]
        self.service.control("alice", device["device_id"], "pause")
        self.assertEqual(self.service.ensure_available("alice")["action"], "paused")
        resumed = self.service.ensure_available("alice", wake=True)
        self.assertEqual(resumed["action"], "resumed")
        self.assertEqual(resumed["device"]["device_id"], device["device_id"])

    def test_concurrent_services_do_not_create_duplicate_computers(self):
        other = DeviceService(self.settings, self.sessions)
        other.providers["e2b"] = self.cloud
        self.cloud.release.clear()
        with ThreadPoolExecutor(2) as executor:
            first = executor.submit(self.service.ensure_available, "alice")
            self.assertTrue(self.cloud.started.wait(2))
            second = other.ensure_available("alice")
            self.assertEqual(second["action"], "preparing")
            device = other.store.list("alice")[0]
            self.assertEqual(other.describe(device)["state"], "preparing")
            self.cloud.release.set()
            self.assertTrue(first.result()["device"]["online"])
        self.assertEqual(self.cloud.created, 1)

    def test_uncertain_creation_is_not_retried(self):
        self.cloud.fail = True
        with self.assertRaises(TimeoutError):
            self.service.ensure_available("alice")
        self.assertEqual(self.service.ensure_available("alice")["action"], "recovery_required")
        self.assertEqual(self.cloud.created, 1)

    def test_expired_execution_is_released_only_after_remote_idle_check(self):
        device = self.service.ensure_available("alice")["device"]
        self.service.store.claim("alice", device["device_id"], "old", {}, 10)
        with self.sessions.transaction() as db:
            db.execute("UPDATE device_locks SET deadline=0")
        self.cloud.execution_idle = lambda device: False
        self.service.ensure_available("alice")
        with self.sessions.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM device_locks").fetchone()[0], 1)
        self.cloud.execution_idle = lambda device: True
        self.service.ensure_available("alice")
        result = self.service.store.commands("alice", device["device_id"], "old")
        self.assertEqual(result["status"], "outcome_unknown")
        self.service.store.claim("alice", device["device_id"], "new", {}, 10)
        self.assertEqual(self.cloud.created, 1)

    def test_automatic_pause_resumes_without_replacing_computer(self):
        device = self.service.ensure_available("alice")["device"]
        ref = self.service.store.get("alice", device["device_id"])["provider_ref"]
        self.cloud.states[ref] = "paused"
        resumed = self.service.ensure_available("alice")
        self.assertEqual(resumed["action"], "resumed")
        self.assertEqual(resumed["device"]["device_id"], device["device_id"])
        self.assertEqual(self.cloud.created, 1)

    def test_expired_ensure_owner_cannot_release_new_owner(self):
        old = self.service.store.begin_ensure("alice")
        with self.sessions.transaction() as db:
            db.execute("UPDATE device_ensures SET deadline=0")
        new = self.service.store.begin_ensure("alice")
        self.service.store.finish_ensure("alice", old)
        self.assertIsNone(self.service.store.begin_ensure("alice"))
        self.service.store.finish_ensure("alice", new)
        self.assertIsNotNone(self.service.store.begin_ensure("alice"))
