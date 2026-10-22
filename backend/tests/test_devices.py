import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hymio_backend.devices.providers import E2BComputer, controller_program
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

    def test_one_binding_per_channel_and_fenced_connection_release(self):
        first = self.store.bind("alice", "browser-a", "web")
        second = self.store.bind("alice", "browser-b", "web")
        self.assertEqual(first["id"], second["id"])
        self.store.bind("alice", "phone-a", "ios")
        self.store.bind("alice", "phone-b", "ios")
        self.assertEqual(
            len([d for d in self.store.list("alice") if d["provider"] == "channel"]), 2
        )
        self.store.connection_claim("alice", "web", "old")
        self.store.connection_claim("alice", "web", "new")
        self.assertFalse(self.store.connection_renew("alice", "web", "old"))
        self.store.connection_release("alice", "web", "old")
        self.assertTrue(self.store.connection_renew("alice", "web", "new"))
        self.store.connection_claim("alice", "ios", "phone")
        self.assertTrue(self.store.connection_renew("alice", "web", "new"))

    def test_late_cloud_dispatch_is_rejected_before_execution(self):
        program = controller_program(
            {"capability": "bash", "arguments": {"command": "echo should-not-run"}, "timeout": 10},
            expires_at=0,
        )
        result = subprocess.run(
            [sys.executable, "-c", program], capture_output=True, text=True, check=True
        )
        self.assertEqual(
            json.loads(result.stdout), {"operation_rejected": "Dispatch deadline expired"}
        )

    def test_existing_duplicate_bindings_are_consolidated(self):
        old = self.store.bind("alice", "old-browser", "web")
        with self.store.transaction() as db:
            db.execute("DROP INDEX one_channel_kind")
            db.execute(
                "INSERT INTO devices(id,user_id,name,kind,provider,provider_ref,"
                "created_at,last_seen) "
                "VALUES('latest','alice','Web','web','channel','latest-browser',1,99999999999)"
            )
        migrated = DeviceStore(SimpleNamespace(transaction=self.store.transaction))
        self.assertEqual(
            [d["id"] for d in migrated.list("alice") if d["kind"] == "web"], ["latest"]
        )
        with self.assertRaises(KeyError):
            migrated.get("alice", old["id"])

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

    def test_non_device_invocation_has_specific_lookup_error(self):
        with self.assertRaises(KeyError) as raised:
            self.store.commands("alice", self.device, "multimodal-invocation")
        self.assertEqual(raised.exception.args, ("command_not_found",))

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

        sdk = SimpleNamespace(
            Sandbox=SimpleNamespace(get_info=info, connect=connect),
            SandboxNotFoundException=type("NotFound", (Exception,), {}),
        )
        with patch.dict("sys.modules", {"e2b": sdk, "e2b_desktop": sdk}):
            provider = E2BComputer(key_file, "test")
            self.assertEqual(provider.state({"provider_ref": "sandbox"}), "paused")
        self.assertEqual(calls, ["info"])

    def test_missing_sandbox_is_distinct_from_connection_failure(self):
        missing = type("NotFound", (Exception,), {})
        key_file = Path(self.temp.name) / "key"
        key_file.write_text("synthetic")
        for error, expected in ((missing(), "missing"), (TimeoutError(), "offline")):
            sdk = SimpleNamespace(
                Sandbox=SimpleNamespace(get_info=lambda *a, **kw: None),
                SandboxNotFoundException=missing,
            )
            with (
                patch.dict("sys.modules", {"e2b": sdk}),
                patch.object(sdk.Sandbox, "get_info", side_effect=error),
            ):
                self.assertEqual(
                    E2BComputer(key_file, "test").state({"provider_ref": "id"}), expected
                )

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
