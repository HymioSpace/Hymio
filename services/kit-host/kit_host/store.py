import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import date

CATEGORIES = {
    "food": "餐饮",
    "transport": "出行",
    "learning": "学习",
    "life": "生活",
    "other": "其他",
}


class KitStore:
    """Persistent business state owned by the Kit Host, not Hymio Backend."""

    def __init__(self, path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS kit_installs (
                    user_id TEXT NOT NULL,
                    kit_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    installed_at REAL NOT NULL,
                    PRIMARY KEY(user_id, kit_id)
                );
                CREATE TABLE IF NOT EXISTS kit_receipts (
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    kit_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(user_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    category TEXT NOT NULL,
                    note TEXT NOT NULL,
                    occurred_on TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ledger_entries_user_date
                    ON ledger_entries(user_id, occurred_on DESC, created_at DESC);
                CREATE TABLE IF NOT EXISTS generated_kits (
                    kit_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    manifest TEXT NOT NULL,
                    app_html TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS generated_kits_owner
                    ON generated_kits(owner_user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS kit_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kit_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS kit_records_user_time
                    ON kit_records(user_id, kit_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS app_projects (
                    kit_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    display_json TEXT NOT NULL,
                    files_json TEXT NOT NULL,
                    source_revision TEXT NOT NULL,
                    status TEXT NOT NULL,
                    coding_agent_id TEXT,
                    published_revision INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS app_projects_owner
                    ON app_projects(owner_user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS app_revisions (
                    revision_id TEXT PRIMARY KEY,
                    kit_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    files_json TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    app_html TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    author_agent_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(kit_id, revision)
                );
                CREATE TABLE IF NOT EXISTS app_coding_messages (
                    message_id TEXT PRIMARY KEY,
                    kit_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS app_coding_messages_thread
                    ON app_coding_messages(kit_id, created_at);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(generated_kits)")}
            if "app_html" not in columns:
                db.execute(
                    "ALTER TABLE generated_kits ADD COLUMN app_html TEXT NOT NULL DEFAULT ''"
                )
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def install(self, user_id, kit_id, version):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO kit_installs(user_id,kit_id,version,installed_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id,kit_id) DO UPDATE SET version=excluded.version",
                (user_id, kit_id, version, time.time()),
            )

    def uninstall(self, user_id, kit_id):
        with self.transaction() as db:
            db.execute(
                "DELETE FROM kit_installs WHERE user_id=? AND kit_id=?",
                (user_id, kit_id),
            )

    def installed(self, user_id):
        with self.transaction() as db:
            return {
                row["kit_id"]: row["version"]
                for row in db.execute(
                    "SELECT kit_id,version FROM kit_installs WHERE user_id=?", (user_id,)
                )
            }

    def create_entry(self, user_id, data, idempotency_key):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 256:
            raise ValueError("A stable idempotency key is required")
        amount = data.get("amount")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not 0 < amount <= 1_000_000
        ):
            raise ValueError("Amount must be between 0 and 1,000,000")
        amount_minor = round(float(amount) * 100)
        category = data.get("category", "other")
        if category not in CATEGORIES:
            raise ValueError("Unknown category")
        note = data.get("note", "")
        if not isinstance(note, str) or len(note.strip()) > 200:
            raise ValueError("Note must be at most 200 characters")
        occurred_on = data.get("occurred_on") or date.today().isoformat()
        if not isinstance(occurred_on, str):
            raise ValueError("Invalid date")
        try:
            occurred_on = date.fromisoformat(occurred_on).isoformat()
        except ValueError as exc:
            raise ValueError("Invalid date") from exc
        entry_id, now = uuid.uuid4().hex, time.time()
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != "hymio.ledger" or receipt["operation"] != "entries.create":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            db.execute(
                "INSERT INTO ledger_entries "
                "(id,user_id,amount_minor,currency,category,note,occurred_on,revision,created_at) "
                "VALUES(?,?,?,?,?,?,?,1,?)",
                (
                    entry_id,
                    user_id,
                    amount_minor,
                    "CNY",
                    category,
                    note.strip(),
                    occurred_on,
                    now,
                ),
            )
            result = {
                "entry": {
                    "id": entry_id,
                    "amount": amount_minor / 100,
                    "currency": "CNY",
                    "category": category,
                    "note": note.strip(),
                    "occurred_on": occurred_on,
                    "revision": 1,
                },
                "message": "这笔记下了。",
            }
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    idempotency_key,
                    "hymio.ledger",
                    "entries.create",
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            return result

    def list_entries(self, user_id, limit=20):
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Limit must be between 1 and 30")
        with self.transaction() as db:
            rows = db.execute(
                "SELECT * FROM ledger_entries WHERE user_id=? "
                "ORDER BY occurred_on DESC,created_at DESC LIMIT ?",
                (user_id, limit),
            )
            return [
                {
                    "id": row["id"],
                    "amount": row["amount_minor"] / 100,
                    "currency": row["currency"],
                    "category": row["category"],
                    "note": row["note"],
                    "occurred_on": row["occurred_on"],
                    "revision": row["revision"],
                }
                for row in rows
            ]

    def summary(self, user_id):
        month = date.today().strftime("%Y-%m")
        with self.transaction() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(amount_minor),0) AS total_minor,COUNT(*) AS count "
                "FROM ledger_entries WHERE user_id=? AND substr(occurred_on,1,7)=?",
                (user_id, month),
            ).fetchone()
            return {
                "month": month,
                "total": row["total_minor"] / 100,
                "count": row["count"],
            }

    def save_generated(self, kit_id, owner_user_id, manifest, app_html):
        now = time.time()
        with self.transaction() as db:
            db.execute(
                "INSERT INTO generated_kits"
                "(kit_id,owner_user_id,manifest,app_html,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(kit_id) DO UPDATE SET manifest=excluded.manifest,"
                "updated_at=excluded.updated_at",
                (
                    kit_id,
                    owner_user_id,
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                    app_html,
                    now,
                    now,
                ),
            )

    def generated(self, owner_user_id):
        with self.transaction() as db:
            return [
                json.loads(row["manifest"])
                for row in db.execute(
                    "SELECT manifest FROM generated_kits WHERE owner_user_id=? "
                    "ORDER BY updated_at DESC",
                    (owner_user_id,),
                )
            ]

    def generated_app(self, owner_user_id, kit_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT app_html FROM generated_kits WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            ).fetchone()
            if not row or not row["app_html"]:
                raise ValueError("Application UI is unavailable")
            return row["app_html"]

    def update_generated(
        self,
        owner_user_id,
        kit_id,
        manifest,
        app_html,
        idempotency_key,
        result,
        expected_revision,
    ):
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (owner_user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != kit_id or receipt["operation"] != "app.update":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            current = db.execute(
                "SELECT app_html FROM generated_kits WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            ).fetchone()
            if not current:
                raise ValueError("Generated application is unavailable")
            current_revision = hashlib.sha256(
                current["app_html"].encode()
            ).hexdigest()
            if expected_revision != current_revision:
                raise ValueError(
                    "Application source changed; call app.get_source again before editing"
                )
            changed = db.execute(
                "UPDATE generated_kits SET manifest=?,app_html=?,updated_at=? "
                "WHERE owner_user_id=? AND kit_id=?",
                (
                    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                    app_html,
                    time.time(),
                    owner_user_id,
                    kit_id,
                ),
            )
            if changed.rowcount != 1:
                raise ValueError("Generated application is unavailable")
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    owner_user_id,
                    idempotency_key,
                    kit_id,
                    "app.update",
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    time.time(),
                ),
            )
            return result

    def generated_management_receipt(
        self, owner_user_id, kit_id, operation, idempotency_key
    ):
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=? AND kit_id=? AND operation=?",
                (owner_user_id, idempotency_key, kit_id, operation),
            ).fetchone()
            return json.loads(receipt["result"]) if receipt else None

    def delete_generated(
        self, owner_user_id, kit_id, idempotency_key, result
    ):
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (owner_user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != kit_id or receipt["operation"] != "app.delete":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            changed = db.execute(
                "DELETE FROM generated_kits WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            )
            if changed.rowcount != 1:
                raise ValueError("Generated application is unavailable")
            db.execute(
                "DELETE FROM kit_records WHERE user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            )
            db.execute(
                "DELETE FROM kit_receipts WHERE user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            )
            db.execute(
                "DELETE FROM kit_installs WHERE user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            )
            db.execute(
                "DELETE FROM app_projects WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            )
            db.execute(
                "DELETE FROM app_revisions WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            )
            db.execute(
                "DELETE FROM app_coding_messages WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            )
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    owner_user_id,
                    idempotency_key,
                    kit_id,
                    "app.delete",
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    time.time(),
                ),
            )
            return result

    def create_project(
        self, owner_user_id, kit_id, display, files, source_revision
    ):
        now = time.time()
        with self.transaction() as db:
            existing = db.execute(
                "SELECT kit_id FROM app_projects WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            ).fetchone()
            if existing:
                return None
            db.execute(
                "INSERT INTO app_projects"
                "(kit_id,owner_user_id,display_json,files_json,source_revision,status,"
                "published_revision,created_at,updated_at) "
                "VALUES(?,?,?,?,?,'draft',0,?,?)",
                (
                    kit_id,
                    owner_user_id,
                    json.dumps(display, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(files, ensure_ascii=False, separators=(",", ":")),
                    source_revision,
                    now,
                    now,
                ),
            )
        return self.project(owner_user_id, kit_id)

    def project(self, owner_user_id, kit_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM app_projects WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            ).fetchone()
            if not row:
                raise ValueError("Application project is unavailable")
            value = dict(row)
            value["display"] = json.loads(value.pop("display_json"))
            value["files"] = json.loads(value.pop("files_json"))
            return value

    def project_by_agent(self, owner_user_id, agent_id):
        with self.transaction() as db:
            row = db.execute(
                "SELECT kit_id FROM app_projects "
                "WHERE owner_user_id=? AND coding_agent_id=?",
                (owner_user_id, agent_id),
            ).fetchone()
            if not row:
                raise ValueError("Coding context is not bound to an application")
            return row["kit_id"]

    def bind_project_agent(self, owner_user_id, kit_id, agent_id):
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE app_projects SET coding_agent_id=?,updated_at=? "
                "WHERE owner_user_id=? AND kit_id=?",
                (agent_id, time.time(), owner_user_id, kit_id),
            )
            if changed.rowcount != 1:
                raise ValueError("Application project is unavailable")

    def update_project(
        self,
        owner_user_id,
        kit_id,
        files,
        source_revision,
        expected_revision,
        idempotency_key,
        result,
    ):
        now = time.time()
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (owner_user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != kit_id or receipt["operation"] != "dev.patch":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            current = db.execute(
                "SELECT source_revision FROM app_projects "
                "WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            ).fetchone()
            if not current:
                raise ValueError("Application project is unavailable")
            if current["source_revision"] != expected_revision:
                raise ValueError("Application source changed; read the tree again")
            db.execute(
                "UPDATE app_projects SET files_json=?,source_revision=?,status='draft',"
                "updated_at=? WHERE owner_user_id=? AND kit_id=?",
                (
                    json.dumps(files, ensure_ascii=False, separators=(",", ":")),
                    source_revision,
                    now,
                    owner_user_id,
                    kit_id,
                ),
            )
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,'dev.patch',?,?)",
                (
                    owner_user_id,
                    idempotency_key,
                    kit_id,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            return result

    def publish_project(
        self,
        owner_user_id,
        kit_id,
        expected_revision,
        manifest,
        app_html,
        source_revision,
        summary,
        author_agent_id,
        idempotency_key,
        result,
        display,
    ):
        now = time.time()
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (owner_user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != kit_id or receipt["operation"] != "dev.publish":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            project = db.execute(
                "SELECT * FROM app_projects WHERE owner_user_id=? AND kit_id=?",
                (owner_user_id, kit_id),
            ).fetchone()
            if not project:
                raise ValueError("Application project is unavailable")
            if project["source_revision"] != expected_revision:
                raise ValueError("Application source changed; build again before publishing")
            revision = project["published_revision"] + 1
            revision_id = uuid.uuid4().hex
            serialized_manifest = json.dumps(
                manifest, ensure_ascii=False, separators=(",", ":")
            )
            db.execute(
                "UPDATE app_projects SET status='published',published_revision=?,"
                "updated_at=?,display_json=? WHERE owner_user_id=? AND kit_id=?",
                (
                    revision,
                    now,
                    json.dumps(
                        display, ensure_ascii=False, separators=(",", ":")
                    ),
                    owner_user_id,
                    kit_id,
                ),
            )
            db.execute(
                "INSERT INTO generated_kits"
                "(kit_id,owner_user_id,manifest,app_html,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(kit_id) DO UPDATE SET "
                "owner_user_id=excluded.owner_user_id,manifest=excluded.manifest,"
                "app_html=excluded.app_html,updated_at=excluded.updated_at",
                (
                    kit_id,
                    owner_user_id,
                    serialized_manifest,
                    app_html,
                    project["created_at"],
                    now,
                ),
            )
            db.execute(
                "INSERT INTO kit_installs(user_id,kit_id,version,installed_at) "
                "VALUES(?,?,?,?) ON CONFLICT(user_id,kit_id) DO UPDATE SET "
                "version=excluded.version",
                (owner_user_id, kit_id, manifest["version"], now),
            )
            db.execute(
                "INSERT INTO app_revisions"
                "(revision_id,kit_id,owner_user_id,revision,files_json,manifest_json,"
                "app_html,summary,author_agent_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    revision_id,
                    kit_id,
                    owner_user_id,
                    revision,
                    project["files_json"],
                    serialized_manifest,
                    app_html,
                    summary[:2000],
                    author_agent_id,
                    now,
                ),
            )
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,'dev.publish',?,?)",
                (
                    owner_user_id,
                    idempotency_key,
                    kit_id,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            return result

    def app_revisions(self, owner_user_id, kit_id):
        with self.transaction() as db:
            return [
                {
                    "revision": row["revision"],
                    "summary": row["summary"],
                    "author_agent_id": row["author_agent_id"],
                    "created_at": row["created_at"],
                }
                for row in db.execute(
                    "SELECT revision,summary,author_agent_id,created_at "
                    "FROM app_revisions WHERE owner_user_id=? AND kit_id=? "
                    "ORDER BY revision DESC LIMIT 50",
                    (owner_user_id, kit_id),
                )
            ]

    def add_coding_message(
        self, owner_user_id, kit_id, message_id, author, content
    ):
        with self.transaction() as db:
            old = db.execute(
                "SELECT author,content FROM app_coding_messages WHERE message_id=?",
                (message_id,),
            ).fetchone()
            if old:
                if (
                    old["author"] != author
                    or old["content"] != content
                ):
                    raise ValueError("Coding message idempotency conflict")
                return
            db.execute(
                "INSERT INTO app_coding_messages"
                "(message_id,kit_id,owner_user_id,author,content,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    message_id,
                    kit_id,
                    owner_user_id,
                    author,
                    content,
                    time.time(),
                ),
            )

    def coding_messages(self, owner_user_id, kit_id):
        with self.transaction() as db:
            return [
                {
                    "id": row["message_id"],
                    "author": row["author"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                }
                for row in db.execute(
                    "SELECT message_id,author,content,created_at "
                    "FROM app_coding_messages "
                    "WHERE owner_user_id=? AND kit_id=? ORDER BY created_at",
                    (owner_user_id, kit_id),
                )
            ]

    def all_app_records(self, user_id, kit_id):
        with self.transaction() as db:
            return [
                {
                    "id": row["id"],
                    "data": json.loads(row["data"]),
                    "revision": row["revision"],
                    "created_at": row["created_at"],
                }
                for row in db.execute(
                    "SELECT id,data,revision,created_at FROM kit_records "
                    "WHERE user_id=? AND kit_id=? ORDER BY created_at",
                    (user_id, kit_id),
                )
            ]

    def apply_app_mutations(
        self,
        user_id,
        kit_id,
        idempotency_key,
        operation,
        mutations,
        result,
    ):
        now = time.time()
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != kit_id or receipt["operation"] != operation:
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            for mutation in mutations:
                kind = mutation.get("kind")
                if kind == "insert":
                    row = mutation["record"]
                    db.execute(
                        "INSERT INTO kit_records(id,user_id,kit_id,data,revision,created_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (
                            row["id"],
                            user_id,
                            kit_id,
                            json.dumps(
                                row["data"],
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            row["revision"],
                            row["created_at"],
                        ),
                    )
                elif kind == "update":
                    row = mutation["record"]
                    db.execute(
                        "UPDATE kit_records SET data=?,revision=? "
                        "WHERE id=? AND user_id=? AND kit_id=?",
                        (
                            json.dumps(
                                row["data"],
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            row["revision"],
                            row["id"],
                            user_id,
                            kit_id,
                        ),
                    )
                elif kind == "delete":
                    db.execute(
                        "DELETE FROM kit_records WHERE id=? AND user_id=? AND kit_id=?",
                        (mutation["id"], user_id, kit_id),
                    )
                else:
                    raise ValueError("Unknown application mutation")
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    idempotency_key,
                    kit_id,
                    operation,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            return result

    def create_record(self, user_id, kit_id, data, idempotency_key):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 256:
            raise ValueError("A stable idempotency key is required")
        with self.transaction() as db:
            receipt = db.execute(
                "SELECT kit_id,operation,result FROM kit_receipts "
                "WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchone()
            if receipt:
                if receipt["kit_id"] != kit_id or receipt["operation"] != "items.create":
                    raise ValueError("Idempotency key belongs to another operation")
                return json.loads(receipt["result"])
            item_id, now = uuid.uuid4().hex, time.time()
            result = {
                "item": {
                    "id": item_id,
                    "fields": data,
                    "revision": 1,
                },
                "message": "已保存。",
            }
            db.execute(
                "INSERT INTO kit_records(id,user_id,kit_id,data,revision,created_at) "
                "VALUES(?,?,?,?,1,?)",
                (
                    item_id,
                    user_id,
                    kit_id,
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            db.execute(
                "INSERT INTO kit_receipts"
                "(user_id,idempotency_key,kit_id,operation,result,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    idempotency_key,
                    kit_id,
                    "items.create",
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            return result

    def list_records(self, user_id, kit_id, limit=20):
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Limit must be between 1 and 30")
        with self.transaction() as db:
            return [
                {
                    "id": row["id"],
                    "fields": json.loads(row["data"]),
                    "revision": row["revision"],
                    "created_at": row["created_at"],
                }
                for row in db.execute(
                    "SELECT * FROM kit_records WHERE user_id=? AND kit_id=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, kit_id, limit),
                )
            ]

    def count_records(self, user_id, kit_id):
        with self.transaction() as db:
            return db.execute(
                "SELECT COUNT(*) FROM kit_records WHERE user_id=? AND kit_id=?",
                (user_id, kit_id),
            ).fetchone()[0]
