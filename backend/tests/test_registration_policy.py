import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from hymio_backend.config import Settings
from hymio_backend.server import build_app


class RegistrationPolicyTests(unittest.TestCase):
    def test_closed_registration_rejects_requests_before_identity_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(
                database=root / "state.sqlite",
                issuer="https://identity.example",
                client_id="hymio",
                client_secret_file=root / "oidc-secret",
                public_url="https://hymio.example",
                callback_url="https://hymio.example/auth/callback",
                service_token_file=root / "service-secret",
                origins=(),
                oath_ws="ws://agent.example",
                oath_biz="http://biz.example",
                signup_enabled=False,
            )
            with patch("hymio_backend.server.CasdoorAccounts.authenticate") as authenticate:
                with TestClient(build_app(settings)) as client:
                    self.assertFalse(client.get("/auth/options").json()["signup_enabled"])
                    response = client.post("/auth/account", json={"action": "signup"})
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json(), {"error": "registration_closed"})
                    authenticate.assert_not_called()

    def test_invitation_rotation_and_missing_file_fail_closed(self):

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codes = root / "invitations"
            codes.write_text("first-code\nsecond-code\n")
            settings = Settings(
                database=root / "state.sqlite",
                issuer="https://identity.example",
                client_id="hymio",
                client_secret_file=root / "oidc-secret",
                public_url="https://hymio.example",
                callback_url="https://hymio.example/auth/callback",
                service_token_file=root / "service-secret",
                origins=(),
                oath_ws="ws://agent.example",
                oath_biz="http://biz.example",
                invitation_codes_file=codes,
            )
            credentials = {
                "action": "signup",
                "username": "new-user",
                "password": "Test-password-123",
            }
            claims = {"iss": settings.issuer, "sub": "synthetic-user"}
            with patch(
                "hymio_backend.server.CasdoorAccounts.authenticate", return_value=claims
            ) as auth:
                with TestClient(build_app(settings)) as client:
                    self.assertTrue(client.get("/auth/options").json()["invitation_required"])
                    for code in (None, "wrong", "☃"):
                        response = client.post(
                            "/auth/account", json={**credentials, "invitation_code": code}
                        )
                        self.assertEqual(response.status_code, 403)
                    auth.assert_not_called()
                    response = client.post(
                        "/auth/account", json={**credentials, "invitation_code": "second-code"}
                    )
                    self.assertEqual(response.status_code, 200)
                    codes.write_text("replacement-code\n")
                    self.assertEqual(
                        client.post(
                            "/auth/account", json={**credentials, "invitation_code": "second-code"}
                        ).status_code,
                        403,
                    )
                    self.assertEqual(
                        client.post(
                            "/auth/account",
                            json={**credentials, "invitation_code": "replacement-code"},
                        ).status_code,
                        200,
                    )
                    codes.write_text("")
                    self.assertEqual(
                        client.post(
                            "/auth/account", json={**credentials, "invitation_code": ""}
                        ).status_code,
                        403,
                    )
                    codes.unlink()
                    self.assertEqual(
                        client.post("/auth/account", json=credentials).status_code, 503
                    )
                    self.assertEqual(auth.call_count, 2)
