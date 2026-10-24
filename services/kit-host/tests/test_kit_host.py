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
    assert first["effect"] == "write"
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
    assert recent["effect"] == "read"
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
    assert {
        "items.create",
        "items.list",
        "summary",
        "app.get_source",
        "app.update",
        "app.delete",
    } == {item["id"] for item in kit["operations"]}
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
    source = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            "user_id": "alice",
            "kit_id": kit["id"],
            "operation": "app.get_source",
            "arguments": {"offset": 0, "limit": 20},
        },
    ).json()
    assert source["effect"] == "read"
    assert source["result"]["complete"] is False
    assert source["result"]["next_offset"] == 20
    first_chunk = source["result"]["app_html"]
    remainder = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            "user_id": "alice",
            "kit_id": kit["id"],
            "operation": "app.get_source",
            "arguments": {"offset": source["result"]["next_offset"]},
        },
    ).json()["result"]
    assert remainder["complete"] is True
    assert first_chunk + remainder["app_html"] == (
        "<!doctype html><html><body><h1>饮水记录</h1></body></html>"
    )
    revision = remainder["source_revision"]

    update = {
        "user_id": "alice",
        "kit_id": kit["id"],
        "operation": "app.update",
        "arguments": {
            "name": "每日饮水",
            "expected_revision": revision,
            "replacements": [
                {"old": "<h1>饮水记录</h1>", "new": "<h1>每日饮水</h1>"}
            ],
        },
        "idempotency_key": "update-water",
    }
    first_update = client.post("/v1/invoke", headers=headers, json=update).json()
    second_update = client.post("/v1/invoke", headers=headers, json=update).json()
    assert first_update == second_update
    assert first_update["effect"] == "write"
    assert first_update["result"]["name"] == "每日饮水"
    stale = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            **update,
            "arguments": {
                **update["arguments"],
                "replacements": [{"old": "每日饮水", "new": "再次修改"}],
            },
            "idempotency_key": "stale-water",
        },
    )
    assert stale.status_code == 400
    updated_source = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            "user_id": "alice",
            "kit_id": kit["id"],
            "operation": "app.get_source",
            "arguments": {},
        },
    ).json()
    assert updated_source["result"]["complete"] is True
    assert "每日饮水" in updated_source["result"]["app_html"]
    assert "<h1>饮水记录</h1>" not in updated_source["result"]["app_html"]

    context = client.post(
        "/v1/agent-context", headers=headers, json={"user_id": "alice"}
    ).json()
    assert kit["id"] in context["content"]
    assert "items.create" in context["content"]
    assert "app.get_source" in context["content"]
    assert "app.update" in context["content"]
    assert "app.delete" in context["content"]
    assert len(context["content"]) <= 7000
    other = client.post(
        "/v1/catalog", headers=headers, json={"user_id": "bob"}
    ).json()["kits"]
    assert kit["id"] not in {item["id"] for item in other}

    deletion = {
        "user_id": "alice",
        "kit_id": kit["id"],
        "operation": "app.delete",
        "arguments": {"confirmation": "DELETE"},
        "idempotency_key": "delete-water",
    }
    assert client.post("/v1/invoke", headers=headers, json=deletion).json()["result"] == {
        "deleted": True
    }
    assert client.post("/v1/invoke", headers=headers, json=deletion).json()["result"] == {
        "deleted": True
    }
    assert kit["id"] not in {
        item["id"]
        for item in client.post(
            "/v1/catalog", headers=headers, json={"user_id": "alice"}
        ).json()["kits"]
    }


def test_static_generated_app_can_omit_fields_and_has_no_business_operations(tmp_path):
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
    assert {item["id"] for item in kit["operations"]} == {
        "app.get_source",
        "app.update",
        "app.delete",
    }
    context = client.post(
        "/v1/agent-context", headers=headers, json={"user_id": "alice"}
    ).json()
    assert kit["id"] in context["content"]
    assert "app.get_source" in context["content"]
    assert "items.create" not in context["content"]
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


