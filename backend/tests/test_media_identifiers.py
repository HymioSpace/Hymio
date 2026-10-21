import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.devices.store import DeviceStore
from hymio_backend.media.routes import media_routes
from hymio_backend.media.store import MediaStore
from hymio_backend.session_store import SessionStore


class SyntheticVision:
    def __init__(self, settings):
        self.settings = settings

    def understand(self, rows, question):
        assert question == "What is visible?"
        return f"Vision inspected {len(rows)} image(s)"


class MediaIdentifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        token_file = root / "service-token"
        token_file.write_text("synthetic-service-token")
        self.settings = SimpleNamespace(
            database=root / "db.sqlite",
            origins=("http://127.0.0.1:1421",),
            service_token_file=token_file,
            media_credential="",
            media_api_base="https://media.example.com",
            model_options=("test-model",),
            vision_model="test-model",
            vault_role_id_file=None,
            vault_secret_id_file=None,
        )
        self.sessions = SessionStore(self.settings)
        with self.sessions.transaction() as db:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,?)",
                ("alice", "test", "alice", "Alice"),
            )
        self.media = MediaStore(self.sessions)
        self.devices = DeviceStore(self.sessions)

        async def body(request):
            return await request.json()

        def bearer(request):
            return request.headers.get("authorization", "").removeprefix("Bearer ")

        with patch("hymio_backend.media.routes.MiniMaxMedia", SyntheticVision):
            routes = media_routes(
                self.settings,
                self.sessions,
                bearer,
                body,
                self.media,
                device_media=self.devices.read_media_record,
            )
        self.client = TestClient(Starlette(routes=routes))
        self.addCleanup(self.client.close)

    def request(self, media_id):
        return self.client.post(
            "/internal/media/understand",
            headers={"Authorization": "Bearer synthetic-service-token"},
            json={
                "user_id": "alice",
                "invocation_id": "understand-" + media_id,
                "media_ids": [media_id],
                "prompt": "What is visible?",
            },
        )

    def test_attachment_and_device_screenshot_resolve_in_same_tool(self):
        attachment = self.media.save("alice", "upload.png", "image/png", b"upload")
        screenshot = self.devices.media("alice", "device-1", b"screenshot")

        uploaded = self.request(attachment["attachment_id"])
        captured = self.request(screenshot)

        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(captured.status_code, 200)
        self.assertEqual(
            uploaded.json()["content"][0]["media"][0]["source"], "attachment"
        )
        self.assertEqual(
            captured.json()["content"][0]["media"][0]["source"], "device_screenshot"
        )
        self.assertEqual(
            captured.json()["content"][0]["media"][0]["attachment_id"], screenshot
        )

    def test_legacy_attachment_ids_parameter_remains_compatible(self):
        attachment = self.media.save("alice", "upload.png", "image/png", b"upload")
        response = self.client.post(
            "/internal/media/understand",
            headers={"Authorization": "Bearer synthetic-service-token"},
            json={
                "user_id": "alice",
                "invocation_id": "legacy-parameter",
                "attachment_ids": [attachment["attachment_id"]],
                "prompt": "What is visible?",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_media_url_is_reduced_to_the_owned_identifier(self):
        screenshot = self.devices.media("alice", "device-1", b"screenshot")
        response = self.request("/devices/media/" + screenshot)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["content"][0]["media"][0]["source"], "device_screenshot"
        )

    def test_unknown_media_id_has_specific_error(self):
        response = self.request("missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "attachment_not_found")
