import asyncio
import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from hymio_backend.config import Settings
from hymio_backend.connectors.catalog import ConnectorError
from hymio_backend.connectors.providers import normalize_native, pull_gmail
from hymio_backend.connectors.routes import connector_routes
from hymio_backend.connectors.service import ConnectorService
from hymio_backend.server import bearer, body
from hymio_backend.session_store import SessionStore


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "DIDA_CLIENT_ID", "DIDA_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    secret = tmp_path / "secret"
    secret.write_text("synthetic-internal-service")
    registration = tmp_path / "registrations.json"
    registration.write_text(
        json.dumps(
            {"gmail": {"client_id": "synthetic-client", "client_secret": "synthetic-secret"}}
        )
    )
    settings = Settings(
        tmp_path / "state.sqlite",
        "https://identity.example",
        "synthetic",
        secret,
        "https://hymio.example",
        "https://hymio.example/auth/callback",
        secret,
        (),
        "wss://agent.example",
        "http://agent",
        connectors_config_file=registration,
    )
    sessions = SessionStore(settings)
    a = sessions.create_session({"iss": settings.issuer, "sub": "a"})
    b = sessions.create_session({"iss": settings.issuer, "sub": "b"})
    service = ConnectorService(settings, sessions)
    app = Starlette(routes=connector_routes(settings, sessions, service, bearer, body))
    return service, sessions, a, b, TestClient(app)


def native(service, uid, provider="apple_health"):
    return service.store.create(uid, provider, "synthetic-phone")


def health(steps=1234):
    return {
        "device_id": "synthetic-phone",
        "captured_at": time.time(),
        "consent": True,
        "items": [
            {
                "external_id": "daily:2026-01-01",
                "day": "2026-01-01",
                "kind": "health_daily",
                "steps": steps,
                "title": "每日活动",
            }
        ],
    }


def test_owner_consent_and_missing_registration(setup):
    service, sessions, a, b, client = setup
    headers = {"Authorization": "Bearer " + a["access_token"]}
    assert client.get("/connectors").status_code == 401
    response = client.post(
        "/connectors",
        headers=headers,
        json={
            "provider": "apple_health",
            "device_id": "synthetic-phone",
            "platform": "ios",
            "consent": True,
        },
    )
    assert response.status_code == 200
    cid = response.json()["id"]
    assert (
        client.post(
            "/connectors/" + cid + "/ingest",
            headers={"Authorization": "Bearer " + b["access_token"]},
            json=health(),
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/connectors/" + cid + "/ingest", headers=headers, json={**health(), "consent": False}
        ).status_code
        == 400
    )
    assert (
        client.post("/connectors/" + cid + "/ingest", headers=headers, json=health()).status_code
        == 200
    )
    assert len(service.read(a["user_id"], cid)) == 1
    assert service.read(b["user_id"]) == []
    assert (
        client.post(
            "/connectors", headers=headers, json={"provider": "dida", "consent": True}
        ).json()["error"]
        == "provider_not_configured"
    )
    assert "credentials" not in json.dumps(service.store.list(a["user_id"]))


def test_environment_registration_takes_precedence(setup, monkeypatch):
    service, _, a, _, _ = setup
    monkeypatch.setenv("DIDA_CLIENT_ID", "synthetic-environment-client")
    monkeypatch.setenv("DIDA_CLIENT_SECRET", "synthetic-environment-secret")
    assert service.registration("dida") == {
        "client_id": "synthetic-environment-client",
        "client_secret": "synthetic-environment-secret",
    }
    cid = service.store.create(a["user_id"], "dida")["id"]
    params = parse_qs(urlsplit(service.authorize(a["user_id"], cid)["url"]).query)
    assert params["client_id"] == ["synthetic-environment-client"]
    assert params["scope"] == ["tasks:read"]


def test_incomplete_environment_registration_is_not_used(setup, monkeypatch):
    service, _, _, _, _ = setup
    monkeypatch.setenv("DIDA_CLIENT_ID", "synthetic-environment-client")
    monkeypatch.delenv("DIDA_CLIENT_SECRET", raising=False)
    assert service.registration("dida") is None


def test_revision_cycles_and_projection_retry(setup):
    service, sessions, a, _, _ = setup
    uid = a["user_id"]
    cid = native(service, uid)["id"]
    service.ingest(uid, cid, health(1))
    service.ingest(uid, cid, health(1))
    service.ingest(uid, cid, health(2))
    service.ingest(uid, cid, health(1))
    with service.store.transaction() as db:
        assert db.execute("select count(*) from connector_changes").fetchone()[0] == 3

    class Context:
        def __init__(self):
            self.requests = []

        def call(self, user, operation, **kwargs):
            self.requests.append(kwargs)
            return {"data": {"id": str(len(self.requests))}}

    context = Context()
    service.context = context
    for _ in range(3):
        service.project()
    assert len(context.requests) == 3
    assert context.requests[1]["data"]["expected_record_id"] == "1"
    assert len({r["operation_id"] for r in context.requests}) == 3
    assert service.store.list(uid)[0]["pending_count"] == 0


