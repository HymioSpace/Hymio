import asyncio
from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

pytest.importorskip("nostalgia")
from nostalgia.dreaming import DreamScheduler
from test_context_integration import append, stack  # noqa: F401

from hymio_backend.context.admin import nostalgia_admin_routes
from hymio_backend.context.discovery import Discovery
from hymio_backend.server import bearer, body
from hymio_backend.tasks.service import TaskService
from hymio_backend.tasks.store import TaskStore


def test_committed_context_opportunity_reaches_authenticated_task_api(request):
    environment = request.getfixturevalue("stack")
    append(environment, "Compare two hiking routes for next month.", "source-1")

    class Provider:
        def propose(self, task):
            record = task["records"][0]
            return {
                "artifacts": [{"id": "_index", "content": "Trip planning", "links": []}],
                "record_states": [
                    {
                        "record_id": record["id"],
                        "processing_state": "noop",
                        "status": "active",
                        "reason": "Future planning",
                    }
                ],
                "opportunities": [
                    {
                        "key": "hiking-options",
                        "title": "Compare routes",
                        "objective": "Research walking routes",
                        "success_criteria": "Two options",
                        "reason": "Planning remains open",
                        "record_ids": [record["id"]],
                    }
                ],
            }

    app = environment.nostalgia
    scheduler = DreamScheduler(app.state.core.settings, app.state.store, app.state.core, Provider())
    assert scheduler.run_once()[0]["state"] == "committed"
    service = TaskService(environment.settings, TaskStore(environment.sessions))
    discovery = Discovery(environment.settings, environment.sessions, service)
    service.oath = AsyncMock(return_value={"accepted": True})
    asyncio.run(discovery.tick())
    asyncio.run(discovery.tick())
    assert service.oath.await_count == 1
    uid = environment.user.user_id
    suggestion = discovery.list(uid)[0]
    task = discovery.accept(uid, suggestion["id"])
    asyncio.run(service.deliver(service.store.claim_due()[0]))
    assert service.store.get(uid, task["id"])["runs"][0]["agent_id"] == "pending"
    environment.settings.admin_user_ids = (uid,)
    admin = Starlette(
        routes=nostalgia_admin_routes(
            environment.settings, environment.sessions, discovery, bearer, body
        )
    )
    with TestClient(admin) as client:
        assert client.get("/admin/api/nostalgia").status_code == 401
        headers = dict(environment.public.headers)
        status = client.get("/admin/api/nostalgia", headers=headers)
        assert status.status_code == 200
        assert status.json()["runtime"]["counts"]["records"] == 1
        profiles = status.json()["user_profiles"]
        assert [profile["user_id"] for profile in profiles] == [uid]
        with environment.sessions.transaction() as db:
            name = db.execute("SELECT name FROM users WHERE user_id=?", (uid,)).fetchone()[0]
        assert profiles[0]["username"] == name
        assert client.get("/admin/api/nostalgia?user_id=other", headers=headers).status_code == 400