def test_react_python_project_build_publish_and_edit(tmp_path):
    client, token, _ = app_for(tmp_path)
    headers = {"Authorization": "Bearer " + token}
    created = client.post(
        "/v1/project/create",
        headers=headers,
        json={
            "user_id": "alice",
            "spec": {
                "name": "饮水记录",
                "tagline": "每天喝了多少，一眼就知道。",
                "description": "记录饮水量并查看最近记录。",
                "category": "生活",
                "item_label": "杯水",
                "accent": "blue",
                "fields": [
                    {
                        "key": "amount",
                        "label": "杯数",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "key": "note",
                        "label": "备注",
                        "type": "text",
                    },
                ],
            },
        },
    ).json()
    assert created["status"] == "draft"
    kit_id = created["kit_id"]
    agent_id = "a" * 32
    client.post(
        "/v1/project/bind-agent",
        headers=headers,
        json={"user_id": "alice", "kit_id": kit_id, "agent_id": agent_id},
    ).raise_for_status()
    context = client.post(
        "/v1/dev/context",
        headers=headers,
        json={"user_id": "alice", "agent_id": agent_id},
    ).json()
    assert "web/src/App.jsx" in context["tree"]
    assert "server/main.py" in context["tree"]

    source = client.post(
        "/v1/dev",
        headers=headers,
        json={
            "user_id": "alice",
            "agent_id": agent_id,
            "dev_action": "read",
            "arguments": {"path": "web/src/App.jsx", "limit": 3000},
        },
    ).json()
    assert source["source_revision"] == created["source_revision"]
    assert source["content"]

    revision = source["source_revision"]
    patch = client.post(
        "/v1/dev",
        headers=headers,
        json={
            "user_id": "alice",
            "agent_id": agent_id,
            "dev_action": "patch",
            "arguments": {
                "expected_revision": revision,
                "changes": [
                    {
                        "path": "web/src/App.jsx",
                        "old": "<h1>{DISPLAY.name}</h1>",
                        "new": "<h1>今日饮水</h1>",
                    }
                ],
            },
            "idempotency_key": "patch-water-1",
        },
    )
    patch.raise_for_status()
    revision = patch.json()["source_revision"]
    checked = client.post(
        "/v1/dev",
        headers=headers,
        json={
            "user_id": "alice",
            "agent_id": agent_id,
            "dev_action": "check",
            "arguments": {},
        },
    ).json()
    assert checked["ok"] is True, checked
    published = client.post(
        "/v1/dev",
        headers=headers,
        json={
            "user_id": "alice",
            "agent_id": agent_id,
            "dev_action": "publish",
            "arguments": {
                "expected_revision": revision,
                "summary": "完成第一版饮水页面",
            },
            "idempotency_key": "publish-water-1",
        },
    )
    published.raise_for_status()
    assert published.json()["installed"] is True
    assert "react" not in published.json()
    app = client.post(
        "/v1/app",
        headers=headers,
        json={"user_id": "alice", "kit_id": kit_id},
    ).json()
    assert "html" in app, app
    assert 'id="root"' in app["html"]
    patched_source = client.post(
        "/v1/dev",
        headers=headers,
        json={
            "user_id": "alice",
            "agent_id": agent_id,
            "dev_action": "read",
            "arguments": {"path": "web/src/App.jsx", "limit": 3000},
        },
    ).json()
    assert "今日饮水" in patched_source["content"]
    written = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            "user_id": "alice",
            "kit_id": kit_id,
            "operation": "items.create",
            "arguments": {"amount": 3, "note": "上午"},
            "idempotency_key": "water-python-1",
        },
    )
    assert written.is_success, written.text
    assert written.json()["result"]["count"] == 1
    listed = client.post(
        "/v1/invoke",
        headers=headers,
        json={
            "user_id": "alice",
            "kit_id": kit_id,
            "operation": "items.list",
            "arguments": {},
        },
    ).json()
    assert listed["result"]["items"][0]["data"] == {"amount": 3, "note": "上午"}

    client.post(
        "/v1/editor/message",
        headers=headers,
        json={
            "user_id": "alice",
            "kit_id": kit_id,
            "message_id": "message-1",
            "author": "user",
            "content": "让标题更有呼吸感",
        },
    ).raise_for_status()
    editor = client.post(
        "/v1/editor",
        headers=headers,
        json={"user_id": "alice", "kit_id": kit_id},
    ).json()
    assert editor["status"] == "published"
    assert editor["messages"][0]["author"] == "user"
    assert editor["changes"][0]["summary"] == "完成第一版饮水页面"
