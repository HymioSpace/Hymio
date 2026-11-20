import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hymio_backend.session_store import SessionStore
from hymio_backend.tasks.remote import RemoteTasks


@pytest.fixture
def remote(tmp_path):
    settings = SimpleNamespace(database=tmp_path / "tasks.sqlite", oath_biz="http://oath.invalid")
    sessions = SessionStore(settings)
    return RemoteTasks(settings, sessions, SimpleNamespace())


def task(task_id, state):
    return {
        "id": task_id,
        "state": state,
        "runs": [{"id": f"run-{task_id}", "status": state, "result": ""}],
    }


def test_archive_lists_only_closed_tasks_and_can_hide_one(remote):
    active, done, cancelled = task("active", "active"), task("done", "closed"), task(
        "cancelled", "closed"
    )
    items = {
        active["id"]: active,
        done["id"]: done,
        cancelled["id"]: cancelled,
    }
    remote.oath = AsyncMock(return_value={"items": [{"task_id": key} for key in items]})
    remote.get = AsyncMock(side_effect=lambda _uid, tid, detail=False: items[tid])

    current = asyncio.run(remote.visible("u1"))
    archive = asyncio.run(remote.visible("u1", archive=True))
    assert [item["id"] for item in current] == ["active"]
    assert {item["id"] for item in archive} == {"done", "cancelled"}

    asyncio.run(remote.hide_archived("u1", "done"))
    assert [item["id"] for item in asyncio.run(remote.visible("u1", archive=True))] == [
        "cancelled"
    ]
    with pytest.raises(ValueError):
        asyncio.run(remote.hide_archived("u1", "active"))


def test_archive_hidden_is_owner_scoped_and_idempotent(remote):
    closed = task("done", "closed")
    remote.oath = AsyncMock(
        side_effect=lambda uid, _path, _payload: (
            {"items": [{"task_id": "done"}]} if uid == "u1" else {"items": []}
        )
    )
    remote.get = AsyncMock(return_value=closed)
    first = asyncio.run(remote.hide_archived("u1", "done"))
    second = asyncio.run(remote.hide_archived("u1", "done"))
    assert first["hidden"] is True and second["hidden"] is True
    assert asyncio.run(remote.visible("u2", archive=True)) == []
