import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.devices.admin import admin_routes
from hymio_backend.devices.resources import ResourceCapacity, ResourceDenied
from hymio_backend.devices.service import DeviceService
from hymio_backend.devices.store import DeviceStore
from hymio_backend.session_store import SessionStore


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = SimpleNamespace(
            database=Path(self.temp.name) / "db.sqlite",
            computer_provider="daytona",
            daytona_key_file=Path(self.temp.name) / "daytona-key",
            daytona_api_url="https://app.daytona.io/api",
            daytona_snapshot="",
            e2b_key_file=None,
            device_api_targets=(),
            admin_user_ids=("admin",),
            origins=("https://app.example.com",),
        )
        self.settings.daytona_key_file.write_text("synthetic")
        self.sessions = SessionStore(self.settings)
        self.service = DeviceService(self.settings, self.sessions)
        with self.sessions.transaction() as db:
            db.executemany(
                "INSERT INTO users VALUES(?,?,?,?)",
                [(u, "synthetic", u, u) for u in ("admin", "alice", "bob")],
            )

        async def body(request):
            return await request.json()

        def bearer(request):
            return request.headers.get("authorization", "").removeprefix("Bearer ")

        # The HTTP boundary still exercises every administrator check; token validation is stubbed.
        self.sessions.verify = lambda token: {"user_id": token}
        self.client = TestClient(
            Starlette(routes=admin_routes(self.settings, self.sessions, bearer, body))
        )
        self.addCleanup(self.client.close)

    def test_new_user_cannot_provision_or_execute_existing_device(self):
        self.assertEqual(self.service.ensure_available("alice")["error"], "resource_access_denied")
        with self.assertRaises(ResourceDenied):
            self.service.provision("alice")
        self.assertEqual(self.service.store.list("alice"), [])

    def test_only_configured_admin_can_grant(self):
        data = {"user_id": "alice", "provider": "daytona", "enabled": True}
        r = self.client.post(
            "/admin/api/resources/grants", headers={"Authorization": "Bearer bob"}, json=data
        )
        self.assertEqual(r.status_code, 403)
        self.assertIsNone(self.service.resources.provider("alice"))
        r = self.client.post(
            "/admin/api/resources/grants", headers={"Authorization": "Bearer admin"}, json=data
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.service.resources.provider("alice"), "daytona")

    def test_cannot_grant_phone_or_unknown_users(self):
        for data in (
            {"user_id": "alice", "provider": "daytona", "enabled": True, "kind": "cloud_android"},
            {"user_id": "missing", "provider": "daytona", "enabled": True},
        ):
            r = self.client.post(
                "/admin/api/resources/grants", headers={"Authorization": "Bearer admin"}, json=data
            )
            self.assertIn(r.status_code, (400, 404))

    def test_cap_is_transactional_across_services(self):
        def create(index):
            try:
                return DeviceStore(self.sessions).create("user-" + str(index), "daytona")["id"]
            except ResourceCapacity:
                return None

        with ThreadPoolExecutor(8) as executor:
            result = list(executor.map(create, range(24)))
        self.assertEqual(len([r for r in result if r]), 10)
        overview = self.service.resources.overview()
        self.assertEqual(
            next(p for p in overview["providers"] if p["provider"] == "daytona")["used"], 10
        )

    def test_pause_and_uncertainty_hold_capacity(self):
        for i in range(10):
            device = self.service.store.create("user-" + str(i), "daytona")
            self.service.resources.mark(device["id"], "outcome_unknown" if i % 2 else "allocated")
        with self.assertRaises(ResourceCapacity):
            self.service.store.create("extra", "daytona")
        self.service.resources.mark(device["id"], "released")
        self.service.store.create("extra", "daytona")

    def test_revoked_access_does_not_free_capacity(self):
        self.service.resources.grant("admin", "alice", "daytona", True)
        self.service.store.create("alice", "daytona")
        self.service.resources.grant("admin", "alice", "daytona", False)
        self.assertIsNone(self.service.resources.provider("alice"))
        self.assertEqual(self.service.ensure_available("alice")["error"], "resource_access_denied")
        self.assertEqual(len(self.service.resources.overview()["devices"]), 1)

    def test_provider_switch_requires_releasing_active_cloud_computer(self):
        self.service.resources.grant("admin", "alice", "daytona", True)
        device = self.service.store.create("alice", "daytona")
        with self.assertRaisesRegex(ResourceCapacity, "resource_release_required"):
            self.service.resources.grant("admin", "alice", "e2b", True)
        self.service.resources.mark(device["id"], "released")
        self.service.resources.grant("admin", "alice", "e2b", True)
        self.assertEqual(self.service.resources.provider("alice"), "e2b")

    def test_untrusted_origin_cannot_mutate(self):
        r = self.client.post(
            "/admin/api/resources/grants",
            headers={"Authorization": "Bearer admin", "Origin": "https://evil.example.com"},
            json={"user_id": "alice", "provider": "daytona", "enabled": True},
        )
        self.assertEqual(r.status_code, 403)

    def test_each_provider_limit(self):
        for provider, limit in (("e2b", 20), ("device_api", 1)):
            with self.subTest(provider=provider):
                for index in range(limit):
                    self.service.store.create(f"{provider}-{index}", provider)
                with self.assertRaises(ResourceCapacity):
                    self.service.store.create(f"{provider}-extra", provider)

    def test_permission_revocation_blocks_dispatch(self):
        self.service.resources.grant("admin", "alice", "daytona", True)
        device = self.service.store.create("alice", "daytona")
        self.service.resources.grant("admin", "alice", "daytona", False)
        with self.assertRaises(ResourceDenied):
            self.service.execute(
                "alice",
                {
                    "device_id": device["id"],
                    "invocation_id": "denied",
                    "capability": "bash",
                    "arguments": {"command": "true"},
                },
            )
        with self.sessions.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM device_commands").fetchone()[0], 0)

    def test_uncertain_release_preserves_capacity_and_blocks_second_release(self):
        from hymio_backend.devices.store import DeviceConflict

        class OfflineProvider:
            def state(self, device):
                return "online"

            def stop(self, device):
                raise TimeoutError()

        self.service.providers["daytona"] = OfflineProvider()
        device = self.service.store.create("alice", "daytona")
        with self.sessions.transaction() as db:
            db.execute("UPDATE devices SET provider_ref='synthetic' WHERE id=?", (device["id"],))
        result = self.service.revoke("alice", device["id"])
        self.assertFalse(result["stopped"])
        with self.assertRaises(DeviceConflict):
            self.service.revoke("alice", device["id"])
        self.assertEqual(
            self.service.resources.overview()["devices"][0]["state"], "release_unknown"
        )

    def test_overview_distinguishes_running_and_stale_device_locks(self):
        device = self.service.store.create("alice", "daytona")
        self.service.store.claim("alice", device["id"], "running", {}, 30)
        row = self.service.resources.overview()["devices"][0]
        self.assertEqual(row["lock_state"], "running")

        with self.sessions.transaction() as db:
            db.execute("UPDATE device_locks SET deadline=0")
        row = self.service.resources.overview()["devices"][0]
        self.assertEqual(row["lock_state"], "stale")
