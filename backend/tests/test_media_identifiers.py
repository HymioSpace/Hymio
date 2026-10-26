import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.devices.store import DeviceStore
from hymio_backend.media.providers import MiniMaxMedia, ModelUnavailable
from hymio_backend.media.routes import media_routes, normalize_image
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
        self.assertEqual(uploaded.json()["content"][0]["media"][0]["source"], "attachment")
        self.assertEqual(captured.json()["content"][0]["media"][0]["source"], "device_screenshot")
        self.assertEqual(captured.json()["content"][0]["media"][0]["attachment_id"], screenshot)

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
        self.assertEqual(response.json()["content"][0]["media"][0]["source"], "device_screenshot")

    def test_unknown_media_id_has_specific_error(self):
        response = self.request("missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "attachment_not_found")

    def test_more_than_twelve_attachments_is_rejected(self):
        response = self.client.post(
            "/internal/media/understand",
            headers={"Authorization": "Bearer synthetic-service-token"},
            json={
                "user_id": "alice",
                "invocation_id": "too-many",
                "media_ids": [f"synthetic-{index}" for index in range(13)],
                "prompt": "What is visible?",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_media_request")

    def test_uploaded_images_are_downsampled_before_storage(self):
        source = io.BytesIO()
        Image.new("RGB", (4000, 1200), "white").save(source, format="PNG")
        normalized = normalize_image(source.getvalue())
        with Image.open(io.BytesIO(normalized)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), 2560)

    def test_empty_vision_analysis_is_a_model_failure(self):
        provider = MiniMaxMedia(self.settings)
        row = {"name": "synthetic.jpg", "mime": "image/jpeg", "content": b"synthetic"}
        with (
            patch.object(
                provider,
                "call",
                return_value={"choices": [{"message": {"content": "  "}}]},
            ),
            self.assertRaises(ModelUnavailable),
        ):
            provider.understand([row], "Describe")

    def test_private_native_resolver_checks_owner_and_authentication(self):
        raw = io.BytesIO()
        Image.new("RGB", (16, 16), "red").save(raw, format="PNG")
        item = self.media.save("alice", "square.png", "image/png", raw.getvalue())
        request = {"user_id": "alice", "image_refs": [item["attachment_id"]]}
        self.assertEqual(self.client.post("/internal/media/resolve", json=request).status_code, 401)
        headers = {"Authorization": "Bearer synthetic-service-token"}
        response = self.client.post("/internal/media/resolve", headers=headers, json=request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.json()["images"][item["attachment_id"]].startswith("data:image/jpeg;base64,")
        )
        response = self.client.post(
            "/internal/media/resolve",
            headers=headers,
            json={
                **request,
                "user_id": "bob",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_reasoning_budget_exhaustion_is_distinct_from_provider_outage(self):
        provider = MiniMaxMedia(self.settings)
        with patch.object(
            provider,
            "call",
            return_value={
                "choices": [
                    {"finish_reason": "length", "message": {"content": "<think>unfinished"}}
                ],
            },
        ):
            with self.assertRaises(ModelUnavailable) as raised:
                provider.understand([], "Describe")
        self.assertEqual(raised.exception.code, "analysis_output_limit")

    def test_failed_analysis_is_terminal_and_idempotent(self):
        item = self.media.save("alice", "square.png", "image/png", b"synthetic")
        with patch.object(
            SyntheticVision,
            "understand",
            side_effect=ModelUnavailable("Output budget exhausted", code="analysis_output_limit"),
        ) as understand:
            first = self.request(item["attachment_id"])
            second = self.request(item["attachment_id"])
        self.assertEqual(first.status_code, 503)
        self.assertEqual(first.json()["reason"], "analysis_output_limit")
        self.assertEqual(second.status_code, 503)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(understand.call_count, 1)
        with self.sessions.transaction() as db:
            status = db.execute("SELECT status FROM media_operations").fetchone()[0]
        self.assertEqual(status, "failed")
