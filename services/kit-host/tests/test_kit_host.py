from pathlib import Path

from starlette.testclient import TestClient

from kit_host.app import build_app
from kit_host.service import KitsService


def app_for(tmp_path):
    token = "kit-host-token-" + "x" * 40
    service = KitsService(
        tmp_path / "kits.sqlite3",
        Path(__file__).resolve().parents[3] / "kits",
    )
    return TestClient(build_app(service, token)), token, service


def test_catalog_install_app_and_idempotent_write(tmp_path):
    client, token, _ = app_for(tmp_path)
    headers = {"Authorization": "Bearer " + token}
    user = "alice"
    catalog = client.post("/v1/catalog", headers=headers, json={"user_id": user}).json()
    assert catalog["kits"][0]["installed"] is False
    assert (
        client.post(
            "/v1/app", headers=headers, json={"user_id": user, "kit_id": "hymio.ledger"}
        ).status_code
        == 409
    )
    client.post(
        "/v1/install",
        headers=headers,
        json={"user_id": user, "kit_id": "hymio.ledger"},
    ).raise_for_status()
    value = client.post(
        "/v1/app", headers=headers, json={"user_id": user, "kit_id": "hymio.ledger"}
    ).json()
    assert "HymioKit.call" in value["html"]

    body = {
        "user_id": user,
        "kit_id": "hymio.ledger",
        "operation": "entries.create",
        "arguments": {"amount": 35, "category": "food", "note": "午饭"},
        "idempotency_key": "same-entry",
    }
    first = client.post("/v1/invoke", headers=headers, json=body).json()
    second = client.post("/v1/invoke", headers=headers, json=body).json()
    assert first["result"]["entry"]["id"] == second["result"]["entry"]["id"]
    assert second["result"]["summary"]["total"] == 35
    recent = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            "user_id": user,
            "kit_id": "hymio.ledger",
            "operation": "entries.list",
            "arguments": {},
        },
    ).json()
    assert recent["result"]["items"][0]["amount"] == 35
    assert "amount_minor" not in recent["result"]["items"][0]


def test_host_rejects_unauthenticated_and_isolates_users(tmp_path):
    client, token, _ = app_for(tmp_path)
    headers = {"Authorization": "Bearer " + token}
    assert client.post("/v1/catalog", json={"user_id": "alice"}).status_code == 401
    client.post(
        "/v1/install",
        headers=headers,
        json={"user_id": "alice", "kit_id": "hymio.ledger"},
    ).raise_for_status()
    bob = client.post(
        "/v1/catalog", headers=headers, json={"user_id": "bob"}
    ).json()["kits"][0]
    assert bob["installed"] is False
    assert (
        client.post(
            "/v1/app", headers=headers, json={"user_id": "bob", "kit_id": "hymio.ledger"}
        ).status_code
        == 409
    )


def test_optional_preview_and_uninstall_preserve_data(tmp_path):
    client, token, service = app_for(tmp_path)
    headers = {"Authorization": "Bearer " + token}
    client.post(
        "/v1/install",
        headers=headers,
        json={"user_id": "alice", "kit_id": "hymio.ledger"},
    ).raise_for_status()
    preview = client.post(
        "/v1/catalog", headers=headers, json={"user_id": "alice"}
    ).json()["kits"][0]["preview"]
    assert preview["label"] == "本月支出"
    service.registry.get("hymio.ledger")["preview"] = False
    generic = client.post(
        "/v1/catalog", headers=headers, json={"user_id": "alice"}
    ).json()["kits"][0]
    assert "preview" not in generic
    service.registry.get("hymio.ledger")["preview"] = True
    client.post(
        "/v1/uninstall",
        headers=headers,
        json={"user_id": "alice", "kit_id": "hymio.ledger"},
    ).raise_for_status()
    client.post(
        "/v1/install",
        headers=headers,
        json={"user_id": "alice", "kit_id": "hymio.ledger"},
    ).raise_for_status()
    assert (
        client.post(
            "/v1/app", headers=headers, json={"user_id": "alice", "kit_id": "hymio.ledger"}
        ).status_code
        == 200
    )


def test_generated_app_is_owned_installed_and_agent_visible(tmp_path):
    client, token, _ = app_for(tmp_path)
    headers = {"Authorization": "Bearer " + token}
    generated = client.post(
        "/v1/generate",
        headers=headers,
        json={
            "user_id": "alice",
            "spec": {
                "name": "饮水记录",
                "tagline": "记下每天喝了多少水。",
                "category": "生活",
                "item_label": "杯水",
                "accent": "blue",
                "app_html": "<!doctype html><html><body><h1>饮水记录</h1></body></html>",
                "fields": [
                    {
                        "key": "amount",
                        "label": "杯数",
                        "type": "number",
                        "required": True,
                    }
                ],
            },
        },
    )
    generated.raise_for_status()
    kit = generated.json()
    assert kit["installed"] is True
    assert kit["id"].startswith("user.")
    assert {item["id"] for item in kit["operations"]} == {
        "items.create",
        "items.list",
        "summary",
    }
    result = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            "user_id": "alice",
            "kit_id": kit["id"],
            "operation": "items.create",
            "arguments": {"amount": 5},
            "idempotency_key": "water-1",
        },
    )
    result.raise_for_status()
    assert result.json()["result"]["count"] == 1
    app = client.post(
        "/v1/app", headers=headers, json={"user_id": "alice", "kit_id": kit["id"]}
    ).json()
    assert "饮水记录" in app["html"]
    assert app["bridge"] == "hymio.kit.bridge/v1"
    context = client.post(
        "/v1/agent-context", headers=headers, json={"user_id": "alice"}
    ).json()
    assert kit["id"] in context["content"]
    assert "items.create" in context["content"]
    assert len(context["content"]) <= 7000
    other = client.post(
        "/v1/catalog", headers=headers, json={"user_id": "bob"}
    ).json()["kits"]
    assert kit["id"] not in {item["id"] for item in other}


def test_static_generated_app_can_omit_fields_and_has_no_agent_operations(tmp_path):
    client, token, _ = app_for(tmp_path)
    headers = {"Authorization": "Bearer " + token}
    result = client.post(
        "/v1/generate",
        headers=headers,
        json={
            "user_id": "alice",
            "spec": {
                "name": "呼吸练习",
                "tagline": "跟着节奏呼吸一分钟。",
                "app_html": "<!doctype html><html><body>吸气，呼气。</body></html>",
            },
        },
    )
    result.raise_for_status()
    kit = result.json()
    assert kit["operations"] == []
    context = client.post(
        "/v1/agent-context", headers=headers, json={"user_id": "alice"}
    ).json()
    assert kit["id"] in context["content"]
    assert '"operations":[]' in context["content"]
    assert (
        client.post(
            "/v1/invoke",
            headers=headers,
            json={
                "user_id": "alice",
                "kit_id": kit["id"],
                "operation": "summary",
                "arguments": {},
                "idempotency_key": "static-no-api",
            },
        ).status_code
        == 404
    )
