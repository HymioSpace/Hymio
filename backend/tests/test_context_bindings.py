import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from hymio_backend.context.bindings import ContextBindings
from hymio_backend.context.client import NostalgiaClient


def test_new_user_is_provisioned_once_and_resolved_dynamically(tmp_path):
    service = tmp_path / "service-token"
    service.write_text("internal-service-token")
    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        service_token_file=service,
        nostalgia_connections_file=None,
        nostalgia_url="http://nostalgia:8000",
    )
    bindings = ContextBindings(settings)
    response = httpx.Response(
        200,
        request=httpx.Request("PUT", "http://nostalgia:8000/v1/admin/tokens/user-1"),
    )
    with patch("hymio_backend.context.bindings.httpx.put", return_value=response) as provision:
        assert bindings.ensure("user-1")
        assert bindings.ensure("user-1")
    assert provision.call_count == 1
    url, token = bindings.get("user-1")
    assert url == "http://nostalgia:8000"
    assert len(token) >= 16
    assert NostalgiaClient(settings).connection("user-1") == (url, token)


def test_retry_reuses_the_same_credential_and_context_access_repairs_a_missing_binding(
    tmp_path,
):
    service = tmp_path / "service-token"
    service.write_text("internal-service-token")
    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        service_token_file=service,
        nostalgia_connections_file=None,
        nostalgia_url="http://nostalgia:8000",
    )
    response = httpx.Response(
        200,
        request=httpx.Request("PUT", "http://nostalgia:8000/v1/admin/tokens/user-1"),
    )
    sent_tokens = []

    def provision(_url, **kwargs):
        sent_tokens.append(kwargs["json"]["token"])
        return response

    with patch("hymio_backend.context.bindings.httpx.put", side_effect=provision):
        bindings = ContextBindings(settings)
        assert bindings.ensure("user-1")
        first = bindings.get("user-1")
        with bindings._connect() as db:
            db.execute("DELETE FROM context_bindings WHERE user_id='user-1'")
        assert NostalgiaClient(settings).connection("user-1") == first
    assert sent_tokens[0] == sent_tokens[1]


def test_legacy_static_binding_is_migrated_to_an_encrypted_dynamic_binding(tmp_path):
    service = tmp_path / "service-token"
    service.write_text("internal-service-token")
    legacy_token = "legacy-token-1234567890"
    (tmp_path / "legacy.token").write_text(legacy_token)
    connections = tmp_path / "connections.json"
    connections.write_text(
        json.dumps(
            {
                "users": {
                    "user-1": {
                        "url": "http://legacy-nostalgia:8000",
                        "token_file": "legacy.token",
                    }
                }
            }
        )
    )
    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        service_token_file=service,
        nostalgia_connections_file=connections,
        nostalgia_url="http://nostalgia:8000",
    )
    response = httpx.Response(
        200,
        request=httpx.Request(
            "PUT", "http://legacy-nostalgia:8000/v1/admin/tokens/user-1"
        ),
    )
    with patch(
        "hymio_backend.context.bindings.httpx.put", return_value=response
    ) as provision:
        bindings = ContextBindings(settings)
        assert bindings.ensure("user-1")
    assert provision.call_args.args[0] == "http://legacy-nostalgia:8000/v1/admin/tokens/user-1"
    assert provision.call_args.kwargs["json"]["token"] == legacy_token
    assert bindings.get("user-1") == ("http://legacy-nostalgia:8000", legacy_token)


def test_provisioning_failure_does_not_create_a_binding(tmp_path):
    service = tmp_path / "service-token"
    service.write_text("internal-service-token")
    settings = SimpleNamespace(
        database=tmp_path / "hymio.sqlite",
        service_token_file=service,
        nostalgia_connections_file=None,
        nostalgia_url="http://nostalgia:8000",
    )
    bindings = ContextBindings(settings)
    request = httpx.Request("PUT", "http://nostalgia:8000/v1/admin/tokens/user-1")
    failure = httpx.Response(503, request=request)
    with patch("hymio_backend.context.bindings.httpx.put", return_value=failure):
        try:
            bindings.ensure("user-1")
        except Exception as error:
            assert type(error).__name__ == "ContextBindingError"
        else:
            raise AssertionError("Provisioning failure was accepted")
    assert bindings.get("user-1") is None
