"""Host API authentication and request boundaries without executing user commands."""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient


class HostAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.token = "synthetic-device-token-over-32-characters"
        path = Path(self.temp.name) / "token"
        path.write_text(self.token)
        host = Path(__file__).resolve().parents[2] / "deploy/computer"
        with patch.dict(os.environ, {"HYMIO_DEVICE_TOKEN_FILE": str(path)}):
            spec = importlib.util.spec_from_file_location(
                "test_host_device_api_module", host / "device_api.py"
            )
            self.module = importlib.util.module_from_spec(spec)
            with patch.dict(
                sys.modules,
                {
                    "device_runtime": type(
                        "Runtime", (), {"handle": lambda data: {"state": "online"}}
                    )
                },
            ):
                spec.loader.exec_module(self.module)
        self.client = TestClient(self.module.app)
        self.addCleanup(self.client.close)

    def test_requires_authentication(self):
        with patch.object(self.module, "handle") as handle:
            self.assertEqual(self.client.post("/v1/status").status_code, 401)
            handle.assert_not_called()

    def test_authenticated_status(self):
        r = self.client.post(
            "/v1/status", headers={"Authorization": "Bearer " + self.token}, json={}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "online")

    def test_rejects_oversized_body_before_execution(self):
        with patch.object(self.module, "handle") as handle:
            r = self.client.post(
                "/v1/execute",
                headers={"Authorization": "Bearer " + self.token},
                content="x" * 65537,
            )
            self.assertEqual(r.status_code, 413)
            handle.assert_not_called()

    def test_rejects_unknown_protocol_fields(self):
        r = self.client.post(
            "/v1/status",
            headers={"Authorization": "Bearer " + self.token},
            json={"user_id": "other-user"},
        )
        self.assertEqual(r.status_code, 400)
