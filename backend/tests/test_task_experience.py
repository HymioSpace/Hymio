import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hymio_backend.context.discovery import Discovery
from hymio_backend.session_store import SessionStore
from hymio_backend.tasks.service import TaskService
from hymio_backend.tasks.store import TaskStore


@pytest.fixture
def environment(tmp_path):
    settings = SimpleNamespace(database=tmp_path / "tasks.sqlite", nostalgia_connections_file=None)
    sessions = SessionStore(settings)
    tasks = TaskService(settings, TaskStore(sessions))
    return settings, sessions, tasks


def test_wait_is_idempotent_owner_scoped_and_cancel_invalidates_followup(environment):
    _, _, service = environment
    store = service.store
    task = store.capture(
        "u1",
        {
            "title": "Research",
            "objective": "Compare routes",
            "success_criteria": "Options",
            "intent_key": "routes",
        },
        "capture-1",
    )
    rid = task["runs"][0]["id"]
    due = time.time() + 120
    store.wait("u1", rid, "device", "Mac offline", "Check Mac availability", due, "wait-1")
    store.wait("u1", rid, "device", "Mac offline", "Check Mac availability", due, "wait-1")
    assert store.get("u1", task["id"])["runs"][0]["followup_version"] == 1
    with pytest.raises(ValueError):
        store.wait("u2", rid, "device", "Offline", "Check", due, "wait-2")
    with patch("hymio_backend.tasks.store.time.time", return_value=due + 1):
        assert len(store.followups()) == 1
        store.control("u1", task["id"], "cancel")
        assert not store.followups()


def test_opportunity_replay_and_acceptance_do_not_duplicate_tasks(environment):
    settings, sessions, service = environment
    discovery = Discovery(settings, sessions, service)
    proposal = {
        "id": "op-1",
        "key": "routes",
        "title": "Compare routes",
        "objective": "Research options",
        "success_criteria": "Sourced comparison",
        "reason": "Unresolved trip",
        "record_ids": ["1"],
    }
    event = {"id": "1", "type": "opportunity.proposed", "data": proposal}
    with patch.object(discovery.client, "call", return_value={"data": {"items": [event]}}):
        discovery.ingest("u1")
        discovery.ingest("u1")
    assert len(discovery.list("u1")) == 1
    assert not service.store.list("u1")
    first = discovery.accept("u1", "op-1")
    assert discovery.accept("u1", "op-1")["id"] == first["id"]
    assert first["source"] == "nostalgia"
    assert not discovery.list("u2")
    with pytest.raises(ValueError):
        discovery.accept("u2", "op-1")
    with sessions.transaction() as db:
        db.execute(
            "INSERT INTO task_opportunities(user_id,id,payload,created_at) VALUES(?,?,?,?)",
            ("u1", "op-2", json.dumps({**proposal, "id": "op-2"}), time.time()),
        )
    discovery.dismiss("u1", "op-2")
    with pytest.raises(ValueError):
        discovery.accept("u1", "op-2")


def test_continuation_keeps_one_request_and_cancellation_fences_it(environment):
    _, _, service = environment
    store = service.store
    task = store.capture(
        "u1",
        {
            "title": "Research",
            "objective": "Compare routes",
            "success_criteria": "Options",
            "intent_key": "routes",
        },
        "capture-1",
    )
    rid = task["runs"][0]["id"]
    store.wait("u1", rid, "user", "Choose route", "Select an option", None, "wait-1")
    store.request_continuation("u1", task["id"], "continue-1")
    store.request_continuation("u1", task["id"], "continue-2")
    assert store.continuations()[0]["resume_request_id"] == "continue-1"
    store.control("u1", task["id"], "cancel")
    assert not store.continuations()
    store.continued("u1", rid, "continue-1")
    assert store.get("u1", task["id"])["runs"][0]["status"] == "cancelled"


def test_new_background_task_starts_bound_delegation_without_main_wake(environment):
    from unittest.mock import AsyncMock

    _, _, service = environment
    task = service.store.create(
        "u1", {"title": "Research", "objective": "Compare routes", "success_criteria": "Report"}
    )
    run = service.store.claim_due()[0]
    service.oath = AsyncMock()
    asyncio.run(service.deliver(run))
    service.oath.assert_not_called()
    stored = service.store.get("u1", task["id"])["runs"][0]
    assert stored["status"] == "running" and stored["agent_id"] == "pending"
