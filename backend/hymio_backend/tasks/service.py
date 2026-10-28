import asyncio
import hashlib
import logging
import time

import httpx

from .credentials import issue

_log = logging.getLogger(__name__)


class TaskService:
    def __init__(self, settings, store, notifications=None):
        self.settings, self.store, self.notifications = settings, store, notifications
        self.slots = asyncio.Semaphore(4)

    async def oath(self, uid, path, data):
        async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
            response = await client.post(
                self.settings.oath_biz.rstrip("/") + path,
                json=data,
                headers={
                    "Authorization": "Bearer " + issue(self.settings, uid),
                    "X-Oath-User-Id": uid,
                },
            )
            response.raise_for_status()
            return response.json()

    async def delegate(self, uid, rid):
        # Persist intent before the network call. Reconciliation retries the same request_id.
        await asyncio.to_thread(self.store.reserve_delegation, uid, rid)
        return {"run_id": rid, "delegation": "requested"}

    async def reconcile(self):
        runs = await asyncio.to_thread(self.store.linked)
        await asyncio.gather(*(self.reconcile_one(run) for run in runs))

    async def reconcile_one(self, run):
        async with self.slots:
            await self.sync_run(run)

    async def sync_run(self, run):
        uid, rid = run["user_id"], run["id"]
        try:
            if run["agent_id"] == "pending":
                try:
                    child = await self.oath(uid, "/subagents/get", {"request_id": rid})
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 400:
                        raise
                    if run["status"] in {"cancelled", "succeeded", "failed"}:
                        if time.time() - (run["finished_at"] or time.time()) > 60:
                            await asyncio.to_thread(self.store.synced, uid, rid)
                        return
                    task = await asyncio.to_thread(self.store.get, uid, run["task_id"])
                    child = await self.oath(
                        uid,
                        "/subagents/spawn",
                        {
                            "request_id": rid,
                            "title": task["title"],
                            "objective": task["objective"],
                            "success_criteria": task["success_criteria"],
                        },
                    )
                await asyncio.to_thread(self.store.link, uid, rid, child["agent_id"])
            else:
                child = await self.oath(uid, "/subagents/get", {"agent_id": run["agent_id"]})
            if run["status"] in {"cancelled", "succeeded", "failed"}:
                if child["status"] == "running":
                    await self.oath(uid, "/subagents/cancel", {"agent_id": child["agent_id"]})
                await asyncio.to_thread(self.store.synced, uid, rid)
                return
            for note in child["notes"]:
                await asyncio.to_thread(
                    self.store.update_run,
                    uid,
                    rid,
                    "running",
                    note["content"],
                    "child:" + note["note_id"],
                )
            if child["status"] != "running":
                status = "succeeded" if child["status"] == "succeeded" else "failed"
                await asyncio.to_thread(
                    self.store.update_run,
                    uid,
                    rid,
                    status,
                    child["result"] or child["status"],
                    "child:terminal",
                )
                await asyncio.to_thread(self.store.synced, uid, rid)
        except Exception as exc:
            _log.debug("Delegation reconciliation deferred: %s", type(exc).__name__)
        finally:
            await asyncio.to_thread(self.store.sync_later, uid, rid)

    async def reconcile_main(self, run):
        uid, rid = run["user_id"], run["id"]
        async with self.slots:
            try:
                result = await self.oath(
                    uid, "/executions/get", {"invocation_id": run["start_invocation_id"]}
                )
                if result["status"] == "running":
                    return
                if (
                    result["status"] == "completed"
                    and run["kind"] == "reminder"
                    and result["content"].strip()
                ):
                    await asyncio.to_thread(
                        self.store.update_run,
                        uid,
                        rid,
                        "succeeded",
                        result["content"],
                        "reconcile:reply",
                    )
                else:
                    await asyncio.to_thread(
                        self.store.update_run,
                        uid,
                        rid,
                        "blocked",
                        "执行已结束，尚未记录明确结果。\n" + result.get("content", "")[:6000],
                        "reconcile:closure:"
                        + hashlib.sha256(run["start_invocation_id"].encode()).hexdigest()[:16],
                        notice="执行已结束，但尚未确认任务结果。请核对后 complete/fail/block；"
                        "不要重复外部操作。",
                    )
            except (httpx.HTTPError, ValueError):
                _log.debug("Main task reconciliation deferred")

    async def notify(self, run):
        async with self.slots:
            try:
                await self.oath(
                    run["user_id"],
                    "/events",
                    {
                        "type": "app.task.reconciled",
                        "event_id": "task-reconciled:"
                        + run["id"]
                        + ":"
                        + str(run["notice_version"]),
                        "payload": {
                            "task_id": run["task_id"],
                            "run_id": run["id"],
                            "status": run["status"],
                            "notice": run["notice"],
                            "instruction": "This is a status reconciliation, not a new task. "
                            "Expired work must not execute. "
                            "Never retry external effects without evidence. "
                            "Inform the user when useful.",
                        },
                    },
                )
                await asyncio.to_thread(
                    self.store.notice_sent, run["user_id"], run["id"], run["notice_version"]
                )
            except httpx.HTTPError:
                _log.debug("Task reconciliation notice deferred")

    async def tick(self):
        await asyncio.to_thread(self.store.reconcile_time)
        main = await asyncio.to_thread(self.store.main_runs)
        await asyncio.gather(*(self.reconcile_main(run) for run in main))
        notices = await asyncio.to_thread(self.store.notices)
        await asyncio.gather(*(self.notify(run) for run in notices))
        runs = await asyncio.to_thread(self.store.claim_due)
        await asyncio.gather(*(self.deliver_one(run) for run in runs))
        await self.reconcile()
        if self.notifications is not None:
            for run in await asyncio.to_thread(self.store.notification_runs):
                kind = (
                    "attention"
                    if run["status"] in {"blocked", "failed", "expired"}
                    else "completion"
                )
                await asyncio.to_thread(
                    self.notifications.notify,
                    run["user_id"],
                    {
                        "kind": kind,
                        "summary": run["title"],
                        "task_id": run["task_id"],
                        "run_id": run["id"],
                    },
                    "task-rule:" + run["id"] + ":" + run["status"],
                )

    async def deliver_one(self, run):
        async with self.slots:
            await self.deliver(run)

    async def deliver(self, run):
        try:
            # A cancellation between this read and delivery is rejected by tasks.start.
            current = await asyncio.to_thread(self.store.get, run["user_id"], run["task_id"])
            occurrence = next((r for r in current["runs"] if r["id"] == run["id"]), None)
            if (
                current["state"] != "active"
                or current["generation"] != run["generation"]
                or not occurrence
                or occurrence["status"] not in {"scheduled", "delivering"}
                or time.time() > occurrence["expires_at"]
            ):
                return
            await self.oath(
                run["user_id"],
                "/events",
                {
                    "type": "app.task.due",
                    "event_id": "task:" + run["id"],
                    "payload": {
                        "task_id": run["task_id"],
                        "run_id": run["id"],
                        "title": run["task"]["title"],
                        "kind": run["task"]["kind"],
                        "expires_at": run["expires_at"],
                        "instruction": "Call tasks(action=start) with this run_id before acting. "
                        "If cancelled, do"
                        " nothing. For a reminder: deliver the reminder text, "
                        "then call tasks with action=complete "
                        "with that text before the final reply. "
                        "For other work: record progress and close with complete/fail/block "
                        "before giving the final reply. "
                        "Never leave a started run without a recorded outcome.",
                    },
                },
            )
            await asyncio.to_thread(self.store.delivered, run["user_id"], run["id"])
        except Exception as exc:
            _log.warning("Task delivery deferred: %s", type(exc).__name__)

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception as exc:
                _log.warning("Task scheduler recovering: %s", type(exc).__name__)
            await asyncio.sleep(5)
