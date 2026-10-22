import hashlib
import json
import time
import uuid

LIMIT = 20 * 1024 * 1024
MAX_ITEMS = 12


class MediaStore:
    def __init__(self, sessions):
        self.sessions = sessions
        with sessions.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
                    mime TEXT NOT NULL, size INTEGER NOT NULL, digest TEXT NOT NULL,
                    content BLOB NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS attachments_owner ON attachments(user_id, created);
                CREATE TABLE IF NOT EXISTS model_preferences (
                    user_id TEXT PRIMARY KEY, model TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS media_operations (
                    user_id TEXT NOT NULL, invocation_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
                    PRIMARY KEY(user_id, invocation_id));
            """)

    def save(self, user, name, mime, content):
        if not content or len(content) > LIMIT:
            raise ValueError("File must be between 1 byte and 20 MB")
        name = "".join(c if c.isprintable() else " " for c in name)[:200] or "attachment"
        identifier = uuid.uuid4().hex
        with self.sessions.transaction() as db:
            total = db.execute(
                "SELECT COALESCE(SUM(size),0) FROM attachments WHERE user_id=?", (user,)
            ).fetchone()[0]
            if total + len(content) > 256 * 1024 * 1024:
                raise ValueError("Attachment quota exceeded")
            db.execute(
                "INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    user,
                    name[:200],
                    mime,
                    len(content),
                    hashlib.sha256(content).hexdigest(),
                    content,
                    time.time(),
                ),
            )
        return {
            "attachment_id": identifier,
            "name": name[:200],
            "mime": mime,
            "size": len(content),
            "url": "/attachments/" + identifier,
        }

    def reference(self, user, identifier):
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT id FROM attachments WHERE user_id=? AND id=?", (user, identifier)
            ).fetchone()
        if row is None:
            raise LookupError("Attachment not found")

    def read(self, user, identifier):
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT * FROM attachments WHERE user_id=? AND id=?", (user, identifier)
            ).fetchone()
        if row is None:
            raise LookupError("Attachment not found")
        return dict(row)

    def model(self, user, default):
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT model FROM model_preferences WHERE user_id=?", (user,)
            ).fetchone()
        return row[0] if row else default

    def select(self, user, model):
        with self.sessions.transaction() as db:
            db.execute(
                "INSERT INTO model_preferences VALUES (?,?) ON CONFLICT(user_id) "
                "DO UPDATE SET model=excluded.model",
                (user, model),
            )

    def begin(self, user, invocation, args):
        fingerprint = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        with self.sessions.transaction() as db:
            row = db.execute(
                "SELECT * FROM media_operations WHERE user_id=? AND invocation_id=?",
                (user, invocation),
            ).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise ValueError("Invocation reused with different arguments")
                return (
                    json.loads(row["result"])
                    if row["result"]
                    else {"status": row["status"], "notice": "Do not repeat this operation."}
                )
            db.execute(
                "INSERT INTO media_operations VALUES (?,?,?,?,NULL)",
                (user, invocation, fingerprint, "outcome_unknown"),
            )
        return None

    def finish(self, user, invocation, result):
        with self.sessions.transaction() as db:
            db.execute(
                "UPDATE media_operations SET status=?, result=? "
                "WHERE user_id=? AND invocation_id=?",
                ("done", json.dumps(result), user, invocation),
            )
