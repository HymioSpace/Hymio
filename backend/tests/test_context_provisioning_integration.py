import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
import uvicorn
from starlette.testclient import TestClient

pytest.importorskip("nostalgia")
from nostalgia.api import create_app as create_nostalgia_app
from nostalgia.bootstrap.config import Settings as NostalgiaSettings

from hymio_backend.config import Settings
from hymio_backend.server import build_app


@contextmanager
def _http_service(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = "http://127.0.0.1:" + str(sock.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert thread.is_alive() and time.monotonic() < deadline
        time.sleep(0.01)
    try:
        yield url
    finally:
        server.should_exit = True
        thread.join(10)
        assert not thread.is_alive()
        sock.close()


def _hymio_settings(root: Path, nostalgia_url: str, service_token: Path):
    return Settings(
        database=root / "hymio.sqlite",
        issuer="https://identity.example",
        client_id="hymio",
        client_secret_file=root / "oidc-secret",
        public_url="https://hymio.example",
        callback_url="https://hymio.example/auth/callback",
        service_token_file=service_token,
        origins=(),
        oath_ws="ws://agent.example",
        oath_biz="http://biz.example",
        nostalgia_url=nostalgia_url,
    )


def test_signup_provisions_and_uses_one_context_identity_end_to_end(tmp_path):
    service_token = tmp_path / "internal-service-token"
    service_token.write_text("s" * 64)
    nostalgia = create_nostalgia_app(
        NostalgiaSettings(
            database=tmp_path / "nostalgia.sqlite",
            tokens={},
            dreaming_provider_token_file=service_token,
        )
    )
    with _http_service(nostalgia) as nostalgia_url:
        settings = _hymio_settings(tmp_path, nostalgia_url, service_token)
        claims = {"iss": settings.issuer, "sub": "single-identity-user"}
        with patch(
            "hymio_backend.server.CasdoorAccounts.authenticate",
            return_value=claims,
        ):
            with TestClient(build_app(settings)) as client:
                signup = client.post(
                    "/auth/account",
                    json={
                        "action": "signup",
                        "username": "single-user",
                        "password": "Test-password-123",
                    },
                )
                assert signup.status_code == 200
                session = signup.json()
                assert session["context_ready"] is True
                authorization = {"Authorization": "Bearer " + session["access_token"]}
                created = client.post(
                    "/context/records",
                    headers={**authorization, "Idempotency-Key": "first-memory"},
                    json={
                        "item_type": "context",
                        "context_type": "text",
                        "context": {"text": "我喜欢不加糖的咖啡"},
                    },
                )
                assert created.status_code == 201, created.text
                listed = client.get("/context/records", headers=authorization)
                assert listed.status_code == 200, listed.text
                assert listed.json()["items"][0]["context"]["text"] == "我喜欢不加糖的咖啡"

        with nostalgia.state.store.transaction() as db:
            token_hash = db.execute("SELECT token_hash FROM api_tokens").fetchone()[0]
        database = (tmp_path / "hymio.sqlite").read_bytes()
        assert service_token.read_bytes() not in database
        assert token_hash.encode() not in database

    with nostalgia.state.store.transaction() as db:
        assert db.execute("SELECT user_id FROM api_tokens").fetchone()[0] == session["user_id"]
