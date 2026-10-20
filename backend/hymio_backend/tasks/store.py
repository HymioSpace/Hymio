import json
import time
import uuid

from .schedule import next_due, normalize

LIVE = {"scheduled", "delivering", "ready", "running", "blocked"}
TERMINAL = {"succeeded", "failed", "cancelled"}


class TaskStore:
    def __init__(self, sessions):
        self.transaction = sessions.transaction
        with self.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
                objective TEXT NOT NULL, success_criteria TEXT NOT NULL,
                state TEXT NOT NULL, schedule TEXT NOT NULL, generation INTEGER NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(user_id,updated_at DESC);
            CREATE TABLE IF NOT EXISTS task_runs (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
                user_id TEXT NOT NULL, generation INTEGER NOT NULL, due_at REAL NOT NULL,
                status TEXT NOT NULL, result TEXT NOT NULL DEFAULT '', agent_id TEXT,
                request_id TEXT, lease_until REAL NOT NULL DEFAULT 0,
                started_at REAL, finished_at REAL, created_at REAL NOT NULL,
                reconciled INTEGER NOT NULL DEFAULT 0);
            CREATE UNIQUE INDEX IF NOT EXISTS task_request ON task_runs(user_id,request_id)
                WHERE request_id IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_task_run ON task_runs(task_id)
                WHERE status IN ('scheduled','delivering','ready','running','blocked');
            CREATE INDEX IF NOT EXISTS task_due ON task_runs(status,due_at,lease_until);
            CREATE TABLE IF NOT EXISTS task_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                note_id TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL,
                UNIQUE(run_id,note_id));
            """)
            if "reconciled" not in {r["name"] for r in db.execute("PRAGMA table_info(task_runs)")}:
                db.execute("ALTER TABLE task_runs ADD COLUMN reconciled INTEGER NOT NULL DEFAULT 0")

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
            if summary:
                run["result"] = run["result"][:600]
                run["updates"] = []
                continue
            run["updates"] = [
                dict(r)
                for r in db.execute(
                    "SELECT note_id,content,created_at FROM task_updates WHERE "
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

    def create(self, uid, data, request_id=None):
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
        schedule = normalize(data.get("schedule", {"mode": "now"}))
        with self.transaction() as db:
            if request_id:
                old = db.execute(
                    "SELECT task_id FROM task_runs WHERE user_id=? AND request_id=?",
                    (uid, request_id),
                ).fetchone()
                if old:
                    return self._view(db, self._task(db, uid, old[0]))
            if (
                db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE user_id=? AND state!='archived'", (uid,)
                ).fetchone()[0]
                >= 100
            ):
                raise ValueError("At most 100 unarchived tasks per user")
            tid = uuid.uuid4().hex
            now = time.time()
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,'active',?,1,?,?)",
                (
                    tid,
                    uid,
                    fields["title"],
                    fields["objective"],
                    fields["success_criteria"],
                    json.dumps(schedule),
                    now,
                    now,
                ),
            )
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
            if "schedule" in data:
                task["schedule"] = json.dumps(normalize(data["schedule"]))
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
                    "UPDATE task_runs SET status='cancelled',finished_at=?,lease_until=0 "
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
                "ORDER BY r.due_at LIMIT 8",
                (now, now),
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

    def start(self, uid, rid):
        with self.transaction() as db:
            run = self._run(db, uid, rid)
            task = self._task(db, uid, run["task_id"])
            continuing = run["status"] == "running" and task["state"] in {"active", "paused"}
            if not continuing and (
                task["state"] != "active"
                or run["generation"] != task["generation"]
                or run["status"] not in {"delivering", "ready"}
            ):
                raise ValueError("Run cancelled, not due, or already finished")
            db.execute(
                "UPDATE task_runs SET "
                "status='running',started_at=COALESCE(started_at,?) WHERE id=?",
                (time.time(), rid),
            )
            return {
                "run_id": rid,
                "title": task["title"],
                "objective": task["objective"],
                "success_criteria": task["success_criteria"],
            }

    def update_run(self, uid, rid, status, content, note_id):
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
                "SELECT content FROM task_updates WHERE run_id=? AND note_id=?", (rid, note_id)
            ).fetchone()
            if old:
                if old[0] != content:
                    raise ValueError("Update identity conflict")
                return self._view(db, task)
            if run["status"] not in {"running", "blocked"}:
                raise ValueError("Run is not active")
            db.execute(
                "INSERT INTO task_updates(run_id,note_id,content,created_at) VALUES(?,?,?,?)",
                (rid, note_id, content, time.time()),
            )
            db.execute(
                "UPDATE task_runs SET status=?,result=?,finished_at=? WHERE id=?",
                (status, content, time.time() if status in TERMINAL else None, rid),
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
