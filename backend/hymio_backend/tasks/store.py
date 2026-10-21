import json
import time
import uuid

from .schedule import next_due, normalize
from .schema import initialize

LIVE = {"scheduled", "delivering", "ready", "running", "blocked"}
TERMINAL = {"succeeded", "failed", "cancelled", "expired"}


class TaskStore:
    def __init__(self, sessions):
        self.transaction = sessions.transaction
        with self.transaction() as db:
            initialize(db)

    def _task(self, db, uid, tid):
        row = db.execute("SELECT * FROM tasks WHERE user_id=? AND id=?", (uid, tid)).fetchone()
        if not row:
            raise ValueError("Task not found")
        return row

    def _run(self, db, uid, rid):
        row = db.execute("SELECT * FROM task_runs WHERE user_id=? AND id=?", (uid, rid)).fetchone()
        if not row:
            raise ValueError("Run not found")
        return row

    def _plan(self, db, task, *, now=None, request_id=None):
        rid = uuid.uuid4().hex
        at = time.time() if now is None else now
        schedule = json.loads(task["schedule"])
        db.execute(
            "INSERT INTO "
            "task_runs(id,task_id,user_id,generation,due_at,status,request_id,created_at)"
            " VALUES(?,?,?,?,?,'scheduled',?,?)",
            (
                rid,
                task["id"],
                task["user_id"],
                task["generation"],
                next_due(schedule, at),
                request_id,
                time.time(),
            ),
        )
        db.execute(
            "UPDATE task_runs SET expires_at=due_at+?,heartbeat_at=? WHERE id=?",
            (schedule.get("grace_seconds", 900), time.time(), rid),
        )
        return rid

    def _view(self, db, row, *, summary=False):
        task = dict(row)
        task["schedule"] = json.loads(task["schedule"])
        if summary:
            task["objective"] = task["objective"][:300]
            task["success_criteria"] = task["success_criteria"][:300]
        task["runs"] = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM task_runs WHERE task_id=? ORDER BY created_at DESC LIMIT ?",
                (row["id"], 1 if summary else 10),
            )
        ]
        for run in task["runs"]:
            run.pop("request_id", None)
            run.pop("lease_until", None)
            run.pop("reconciled", None)
            for key in (
                "start_invocation_id",
                "notice",
                "notice_sent",
                "notice_version",
                "intervention_count",
                "heartbeat_at",
            ):
                run.pop(key, None)
            if summary:
                run["result"] = run["result"][:600]
                run["progress"] = run["progress"][:600]
                run["updates"] = []
                continue
            run["updates"] = [
                dict(r)
                for r in db.execute(
                    "SELECT note_id,content,created_at,status,phase FROM task_updates WHERE "
                    "run_id=? ORDER BY id DESC LIMIT 20",
                    (run["id"],),
                )
            ][::-1]
        return task

    def list(self, uid):
        with self.transaction() as db:
            return [
                self._view(db, r, summary=True)
                for r in db.execute(
                    "SELECT * FROM tasks WHERE user_id=? AND state!='archived' ORDER "
                    "BY updated_at DESC LIMIT 100",
                    (uid,),
                )
            ]

    def get(self, uid, tid):
        with self.transaction() as db:
            return self._view(db, self._task(db, uid, tid))

    def capture(self, uid, data, request_id=None):
        """Record work already admitted by the conversation, without dispatching it again."""
        key = data.get("intent_key")
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 160:
            raise ValueError("A stable intent_key is required")
        if data.get("schedule"):
            raise ValueError("Capture does not schedule work; use create for future work")
        return self.create(uid, data, request_id, captured=True)

    def create(self, uid, data, request_id=None, *, captured=False):
        if request_id is not None and (
            not isinstance(request_id, str) or not 1 <= len(request_id) <= 256
        ):
            raise ValueError("Invalid request identity")
        fields = {k: data.get(k, "") for k in ("title", "objective", "success_criteria")}
        if any(not isinstance(v, str) for v in fields.values()):
            raise ValueError("Task descriptions must be strings")
        fields = {k: v.strip() for k, v in fields.items()}
        if any(not v or len(v) > 10000 for v in fields.values()) or len(fields["title"]) > 160:
            raise ValueError("Title, objective and success criteria required")
        kind = data.get("kind", "task")
        if kind not in {"task", "reminder"}:
            raise ValueError("Invalid task kind")
        schedule = normalize(data.get("schedule", {"mode": "now"}))
        key = data["intent_key"].strip() if captured else None
        status = data.get("status", "running") if captured else "scheduled"
        if captured and status not in {"running", "blocked", "succeeded"}:
            raise ValueError("Invalid capture status")
        content = data.get("content", "") if captured else ""
        phase, next_step = self._milestone(data)
        if status == "succeeded":
            next_step = ""
        if not isinstance(content, str) or len(content) > 16000:
            raise ValueError("Invalid update")
        if status in {"blocked", "succeeded"} and not content.strip():
            raise ValueError("A blocker or completed task needs an explanation")
        with self.transaction() as db:
            if key:
                old = db.execute(
                    "SELECT * FROM tasks WHERE user_id=? AND intent_key=?", (uid, key)
                ).fetchone()
                if old:
                    return self._view(db, old)
            if request_id:
                old = db.execute(
                    "SELECT task_id FROM task_runs WHERE user_id=? AND request_id=?",
                    (uid, request_id),
                ).fetchone()
                if old:
                    return self._view(db, self._task(db, uid, old[0]))
            if (
                db.execute(
                    "SELECT COUNT(*) FROM tasks t WHERE t.user_id=? AND t.state!='archived' "
                    "AND EXISTS(SELECT 1 FROM task_runs r WHERE r.task_id=t.id AND r.status "
                    "IN ('scheduled','delivering','ready','running','blocked'))",
                    (uid,),
                ).fetchone()[0]
                >= 100
            ):
                raise ValueError("At most 100 unfinished tasks per user")
            tid = uuid.uuid4().hex
            now = time.time()
            db.execute(
                "INSERT INTO "
                "tasks(id,user_id,title,objective,success_criteria,state,schedule,generation,"
                "created_at,updated_at,source,intent_key) VALUES(?,?,?,?,?,'active',?,1,?,?,?,?)",
                (
                    tid,
                    uid,
                    fields["title"],
                    fields["objective"],
                    fields["success_criteria"],
                    json.dumps(schedule),
                    now,
                    now,
                    "conversation"
                    if captured
                    else "scheduled"
                    if schedule["mode"] != "now"
                    else "manual",
                    key,
                ),
            )
            db.execute("UPDATE tasks SET kind=? WHERE id=?", (kind, tid))
            if captured:
                rid = uuid.uuid4().hex
                db.execute(
                    "INSERT INTO "
                    "task_runs(id,task_id,user_id,generation,due_at,status,result,progress,phase,"
                    "next_step,request_id,started_at,finished_at,created_at) "
                    "VALUES(?,?,?,1,?,?,?,?,?,?,?,?,?,?)",
                    (
                        rid,
                        tid,
                        uid,
                        now,
                        status,
                        content if status == "succeeded" else "",
                        content if status != "succeeded" else "",
                        phase,
                        next_step,
                        request_id,
                        now,
                        now if status == "succeeded" else None,
                        now,
                    ),
                )
                db.execute(
                    "INSERT INTO task_updates(run_id,note_id,content,created_at,"
                    "status,phase) "
                    "VALUES(?,?,?,?,?,?)",
                    (rid, request_id or rid, content, now, status, phase),
                )
                if status == "running":
                    db.execute(
                        "UPDATE task_runs SET start_invocation_id=? WHERE id=?", (request_id, rid)
                    )
            else:
                self._plan(db, self._task(db, uid, tid), request_id=request_id)
            return self._view(db, self._task(db, uid, tid))

    def edit(self, uid, tid, data):
        with self.transaction() as db:
            task = dict(self._task(db, uid, tid))
            for k in ("title", "objective", "success_criteria"):
                if k in data:
                    if not isinstance(data[k], str):
                        raise ValueError("Task descriptions must be strings")
                    v = data[k].strip()
                    if not v or len(v) > (160 if k == "title" else 10000):
                        raise ValueError("Invalid task text")
                    task[k] = v
            if "kind" in data and data["kind"] not in {"task", "reminder"}:
                raise ValueError("Invalid task kind")
            if "schedule" in data:
                task["schedule"] = json.dumps(normalize(data["schedule"]))
            task["kind"] = data.get("kind", task["kind"])
            # Editing active work must be explicit: cancel it before changing its contract.
            if db.execute(
                "SELECT 1 FROM task_runs WHERE task_id=? AND status IN ('running','blocked')",
                (tid,),
            ).fetchone():
                raise ValueError("Cancel the active run before editing")
            db.execute(
                "UPDATE task_runs SET status='cancelled',finished_at=? WHERE "
                "task_id=? AND status IN ('scheduled','delivering','ready')",
                (time.time(), tid),
            )
            db.execute(
                "UPDATE tasks SET "
                "title=?,objective=?,success_criteria=?,schedule=?,generation=generation+1,updated_at=?"
                " WHERE id=?",
                (
                    task["title"],
                    task["objective"],
                    task["success_criteria"],
                    task["schedule"],
                    time.time(),
                    tid,
                ),
            )
            db.execute("UPDATE tasks SET kind=? WHERE id=?", (task["kind"], tid))
            row = self._task(db, uid, tid)
            if row["state"] == "active":
                self._plan(db, row)
            return self._view(db, row)

    def control(self, uid, tid, action):
        state = {
            "pause": "paused",
            "resume": "active",
            "cancel": "cancelled",
            "delete": "archived",
        }.get(action)
        if not state:
            raise ValueError("Invalid action")
        with self.transaction() as db:
            current = self._task(db, uid, tid)
            live = db.execute(
                "SELECT 1 FROM task_runs WHERE task_id=? AND status IN "
                "('scheduled','delivering','ready','running','blocked')",
                (tid,),
            ).fetchone()
            if current["state"] == state and (action != "resume" or live):
                return self._view(db, current)
            db.execute(
                "UPDATE tasks SET state=?,generation=generation+1,updated_at=? WHERE id=?",
                (state, time.time(), tid),
            )
            statuses = (
                "('scheduled','delivering','ready')"
                if action == "pause"
                else "('scheduled','delivering','ready','running','blocked')"
            )
            if action != "resume":
                db.execute(
                    "UPDATE task_runs SET status='cancelled',finished_at=?,lease_until=0,notice='' "
                    f"WHERE task_id=? AND status IN {statuses}",
                    (time.time(), tid),
                )
            row = self._task(db, uid, tid)
            if (
                action == "resume"
                and not db.execute(
                    "SELECT 1 FROM task_runs WHERE task_id=? AND status IN "
                    "('scheduled','delivering','ready','running','blocked')",
                    (tid,),
                ).fetchone()
            ):
                self._plan(db, row)
            return self._view(db, row)

    def claim_due(self):
        now = time.time()
        with self.transaction() as db:
            rows = db.execute(
                "SELECT r.* FROM task_runs r JOIN tasks t ON t.id=r.task_id WHERE "
                "t.state='active' AND r.generation=t.generation AND r.status IN "
                "('scheduled','delivering') AND r.due_at<=? AND r.lease_until<=? "
                "AND r.expires_at>=? "
                "ORDER BY r.due_at LIMIT 8",
                (now, now, now),
            ).fetchall()
            result = []
            for row in rows:
                db.execute(
                    "UPDATE task_runs SET status='delivering',lease_until=? WHERE id=?",
                    (now + 30, row["id"]),
                )
                result.append(
                    {**dict(row), "task": dict(self._task(db, row["user_id"], row["task_id"]))}
                )
            return result

    def delivered(self, uid, rid):
        with self.transaction() as db:
            self._run(db, uid, rid)
            db.execute(
                "UPDATE task_runs SET status='ready',lease_until=0 WHERE id=? AND "
                "status='delivering'",
                (rid,),
            )

    def start(self, uid, rid, invocation_id=None):
        with self.transaction() as db:
            run = self._run(db, uid, rid)
            task = self._task(db, uid, run["task_id"])
            if (
                run["status"] in {"scheduled", "delivering", "ready"}
                and time.time() > run["expires_at"]
            ):
                raise ValueError("Run expired; do not execute its objective")
            continuing = run["status"] == "running" and task["state"] in {"active", "paused"}
            if not continuing and (
                task["state"] != "active"
                or run["generation"] != task["generation"]
                or run["status"] not in {"delivering", "ready"}
            ):
                raise ValueError("Run cancelled, not due, or already finished")
            db.execute(
                "UPDATE task_runs SET "
                "status='running',started_at=COALESCE(started_at,?),heartbeat_at=?,"
                "start_invocation_id=COALESCE(start_invocation_id,?),lease_until=0 "
                "WHERE id=? AND status IN ('ready','delivering')",
                (time.time(), time.time(), invocation_id, rid),
            )
            return {
                "run_id": rid,
                "kind": task["kind"],
                "expires_at": run["expires_at"],
                "title": task["title"],
                "objective": task["objective"],
                "success_criteria": task["success_criteria"],
            }

    @staticmethod
    def _milestone(data):
        values = [data.get("phase", ""), data.get("next_step", "")]
        if any(not isinstance(v, str) or len(v) > 500 for v in values):
            raise ValueError("Phase and next step must be strings of at most 500 characters")
        return tuple(v.strip() for v in values)

    def update_run(
        self,
        uid,
        rid,
        status,
        content,
        note_id,
        *,
        phase=None,
        next_step=None,
        notice=None,
        invocation_id=None,
    ):
        self._milestone(
            {
                "phase": "" if phase is None else phase,
                "next_step": "" if next_step is None else next_step,
            }
        )
        if not isinstance(content, str) or not content.strip() or len(content) > 16000:
            raise ValueError("Nonempty update required")
        if not isinstance(note_id, str) or not 1 <= len(note_id) <= 256:
            raise ValueError("Invalid update identity")
        if status not in {"running", "blocked", "succeeded", "failed"}:
            raise ValueError("Invalid status")
        with self.transaction() as db:
            run = self._run(db, uid, rid)
            task = self._task(db, uid, run["task_id"])
            old = db.execute(
                "SELECT content,status,phase FROM task_updates WHERE run_id=? AND note_id=?",
                (rid, note_id),
            ).fetchone()
            if old:
                if (
                    old[0] != content
                    or (old[1] and old[1] != status)
                    or (phase is not None and old[2] != phase)
                ):
                    raise ValueError("Update identity conflict")
                return self._view(db, task)
            if run["status"] not in {"running", "blocked"}:
                raise ValueError("Run is not active")
            db.execute(
                "INSERT INTO "
                "task_updates(run_id,note_id,content,created_at,"
                "status,phase) "
                "VALUES(?,?,?,?,?,?)",
                (
                    rid,
                    note_id,
                    content,
                    time.time(),
                    status,
                    phase if phase is not None else run["phase"],
                ),
            )
            db.execute(
                "UPDATE task_runs SET "
                "status=?,result=?,progress=?,phase=?,next_step=?,finished_at=?,heartbeat_at=? "
                "WHERE id=?",
                (
                    status,
                    content if status in TERMINAL else "",
                    content if status not in TERMINAL else run["progress"],
                    phase if phase is not None else run["phase"],
                    ""
                    if status in TERMINAL
                    else next_step
                    if next_step is not None
                    else run["next_step"],
                    time.time() if status in TERMINAL else None,
                    time.time(),
                    rid,
                ),
            )
            if status == "running" and invocation_id:
                db.execute(
                    "UPDATE task_runs SET start_invocation_id=?,notice='' WHERE id=?",
                    (invocation_id, rid),
                )
            if notice is None:
                db.execute("UPDATE task_runs SET notice='' WHERE id=?", (rid,))
            if notice:
                db.execute(
                    "UPDATE task_runs SET notice=?,notice_sent=0,"
                    "notice_version=notice_version+1 WHERE id=?",
                    (notice, rid),
                )
            db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (time.time(), task["id"]))
            if (
                status in TERMINAL
                and task["state"] == "active"
                and json.loads(task["schedule"])["mode"] in {"daily", "weekly"}
            ):
                self._plan(db, task)
            return self._view(db, self._task(db, uid, task["id"]))

    def reserve_delegation(self, uid, rid):
        with self.transaction() as db:
            run = self._run(db, uid, rid)
            if run["status"] != "running":
                raise ValueError("Start the run before delegating")
            db.execute(
                "UPDATE task_runs SET agent_id=COALESCE(agent_id,'pending') WHERE id=?", (rid,)
            )

    def link(self, uid, rid, agent_id):
        with self.transaction() as db:
            run = self._run(db, uid, rid)
            if run["status"] not in {"running", "cancelled", "succeeded", "failed"}:
                raise ValueError("Run is not active")
            if run["agent_id"] and run["agent_id"] not in {"pending", agent_id}:
                raise ValueError("Run already delegated")
            db.execute("UPDATE task_runs SET agent_id=? WHERE id=?", (agent_id, rid))

    def synced(self, uid, rid):
        with self.transaction() as db:
            self._run(db, uid, rid)
            db.execute("UPDATE task_runs SET reconciled=1 WHERE id=?", (rid,))

    def sync_later(self, uid, rid):
        with self.transaction() as db:
            self._run(db, uid, rid)
            db.execute(
                "UPDATE task_runs SET lease_until=? WHERE id=? AND reconciled=0",
                (time.time() + 5, rid),
            )

    def linked(self):
        now = time.time()
        with self.transaction() as db:
            rows = db.execute(
                "SELECT * FROM task_runs WHERE agent_id IS NOT NULL AND reconciled=0 "
                "AND lease_until<=? ORDER BY lease_until,created_at LIMIT 12",
                (now,),
            ).fetchall()
            for row in rows:
                db.execute("UPDATE task_runs SET lease_until=? WHERE id=?", (now + 120, row["id"]))
            return [dict(row) for row in rows]

    def reconcile_time(self):
        now = time.time()
        with self.transaction() as db:
            rows = db.execute(
                "SELECT r.*,t.schedule FROM task_runs r JOIN tasks t ON t.id=r.task_id "
                "WHERE (r.status IN ('scheduled','delivering','ready') AND r.expires_at<?) "
                "OR (r.status='running' AND COALESCE(r.heartbeat_at,r.started_at,r.created_at) "
                "+COALESCE(json_extract(t.schedule,'$.run_timeout_seconds'),3600)<?) "
                "ORDER BY r.due_at LIMIT 200",
                (now, now),
            ).fetchall()
            for row in rows:
                schedule = json.loads(row["schedule"])
                expired = row["status"] != "running" and now > row["expires_at"]
                stale = row["status"] == "running" and now - (
                    row["heartbeat_at"] or row["started_at"] or row["created_at"]
                ) > schedule.get("run_timeout_seconds", 3600)
                if not expired and not stale:
                    continue
                status = "expired" if expired else "blocked"
                text = (
                    "已超过允许的补执行时间，本次未执行。"
                    if expired
                    else "长时间没有进展记录，需要确认执行结果。"
                )
                db.execute(
                    "UPDATE task_runs SET status=?,result=?,progress=?,finished_at=?, "
                    "notice=?,notice_sent=0,notice_version=notice_version+1 "
                    "WHERE id=?",
                    (
                        status,
                        text if expired else row["result"],
                        row["progress"] if expired else text,
                        now if expired else None,
                        text,
                        row["id"],
                    ),
                )
                db.execute(
                    "INSERT OR IGNORE INTO task_updates(run_id,note_id,content,created_at,"
                    "status,phase) "
                    "VALUES(?,?,?,?,?,?)",
                    (row["id"], "reconcile:" + status, text, now, status, "对账"),
                )
                db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, row["task_id"]))
                task = self._task(db, row["user_id"], row["task_id"])
                if (
                    expired
                    and task["state"] == "active"
                    and schedule["mode"] in {"daily", "weekly"}
                ):
                    self._plan(db, task, now=now)

    def main_runs(self):
        with self.transaction() as db:
            rows = db.execute(
                "SELECT r.*,t.kind FROM task_runs r JOIN tasks t ON t.id=r.task_id "
                "WHERE r.status='running' AND r.agent_id IS NULL "
                "AND r.start_invocation_id IS NOT NULL "
                "AND r.lease_until<=? ORDER BY r.lease_until LIMIT 12",
                (time.time(),),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE task_runs SET lease_until=? WHERE id=?", (time.time() + 15, row["id"])
                )
            return [dict(row) for row in rows]

    def notices(self):
        with self.transaction() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM task_runs WHERE notice!='' "
                    "AND notice_sent=0 AND intervention_count=0 "
                    "ORDER BY created_at LIMIT 12"
                )
            ]

    def notice_sent(self, uid, rid, version):
        with self.transaction() as db:
            self._run(db, uid, rid)
            db.execute(
                "UPDATE task_runs SET notice_sent=1,intervention_count=1 "
                "WHERE id=? AND notice_version=?",
                (rid, version),
            )
