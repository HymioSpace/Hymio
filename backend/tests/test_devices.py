import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hymio_backend.devices.providers import E2BComputer
from hymio_backend.devices.store import DeviceConflict, DeviceStore
from hymio_backend.session_store import SessionStore


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = DeviceStore(
            SessionStore(
                SimpleNamespace(
                    database=Path(self.temp.name) / "test.sqlite",
                )
            )
        )
        self.device = self.store.create("alice", "e2b")["id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_ownership(self):
        with self.assertRaises(KeyError):
            self.store.claim("bob", self.device, "tool1", {}, 10)
        self.assertEqual(self.store.list("bob"), [])

    def test_one_owner_wins_concurrent_claim(self):
        def claim(index):
            try:
                self.store.claim("alice", self.device, str(index), {}, 10)
                return True
            except DeviceConflict:
                return False

        with ThreadPoolExecutor(8) as pool:
            self.assertEqual(sum(pool.map(claim, range(8))), 1)

    def test_duplicate_is_not_executed(self):
        self.store.claim("alice", self.device, "tool1", {"command": "write"}, 10)
        self.store.finish("alice", "tool1", {"status": "succeeded", "value": 42})
        _, result = self.store.claim("alice", self.device, "tool1", {"command": "write"}, 10)
        self.assertEqual(result["value"], 42)
        with self.assertRaises(DeviceConflict):
            self.store.claim("alice", self.device, "tool1", {"command": "other"}, 10)

    def test_unknown_keeps_device_blocked(self):
        self.store.claim("alice", self.device, "tool1", {}, 10)
        self.store.finish("alice", "tool1", {"status": "outcome_unknown"}, release=False)
        with self.assertRaises(DeviceConflict):
            self.store.claim("alice", self.device, "tool2", {}, 10)

    def test_revoke_prevents_execution(self):
        self.store.revoke("alice", self.device)
        with self.assertRaises(KeyError):
            self.store.claim("alice", self.device, "tool1", {}, 10)

    def test_pause_blocks_commands_and_resume_preserves_history(self):
        self.store.claim("alice", self.device, "tool1", {"capability": "bash"}, 10)
        with self.assertRaises(DeviceConflict):
            self.store.begin_control("alice", self.device, "pause")
        self.store.finish("alice", "tool1", {"status": "succeeded"})
        control = self.store.begin_control("alice", self.device, "pause")
        self.store.finish_control("alice", self.device, control, "paused")
        with self.assertRaises(DeviceConflict):
            self.store.claim("alice", self.device, "tool2", {}, 10)
        control = self.store.begin_control("alice", self.device, "resume")
        self.store.finish_control("alice", self.device, control, "active")
        self.store.claim("alice", self.device, "tool2", {}, 10)
        self.assertEqual(self.store.commands("alice", self.device, "tool1")["status"], "succeeded")
        with self.assertRaises(KeyError):
            self.store.commands("bob", self.device)

    def test_control_cannot_clear_unknown_tool_lock(self):
        self.store.claim("alice", self.device, "tool1", {}, 10)
        self.store.finish("alice", "tool1", {"status": "outcome_unknown"}, release=False)
        with self.store.transaction() as db:
            db.execute("UPDATE device_locks SET deadline=0")
        with self.assertRaises(DeviceConflict):
            self.store.begin_control("alice", self.device, "resume")

    def test_stale_control_cannot_unlock_new_control(self):
        first = self.store.begin_control("alice", self.device, "pause")
        with self.store.transaction() as db:
            db.execute("UPDATE device_locks SET deadline=0")
        second = self.store.begin_control("alice", self.device, "resume")
        with self.assertRaises(DeviceConflict):
            self.store.finish_control("alice", self.device, first, "paused")
        with self.assertRaises(DeviceConflict):
            self.store.claim("alice", self.device, "tool1", {}, 10)
        self.store.finish_control("alice", self.device, second, "active")
        self.store.claim("alice", self.device, "tool1", {}, 10)

    def test_provider_state_never_connects_or_resumes(self):
        key_file = Path(self.temp.name) / "key"
        key_file.write_text("synthetic-key")
        calls = []

        def info(*args, **kwargs):
            calls.append("info")
            return SimpleNamespace(state=SimpleNamespace(value="paused"))

        def connect(*args, **kwargs):
            raise AssertionError("State query resumed a sandbox")

        sdk = SimpleNamespace(Sandbox=SimpleNamespace(get_info=info, connect=connect))
        with patch.dict("sys.modules", {"e2b": sdk, "e2b_desktop": sdk}):
            provider = E2BComputer(key_file, "test")
            self.assertEqual(provider.state({"provider_ref": "sandbox"}), "paused")
        self.assertEqual(calls, ["info"])

    def test_late_result_cannot_replace_unknown(self):
        self.store.claim("alice", self.device, "tool1", {}, 10)
        with self.store.transaction() as db:
            db.execute("UPDATE device_commands SET deadline=0")
        _, result = self.store.claim("alice", self.device, "tool1", {}, 10)
        self.assertEqual(result["status"], "outcome_unknown")
        result = self.store.finish("alice", "tool1", {"status": "succeeded"})
        self.assertEqual(result["status"], "outcome_unknown")
        with self.assertRaises(DeviceConflict):
            self.store.claim("alice", self.device, "tool2", {}, 10)

    def test_channels_are_stable_but_mac_is_unique(self):
        mac = self.store.bind("alice", "installation1", "mac")
        self.assertEqual(mac["id"], self.store.bind("alice", "installation1", "mac")["id"])
        with self.assertRaises(DeviceConflict):
            self.store.bind("alice", "installation2", "mac")
        self.store.bind("alice", "installation2", "ios")
        self.store.bind("bob", "installation1", "mac")
