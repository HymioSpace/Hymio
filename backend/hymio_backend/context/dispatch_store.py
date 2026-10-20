import json
import sqlite3
from contextlib import closing


def freeze(database, user_id, dream_id, request_id, frame):
    """Persist exact command bytes before dispatch, so retries survive process restarts."""
    with closing(sqlite3.connect(database, timeout=5)) as db, db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS context_dispatches (
                user_id TEXT NOT NULL, dream_id TEXT NOT NULL, request_id TEXT NOT NULL,
                frame_json TEXT NOT NULL, PRIMARY KEY(user_id,dream_id,request_id))
        """)
        db.execute(
            "INSERT OR IGNORE INTO context_dispatches VALUES(?,?,?,?)",
            (user_id, dream_id, request_id, json.dumps(frame, ensure_ascii=False)),
        )
        return json.loads(
            db.execute(
                "SELECT frame_json FROM context_dispatches "
                "WHERE user_id=? AND dream_id=? AND request_id=?",
                (user_id, dream_id, request_id),
            ).fetchone()[0]
        )
