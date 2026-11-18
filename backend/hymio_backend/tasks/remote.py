"""Hymio only displays and delivers tasks; Oath owns their state and schedule."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..session_store import Unauthorized
from .credentials import issue

_log = logging.getLogger(__name__)


class RemoteTasks:
    def __init__(self, settings, sessions, notifications):
        self.settings, self.sessions, self.notifications = settings, sessions, notifications
        self.owner = "hymio-" + uuid.uuid4().hex
        with sessions.transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS task_delivery_inbox "
                "(delivery_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,"
                "payload TEXT NOT NULL,created_at REAL NOT NULL)"
            )
            columns = {r[1] for r in db.execute("PRAGMA table_info(task_delivery_inbox)")}
            if "ack_json" not in columns:
                db.execute(
                    "ALTER TABLE task_delivery_inbox ADD COLUMN ack_json TEXT NOT NULL DEFAULT '{}'"
                )
                db.execute(
                    "ALTER TABLE task_delivery_inbox ADD COLUMN acked INTEGER NOT NULL DEFAULT 0"
                )

    async def oath(self, uid, path, data, request_id=None):
        headers = {"Authorization": "Bearer " + issue(self.settings, uid), "X-Oath-User-Id": uid}
        if request_id:
            headers["Idempotency-Key"] = request_id
        async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
            result = await client.post(
                self.settings.oath_biz.rstrip("/") + path, json=data, headers=headers
            )
            result.raise_for_status()
            return result.json()

    async def get(self, uid, tid, *, detail=True):
        value = await self.oath(
            uid, "/tasks/get", {"task_id": tid, "view": "detail", "include_execution": detail}
        )
        t = value["task"]
        spec = value["spec"]
        run = value["run"]

        def stamp(v):
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() if v else None

        runs = []
        if run:
            runs = [
                {
                    "id": run["run_id"],
                    "status": run["status"],
                    "progress": run["progress"],
                    "result": (run["result"] or {}).get("summary", ""),
                    "phase": run["stage"],
                    "next_step": run.get("next_step") or run["wait_reason"] or "",
                    "wait_kind": run.get("wait_kind"),
                    "wait_reason": run["wait_reason"],
                    "resume_at": stamp(run["next_check_at"]),
                    "due_at": stamp(run.get("due_at")) or time.time(),
                    "started_at": stamp(run.get("started_at")),
                    "finished_at": stamp(run.get("finished_at")),
                    "agent_id": run.get("agent_id"),
                    "updates": [],
                }
            ]
        return {
            "id": t["task_id"],
            "revision": t["revision"],
            "state": t["lifecycle"],
            "needs_attention": t["needs_attention"],
            "title": t["title"],
            "objective": spec["objective"],
            "success_criteria": spec["acceptance"]["criteria"],
            "context": spec["context"],
            "plan": spec["plan"],
            "execution": value.get("execution", {}),
            "evidence": (run["result"] or {}).get("evidence", []) if run else [],
            "schedule": spec["trigger"],
            "source": "agent",
            "kind": "reminder" if spec["executor"]["kind"] == "program" else "task",
            "updated_at": stamp(t["updated_at"]),
            "next_due_at": stamp(t["next_due_at"]),
            "runs": runs,
            "for_user": True,
        }

    async def reconcile(self, uid):
        with self.sessions.transaction() as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT delivery_id,ack_json FROM task_delivery_inbox "
                    "WHERE user_id=? AND acked=0",
                    (uid,),
                )
            ]
        for row in rows:
            ack = json.loads(row["ack_json"])
            if not ack:
                continue
            await self.oath(uid, "/task-deliveries/ack", ack)
            with self.sessions.transaction() as db:
                db.execute(
                    "UPDATE task_delivery_inbox SET acked=1 WHERE delivery_id=?",
                    (row["delivery_id"],),
                )

    async def deliver(self, uid):
        await self.reconcile(uid)
        d = await self.oath(uid, "/task-deliveries/claim", {"owner": self.owner})
        if not d:
            return
        ack = {
            "delivery_id": d["delivery_id"],
            "owner": self.owner,
            "lease_token": d["lease_token"],
            "status": "accepted",
            "error": None,
            "receipt": {
                "provider_id": d["delivery_id"],
                "accepted_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        # The persisted inbox and acknowledgment survive bridge restarts together.
        with self.sessions.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO task_delivery_inbox"
                "(delivery_id,user_id,payload,created_at,ack_json) VALUES(?,?,?,?,?)",
                (
                    d["delivery_id"],
                    uid,
                    json.dumps(d["payload"], ensure_ascii=False),
                    time.time(),
                    json.dumps(ack),
                ),
            )
        await asyncio.to_thread(
            self.notifications.notify,
            uid,
            {"kind": "completion", "summary": d["payload"].get("text", "Task result")[:180]},
            d["delivery_id"],
        )
        await self.reconcile(uid)

    async def run(self):
        while True:
            with self.sessions.transaction() as db:
                users = [r[0] for r in db.execute("SELECT user_id FROM users")]
            for uid in users:
                try:
                    await self.deliver(uid)
                except Exception as exc:
                    _log.warning("Task delivery deferred: %s", type(exc).__name__)
            await asyncio.sleep(2)


def remote_task_routes(settings, sessions, service, bearer, body):
    async def endpoint(request):
        try:
            if request.headers.get("origin") and request.headers["origin"] not in settings.origins:
                return JSONResponse({"error": "origin_denied"}, 403)
            identity = await asyncio.to_thread(sessions.verify, bearer(request))
            uid = identity["user_id"]
            data = await body(request, limit=131072) if request.method == "POST" else {}
            action = data.pop("action", "list")
            if action == "list":
                page = await service.oath(uid, "/tasks/list", {"lifecycle": "all", "limit": 100})
                items = await asyncio.gather(
                    *(service.get(uid, t["task_id"], detail=False) for t in page["items"])
                )
                return JSONResponse({"tasks": items})
            if action == "get":
                return JSONResponse(await service.get(uid, data["task_id"]))
            if action not in {"pause", "resume", "cancel"}:
                return JSONResponse(
                    {"error": "agent_managed", "message": "请在对话中创建或修改任务。"}, 400
                )
            original = await service.get(uid, data["task_id"])
            await service.oath(
                uid,
                "/tasks/" + action,
                {
                    "task_id": data["task_id"],
                    "expected_revision": data.get("expected_revision", original["revision"]),
                    "reason": "User selected " + action,
                },
                request.headers.get("idempotency-key") or uuid.uuid4().hex,
            )
            return JSONResponse(await service.get(uid, data["task_id"]))
        except Unauthorized:
            return JSONResponse({"error": "unauthorized"}, 401)
        except (ValueError, KeyError):
            return JSONResponse({"error": "bad_request"}, 400)
        except httpx.HTTPError:
            return JSONResponse({"error": "task_service_unavailable"}, 503)

    return [Route("/tasks", endpoint, methods=["GET", "POST"])]
