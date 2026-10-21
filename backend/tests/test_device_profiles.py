"""Provider changes must not grant capabilities or cross resource boundaries."""

import unittest

from test_device_ensure import EnsureTests

from hymio_backend.devices.providers import DeviceProfile


class ProfileTests(EnsureTests):
    def test_description_and_execution_use_provider_capabilities(self):
        self.cloud.profile = DeviceProfile(
            capabilities=("computer",), workspace=None, resolution=(720, 1280)
        )
        device = self.service.ensure_available("alice")["device"]
        self.assertEqual(device["capabilities"], ["computer"])
        self.assertIsNone(device["workspace"])
        self.assertEqual(device["resolution"], {"width": 720, "height": 1280})
        with self.assertRaisesRegex(ValueError, "device_capability_not_supported"):
            self.service.execute(
                "alice",
                {
                    "device_id": device["device_id"],
                    "invocation_id": "unsupported",
                    "capability": "bash",
                    "arguments": {"command": "pwd"},
                },
            )

    def test_missing_persistent_device_is_not_replaced(self):
        self.cloud.profile = DeviceProfile(replace_missing=False, preserves_files_on_revoke=True)
        original = self.service.ensure_available("alice")["device"]
        device = self.service.store.get("alice", original["device_id"])
        self.cloud.states[device["provider_ref"]] = "missing"
        result = self.service.ensure_available("alice")
        self.assertEqual(result["action"], "recovery_required")
        self.assertEqual(result["device"]["device_id"], original["device_id"])
        self.assertEqual(self.cloud.created, 1)

    def test_replacement_retains_provider(self):
        device = self.service.store.create("alice", "daytona")
        replacement = self.service.store.replace_missing("alice", device["id"])
        self.assertEqual(replacement["provider"], "daytona")
        self.assertEqual(replacement["kind"], device["kind"])
        self.assertEqual(replacement["replaces_device_id"], device["id"])


if __name__ == "__main__":
    unittest.main()
