def initialize(db):
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

    additions = {
        "tasks": {
            "source": "TEXT NOT NULL DEFAULT 'manual'",
            "intent_key": "TEXT",
            "kind": "TEXT NOT NULL DEFAULT 'task'",
            "for_user": "INTEGER NOT NULL DEFAULT 0",
        },
        "task_runs": {
            "expires_at": "REAL",
            "heartbeat_at": "REAL",
            "start_invocation_id": "TEXT",
            "notice": "TEXT NOT NULL DEFAULT ''",
            "notice_sent": "INTEGER NOT NULL DEFAULT 0",
            "notice_version": "INTEGER NOT NULL DEFAULT 0",
            "intervention_count": "INTEGER NOT NULL DEFAULT 0",
            "resume_note": "TEXT NOT NULL DEFAULT ''",
            "resume_request_id": "TEXT NOT NULL DEFAULT ''",
            "wait_reason": "TEXT NOT NULL DEFAULT ''",
            "resume_at": "REAL",
            "followup_version": "INTEGER NOT NULL DEFAULT 0",
            "followup_sent": "INTEGER NOT NULL DEFAULT 0",
            "phase": "TEXT NOT NULL DEFAULT ''",
            "next_step": "TEXT NOT NULL DEFAULT ''",
            "progress": "TEXT NOT NULL DEFAULT ''",
        },
        "task_updates": {
            "status": "TEXT NOT NULL DEFAULT ''",
            "phase": "TEXT NOT NULL DEFAULT ''",
        },
    }
    for table, columns in additions.items():
        existing = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS task_intent ON tasks(user_id,intent_key) "
        "WHERE intent_key IS NOT NULL"
    )
    db.execute(
        "UPDATE task_runs SET progress=result,result='' "
        "WHERE status IN ('running','blocked') AND progress='' AND result!=''"
    )

    db.execute("UPDATE task_runs SET expires_at=due_at+900 WHERE expires_at IS NULL")
    db.execute(
        "UPDATE task_runs SET heartbeat_at=COALESCE(started_at,created_at) "
        "WHERE heartbeat_at IS NULL"
    )

    db.execute("CREATE INDEX IF NOT EXISTS task_expiry ON task_runs(status,expires_at)")
