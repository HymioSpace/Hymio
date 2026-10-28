
import pytest
from test_device_link import pair, stack  # noqa: F401, F811

from hymio_backend.devices.store import DeviceConflict


def test_nested_device_operations_keep_the_parent_lease(request):
    client, link = request.getfixturevalue("stack")
    paired, _ = pair(client)
    store = link.store
    user, device = "alice", paired["device_id"]
    store.claim(
        user, device, "shell", {"capability": "bash", "arguments": {"command": "compose"}}, 30
    )
    _, known = store.claim(
        user,
        device,
        "child",
        {
            "capability": "browser",
            "arguments": {"action": "snapshot"},
            "parent_invocation_id": "shell",
        },
        20,
    )
    assert known is None
    with pytest.raises(DeviceConflict):
        store.claim(
            user,
            device,
            "unrelated",
            {"capability": "computer", "arguments": {"action": "screenshot"}},
            10,
        )
    with pytest.raises(DeviceConflict):
        store.claim(
            user,
            device,
            "parallel-child",
            {
                "capability": "browser",
                "arguments": {"action": "snapshot"},
                "parent_invocation_id": "shell",
            },
            10,
        )
    store.finish(user, "shell", {"status": "succeeded"})
    with store.transaction() as db:
        assert (
            db.execute(
                "select invocation_id from device_locks where device_id=?", (device,)
            ).fetchone()[0]
            == "child"
        )
    store.finish(user, "child", {"status": "succeeded"})
    store.claim(
        user, device, "next", {"capability": "browser", "arguments": {"action": "snapshot"}}, 10
    )


def test_unrelated_and_cross_user_parents_are_rejected(request):
    client, link = request.getfixturevalue("stack")
    paired, _ = pair(client)
    store = link.store
    device = paired["device_id"]
    store.claim(
        "alice",
        device,
        "real",
        {"capability": "computer", "arguments": {"action": "screenshot"}},
        30,
    )
    with pytest.raises(DeviceConflict):
        store.claim(
            "alice",
            device,
            "nested",
            {
                "capability": "computer",
                "arguments": {"action": "screenshot"},
                "parent_invocation_id": "real",
            },
            10,
        )
    with pytest.raises(KeyError):
        store.claim(
            "bob",
            device,
            "bad",
            {
                "capability": "browser",
                "arguments": {"action": "snapshot"},
                "parent_invocation_id": "real",
            },
            10,
        )


def test_android_cannot_advertise_mac_browser_capability():
    from hymio_backend.devices.link import DeviceLink

    with pytest.raises(ValueError):
        DeviceLink.report({"capabilities": ["browser"]}, "personal_android")
    assert DeviceLink.report({"capabilities": ["browser", "bash"]})[0] == ["browser", "bash"]
