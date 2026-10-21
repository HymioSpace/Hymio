import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx

from hymio_backend.devices.api_provider import APIComputer, APITarget, targets_from_config
from hymio_backend.devices.providers import DispatchRejected, ProviderUnavailable, ProvisionRejected


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        key = self.root / "token"
        key.write_text("synthetic-test-token-with-at-least-32-characters")
        key.chmod(0o600)
        self.target = APITarget("cloud-primary", "alice", "https://device.example.com", str(key))
        self.provider = APIComputer((self.target,))
        self.device = {"user_id": "alice", "provider_ref": "cloud-primary"}
        self.addCleanup(self.temp.cleanup)

    def test_binding_survives_endpoint_change(self):
        changed = APIComputer((replace(self.target, base_url="https://new.example.com"),))
        self.assertEqual(changed.target(self.device).id, self.target.id)

    def test_other_user_cannot_use_target(self):
        with self.assertRaises(ProviderUnavailable):
            self.provider.target({**self.device, "user_id": "bob"})
        with self.assertRaises(ProvisionRejected):
            self.provider.provision({"user_id": "bob"})

    def test_requires_https_and_private_token(self):
        for url in (
            "http://device.example.com",
            "https://user:password@device.example.com",
            "https://device.example.com/?token=bad",
        ):
            with self.assertRaises(ValueError):
                targets_from_config([{**vars(self.target), "base_url": url}])
        Path(self.target.token_file).chmod(0o644)
        with self.assertRaises(ValueError):
            targets_from_config([vars(self.target)])

    def test_assignments_cannot_share_account_or_endpoint(self):
        data = vars(self.target)
        for change in (
            {"id": "second", "user_id": "bob"},
            {"id": "second", "base_url": "https://second.example.com"},
        ):
            with self.assertRaises(ValueError):
                targets_from_config([data, {**data, **change}])

    def transport(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        self.addCleanup(client.close)
        return patch("hymio_backend.devices.api_provider.httpx.Client", return_value=client)

    def test_http_auth_and_no_redirect(self):
        requests = []

        def handler(request):
            requests.append(request)
            self.assertTrue(request.headers["authorization"].startswith("Bearer "))
            return httpx.Response(307, headers={"location": "https://untrusted.example.com"})

        with self.transport(handler), self.assertRaises(ProviderUnavailable):
            self.provider.state(self.device)
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), "https://device.example.com/v1/status")

    def test_timeout_never_replays(self):
        requests = []

        def handler(request):
            requests.append(request)
            raise httpx.ReadTimeout("interrupted")

        with self.transport(handler), self.assertRaises(ProviderUnavailable):
            self.provider.execute(self.device, {"timeout": 1}, 1)
        self.assertEqual(len(requests), 1)

    def test_busy_is_not_dispatched(self):
        with self.transport(lambda r: httpx.Response(200, json={"rejected": "device_busy"})):
            with self.assertRaises(DispatchRejected):
                self.provider.execute(self.device, {}, 1)