def test_oauth_pkce_single_use_encrypted_tokens_and_fence(setup):
    service, sessions, a, _, _ = setup
    uid = a["user_id"]
    cid = service.store.create(uid, "gmail")["id"]
    url = service.authorize(uid, cid)["url"]
    params = parse_qs(urlsplit(url).query)
    assert params["code_challenge_method"] == ["S256"]

    async def fake(req):
        assert req.url.host == "oauth2.googleapis.com"
        return httpx.Response(
            200,
            json={
                "access_token": "synthetic-provider-token",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
            },
        )

    service.http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    asyncio.run(service.callback("gmail", params["state"][0], "synthetic-code"))
    with service.store.transaction() as db:
        row = service.store.owned(db, uid, cid)
        assert "synthetic-provider-token" not in row["credentials"]
    with pytest.raises(ConnectorError):
        asyncio.run(service.callback("gmail", params["state"][0], "synthetic-code"))
    claimed = service.store.claim()
    service.store.action(uid, cid, "pause")
    with pytest.raises(ConnectorError):
        service.store.apply(
            uid, cid, [], {}, lease=claimed["lease"], generation=claimed["generation"]
        )
    assert service.store.list(uid)[0]["state"] == "paused"


def test_partial_calendar_never_removes_and_full_window_reconciles(setup):
    service, _, a, _, _ = setup
    uid = a["user_id"]
    cid = native(service, uid, "apple_calendar")["id"]
    event = {
        "external_id": "event-1",
        "title": "Synthetic meeting",
        "calendar_id": "cal",
        "start": "2026-01-01T09:00:00Z",
        "end": "2026-01-01T10:00:00Z",
    }
    payload = {
        "device_id": "synthetic-phone",
        "captured_at": time.time(),
        "consent": True,
        "items": [event],
    }
    service.ingest(uid, cid, payload)
    service.ingest(uid, cid, {**payload, "captured_at": time.time(), "items": []})
    assert len(service.read(uid, cid)) == 1
    service.ingest(
        uid,
        cid,
        {
            **payload,
            "items": [],
            "complete": True,
            "captured_at": time.time(),
            "window": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-08T00:00:00Z",
                "calendars": ["cal"],
            },
        },
    )
    assert service.read(uid, cid) == []


def test_gmail_page_checkpoint_and_no_attachment_fetch():
    paths = []

    async def fake(req):
        paths.append(req.url.path)
        if req.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "123"})
        if req.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1"}], "nextPageToken": "next"})
        return httpx.Response(
            200,
            json={
                "id": "m1",
                "labelIds": ["INBOX"],
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [{"name": "Subject", "value": "Hello"}],
                    "body": {"data": base64.urlsafe_b64encode(b"World").decode()},
                },
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as client:
            return await pull_gmail(client, "synthetic", {})

    items, checkpoint = asyncio.run(run())
    assert items[0]["text"] == "World" and checkpoint == {"anchor": "123", "page": "next"}
    assert len(paths) == 3


def test_health_validation():
    with pytest.raises(ConnectorError):
        normalize_native("apple_health", health(float("nan")))


def test_native_replay_and_old_snapshot_rejected(setup):
    service, _, a, _, _ = setup
    uid = a["user_id"]
    cid = native(service, uid)["id"]
    first = health(100)
    service.ingest(uid, cid, first)
    service.ingest(uid, cid, first)
    with service.store.transaction() as db:
        assert db.execute("select count(*) from connector_changes").fetchone()[0] == 1
    older = {**health(99), "captured_at": first["captured_at"] - 1}
    with pytest.raises(ConnectorError, match="stale_device_snapshot"):
        service.ingest(uid, cid, older)
    assert service.read(uid, cid)[0]["data"]["steps"] == 100


def test_invalid_grant_and_quota_are_different():
    from hymio_backend.connectors.providers import request

    async def call(status, payload):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload))
        ) as client:
            return await request(client, "GET", "https://gmail.googleapis.com/synthetic")

    with pytest.raises(ConnectorError, match="reconnect_required"):
        asyncio.run(call(400, {"error": "invalid_grant"}))
    with pytest.raises(ConnectorError, match="upstream_rate_limited"):
        asyncio.run(call(403, {"error": {"errors": [{"reason": "rateLimitExceeded"}]}}))


def test_expired_lease_and_projection_failure_keep_work(setup):
    service, _, a, _, _ = setup
    uid = a["user_id"]
    cid = service.store.create(uid, "gmail")["id"]
    with service.store.transaction() as db:
        db.execute("update connections set next_sync=? where id=?", (time.time() - 1, cid))
    claimed = service.store.claim()
    with service.store.transaction() as db:
        db.execute("update connections set lease_until=0 where id=?", (cid,))
    with pytest.raises(ConnectorError, match="sync_superseded"):
        service.store.apply(
            uid,
            cid,
            [],
            {"history": "new"},
            lease=claimed["lease"],
            generation=claimed["generation"],
        )
    native_id = native(service, uid)["id"]
    service.ingest(uid, native_id, health())

    class FailedContext:
        def call(self, *args, **kwargs):
            raise RuntimeError("synthetic failure")

    service.context = FailedContext()
    service.project()
    assert service.store.list(uid)[1]["pending_count"] == 1


def test_dida_bounded_read_only_completed_tasks():
    from hymio_backend.connectors.providers import pull_dida

    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic"
        if request.url.path.endswith("/project"):
            return httpx.Response(200, json=[{"id": "p", "name": "Synthetic project"}])
        if request.url.path.endswith("/data"):
            return httpx.Response(200, json={"tasks": [{"id": "a", "title": "Pending"}]})
        assert request.url.path.endswith("/task/completed")
        assert request.method == "POST"
        assert json.loads(request.content)["projectIds"] == ["p"]
        return httpx.Response(200, json=[{"id": "b", "projectId": "p", "title": "Done"}])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            items, cursor = await pull_dida(client, "synthetic", {})
        assert [(item["external_id"], item["completed"]) for item in items] == [
            ("p:a", False),
            ("p:b", True),
        ]
        assert cursor == {"project_offset": 0}

    asyncio.run(run())
    assert len(requests) == 3
